import {
  Deal,
  DealActivity,
  DealInstallment,
  DealPayment,
  DealStatus,
} from "../types";
import {
  dealSummaryDescriptionFromSql,
  legacyDescriptionFromMisfiledOfferNumber,
} from "../utils/dealTitleDisplay";
import { pickBestDealPayment } from "../utils/dealPaymentMatch";
import {
  assertDealPaymentsNotOverTotal,
  dedupeDealPaymentsForPatch,
} from "../utils/dealPaymentLimits";
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";

export type PaymentPostingDiagnostics = {
  payment_id: number;
  is_posted: boolean;
  journal_id: number | null;
  auto_posting_disabled: boolean;
  blockers: string[];
  can_auto_post: boolean;
};

type SqlDeal = any;

// Was previously hardcoded to 1. That caused a silent inconsistency:
// dealsService.subscribeToDeals returned tenant=1 data unconditionally while
// shipments/clearance read from resolveTenantId(). If localStorage.tenantId
// was set to a different value, the user saw deals but empty shipments/
// clearance — exactly the symptom in the owner's screenshot.
import { resolveTenantId as _resolveTenantId } from "../utils/tenantContext";
const getTenantId = () => _resolveTenantId();

function pickFirst(...values: any[]): string {
  for (const v of values) {
    if (v === null || v === undefined) continue;
    const s = String(v).trim();
    if (s) return s;
  }
  return "";
}

function mapStatusFromSql(status?: string): DealStatus {
  const s = String(status || "").toLowerCase();
  if (s.includes("cancel")) return "cancelled";
  // ج7: «Cleared» (بانتظار التخليص) مرحلة في مسار حي وليست نهاية —
  // كانت تُحسب completed فتقفل النموذج وتخفي الخريطة.
  if (s.includes("ship") || s.includes("clear")) return "shipped";
  if (s.includes("close")) return "completed";
  return "initial";
}

function mapStatusToSql(status?: DealStatus): string {
  if (!status) return "Open";
  if (status === "cancelled") return "Cancelled";
  if (status === "shipped" || status === "shipping_preparation" || status === "shipping_in_progress") return "Shipped";
  if (status === "completed") return "Closed";
  return "Open";
}

function mapPaymentFromSql(p: any, idx: number): DealPayment {
  const st = String(p?.status || "").toLowerCase();
  const isPosted = Boolean(p?.is_posted);
  const supplierConfirmed = Boolean(p?.confirmed_by_supplier);
  const payNumRaw = p?.payment_number;
  const payNum =
    payNumRaw != null && Number.isFinite(Number(payNumRaw))
      ? Number(payNumRaw)
      : undefined;
  const installmentNumber = payNum ?? idx + 1;
          return {
    id: String(p?.id ?? `p-${idx}`),
    type: p?.title || `payment_${idx + 1}`,
    installmentNumber,
    installmentId:
      Number.isFinite(payNum as number) && payNum != null
        ? `sql-inst-${payNum}`
        : undefined,
    amount: Number(p?.amount || 0),
    usdToIls: Number(p?.usd_to_ils || 0),
    transferCost: Number(p?.transfer_cost || 0),
    paymentDate: p?.transfer_date || p?.due_date || new Date().toISOString(),
    paymentConfirmationDate: p?.confirmation_date,
    notes: p?.notes || "",
    alibabaClaimImage: p?.claim_doc || p?.alibaba_claim_image,
    bankSwiftImage: p?.bank_swift_image,
    /** فعلياً من عمود SQL — لا نخلط حالة Paid (بعد السليب) مع تأكيد المورد */
    confirmedBySupplier: supplierConfirmed,
    isPosted,
    journalId:
      p?.journal != null && typeof p.journal === "object"
        ? Number(p.journal?.id)
        : p?.journal_id != null
          ? Number(p.journal_id)
          : p?.journal_id_display != null
            ? Number(p.journal_id_display)
            : undefined,
    confirmedAt: p?.confirmation_date,
    supplierConfirmationImage: p?.supplier_confirmation_image,
    supplierNotes: p?.supplier_notes || "",
    cashBoxId: p?.cash_box_external_id || undefined,
  };
}

function paymentsAreDuplicateFullDeal(
  payments: DealPayment[],
  dealTotal: number
): boolean {
  const total = Number(dealTotal || 0);
  if (payments.length < 2 || total <= 0) return false;
  const eps = Math.max(0.01, total * 0.005);
  return payments.every((p) => Math.abs(Number(p.amount || 0) - total) < eps);
}

