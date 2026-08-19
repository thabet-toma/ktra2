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

/** ما تعرضه الشاشة عن كل صنف. */
export interface StoreAdminProduct {
  id: number;
  sku: string | null;
  name_ar: string | null;
  name_en: string | null;
  brand: string | null;
  category_name: string | null;
  is_for_sale_online: boolean;
  allow_preorder: boolean;
  online_price: string | null;
  online_description: string | null;
  /** سعر البيع الافتراضي — هو ما يعرضه المتجر حين يُترك سعر المتجر فارغاً. */
  sale_price: string | null;
}

/** حجم صفحة الجدول. */
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

/** أصناف الشركة للجدول. */
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

/** تعديل نشر صنف أو سعره أو وصفه أو الطلب المسبق. */
export function updateProductPublishing(
  productId: number,
  patch: Partial<Pick<StoreAdminProduct,
    "is_for_sale_online" | "allow_preorder" | "online_price" | "online_description">>,
): Promise<StoreAdminProduct> {
  return apiPatchObject<StoreAdminProduct>(
    `store/admin/products/${productId}/`,
    patch,
    tenantOpts(),
  );
}

export interface CreateStoreProductPayload {
  name_ar: string;
  name_en?: string;
  brand?: string;
  sku?: string;
  online_price?: string;
  online_description?: string;
  allow_preorder?: boolean;
  is_for_sale_online?: boolean;
  initial_images?: string[];
}

/** إضافة منتج جديد للمتجر الإلكتروني مباشرة. */
export function createStoreProduct(
  payload: CreateStoreProductPayload,
): Promise<StoreAdminProduct> {
  return apiPostObject<StoreAdminProduct>(
    "store/admin/products/",
    payload,
    tenantOpts(),
  );
}

/** حذف أو إلغاء نشر منتج من المتجر. */
export function deleteStoreProduct(productId: number): Promise<void> {
  return apiDelete(`store/admin/products/${productId}/`, tenantOpts());
}

/** اسم الصنف المعروض في الجدول. */
export function storeAdminProductName(product: StoreAdminProduct): string {
  return (product.name_ar || product.name_en || "").trim() || `صنف ${product.id}`;
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
  product: number;
  image_url: string;
  sort_order: number;
  is_cover: boolean;
  caption: string;
  overlay_text?: string;
  overlay_style?: string;
  overlay_color?: string;
  created_at?: string;
}

export function getStoreProductImages(productId: number): Promise<StoreProductImageAdmin[]> {
  return apiGetObject<StoreProductImageAdmin[]>("store/admin/product-images/", {
    ...tenantOpts(),
    query: { product_id: productId },
  });
}

export function createStoreProductImage(payload: {
  product: number;
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

