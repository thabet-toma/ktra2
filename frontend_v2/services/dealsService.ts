import { Deal, DealActivity, DealPayment, DealStatus } from "../types";
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";

type SqlDeal = any;

const TENANT_ID = 1;

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
  if (s.includes("ship")) return "shipped";
  if (s.includes("close") || s.includes("clear")) return "completed";
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
  return {
    id: String(p?.id ?? `p-${idx}`),
    type: p?.title || `payment_${idx + 1}`,
    amount: Number(p?.amount || 0),
    usdToIls: Number(p?.usd_to_ils || 0),
    transferCost: Number(p?.transfer_cost || 0),
    paymentDate: p?.transfer_date || p?.due_date || new Date().toISOString(),
    paymentConfirmationDate: p?.confirmation_date,
    notes: p?.notes || "",
    bankSwiftImage: p?.bank_swift_image,
    confirmedBySupplier: st.includes("confirm"),
    confirmedAt: p?.confirmation_date,
    supplierConfirmationImage: p?.supplier_confirmation_image,
    supplierNotes: p?.supplier_notes || "",
  };
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
    factoryName: d?.partner_name || d?.partner?.name || d?.factory_name || "",
    supplierInvoiceNumber: pickFirst(d?.supplier_invoice_number, d?.supplierInvoiceNumber, d?.pi_number, d?.piNumber),
    quoteImages: quoteImages.length ? quoteImages : undefined,
    quotePdfs: quotePdfs.length ? quotePdfs : undefined,
    status: mapStatusFromSql(d?.status),
    installments: [],
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
    internalNotes: pickFirst(d?.notes, d?.internal_notes, d?.internalNotes, d?.description),
    paymentMethod: pickFirst(d?.payment_method, d?.paymentMethod),
    warrantyDuration: d?.warranty_duration || undefined,
    totalWeight: Number(d?.total_weight || 0) || undefined,
    totalVolume: Number(d?.total_cbm || 0) || undefined,
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
      tradeName: pickFirst(d?.partner_name, d?.partner?.name, d?.factory_name),
      alias: pickFirst(d?.partner?.alias, d?.partner_alias),
    },
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

  const payments = (deal.payments || []).map((p: any, idx: number) => ({
    id: p.id && /^\d+$/.test(String(p.id)) ? Number(p.id) : undefined,
    payment_number: idx + 1,
    title: p.type || p.title || `Payment ${idx + 1}`,
    amount: Number(p.amount || 0),
    transfer_date: p.paymentDate ? String(p.paymentDate).slice(0, 10) : null,
    due_date: p.paymentDate ? String(p.paymentDate).slice(0, 10) : null,
    status: p.confirmedBySupplier ? "Confirmed" : "Pending",
    notes: p.notes || "",
  }));

  const supplierRaw = (deal.supplierId || "").toString();
  const partner = /^\d+$/.test(supplierRaw) ? Number(supplierRaw) : undefined;

  return {
    ref_number: deal.dealNumber,
    partner,
    order_date: (deal.dealDate || new Date().toISOString().slice(0, 10)).slice(0, 10),
    status: mapStatusToSql(deal.status),
    description: deal.internalNotes || "",
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
  };
}

async function fetchDealsMapped(): Promise<Deal[]> {
  const rows = await apiGetList<SqlDeal>("logistics/deals/", { tenantId: TENANT_ID });
  return rows.map(mapDealFromSql);
}

export const dealsService = {
  subscribeToDeals(callback: (deals: Deal[]) => void) {
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
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  },

  async getDeal(dealId: string): Promise<Deal> {
    const row = await apiGetObject<SqlDeal>(`logistics/deals/${dealId}/`, { tenantId: TENANT_ID });
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
    const payload = mapDealToSqlPayload({
      ...dealData,
      dealNumber: dealData.dealNumber || (await this.getNextDealNumber()),
    });
    if (!payload.partner) {
      throw new Error("المورد غير مرتبط بمعرف SQL صحيح");
    }
    const created = await apiPostObject<SqlDeal>("logistics/deals/", payload, { tenantId: TENANT_ID });
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
    await apiPatchObject(`logistics/deals/${dealId}/`, payload, { tenantId: TENANT_ID });
  },

  async updateDealStatus(
    dealId: string,
    newStatus: DealStatus,
    _userId?: string,
    _userName?: string,
    _userRole?: string,
    _notes?: string
  ): Promise<void> {
    await apiPatchObject(`logistics/deals/${dealId}/`, { status: mapStatusToSql(newStatus) }, { tenantId: TENANT_ID });
  },

  async addPayment(
    dealId: string,
    payment: Omit<DealPayment, "id">,
    _userId?: string,
    _userName?: string,
    _userRole?: string
  ): Promise<string> {
      const deal = await this.getDeal(dealId);
    const newPayment: DealPayment = { ...payment, id: `tmp-${Date.now()}` };
    await this.updateDeal(dealId, { payments: [...(deal.payments || []), newPayment] });
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
    const payments = (deal.payments || []).map((p) => (p.id === paymentId ? { ...p, ...updates } : p));
    await this.updateDeal(dealId, { payments });
  },

  async confirmPayment(
    dealId: string,
    paymentId: string,
    _userId?: string,
    _userName?: string,
    _userRole?: string,
    supplierConfirmationImage?: string,
    supplierNotes?: string,
    paymentConfirmationDate?: string
  ): Promise<void> {
    const deal = await this.getDeal(dealId);
    const payments = (deal.payments || []).map((p) =>
      p.id === paymentId
        ? {
            ...p,
            confirmedBySupplier: true,
            supplierConfirmationImage,
            supplierNotes,
            paymentConfirmationDate: paymentConfirmationDate || new Date().toISOString(),
          }
        : p
    );
    await this.updateDeal(dealId, { payments });
  },

  async cancelPayment(
    dealId: string,
    paymentId: string,
    _userId?: string,
    _userName?: string,
    _userRole?: string
  ): Promise<void> {
    const deal = await this.getDeal(dealId);
    const payments = (deal.payments || []).filter((p) => p.id !== paymentId);
    await this.updateDeal(dealId, { payments });
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
    await apiDelete(`logistics/deals/${dealId}/`, { tenantId: TENANT_ID });
  },
};

