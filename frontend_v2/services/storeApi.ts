/**
 * عميل المتجر العام — النقاط الوحيدة التي يُطلبها زائرٌ بلا جلسة.
 *
 * الخادم `store/views.py`: بلا مصادقة إطلاقاً (`authentication_classes = []`)،
 * والشركة تأتي من الـslug في المسار لا من ترويسة، وكل «غير موجود» **404**.
 */
import { apiGetObject, apiGetPagedList, apiPostObject, type PagedList } from "./restApi";

/** بطاقة الشركة وإعدادات المظهر والهوية كما يراها زائر. */
export interface StoreProfile {
  slug: string;
  name: string;
  logo_url: string | null;
  phone: string | null;
  address: string | null;
  /** رمز العملة التي تُقرأ بها كل أسعار هذا المتجر — `null` إن لم تُضبَط. */
  currency: string | null;
  // إعدادات المظهر والهوية
  hero_title?: string | null;
  hero_subtitle?: string | null;
  announcement_bar?: string | null;
  show_announcement?: boolean;
  theme_preset?: string;
  primary_color?: string;
  accent_color?: string;
  background_color?: string;
  background_image_url?: string | null;
  background_style?: "cover" | "repeat_pattern" | "soft_blur" | string;
  banner_image_url?: string | null;
  instagram_url?: string | null;
  tiktok_url?: string | null;
  facebook_url?: string | null;
  snapchat_url?: string | null;
  whatsapp_number?: string | null;
  catalog_mode_default?: "grid" | "slideshow" | "compact" | string;
  allow_cart?: boolean;
  /** `false` ⇒ المتجر كتالوج بلا أسعار: `price` يصل `null` من الخادم. */
  show_prices?: boolean;
}

/** حالة التوفّر نصّية دائماً: متوفر، كمية محدودة، غير متوفر، أو طلب مسبق. */
export type StoreAvailability = "available" | "limited" | "out" | "preorder";

export interface StoreImageOverlayData {
  text: string;
  style?: "diagonal_ribbon" | "bottom_banner" | "pill_badge" | "glass_tag" | string;
  color?: "red_fire" | "gold_luxury" | "emerald_fresh" | "blue_pro" | "neon_purple" | "dark_glass" | string;
}

/**
 * الحمولة العامة — العقد الأصليّ (أحد عشر حقلاً) + ستٌّ إضافيةٌ محضة منذ
 * THA-166 م٢ (`docs/modules/store.md`). الحقول الإضافية اختياريّة هنا: خادمٌ
 * أقدم لا يرسلها، فسقوطها لا يكسر شاشةً لا تقرؤها.
 */
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
  cover_overlay?: StoreImageOverlayData | null;
  slug?: string;
  /** السعر قبل الخصم — موجودٌ فقط حين يكون هناك خصمٌ فعليّ (منتجٍ مفردٍ أو حملة). */
  original_price?: string | null;
  /** نسبةٌ صحيحةٌ للشارة فقط — `null` بلا خصمٍ فعليّ. */
  discount_percent?: number | null;
  categories?: { id: number; name: string; slug: string }[];
  stock_state?: string;
  brand_id?: number | null;
}

export type StoreSort = "" | "price_asc" | "price_desc";

/** كتلُ الصفحة الرئيسية (THA-166 م٦) — سبعةُ حقولٍ ثابتة بصرف النظر عن
 * `kind`: `products`/`campaigns` فارغتان لما لا يخصّها النوع. */
export type StoreHomeBlockKind =
  | "hero"
  | "campaign_row"
  | "category_row"
  | "featured"
  | "most_viewed"
  | "active_campaigns";

export type StoreHomeLinkKind = "collection" | "category" | "product" | "url" | "none";

/** وجهةٌ مُصنَّفة — `target` سلاجُ الحملة/معرّف الفئة أو المنتج، و`url` للرابط الخارجي وحده. */
export interface StoreHomeLink {
  kind: StoreHomeLinkKind;
  target: string | number | null;
  url: string | null;
}

export interface StoreHomeBlock {
  id: number;
  kind: StoreHomeBlockKind;
  title: string;
  subtitle: string;
  image_url: string | null;
  image_url_mobile: string | null;
  link: StoreHomeLink;
  products: StoreProduct[];
  campaigns: StoreCollection[];
}

export interface StoreHomePayload {
  blocks: StoreHomeBlock[];
}

