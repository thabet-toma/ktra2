import { resolveTenantId } from "../utils/tenantContext";
import { eventBus } from "../utils/eventBus";
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";

const tid = () => resolveTenantId();
const BASE = "sales";

export type SalesInvoiceRow = {
  id: number;
  invoice_number: string;
  customer: number;
  customer_name?: string;
  invoice_date: string;
  due_date?: string | null;
  invoice_type: "cash" | "credit";
  status: string;
  grand_total: string;
  amount_paid?: string;
  currency: number;
  stock_on_post?: boolean;
  /** M2-T1: book number (0 = manual). */
  book_number?: number;
};

/** M2-T3: cheque attached to a sales invoice (read-side). */
export type AttachedCheque = {
  id: number;
  cheque_number: string;
  bank_name?: string;
  amount: string;
  due_date?: string | null;
  issue_date?: string | null;
  payee_name?: string | null;
  status: string;
  notes?: string | null;
};

export type SalesInvoiceDetail = SalesInvoiceRow & {
  exchange_rate: string;
  subtotal_excl_tax: string;
  invoice_discount: string;
  tax_amount: string;
  revenue_account: number | null;
  cash_or_bank_account: number | null;
  accounts_receivable_account: number | null;
  journal: number | null;
  notes: string;
  lines: {
    id: number;
    product: number;
    quantity: string;
    unit_price: string;
    line_discount: string;
    tax_rate: number | null;
    line_total_excl_tax: string;
    line_tax_amount: string;
    /** M2-T2: Aseel line columns */
    unit?: string;
    warehouse?: string;
    catalog_no?: string;
    expiry_date?: string | null;
    extra_quantity?: string | null;
    line_tax_percent?: string | null;
  }[];
  created_at?: string;
  // M2-T1: Aseel header fields
  book_number?: number;
  second_date?: string | null;
  licensed_dealer_no?: string;
  settlement_invoice_no?: string;
  prices_include_tax?: boolean;
  discount_percent?: string;
  // M2-T3: Financial instrument + attached voucher
  financial_document_no?: string;
  attached_cash_amount?: string;
  attached_cash_account?: number | null;
  cheques?: AttachedCheque[];
  // M2-T4: source-discount overrides (null = use customer default)
  source_discount_percent_override?: string | null;
  source_discount_amount_override?: string | null;
};

/** M2-T3: payload for attaching cash + cheques to an invoice. */
export type PaymentVoucherInput = {
  cash_amount: string;
  cash_account_id?: number | null;
  cheques: Array<{
    cheque_number: string;
    amount: string;
    bank_name?: string;
    due_date?: string | null;
    issue_date?: string | null;
    payee_name?: string;
    notes?: string;
  }>;
};

export async function attachPaymentVoucher(
  invoiceId: number,
  payload: PaymentVoucherInput
): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${invoiceId}/payment-voucher/`, payload, {
    tenantId: tid(),
  });
}

export async function listSalesInvoices(
  query?: Record<string, string | number | boolean | undefined>
): Promise<SalesInvoiceRow[]> {
  return apiGetList(`${BASE}/invoices/`, { tenantId: tid(), query });
}

export async function getSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiGetObject(`${BASE}/invoices/${id}/`, { tenantId: tid() });
}

/** F4: preview the next invoice number for the active tenant/book (non-consuming). */
export async function getNextInvoiceNumber(book: number): Promise<string> {
  const data = await apiGetObject<{ next_number?: string }>(
    `${BASE}/invoices/next-number/?book=${encodeURIComponent(String(book))}`,
    { tenantId: tid() }
  );
  return data?.next_number || "";
}

export async function createSalesInvoice(
  body: Record<string, unknown>
): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/`, body, { tenantId: tid() });
}

export async function patchSalesInvoice(
  id: number,
  body: Record<string, unknown>
): Promise<SalesInvoiceDetail> {
  return apiPatchObject(`${BASE}/invoices/${id}/`, body, { tenantId: tid() });
}

export async function postSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/post/`, {}, { tenantId: tid() });
}

/** التراجع عن ترحيل الفاتورة: حذف قيودها وحركات مخزونها وإرجاعها مسودة (Feature 1). */
export async function unpostSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/unpost/`, {}, { tenantId: tid() });
}