/** أقساط من دفعات SQL — معرفات ثابتة حتى يطابقها الواجهة بعد إعادة التحميل */
function buildInstallmentsFromSqlPayments(
  payments: DealPayment[],
  totalAmount: number,
  planEnabled: boolean
): DealInstallment[] {
  if (!planEnabled) return [];
  const total = Number(totalAmount || 0);
  const now = new Date().toISOString();
  if (payments.length > 0) {
    if (paymentsAreDuplicateFullDeal(payments, total)) {
      const best = pickBestDealPayment(payments);
      const paid = Boolean(
        best &&
          (best.bankSwiftImage ||
            best.confirmedBySupplier ||
            best.isPosted)
      );
      return [
        {
          id: "sql-inst-1",
          installmentNumber: 1,
          percentage: total > 0 ? 100 : 0,
          amount: total,
          status: paid ? "paid" : "unpaid",
          createdAt: now,
          updatedAt: now,
        } as DealInstallment,
      ];
    }

    const byNum = new Map<number, DealPayment[]>();
    const sorted = [...payments].sort(
      (a, b) =>
        (a.installmentNumber ?? 999) - (b.installmentNumber ?? 999)
    );
    for (const p of sorted) {
      const n = p.installmentNumber ?? sorted.indexOf(p) + 1;
      if (!byNum.has(n)) byNum.set(n, []);
      byNum.get(n)!.push(p);
    }

    const rows: DealInstallment[] = [];
    const nums = [...byNum.keys()].sort((a, b) => a - b);
    for (const n of nums) {
      const group = byNum.get(n)!;
      const best = pickBestDealPayment(group);
      let amt = group.reduce((s, p) => s + Number(p.amount || 0), 0);
      if (amt > total + Math.max(0.01, total * 0.01)) {
        const maxOne = Math.max(...group.map((p) => Number(p.amount || 0)));
        amt = Math.min(total, maxOne);
      }
      const pct =
        total > 0 ? Number(((amt / total) * 100).toFixed(2)) : 0;
      const paid = Boolean(
        best &&
          (best.bankSwiftImage ||
            best.confirmedBySupplier ||
            best.isPosted)
      );
      rows.push({
        id: `sql-inst-${n}`,
        installmentNumber: n,
        percentage: pct,
        amount: amt,
        status: paid ? "paid" : "unpaid",
        createdAt: now,
        updatedAt: now,
      } as DealInstallment);
    }
    /**
     * بعد حذف دفعات من SQL تبقى أقساط فقط لما وُجد من سجلات — النسب لا تُجمَّع 100%
     * فيُقفل التحقق و«إضافة دفعة». نكمِّل بقية الصفقة كقسط(أقساط) غير مدفوعة.
     */
    const sumPct = rows.reduce((s, r) => s + Number(r.percentage || 0), 0);
    const sumAmt = rows.reduce((s, r) => s + Number(r.amount || 0), 0);
    if (total > 0.005 && (sumPct < 99.9 || sumAmt < total - 0.02)) {
      const remPct = Math.max(0, Number((100 - sumPct).toFixed(2)));
      const remAmt = Math.max(0, Number((total - sumAmt).toFixed(2)));
      if (remPct > 0.05 || remAmt > 0.05) {
        const maxNum = rows.reduce((m, r) => Math.max(m, r.installmentNumber ?? 0), 0);
        rows.push({
          id: `sql-inst-${maxNum + 1}`,
          installmentNumber: maxNum + 1,
          percentage: remPct,
          amount: remAmt,
          status: "unpaid",
          createdAt: now,
          updatedAt: now,
        } as DealInstallment);
      }
    }
    return rows;
  }
  return [
    {
      id: "sql-inst-1",
      installmentNumber: 1,
      percentage: 100,
      amount: total,
      status: "unpaid",
      createdAt: now,
      updatedAt: now,
    } as DealInstallment,
  ];
}

function mapItemFromSql(i: any, idx: number) {
  const qty = Number(i?.quantity || 0);
  const unit = Number(i?.unit_price || 0);
  const rawUrls = i?.image_urls ?? i?.imageUrls;
  const imageUrls = Array.isArray(rawUrls)
    ? rawUrls.map((u: any) => String(u || "").trim()).filter(Boolean)
    : [];
        return {
    id: String(i?.id ?? `i-${idx}`),
    itemId: String(i?.product ?? i?.id ?? ""),
    name: i?.product_name || "صنف",
    categoryId: "",
    categoryName: "",
    specifications: i?.notes || "",
    imageUrls,
    quantity: qty,
    unitPrice: unit,
    totalPrice: Number(i?.total_price || qty * unit),
    notes: i?.notes || "",
  };
}

