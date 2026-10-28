import { Page } from '@playwright/test';

/**
 * محاكي واجهة شجرة المنتجات (`/items`) — نفسه لاختبارَي الشجرة
 * (`items-tree-card-pane` و`items-tree-context-menu`).
 *
 * كان كلُّ ملفٍّ ينسخ ~90 سطراً: صفوفُ المنتجات وبروفايلها ومسارٌ يعترض كلَّ
 * طلب API ويردّ شكلاً ثابتاً. نسختان تتفرّقان صامتتين: يُضاف حقلٌ إلى عقد
 * الخادم في واحدةٍ فتصير الأخرى تكذب على المكوّن بلا أن يحمرّ شيء.
 *
 * القاعدة هنا نفسها في `pw-offline-test-utils`: تركيبُ الجلسة والمسارات في
 * دالّةٍ واحدة، والأسماء تصف ما تُركّبه.
 */

/** صفّ منتج كما يردّه `/inventory/products/` (عقد المنتقي/الشجرة). */
export type ItemsTreeProductRow = {
  id: number;
  sku: string;
  name_ar: string;
  name_en: string;
  display_name: string;
  category: number | null;
  category_name: string;
  quantity_on_hand: string;
  reserved_quantity: string;
  available_quantity: string;
  avg_cost: string;
  sale_price: string;
  min_stock_level: number;
  stock_status: string;
  has_group: boolean;
  group_key: string | null;
  /** C3: عدد براندات العائلة — تقرؤه نافذة النقل لتحذير انتقال المنتج كلّه
   *  ببرانداته. */
  family_brand_count?: number;
};

const CATEGORIES = [{ id: 3, name: 'إطارات', parent: null }];

/**
 * 403 الذي يردّه `requires_perm` — الرسالة تبنيها `core/access.require_perm`
 * بالاسم العربي للصلاحية والدور، والدور هنا `manager` كما يردّ `/permissions/me/`.
 */
const PERMISSION_DENIED = {
  detail: 'صلاحية «إدارة المنتجات والفئات» غير ممنوحة لدورك (manager).',
};

/** عقدة تصنيف كما يردّها `/inventory/categories/` — يُعاد استخدام النوع في اختبارات C2. */
export type ItemsTreeCategory = { id: number; name: string; parent: number | null };

/** المنتجان الأساسيان — التصنيف «إطارات» (3) وحده. */
export const PRODUCTS: ItemsTreeProductRow[] = [
  {
    id: 7, sku: 'SKU-7', name_ar: 'إطار 205/55', name_en: '', display_name: 'إطار 205/55 — ميشلان',
    category: 3, category_name: 'إطارات', quantity_on_hand: '12', reserved_quantity: '0',
    available_quantity: '12', avg_cost: '30', sale_price: '45', min_stock_level: 2,
    stock_status: 'in_stock', has_group: false, group_key: null,
  },
  {
    id: 8, sku: 'SKU-8', name_ar: 'بطارية 70A', name_en: '', display_name: 'بطارية 70A',
    category: 3, category_name: 'إطارات', quantity_on_hand: '0', reserved_quantity: '0',
    available_quantity: '0', avg_cost: '55', sale_price: '80', min_stock_level: 1,
    stock_status: 'out_of_stock', has_group: false, group_key: null,
  },
];

/** منتجٌ بلا تصنيف (`category: null`) — يظهر تحت صفّ «بدون تصنيف» لا تحت تصنيف. */
export const UNCATEGORIZED_PRODUCT: ItemsTreeProductRow = {
  id: 9, sku: 'SKU-9', name_ar: 'زيت محرك', name_en: '', display_name: 'زيت محرك',
  category: null, category_name: '', quantity_on_hand: '4', reserved_quantity: '0',
  available_quantity: '4', avg_cost: '70', sale_price: '95', min_stock_level: 1,
  stock_status: 'in_stock', has_group: false, group_key: null,
};

