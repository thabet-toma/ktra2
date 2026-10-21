import { test, expect, type Locator, type Page } from '@playwright/test';

/**
 * B2 — البراند قابلٌ للتعديل من كل سطح تعديل، ولا يُمسح بالخطأ.
 *
 * ثلاثةُ عيوبٍ أثبتها التحقيق (D5 في خطة الجرد):
 *   1. حقلُ البراند في وضع التعديل كان في شريط الهوية وحده، وتبويب «بيانات عامة»
 *      — حيث يعمل المستخدم — بلا حقل.
 *   2. «+» في `ValuePicker` كان يستدعي `onChange("")`، وكذلك «إلغاء» — فيمسح
 *      البراند فوراً ويُحفظ فارغاً إن ضغط المستخدم «تخزين».
 *   3. `ItemQuickEditModal` (قلم التعديل من كل مستند) لم يكن يعرضه أصلاً.
 *
 * الشبكة موقوفة بالكامل: موضوع الفحص هو الحقل والحمولة، لا الخادم. كل ردٍّ يحمل
 * شكل `ProductSerializer` الحقيقي (نفس عقد `items-tree-stubs.ts`).
 */

const DETAIL_7 = {
  id: 7, tenant: 1, sku: 'SKU-7', barcode: '6291000',
  name_ar: 'إطار 205/55', name_en: '', display_name: 'إطار 205/55 — ميشلان',
  variant_group: 'إطار رياضي', brand: 'ميشلان', category: 3, category_name: 'إطارات',
  uom_id: null, uom_name: null, uom2: null, uom2_factor: null, uom3: null, uom3_factor: null,
  description: null, storage_location: null, image_url: null,
  sale_account_override: null, sale_return_account_override: null,
  purchase_account_override: null, purchase_return_account_override: null,
  supplier_account_override: null, ending_inventory_account_override: null,
  price_tiers: [], weight_kg: null, volume_cbm: null, hs_code: null,
  min_stock_level: 2, max_stock_level: null, reorder_mode: 'manual',
  is_serialized: false, is_service: false, is_active: true,
  is_for_sale_online: false, online_price: null, online_description: null,
  quantity_on_hand: '12', reserved_quantity: '0', available_quantity: '12', avg_cost: '30',
  sale_price: '45', purchased_qty: '20', avg_monthly_sales: '4',
  indicative_purchase_price: null, indicative_purchase_price_source: null,
  stock_status: 'in_stock', group_key: null, has_group: false,
  family_id: 40, family_name: 'إطار 205/55',
  effective_min_stock_level: 2, effective_max_stock_level: null, serial_required_by: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-21T00:00:00Z',
  attachments: [],
};

/**
 * صفُّ قائمة `/inventory/products/`: بلا `page` يعيد الخادم مصفوفةً عارية
 * (`OptionalPageNumberPagination`)، وبلا `view=lookup` سيرياليزرُه
 * `ProductSerializer` نفسه (`ProductViewSet.get_serializer_class`) — فمفاتيح
 * الصفّ هي مفاتيح الكرت حرفاً، لا مجموعةً مصغَّرة. والاسمُ في الجدول يُحرَّر عبر
 * `simpleFieldsFromProduct(row)`، فغيابُ `brand` من الصفّ كان يجعل الحمولة
 * تقارنه بفراغ.
 */
const LIST_ROW = DETAIL_7;

type Patch = { id: number; body: Record<string, unknown> };
let patches: Patch[] = [];

/**
 * ما يرفضه DRF لـ`Product.brand` بالضبط: `CharField(max_length=100, blank=True)`
 * بلا `allow_null` ⇒ `null` خطأٌ لا محو، وأكثر من 100 حرفٍ خطأُ طول. وشكلُ
 * الخطأ كما يعيده DRF: `{"brand": ["..."]}`.
 */
const brandFieldError = (body: Record<string, unknown>): string | null => {
  const brand = body.brand;
  if (brand === undefined) return null;
  if (brand === null) return 'This field may not be null.';
  if (typeof brand === 'string' && brand.length > 100) {
    return 'Ensure this field has no more than 100 characters.';
  }
  return null;
};

