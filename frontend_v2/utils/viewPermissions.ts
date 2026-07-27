/**
 * T-PERM (المرحلة 2، البند 1): خريطة **واحدة** «شاشة ← صلاحية».
 *
 * يستهلكها موضعان لا ثالث لهما: الشريط الجانبي (إخفاء الروابط) وموجّه `App.tsx`
 * (منع الدخول المباشر بالرابط). لولا التوحيد لظهر رابطٌ يقود إلى لوحة التحكم —
 * قائمة تَعِد بما لا تُنجزه.
 *
 * الشاشة غير المذكورة هنا مفتوحة للجميع (صالة الصور، من نحن، مهامي…).
 * مفاتيح الصلاحيات مطابقة لكتالوج `core/access.py`.
 */
export const VIEW_PERMISSIONS: Record<string, string> = {
  // المبيعات
  "sales-invoices": "sales.invoice.view",
  "sales-quotations": "sales.quotation.manage",
  "sales-orders": "sales.quotation.manage",
  "credit-debit-notes": "sales.invoice.view",
  "sales-return": "sales.invoice.view",
  "invoice-profits": "inventory.cost.view",
  "sales-settings": "sales.settings.manage",
  "aseel-sales": "sales.invoice.view",
  // العملاء
  "sales-customers": "sales.customer.view",
  "sales-customer-payments": "sales.payment.create",
  "partner-profile": "sales.customer.view",
  // المشتريات
  "purchase-invoices": "purchase.invoice.view",
  "price-offers": "purchase.invoice.view",
  "purchase-return": "purchase.invoice.view",
  "supplier-payments": "purchase.payment.create",
  "purchase-settings": "purchase.settings.manage",
  "supplier-management": "purchase.supplier.view",
  // الاستيراد (يبقى مشروطاً أيضاً بتفعيل الوحدة للشركة)
  "import-offers": "import.deal.manage",
  "international-invoices": "import.deal.manage",
  "deals-management": "import.deal.manage",
  "old-invoices": "import.deal.manage",
  "import-flow": "import.deal.manage",
  "shipments-management": "import.shipment.manage",
  "shipment-management": "import.shipment.manage",
  shipments: "import.shipment.manage",
  "local-shipping": "import.shipment.manage",
  "customs-clearance": "import.shipment.manage",
  clearance: "import.shipment.manage",
  // المخزون
  "stock-levels": "inventory.item.view",
  "items-management": "inventory.item.view",
  "items-categories": "inventory.item.manage",
  "stock-movements": "inventory.item.view",
  "product-profile": "inventory.item.view",
  "product-group": "inventory.item.view",
  "product-cost": "inventory.cost.view",
  warehouses: "inventory.item.manage",
  "warehouse-transfer": "inventory.doc.post",
  stocktake: "inventory.doc.post",
  // المالية والمحاسبة
  "cash-boxes": "finance.cashbox.manage",
  "accounting-coa": "accounting.account.manage",
  "accounting-journals": "accounting.journal.view",
  "accounting-journal-entry": "accounting.journal.create",
  "accounting-cheques": "accounting.journal.view",
  "accounting-general-ledger": "accounting.journal.view",
  "accounting-exchange-rates": "accounting.journal.view",
  "property-rental": "accounting.journal.view",
  "accounting-trial-balance": "accounting.report.view",
  "accounting-vat-report": "accounting.report.view",
  "accounting-vat-statements": "accounting.report.view",
  "accounting-landed-cost": "accounting.report.view",
  "accounting-balance-sheet": "accounting.report.view",
  "accounting-income-statement": "accounting.report.view",
  reports: "accounting.report.view",
  "accounting-fiscal-periods": "accounting.period.manage",
  "accounting-year-end-close": "accounting.period.manage",
  // شؤون الموظفين والإدارة
  users: "hr.employees.manage",
  "employee-notes": "hr.employees.manage",
  attendance: "hr.attendance.view",
  "points-management": "hr.points.manage",
  "task-management": "hr.tasks.manage",
  "activity-log": "admin.activity.view",
  permissions: "admin.permissions.manage",
  // «الرئيسية» تختار بين اللوحة التجارية والشخصية — لا تُدرَج هنا كي لا تُحجب
  // الشاشة كلياً؛ الاختيار يتم بدور manager الفعلي في App.tsx.
};

/** صلاحية الشاشة إن وُجدت، وإلا undefined (شاشة مفتوحة). */
export const permForView = (view: string): string | undefined =>
  VIEW_PERMISSIONS[view];

export type InvoicePermissionScope = "sales" | "purchase";

/**
 * سياسة واحدة لأزرار الفاتورة المركّبة:
 * - الجديدة تُحفَظ بصلاحية الإنشاء.
 * - القائمة تُحفَظ بصلاحية التعديل.
 * - «حفظ وترحيل» يحتاج صلاحية الحفظ المناسبة + الترحيل.
 */
export const invoiceActionPermissions = (
  scope: InvoicePermissionScope,
  isNew: boolean,
  can: (key: string) => boolean,
): { canSave: boolean; canPost: boolean; canSaveAndPost: boolean } => {
  const canSave = can(`${scope}.invoice.${isNew ? "create" : "edit"}`);
  const canPost = can(`${scope}.invoice.post`);
  return { canSave, canPost, canSaveAndPost: canSave && canPost };
};