export async function deleteSalesInvoice(id: number): Promise<void> {
  return apiDelete(`${BASE}/invoices/${id}/`, { tenantId: tid() });
}

export async function duplicateSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/duplicate/`, {}, { tenantId: tid() });
}

export async function createDeliveryOrder(
  invoiceId: number,
  notes?: string
): Promise<{ id: number; invoice: number; status: string }> {
  return apiPostObject(
    `${BASE}/invoices/${invoiceId}/delivery-order/`,
    { notes: notes ?? "" },
    { tenantId: tid() }
  );
}

export async function deliverOrder(deliveryOrderId: number): Promise<unknown> {
  return apiPostObject(
    `${BASE}/delivery-orders/${deliveryOrderId}/deliver/`,
    {},
    { tenantId: tid() }
  );
}

export type CreditPreviewResponse = {
  credit_limit: string | null;
  open_balance: string;
  proposed_total: string;
  projected_balance: string;
  would_exceed: boolean;
};

export async function getCreditPreview(params: {
  customer: number;
  proposed_total: string | number;
  excludeInvoice?: number;
}): Promise<CreditPreviewResponse> {
  const q = new URLSearchParams();
  q.set("customer", String(params.customer));
  q.set("proposed_total", String(params.proposed_total));
  if (params.excludeInvoice != null) q.set("exclude_invoice", String(params.excludeInvoice));
  return apiGetObject(`sales/invoices/credit-preview/?${q.toString()}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// task18 DEF-C2: آخر سعر بيع للوحدة (عام أو لعميل محدّد)
// -------------------------------------------------------------
export type LastSalePriceResponse = {
  unit_price: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
};