function mapDealFromSql(d: SqlDeal): Deal {
  const payments = (d?.payments || []).map((p: any, idx: number) => mapPaymentFromSql(p, idx));
  const items = (d?.items || []).map((i: any, idx: number) => mapItemFromSql(i, idx));
  const quoteImagesRaw = d?.quote_images ?? d?.quoteImages;
  const quoteImages = Array.isArray(quoteImagesRaw)
    ? quoteImagesRaw.map((u: any) => String(u || "").trim()).filter(Boolean)
    : [];
  const quotePdfsRaw = d?.quote_pdfs ?? d?.quotePdfs;
  const quotePdfs = Array.isArray(quotePdfsRaw)
    ? quotePdfsRaw
        .map((row: any) => ({
          name: String(row?.name || "quote.pdf"),
          url: String(row?.url || row?.file_path || "").trim(),
          size: Number(row?.size || 0),
          type: String(row?.type || "application/pdf"),
        }))
        .filter((x) => x.url)
    : [];
  const totalAmount = Number(d?.total_amount || 0);
  const paid = payments.reduce((s, p) => s + Number(p.amount || 0), 0);
  const partnerField = d?.partner;
  const partnerId =
    typeof partnerField === "object" && partnerField !== null
      ? partnerField.id
      : partnerField;
  const dealDescriptionResolved =
    dealSummaryDescriptionFromSql(d?.description, d?.notes) ||
    legacyDescriptionFromMisfiledOfferNumber(d?.original_offer_number);
        return {
    id: String(d?.id),
    dealNumber: d?.ref_number || `D-${d?.id}`,
    priceOfferId: d?.price_offer_id || "",
    originalOfferNumber: pickFirst(
      d?.original_offer_number,
      d?.originalOfferNumber,
      d?.offer_number,
      d?.offerNumber,
      d?.deal_title,
      d?.dealTitle,
      d?.title
    ),
    supplierId: String(partnerId || d?.partner_id || d?.PartnerID || d?.partner_name || ""),
    factoryName: d?.factory_name || d?.partner_name || d?.partner?.name || "",
    supplierInvoiceNumber: pickFirst(d?.supplier_invoice_number, d?.supplierInvoiceNumber, d?.pi_number, d?.piNumber),
    quoteImages: quoteImages.length ? quoteImages : undefined,
    quotePdfs: quotePdfs.length ? quotePdfs : undefined,
    status: mapStatusFromSql(d?.status),
    installments: buildInstallmentsFromSqlPayments(
      payments,
      totalAmount,
      Boolean(d?.installment_plan_enabled)
    ),
    installmentPlanEnabled: Boolean(d?.installment_plan_enabled),
    currentInstallmentNumber: d?.current_installment_number || undefined,
    payments,
    items,
    totalAmount,
    remainingAmount: Math.max(0, Number(d?.remaining_amount || totalAmount - paid)),
    subtotal: Number(d?.subtotal || totalAmount),
    shippingCost: Number(d?.shipping_cost_estimate || 0),
    shippingIncluded: Boolean(d?.is_shipping_included),
    discountAmount: Number(d?.discount_amount || 0),
    taxRate: Number(d?.tax_rate || 0),
    taxAmount: Number(d?.tax_amount || 0),
    taxType: d?.tax_type === "amount" ? "amount" : "percentage",
    shippingMethod: pickFirst(d?.shipping_method, d?.shippingMethod),
    alibabaOrderLink: pickFirst(d?.alibaba_link, d?.alibabaOrderLink, d?.alibaba_link_url, d?.alibabaLink),
    dealDescription: dealDescriptionResolved,
    /* الملاحظات الكاملة منفصلة عن العنوان المعروض */
    internalNotes: pickFirst(d?.internal_notes, d?.internalNotes, d?.notes),
    paymentMethod: pickFirst(d?.payment_method, d?.paymentMethod),
    warrantyDuration: d?.warranty_duration || undefined,
    totalWeight: Number(d?.total_weight || 0) || undefined,
    totalVolume: Number(d?.total_cbm ?? 0),
    totalWeightKg: Number(d?.total_weight_kg || 0) || undefined,
    certificates: d?.certificates || "",
    shipmentNotes: d?.shipment_notes || "",
    dealDate: d?.order_date,
    firstPaymentDate: d?.first_payment_date || undefined,
    paymentDate: d?.payment_date || undefined,
    productionDays: d?.production_days || 0,
    deliveryDays: d?.delivery_days || 0,
    startedProductionAt: d?.started_production_at || undefined,
    statusHistory: [],
    activityLog: [],
    createdBy: String(d?.created_by || ""),
    createdAt: d?.created_at || new Date().toISOString(),
    updatedAt: d?.created_at || new Date().toISOString(),
    updatedBy: "",
    supplierSnapshot: {
      /* اسم الشريك في partners = غالباً الاسم المعروف محلياً / بالعربي */
      alias: pickFirst(d?.partner_name, d?.partner?.name)?.trim() || undefined,
      tradeName: pickFirst(
        d?.factory_name,
        d?.partner_legal_name,
        d?.partner?.legal_name,
        d?.partner_name
      )?.trim() || undefined,
      legalName: pickFirst(d?.partner_legal_name, d?.partner?.legal_name)?.trim() || undefined,
    },
    shippingWorkflowStatus: d?.shipping_workflow_status || null,
    linkedShipment: d?.linked_shipment
      ? {
          id: Number(d.linked_shipment.id),
          shipmentNumber: String(d.linked_shipment.shipment_number || ""),
          shipmentName: String(d.linked_shipment.shipment_name || ""),
        }
      : null,
  };
}

