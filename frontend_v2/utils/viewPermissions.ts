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
  "sales-delivery-notes": "sales.invoice.view",
  "invoice-profits": "inventory.cost.view",
  "reserved-stock": "sales.quotation.manage",
  "sales-settings": "sales.settings.manage",
  "sales-classic": "sales.invoice.view",
  // العملاء
  "sales-customers": "sales.customer.view",
  "sales-customer-payments": "sales.payment.create",
  "partner-profile": "sales.customer.view",
  // المشتريات
  "purchase-invoices": "purchase.invoice.view",
  "price-offers": "purchase.invoice.view",
  "purchase-return": "purchase.invoice.view",
  "purchase-receipts": "purchase.invoice.view",
  "supplier-payments": "purchase.payment.create",
  "purchase-settings": "purchase.settings.manage",
  "supplier-management": "purchase.supplier.view",
  // الاستيراد (يبقى مشروطاً أيضاً بتفعيل الوحدة للشركة)
  "import-offers": "import.deal.manage",
  "international-invoices": "import.deal.manage",
  "deals-management": "import.deal.manage",
  "old-invoices": "import.deal.manage",
  "import-flow": "import.deal.manage",
  // THA-114: شرح مستندات ملف الاستيراد — مشروط أيضاً بترخيص الوحدة أدناه.
  "import-file-guide": "importfile.file.view",
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
  "accounting-banks": "accounting.account.manage",
  "accounting-bank-reconciliation": "accounting.journal.view",
  "accounting-general-ledger": "accounting.journal.view",
  "accounting-exchange-rates": "accounting.journal.view",
  "property-rental": "accounting.journal.view",
  "accounting-trial-balance": "accounting.report.view",
  "accounting-vat-report": "accounting.report.view",
  "accounting-vat-statements": "accounting.report.view",
  "accounting-landed-cost": "accounting.report.view",
  "accounting-balance-sheet": "accounting.report.view",
  "accounting-income-statement": "accounting.report.view",
  // T-REPORTS: فهرس التقارير مفتوح — الخادم يصفّي كل تقرير بصلاحيته الخاصة
  // (`/api/reports/`)، فحصْره بصلاحية محاسبية واحدة كان يحجب تقارير المبيعات
  // والمخزون عن أصحابها. «تقارير الفريق» القديمة تبقى إدارية.
  "team-time-report": "hr.employees.manage",
  "accounting-fiscal-periods": "accounting.period.manage",
  "accounting-year-end-close": "accounting.period.manage",
  // الأرصدة الافتتاحية: إدخالٌ يُنتج قيداً — الترحيل وإلغاؤه محروسان خادمياً
  // بصلاحيتَيهما، وهذا مفتاح رؤية الشاشة لا إذن الترحيل.
  "accounting-opening-balances": "accounting.journal.create",
  // شؤون الموظفين والإدارة
  users: "hr.employees.manage",
  "employee-notes": "hr.employees.manage",
  attendance: "hr.attendance.view",
  payroll: "hr.payroll.view",
  "points-management": "hr.points.manage",
  "task-management": "hr.tasks.manage",
  "activity-log": "admin.activity.view",
  permissions: "admin.permissions.manage",
  // ST-3: «متجري» — فتح المتجر العام واختيار رابطه وتحديد ما يُنشر فيه.
  "store-settings": "store.manage",
  "company-accountant-engagements": "admin.members.manage",
  // THA-45: وحدة الأجهزة الحساسة — مشروطة أيضاً بترخيص الوحدة أدناه.
  "sensitive-devices": "devices.registry.view",
  // THA-24: بطاقات الكفالة — وحدة «خدمة ما بعد البيع» المرخّصة.
  "after-sales": "aftersales.warranty.view",
  // THA-24 م4: أوامر الصيانة — نفس الوحدة، ومفتاح صلاحيتها مستقل: من يرى
  // الكفالات لا يرى بالضرورة ملفات الصيانة (مفاتيح الخادم السبعة منفصلة).
  "service-orders": "aftersales.order.view",
  // «الرئيسية» تختار بين اللوحة التجارية والشخصية — لا تُدرَج هنا كي لا تُحجب
  // الشاشة كلياً؛ الاختيار يتم بدور manager الفعلي في App.tsx.
};

