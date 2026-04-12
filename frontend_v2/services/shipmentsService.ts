import { Shipment, DealPayment, Deal } from "../types";
import { effectiveDealTitleForDisplay } from "../utils/dealTitleDisplay";
import { assertShipmentPaymentsNotOverTotal } from "../utils/dealPaymentLimits";
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const getTenantId = () => resolveTenantId();

/**
 * يطابق Django: LogisticsShipment.total_volume / total_weight_kg — Decimal(10,3).
 * بدونه قد يرفض الخادم الطلب (أرقام عشرية طويلة من JS، أو تجاوز 7 خانات صحيحة).
 */
function toSqlVolumeOrWeight10_3(value: unknown): number {
  const x = Number(value);
  if (!Number.isFinite(x)) return 0;
  const rounded = Math.round(x * 1000) / 1000;
  const max = 9999999.999;
  return Math.min(max, Math.max(0, rounded));
}

/** مسار الواجهة (agent_warehouse, at_sea, …) → عمود logistics_shipments.Status */
export function routeStatusToSqlShipmentStatus(
  route: string,
  shippingType: string
): string {
  const r = (route || "").toLowerCase();
  if (["released", "delivered_local"].includes(r)) return "Cleared";
  if (r === "israel_customs_clearance") return "Clearing";
  if (["arrived_port", "arrived_airport"].includes(r)) return "Arrived";
  if (
    [
      "on_board",
      "at_sea",
      "departed",
      "in_transit",
      "delivered_to_shipping_company",
    ].includes(r)
  )
    return "In-Transit";
  /* مستودع الوكيل + جمارك الصين وغيرها قبل الإبحار = Pending */
  return "Pending";
}

/** ترتيب مسار الشحنة (بحري / جوي) — للمقارنة عند التقديم التلقائي دون تراجع */
const SEA_ROUTE_ORDER = [
  "agent_warehouse",
  "china_customs_clearance",
  "on_board",
  "at_sea",
  "arrived_port",
  "israel_customs_clearance",
  "released",
  "delivered_local",
];
const AIR_ROUTE_ORDER = [
  "agent_warehouse",
  "delivered_to_shipping_company",
  "china_customs_clearance",
  "departed",
  "in_transit",
  "arrived_airport",
  "israel_customs_clearance",
  "released",
  "delivered_local",
];

export function shipmentRouteOrder(shippingType: string): string[] {
  return shippingType === "air" ? AIR_ROUTE_ORDER : SEA_ROUTE_ORDER;
}

/** لا نرجع للخلف: نأخذ الأبعد في المسار بين الحالية والحد الأدنى المطلوب */
export function advanceShipmentRouteAtLeast(
  current: string | undefined,
  minimumTarget: string,
  shippingType: string
): string {
  const seq = shipmentRouteOrder(shippingType);
  const ic = current ? seq.indexOf(current) : -1;
  const im = seq.indexOf(minimumTarget);
  if (im < 0) return (current || minimumTarget || "agent_warehouse").trim() || "agent_warehouse";
  const base = ic < 0 ? 0 : ic;
  const ix = Math.max(base, im);
  return seq[Math.min(ix, seq.length - 1)];
}

/** عند غياب shipment_route_status: اشتقاق مرحلة افتراضية من الحالة الخشنة */
export function defaultRouteFromSqlShipmentStatus(
  statusLower: string,
  shippingType: string
): string {
  const s = (statusLower || "").toLowerCase().trim().replace(/\s+/g, "-");
  const air = shippingType === "air";
  switch (s) {
    case "in-transit":
      return air ? "in_transit" : "at_sea";
    case "arrived":
      return air ? "arrived_airport" : "arrived_port";
    case "clearing":
      return "israel_customs_clearance";
    case "cleared":
      return "released";
    default:
      return "agent_warehouse";
  }
}

