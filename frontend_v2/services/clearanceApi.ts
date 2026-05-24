import {
  apiGetList,
  apiGetObject,
  apiPostObject,
  apiPatchObject,
} from "./restApi";
import type { ClearanceCostLine, ClearanceLine } from "@/constants/clearanceDefaults";
import { resolveTenantId } from "@/utils/tenantContext";

const tid = () => resolveTenantId();

export type ClearanceRow = {
  id: number;
  shipment: number;
  shipment_number?: string;
  /** اسم تعريفي للشحنة (عربي) — من logistics_shipments.shipment_name */
  shipment_name?: string | null;
  customs_broker: number | null;
  broker_name?: string;
  declaration_number?: string | null;
  clearance_date?: string | null;
  status: string;
  notes?: string | null;
  transaction_time?: string | null;
  second_date?: string | null;
  licensed_dealer_no?: string;
  settlement_invoice_number?: string;
  currency?: number | null;
  exchange_rate?: number | null;
  vat_statement?: number | null;
  subtotal_no_vat?: number | null;
  vat_total?: number | null;
  grand_total?: number | null;
  journal?: number | null;
  editable?: boolean;
  cost_lines?: ClearanceCostLine[];
  /** البنود المهيكلة (P-D-1: LogisticsClearanceLine) */
  lines?: ClearanceLine[];
  /** عدد صفقات الشحنة المرتبطة */
  deals_count?: number;
  /** معاينة عناوين الصفقات (من description / رقم الصفقة) */
  deals_preview?: string | null;
  /** سجلات الشحن المحلي المرتبطة بهذا التخليص (مصدر الحقيقة — T2-04/T4-04).
   *  وجودها يعني أن النقل المحلي يُدار كسجل رسمي لا كسطر تكلفة مكرّر. */
  local_shipments?: {
    id: number;
    shipment_number: string;
    amount: string;
    status: string;
    is_posted: boolean;
    currency: number | null;
  }[];
};

/** سطر عرض موحّد: «اسم الشحنة — S-00xx» كما في شاشة التخليص */
export function formatClearanceShipmentLine(c: ClearanceRow): string {
  const num = (c.shipment_number || "").trim();
  const name = (c.shipment_name || "").trim();
  const fallback = c.shipment ? `شحنة #${c.shipment}` : "شحنة";
  if (name && num && name !== num) return `${name} — ${num}`;
  if (name) return name;
  if (num) return `شحنة ${num}`;
  return fallback;
}

export type ClearancePaymentRow = {
  id: number;
  clearance: number;
  amount: number;
  currency?: number | null;
  currency_code?: string | null;
  payment_date?: string | null;
  cash_box_external_id: string;
  notes?: string | null;
  payment_purpose?: string;
  is_posted: boolean;
  journal?: number | null;
  journal_id_display?: number | null;
  broker_name?: string;
  created_at?: string;
};

export async function listClearances(): Promise<ClearanceRow[]> {
  return apiGetList<ClearanceRow>("logistics/clearances/", {
    tenantId: tid(),
  });
}

export async function getClearance(id: number): Promise<ClearanceRow> {
  return apiGetObject<ClearanceRow>(`logistics/clearances/${id}/`, {
    tenantId: tid(),
  });
}

export async function createClearance(body: {
  shipment: number;
  customs_broker?: number | null;
  declaration_number?: string;
  clearance_date?: string | null;
  status?: string;
  notes?: string;
  cost_lines?: ClearanceCostLine[];
}): Promise<ClearanceRow> {
  return apiPostObject<ClearanceRow>("logistics/clearances/", body as any, {
    tenantId: tid(),
  });
}

export async function updateClearance(
  id: number,
  body: Partial<{
    customs_broker: number | null;
    declaration_number: string;
    clearance_date: string | null;
    status: string;
    notes: string;
    transaction_time: string | null;
    second_date: string | null;
    licensed_dealer_no: string | null;
    settlement_invoice_number: string | null;
    currency: number | null;
    exchange_rate: number | null;
    subtotal_no_vat: number | null;
    vat_total: number | null;
    grand_total: number | null;
    cost_lines: ClearanceCostLine[];
  }>
): Promise<ClearanceRow> {
  return apiPatchObject<ClearanceRow>(`logistics/clearances/${id}/`, body as any, {
    tenantId: tid(),
  });
}

export async function listClearancePayments(
  clearanceId: number
): Promise<ClearancePaymentRow[]> {
  return apiGetList<ClearancePaymentRow>(
    `logistics/clearances/${clearanceId}/payments/`,
    { tenantId: tid() }
  );
}

export async function payClearanceFromCashBox(
  clearanceId: number,
  payload: {
    amount: number;
    cash_box_external_id: string;
    payment_date?: string;
    notes?: string;
    /** افتراضي: clearance — للشحن يُمرَّر shipping مع payee_partner_id */
    payment_kind?: "clearance" | "shipping";
    payee_partner_id?: number;
  }
): Promise<{ status: string; journal_id?: number; payment: ClearancePaymentRow }> {
  return apiPostObject<{ status: string; journal_id?: number; payment: ClearancePaymentRow }>(
    `logistics/clearances/${clearanceId}/pay_from_cashbox/`,
    payload as any,
    { tenantId: tid() }
  );
}