test.beforeEach(async ({ page }) => {
  patches = [];

  await page.addInitScript(() => {
    localStorage.setItem('token', 'items-brand-e2e-token');
    localStorage.setItem('userId', 'items-brand-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = route.request().method();
    const detail = path.match(/\/inventory\/products\/(\d+)\/$/);

    if (detail && method === 'PATCH') {
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      const brandError = brandFieldError(body);
      if (brandError) {
        await route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ brand: [brandError] }),
        });
        return;
      }
      patches.push({ id: Number(detail[1]), body });
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ...DETAIL_7, ...body }),
      });
      return;
    }

    let body: unknown = [];
    if (path.endsWith('/hr/users/items-brand-e2e-user/')) {
      body = {
        id: 'items-brand-e2e-user', name: 'Brand Tester', role: 'manager',
        email: 'brand@example.test', employmentStatus: 'active',
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
    } else if (path.endsWith('/inventory/products/brands/')) {
      body = ['ميشلان', 'تويو'];
    } else if (path.endsWith('/inventory/products/groups/')) {
      body = ['إطار رياضي'];
    } else if (path.endsWith('/inventory/categories/')) {
      body = [{ id: 3, name: 'إطارات', parent: null }];
    } else if (path.endsWith('/inventory/stock-movements/summary/')) {
      body = { total_products_in_stock: 1, total_inventory_value: '360' };
    } else if (/\/inventory\/products\/\d+\/profile\/$/.test(path)) {
      body = {
        id: 7, sku: 'SKU-7', name: 'إطار 205/55 — ميشلان', brand: 'ميشلان',
        uom: 'حبة', category: 'إطارات', family_id: 40,
        quantity_on_hand: '12', reserved_quantity: '0', available_quantity: '12',
        avg_cost: '30', inventory_valuation: '360', sale_price: '45',
        effective_sale_price: '45', profit_per_unit: '15', profit_margin_pct: '33.33',
      };
    } else if (/\/inventory\/products\/\d+\/(stock-ledger|invoices|serials)\/$/.test(path)) {
      body = { count: 0, results: [] };
    } else if (detail) {
      body = DETAIL_7;
    } else if (path.endsWith('/inventory/products/')) {
      // بلا `page` → مصفوفة (OptionalPageNumberPagination).
      body = [LIST_ROW];
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
});

/**
 * حقلٌ عنوانُه «البراند» **نصّاً تامّاً** — لا `hasText` الجزئي الذي يلتقط
 * «— بلا براند —» أو «أضف البراند تحته» في نفس الشاشة.
 */
const brandField = (root: Page | Locator) =>
  root.getByText('البراند', { exact: true })
    .locator('xpath=ancestor::label').first();

/** حقلُ «الصنف / المجموعة» في الكرت (خلف «متقدم») — عنوانُه الطويل بنصّه التام. */
const groupField = (page: Page) =>
  page.getByText('الصنف / المجموعة (موديلات الصنف الواحد بدائلُ بعضها)', { exact: true })
    .locator('xpath=ancestor::label').first();

const floatWin = (page: Page, titlePart: string) =>
  page.locator('.ktra-float-win')
    .filter({ has: page.locator('.ktra-float-win__title', { hasText: titlePart }) });

const openItemCard = async (page: Page) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  // نقرتان على خلية الرمز تفتحان الكرت الكامل (المنفذ القائم).
  await page.getByTitle('SKU-7').first().dblclick();
  await page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' }).waitFor();
  await page.getByRole('tab', { name: 'بيانات عامة' }).click();
};

const saveCard = (page: Page) => page.getByRole('button', { name: /تخزين/ }).click();

