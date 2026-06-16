export interface PurchaseInvoiceItemDto {
  id?: number;
  product?: number | null;
  product_name?: string | null;
  name: string;
  quantity: number;
  received_quantity?: number;
  unit_price: number;
  total_price: number;
  notes?: string | null;
  hs_code?: string | null;
  warehouse?: string | null;
  landed_unit_price_ils?: number | null;
  landed_line_total_ils?: number | null;
  expense_account?: number | null;
  expense_account_code?: string | null;
  expense_account_name?: string | null;
}

export type ReceiptStatus =
  | "not_received"
  | "partially_received"
  | "received";

export interface PurchaseInvoiceFeeDto {
  id?: number;
  description: string;
  amount: number;
  expense_account: number;
  expense_account_code?: string | null;
  expense_account_name?: string | null;
  expense_account_type?: string | null;
  capitalize_to_inventory?: boolean;
  is_taxable?: boolean;
}

export interface PurchaseInvoiceListDto {
  id: number;
  invoice_number: string;
  invoice_name?: string | null;
  invoice_date?: string | null;
  partner: number;
  partner_name: string;
  deal?: number | null;
  deal_ref?: string | null;
  shipment?: number | null;
  clearance?: number | null;
  currency?: number | null;
  currency_code?: string | null;
  exchange_rate: number;
  subtotal: number;
  discount_amount: number;
  tax_rate: number;
  tax_amount: number;
  grand_total: number;
  status: string;
  status_display: string;
  receipt_status?: ReceiptStatus;
  receipt_status_display?: string;
  is_posted: boolean;
  journal_id_display?: number | null;
  items_count: number;
  created_at: string;
  updated_at: string;
}

export interface PurchaseInvoiceDto {
  id?: number;
  invoice_number?: string;
  invoice_name?: string | null;
  invoice_date?: string | null;
  partner: number;
  partner_name?: string;
  deal?: number | null;
  deal_ref?: string | null;
  shipment?: number | null;
  clearance?: number | null;
  currency?: number | null;
  currency_code?: string | null;
  exchange_rate?: number;
  subtotal: number;
  discount_amount?: number;
  tax_rate?: number;
  tax_amount?: number;
  tax_type?: "percentage" | "amount";
  shipping_cost?: number;
  shipping_included?: boolean;
  grand_total: number;
  local_payments_json?: Record<string, unknown> | null;
  conversion_metadata_json?: Record<string, unknown> | null;
  status: string;
  status_display?: string;
  receipt_status?: ReceiptStatus;
  receipt_status_display?: string;
  is_local?: boolean;
  // task16 C10: حالة الدفع + المبلغ المدفوع + المتبقي (محسوبة في الخادم)
  amount_paid?: string;
  remaining_balance?: string;
  payment_status?: "paid" | "partially_paid" | "unpaid";
  payment_status_display?: string;
  notes?: string | null;
  supplier_invoice_number?: string | null;
  factory_name?: string | null;
  is_posted?: boolean;
  journal?: number | null;
  journal_id_display?: number | null;
  firestore_id?: string | null;
  items: PurchaseInvoiceItemDto[];
  fees?: PurchaseInvoiceFeeDto[];
  payment_type?: "credit" | "cash";
  cash_or_bank_account?: number | null;
  cash_or_bank_account_name?: string | null;
  cash_or_bank_account_code?: string | null;
  created_at?: string;
  updated_at?: string;
  created_by?: number | null;
}