function mapDealToSqlPayload(deal: Partial<Deal>): Record<string, any> {
  const items = (deal.items || []).map((i: any) => ({
    id: i.id && /^\d+$/.test(String(i.id)) ? Number(i.id) : undefined,
    product: i.itemId && /^\d+$/.test(String(i.itemId)) ? Number(i.itemId) : undefined,
    quantity: Number(i.quantity || 0),
    unit_price: Number(i.unitPrice || 0),
    notes: i.notes || i.specifications || "",
  }));

  const payments = (deal.payments || []).map((p: any, idx: number) => {
    const swift =
      p.bankSwiftImage && String(p.bankSwiftImage).trim()
        ? String(p.bankSwiftImage).trim().slice(0, 500)
        : undefined;
    const claimDoc =
      p.alibabaClaimImage && String(p.alibabaClaimImage).trim()
        ? String(p.alibabaClaimImage).trim().slice(0, 500)
        : undefined;
    const confDateRaw = p.confirmedAt || p.paymentConfirmationDate;
    const confirmation_date = confDateRaw
      ? String(confDateRaw).slice(0, 10)
      : null;
    const payNo =
      Number(p.installmentNumber) > 0 ? Number(p.installmentNumber) : idx + 1;
        return {
      id: p.id && /^\d+$/.test(String(p.id)) ? Number(p.id) : undefined,
      payment_number: payNo,
      title: p.type || p.title || `Payment ${idx + 1}`,
      amount: Number(p.amount || 0),
      transfer_date: p.paymentDate ? String(p.paymentDate).slice(0, 10) : null,
      due_date: p.paymentDate ? String(p.paymentDate).slice(0, 10) : null,
      // Paid يفعّل ترحيل التلقائي — يجب أن يصل لـ SQL مع السليب والصندوق
      status: p.confirmedBySupplier
        ? "Confirmed"
        : swift
          ? "Paid"
          : "Pending",
      notes: p.notes || "",
      cash_box_external_id: p.cashBoxId || p.cash_box_external_id || undefined,
      ...(swift ? { bank_swift_image: swift } : {}),
      ...(claimDoc ? { claim_doc: claimDoc } : {}),
      confirmed_by_supplier: Boolean(p.confirmedBySupplier),
      usd_to_ils: Number(p.usdToIls ?? p.usd_to_ils ?? 3.5),
      transfer_cost: Number(p.transferCost ?? p.transfer_cost ?? 0),
      ...(p.supplierConfirmationImage && String(p.supplierConfirmationImage).trim()
        ? {
            supplier_confirmation_image: String(p.supplierConfirmationImage)
              .trim()
              .slice(0, 500),
          }
        : {}),
      ...(p.supplierNotes ? { supplier_notes: String(p.supplierNotes) } : {}),
      ...(confirmation_date && confirmation_date.length >= 8
        ? { confirmation_date }
        : {}),
        };
      });

  const supplierRaw = (deal.supplierId || "").toString();
  const partner = /^\d+$/.test(supplierRaw) ? Number(supplierRaw) : undefined;

  return {
    ref_number: deal.dealNumber,
    partner,
    order_date: (deal.dealDate || new Date().toISOString().slice(0, 10)).slice(0, 10),
    status: mapStatusToSql(deal.status),
    description: String(deal.dealDescription ?? "").trim().slice(0, 255),
    notes: deal.internalNotes || "",
    currency: 1,
    items,
    payments,
    subtotal: Number(deal.subtotal || 0),
    total_amount: Number(deal.totalAmount || 0),
    remaining_amount: Number(deal.remainingAmount || 0),
    shipping_cost_estimate: Number(deal.shippingCost || 0),
    discount_amount: Number(deal.discountAmount || 0),
    tax_rate: Number(deal.taxRate || 0),
    tax_amount: Number(deal.taxAmount || 0),
    tax_type: deal.taxType === "amount" ? "amount" : "percentage",
    payment_method: deal.paymentMethod || "T/T",
    shipping_method: deal.shippingMethod || "Sea",
    alibaba_link: deal.alibabaOrderLink || "",
    installment_plan_enabled: Boolean(deal.installmentPlanEnabled),
    price_offer_id: deal.priceOfferId || "",
    original_offer_number: deal.originalOfferNumber || "",
    supplier_invoice_number: deal.supplierInvoiceNumber || "",
    factory_name: deal.factoryName || "",
    shipment_notes: deal.shipmentNotes || "",
    total_weight: Number(deal.totalWeight || 0),
    total_cbm: Number(deal.totalVolume || 0),
    total_weight_kg: Number(deal.totalWeightKg || 0),
    production_days: Number(deal.productionDays || 0),
    delivery_days: Number(deal.deliveryDays || 0),
    warranty_duration: deal.warrantyDuration || null,
    certificates: deal.certificates || "",
    shipping_workflow_status: deal.shippingWorkflowStatus || null,
  };
}

