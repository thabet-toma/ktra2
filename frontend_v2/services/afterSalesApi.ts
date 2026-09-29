/**
 * THA-24 م2 — عميل REST لوحدة «خدمة ما بعد البيع» (بطاقات الكفالة).
 *
 * الخادم `after_sales/views.py` يفتح كل نقطة ببوابة الترخيص **قبل** الصلاحية،
 * فيردّ **404 لا 403** على شركةٍ غير مرخّصة — الفشل هنا يُقرأ «لا وجود للوحدة».
 * لذلك لا تُبنى في الواجهة طبقةُ إخفاءٍ ثالثة: الشاشة خلف حارس الترخيص في
 * `App.tsx`، والصلاحيات تُعطّل ما لا يملكه المستخدم داخلها.
 *
 * **حالة الكفالة مشتقّة دائماً** من `end_date` — لا حقل حالة يُرسَل ولا يُخزَّن،
 * والخادم يردّ `status` و`days_remaining` محسوبَين عند كل قراءة.
 */
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiGetPagedList,
  apiPatchObject,
  apiPostObject,
  type PagedList,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";
import type { WarrantySource, WarrantyStatus } from "../utils/warranty";

const BASE = "after-sales/warranties/";

const tenantOpts = () => ({ tenantId: resolveTenantId() });

// المصدر والحالة معرَّفتان في `utils/warranty` مع القواعد التي تحكمهما،
// ويُعاد تصديرهما هنا كي تستوردهما الشاشات من عميلها الواحد.
export type { WarrantySource, WarrantyStatus };

export interface WarrantyCardRow {
  id: number;
  product: number | null;
  product_name: string;
  device_name: string;
  serial: string;
  product_serial: number | null;
  sales_invoice_line: number | null;
  sales_invoice: number | null;
  sales_invoice_number: string | null;
  partner: number | null;
  partner_name: string;
  customer_name: string;
  customer_phone: string;
  start_date: string;
  duration_months: number;
  end_date: string;
  source: WarrantySource;
  source_label: string;
  supplier: number | null;
  supplier_name: string;
  supplier_warranty_end_date: string | null;
  supplier_warranty_active: boolean;
  notes: string;
  // #232: طبقة كفالة المصنع — `manufacturer_warrantor` الفارغ = «لا يوجد»،
  // ومعه `manufacturer_status`/`manufacturer_days_remaining` بـ`null` حينها
  // (لا حالة رابعة، بل غياب طبقة). مجمَّدةٌ عند الإنشاء؛ `manufacturer_start_date`
  // وحدها قابلة للتعديل، وتُعيد `manufacturer_end_date` احتسابها من الخادم.
  manufacturer_warrantor: number | null;
  manufacturer_warrantor_name: string;
  manufacturer_start_date: string | null;
  manufacturer_duration_months: number;
  manufacturer_end_date: string | null;
  manufacturer_status: WarrantyStatus | null;
  manufacturer_days_remaining: number | null;
  status: WarrantyStatus;
  days_remaining: number;
  // #234: بطاقة «كفالة على الفاتورة» — صفرٌ على بطاقة وحدة مُرقَّمة (لا معنى
  // له هناك). `covered_quantity` محسوبةٌ في الخادم (`quantity − returned_quantity`)
  // لا تُعاد حسابها هنا.
  quantity: number;
  returned_quantity: number;
  covered_quantity: number;
  // #222: واقعة الانتهاء — `ended` يغلب `status`، والسبب يُعرض للموظف داخلياً
  // لا للزبون (الصفحة العامة لا تنشره، انظر `docshare/documents/aftersales_docs.py`).
  ended: boolean;
  ended_on: string | null;
  end_reason: string;
  end_reason_label: string;
  /** #236: إلغاء كفالة التاجر — `null` ما لم تُلغَ. */
  void: WarrantyVoidInfo | null;
  /** #237: رابط صفحة التحقق العامة — للموظف، والرمز نفسه لا يخرج حقلاً. */
  verify_url: string;
  created_at: string;
  updated_at: string;
}

/** #236: من ألغى الكفالة ولماذا — يقرؤه الموظف فقط، ولا يخرج للصفحة العامة. */
export interface WarrantyVoidInfo {
  reason: string;
  reason_label: string;
  note: string;
  voided_at: string;
  voided_by_name: string;
  service_order_number: string | null;
}