/** كتلُ الصفحة الرئيسية — `{blocks: []}` لمتجرٍ لم يضبط شيئاً (قاعدة السقوط). */
export function getStoreHome(slug: string): Promise<StoreHomePayload> {
  return apiGetObject<StoreHomePayload>(`${base(slug)}home/`);
}

export interface StoreProductQuery {
  q?: string;
  /** معرّفات ماركات مفصولة بفواصل (OR داخل المحور)، أو اسمٌ مفردٌ للتوافق الخلفي. */
  brand?: string;
  /** معرّفات فئات مفصولة بفواصل (OR داخل المحور)، أو اسمٌ مفردٌ للتوافق الخلفي. */
  category?: string;
  onSale?: boolean;
  isNew?: boolean;
  inStock?: boolean;
  minPrice?: string;
  maxPrice?: string;
  sort?: StoreSort;
  page?: number;
  /** يفرض عودة `facets`/`price_range` على صفحةٍ غير الأولى (THA-166 م٧). */
  includeFacets?: boolean;
}

/** عدّاد فئةٍ واحدة — شجريّ شاملٌ للأبناء (`docs/modules/store.md`). */
export interface StoreFacetCategory {
  id: number;
  name: string;
  parent_id: number | null;
  count: number;
}

export interface StoreFacetBrand {
  id: number;
  name: string;
  count: number;
}

export interface StoreFacetFlags {
  on_sale: number;
  is_new: number;
  in_stock: number;
}

/** محاورُ الفلترة السياقيّة — قد يتجاوز مجموع عدّادات محورٍ عددَ النتائج (قصدياً). */
export interface StoreFacets {
  categories: StoreFacetCategory[];
  brands: StoreFacetBrand[];
  flags: StoreFacetFlags;
}

/** مدى السعر السياقيّ — غائبٌ كلّياً حين تُحجَب الأسعار عن هذا المتجر. */
export interface StorePriceRange {
  min: string | null;
  max: string | null;
}

/** استجابة `/products/` الخام — `facets`/`price_range` فقط في الصفحة الأولى
 * (أو بـ`includeFacets`)؛ غائبان تماماً فيما عداها. */
export interface StoreProductListResult {
  results: StoreProduct[];
  count: number;
  hasNext: boolean;
  facets?: StoreFacets;
  price_range?: StorePriceRange;
}

function toStoreProductListResult(raw: unknown): StoreProductListResult {
  const payload = (raw || {}) as Record<string, unknown>;
  const results = Array.isArray(payload.results) ? (payload.results as StoreProduct[]) : [];
  return {
    results,
    count: Number(payload.count ?? results.length) || results.length,
    hasNext: payload.next != null,
    facets: payload.facets as StoreFacets | undefined,
    price_range: payload.price_range as StorePriceRange | undefined,
  };
}

/** المجموعة والحملة الإعلانية كما تظهر في القائمة العامة. */
export interface StoreCollection {
  id: number;
  title: string;
  slug: string;
  description: string | null;
  banner_image_url: string | null;
  badge_text: string | null;
  featured_product_id: number | null;
  items_count: number;
}

/** تفاصيل الحملة الإعلانية / صفحة الهبوط. */
export interface StoreCollectionDetail {
  id: number;
  title: string;
  slug: string;
  description: string | null;
  banner_image_url: string | null;
  badge_text: string | null;
  /** THA-166 م٧ — عدّادُ الانتهاء وحده؛ `starts_at` غيرُ منشورٍ عمداً. */
  ends_at: string | null;
  featured_product: StoreProduct | null;
}

/** رأسُ صفحة الفئة العامّ (THA-166 م٧) — اسمٌ وصورةٌ وأبٌ لمسار التنقّل. */
export interface StoreCategoryDetail {
  id: number;
  name: string;
  slug: string;
  image_url: string | null;
  parent: { id: number; name: string; slug: string } | null;
}

export function getStoreCategory(slug: string, categoryId: number | string): Promise<StoreCategoryDetail> {
  return apiGetObject<StoreCategoryDetail>(
    `${base(slug)}categories/${encodeURIComponent(String(categoryId))}/`,
  );
}

export interface StoreCampaignResponse {
  collection: StoreCollectionDetail;
  /** الخادم لا يبني `facets`/`price_range` لهذه النقطة — الحقلان غائبان دائماً. */
  products: StoreProductListResult;
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
  preorder: "طلب مسبق / عند الطلب",
};