function mapShipmentFromSql(s: any): Shipment {
  const allocByDealId = new Map<
    string,
    { distributed: number; extra: number }
  >();
  for (const row of s.shipment_deal_allocations || []) {
    const did = row.deal != null ? String(row.deal) : "";
    if (!did) continue;
    allocByDealId.set(did, {
      distributed: Number(row.allocated_shipping_cost || 0),
      extra: Number(row.extra_costs || 0),
    });
  }
  const deals = (s.deals || []).map((d: any) => {
    const dealNumber = d.ref_number || `D-${d.id}`;
    const descRaw = String(d.description || "").trim();
    const alloc = allocByDealId.get(String(d.id));
    return {
      dealId: String(d.id),
      dealNumber,
      originalOfferNumber: d.original_offer_number || "",
      totalAmount: Number(d.total_amount || 0),
      /** مصدر الحقيقة: حقول الصفقة في SQL (total_cbm / الوزن) — نفس dealsService */
      totalVolume: Number(d.total_cbm ?? 0),
      totalWeightKg: Number(d.total_weight_kg ?? d.total_weight ?? 0),
      distributedCost: alloc?.distributed ?? 0,
      extraCosts: alloc?.extra ?? 0,
      notes: d.notes || "",
      dealDescriptionRaw: descRaw || undefined,
      displayTitle: effectiveDealTitleForDisplay({
        description: d.description,
        notes: d.notes,
        original_offer_number: d.original_offer_number,
        ref_number: dealNumber,
      }),
      factoryName: String(d.factory_name || "").trim() || undefined,
      partnerName: String(
        d.partner_name || (typeof d.partner === "object" && d.partner?.name) || ""
      ).trim() || undefined,
    };
  });
  /** إجمالي الشحنة = مجموع صفقاتها (لا أعمدة shipment.total_volume القديمة وحدها) */
  const derivedVolume =
    deals.length > 0
      ? deals.reduce((sum, d) => sum + (Number(d.totalVolume) || 0), 0)
      : Number(s.total_volume || 0);
  const derivedWeightKg =
    deals.length > 0
      ? deals.reduce((sum, d) => sum + (Number(d.totalWeightKg) || 0), 0)
      : Number(s.total_weight_kg || 0);
  const payments = (s.payments || []).map((p: any, idx: number) => {
    const jidRaw =
      p.journal ??
      p.journal_id ??
      p.JournalID ??
      p.journal_id_display;
    const jid =
      jidRaw != null && jidRaw !== ""
        ? Number(jidRaw)
        : NaN;
    return {
      id: String(p.id ?? `p-${idx}`),
      type: p.title || `payment_${idx + 1}`,
      installmentNumber:
        Number(p.payment_number) > 0 ? Number(p.payment_number) : idx + 1,
      amount: Number(p.amount || 0),
      usdToIls: Number(p.usd_to_ils || 0),
      transferCost: Number(p.transfer_cost || 0),
      paymentDate: p.transfer_date || p.due_date || new Date().toISOString(),
      paymentConfirmationDate: p.confirmation_date,
      notes: p.notes || "",
      bankSwiftImage: p.bank_swift_image,
      alibabaClaimImage: p.claim_doc || undefined,
      cashBoxId: p.cash_box_external_id || undefined,
      confirmedBySupplier: String(p.status || "").toLowerCase().includes("confirm"),
      confirmedAt: p.confirmation_date,
      isPosted: Boolean(p.is_posted),
      journalId: Number.isFinite(jid) && jid > 0 ? jid : undefined,
    };
  });
  const paid = payments.reduce((sum: number, p: any) => sum + Number(p.amount || 0), 0);
  const total = Number(s.total_shipping_cost_usd || 0);
  let status: Shipment["status"] = "draft";
  if (paid >= total && total > 0) status = "paid";
  else if (paid > 0) status = "partially_paid";
  else if (payments.length) status = "payment_pending";

  const shippingTypeSql = s.shipping_type === "air" ? "air" : "sea";
  const coarseNorm = String(s.status || "Pending")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-");
  const routeSaved = s.shipment_route_status
    ? String(s.shipment_route_status).trim()
    : "";
  const effectiveRouteStatus =
    routeSaved ||
    defaultRouteFromSqlShipmentStatus(coarseNorm, shippingTypeSql);

  return {
    id: String(s.id),
    shipmentNumber: s.shipment_number || `S-${s.id}`,
    agentShipmentNumber: s.agent_shipment_number || "",
    shippingAgentId: String(s.shipping_agent || ""),
    shippingAgentName: s.agent_name || "",
    israeliSideName: s.israeli_side_name || "",
    shippingInfo: {
      shippingType: shippingTypeSql,
      shipName: s.ship_name || "",
      containerNumber: s.container_number || "",
      departureDate: s.departure_date || "",
      arrivalDate: s.arrival_date || "",
      internationalShippingCompany: s.international_shipping_company || "",
      billOfLadingNumber: s.bill_of_lading || "",
      billOfLadingFile: s.bill_of_lading_file || "",
      flightNumber: s.flight_number || "",
      airwayBillNumber: s.airway_bill_number || "",
      airwayBillFile: s.airway_bill_file || "",
      fromTerm: s.from_term || "",
      toTerm: s.to_term || "",
      imoNumber: s.imo_number || "",
      mmsiNumber: s.mmsi_number || "",
      trackingLink: s.tracking_link || "",
      shipmentStatus: {
        status: effectiveRouteStatus,
        statusDate: s.arrival_date || s.departure_date || "",
      },
    },
    deals,
    totalShippingCostUsd: total,
    totalVolume: derivedVolume,
    totalWeightKg: derivedWeightKg,
    status,
    notes: s.notes || "",
    shipmentName: s.shipment_name || "",
    pricingMethod: s.pricing_method || "total",
    unitType: s.unit_type || "cbm",
    pricePerUnit: Number(s.price_per_unit || 0),
    installments: [],
    installmentPlanEnabled: Boolean(s.installment_plan_enabled),
    payments,
    remainingAmount: Math.max(0, total - paid),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    createdBy: "",
    updatedBy: "",
  };
}