const PROFILE_7 = {
  id: 7, sku: 'SKU-7', name: 'إطار 205/55 — ميشلان', brand: 'ميشلان', uom: 'حبة',
  barcode: '6291000', is_service: false, min_stock_level: 2, category: 'إطارات',
  quantity_on_hand: '12', reserved_quantity: '0', available_quantity: '12',
  avg_cost: '30', inventory_valuation: '360', purchased_qty: '20', purchased_value: '600',
  sold_qty: '8', sold_value: '360', avg_weekly_sales: '1', avg_monthly_sales: '4',
  sale_price: '45', last_sale_price: '45', last_sale_invoice: 'INV-1', last_sale_date: '2026-08-01',
  last_purchase_price: '30', effective_sale_price: '45', sale_price_source: 'product',
  profit_per_unit: '15', profit_margin_pct: '33.33', sale_valuation: '540',
};

export type ItemsTreeStubsOptions = {
  /** صفوفٌ تُضاف إلى الأساسيين — لموقفٍ لا تحتاجه بقية الاختبارات. */
  extraProducts?: ItemsTreeProductRow[];
  /** تُنادى بجسم كل POST إلى `/inventory/products/` — إثباتُ ما أرسلته الشاشة فعلاً. */
  onCreateProduct?: (body: Record<string, unknown>) => void;
  /** تصنيفات الشجرة (الافتراضي: جذرٌ واحد «إطارات» على المعرّف 3). */
  categories?: ItemsTreeCategory[];
  /**
   * كرت منتجٍ (`GET /inventory/products/{id}/`) بمفاتيحه — ومعرّفٌ غير موجود فيه
   * يردّ 404 بشكل DRF (`{"detail": …}`)، لا `[]` بـ200.
   */
  productDetails?: Record<number, Record<string, unknown>>;
  /** تُنادى بجسم كل PATCH، ويُردّ صفُّ الكرت بعد الدمج. */
  onUpdateProduct?: (id: number, body: Record<string, unknown>) => void;
  /** C3: تُنادى بجسم `bulk-set-category/` قبل تطبيقه على الحالة المحاكية. */
  onBulkSetCategory?: (body: Record<string, unknown>) => void;
  /** C3: تُنادى بجسم PATCH لتصنيفٍ (إعادة الربط) بعد اجتياز حارس الحلقة. */
  onUpdateCategory?: (id: number, body: Record<string, unknown>) => void;
  /** TASK-1: تُنادى بجسم `POST /inventory/categories/` بعد اجتياز تحقّق الاسم. */
  onCreateCategory?: (body: Record<string, unknown>) => void;
  /** صلاحيات `/permissions/me/` (الافتراضي: عرض وإدارة المنتجات). */
  permissions?: string[];
};

/**
 * ردُّ DRF لكائنٍ غير موجود على مسارٍ تفصيليّ (404 وجسمُ `detail`)، لا `[]`
 * بـ200 — محاكٍ يردّ نجاحاً على معرّفٍ مجهول يُخفي عطباً حقيقياً في الكرت.
 */
const PRODUCT_NOT_FOUND = { detail: 'No Product matches the given query.' };

/**
 * ما يرفضه الخادم فعلاً في `category`: ليس عدداً صحيحاً، أو تصنيفٌ ليس للشركة
 * (هنا: ليس في الشجرة). شكلُ الردّ كما يعيده DRF: `{"category": ["…"]}`.
 * محاكٍ يقبل كل شيء يُخفي عطباً حقيقياً — القاعدة في §6 من تذكرة C2.
 */
