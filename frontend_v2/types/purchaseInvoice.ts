export interface PurchaseInvoiceItemDto {
  id?: number;
  product?: number | null;
  product_name?: string | null;
  name: string;
  quantity: number;
  received_quantity?: number;
  /** T-RECVIS: الباقي على البند (الكمية − المستلَم) — يحسبه الخادم لا الشاشة. */
  remaining_quantity?: string;
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
  /** T-SERIAL: أرقام وحدات البند (نيّة على البند؛ الوحدات تُنشأ عند الاستلام). */
  serials?: string[] | null;
}

export type ReceiptStatus =
  | "not_received"
  | "partially_received"
  | "received";

/**
 * T-RECVIS: ملخّص استلام الفاتورة — «استُلم X من Y — باقي Z».
 *
 * الكميات نصوص (Decimal بدقّة أربع خانات لا يُسلسَل float بأمانة)، والعدّان
 * أعدادٌ صحيحة. تعدّ الأصناف المخزنية وحدها — بند الخدمة لا يدخل مستودعاً.
 */
export interface ReceiptProgressDto {
  ordered: string;
  received: string;
  remaining: string;
  lines_total: number;
  lines_remaining: number;
}

export interface PurchaseInvoiceFeeDto {
  id?: number;
  description: string;
  amount: number;
  calculation_type?: "amount" | "percentage";
  calculation_value?: number;
  percentage_basis?: "goods" | "after_main_vat";
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
  invoice_type?: "local" | "international";
  partner: number;
  partner_name: string;
  deal?: number | null;
  deal_ref?: string | null;
  /** اسم الصفقة المحوَّلة (من قائمة الصفقات) */
  deal_title?: string | null;
  shipment?: number | null;
  shipment_number?: string | null;
  shipment_name?: string | null;
  clearance?: number | null;
  currency?: number | null;
  currency_code?: string | null;
  exchange_rate: number;
  subtotal: number;
  discount_amount: number;
  tax_rate: number;
  tax_amount: number;
  grand_total: number;
  fees_total?: string;
  payable_total?: string;
  amount_paid?: string;
  remaining_balance?: string;
  payment_status?: "paid" | "partially_paid" | "unpaid";
  payment_status_display?: string;
  supplier_balance?: string;
  status: string;
  status_display: string;
  receipt_status?: ReceiptStatus;
  receipt_status_display?: string;
  is_posted: boolean;
  is_return?: boolean;
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
  /** اسم الصفقة المحوَّلة (من قائمة الصفقات) */
  deal_title?: string | null;
  shipment?: number | null;
  shipment_number?: string | null;
  shipment_name?: string | null;
  clearance?: number | null;
  /** T-PLINEAGE: المستند الذي وُلدت منه الفاتورة (عرض سعر أو طلبية شراء). */
  source_document?: {
    kind: "order" | "quotation";
    id: number;
    number: string;
    origin_kind?: "quotation" | null;
    origin_id?: number | null;
    origin_number?: string | null;
  } | null;
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
  invoice_type?: "local" | "international";
  fees_total?: string;
  payable_total?: string;
  local_payments_json?: Record<string, unknown> | null;
  conversion_metadata_json?: Record<string, unknown> | null;
  status: string;
  status_display?: string;
  receipt_status?: ReceiptStatus;
  receipt_status_display?: string;
  /** T-RECVIS: ملخّص الاستلام — على قراءة الفاتورة الكاملة فقط لا على القائمة. */
  receipt_progress?: ReceiptProgressDto;
  is_local?: boolean;
  // task16 C10: حالة الدفع + المبلغ المدفوع + المتبقي (محسوبة في الخادم)
  amount_paid?: string;
  remaining_balance?: string;
  payment_status?: "paid" | "partially_paid" | "unpaid";
  payment_status_display?: string;
  supplier_balance_current?: string;
  supplier_balance_before_invoice?: string;
  supplier_balance_after_invoice?: string;
  payment_details?: Array<{
    source: "supplier_payment" | "purchase_invoice_payment";
    id: number;
    payment_date: string;
    amount: string;
    currency_code: string;
    exchange_rate: string;
    cash_or_bank_account_name?: string | null;
    is_posted: boolean;
    journal: number | null;
    notes?: string;
  }>;
  notes?: string | null;
  supplier_invoice_number?: string | null;
  factory_name?: string | null;
  is_posted?: boolean;
  // W7a: هوية مستند المرجع.
  is_return?: boolean;
  original_invoice?: number | null;
  original_invoice_number?: string | null;
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
  // W7c: مرفقات الفاتورة/المرجع (صور + PDF) — قراءة من الخادم، تُرسل عند الحفظ.
  quote_images?: string[];
  quote_pdfs?: { name: string; url: string; size: number; type: string }[];
}