function isNumericSqlPaymentId(id: string | number | undefined): boolean {
  if (id == null) return false;
  return /^\d+$/.test(String(id));
}

/** مطابقة معرفات الدفعة بين الواجهة والخادم (رقم JSON مقابل نص، إلخ) */
function sameDealPaymentId(a: unknown, b: unknown): boolean {
  return String(a ?? "") === String(b ?? "");
}

/**
 * بعد PATCH قد يُنشأ صف دفعة بمعرّف SQL جديد (كان الواجهة تستخدم tmp-…).
 * نحل المعرّف الصحيح لـ post_payment وواجهة التشخيص.
 */
function resolvePaymentIdForApi(
  requestedId: string,
  beforeRow: DealPayment | undefined,
  refreshedPayments: DealPayment[] | undefined
): string {
  const list = refreshedPayments || [];
  const direct = list.find((x) => String(x.id) === String(requestedId));
  if (direct && isNumericSqlPaymentId(direct.id)) {
    return String(direct.id);
  }
  if (isNumericSqlPaymentId(requestedId)) {
    return String(requestedId);
  }
  if (beforeRow) {
    const amt = Number(beforeRow.amount || 0);
    const inst = beforeRow.installmentNumber;
    const typ = String(beforeRow.type || "").trim();
    const candidates = list.filter((p) => {
      const sameAmt = Math.abs(Number(p.amount || 0) - amt) < 0.02;
      const sameInst =
        inst == null ||
        p.installmentNumber === inst ||
        Number(p.installmentNumber) === Number(inst);
      const sameType = !typ || String(p.type || "").trim() === typ;
      return sameAmt && sameInst && sameType;
    });
    const confirmed = candidates.find((p) => p.confirmedBySupplier);
    const pick = confirmed || candidates[0];
    if (pick && isNumericSqlPaymentId(pick.id)) {
      return String(pick.id);
    }
  }
  const numericRows = list.filter((p) => isNumericSqlPaymentId(p.id));
  if (numericRows.length === 1) {
    return String(numericRows[0].id);
  }
  return requestedId;
}

async function fetchDealsMapped(): Promise<Deal[]> {
  const rows = await apiGetList<SqlDeal>("logistics/deals/", { tenantId: getTenantId() });
  return rows.map(mapDealFromSql);
}