/**
 * T-EXTACCT: شاشات الوحدات المرخّصة لكل شركة. الشاشة هنا لا تُعرض ولا تُوجَّه
 * إليها ما لم تكن وحدتها مرخّصة — والحارس يسبق `import()` فلا يُنزَّل chunkها
 * أصلاً للشركة غير المرخّصة.
 *
 * ملاحظة مقصودة: شاشات المحاسب نفسه ليست هنا — فهي في قشرة المكتب المستقلة،
 * ويبلغها المحاسب بلا أي عضوية في شركة تجارية.
 */
export const VIEW_MODULES: Record<string, string> = {
  // شاشة واحدة فقط داخل النظام التجاري: «واجهة المحاسب القانوني». بقية شاشات
  // المحاسب تعيش في قشرة المكتب المستقلة ولا تخصّ الشركة التجارية أصلاً.
  "company-accountant-engagements": "accountant_portal",
  // THA-45: سجل الأجهزة الحساسة. الخادم يرد 404 لا 403 على شركةٍ غير مرخّصة،
  // وهذا المدخل يمنع حتى تنزيل chunk الشاشة عندها.
  "sensitive-devices": "sensitive_devices",
  // THA-24: خدمة ما بعد البيع — نفس العقد: 404 خادمياً، وبلا العَلَم لا يُطلب chunk.
  "after-sales": "after_sales",
  "service-orders": "after_sales",
  // THA-114: ملف الاستيراد — نفس العقد: 404 خادمياً (`import_file/views.py`)،
  // وبلا العَلَم لا يُطلب chunk الشاشة. لوحة الملف داخل الصفقة محروسة بالعَلَم
  // نفسه في `DealForm.tsx` — تبويب لا يُبنى أصلاً بلا ترخيص.
  "import-file-guide": "import_file",
};

/** صلاحية الشاشة إن وُجدت، وإلا undefined (شاشة مفتوحة). */
export const permForView = (view: string): string | undefined =>
  VIEW_PERMISSIONS[view];

/** وحدة الشاشة إن كانت شاشة وحدة مرخّصة. */
export const moduleForView = (view: string): string | undefined =>
  VIEW_MODULES[view];

/**
 * يفشل **مغلقاً**: ما لم تصل أعلام الوحدات بقيمة `true` صريحة تُعدّ الوحدة
 * مطفأة. عكس `can()` — فهذه ترخيص لا تجميل.
 */
export const moduleAllowsView = (
  view: string,
  modules?: Record<string, boolean> | null,
): boolean => {
  const key = VIEW_MODULES[view];
  return !key || modules?.[key] === true;
};

/** أين يظهر بند «الأجهزة الحساسة» في الشريط الجانبي. */
export type DevicesNavPlacement = "hidden" | "standalone" | "after-sales";

/**
 * THA-24: بندٌ واحد للأجهزة الحساسة لا اثنان.
 *
 * المالك يعدّ سجل الأجهزة الحساسة إجراءً ضمن نظام ما بعد البيع، فحين تُرخَّص
 * الوحدتان معاً ينتقل البند تحت قسم «خدمة ما بعد البيع»؛ وحين تُرخَّص وحدة
 * الأجهزة وحدها يبقى حيث هو اليوم — عقد THA-45 يقول إنها تُطفأ وتُشغَّل
 * باستقلال، فلا يختفي بندها لغياب وحدةٍ أخرى.
 *
 * القرار هنا لا داخل JSX: `tsc` لا يفحص خصائص JSX في هذا المستودع، فقاعدةٌ
 * مدفونة في الشرط لا يحرسها شيء.
 */
export const devicesNavPlacement = (
  modules?: Record<string, boolean> | null,
): DevicesNavPlacement => {
  if (!moduleAllowsView("sensitive-devices", modules)) return "hidden";
  return moduleAllowsView("after-sales", modules) ? "after-sales" : "standalone";
};

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

/**
 * T-PERMBOX: تحويل نقرة **خانة اختيار** واحدة إلى تجاوز فردي للعضو.
 *
 * الخانة تعرض الحالة الفعلية (مؤشَّرة = ممنوحة)، والمخزون ثلاثيّ: منح، منع، أو
 * لا شيء (يتبع الدور). فإن ساوى المطلوبُ ما يعطيه الدور أصلاً نُرجع `null`
 * فيُحذف التجاوز — فلا نُخزّن صفّاً يساوي الافتراضي (نفس قاعدة تبويب الأدوار).
 */
export const memberOverrideForCheckbox = (
  roleAllowed: boolean,
  nextChecked: boolean,
): boolean | null => (nextChecked === roleAllowed ? null : nextChecked);