/** ما يُرسَل لإلغاء الكفالة أو لرفضها لهذا العطل. */
export interface WarrantyVoidInput {
  reason: string;
  note: string;
  service_order?: number | null;
}

/** معاينة أثر الإلغاء (`GET void-impact/`) — تُحسب بالدالة نفسها التي تنفّذه. */
export interface WarrantyVoidImpact {
  card_id: number;
  can_void: boolean;
  blockers: string[];
  orders: Array<{
    id: number;
    order_number: string;
    status: string;
    status_label: string;
    returns_to_approval: boolean;
    parts: Array<{
      id: number;
      product_name: string;
      quantity: string;
      unit_price: string;
      will_bill_price: string;
      empty_price: boolean;
    }>;
  }>;
}

/** ما يُرسَل عند إنشاء بطاقة يدوية أو تعديلها — المصدر والنسب من الخادم وحده. */
export interface WarrantyCardDraft {
  product: number | null;
  device_name: string;
  serial: string;
  partner: number | null;
  customer_name: string;
  customer_phone: string;
  start_date: string;
  duration_months: number | null;
  end_date?: string | null;
  supplier: number | null;
  supplier_warranty_end_date: string | null;
  // #232: بلا جهة، اتركها `null` وصفّر `manufacturer_duration_months` — يفرض
  // الخادم أن الجهة والمدة والبداية تجتمع أو تغيب معاً (`WarrantyCardSerializer.validate`).
  manufacturer_warrantor: number | null;
  manufacturer_start_date: string | null;
  manufacturer_duration_months: number | null;
  notes: string;
}

export interface WarrantyListFilters {
  q?: string;
  status?: WarrantyStatus | "";
  source?: WarrantySource | "";
  product?: number | "";
  partner?: number | "";
  expiring_within_days?: number | "";
}

/** ملخّص بطاقة كما يردّه `check/` — أضيق من صف القائمة. */
export interface WarrantyCoverageCard {
  id: number;
  serial: string;
  product: number | null;
  device_name: string;
  start_date: string;
  end_date: string;
  duration_months: number;
  source: WarrantySource;
  status: WarrantyStatus;
  days_remaining: number;
  customer_name: string;
  partner: number | null;
  supplier: number | null;
  supplier_warranty_end_date: string | null;
  supplier_warranty_active: boolean;
  // #232: طبقة المصنع — راجع الشرح في `WarrantyCardRow` أعلاه.
  manufacturer_warrantor: number | null;
  manufacturer_warrantor_name: string;
  manufacturer_start_date: string | null;
  manufacturer_duration_months: number;
  manufacturer_end_date: string | null;
  manufacturer_status: WarrantyStatus | null;
  manufacturer_days_remaining: number | null;
}

/** الوحدة المُرقَّمة كما يعرفها المخزون — تظهر ولو لم تكن لها بطاقة. */
export interface WarrantyCoverageUnit {
  id: number;
  serial: string;
  status: string;
  status_display: string;
  product: number | null;
  product_name: string;
  dealer_months: number | null;
  supplier_months: number | null;
  sales_invoice: number | null;
  sales_invoice_number: string | null;
  sale_date: string | null;
  customer_name: string | null;
}

export interface WarrantyCoverage {
  serial: string;
  covered: boolean;
  supplier_covered?: boolean;
  cards: WarrantyCoverageCard[];
  unit: WarrantyCoverageUnit | null;
}

/** التمديد: تاريخ نهاية جديد صريح، أو عدد أشهر يُضاف إلى النهاية الحالية. */
export interface WarrantyExtendInput {
  end_date?: string;
  months?: number;
  reason?: string;
}

/**
 * القائمة مُرقَّمة دائماً (`page`): البطاقات تُنشأ آلياً مع كل وحدة مباعة، فهي
 * تنمو بعدد المبيعات لا بعدد المنتجات — جلبها كاملة يثقل الشاشة بعد أشهر.
 */
