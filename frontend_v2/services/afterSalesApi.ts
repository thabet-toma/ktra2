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
 * تنمو بعدد المبيعات لا بعدد الأصناف — جلبها كاملة يثقل الشاشة بعد أشهر.
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