function categoryFieldError(
  body: Record<string, unknown>, categories: ItemsTreeCategory[],
): string | null {
  if (!('category' in body)) return null;
  const raw = body.category;
  if (raw === null) return null;
  if (typeof raw !== 'number' && typeof raw !== 'string') {
    return 'Incorrect type. Expected pk value, received ' + typeof raw + '.';
  }
  const id = Number(raw);
  if (!Number.isInteger(id)) return 'Incorrect type. Expected pk value.';
  if (!categories.some((c) => c.id === id)) {
    return `Invalid pk "${String(raw)}" - object does not exist.`;
  }
  return null;
}

/**
 * C3: ما يرفضه `CategorySerializer._validate_parent` — العقدة أباً لنفسها، أو
 * أحد أحفادها أباً لها (حلقة)، أو أبٌ غير موجود. المحاكي يردّ 400 بالشكل نفسه
 * الذي يردّه DRF (`{"parent": ["…"]}`) كي لا يكون الاختبار أرخى من الخادم.
 */
function categoryParentError(
  id: number, parent: unknown, categories: ItemsTreeCategory[],
): string | null {
  if (parent === null) return null;
  if (typeof parent !== 'number' || !Number.isInteger(parent)) {
    return 'Incorrect type. Expected pk value.';
  }
  if (parent === id) return 'لا يصلح التصنيف أباً لنفسه.';
  const byId = new Map(categories.map((c) => [c.id, c]));
  if (!byId.has(parent)) return `Invalid pk "${parent}" - object does not exist.`;
  let node = byId.get(parent);
  const seen = new Set<number>();
  while (node && !seen.has(node.id)) {
    if (node.id === id) {
      return 'لا يصلح تصنيفٌ فرعي أباً لأصله — تنشأ حلقة في الشجرة.';
    }
    seen.add(node.id);
    node = node.parent == null ? undefined : byId.get(node.parent);
  }
  return null;
}

/**
 * ردُّ الإنشاء الحقيقي: `POST /inventory/products/` يعيد صفَّ `ProductSerializer`
 * كاملاً، وواجهةُ الإنشاء السريع تمرّره إلى `productToItem` التي تقرأ منه
 * `id` و`name_ar` و`category`. ردٌّ بـ`{}` يمرّ في المحاكي ويسقط في الإنتاج.
 */
function createdProductRow(
  sent: Record<string, unknown>, id: number, categories: ItemsTreeCategory[],
): Record<string, unknown> {
  const category = sent.category == null ? null : Number(sent.category);
  const nameAr = sent.name_ar == null ? '' : String(sent.name_ar);
  const nameEn = sent.name_en == null ? '' : String(sent.name_en);
  const sku = `SKU-${id}`;
  const categoryName = categories.find((c) => c.id === category)?.name ?? '';
  return {
    id, tenant: 1, sku, barcode: sent.barcode ?? null,
    name_ar: nameAr || null, name_en: nameEn || null,
    display_name: nameAr || nameEn || sku,
    variant_group: null, brand: sent.brand || null,
    category, category_name: categoryName,
    uom_id: sent.uom_id ?? null, uom_name: null,
    uom2: null, uom2_factor: null, uom3: null, uom3_factor: null,
    description: null, storage_location: null, image_url: null,
    sale_account_override: null, sale_return_account_override: null,
    purchase_account_override: null, purchase_return_account_override: null,
    supplier_account_override: null, ending_inventory_account_override: null,
    price_tiers: [],
    weight_kg: null, volume_cbm: null, hs_code: null,
    min_stock_level: 0, max_stock_level: null, reorder_mode: 'manual',
    is_serialized: Boolean(sent.is_serialized), is_service: Boolean(sent.is_service),
    is_active: true, is_for_sale_online: false, online_price: null, online_description: null,
    quantity_on_hand: '0', reserved_quantity: '0', available_quantity: '0', avg_cost: '0',
    sale_price: sent.sale_price ?? null,
    purchased_qty: '0', avg_monthly_sales: '0',
    indicative_purchase_price: null, indicative_purchase_price_source: null,
    stock_status: 'out_of_stock', group_key: null,
    has_group: false, family_id: null, family_name: null,
    effective_min_stock_level: 0, effective_max_stock_level: null,
    serial_required_by: null,
    created_at: '2026-10-21T00:00:00Z', updated_at: '2026-10-21T00:00:00Z',
    attachments: [],
  };
}