/** اسم المنتج المعروض: العربي أولاً — الواجهة والزبون عربيان. */
export function storeProductName(product: StoreProduct): string {
  return (product.name_ar || product.name_en || "").trim() || `منتج ${product.id}`;
}

const base = (slug: string) => `store/${encodeURIComponent(slug)}/`;

export function getStoreProfile(slug: string): Promise<StoreProfile> {
  return apiGetObject<StoreProfile>(base(slug));
}

/** بناء معاملات `/products/` من `StoreProductQuery` — مشتركةٌ بين المتجر والحملة. */
function buildProductQueryParams(query: StoreProductQuery) {
  return {
    page: query.page ?? 1,
    page_size: STORE_PAGE_SIZE,
    q: query.q?.trim() || undefined,
    brand: query.brand?.trim() || undefined,
    category: query.category?.trim() || undefined,
    sort: query.sort || undefined,
    on_sale: query.onSale ? 1 : undefined,
    is_new: query.isNew ? 1 : undefined,
    in_stock: query.inStock ? 1 : undefined,
    min_price: query.minPrice?.trim() || undefined,
    max_price: query.maxPrice?.trim() || undefined,
    include_facets: query.includeFacets ? 1 : undefined,
  };
}

/** `GET /products/` بعدّاداتٍ سياقيّة (`facets`/`price_range` بالصفحة الأولى). */
export function getStoreProducts(
  slug: string,
  query: StoreProductQuery = {},
): Promise<StoreProductListResult> {
  return apiGetObject<unknown>(`${base(slug)}products/`, {
    query: buildProductQueryParams(query),
  }).then(toStoreProductListResult);
}

/** تفصيل منتج — هذا النداء وحده هو ما يزيد عدّاد المشاهدات اليومي. */
export function getStoreProduct(slug: string, productId: string | number): Promise<StoreProduct> {
  return apiGetObject<StoreProduct>(
    `${base(slug)}products/${encodeURIComponent(String(productId))}/`,
  );
}

/** عدد الحملات المجلوبة في نداءٍ واحد — الترويسة تعرض شريطاً لا كتالوجاً. */
export const STORE_COLLECTIONS_PAGE_SIZE = 50;

/** المجموعات والحملات الإعلانية الترويجية للمتجر — مُرقَّمة كقائمة المنتجات. */
export function getStoreCollections(
  slug: string,
  page = 1,
): Promise<PagedList<StoreCollection>> {
  return apiGetPagedList<StoreCollection>(`${base(slug)}collections/`, {
    query: { page, page_size: STORE_COLLECTIONS_PAGE_SIZE },
  });
}

/** صفحة الهبوط لحملة إعلانية / مجموعة. */
export function getStoreCollectionDetail(
  slug: string,
  collectionSlug: string,
  query: StoreProductQuery = {},
): Promise<StoreCampaignResponse> {
  return apiGetObject<{ collection: StoreCollectionDetail; products: unknown }>(
    `${base(slug)}collections/${encodeURIComponent(collectionSlug)}/`,
    { query: buildProductQueryParams(query) },
  ).then((raw) => ({
    collection: raw.collection,
    products: toStoreProductListResult(raw.products),
  }));
}

/** 404 = لا متجر بهذا الاسم، أو منتج غير منشور — حالة عرضٍ لا خطأ يُشتكى منه. */
export function isStoreNotFound(error: unknown): boolean {
  return (error as { status?: number } | null)?.status === 404;
}

/** بند نيّة الطلب المُرسَل — لا سعر هنا: الخادم يحسبه من `StoreProduct` وحده. */
export interface StoreOrderIntentItem {
  product_id: number;
  quantity: number;
}

/**
 * يسجّل نيّةَ طلبٍ على الخادم **قبل** فتح واتساب (مواصفة #166 م٥) — لقطةٌ
 * مساعدة لا مصدر حقيقة، فاستدعاؤها لا يُنتظر ولا يمنع فتح رابط الطلب أبداً.
 */
export function createStoreOrderIntent(
  slug: string,
  items: StoreOrderIntentItem[],
  collectionSlug?: string | null,
): Promise<{ ok: boolean }> {
  return apiPostObject<{ ok: boolean }>(`${base(slug)}order-intent/`, {
    items,
    collection_slug: collectionSlug || undefined,
  });
}

