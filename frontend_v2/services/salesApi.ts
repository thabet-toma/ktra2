import { resolveTenantId } from "../utils/tenantContext";
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
  }[];
  created_at?: string;
};

export async function listSalesInvoices(
  query?: Record<string, string | number | boolean | undefined>
): Promise<SalesInvoiceRow[]> {
  return apiGetList(`${BASE}/invoices/`, { tenantId: tid(), query });
}

export async function getSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiGetObject(`${BASE}/invoices/${id}/`, { tenantId: tid() });
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
  return apiPatchObject(`${BASE}/settings/current/`, body, { tenantId: tid() });
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
