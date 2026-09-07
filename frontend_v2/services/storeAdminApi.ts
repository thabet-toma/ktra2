/**
 * ST-3 — نداءات شاشة «إدارة المتجر»، وكلها مصادَق عليها بصلاحية `store.manage`.
 */
import { resolveTenantId } from "../utils/tenantContext";
import {
  apiDelete,
  apiGetObject,
  apiGetPagedList,
  apiPatchObject,
  apiPostObject,
  type PagedList,
} from "./restApi";

/** الشركة النشطة تُرسَل صراحةً مع كل نداء — العزل قانون المشروع لا افتراضاً. */
const tenantOpts = () => ({ tenantId: resolveTenantId() });

export interface StoreSlugResult {
  TenantID: number;
  store_slug: string | null;
}

/** يفتح المتجر بمعرّف، أو يقفله بقيمة فارغة. */
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

/** حالة توفّر منتج المتجر — إعلانٌ من التاجر لا رقمٌ مشتقّ من رصيد. */
export type StoreStockState = "in_stock" | "out_of_stock" | "preorder";

/** ما تعرضه الشاشة عن كل منتج — يطابق `StoreProduct` (THA-166 م٣). */
export interface StoreAdminProduct {
  id: number;
  name_ar: string | null;
  name_en: string | null;
  slug: string;
  brand: number | null;
  categories: number[];
  unit: string;
  price: string | null;
  /** مبلغٌ مطلقٌ لا نسبة — السعر بعد الخصم نفسه. */
  sale_price: string | null;
  stock_state: StoreStockState;
  description: string | null;
  is_active: boolean;
  sort_order: number;
  images: string[];
  imported_from_product_id: number | null;
  created_at?: string;
}

/** حجم صفحة الجدول. */
export const STORE_ADMIN_PAGE_SIZE = 25;

/** تبويب الجدول: الكل، أو المنشور وحده، أو غير المنشور وحده. */
export type StoreAdminScope = "all" | "published" | "unpublished";

export interface StoreAdminQuery {
  scope?: StoreAdminScope;
  search?: string;
  page?: number;
}

/** منتجات الشركة للجدول. */
export function getStoreAdminProducts(
  query: StoreAdminQuery = {},
): Promise<PagedList<StoreAdminProduct>> {
  return apiGetPagedList<StoreAdminProduct>("store/admin/products/", {
    ...tenantOpts(),
    query: {
      page: query.page ?? 1,
      page_size: STORE_ADMIN_PAGE_SIZE,
      scope: query.scope ?? "all",
      search: query.search?.trim() || undefined,
    },
  });
}

/** المنشور حالياً: أول صفحة + العدّ الكلي من الترقيم. */
export function getPublishedProducts(): Promise<PagedList<StoreAdminProduct>> {
  return getStoreAdminProducts({ scope: "published", page: 1 });
}

export interface StoreProductPayload {
  name_ar: string;
  name_en?: string;
  brand?: number | null;
  categories?: number[];
  unit?: string;
  price?: string | null;
  sale_price?: string | null;
  stock_state?: StoreStockState;
  description?: string;
  is_active?: boolean;
  sort_order?: number;
  initial_images?: string[];
}

/** إضافة منتج جديد للمتجر الإلكتروني مباشرة. */
export function createStoreProduct(
  payload: StoreProductPayload,
): Promise<StoreAdminProduct> {
  return apiPostObject<StoreAdminProduct>(
    "store/admin/products/",
    payload,
    tenantOpts(),
  );
}

/** تعديل منتج قائم — أيّ حقلٍ من حقول `StoreProduct` (لا حصر بعد م٢). */
export function updateStoreProduct(
  productId: number,
  patch: Partial<StoreProductPayload>,
): Promise<StoreAdminProduct> {
  return apiPatchObject<StoreAdminProduct>(
    `store/admin/products/${productId}/`,
    patch,
    tenantOpts(),
  );
}

/** حذف منتج من المتجر. */
export function deleteStoreProduct(productId: number): Promise<void> {
  return apiDelete(`store/admin/products/${productId}/`, tenantOpts());
}

/** نتيجة «استيراد من الأصناف» — الجسر الوحيد المسموح بين المخزون والمتجر. */
export interface ImportFromInventoryResult {
  imported_count: number;
  skipped_count: number;
  imported_ids: number[];
  message: string;
}

