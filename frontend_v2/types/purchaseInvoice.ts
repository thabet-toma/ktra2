export interface PurchaseInvoiceItemDto {
  id?: number;
  product?: number | null;
  product_name?: string | null;
  name: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  notes?: string | null;
  hs_code?: string | null;
  landed_unit_price_ils?: number | null;
  landed_line_total_ils?: number | null;
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
  notes?: string | null;
  supplier_invoice_number?: string | null;
  factory_name?: string | null;
  is_posted?: boolean;
  journal?: number | null;
  journal_id_display?: number | null;
  firestore_id?: string | null;
  items: PurchaseInvoiceItemDto[];
  created_at?: string;
  updated_at?: string;
  created_by?: number | null;
}