export async function getLastSalePrice(params: {
  product: number;
  customer?: number | "";
}): Promise<LastSalePriceResponse> {
  const q = new URLSearchParams();
  q.set("product", String(params.product));
  if (params.customer != null && params.customer !== "") q.set("customer", String(params.customer));
  return apiGetObject(`sales/invoices/last-price/?${q.toString()}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// FEAT-2: السعر المقترح لبند البيع عبر PriceResolver المشترك
// (آخر سعر دفعه العميل ← سعر البيع الافتراضي ← فارغ) مع تطبيع العملة/الضريبة.
// -------------------------------------------------------------
export type ResolvedPriceResponse = {
  unit_price: string | null;
  strategy_used: string | null;
  strategy_requested: string;
  source: { document_type: string; document_number?: string } | null;
};

export async function resolveSalePrice(params: {
  product: number;
  customer?: number | "";
  currency?: number | "";
  exchange_rate?: number | string;
  tax_inclusive?: boolean;
}): Promise<ResolvedPriceResponse> {
  const q = new URLSearchParams();
  q.set("product", String(params.product));
  if (params.customer != null && params.customer !== "") q.set("customer", String(params.customer));
  if (params.currency != null && params.currency !== "") q.set("currency", String(params.currency));
  if (params.exchange_rate != null) q.set("exchange_rate", String(params.exchange_rate));
  if (params.tax_inclusive) q.set("tax_inclusive", "true");
  return apiGetObject(`sales/invoices/resolve-price/?${q.toString()}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// task18 DEF-C1: رصيد الشريك (قبل/بعد) — يعمل للعميل والمورد
// -------------------------------------------------------------
export type PartnerBalanceResponse = {
  partner: number;
  partner_type: string;
  debit: string;
  credit: string;
  open_balance: string;
  proposed_total: string;
  projected_balance: string;
};

export async function getPartnerBalance(params: {
  partnerId: number | string;
  proposedTotal?: string | number;
}): Promise<PartnerBalanceResponse> {
  const q = new URLSearchParams();
  if (params.proposedTotal != null) q.set("proposed_total", String(params.proposedTotal));
  const qs = q.toString();
  return apiGetObject(`partners/${params.partnerId}/balance/${qs ? `?${qs}` : ""}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// task18 DEF-C4: تقرير أرباح الفواتير
// -------------------------------------------------------------
export type InvoiceProfitRow = {
  invoice: number;
  invoice_number: string;
  invoice_date: string | null;
  customer: number | null;
  customer_name: string;
  revenue: string;
  cost: string;
  profit: string;
  margin_pct: string;
};

export type InvoiceProfitsResponse = {
  rows: InvoiceProfitRow[];
  totals: {
    count: number;
    revenue: string;
    cost: string;
    profit: string;
    margin_pct: string;
  };
};

export async function getInvoiceProfits(params: {
  dateFrom?: string;
  dateTo?: string;
  customer?: number;
}): Promise<InvoiceProfitsResponse> {
  const q = new URLSearchParams();
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  if (params.customer != null) q.set("customer", String(params.customer));
  const qs = q.toString();
  return apiGetObject(`sales/invoices/profits/${qs ? `?${qs}` : ""}`, { tenantId: tid() });
}

export type FifoAllocationRow = {
  invoice: number;
  invoice_number: string;
  amount: string;
};

export async function suggestFifoAllocations(params: {
  partner: number;
  amount: string | number;
}): Promise<FifoAllocationRow[]> {
  return apiPostObject(
    `${BASE}/payments/suggest-fifo-allocations/`,
    { partner: params.partner, amount: params.amount },
    { tenantId: tid() }
  );
}

// -------------------------------------------------------------
// Customer Payments (دفعات العملاء)
// -------------------------------------------------------------
export type CustomerPaymentAllocation = {
  id?: number;
  invoice: number;
  amount: string;
  amount_in_invoice_currency?: string;
  conversion_rate?: string;
};

export type CustomerPaymentRow = {
  id: number;
  partner: number;
  payment_date: string;
  amount: string;
  currency: number;
  exchange_rate: string;
  cash_or_bank_account: number;
  journal: number | null;
  is_posted: boolean;
  notes: string;
  allocations: CustomerPaymentAllocation[];
  created_at?: string;
};

export async function listCustomerPayments(
  query?: Record<string, string | number | boolean | undefined>,
): Promise<CustomerPaymentRow[]> {
  return apiGetList(`${BASE}/payments/`, { tenantId: tid(), query });
}

export async function getCustomerPayment(id: number): Promise<CustomerPaymentRow> {
  return apiGetObject(`${BASE}/payments/${id}/`, { tenantId: tid() });
}

export async function createCustomerPayment(
  body: {
    partner: number;
    payment_date: string;
    amount: string | number;
    currency: number;
    exchange_rate?: string | number;
    cash_or_bank_account: number;
    notes?: string;
    allocations?: Array<{ invoice: number; amount: string | number }>;
  },
): Promise<CustomerPaymentRow> {
  return apiPostObject(`${BASE}/payments/`, body, { tenantId: tid() });
}

export async function postCustomerPayment(id: number): Promise<CustomerPaymentRow> {
  return apiPostObject(`${BASE}/payments/${id}/post/`, {}, { tenantId: tid() });
}

export async function deleteCustomerPayment(id: number): Promise<void> {
  return apiDelete(`${BASE}/payments/${id}/`, { tenantId: tid() });
}

// -------------------------------------------------------------
// Sales Settings (إعدادات المبيعات المركزية)
// -------------------------------------------------------------
export type SalesSettings = {
  id: number;
  default_customer: number | null;
  default_customer_name?: string;
  default_currency: number | null;
  default_currency_code?: string;
  default_revenue_account_product: number | null;
  default_revenue_account_product_name?: string;
  default_revenue_account_service: number | null;
  default_revenue_account_service_name?: string;
  default_cash_account: number | null;
  default_cash_account_name?: string;
  default_inventory_account: number | null;
  default_cogs_account: number | null;
  default_ar_account: number | null;
  default_payment_type: "cash" | "credit";
  stock_on_post_default: boolean;
  allow_negative_stock_default: boolean;
  default_vat_rate: number | null;
  default_vat_rate_code?: string;
  default_vat_rate_value?: string;
  prices_include_tax: boolean;
  auto_post_invoices: boolean;
  show_journal_preview: boolean;
  default_shipping_origin: string;
  default_shipping_destination: string;
  updated_at?: string;
};

export async function getSalesSettings(): Promise<SalesSettings> {
  return apiGetObject(`${BASE}/settings/current/`, { tenantId: tid() });
}

export async function updateSalesSettings(
  body: Partial<SalesSettings>,
): Promise<SalesSettings> {
  const settings = await apiPatchObject(`${BASE}/settings/current/`, body, { tenantId: tid() });
  try {
    eventBus.publish("settings", tid());
  } catch (e) {
    console.error("Failed to publish settings event:", e);
  }
  return settings;
}

export async function getAgingReport(): Promise<
  {
    invoice_id: number;
    invoice_number: string;
    customer_id: number;
    customer_name: string;
    invoice_date: string;
    due_date?: string | null;
    grand_total: string;
    amount_paid: string;
    remaining: string;
  }[]
> {
  return apiGetList(`${BASE}/reports/aging/`, { tenantId: tid() });
}

// -------------------------------------------------------------
// Sales Quotations (العروض والطلبيات — T4-01)
// -------------------------------------------------------------
export type SalesQuotationRow = {
  id: number;
  quotation_number: string;
  customer: number;
  customer_name?: string;
  quotation_date: string;
  valid_until?: string | null;
  status: string;
  grand_total: string;
  notes?: string;
};

export type SalesQuotationDetail = SalesQuotationRow & {
  currency: number;
  currency_code?: string;
  exchange_rate: string;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  lines: {
    id: number;
    product: number;
    product_name?: string;
    quantity: string;
    unit_price: string;
    line_discount: string;
    tax_rate: number | null;
    line_total: string;
  }[];
};

export async function listQuotations(): Promise<SalesQuotationRow[]> {
  return apiGetList(`${BASE}/quotations/`, { tenantId: tid() });
}

export async function getQuotation(id: number): Promise<SalesQuotationDetail> {
  return apiGetObject(`${BASE}/quotations/${id}/`, { tenantId: tid() });
}

export async function createQuotation(
  body: Record<string, unknown>,
): Promise<SalesQuotationDetail> {
  return apiPostObject(`${BASE}/quotations/`, body, { tenantId: tid() });
}

export async function updateQuotation(
  id: number,
  body: Record<string, unknown>,
): Promise<SalesQuotationDetail> {
  return apiPatchObject(`${BASE}/quotations/${id}/`, body, { tenantId: tid() });
}

export async function deleteQuotation(id: number): Promise<void> {
  return apiDelete(`${BASE}/quotations/${id}/`, { tenantId: tid() });
}

export async function convertQuotationToInvoice(
  id: number,
): Promise<{ invoice_id: number; invoice_number: string }> {
  return apiPostObject(
    `${BASE}/quotations/${id}/convert/`,
    {},
    { tenantId: tid() },
  );
}

// -------------------------------------------------------------
// M4-T4 — Credit / Debit notes (إشعارات مدينة/دائنة)
// -------------------------------------------------------------
export type CreditDebitNoteRow = {
  id: number;
  note_number: string;
  note_date: string;
  note_type: "credit" | "debit";
  customer: number;
  customer_name?: string;
  related_invoice: number | null;
  related_invoice_number?: string | null;
  amount: string;
  reason?: string;
  status: string;
  journal?: number | null;
  created_at?: string;
};

export async function listCreditDebitNotes(): Promise<CreditDebitNoteRow[]> {
  return apiGetList(`${BASE}/credit-debit-notes/`, { tenantId: tid() });
}

export async function getCreditDebitNote(id: number): Promise<CreditDebitNoteRow> {
  return apiGetObject(`${BASE}/credit-debit-notes/${id}/`, { tenantId: tid() });
}

export async function createCreditDebitNote(
  body: {
    note_date: string;
    note_type: "credit" | "debit";
    customer: number;
    related_invoice?: number | null;
    amount: string | number;
    reason?: string;
  },
): Promise<CreditDebitNoteRow> {
  return apiPostObject(`${BASE}/credit-debit-notes/`, body, { tenantId: tid() });
}

export async function updateCreditDebitNote(
  id: number,
  body: Partial<{
    note_date: string;
    note_type: "credit" | "debit";
    customer: number;
    related_invoice: number | null;
    amount: string | number;
    reason: string;
  }>,
): Promise<CreditDebitNoteRow> {
  return apiPatchObject(`${BASE}/credit-debit-notes/${id}/`, body, { tenantId: tid() });
}

export async function deleteCreditDebitNote(id: number): Promise<void> {
  return apiDelete(`${BASE}/credit-debit-notes/${id}/`, { tenantId: tid() });
}

export async function postCreditDebitNote(id: number): Promise<CreditDebitNoteRow> {
  return apiPostObject(
    `${BASE}/credit-debit-notes/${id}/post/`,
    {},
    { tenantId: tid() },
  );
}