/** ينسخ أصنافاً مخزنيّةً مرّةً واحدةً إلى كتالوج المتجر المستقلّ — بلا علاقةٍ
 * ولا مزامنة لاحقة، ويتخطّى ما استُورد من قبل. */
export function importStoreProductsFromInventory(
  productIds: number[],
): Promise<ImportFromInventoryResult> {
  return apiPostObject<ImportFromInventoryResult>(
    "store/admin/products/import-from-inventory/",
    { product_ids: productIds },
    tenantOpts(),
  );
}

/** اسم المنتج المعروض في الجدول. */
export function storeAdminProductName(product: StoreAdminProduct): string {
  return (product.name_ar || product.name_en || "").trim() || `منتج ${product.id}`;
}

// ── الماركات (Store Brands) ────────────────────────────────────────────

export interface StoreAdminBrand {
  id: number;
  name: string;
  sort_order: number;
  is_active: boolean;
  created_at?: string;
}

export function getStoreAdminBrands(): Promise<StoreAdminBrand[]> {
  return apiGetPagedList<StoreAdminBrand>("store/admin/brands/", {
    ...tenantOpts(),
    query: { page_size: 500 },
  }).then((paged) => paged.results);
}

export function createStoreAdminBrand(
  payload: Pick<StoreAdminBrand, "name"> & Partial<Pick<StoreAdminBrand, "sort_order" | "is_active">>,
): Promise<StoreAdminBrand> {
  return apiPostObject<StoreAdminBrand>("store/admin/brands/", payload, tenantOpts());
}

export function updateStoreAdminBrand(
  id: number,
  patch: Partial<StoreAdminBrand>,
): Promise<StoreAdminBrand> {
  return apiPatchObject<StoreAdminBrand>(`store/admin/brands/${id}/`, patch, tenantOpts());
}

export function deleteStoreAdminBrand(id: number): Promise<void> {
  return apiDelete(`store/admin/brands/${id}/`, tenantOpts());
}

// ── الفئات (Store Categories) ──────────────────────────────────────────

export interface StoreAdminCategory {
  id: number;
  name: string;
  parent: number | null;
  slug: string;
  sort_order: number;
  is_active: boolean;
  image_url: string;
  created_at?: string;
}

export function getStoreAdminCategories(): Promise<StoreAdminCategory[]> {
  return apiGetPagedList<StoreAdminCategory>("store/admin/categories/", {
    ...tenantOpts(),
    query: { page_size: 500 },
  }).then((paged) => paged.results);
}

export interface StoreCategoryPayload {
  name: string;
  parent?: number | null;
  sort_order?: number;
  is_active?: boolean;
  image_url?: string;
}

export function createStoreAdminCategory(
  payload: StoreCategoryPayload,
): Promise<StoreAdminCategory> {
  return apiPostObject<StoreAdminCategory>("store/admin/categories/", payload, tenantOpts());
}

export function updateStoreAdminCategory(
  id: number,
  patch: Partial<StoreCategoryPayload>,
): Promise<StoreAdminCategory> {
  return apiPatchObject<StoreAdminCategory>(`store/admin/categories/${id}/`, patch, tenantOpts());
}

export function deleteStoreAdminCategory(id: number): Promise<void> {
  return apiDelete(`store/admin/categories/${id}/`, tenantOpts());
}

// ── إعدادات المظهر والهوية (Store Theme Settings) ─────────────────────────

export interface StoreThemeSettings {
  id?: number;
  hero_title: string;
  hero_subtitle: string;
  announcement_bar: string;
  show_announcement: boolean;
  theme_preset: string;
  primary_color: string;
  accent_color: string;
  background_color: string;
  background_image_url: string | null;
  background_style: "cover" | "repeat_pattern" | "soft_blur" | string;
  banner_image_url: string | null;
  instagram_url: string | null;
  tiktok_url: string | null;
  facebook_url: string | null;
  snapchat_url: string | null;
  whatsapp_number: string | null;
  catalog_mode_default: "grid" | "slideshow" | "compact" | string;
  allow_cart: boolean;
}

export function getStoreThemeSettings(): Promise<StoreThemeSettings> {
  return apiGetObject<StoreThemeSettings>("store/admin/settings/", tenantOpts());
}

export function updateStoreThemeSettings(
  patch: Partial<StoreThemeSettings>,
): Promise<StoreThemeSettings> {
  return apiPatchObject<StoreThemeSettings>("store/admin/settings/", patch, tenantOpts());
}

