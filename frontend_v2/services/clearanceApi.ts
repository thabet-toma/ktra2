import {
  apiGetList,
  apiGetObject,
  apiPostObject,
  apiPatchObject,
  apiDelete,
} from "./restApi";
import type { ClearanceCostLine, ClearanceLine } from "@/constants/clearanceDefaults";
import { resolveTenantId } from "@/utils/tenantContext";
import type { AccrualKind, AccrualStatus } from "@/utils/voucherAllocation";

const tid = () => resolveTenantId();

export type ClearanceRow = {
  id: number;
  shipment: number;
  shipment_number?: string;
  /** اسم تعريفي للشحنة (عربي) — من logistics_shipments.shipment_name */
  shipment_name?: string | null;
  /** «SH-0017 — شحنة رقع» من الخادم (`shipment.display_label`). */
  shipment_label?: string | null;
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
  /** رقم مطالبة المخلّص — يُعدَّل بعد ترحيل الاستحقاق أيضاً. */
  broker_claim_number?: string;
  currency?: number | null;
  exchange_rate?: number | null;
  vat_statement?: number | null;
  subtotal_no_vat?: number | null;
  vat_total?: number | null;
  grand_total?: number | null;
  journal?: number | null;
  editable?: boolean;
  amount_paid?: string;
  remaining_balance?: string;
  /** الزائد المدفوع عن المستحق — بعد ترحيل الاستحقاق من الخادم (`document_settlement`). */
  advance_balance?: string;
  payment_status?: "paid" | "partially_paid" | "unpaid";
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
  if ((c.shipment_label || "").trim()) return String(c.shipment_label).trim();
  const num = (c.shipment_number || "").trim();
  const name = (c.shipment_name || "").trim();
  const fallback = c.shipment ? `شحنة #${c.shipment}` : "شحنة";
  if (name && num && name !== num) return `${name} — ${num}`;
  if (name) return name;
  if (num) return `شحنة ${num}`;
  return fallback;
}

export type ClearancePaymentRow = {
  /** رقمٌ للدفعة المباشرة، و`alloc-<n>` لصفّ سندٍ موزَّع. */
  id: number | string;
  clearance?: number;
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
  shipment_label?: string | null;
  /** صفّ سند صرفٍ موزَّع على التخليص (`party_accruals.document_voucher_rows`) لا دفعة مباشرة. */
  row_type?: "voucher_allocation";
  voucher_id?: number;
  kind_label?: string;
};

/** بند مخلّص من إعدادات الشركة (`ClearanceItemType`). */
export type ClearanceItemType = {
  id: number;
  name: string;
  /** معنى البند للمحرّك: `vat` ضريبة مدخلات، وغيره تكلفة استيراد. */
  legacy_type: string;
  account: number | null;
  account_code?: string | null;
  account_name?: string | null;
  is_active: boolean;
  sort_order: number;
};

export async function listClearanceItemTypes(): Promise<ClearanceItemType[]> {
  return apiGetList<ClearanceItemType>("logistics/clearance-item-types/", { tenantId: tid() });
}

export async function saveClearanceItemType(
  body: Partial<ClearanceItemType> & { name: string },
): Promise<ClearanceItemType> {
  if (body.id) {
    return apiPatchObject<ClearanceItemType>(
      `logistics/clearance-item-types/${body.id}/`, body, { tenantId: tid() });
  }
  return apiPostObject<ClearanceItemType>("logistics/clearance-item-types/", body, { tenantId: tid() });
}

export async function deleteClearanceItemType(id: number): Promise<void> {
  return apiDelete(`logistics/clearance-item-types/${id}/`, { tenantId: tid() });
}

export async function listClearances(
  query?: Record<string, string | number | boolean | undefined>,
): Promise<ClearanceRow[]> {
  return apiGetList<ClearanceRow>("logistics/clearances/", {
    tenantId: tid(),
    query,
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
    broker_claim_number: string | null;
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

/** دفعة التخليص؛ `payment` فارغٌ إن كان التخليص مسدَّداً فصارت كلّها سنداً «تحت الحساب». */
export type ClearancePaymentResult = {
  status: string;
  journal_id?: number;
  payment: ClearancePaymentRow | null;
  on_account_voucher?: { id: number; amount: string } | null;
};

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
): Promise<ClearancePaymentResult> {
  return apiPostObject<ClearancePaymentResult>(
    `logistics/clearances/${clearanceId}/pay_from_cashbox/`,
    payload as any,
    { tenantId: tid() }
  );
}

/** متبقّي مستحقٍّ لوجستي واحد — مصدر تنبيه «سيُفصل X كدفعة تحت الحساب». */
export async function getAccrualStatus(kind: AccrualKind, id: number): Promise<AccrualStatus> {
  return apiGetObject<AccrualStatus>("logistics/supplier-payments/accrual-status/", {
    tenantId: tid(),
    query: { kind, id },
  });
}

export async function postClearanceAccrual(
  clearanceId: number,
): Promise<{ journal_id: number; total: string; message: string }> {
  return apiPostObject(
    `logistics/clearances/${clearanceId}/post-to-accounting/`,
    {},
    { tenantId: tid() },
  );
}

export async function unpostClearanceAccrual(
  clearanceId: number,
): Promise<{ message: string }> {
  return apiPostObject(
    `logistics/clearances/${clearanceId}/unpost-accrual/`,
    {},
    { tenantId: tid() },
  );
}