/**
 * يثبّت جلسةً مسجَّلة ويردّ كلَّ طلبات API بشجرة منتجاتٍ ثابتة (تصنيف واحد
 * «إطارات» + المنتجات المطلوبة). كلُّ ما لا يُعرف يردّ `[]`.
 */
export async function installItemsTreeApiStubs(page: Page, options: ItemsTreeStubsOptions = {}) {
  // نسخةٌ سطحيّة لكل تركيب: نقلُ منتجٍ أو إعادةُ ربط تصنيفٍ في اختبارٍ لا يجوز
  // أن تتسرّب إلى الاختبار التالي عبر الكائنات المشتركة في هذا الملف.
  const products = [...PRODUCTS, ...(options.extraProducts ?? [])].map((p) => ({ ...p }));
  const categories = (options.categories ?? CATEGORIES).map((c) => ({ ...c }));
  const permissions = options.permissions
    ?? ['inventory.item.view', 'inventory.item.manage'];
  const canManageCatalog = permissions.includes('inventory.item.manage');

  await page.addInitScript(() => {
    localStorage.setItem('token', 'items-tree-e2e-token');
    localStorage.setItem('userId', 'items-tree-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = route.request().method();

    // تعديل منتج — معرّفٌ مجهول 404، وتصنيفٌ غير صالح يُرفض كما يرفضه الخادم
    // (لا محاكٍ يقبل كل شيء). الترتيب ترتيبُ DRF: الكائن أوّلاً ثم حقوله.
    const detail = path.match(/\/inventory\/products\/(\d+)\/$/);
    if (detail && method === 'PATCH') {
      // فحصُ الصلاحية يسبق وجودَ الكائن في DRF (المزيّن قبل جسم الإجراء).
      if (!canManageCatalog) {
        await route.fulfill({
          status: 403, contentType: 'application/json',
          body: JSON.stringify(PERMISSION_DENIED),
        });
        return;
      }
      const id = Number(detail[1]);
      const known = options.productDetails?.[id];
      if (!known) {
        await route.fulfill({
          status: 404, contentType: 'application/json',
          body: JSON.stringify(PRODUCT_NOT_FOUND),
        });
        return;
      }
      const sent = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      const categoryError = categoryFieldError(sent, categories);
      if (categoryError) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ category: [categoryError] }),
        });
        return;
      }
      options.onUpdateProduct?.(id, sent);
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ...known, ...sent }),
      });
      return;
    }

    // إنشاء منتج من الشجرة — يُلتقط الجسم ويُردّ صفٌّ بشكله الحقيقي.
    if (method === 'POST' && path.endsWith('/inventory/products/')) {
      if (!canManageCatalog) {
        await route.fulfill({
          status: 403, contentType: 'application/json',
          body: JSON.stringify(PERMISSION_DENIED),
        });
        return;
      }
      const sent = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      const categoryError = categoryFieldError(sent, categories);
      if (categoryError) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ category: [categoryError] }),
        });
        return;
      }
      options.onCreateProduct?.(sent);
      const created = createdProductRow(sent, 100, categories);
      // يظهر في القوائم التالية — وإلا «أُنشئ» منتجٌ لا تعرفه الشجرة أبداً.
      products.push(created as unknown as ItemsTreeProductRow);
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) });
      return;
    }

    // C3: نقل منتجاتٍ دفعةً — نفس تحقّق الخادم: قائمةٌ غير فارغة، معرّفاتٌ
    // صحيحة، مفتاح `category` حاضر (null صريحٌ = بدون تصنيف)، وتصنيفٌ من شجرة
    // الشركة. ثم تُحدَّث الحالة المحاكية كي تُظهر إعادةُ الجلب الموضعَ الجديد.
    if (method === 'POST' && path.endsWith('/inventory/products/bulk-set-category/')) {
      if (!canManageCatalog) {
        await route.fulfill({
          status: 403, contentType: 'application/json',
          body: JSON.stringify(PERMISSION_DENIED),
        });
        return;
      }
      const sent = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      const rawIds = sent.product_ids;
      if (!Array.isArray(rawIds) || rawIds.length === 0) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: 'لم تُحدَّد منتجات' }),
        });
        return;
      }
      if (!rawIds.every((id) => typeof id === 'number' && Number.isInteger(id))) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: 'معرّف منتج غير صالح في القائمة' }),
        });
        return;
      }
      if (!('category' in sent)) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: 'category مطلوب — معرّف تصنيف أو null' }),
        });
        return;
      }
      const rawCategory = sent.category;
      if (
        rawCategory !== null
        && (typeof rawCategory !== 'number' || !Number.isInteger(rawCategory))
      ) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: 'category يجب أن يكون معرّف تصنيف أو null' }),
        });
        return;
      }
      const category = rawCategory === null
        ? null
        : categories.find((c) => c.id === rawCategory) ?? null;
      if (rawCategory !== null && !category) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ category: ['التصنيف غير موجود لهذه الشركة.'] }),
        });
        return;
      }
      options.onBulkSetCategory?.(sent);
      const requested = rawIds as number[];
      const skipped: number[] = [];
      let moved = 0;
      let brandsMoved = 0;
      for (const id of requested) {
        const row = products.find((p) => p.id === id);
        if (!row) {
          if (!skipped.includes(id)) skipped.push(id);
          continue;
        }
        const target = category ? category.id : null;
        if (row.category !== target) {
          row.category = target;
          row.category_name = category ? category.name : '';
          moved += 1;
          // إخوة العائلة ليسوا صفوفاً في هذه القائمة المحاكية: يُضافون بالعدد
          // كما يعيدهم الخادم (نقل صفٍّ واحد ينقل كل براندات المنتج).
          const familyBrands = row.family_brand_count ?? 1;
          brandsMoved += 1 + (familyBrands > 1 ? familyBrands - 1 : 0);
        }
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ moved, brands_moved: brandsMoved, skipped }),
      });
      return;
    }

    // TASK-1: إنشاء تصنيف — نفس ما يرفضه `CategorySerializer`: اسمٌ فارغ 400
    // (`validate_name`)، وأبٌ غير موجودٍ للشركة 400 (`_validate_parent`). ويُضاف
    // إلى الحالة المحاكية كي تُظهره إعادةُ الجلب التالية (كان «أُنشئ» تصنيفاً لا
    // تعرفه الشجرة أبداً). الجسمُ بردّ `CategorySerializer` نفسه.
    if (method === 'POST' && path.endsWith('/inventory/categories/')) {
      if (!canManageCatalog) {
        await route.fulfill({
          status: 403, contentType: 'application/json',
          body: JSON.stringify(PERMISSION_DENIED),
        });
        return;
      }
      const sent = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      const name = typeof sent.name === 'string' ? sent.name.trim() : '';
      if (!name) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ name: ['اسم التصنيف مطلوب.'] }),
        });
        return;
      }
      const parent = sent.parent == null ? null : Number(sent.parent);
      if (parent !== null && !categories.some((c) => c.id === parent)) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ parent: ['التصنيف الأب غير موجود لهذه الشركة.'] }),
        });
        return;
      }
      options.onCreateCategory?.(sent);
      const created = { id: Math.max(0, ...categories.map((c) => c.id)) + 1, name, parent };
      categories.push(created);
      await route.fulfill({
        status: 201, contentType: 'application/json',
        body: JSON.stringify({ ...created, tenant: 1, children: [] }),
      });
      return;
    }

    // C3: إعادة ربط تصنيف — 404 لمعرّفٍ مجهول، و400 بالشكل الحقيقي للحلقة.
    const categoryDetail = path.match(/\/inventory\/categories\/(\d+)\/$/);
    if (categoryDetail && method === 'PATCH') {
      if (!canManageCatalog) {
        await route.fulfill({
          status: 403, contentType: 'application/json',
          body: JSON.stringify(PERMISSION_DENIED),
        });
        return;
      }
      const id = Number(categoryDetail[1]);
      const node = categories.find((c) => c.id === id);
      if (!node) {
        await route.fulfill({
          status: 404, contentType: 'application/json',
          body: JSON.stringify({ detail: 'No ProductCategory matches the given query.' }),
        });
        return;
      }
      const sent = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      if ('parent' in sent) {
        const parentError = categoryParentError(id, sent.parent, categories);
        if (parentError) {
          await route.fulfill({
            status: 400, contentType: 'application/json',
            body: JSON.stringify({ parent: [parentError] }),
          });
          return;
        }
      }
      if (typeof sent.name === 'string') node.name = sent.name;
      if ('parent' in sent) {
        node.parent = sent.parent === null ? null : Number(sent.parent);
      }
      options.onUpdateCategory?.(id, sent);
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(node) });
      return;
    }

    let body: unknown = [];
    if (path.endsWith('/hr/users/items-tree-e2e-user/')) {
      body = {
        id: 'items-tree-e2e-user', name: 'Items Tester', role: 'manager',
        email: 'items@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة المنتجات', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = {
        role: 'manager', is_manager: true, ui_mode: 'advanced',
        permissions,
      };
    } else if (path.endsWith('/inventory/categories/')) {
      body = categories;
    } else if (detail && method === 'GET') {
      const known = options.productDetails?.[Number(detail[1])];
      if (!known) {
        await route.fulfill({
          status: 404, contentType: 'application/json',
          body: JSON.stringify(PRODUCT_NOT_FOUND),
        });
        return;
      }
      body = known;
    } else if (/\/inventory\/products\/\d+\/profile\/$/.test(path)) {
      const id = Number(path.match(/products\/(\d+)\/profile/)![1]);
      body = id === 7 ? PROFILE_7 : { ...PROFILE_7, id, sku: `SKU-${id}`, name: 'بطارية 70A' };
    } else if (/\/inventory\/products\/\d+\/stock-ledger\/$/.test(path)) {
      body = { count: 0, results: [] };
    } else if (/\/inventory\/products\/\d+\/invoices\/$/.test(path)) {
      body = [];
    } else if (path.endsWith('/inventory/products/group-profile/')) {
      body = {
        name: 'إطارات', category: 'إطارات', member_count: products.length,
        members: products.map((p) => ({
          id: p.id, sku: p.sku, brand: '—', name: p.display_name,
          quantity_on_hand: p.quantity_on_hand, avg_cost: p.avg_cost,
          inventory_valuation: '360', sold_qty: '8',
        })),
        quantity_on_hand: '12', inventory_valuation: '360',
        purchased_qty: '20', purchased_value: '600', sold_qty: '8', sold_value: '360',
      };
    } else if (path.endsWith('/inventory/products/group-ledger/')) {
      body = { count: 0, results: [] };
    } else if (path.endsWith('/inventory/products/group-invoices/')) {
      body = [];
    } else if (path.endsWith('/inventory/products/')) {
      // `OptionalPageNumberPagination`: بلا `page` يعيد الخادم مصفوفةً عارية،
      // ومع `page` يعيد `{count, results, …}` — والمحاكي يقول ما يقوله الخادم
      // (شاشة الأرصدة تطلب بلا `page` وتقرأ مصفوفة، والشجرة تطلب بصفحات).
      body = url.searchParams.has('page')
        ? { count: products.length, results: products, next: null, previous: null }
        : products;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}
