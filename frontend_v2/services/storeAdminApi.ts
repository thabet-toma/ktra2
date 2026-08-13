/**
 * ST-3 — نداءات شاشة «متجري»، وكلها مصادَق عليها.
 *
 * منفصل عن `storeApi.ts` عمداً: ذاك عميل الزائر المجهول (بلا توكن ولا شركة
 * نشطة)، وهذا مصادَق عليه بصلاحية `store.manage`. خلطهما في ملف واحد كان
 * سيُفقد قارئَ الأمن الخاصيةَ الوحيدة التي تجعل الملف الآخر قابلاً للمراجعة
 * في نظرة: أن كل ما فيه عام.
 *
 * **ولا نقطة نشرٍ جديدة هنا ولا سيريالايزر ثانٍ**: `is_for_sale_online`
 * و`online_price` و`online_description` حقولٌ قائمة على `Product` تقبلها
 * `inventory/views.py` (`ProductViewSet`) بـPATCH منذ ما قبل المتجر — الشاشة
 * تستعملها كما هي.
 */
import { resolveTenantId } from "../utils/tenantContext";
import { apiGetPagedList, apiPatchObject, apiPostObject, type PagedList } from "./restApi";

/** الشركة النشطة تُرسَل صراحةً مع كل نداء — العزل قانون المشروع لا افتراضاً. */
const tenantOpts = () => ({ tenantId: resolveTenantId() });

export interface StoreSlugResult {
  TenantID: number;
  store_slug: string | null;
}

/**
 * يفتح المتجر بمعرّف، أو يقفله بقيمة فارغة — **القيمة نفسها هي مفتاح التفعيل**
 * (`NULL` = مقفل)، فلا نداء ثانٍ لـ«تشغيل/إيقاف».
 *
 * التحقّق من الشكل والكلمات المحجوزة على الخادم وحده؛ لا نكرّره هنا كي لا
 * تتباعد النسختان — الواجهة تعرض رسالته كما هي.
 */
export function setStoreSlug(
  companyId: number,
  slug: string,
): Promise<StoreSlugResult> {
  return apiPostObject<StoreSlugResult>(
    `tenants/companies/${companyId}/set-store-slug/`,
    { store_slug: slug },
    tenantOpts(),
  );
}

/** ما تعرضه الشاشة عن كل صنف — لا أكثر ممّا يُقرأ أو يُحرَّر في الجدول. */
export interface StoreAdminProduct {
  id: number;
  sku: string | null;
  name_ar: string | null;
  name_en: string | null;
  brand: string | null;
  category_name: string | null;
  is_for_sale_online: boolean;
  online_price: string | null;
  online_description: string | null;
  /** سعر البيع الافتراضي — هو ما يعرضه المتجر حين يُترك سعر المتجر فارغاً. */
  sale_price: string | null;
}

/** حجم صفحة الجدول — مُرقَّم كبقية جداول النظام، لا «حمّل كل شيء». */
export const STORE_ADMIN_PAGE_SIZE = 25;

/** تبويب الجدول: الكل، أو المنشور وحده، أو غير المنشور وحده. */
export type StoreAdminScope = "all" | "published" | "unpublished";

const SCOPE_PARAM: Record<StoreAdminScope, string | undefined> = {
  all: undefined,
  published: "true",
  unpublished: "false",
};

export interface StoreAdminQuery {
  scope?: StoreAdminScope;
  search?: string;
  page?: number;
}

/**
 * أصناف الشركة للجدول.
 *
 * `view=lookup` عمداً: العقد الكامل يحسب ثلاث تجميعات على جدول الحركات لكل
 * صفّ (مشتريات ومتوسط مبيعات 90 يوماً) لا تعرض هذه الشاشة منها شيئاً.
 */
export function getStoreAdminProducts(
  query: StoreAdminQuery = {},
): Promise<PagedList<StoreAdminProduct>> {
  return apiGetPagedList<StoreAdminProduct>("inventory/products/", {
    ...tenantOpts(),
    query: {
      view: "lookup",
      page: query.page ?? 1,
      page_size: STORE_ADMIN_PAGE_SIZE,
      is_for_sale_online: SCOPE_PARAM[query.scope ?? "all"],
      search: query.search?.trim() || undefined,
      ordering: "name_ar",
    },
  });
}

/**
 * المنشور حالياً: أول صفحة + العدّ الكلي من الترقيم.
 *
 * تستعمله **مراجعة أول تفعيل**: `is_for_sale_online` ليس حقلاً جديداً، وقد
 * تكون الشركة علّمته على أصناف لسببٍ تسعيري (`core/pricing.py` يقرؤه سعراً
 * افتراضياً في الفوترة). تلك الأصناف تصير علنيةً لحظةَ اختيار المعرّف، فيجب
 * أن تُعرَض على المدير **قبل** الفتح لا بعده.
 */
export function getPublishedProducts(): Promise<PagedList<StoreAdminProduct>> {
  return getStoreAdminProducts({ scope: "published", page: 1 });
}

/** تعديل نشر صنف أو سعره أو وصفه في المتجر — الحقول الثلاثة القائمة وحدها. */
export function updateProductPublishing(
  productId: number,
  patch: Partial<Pick<StoreAdminProduct,
    "is_for_sale_online" | "online_price" | "online_description">>,
): Promise<StoreAdminProduct> {
  return apiPatchObject<StoreAdminProduct>(
    `inventory/products/${productId}/`,
    patch,
    tenantOpts(),
  );
}

/** اسم الصنف المعروض في الجدول — العربي أولاً كما في بقية الشاشات. */
export function storeAdminProductName(product: StoreAdminProduct): string {
  return (product.name_ar || product.name_en || "").trim() || `صنف ${product.id}`;
}

// الرابط الذي يُنسَخ من هذه الشاشة يُبنى بـ`utils/storeLinks.ts` (`storeHomeUrl`)
// — نفس الدالة التي تبني روابط المتجر العام، فلا نسختان لنمط مسارٍ واحد.