/** نفس ترميز دفعات الصفقة (dealsService.mapDealToSqlPayload) لدفعات وكيل الشحن */
function mapShipmentPaymentsToSql(payments: any[] | undefined): Record<string, any>[] {
  if (!payments?.length) return [];
  return payments.map((p: any, idx: number) => {
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
}

function toSqlShipmentPayload(form: any) {
  const stype = form.shippingInfo?.shippingType || "sea";
  const route = form.shippingInfo?.shipmentStatus?.status;
  const payload: Record<string, any> = {
    shipment_number: form.shipmentNumber || undefined,
    shipment_name: form.shipmentName || "",
    agent_shipment_number: form.agentShipmentNumber || "",
    shipping_agent: form.shippingAgentId && /^\d+$/.test(String(form.shippingAgentId)) ? Number(form.shippingAgentId) : null,
    israeli_side_name: form.israeliSideName || "",
    shipping_type: stype,
    ship_name: form.shippingInfo?.shipName || "",
    container_number: form.shippingInfo?.containerNumber || "",
    departure_date: form.shippingInfo?.departureDate ? String(form.shippingInfo.departureDate).slice(0, 10) : null,
    arrival_date: form.shippingInfo?.arrivalDate ? String(form.shippingInfo.arrivalDate).slice(0, 10) : null,
    international_shipping_company: form.shippingInfo?.internationalShippingCompany || "",
    bill_of_lading: form.shippingInfo?.billOfLadingNumber || "",
    bill_of_lading_file: form.shippingInfo?.billOfLadingFile || "",
    flight_number: form.shippingInfo?.flightNumber || "",
    airway_bill_number: form.shippingInfo?.airwayBillNumber || "",
    airway_bill_file: form.shippingInfo?.airwayBillFile || "",
    from_term: form.shippingInfo?.fromTerm || "",
    to_term: form.shippingInfo?.toTerm || "",
    imo_number: form.shippingInfo?.imoNumber || "",
    mmsi_number: form.shippingInfo?.mmsiNumber || "",
    tracking_link: form.shippingInfo?.trackingLink || "",
    total_shipping_cost_usd: Number(form.totalShippingCostUsd || 0),
    total_volume: toSqlVolumeOrWeight10_3(form.totalVolume),
    total_weight_kg: toSqlVolumeOrWeight10_3(form.totalWeightKg),
    remaining_amount: Number(form.remainingAmount || 0),
    installment_plan_enabled: Boolean(form.installmentPlanEnabled),
    pricing_method: form.pricingMethod || "total",
    unit_type: form.unitType || "cbm",
    price_per_unit: Number(form.pricePerUnit || 0),
    notes: form.notes || "",
  };
  if (Array.isArray(form.payments)) {
    payload.payments = mapShipmentPaymentsToSql(form.payments);
  }
  if (Array.isArray(form.deals) && form.deals.length) {
    const rows = form.deals
      .filter((d: any) => d.dealId && /^\d+$/.test(String(d.dealId).trim()))
      .map((d: any) => ({
        deal_id: Number(String(d.dealId).trim()),
        allocated_shipping_cost: Number(d.distributedCost || 0),
        extra_costs: Number(d.extraCosts || 0),
      }));
    if (rows.length) payload.deal_allocations = rows;
  }
  if (route && String(route).trim()) {
    const r = String(route).trim();
    payload.shipment_route_status = r;
    payload.status = routeStatusToSqlShipmentStatus(r, stype);
  }
  return payload;
}

export const shipmentsService = {
  subscribeToShipments(callback: (shipments: Shipment[]) => void) {
    let alive = true;
    const load = async () => {
      try {
        const rows = await apiGetList<any>("logistics/shipments/", { tenantId: getTenantId() });
        if (alive) callback(rows.map(mapShipmentFromSql));
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

  async getShipment(shipmentId: string): Promise<Shipment> {
    const row = await apiGetObject<any>(`logistics/shipments/${shipmentId}/`, { tenantId: getTenantId() });
    return mapShipmentFromSql(row);
  },

  /** لقطة واحدة من SQL (بدون اشتراك) — تذكيرات وصول، تقارير، إلخ */
  async listShipmentsOnce(): Promise<Shipment[]> {
    try {
      const rows = await apiGetList<any>("logistics/shipments/", { tenantId: getTenantId() });
      return rows.map(mapShipmentFromSql);
    } catch {
      return [];
    }
  },

  async getNextShipmentNumber(): Promise<string> {
    const rows = await apiGetList<any>("logistics/shipments/", { tenantId: getTenantId() });
    const nums = rows
      .map((r: any) => (r.shipment_number || "").match(/^S-(\d+)$/)?.[1])
      .filter(Boolean)
      .map((x: any) => Number(x));
    const next = (nums.length ? Math.max(...nums) : 0) + 1;
    return `S-${String(next).padStart(4, "0")}`;
  },

  calculateDistribution(
    deals: any[],
    totalCostUsd: number,
    opts?: { pricingMethod?: string; unitType?: string }
  ) {
    const method = (opts?.pricingMethod || "total").toLowerCase();
    const unitType = (opts?.unitType || "cbm").toLowerCase();
    const useWeight = method === "unit" && unitType === "weight";
    const denom = useWeight
      ? deals.reduce((sum, d) => sum + (Number(d.totalWeightKg) || 0), 0)
      : deals.reduce((sum, d) => sum + (d.totalVolume || 0), 0);
    if (!denom)
      return deals.map((d) => ({
        ...d,
        distributedCost: deals.length ? totalCostUsd / deals.length : 0,
      }));
    return deals.map((d) => {
      const w = useWeight
        ? Number(d.totalWeightKg) || 0
        : Number(d.totalVolume) || 0;
      return { ...d, distributedCost: (w / denom) * totalCostUsd };
    });
  },

  async createShipment(shipmentData: any, _userId: string, _userName: string) {
    const payload = toSqlShipmentPayload(shipmentData);
    const created = await apiPostObject<any>("logistics/shipments/", payload, { tenantId: getTenantId() });
    return String(created.id);
  },

  async updateShipment(shipmentId: string, updates: Partial<Shipment>, _userId: string, _userName: string) {
    const current = await this.getShipment(shipmentId);
    const u: any = updates;
    const merged: any = {
      ...current,
      ...updates,
      shippingInfo: {
        ...current.shippingInfo,
        ...(u.shippingInfo || {}),
      },
    };
    if (Object.prototype.hasOwnProperty.call(u, "payments")) {
      assertShipmentPaymentsNotOverTotal(merged, current.payments);
    }
    const payload = toSqlShipmentPayload(merged);
    await apiPatchObject(`logistics/shipments/${shipmentId}/`, payload, { tenantId: getTenantId() });
  },

  /** عند تسجيل دفعة من نموذج الشحنة: مرّر إجمالي الشحنة/الصفوف حتى لا يبقى الحدّ 0 إن كان الآبِي قديماً. */
  async addShipmentAgentPayment(
    shipmentId: string,
    payment: Omit<DealPayment, "id">,
    syncFromForm?: { totalShippingCostUsd?: number; deals?: Shipment["deals"] }
  ): Promise<string> {
    const cur = await this.getShipment(shipmentId);
    const newPayment: DealPayment = { ...payment, id: `tmp-${Date.now()}` };
    await this.updateShipment(
      shipmentId,
      {
        ...(syncFromForm?.totalShippingCostUsd != null
          ? { totalShippingCostUsd: syncFromForm.totalShippingCostUsd }
          : {}),
        ...(syncFromForm?.deals != null ? { deals: syncFromForm.deals } : {}),
        payments: [...(cur.payments || []), newPayment],
      } as Partial<Shipment>,
      "",
      ""
    );
    return newPayment.id;
  },

  async updateShipmentAgentPaymentWithSwift(
    shipmentId: string,
    paymentId: string,
    updates: Partial<DealPayment>,
    syncFromForm?: { totalShippingCostUsd?: number; deals?: Shipment["deals"] }
  ): Promise<void> {
    const cur = await this.getShipment(shipmentId);
    const payments = (cur.payments || []).map((p) =>
      p.id === paymentId ? { ...p, ...updates } : p
    );
    await this.updateShipment(
      shipmentId,
      {
        ...(syncFromForm?.totalShippingCostUsd != null
          ? { totalShippingCostUsd: syncFromForm.totalShippingCostUsd }
          : {}),
        ...(syncFromForm?.deals != null ? { deals: syncFromForm.deals } : {}),
        payments,
      } as Partial<Shipment>,
      "",
      ""
    );
  },

  /** ترحيل دفعة وكيل الشحن إلى المحاسبة (ينشئ قيداً ويربطه بالدفعة). */
  async postShipmentAgentPaymentToAccounting(
    shipmentId: string,
    paymentId: string,
    body?: { cash_box_external_id?: string; bank_account_id?: number }
  ): Promise<{ status?: string; journal_id?: number; error?: string }> {
    return apiPostObject(
      `logistics/shipments/${shipmentId}/post_agent_payment/${encodeURIComponent(String(paymentId))}/`,
      body || {},
      { tenantId: getTenantId() }
    );
  },

  /**
   * بعد السليب/الخصم من الصندوق: محاولة إنشاء القيد تلقائياً (مثل دفعات الصفقة).
   */
  async tryAutoPostShipmentAgentPaymentAccounting(
    shipmentId: string,
    paymentId: string,
    opts?: { cashBoxExternalId?: string }
  ): Promise<{ journalId?: number; posted: boolean; blockers?: string[] }> {
    const pid = String(paymentId ?? "").trim();
    if (!/^\d+$/.test(pid)) {
      return { posted: false, blockers: ["معرّف الدفعة غير رقمي بعد — أعد فتح الشحنة."] };
    }

    const body: Record<string, any> = {};
    const ext = opts?.cashBoxExternalId?.trim();
    if (ext) body.cash_box_external_id = ext.slice(0, 128);

    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

    let lastMsg = "";
    for (let attempt = 0; attempt < 4; attempt++) {
      if (attempt > 0) {
        await sleep(350);
      }
      let refreshed = await this.getShipment(shipmentId);
      let row = refreshed.payments?.find((p) => String(p.id) === pid);
      const jidRow = row?.journalId != null ? Number(row.journalId) : NaN;
      if (row?.isPosted && Number.isFinite(jidRow) && jidRow > 0) {
        return { posted: true, journalId: jidRow };
      }

      try {
        const res = await this.postShipmentAgentPaymentToAccounting(shipmentId, pid, body);
        if (res?.journal_id != null) {
          return { posted: true, journalId: Number(res.journal_id) };
        }
        return {
          posted: false,
          blockers: ["لم يُرجع الخادم رقم القيد."],
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        lastMsg = msg;
        if (/مرحلة بالفعل|already posted/i.test(msg)) {
          const again = await this.getShipment(shipmentId);
          const pr = again.payments?.find((p) => String(p.id) === pid);
          const j = pr?.journalId != null ? Number(pr.journalId) : NaN;
          if (Number.isFinite(j) && j > 0) {
            return { posted: true, journalId: j };
          }
        }
        const retryable =
          attempt < 3 &&
          /حالة الدفعة|قبل الترحيل|يجب تسجيل السليب|Pending|Paid|Confirmed/i.test(
            msg
          );
        if (!retryable) {
          return { posted: false, blockers: [msg] };
        }
      }
    }
    return { posted: false, blockers: [lastMsg || "تعذّر ترحيل الدفعة بعد عدة محاولات."] };
  },

  async linkShipmentAgentPaymentJournal(
    shipmentId: string,
    paymentId: string,
    journalId: number
  ): Promise<{ status: string; journal_id?: number; payment_id?: number }> {
    return apiPostObject(
      `logistics/shipments/${shipmentId}/link_agent_payment_journal/${encodeURIComponent(String(paymentId))}/`,
      { journal_id: journalId },
      { tenantId: getTenantId() }
    );
  },

  async confirmShipmentAgentPayment(
    shipmentId: string,
    paymentId: string,
    supplierConfirmationImage?: string,
    supplierNotes?: string,
    paymentConfirmationDate?: string,
    cashBoxId?: string
  ): Promise<{ message: string; openManualJournal?: boolean }> {
    const cur = await this.getShipment(shipmentId);
    const when = paymentConfirmationDate || new Date().toISOString();
    const payments = (cur.payments || []).map((p) =>
      p.id === paymentId
        ? {
            ...p,
            confirmedBySupplier: true,
            supplierConfirmationImage,
            supplierNotes,
            paymentConfirmationDate: when,
            confirmedAt: when,
            cashBoxId: cashBoxId || p.cashBoxId,
          }
        : p
    );
    await this.updateShipment(shipmentId, { payments } as Partial<Shipment>, "", "");
    return {
      message: "تم حفظ تأكيد وكيل الشحن.",
      openManualJournal: false,
    };
  },

  async cancelShipmentAgentPayment(shipmentId: string, paymentId: string): Promise<void> {
    const cur = await this.getShipment(shipmentId);
    const payments = (cur.payments || []).filter((p) => p.id !== paymentId);
    await this.updateShipment(shipmentId, { payments } as Partial<Shipment>, "", "");
  },

  async deleteShipment(shipmentId: string) {
    await apiDelete(`logistics/shipments/${shipmentId}/`, { tenantId: getTenantId() });
  },

  /** يربط صفقة بالشحنة في SQL (يُفعّل التحديث التلقائي لحالة الصفقة) */
  /**
   * تحديث مسار الشحنة المرتبطة بصفقة (مثل حفظ فاتورة → مفرج عنها، بمواءمة حالة الصفقة).
   */
  /** PATCH مباشر لمسار الشحنة (بدون إرسال بقية حقول النموذج) */
  async patchShipmentRoute(
    shipmentId: string,
    routeStatus: string,
    shippingType: string = "sea"
  ): Promise<void> {
    const sid = String(shipmentId).trim();
    if (!sid) return;
    const stype = shippingType === "air" ? "air" : "sea";
    await apiPatchObject(
      `logistics/shipments/${sid}/`,
      {
        shipment_route_status: routeStatus,
        status: routeStatusToSqlShipmentStatus(routeStatus, stype),
      },
      { tenantId: getTenantId() }
    );
  },

  async patchLinkedShipmentsRouteForDeal(
    dealId: string,
    routeStatus: string
  ): Promise<void> {
    const sid = String(dealId).trim();
    if (!sid) return;
    const rows = await apiGetList<any>("logistics/shipments/", {
      tenantId: getTenantId(),
    });
    for (const r of rows) {
      const ids = (r.deals || []).map((d: any) => String(d.id));
      if (!ids.includes(sid)) continue;
      const stype = r.shipping_type === "air" ? "air" : "sea";
      await apiPatchObject(
        `logistics/shipments/${r.id}/`,
        {
          shipment_route_status: routeStatus,
          status: routeStatusToSqlShipmentStatus(routeStatus, stype),
        },
        { tenantId: getTenantId() }
      );
    }
  },

  async addDealToShipment(shipmentId: string, dealId: string): Promise<void> {
    const did = Number(dealId);
    if (!Number.isFinite(did) || !shipmentId) return;
    try {
      await apiPostObject(
        `logistics/shipments/${shipmentId}/add_deal/`,
        { deal_id: did },
        { tenantId: getTenantId() }
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/unique|already|400|duplicate/i.test(msg)) return;
      throw e;
    }
  },
};