export const dealsService = {
  /** جلب قائمة الصفقات مرة واحدة — للتحديث الصريح بعد العمليات. */
  async listDeals(): Promise<Deal[]> {
    return fetchDealsMapped();
  },

  /**
   * كان polling كل 5 ثوانٍ لكل مشترك (مكلف، وكان يقلب وضع الواجهة — بق «اختفاء
   * التعديل»). الآن: تحميل عند الاشتراك + تحديث عند عودة التركيز/الظهور للتبويب
   * (يلتقط تعديلات التبويبات الأخرى بلا مؤقّت). `intervalMs` اختياري لمن يحتاج
   * تحديثاً دورياً صريحاً.
   */
  subscribeToDeals(
    callback: (deals: Deal[]) => void,
    opts?: { intervalMs?: number | null; refreshOnFocus?: boolean }
  ) {
    let alive = true;
    const load = async () => {
      try {
        const mapped = await fetchDealsMapped();
        if (alive) callback(mapped);
      } catch {
        if (alive) callback([]);
      }
    };
    load();
    const timer = opts?.intervalMs ? setInterval(load, opts.intervalMs) : null;
    const refreshOnFocus = opts?.refreshOnFocus ?? true;
    const onFocus = () => {
      if (document.visibilityState === "visible") void load();
    };
    if (refreshOnFocus && typeof window !== "undefined") {
      window.addEventListener("focus", onFocus);
      document.addEventListener("visibilitychange", onFocus);
    }
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
      if (refreshOnFocus && typeof window !== "undefined") {
        window.removeEventListener("focus", onFocus);
        document.removeEventListener("visibilitychange", onFocus);
      }
    };
  },

  async getDeal(dealId: string): Promise<Deal> {
    const row = await apiGetObject<SqlDeal>(`logistics/deals/${dealId}/`, { tenantId: getTenantId() });
    return mapDealFromSql(row);
  },

  async getDealActivities(_dealId: string): Promise<DealActivity[]> {
    return [];
  },

  async getNextDealNumber(): Promise<string> {
    const deals = await fetchDealsMapped();
    const nums = deals
      .map((d) => (d.dealNumber || "").match(/^D-(\d+)$/)?.[1])
      .filter(Boolean)
      .map((v) => Number(v));
    const next = (nums.length ? Math.max(...nums) : 0) + 1;
    return `D-${String(next).padStart(4, "0")}`;
  },

  async createDeal(dealData: Record<string, any>): Promise<string> {
    const toCreate = {
      ...dealData,
      dealNumber: dealData.dealNumber || (await this.getNextDealNumber()),
    };
    if (Array.isArray((toCreate as Partial<Deal>).payments)) {
      (toCreate as Partial<Deal>).payments = dedupeDealPaymentsForPatch(
        (toCreate as Partial<Deal>).payments || []
      );
    }
    assertDealPaymentsNotOverTotal(toCreate as Partial<Deal>);
    const payload = mapDealToSqlPayload(toCreate);
    if (!payload.partner) {
      throw new Error("المورد غير مرتبط بمعرف SQL صحيح");
    }
    const created = await apiPostObject<SqlDeal>(
      "logistics/deals/",
      payload,
      { tenantId: getTenantId() }
    );
    return String(created.id);
  },

  async updateDeal(
    dealId: string,
    updates: Partial<Deal>,
    _userId?: string,
    _userName?: string,
    _userRole?: string,
    _action?: string,
    _details?: string
  ): Promise<void> {
    const current = await this.getDeal(dealId);
    const merged = { ...current, ...updates };
    const payload = mapDealToSqlPayload(merged);
    delete payload.payments;
    await apiPatchObject(`logistics/deals/${dealId}/`, payload, { tenantId: getTenantId() });
  },

  /**
   * تحديث صفقة **مع** الدفعات — يُستخدم حصرياً من مسارات الدفع الصريحة
   * (addPayment, updatePaymentWithSwift, confirmPayment).
   */
  async _updateDealWithPayments(
    dealId: string,
    updates: Partial<Deal>
  ): Promise<void> {
    const current = await this.getDeal(dealId);
    const merged = { ...current, ...updates };
    const previousPaymentsDeduped = dedupeDealPaymentsForPatch(
      current.payments || []
    );
    if (Array.isArray(merged.payments)) {
      merged.payments = dedupeDealPaymentsForPatch(merged.payments);
    }
    assertDealPaymentsNotOverTotal(merged, previousPaymentsDeduped);
    const payload = mapDealToSqlPayload(merged);
    await apiPatchObject(`logistics/deals/${dealId}/`, payload, { tenantId: getTenantId() });
  },

  async updateDealStatus(
    dealId: string,
    newStatus: DealStatus,
    _userId?: string,
    _userName?: string,
    _userRole?: string,
    _notes?: string
  ): Promise<void> {
    await apiPatchObject(`logistics/deals/${dealId}/`, { status: mapStatusToSql(newStatus) }, { tenantId: getTenantId() });
  },

  /** مراحل الشحن/التصنيع (حقل shipping_workflow_status في SQL) */
  async patchShippingWorkflow(
    dealId: string,
    code: string
  ): Promise<void> {
    await apiPatchObject(
      `logistics/deals/${dealId}/`,
      { shipping_workflow_status: code },
      { tenantId: getTenantId() }
    );
  },

  async addPayment(
    dealId: string,
    payment: Omit<DealPayment, "id">,
    _userId?: string,
    _userName?: string,
    _userRole?: string
  ): Promise<string> {
    const deal = await this.getDeal(dealId);
    const base = dedupeDealPaymentsForPatch(deal.payments || []);
    const newPayment: DealPayment = { ...payment, id: `tmp-${Date.now()}` };
    await this._updateDealWithPayments(dealId, { payments: [...base, newPayment] });
    return newPayment.id;
  },

  async updatePaymentWithSwift(
    dealId: string,
    paymentId: string,
    updates: Partial<DealPayment>,
    _userId?: string,
    _userName?: string,
    _userRole?: string,
    _cashBoxId?: string
  ): Promise<void> {
    const deal = await this.getDeal(dealId);
    const cleaned = dedupeDealPaymentsForPatch(deal.payments || []);
    const payments = cleaned.map((p) =>
      sameDealPaymentId(p.id, paymentId) ? { ...p, ...updates } : p
    );
    await this._updateDealWithPayments(dealId, { payments });
  },

  async getPaymentPostingDiagnostics(
    dealId: string,
    paymentId: string
  ): Promise<PaymentPostingDiagnostics> {
    return apiGetObject<PaymentPostingDiagnostics>(
      `logistics/deals/${dealId}/payment-posting-diagnostics/${encodeURIComponent(String(paymentId))}/`,
      { tenantId: getTenantId() }
    );
  },

  /** ترحيل دفعة إلى المحاسبة (ينشئ قيداً ويربطه بالدفعة) — نفس مسار الخادم post_payment */
  async postDealPaymentToAccounting(
    dealId: string,
    paymentId: string,
    body?: { cash_box_external_id?: string; bank_account_id?: number }
  ): Promise<{ status?: string; journal_id?: number; error?: string }> {
    return apiPostObject(
      `logistics/deals/${dealId}/post_payment/${encodeURIComponent(String(paymentId))}/`,
      body || {},
      { tenantId: getTenantId() }
    );
  },

  /**
   * محاولة ترحيل الدفعة عبر API (بعد سليب/تأكيد) حتى لو كان الترحيل بالإشارة معطّلاً في .env.
   */
  async tryAutoPostDealPaymentAccounting(
    dealId: string,
    paymentId: string,
    opts?: { cashBoxExternalId?: string }
  ): Promise<{ journalId?: number; posted: boolean; blockers?: string[] }> {
    const pid = String(paymentId ?? "").trim();
    if (!/^\d+$/.test(pid)) {
      return { posted: false, blockers: ["معرّف الدفعة غير رقمي بعد — أعد فتح الصفقة."] };
    }
    let refreshed = await this.getDeal(dealId);
    let row = refreshed.payments?.find((p) => String(p.id) === pid);
    const jidRow = row?.journalId != null ? Number(row.journalId) : NaN;
    if (row?.isPosted && Number.isFinite(jidRow) && jidRow > 0) {
      return { posted: true, journalId: jidRow };
    }

    const body: Record<string, any> = {};
    const ext = opts?.cashBoxExternalId?.trim();
    if (ext) body.cash_box_external_id = ext.slice(0, 128);

    try {
      const res = await this.postDealPaymentToAccounting(dealId, pid, body);
      if (res?.journal_id != null) {
        return { posted: true, journalId: Number(res.journal_id) };
      }
      return { posted: false, blockers: ["لم يُرجع الخادم رقم القيد."] };
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/مرحلة بالفعل|already posted/i.test(msg)) {
        refreshed = await this.getDeal(dealId);
        row = refreshed.payments?.find((p) => String(p.id) === pid);
        const j = row?.journalId != null ? Number(row.journalId) : NaN;
        if (Number.isFinite(j) && j > 0) {
          return { posted: true, journalId: j };
        }
      }
      return { posted: false, blockers: [msg] };
    }
  },

  /**
   * ربط دفعة بقيد يومية أنشئ يدوياً (يظهر رابط القيد في الواجهة ويُعلَم الترحيل على الدفعة).
   */
  async linkDealPaymentJournal(
    dealId: string,
    paymentId: string,
    journalId: number
  ): Promise<{ status: string; journal_id?: number; payment_id?: number }> {
    return apiPostObject(
      `logistics/deals/${dealId}/link_payment_journal/${encodeURIComponent(String(paymentId))}/`,
      { journal_id: journalId },
      { tenantId: getTenantId() }
    );
  },

  async unpostDealPayment(
    dealId: string,
    paymentId: string,
    opts?: { reversalDate?: string }
  ): Promise<{
    reversal_journal_id?: number;
    voided_journal_id?: number;
    status?: string;
    accounting_note?: string;
  }> {
    return apiPostObject(
      `logistics/deals/${dealId}/unpost_payment/${encodeURIComponent(String(paymentId))}/`,
      {
        ...(opts?.reversalDate ? { reversal_date: opts.reversalDate } : {}),
      },
      { tenantId: getTenantId() }
    );
  },

  async confirmPayment(
    dealId: string,
    paymentId: string,
    _userId?: string,
    _userName?: string,
    _userRole?: string,
    supplierConfirmationImage?: string,
    supplierNotes?: string,
    paymentConfirmationDate?: string,
    _cashBoxId?: string
  ): Promise<{
    journalId?: number;
    message: string;
    postingBlockers?: string[];
    /** فتح قيد يومية جديد في المحاسبة — الترحيل يدوي من هناك */
    openManualJournal?: boolean;
  }> {
    const deal = await this.getDeal(dealId);
    const cleaned = dedupeDealPaymentsForPatch(deal.payments || []);
    const when = paymentConfirmationDate || new Date().toISOString();
    const payments = cleaned.map((p) =>
      sameDealPaymentId(p.id, paymentId)
        ? {
            ...p,
            confirmedBySupplier: true,
            supplierConfirmationImage,
            supplierNotes,
            paymentConfirmationDate: when,
            confirmedAt: when,
          }
        : p
    );
    await this._updateDealWithPayments(dealId, { payments });

    const row = payments.find((p) => sameDealPaymentId(p.id, paymentId));
    const refreshed = await this.getDeal(dealId);
    const effectivePaymentId = resolvePaymentIdForApi(
      paymentId,
      row,
      refreshed.payments
    );

    const manualHint =
      "يمكنك فتح قيد يومية جديد يدوياً من المحاسبة إن احتجت، أو استخدم «ربط قيد يدوي» في سجل المدفوعات.";

    if (!isNumericSqlPaymentId(effectivePaymentId)) {
      return {
        message:
          "تم حفظ تأكيد المورد.\n\n" +
          "(تنبيه: رقم الدفعة في الخادم غير واضح بعد — أعد فتح الصفقة.)\n\n" +
          manualHint,
        openManualJournal: true,
      };
    }

    const effRow = refreshed.payments?.find(
      (p) => String(p.id) === String(effectivePaymentId)
    );
    const postTry = await this.tryAutoPostDealPaymentAccounting(
      dealId,
      String(effectivePaymentId),
      {
        cashBoxExternalId: effRow?.cashBoxId
          ? String(effRow.cashBoxId).trim()
          : undefined,
      }
    );

    if (postTry.posted && postTry.journalId != null) {
      return {
        message:
          "تم حفظ تأكيد المورد وإنشاء قيد المحاسبة وربطه بالدفعة تلقائياً.",
        journalId: postTry.journalId,
        openManualJournal: false,
      };
    }

    return {
      message:
        "تم حفظ تأكيد المورد.\n\n" +
        "لم يُنجَز الترحيل التلقائي عبر الخادم:\n" +
        (postTry.blockers?.length
          ? postTry.blockers.map((b, i) => `${i + 1}. ${b}`).join("\n")
          : "—") +
        "\n\n" +
        manualHint,
      openManualJournal: true,
      postingBlockers: postTry.blockers,
    };
  },

  async cancelPayment(
    dealId: string,
    paymentId: string,
    _userId?: string,
    _userName?: string,
    _userRole?: string
  ): Promise<void> {
    const pid = String(paymentId ?? "").trim();
    if (!pid) {
      throw new Error("معرّف الدفعة مفقود.");
    }

    const fresh = await this.getDeal(dealId);
    const row = fresh.payments?.find((p) => String(p.id) === pid);

    if (row?.isPosted) {
      throw new Error(
        "لا يمكن حذف دفعة مرحّلة محاسبياً. استخدم «إلغاء الترحيل (مدير)» أولاً ثم احذف من السجل."
      );
    }

    if (/^\d+$/.test(pid)) {
      try {
        await apiPostObject(
          `logistics/deals/${dealId}/remove_payment/${encodeURIComponent(pid)}/`,
          {},
          { tenantId: getTenantId() }
        );
        return;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (/غير موجود|not found|404/i.test(msg) || /API error:\s*404/i.test(msg)) {
          return;
        }
        throw e;
      }
    }

    if (!row) {
      return;
    }

    const cleaned = dedupeDealPaymentsForPatch(fresh.payments || []);
    const payments = cleaned.filter((p) => !sameDealPaymentId(p.id, paymentId));
    await this._updateDealWithPayments(dealId, { payments });
  },

  async checkDealUniqueness(invoiceNumber?: string, alibabaLink?: string, currentDealId?: string) {
    const deals = await fetchDealsMapped();
    const inv = (invoiceNumber || "").trim();
    const link = (alibabaLink || "").trim();
    if (inv) {
      const duplicate = deals.find((d) => d.id !== currentDealId && (d.supplierInvoiceNumber || "").trim() === inv);
      if (duplicate) return { isUnique: false, errorField: "invoice", existingDealNumber: duplicate.dealNumber };
    }
    if (link) {
      const duplicate = deals.find((d) => d.id !== currentDealId && (d.alibabaOrderLink || "").trim() === link);
      if (duplicate) return { isUnique: false, errorField: "link", existingDealNumber: duplicate.dealNumber };
    }
    return { isUnique: true };
  },

  async deleteDeal(dealId: string): Promise<void> {
    await apiDelete(`logistics/deals/${dealId}/`, { tenantId: getTenantId() });
  },
};

