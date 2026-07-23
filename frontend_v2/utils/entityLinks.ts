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

/** مسار مستند/حركة من سجل النشاط أو كشف الحساب — مصدر تنقّل واحد. */
export function entityPathForReference(
  referenceType?: string | null,
  referenceId?: number | null
): string | null {
  const invoicePath = invoicePathForReference(referenceType, referenceId);
  if (invoicePath) return invoicePath;
  if (referenceId == null) return null;
  const t = (referenceType || "").toUpperCase();
  if (t === "DEAL" || t === "LOGISTICS_DEAL") return `/deals/${referenceId}`;
  if (t === "SHIPMENT" || t === "LOGISTICS_SHIPMENT") return `/import-flow/${referenceId}`;
  if (t === "CUSTOMER_PAYMENT") return `/sales/customer-payments?payment_id=${referenceId}`;
  if (t === "SUPPLIER_PAYMENT") return `/supplier-payments?payment_id=${referenceId}`;
  return null;
}

/**
 * كشف الحساب: تسمية عربية واضحة لنوع الحركة بدل رمز `reference_type` الإنجليزي الخام
 * (SALES_INVOICE / CUSTOMER_PAYMENT …). مصدر حقيقة واحد يخدم كشف الحساب ونافذة التفاصيل.
 */
export function referenceTypeLabel(referenceType?: string | null): string {
  const t = (referenceType || "").toUpperCase();
  if (!t) return "حركة";
  if (t.includes("SALES_RETURN")) return "مرتجع مبيعات";
  if (t.includes("PURCHASE_RETURN")) return "مرتجع مشتريات";
  if (
    t.includes("SALES_INVOICE") ||
    t.includes("SALES_DELIVERY") ||
    t === "SALE" ||
    t === "STOCK_ISSUE"
  )
    return "فاتورة مبيعات";
  if (t.includes("PURCHASE_INVOICE") || t === "PURCHASE_RECEIPT") return "فاتورة مشتريات";
  if (t === "CUSTOMER_PAYMENT") return "سند قبض";
  if (t === "SUPPLIER_PAYMENT") return "سند صرف";
  if (t === "LOGISTICS_CLEARANCE") return "مستحق تخليص";
  if (t === "CLEARANCE_PAYMENT") return "دفع تخليص جمركي";
  if (t === "LOCAL_SHIPMENT") return "ارسالية";
  if (t === "LOCAL_SHIPMENT_PAYMENT") return "دفع للناقل";
  if (t === "LOGISTICS_PAYMENT" || t === "PAYMENT") return "سند دفع";
  if (t === "CREDIT_DEBIT_NOTE") return "إشعار مدين/دائن";
  if (t === "PARTNER_OPENING") return "رصيد افتتاحي";
  if (t === "JOURNAL_REVERSAL") return "عكس قيد";
  return "قيد يومية";
}

/**
 * كشف الحساب: «بيان» مقروء بدل مصطلح الحساب الخام («ذمم» / «تسديد ذمم») الذي يربك
 * المستخدم. يستبدل الجزء الأول (اسم الحساب) بتسمية الحركة العربية ويُبقي رقم المستند
 * في الذيل — يعمل على البيانات القديمة (تحويل وقت العرض، بلا مساس بسجلّ القيد).
 * الفاصل em-dash «—» (رقم الفاتورة مثل SI-1-6 يستخدم شرطة ASCII، فالفصل آمن).
 */
export function clarifyStatementDescription(
  referenceType?: string | null,
  description?: string | null
): string {
  const label = referenceTypeLabel(referenceType);
  const desc = (description || "").trim();
  if (!desc) return label;
  const sep = desc.indexOf("—");
  const tail = sep >= 0 ? desc.slice(sep + 1).trim() : "";
  return tail ? `${label} — ${tail}` : desc;
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
