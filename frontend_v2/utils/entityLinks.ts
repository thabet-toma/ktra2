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
 * task16 A4: روابط الكيانات (مورد/عميل/صنف). لا توجد مسارات تفصيل مستقلة لكل
 * كيان في النظام الحالي — يفتح الرابط صفحة إدارة الكيان (يمكن لاحقاً توجيهه
 * لصفحة تفصيل مخصّصة دون تغيير المستهلكين).
 */
export function productPath(): string {
  return "/items";
}

export function supplierPath(): string {
  return "/suppliers";
}

export function customerPath(): string {
  return "/sales/customers";
}
