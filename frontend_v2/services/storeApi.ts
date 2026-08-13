/**
 * عميل المتجر العام — النقاط الوحيدة التي يُطلَبها زائرٌ بلا جلسة.
 *
 * الخادم `store/views.py`: بلا مصادقة إطلاقاً (`authentication_classes = []`)،
 * والشركة تأتي من الـslug في المسار لا من ترويسة، وكل «غير موجود» **404** — لا
 * فرق بين متجر مقفل وslug مجهول وصنف غير منشور، وهذا مقصود فلا يُستدل على وجود
 * شركة بتخمين المعرّفات. لذلك `isStoreNotFound` هي كل ما تحتاجه الشاشات.
 *
 * الترقيم **إلزامي** على القائمة (`EnforcedPageNumberPagination`) خلافاً
 * لافتراضي المشروع الاختياري: نقطة مجهولة بلا ترقيم تبثّ الكتالوج كاملاً بكل
 * طلب. فالرد دائماً `{count, next, previous, results}` ولا وجود لشاشة بلا زر
 * «عرض المزيد».
 */
import { apiGetObject, apiGetPagedList, type PagedList } from "./restApi";

/** بطاقة الشركة كما يراها زائر — مَن هي وكيف يتواصل معها، لا أكثر. */
export interface StoreProfile {
  slug: string;
  name: string;
  logo_url: string | null;
  phone: string | null;
  address: string | null;
  /** رمز العملة التي تُقرأ بها كل أسعار هذا المتجر — `null` إن لم تُضبَط. */
  currency: string | null;
}

/** حالة التوفّر نصّية دائماً — الرقم الخام لا يغادر الخادم بنيوياً. */
export type StoreAvailability = "available" | "limited" | "out";

/** الحمولة العامة كاملةً — عشرة حقول، وما ليس هنا لا يُرسله الخادم. */
export interface StoreProduct {
  id: number;
  name_ar: string | null;
  name_en: string | null;
  brand: string | null;
  category_name: string | null;
  uom_name: string | null;
  price: string | null;
  availability: StoreAvailability;
  description: string | null;
  images: string[];
}

export type StoreSort = "" | "price_asc" | "price_desc";

export interface StoreProductQuery {
  q?: string;
  brand?: string;
  category?: string;
  sort?: StoreSort;
  page?: number;
}

/** حجم الصفحة: يملأ شبكة أربعة أعمدة ست مرات، وتحته سقف الخادم (200). */
export const STORE_PAGE_SIZE = 24;

export const STORE_SORTS: { key: StoreSort; label: string }[] = [
  { key: "", label: "الترتيب: الاسم" },
  { key: "price_asc", label: "السعر: من الأقل" },
  { key: "price_desc", label: "السعر: من الأعلى" },
];

export const AVAILABILITY_LABEL: Record<StoreAvailability, string> = {
  available: "متوفر",
  limited: "كمية محدودة",
  out: "غير متوفر حالياً",
};

/** اسم الصنف المعروض: العربي أولاً — الواجهة والزبون عربيان. */
export function storeProductName(product: StoreProduct): string {
  return (product.name_ar || product.name_en || "").trim() || `صنف ${product.id}`;
}

const base = (slug: string) => `store/${encodeURIComponent(slug)}/`;

export function getStoreProfile(slug: string): Promise<StoreProfile> {
  return apiGetObject<StoreProfile>(base(slug));
}

export function getStoreProducts(
  slug: string,
  query: StoreProductQuery = {},
): Promise<PagedList<StoreProduct>> {
  return apiGetPagedList<StoreProduct>(`${base(slug)}products/`, {
    query: {
      page: query.page ?? 1,
      page_size: STORE_PAGE_SIZE,
      // القيم الفارغة تُحذف في `restApi` فقط إن كانت `undefined` — لا `""`،
      // وإلا صار مفتاح كاش الخادم مختلفاً لكل بحثٍ أُفرِغ ثم أُعيد.
      q: query.q?.trim() || undefined,
      brand: query.brand?.trim() || undefined,
      category: query.category?.trim() || undefined,
      sort: query.sort || undefined,
    },
  });
}

/** تفصيل صنف — هذا النداء وحده هو ما يزيد عدّاد المشاهدات اليومي. */
export function getStoreProduct(slug: string, productId: string | number): Promise<StoreProduct> {
  return apiGetObject<StoreProduct>(
    `${base(slug)}products/${encodeURIComponent(String(productId))}/`,
  );
}

/** 404 = لا متجر بهذا الاسم، أو صنف غير منشور — حالة عرضٍ لا خطأ يُشتكى منه. */
export function isStoreNotFound(error: unknown): boolean {
  return (error as { status?: number } | null)?.status === 404;
}
