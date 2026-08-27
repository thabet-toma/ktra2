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
  status: WarrantyStatus;
  days_remaining: number;
  created_at: string;
  updated_at: string;
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
}

/** الوحدة المُرقَّمة كما يعرفها المخزون — تظهر ولو لم تكن لها بطاقة. */
export interface WarrantyCoverageUnit {
  id: number;
  serial: string;
  status: string;
  status_display: string;
  product: number | null;
  product_name: string;
  warranty_months: number | null;
  supplier_warranty_months: number | null;
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

/** تمديد الكفالة مجاملةً — يُوثَّق في ملاحظات البطاقة بتاريخ الخادم. */
export function extendWarrantyCard(
  id: number,
  input: WarrantyExtendInput,
): Promise<WarrantyCardRow> {
  return apiPostObject<WarrantyCardRow>(`${BASE}${id}/extend/`, input, tenantOpts());
}

/** «هل هذه الوحدة تحت الكفالة؟» — من البطاقة ومن نسب الوحدة معاً. */
export function checkWarrantyBySerial(serial: string): Promise<WarrantyCoverage> {
  return apiGetObject<WarrantyCoverage>(
    `${BASE}check/?serial=${encodeURIComponent(serial)}`,
    tenantOpts(),
  );
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
  part: { product: number; quantity: string; billing: PartBilling; unit_price?: string; notes?: string },
): Promise<ServiceOrderPartRow> {
  return apiPostObject<ServiceOrderPartRow>(`${ORDERS}${id}/parts/`, part, tenantOpts());
}

export function updateServiceOrderPart(
  id: number,
  partId: number,
  patch: Partial<{ quantity: string; billing: PartBilling; unit_price: string; notes: string }>,
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
