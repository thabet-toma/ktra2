/**
 * ISSUE #147 — قاعدةُ خريطة سعر الزبون (`sales/customer-price-list/`) في مكانٍ
 * واحد: **وجودُ السعر لا كونُه موجباً**. سطرٌ بِيع فعلاً بصفر (هديّة، أو بندٌ
 * مجّانيّ ضمن صفقة) رقمٌ حقيقيٌّ في تاريخ الزبون، وإسقاطُه يجعل المنتقي يقول
 * «سعر عام»/«بدون سعر» وهو كاذب. والقاعدةُ الذهبية «فارغٌ يبقى فارغاً» تمنع
 * اختلاقَ صفرٍ لا وجود له، لا إخفاءَ صفرٍ موجود.
 *
 * مستهلكوها: `SalesInvoiceEditor.tsx` · `SalesQuotationsPage.tsx` ·
 * `SalesOrdersPage.tsx` — كانت فاتورةُ البيع وحدها على `Number(price) > 0`.
 */
export function hasRecordedCustomerPrice(price: unknown): boolean {
  return price != null && String(price).trim() !== "";
}