export function listWarrantyCards(
  filters: WarrantyListFilters = {},
  page = 1,
  pageSize = 25,
): Promise<PagedList<WarrantyCardRow>> {
  return apiGetPagedList<WarrantyCardRow>(BASE, {
    ...tenantOpts(),
    query: {
      page,
      page_size: pageSize,
      q: filters.q?.trim() || undefined,
      status: filters.status || undefined,
      source: filters.source || undefined,
      product: filters.product || undefined,
      partner: filters.partner || undefined,
      expiring_within_days: filters.expiring_within_days || undefined,
    },
  });
}

export function getWarrantyCard(id: number): Promise<WarrantyCardRow> {
  return apiGetObject<WarrantyCardRow>(`${BASE}${id}/`, tenantOpts());
}

/** كل ما يُنشأ من هذه النقطة **يدويّ** — التلقائي من ترحيل الفاتورة وحده. */
export function createWarrantyCard(draft: WarrantyCardDraft): Promise<WarrantyCardRow> {
  return apiPostObject<WarrantyCardRow>(BASE, draft, tenantOpts());
}

/**
 * البطاقة التلقائية لا تقبل إلا تاريخ الانتهاء والملاحظات وكفالة المورد — يفرضه
 * الخادم ويردّ سببه نصّاً عربياً يعرضه `humanizeDrfError` كما هو.
 */
export function updateWarrantyCard(
  id: number,
  patch: Partial<WarrantyCardDraft>,
): Promise<WarrantyCardRow> {
  return apiPatchObject<WarrantyCardRow>(`${BASE}${id}/`, patch, tenantOpts());
}

/** حذف نهائي للبطاقة اليدوية؛ التلقائية يرفضها الخادم (تُحذف مع إلغاء الترحيل). */
export function deleteWarrantyCard(id: number): Promise<void> {
  return apiDelete(`${BASE}${id}/`, tenantOpts());
}

/** تمديد الكفالة مجاملةً — يُسجَّل حدث `extend` في سجل البطاقة (#229) لا في ملاحظاتها. */
export function extendWarrantyCard(
  id: number,
  input: WarrantyExtendInput,
): Promise<WarrantyCardRow> {
  return apiPostObject<WarrantyCardRow>(`${BASE}${id}/extend/`, input, tenantOpts());
}

export function getWarrantyVoidImpact(id: number): Promise<WarrantyVoidImpact> {
  return apiGetObject<WarrantyVoidImpact>(`${BASE}${id}/void-impact/`, tenantOpts());
}

export function voidWarrantyCard(id: number, input: WarrantyVoidInput): Promise<WarrantyCardRow> {
  return apiPostObject<WarrantyCardRow>(`${BASE}${id}/void/`, input, tenantOpts());
}

export function unvoidWarrantyCard(id: number, reason: string): Promise<WarrantyCardRow> {
  return apiPostObject<WarrantyCardRow>(`${BASE}${id}/unvoid/`, { reason }, tenantOpts());
}

/** تقصير نهاية كفالة التاجر — بصلاحية الإلغاء وسببٍ موثَّق (يُسجَّل بتاريخيه). */
export function shortenWarrantyCard(
  id: number,
  endDate: string,
  reason: string,
): Promise<WarrantyCardRow> {
  return apiPostObject<WarrantyCardRow>(
    `${BASE}${id}/shorten/`, { end_date: endDate, reason }, tenantOpts(),
  );
}

/** «هل هذه الوحدة تحت الكفالة؟» — من البطاقة ومن نسب الوحدة معاً. */
export function checkWarrantyBySerial(serial: string): Promise<WarrantyCoverage> {
  return apiGetObject<WarrantyCoverage>(
    `${BASE}check/?serial=${encodeURIComponent(serial)}`,
    tenantOpts(),
  );
}

/** #237: رابط التحقق ورمز QR (SVG من الخادم) للبطاقة. */
export interface WarrantyCardQr {
  verify_url: string;
  svg: string;
}

export function getWarrantyCardQr(id: number): Promise<WarrantyCardQr> {
  return apiGetObject<WarrantyCardQr>(`${BASE}${id}/qr/`, tenantOpts());
}

/** سجل أحداث البطاقة (#229) — إلحاقيّ، للقراءة فقط. */
export interface WarrantyCardEventRow {
  id: number;
  event_type: string;
  event_type_label: string;
  reason_code: string;
  text: string;
  service_order: number | null;
  service_order_number: string | null;
  actor: number | null;
  actor_name: string;
  old_end_date: string | null;
  new_end_date: string | null;
  quantity: number | null;
  created_at: string;
}

