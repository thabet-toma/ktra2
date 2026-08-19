/**
 * عميل المتجر العام — النقاط الوحيدة التي يُطلبها زائرٌ بلا جلسة.
 *
 * الخادم `store/views.py`: بلا مصادقة إطلاقاً (`authentication_classes = []`)،
 * والشركة تأتي من الـslug في المسار لا من ترويسة، وكل «غير موجود» **404**.
 */
import { apiGetObject, apiGetPagedList, type PagedList } from "./restApi";

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
  cover_overlay?: StoreImageOverlayData | null;
}

export type StoreSort = "" | "price_asc" | "price_desc";

export interface StoreProductQuery {
  q?: string;
  brand?: string;
  category?: string;
  sort?: StoreSort;
  page?: number;
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
  featured_product: StoreProduct | null;
}

export interface StoreCampaignResponse {
  collection: StoreCollectionDetail;
  products: PagedList<StoreProduct>;
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
  return apiGetObject<StoreCampaignResponse>(
    `${base(slug)}collections/${encodeURIComponent(collectionSlug)}/`,
    {
      query: {
        page: query.page ?? 1,
        page_size: STORE_PAGE_SIZE,
        q: query.q?.trim() || undefined,
        brand: query.brand?.trim() || undefined,
        category: query.category?.trim() || undefined,
        sort: query.sort || undefined,
      },
    },
  );
}

/** 404 = لا متجر بهذا الاسم، أو صنف غير منشور — حالة عرضٍ لا خطأ يُشتكى منه. */
export function isStoreNotFound(error: unknown): boolean {
  return (error as { status?: number } | null)?.status === 404;
}