// ── صور المتجر المخصصة للمنتج (Store Product Images) ─────────────────────

export interface StoreProductImageAdmin {
  id: number;
  store_product: number;
  image_url: string;
  sort_order: number;
  is_cover: boolean;
  caption: string;
  overlay_text?: string;
  overlay_style?: string;
  overlay_color?: string;
  created_at?: string;
}

export function getStoreProductImages(storeProductId: number): Promise<StoreProductImageAdmin[]> {
  return apiGetObject<StoreProductImageAdmin[]>("store/admin/product-images/", {
    ...tenantOpts(),
    query: { store_product_id: storeProductId },
  });
}

export function createStoreProductImage(payload: {
  store_product: number;
  image_url: string;
  sort_order?: number;
  is_cover?: boolean;
  caption?: string;
  overlay_text?: string;
  overlay_style?: string;
  overlay_color?: string;
}): Promise<StoreProductImageAdmin> {
  return apiPostObject<StoreProductImageAdmin>(
    "store/admin/product-images/",
    payload,
    tenantOpts(),
  );
}

export function updateStoreProductImage(
  id: number,
  patch: Partial<StoreProductImageAdmin>,
): Promise<StoreProductImageAdmin> {
  return apiPatchObject<StoreProductImageAdmin>(
    `store/admin/product-images/${id}/`,
    patch,
    tenantOpts(),
  );
}

export function deleteStoreProductImage(id: number): Promise<void> {
  return apiDelete(`store/admin/product-images/${id}/`, tenantOpts());
}

// ── المجموعات والحملات الإعلانية (Store Collections) ─────────────────────

export interface StoreCollectionAdmin {
  id: number;
  title: string;
  slug: string;
  description: string;
  banner_image_url: string | null;
  badge_text: string;
  featured_product: number | null;
  is_active: boolean;
  sort_order: number;
  items_count?: number;
  discount_percent?: string;
  starts_at?: string | null;
  ends_at?: string | null;
  /** يحسم التعادل بين حملتين بنفس نسبة الخصم — الأعلى يفوز. تحت `store.manage` (ليست مالاً). */
  priority?: number;
  /** مواصفة #166 م٥ — القياس: مشاهداتُ صفحة الحملة، وطلباتها، ونسبة التحويل. */
  views_count?: number;
  orders_count?: number;
  conversion_rate?: number | null;
  created_at?: string;
}

export interface StoreCollectionItemAdmin {
  id: number;
  collection: number;
  product: number;
  product_name: string;
  sku: string;
  price: string | null;
  image_url: string | null;
  sort_order: number;
}

export function getStoreCollectionsAdmin(): Promise<StoreCollectionAdmin[]> {
  return apiGetObject<StoreCollectionAdmin[]>("store/admin/collections/", tenantOpts());
}

export function createStoreCollectionAdmin(
  payload: Partial<StoreCollectionAdmin>,
): Promise<StoreCollectionAdmin> {
  return apiPostObject<StoreCollectionAdmin>("store/admin/collections/", payload, tenantOpts());
}

export function updateStoreCollectionAdmin(
  id: number,
  patch: Partial<StoreCollectionAdmin>,
): Promise<StoreCollectionAdmin> {
  return apiPatchObject<StoreCollectionAdmin>(
    `store/admin/collections/${id}/`,
    patch,
    tenantOpts(),
  );
}

export function deleteStoreCollectionAdmin(id: number): Promise<void> {
  return apiDelete(`store/admin/collections/${id}/`, tenantOpts());
}

export function getStoreCollectionItemsAdmin(
  collectionId: number,
): Promise<StoreCollectionItemAdmin[]> {
  return apiGetObject<StoreCollectionItemAdmin[]>("store/admin/collection-items/", {
    ...tenantOpts(),
    query: { collection_id: collectionId },
  });
}

export function addStoreCollectionItemAdmin(payload: {
  collection: number;
  product: number;
  sort_order?: number;
}): Promise<StoreCollectionItemAdmin> {
  return apiPostObject<StoreCollectionItemAdmin>(
    "store/admin/collection-items/",
    payload,
    tenantOpts(),
  );
}

export function deleteStoreCollectionItemAdmin(id: number): Promise<void> {
  return apiDelete(`store/admin/collection-items/${id}/`, tenantOpts());
}

