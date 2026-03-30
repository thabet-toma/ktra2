import { Shipment } from "../types";
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";

const TENANT_ID = 1;

function mapShipmentFromSql(s: any): Shipment {
  const deals = (s.deals || []).map((d: any) => ({
    dealId: String(d.id),
    dealNumber: d.ref_number || `D-${d.id}`,
    originalOfferNumber: d.original_offer_number || "",
    totalAmount: Number(d.total_amount || 0),
    totalVolume: Number(d.total_cbm || 0),
    totalWeightKg: Number(d.total_weight_kg || d.total_weight || 0),
    distributedCost: 0,
    notes: d.notes || "",
  }));
  const payments = (s.payments || []).map((p: any, idx: number) => ({
    id: String(p.id ?? `p-${idx}`),
    type: p.title || `payment_${idx + 1}`,
    amount: Number(p.amount || 0),
    usdToIls: Number(p.usd_to_ils || 0),
    transferCost: Number(p.transfer_cost || 0),
    paymentDate: p.transfer_date || p.due_date || new Date().toISOString(),
    paymentConfirmationDate: p.confirmation_date,
    notes: p.notes || "",
    bankSwiftImage: p.bank_swift_image,
    confirmedBySupplier: String(p.status || "").toLowerCase().includes("confirm"),
    confirmedAt: p.confirmation_date,
  }));
  const paid = payments.reduce((sum: number, p: any) => sum + Number(p.amount || 0), 0);
  const total = Number(s.total_shipping_cost_usd || 0);
  let status: Shipment["status"] = "draft";
  if (paid >= total && total > 0) status = "paid";
  else if (paid > 0) status = "partially_paid";
  else if (payments.length) status = "payment_pending";

  return {
    id: String(s.id),
    shipmentNumber: s.shipment_number || `S-${s.id}`,
    agentShipmentNumber: s.agent_shipment_number || "",
    shippingAgentId: String(s.shipping_agent || ""),
    shippingAgentName: s.agent_name || "",
    israeliSideName: s.israeli_side_name || "",
    shippingInfo: {
      shippingType: s.shipping_type === "air" ? "air" : "sea",
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
        status: String(s.status || "Pending").toLowerCase(),
        statusDate: s.arrival_date || s.departure_date || "",
      },
    },
    deals,
    totalShippingCostUsd: total,
    totalVolume: Number(s.total_volume || 0),
    totalWeightKg: Number(s.total_weight_kg || 0),
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

function toSqlShipmentPayload(form: any) {
  return {
    shipment_number: form.shipmentNumber || undefined,
    shipment_name: form.shipmentName || "",
    agent_shipment_number: form.agentShipmentNumber || "",
    shipping_agent: form.shippingAgentId && /^\d+$/.test(String(form.shippingAgentId)) ? Number(form.shippingAgentId) : null,
    israeli_side_name: form.israeliSideName || "",
    shipping_type: form.shippingInfo?.shippingType || "sea",
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
    total_volume: Number(form.totalVolume || 0),
    total_weight_kg: Number(form.totalWeightKg || 0),
    remaining_amount: Number(form.remainingAmount || 0),
    installment_plan_enabled: Boolean(form.installmentPlanEnabled),
    pricing_method: form.pricingMethod || "total",
    unit_type: form.unitType || "cbm",
    price_per_unit: Number(form.pricePerUnit || 0),
    notes: form.notes || "",
  };
}

export const shipmentsService = {
  subscribeToShipments(callback: (shipments: Shipment[]) => void) {
    let alive = true;
    const load = async () => {
      try {
        const rows = await apiGetList<any>("logistics/shipments/", { tenantId: TENANT_ID });
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
    const row = await apiGetObject<any>(`logistics/shipments/${shipmentId}/`, { tenantId: TENANT_ID });
    return mapShipmentFromSql(row);
  },

  async getNextShipmentNumber(): Promise<string> {
    const rows = await apiGetList<any>("logistics/shipments/", { tenantId: TENANT_ID });
    const nums = rows
      .map((r: any) => (r.shipment_number || "").match(/^S-(\d+)$/)?.[1])
      .filter(Boolean)
      .map((x: any) => Number(x));
    const next = (nums.length ? Math.max(...nums) : 0) + 1;
    return `S-${String(next).padStart(4, "0")}`;
  },

  calculateDistribution(deals: any[], totalCostUsd: number) {
    const totalVolume = deals.reduce((sum, d) => sum + (d.totalVolume || 0), 0);
    if (!totalVolume) return deals.map((d) => ({ ...d, distributedCost: deals.length ? totalCostUsd / deals.length : 0 }));
    return deals.map((d) => ({ ...d, distributedCost: ((d.totalVolume || 0) / totalVolume) * totalCostUsd }));
  },

  async createShipment(shipmentData: any, _userId: string, _userName: string) {
    const payload = toSqlShipmentPayload(shipmentData);
    const created = await apiPostObject<any>("logistics/shipments/", payload, { tenantId: TENANT_ID });
    return String(created.id);
  },

  async updateShipment(shipmentId: string, updates: Partial<Shipment>, _userId: string, _userName: string) {
    const payload = toSqlShipmentPayload(updates);
    await apiPatchObject(`logistics/shipments/${shipmentId}/`, payload, { tenantId: TENANT_ID });
  },

  async deleteShipment(shipmentId: string) {
    await apiDelete(`logistics/shipments/${shipmentId}/`, { tenantId: TENANT_ID });
  },
};

