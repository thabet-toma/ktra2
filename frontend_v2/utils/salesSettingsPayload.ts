import type { SalesSettings } from '../services/salesApi';

// الحقول القابلة للكتابة في إعدادات المبيعات — نتجاهل الـ read-only مثل *_name.
// قائمةٌ واحدة: حقلٌ يُعرض في الصفحة ويغيب من هنا يُحرَّر ثم يسقط بصمت عند الحفظ
// (هكذا ضاع قسم «مستند التسليم» كاملاً).
const WRITABLE_KEYS = [
  'default_customer',
  'default_currency',
  'default_revenue_account_product',
  'default_revenue_account_service',
  'default_cash_account',
  'default_inventory_account',
  'default_cogs_account',
  'default_ar_account',
  'default_payment_type',
  'stock_on_post_default',
  'negative_stock_policy',
  'default_vat_rate',
  'prices_include_tax',
  'auto_post_invoices',
  'auto_post_payments',
  'auto_refund_on_sales_return',
  'show_journal_preview',
  'warn_on_duplicate_item',
  'loss_invoice_policy',
  'dormant_customer_days',
  'quotation_valid_days',
  'order_reserve_days',
  'allow_document_delete',
  'block_reserved_stock_sale',
  'serial_entry_mode',
  'default_shipping_origin',
  'default_shipping_destination',
  'delivery_doc_label',
  'standalone_delivery_label',
  'allow_standalone_delivery',
  'allow_edit_delivery',
] as const satisfies readonly (keyof SalesSettings)[];

export function salesSettingsWritablePayload(settings: SalesSettings): Partial<SalesSettings> {
  const payload: Partial<SalesSettings> = {};
  for (const key of WRITABLE_KEYS) {
    (payload as Record<string, unknown>)[key] = settings[key];
  }
  return payload;
}
