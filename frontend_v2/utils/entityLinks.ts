/**
 * task16 (A4-A6): روابط موحّدة بين الكيانات.
 *
 * أي مرجع لفاتورة (في حركات المخزن، قيود اليومية، …) يجب أن يفتح الفاتورة
 * نفسها. هذه الدالة تترجم (reference_type, reference_id) إلى مسار الفاتورة.
 * مصدر حقيقة واحد كي لا يتكرر منطق المطابقة في كل شاشة (DRY).
 */
export function invoicePathForReference(
  referenceType?: string | null,
  referenceId?: number | null
): string | null {
  if (referenceId == null) return null;
  const t = (referenceType || "").toUpperCase();
  // مراجع فاتورة الشراء (الاستلام/الترحيل)
  if (t.includes("PURCHASE_INVOICE")) return `/purchase-invoices/${referenceId}`;
  // مراجع فاتورة المبيعات: الفاتورة نفسها + حركات المخزون/التكلفة الناتجة عنها
  if (
    t.includes("SALES_INVOICE") ||
    t.includes("SALES_DELIVERY") ||
    t === "SALE" ||
    t === "STOCK_ISSUE"
  ) {
    return `/sales/invoices/${referenceId}`;
  }
  return null;
}

/**
 * task16 A4 / ربط المنتجات: رابط بطاقة الصنف. أي «ذكر لمنتج» في الموقع يجب أن
 * يكون قابلاً للنقر ويفتح بطاقة الصنف على تبويب «حركة المخزون» (لا النظرة العامة)
 * — مصدر حقيقة واحد كي لا يتكرر بناء المسار في كل شاشة (DRY). التبويب يُمرَّر
 * عبر `?tab=` ويُقرأ في `ProductProfilePage` كـ `initialTab`.
 */
export function productProfilePath(
  productId: number | string,
  tab: "kpis" | "invoices" | "ledger" = "ledger"
): string {
  return `/products/${productId}?tab=${tab}`;
}

export function supplierPath(): string {
  return "/suppliers";
}

export function customerPath(): string {
  return "/sales/customers";
}
