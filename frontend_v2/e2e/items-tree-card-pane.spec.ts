import { test, expect } from '@playwright/test';

/**
 * العرض الشجري للمنتجات: الشجرة شريط 240px على اليمين، وبقية عرض الشاشة — التي
 * كانت بياضاً معطَّلاً — بطاقةُ المنتج المحدَّد. يثبّت الاختبار العقد: قبل الاختيار
 * دعوةٌ لاختيار منتج، وبعده تظهر البطاقة **في الصفحة نفسها** (لا تبويب جديد)
 * وتحتلّ المساحة الفارغة إلى يسار الشجرة.
 */
const PRODUCTS = [
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

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'items-tree-e2e-token');
    localStorage.setItem('userId', 'items-tree-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    let body: unknown = [];
    const path = url.pathname;
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
      body = [{ id: 3, name: 'إطارات', parent: null }];
    } else if (/\/inventory\/products\/\d+\/profile\/$/.test(path)) {
      const id = Number(path.match(/products\/(\d+)\/profile/)![1]);
      body = id === 7 ? PROFILE_7 : { ...PROFILE_7, id, sku: `SKU-${id}`, name: 'بطارية 70A' };
    } else if (/\/inventory\/products\/\d+\/stock-ledger\/$/.test(path)) {
      body = { count: 0, results: [] };
    } else if (/\/inventory\/products\/\d+\/invoices\/$/.test(path)) {
      body = [];
    } else if (path.endsWith('/inventory/products/group-profile/')) {
      body = {
        name: 'إطارات', category: 'إطارات', member_count: 2,
        members: PRODUCTS.map((p) => ({
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
      body = { count: PRODUCTS.length, results: PRODUCTS, next: null, previous: null };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
});

test('الفراغ بجانب شجرة المنتجات يصير بطاقة المنتج عند النقر على منتج', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');

  // التبديل إلى العرض الشجري (الافتراضي جدول).
  await page.getByTitle('عرض كشجرة تصنيفات').click();

  const hint = page.getByText('اختر منتجاً من الشجرة لتظهر بطاقته هنا');
  await expect(hint).toBeVisible();

  const tree = page.locator('.ktra-tree-panel');
  await expect(tree).toBeVisible();

  // فتح التصنيف ثم النقر على المنتج.
  await tree.getByTitle('فتح').first().click();
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click();

  // البطاقة ظهرت في الصفحة نفسها — لا تبويب جديد.
  expect(page.context().pages()).toHaveLength(1);
  await expect(hint).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'نظرة عامة' })).toBeVisible();
  await expect(page.getByText('سعر البيع العام')).toBeVisible();
  await expect(page.getByRole('button', { name: /الكرت الكامل/ })).toBeVisible();

  // البطاقة تحتلّ المساحة التي كانت بيضاء: إلى يسار الشجرة وأعرض منها.
  const treeBox = (await tree.boundingBox())!;
  const paneBox = (await page.getByRole('tab', { name: 'نظرة عامة' })
    .locator('xpath=ancestor::div[contains(@class,"flex-1")][1]').boundingBox())!;
  expect(paneBox.x).toBeLessThan(treeBox.x);
  expect(paneBox.width).toBeGreaterThan(treeBox.width);
});

test('اختيار منتج آخر يبدّل البطاقة في مكانها', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await page.getByTitle('عرض كشجرة تصنيفات').click();

  const tree = page.locator('.ktra-tree-panel');
  await tree.getByTitle('فتح').first().click();
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click();
  await expect(page.getByText('SKU-7').first()).toBeVisible();

  await tree.getByRole('button', { name: /بطارية 70A/ }).click();
  await expect(page.getByText('SKU-8').first()).toBeVisible();
  await expect(page.getByText('SKU-7')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /تعديل/ })).toBeVisible();
  expect(page.context().pages()).toHaveLength(1);
});

test('النقر على تصنيف يعرض كرته المجمّع في البطاقة نفسها — لا تبويب جديد', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await page.getByTitle('عرض كشجرة تصنيفات').click();

  const tree = page.locator('.ktra-tree-panel');
  await tree.getByRole('button', { name: 'إطارات' }).click();

  expect(page.context().pages()).toHaveLength(1);
  await expect(page.getByRole('tab', { name: 'نظرة عامة (مجمّع)' })).toBeVisible();
  await expect(page.getByText('عدد البراندات')).toBeVisible();
  await expect(page.getByText('2 منتج')).toBeVisible();

  // الكبسة نفسها تفتح الفرع فتظهر أوراقه (اختيارٌ وكشفٌ بكبسة واحدة).
  await expect(tree.getByRole('button', { name: /بطارية 70A/ })).toBeVisible();

  // تبويب البراندات يسرد أعضاء المجموعة داخل البطاقة نفسها.
  await page.getByRole('tab', { name: 'البراندات' }).click();
  await expect(page.getByRole('button', { name: /بطارية 70A/ }).last()).toBeVisible();

  // ومنها إلى منتج مفرد: البطاقة تتبدّل في مكانها.
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click();
  await expect(page.getByRole('tab', { name: 'نظرة عامة', exact: true })).toBeVisible();
  expect(page.context().pages()).toHaveLength(1);
});

test('طيّ الشجرة يسلّم عرضها للبطاقة — شريط لا لوحة فارغة', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await page.getByTitle('عرض كشجرة تصنيفات').click();
  await page.locator('.ktra-tree-panel').getByRole('button', { name: 'إطارات' }).click();

  const paneBefore = (await page.getByRole('tablist').boundingBox())!;
  await page.getByTitle('طيّ اللوحة').click();

  const rail = page.locator('.ktra-tree-rail');
  const railBox = (await rail.boundingBox())!;
  expect(railBox.width).toBeLessThan(60);
  await expect(page.locator('.ktra-tree-panel')).toHaveCount(0);

  const paneAfter = (await page.getByRole('tablist').boundingBox())!;
  expect(paneAfter.width).toBeGreaterThan(paneBefore.width);

  // ولا طريق مسدود: الشريط يعيد الشجرة.
  await rail.click();
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();
});

/**
 * الشكل الحاليّ للرابط: التصنيف وحده — الخادم يشتقّ منتجاته وأحفاده. تعدادُ
 * المعرّفات لتصنيفٍ فيه ~1500 منتج كان يُنتج رابطاً ~7.5KB فيردّه nginx (414)
 * قبل أن تُقلع الواجهة أصلاً.
 */
test('الكرت المجمّع بالتصنيف (/product-group?category=) يعرض التبويبات', async ({ page }) => {
  await page.goto('/product-group?category=3&name=%D8%A5%D8%B7%D8%A7%D8%B1%D8%A7%D8%AA');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('كرت مجمّع: إطارات')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'نظرة عامة (مجمّع)' })).toBeVisible();
});

/** الصفحة الكاملة صارت غلافاً فوق نفس الخطّاف — فلتبقَ حيّة بتبويباتها.
 *  و`?ids=` يبقى مفهوماً: روابط قديمة محفوظة عند المستخدمين. */
test('الكرت المجمّع الكامل (/product-group) يعرض التبويبات نفسها', async ({ page }) => {
  await page.goto('/product-group?ids=7,8&name=%D8%A5%D8%B7%D8%A7%D8%B1%D8%A7%D8%AA');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('كرت مجمّع: إطارات')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'نظرة عامة (مجمّع)' })).toBeVisible();
  await expect(page.getByText('عدد البراندات')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'حركة المخزون (مجمّعة)' })).toBeVisible();
});