export function getWarrantyCardEvents(id: number): Promise<WarrantyCardEventRow[]> {
  return apiGetObject<WarrantyCardEventRow[]>(`${BASE}${id}/events/`, tenantOpts());
}

/* ══════════════════════════════════════════════════════════════════════════
 * جهات كفالة المصنع وإعدادات الوحدة (#230)
 *
 * إدارة الجهات الكاملة (`manufacturer-warrantors/`) خلف `aftersales.settings.manage`؛
 * `lookup/` أوسع (تقرأها `purchase.invoice.edit` أيضاً) وتقتصر على المفعَّلة —
 * تغذّي منتقي كفالة المصنع على بند الشراء لاحقاً (#235). و`settings/` صفٌّ
 * واحد لكل شركة: `GET` لكل من يملك الوحدة، و`PATCH` خلف صلاحية الإدارة وحدها.
 * ══════════════════════════════════════════════════════════════════════════ */

const WARRANTORS = "after-sales/manufacturer-warrantors/";
const AFTER_SALES_SETTINGS = "after-sales/settings/";

export interface ManufacturerWarrantorRow {
  id: number;
  name: string;
  service_center_address: string;
  phone: string;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ManufacturerWarrantorDraft {
  name: string;
  service_center_address: string;
  phone: string;
  notes: string;
  is_active: boolean;
}

export function listManufacturerWarrantors(): Promise<ManufacturerWarrantorRow[]> {
  return apiGetList<ManufacturerWarrantorRow>(WARRANTORS, tenantOpts());
}

/** الجهات المفعَّلة وحدها — لمنتقي كفالة المصنع لا لشاشة الإدارة. */
export function lookupManufacturerWarrantors(): Promise<ManufacturerWarrantorRow[]> {
  return apiGetList<ManufacturerWarrantorRow>(`${WARRANTORS}lookup/`, tenantOpts());
}

export function createManufacturerWarrantor(
  draft: ManufacturerWarrantorDraft,
): Promise<ManufacturerWarrantorRow> {
  return apiPostObject<ManufacturerWarrantorRow>(WARRANTORS, draft, tenantOpts());
}

export function updateManufacturerWarrantor(
  id: number,
  patch: Partial<ManufacturerWarrantorDraft>,
): Promise<ManufacturerWarrantorRow> {
  return apiPatchObject<ManufacturerWarrantorRow>(`${WARRANTORS}${id}/`, patch, tenantOpts());
}

/** حذفٌ نهائي — يُرفض بـ400 مقروءاً إن كانت الجهة مرتبطة بسجلات أخرى. */
export function deleteManufacturerWarrantor(id: number): Promise<void> {
  return apiDelete(`${WARRANTORS}${id}/`, tenantOpts());
}

export interface AfterSalesSettingsRow {
  default_terms: string;
  extend_for_shop_days: boolean;
  repair_warranty_days: number;
  repair_terms: string;
  updated_at: string;
}

export type AfterSalesSettingsDraft = Omit<AfterSalesSettingsRow, "updated_at">;

export function getAfterSalesSettings(): Promise<AfterSalesSettingsRow> {
  return apiGetObject<AfterSalesSettingsRow>(AFTER_SALES_SETTINGS, tenantOpts());
}

export function updateAfterSalesSettings(
  patch: Partial<AfterSalesSettingsDraft>,
): Promise<AfterSalesSettingsRow> {
  return apiPatchObject<AfterSalesSettingsRow>(AFTER_SALES_SETTINGS, patch, tenantOpts());
}

/* ══════════════════════════════════════════════════════════════════════════
 * سياسات الكفالة (#231) — صفٌّ واحد لكل براند (`inventory.Product`)
 *
 * لا سياسة = لا بطاقة تلقائية عند البيع. القراءة خلف `aftersales.warranty.view`،
 * والكتابة والتطبيق الجماعي خلف `aftersales.settings.manage` كبقية إعدادات
 * الوحدة. `bulk/` يطبّق سياسةً واحدة على كل براندات منتجٍ أبٍ أو تصنيف —
 * كلٌّ أو لا شيء عند فشل أيّ براند (#231 قرارٌ متعمَّد: لا كتابة جزئية).
 * ══════════════════════════════════════════════════════════════════════════ */

const WARRANTY_POLICIES = "after-sales/warranty-policies/";

export type WarrantyPolicyMethod = "serial" | "invoice";

export interface WarrantyPolicyRow {
  id: number;
  product: number;
  product_name: string;
  method: WarrantyPolicyMethod;
  method_label: string;
  dealer_months: number;
  manufacturer_warrantor: number | null;
  manufacturer_warrantor_name: string;
  manufacturer_months: number;
  supplier_months: number;
  terms_override: string;
  /** آخر شراء مرحَّل لهذا المنتج بكفالةٍ على سطره (#235) — للتلميح فقط. */
  last_purchase?: WarrantyPolicyLastPurchase | null;
  created_at: string;
  updated_at: string;
}

export interface WarrantyPolicyLastPurchase {
  manufacturer_warrantor: number | null;
  manufacturer_warrantor_name: string;
  manufacturer_months: number;
  supplier_months: number | null;
  invoice_date: string | null;
  invoice_number: string;
}

export interface WarrantyPolicyDraft {
  product: number;
  method: WarrantyPolicyMethod;
  dealer_months: number;
  manufacturer_warrantor: number | null;
  manufacturer_months: number;
  supplier_months: number;
  terms_override: string;
}

export interface WarrantyPolicyBulkInput {
  family?: number;
  category?: number;
  method: WarrantyPolicyMethod;
  dealer_months: number;
  manufacturer_warrantor?: number | null;
  manufacturer_months?: number;
  supplier_months?: number;
  terms_override?: string;
}

export interface WarrantyPolicyBulkResult {
  applied: number;
  policies: WarrantyPolicyRow[];
}

export function listWarrantyPolicies(
  filters: { product?: number; family?: number; category?: number } = {},
): Promise<WarrantyPolicyRow[]> {
  return apiGetList<WarrantyPolicyRow>(WARRANTY_POLICIES, {
    ...tenantOpts(),
    query: {
      product: filters.product || undefined,
      family: filters.family || undefined,
      category: filters.category || undefined,
    },
  });
}

/** #235: ما يحتاجه محرّر فاتورة الشراء من سياسة المنتج — يقرؤه `purchase.invoice.edit`. */
export interface PurchaseLinePolicyRow {
  id: number;
  product: number;
  method: WarrantyPolicyRow["method"];
  manufacturer_warrantor: number | null;
  manufacturer_months: number;
  supplier_months: number;
}

/** سياسات منتجات فاتورة الشراء بنداءٍ واحد (`warranty-policies/for-products/`). */
export function listPurchaseLinePolicies(productIds: number[]): Promise<PurchaseLinePolicyRow[]> {
  return apiGetList<PurchaseLinePolicyRow>(`${WARRANTY_POLICIES}for-products/`, {
    ...tenantOpts(),
    query: { products: productIds.join(",") },
  });
}

export function createWarrantyPolicy(draft: WarrantyPolicyDraft): Promise<WarrantyPolicyRow> {
  return apiPostObject<WarrantyPolicyRow>(WARRANTY_POLICIES, draft, tenantOpts());
}

export function updateWarrantyPolicy(
  id: number,
  patch: Partial<WarrantyPolicyDraft>,
): Promise<WarrantyPolicyRow> {
  return apiPatchObject<WarrantyPolicyRow>(`${WARRANTY_POLICIES}${id}/`, patch, tenantOpts());
}

export function deleteWarrantyPolicy(id: number): Promise<void> {
  return apiDelete(`${WARRANTY_POLICIES}${id}/`, tenantOpts());
}

export function bulkApplyWarrantyPolicy(
  input: WarrantyPolicyBulkInput,
): Promise<WarrantyPolicyBulkResult> {
  return apiPostObject<WarrantyPolicyBulkResult>(`${WARRANTY_POLICIES}bulk/`, input, tenantOpts());
}

/* ══════════════════════════════════════════════════════════════════════════
 * كفالة المصنع على سطر الشراء (#235)
 *
 * فاتورةٌ في المسودة تحمل الكفالة مع بنودها (`extensions.manufacturer_warranty`
 * في حمولة الفاتورة). المرحَّلة تُصحَّح بدفعةٍ واحدة هنا خلف
 * `aftersales.warranty.manage` — ولا تمسّ بطاقةً صدرت.
 * ══════════════════════════════════════════════════════════════════════════ */

const PURCHASE_LINE_WARRANTIES = "after-sales/purchase-line-warranties/";

export interface PurchaseLineWarrantyPayload {
  manufacturer_warrantor: number | null;
  manufacturer_months: number;
  supplier_months: number | null;
}

export interface PurchaseLineWarrantyPatchLine extends PurchaseLineWarrantyPayload {
  item: number;
}

export function savePurchaseLineWarranties(
  invoice: number,
  lines: PurchaseLineWarrantyPatchLine[],
): Promise<{ invoice: number; updated: number }> {
  return apiPatchObject<{ invoice: number; updated: number }>(
    PURCHASE_LINE_WARRANTIES,
    { invoice, lines },
    tenantOpts(),
  );
}

/** معاينة قبل حفظ سياسة `serial` (#233) — البراندات الشقيقة غير المتتبَّعة
 *  التي سترتفع معها، وعدد الوحدات غير المرقَّمة الآن لكل منتج. */
export interface WarrantySerialImpactSibling {
  id: number;
  name: string;
}

export interface WarrantySerialImpact {
  sibling_brands: WarrantySerialImpactSibling[];
  unnumbered_units: Record<number, number>;
}

export function getWarrantySerialImpact(
  selector: { product?: number } | { family?: number } | { category?: number },
): Promise<WarrantySerialImpact> {
  return apiGetObject<WarrantySerialImpact>(`${WARRANTY_POLICIES}serial-impact/`, {
    ...tenantOpts(),
    query: { ...selector },
  });
}

/* ══════════════════════════════════════════════════════════════════════════
 * أوامر الصيانة (م3/م4)
 *
 * الحالة والنتيجة والمراسي المالية (`covered_posted_at`, `sales_invoice`) كلها
 * **للقراءة فقط**: الحالة تنتقل بنقطة `transition/` المحروسة وحدها، فبواباتها
 * (لا تسليم وقطعٌ مغطاة غير مرحّلة، ولا إلغاء وفي الأمر ترحيلٌ قائم) لا تُتخطّى
 * بـPATCH. والخادم يردّ `delivery_blockers`/`cancellation_blockers` محسوبَين
 * فتعرضهما الشاشة كما هي بدل أن تعيد استنتاجهما وتخالفه.
 * ══════════════════════════════════════════════════════════════════════════ */

const ORDERS = "after-sales/service-orders/";

export type ServiceOrderStatus =
  | "received" | "in_diagnosis" | "awaiting_approval"
  | "in_repair" | "ready" | "delivered" | "cancelled";

export type ServiceOrderOutcome =
  | "repaired" | "unrepaired" | "rejected_estimate" | "no_fault" | "";

export type PartBilling = "billable" | "covered";

export interface ServiceOrderPartRow {
  id: number;
  product: number | null;
  product_name: string;
  quantity: string;
  billing: PartBilling;
  billing_label: string;
  unit_price: string;
  /** أرقام تسلسلية مختارة لقطعةٍ مغطاة مرقّمة — تُستهلَك عند ترحيل صرفها. */
  serials: string[];
  /** كلفة FIFO الفعلية لحركة الصرف — تُملأ بعد الترحيل، للقراءة فقط. */
  issued_cost: string | null;
  notes: string;
  sales_invoice_line: number | null;
  materialized_at: string | null;
  is_materialized: boolean;
  created_at: string;
}

export interface ServiceOrderEventRow {
  id: number;
  event_type: string;
  event_type_label: string;
  from_status: string;
  to_status: string;
  text: string;
  actor: number | null;
  actor_name: string;
  created_at: string;
}

/** صفّ القائمة — خفيف بلا بنود ولا أحداث. */
export interface ServiceOrderListRow {
  id: number;
  order_number: string;
  order_date: string;
  partner: number | null;
  partner_name: string;
  customer_name: string;
  customer_phone: string;
  product: number | null;
  product_name: string;
  serial: string;
  device_description: string;
  complaint: string;
  status: ServiceOrderStatus;
  status_label: string;
  outcome: ServiceOrderOutcome;
  outcome_label: string;
  warranty_covered: boolean;
  estimated_amount: string | null;
  covered_posted_at: string | null;
  sales_invoice: number | null;
  delivered_at: string | null;
  created_at: string;
}

export interface ServiceOrderDetail extends ServiceOrderListRow {
  received_condition: string;
  accessories: string;
  diagnosis: string;
  resolution: string;
  technician: number | null;
  technician_name: string;
  warranty_card: number | null;
  warranty_status: {
    id: number;
    end_date: string;
    status: WarrantyStatus;
    days_remaining: number;
    supplier_warranty_end_date: string | null;
    supplier_warranty_active: boolean;
    coverage_refused: boolean;
  } | null;
  supplier_claim: boolean;
  supplier_claim_note: string;
  approved_at: string | null;
  approved_by: number | null;
  sales_invoice_number: string | null;
  billing_waived_reason: string;
  photos: unknown[];
  notes: string;
  parts: ServiceOrderPartRow[];
  events: ServiceOrderEventRow[];
  /** أسباب المنع كما يحسبها الخادم — تُعرض لا تُستنتج. */
  delivery_blockers: string[];
  cancellation_blockers: string[];
  updated_at: string;
}

/** حقول الاستقبال والتحرير — ما يقبله الخادم بـPOST/PATCH لا أكثر. */
export interface ServiceOrderDraft {
  order_date: string;
  partner: number | null;
  customer_name: string;
  customer_phone: string;
  product: number | null;
  serial: string;
  device_description: string;
  received_condition: string;
  accessories: string;
  complaint: string;
  diagnosis: string;
  resolution: string;
  warranty_card: number | null;
  warranty_covered: boolean;
  supplier_claim: boolean;
  supplier_claim_note: string;
  estimated_amount: string | null;
  billing_waived_reason: string;
  notes: string;
}

export interface ServiceOrderListFilters {
  q?: string;
  status?: ServiceOrderStatus | "";
  open?: boolean;
  partner?: number | "";
  date_from?: string;
  date_to?: string;
}

/** ما يعرفه النظام عن معرّف واحد — ثلاثة مصادر بلا مفتاح أجنبي بينها. */
export interface IntakeSensitiveDevice {
  id: number;
  model_name: string;
  serial_number: string;
  imei: string;
  status: string;
  status_display: string;
  customer_name: string;
  customer_phone: string;
  registered_at: string;
}

export interface IntakeLookup {
  term: string;
  warranty: WarrantyCoverage;
  sensitive_devices: IntakeSensitiveDevice[];
  open_orders: {
    id: number;
    order_number: string;
    order_date: string;
    status: ServiceOrderStatus;
    status_display: string;
    complaint: string;
  }[];
}

export function listServiceOrders(
  filters: ServiceOrderListFilters = {},
  page = 1,
  pageSize = 25,
): Promise<PagedList<ServiceOrderListRow>> {
  return apiGetPagedList<ServiceOrderListRow>(ORDERS, {
    ...tenantOpts(),
    query: {
      page,
      page_size: pageSize,
      q: filters.q?.trim() || undefined,
      status: filters.status || undefined,
      open: filters.open ? 1 : undefined,
      partner: filters.partner || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
    },
  });
}

export function getServiceOrder(id: number): Promise<ServiceOrderDetail> {
  return apiGetObject<ServiceOrderDetail>(`${ORDERS}${id}/`, tenantOpts());
}

export function createServiceOrder(
  draft: Partial<ServiceOrderDraft>,
): Promise<ServiceOrderDetail> {
  return apiPostObject<ServiceOrderDetail>(ORDERS, draft, tenantOpts());
}

export function updateServiceOrder(
  id: number,
  patch: Partial<ServiceOrderDraft>,
): Promise<ServiceOrderDetail> {
  return apiPatchObject<ServiceOrderDetail>(`${ORDERS}${id}/`, patch, tenantOpts());
}

/** البوابة الوحيدة لتغيير الحالة — النتيجة إلزامية عند التسليم. */
export function transitionServiceOrder(
  id: number,
  body: { to_status: ServiceOrderStatus; outcome?: ServiceOrderOutcome; note?: string },
): Promise<ServiceOrderDetail> {
  return apiPostObject<ServiceOrderDetail>(`${ORDERS}${id}/transition/`, body, tenantOpts());
}

export function addServiceOrderNote(
  id: number,
  text: string,
): Promise<ServiceOrderEventRow> {
  return apiPostObject<ServiceOrderEventRow>(`${ORDERS}${id}/note/`, { text }, tenantOpts());
}

export function approveServiceOrder(id: number, note = ""): Promise<ServiceOrderDetail> {
  return apiPostObject<ServiceOrderDetail>(`${ORDERS}${id}/approve/`, { note }, tenantOpts());
}

export function addServiceOrderPart(
  id: number,
  part: {
    product: number; quantity: string; billing: PartBilling; unit_price?: string;
    serials?: string[]; notes?: string;
  },
): Promise<ServiceOrderPartRow> {
  return apiPostObject<ServiceOrderPartRow>(`${ORDERS}${id}/parts/`, part, tenantOpts());
}

export function updateServiceOrderPart(
  id: number,
  partId: number,
  patch: Partial<{
    quantity: string; billing: PartBilling; unit_price: string; serials: string[]; notes: string;
  }>,
): Promise<ServiceOrderPartRow> {
  return apiPatchObject<ServiceOrderPartRow>(
    `${ORDERS}${id}/parts/${partId}/`, patch, tenantOpts(),
  );
}

export function deleteServiceOrderPart(id: number, partId: number): Promise<void> {
  return apiDelete(`${ORDERS}${id}/parts/${partId}/`, tenantOpts());
}

/** الردّ يحمل الأمر بعد الترحيل — تُستهلك نسخته بدل قراءةٍ ثانية. */
interface OrderEnvelope { order: ServiceOrderDetail }

export async function postCoveredParts(id: number): Promise<ServiceOrderDetail> {
  const res = await apiPostObject<OrderEnvelope>(
    `${ORDERS}${id}/post-covered/`, {}, tenantOpts(),
  );
  return res.order;
}

export async function unpostCoveredParts(id: number): Promise<ServiceOrderDetail> {
  const res = await apiPostObject<OrderEnvelope>(
    `${ORDERS}${id}/unpost-covered/`, {}, tenantOpts(),
  );
  return res.order;
}

/** «رفض الكفالة لهذا العطل» (#236): البطاقة تبقى سارية والأمر وحده يفقد التغطية. */
export function refuseServiceOrderCoverage(
  id: number,
  input: Omit<WarrantyVoidInput, "service_order">,
): Promise<ServiceOrderDetail> {
  return apiPostObject<ServiceOrderDetail>(`${ORDERS}${id}/refuse-coverage/`, input, tenantOpts());
}

export function restoreServiceOrderCoverage(id: number, reason: string): Promise<ServiceOrderDetail> {
  return apiPostObject<ServiceOrderDetail>(
    `${ORDERS}${id}/restore-coverage/`, { reason }, tenantOpts(),
  );
}

export interface GeneratedServiceInvoice {
  invoice: { id: number; invoice_number: string; status: string; grand_total: string };
  order: ServiceOrderDetail;
}

/** تُنشئ فاتورة **مسودة** — الترحيل يبقى في شاشة الفواتير القائمة. */
export function generateServiceInvoice(
  id: number,
  labourAmount?: string,
): Promise<GeneratedServiceInvoice> {
  return apiPostObject<GeneratedServiceInvoice>(
    `${ORDERS}${id}/generate-invoice/`,
    labourAmount ? { labour_amount: labourAmount } : {},
    tenantOpts(),
  );
}

export async function detachServiceInvoice(id: number): Promise<ServiceOrderDetail> {
  const res = await apiPostObject<OrderEnvelope>(
    `${ORDERS}${id}/detach-invoice/`, {}, tenantOpts(),
  );
  return res.order;
}

/** بحث الاستقبال بمعرّف واحد (تسلسلي/IMEI) في ثلاثة مصادر. */
export function lookupIntake(serial: string): Promise<IntakeLookup> {
  return apiGetObject<IntakeLookup>(
    `${ORDERS}lookup/?serial=${encodeURIComponent(serial)}`,
    tenantOpts(),
  );
}
