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
};

const CATEGORIES = [{ id: 3, name: 'إطارات', parent: null }];

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
};

/**
 * ردُّ الإنشاء الحقيقي: `POST /inventory/products/` يعيد صفَّ `ProductSerializer`
 * كاملاً، وواجهةُ الإنشاء السريع تمرّره إلى `productToItem` التي تقرأ منه
 * `id` و`name_ar` و`category`. ردٌّ بـ`{}` يمرّ في المحاكي ويسقط في الإنتاج.
 */
function createdProductRow(sent: Record<string, unknown>, id: number): Record<string, unknown> {
  const category = sent.category == null ? null : Number(sent.category);
  const nameAr = sent.name_ar == null ? '' : String(sent.name_ar);
  const nameEn = sent.name_en == null ? '' : String(sent.name_en);
  const sku = `SKU-${id}`;
  const categoryName = CATEGORIES.find((c) => c.id === category)?.name ?? '';
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
  const products = [...PRODUCTS, ...(options.extraProducts ?? [])];

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

    // إنشاء منتج من الشجرة — يُلتقط الجسم ويُردّ صفٌّ بشكله الحقيقي.
    if (method === 'POST' && path.endsWith('/inventory/products/')) {
      const sent = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      options.onCreateProduct?.(sent);
      const created = createdProductRow(sent, 100);
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) });
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
        permissions: ['inventory.item.view', 'inventory.item.manage'],
      };
    } else if (path.endsWith('/inventory/categories/')) {
      body = CATEGORIES;
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
      body = { count: products.length, results: products, next: null, previous: null };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}