test('حقل البراند في «بيانات عامة» يبقى «ميشلان» بعد «+» و«إلغاء» — ولا يُحفظ فارغاً', async ({ page }) => {
  await openItemCard(page);

  // 1) الحقل موجودٌ في التبويب الذي يعمل فيه المستخدم، بقيمته الحقيقية.
  const select = brandField(page).locator('select');
  await expect(select).toHaveValue('ميشلان');

  // 2) «+» لا يمسح القيمة: يفتح إدخالاً فارغاً، و«إلغاء» يعود بلا كتابة.
  await brandField(page).getByTitle('براند جديد').click();
  await expect(brandField(page).getByPlaceholder('مثال: ميشلان')).toHaveValue('');
  await brandField(page).getByTitle('إلغاء').click();
  await expect(brandField(page).locator('select')).toHaveValue('ميشلان');

  // 3) الحفظ بعد الإلغاء يحمل البراند نفسه — لا فقدان بيانات ولا `""`.
  await saveCard(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0].id).toBe(7);
  expect(patches[0].body.brand).toBe('ميشلان');
});

test('تغيير البراند عبر «✓» يُرسَل في حمولة الحفظ', async ({ page }) => {
  await openItemCard(page);

  await brandField(page).getByTitle('براند جديد').click();
  const input = brandField(page).getByPlaceholder('مثال: ميشلان');
  await input.fill('تويو');
  await brandField(page).getByTitle('تم').click();

  await expect(brandField(page).locator('select')).toHaveValue('تويو');

  await saveCard(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0].body.brand).toBe('تويو');
});

test('ما كُتب في «+» يُحفظ بلا «✓» إن ضغط المستخدم «تخزين»', async ({ page }) => {
  await openItemCard(page);

  await brandField(page).getByTitle('براند جديد').click();
  // الكتابة وحدها — لا «✓» ولا Enter.
  await brandField(page).getByPlaceholder('مثال: ميشلان').fill('تويو');

  await saveCard(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0].body.brand).toBe('تويو');
});

test('التحرير السريع: تغيير البراند وحده يرسل `{ brand }` وحده', async ({ page }) => {
  await page.goto('/stock-levels');
  await page.waitForLoadState('networkidle');

  await page.getByTitle('تعديل سريع للمنتج').first().click();
  const win = floatWin(page, 'تعديل سريع');
  await expect(brandField(win).locator('select')).toHaveValue('ميشلان');

  await brandField(win).getByTitle('براند جديد').click();
  await brandField(win).getByPlaceholder('مثال: ميشلان').fill('تويو');
  await brandField(win).getByTitle('تم').click();
  await expect(brandField(win).locator('select')).toHaveValue('تويو');

  await win.getByRole('button', { name: 'حفظ', exact: true }).click();
  await expect(win).toHaveCount(0);

  await expect.poll(() => patches.length).toBe(1);
  // فرقُ ما تغيّر وحده — لا الاسم ولا التصنيف ولا سعر البيع.
  expect(patches[0].body).toEqual({ brand: 'تويو' });
});

test('«الصنف/المجموعة»: «+» ثم «إلغاء» يُبقي المجموعة الأصلية في الحقل وفي الحمولة', async ({ page }) => {
  await openItemCard(page);
  // «الصنف / المجموعة» من حقول «متقدم» في الكرت — يُفتح أوّلاً.
  await page.getByRole('button', { name: /متقدم/ }).click();

  await expect(groupField(page).locator('select')).toHaveValue('إطار رياضي');

  await groupField(page).getByTitle('صنف جديد').click();
  await expect(groupField(page).getByPlaceholder('مثال: ايفون 14 برو')).toHaveValue('');
  await groupField(page).getByTitle('إلغاء').click();

  await expect(groupField(page).locator('select')).toHaveValue('إطار رياضي');

  await saveCard(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0].body.variant_group).toBe('إطار رياضي');
});

test('التحرير السريع (قلم أرصدة المخزون) يعرض البراند الحالي', async ({ page }) => {
  await page.goto('/stock-levels');
  await page.waitForLoadState('networkidle');

  await page.getByTitle('تعديل سريع للمنتج').first().click();
  const win = floatWin(page, 'تعديل سريع');
  await expect(brandField(win).locator('select')).toHaveValue('ميشلان');
});
