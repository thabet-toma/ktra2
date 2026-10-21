import { test, expect, type Page } from '@playwright/test';

/**
 * R1 — تقرير «المبيعات حسب المنتج»: «المنتج» مقابل «البراند»، وفلاتر تُبحث.
 *
 * ما يُثبَت هنا سلوكُ الشاشة وحده (الخادم يثبته `core/tests/
 * test_reports_family_rollup.py`): الفلتر يبحث في الخادم بـ`?search=` بدل تنزيل
 * الكتالوج كلّه، والاختيار والمسح يُشغّلان التقرير بالمفتاح الصحيح، والموقوف
 * يحمل لافتته، وسهم التوسيع يفتح البراندات.
 *
 * المحاكي يردّ بالأشكال الحقيقية: القوائم مغلَّفة بـ`{count, next, previous,
 * results}` لأن الطلب يحمل `page` (`core/pagination.py`
 * `OptionalPageNumberPagination`)، وطلبٌ بلا `search` يُرفض 400 — فرجوعٌ إلى
 * تنزيل الكتالوج كاملاً يُسقط الاختبار بدل أن يمرّ صامتاً.
 */

const GRAIN_HINT = 'كل صفّ منتجٌ بكلّ براندَاته — افتح الصفّ لترى البراندات';

const COLUMNS = [
  { key: 'sku', header: 'الرمز', kind: 'text', total: false, width: null },
  { key: 'name', header: 'المنتج', kind: 'text', total: false, width: null },
  { key: 'brand_count', header: 'عدد البراندات', kind: 'int', total: false, width: null },
  { key: 'quantity', header: 'الكمية', kind: 'number', total: true, width: null },
  { key: 'net_sales', header: 'صافي المبيعات', kind: 'money', total: true, width: null },
];

const DRILL_COLUMNS = [
  { key: 'brand', header: 'البراند', kind: 'text', total: false, width: null },
  { key: 'sku', header: 'الرمز', kind: 'text', total: false, width: null },
  { key: 'name', header: 'المنتج', kind: 'text', total: false, width: null },
  { key: 'quantity', header: 'الكمية', kind: 'number', total: true, width: null },
  { key: 'net_sales', header: 'صافي المبيعات', kind: 'money', total: true, width: null },
];

const SUMMARY = {
  key: 'sales-by-product',
  title: 'المبيعات حسب المنتج',
  description: 'كمّ بيع كل منتج وربحه.',
  hint: GRAIN_HINT,
  permission: null,
  screen_path: null,
  row_link: null,
  filters: [
    { key: 'from', label: 'من تاريخ', kind: 'date', options: [], default: null },
    { key: 'to', label: 'إلى تاريخ', kind: 'date', options: [], default: null },
    { key: 'family_id', label: 'المنتج', kind: 'family', options: [], default: null },
    { key: 'product', label: 'البراند', kind: 'product', options: [], default: null },
  ],
  columns: COLUMNS,
};

const RESULT = {
  key: 'sales-by-product',
  title: 'المبيعات حسب المنتج',
  category: 'sales',
  description: 'كمّ بيع كل منتج وربحه.',
  hint: GRAIN_HINT,
  row_link: null,
  drill: { title: 'برندات هذا المنتج', keys: ['family_id', 'product_id'], columns: DRILL_COLUMNS },
  columns: COLUMNS,
  rows: [
    { sku: '', name: 'مقاس 195/85/15', brand: '', brand_count: 2, quantity: '4', net_sales: '230.00', family_id: 3, product_id: '' },
  ],
  totals: { quantity: '4', net_sales: '230.00' },
  total_rows: 1,
  truncated: false,
  generated_at: '2026-10-21T10:00:00',
};

const DRILL_RESULT = {
  key: 'sales-by-product',
  title: 'برندات هذا المنتج',
  columns: DRILL_COLUMNS,
  rows: [
    { brand: 'دانتير', sku: 'TIRE-A', name: '195/85/15 دانتير', quantity: '3', net_sales: '150.00' },
    { brand: 'أوتولوكس', sku: 'TIRE-B', name: '195/85/15 أوتولوكس', quantity: '1', net_sales: '80.00' },
  ],
  totals: { quantity: '4', net_sales: '230.00' },
  total_rows: 2,
  truncated: false,
};

/** كل ما يقرؤه هذا الفلتر من `ProductLookupSerializer` — ومنه `is_active`. */
const PRODUCT_ROWS = [
  {
    id: 7, sku: 'TIRE-A', barcode: '6291000000017', brand: 'دانتير',
    name_ar: '195/85/15 دانتير', name_en: null,
    display_name: '195/85/15 دانتير (دانتير)',
    family_id: 3, family_name: 'مقاس 195/85/15',
    category_name: 'إطارات', supplier_codes_text: 'MICH-195',
    min_stock_level: 0, is_active: true,
  },
  {
    id: 9, sku: 'TIRE-X', barcode: '', brand: 'دانتير',
    name_ar: '195/85/15 قديم', name_en: null,
    display_name: '195/85/15 قديم (دانتير)',
    family_id: 3, family_name: 'مقاس 195/85/15',
    category_name: 'إطارات', supplier_codes_text: '',
    min_stock_level: 0, is_active: false,
  },
];

/** ما يقرؤه الفلتر من `ProductFamilySerializer` — لا `is_active` فيه أصلاً. */
const FAMILY_ROWS = [
  { id: 3, tenant: 1, name_ar: 'مقاس 195/85/15', name_en: null },
];

const BRAND_PLACEHOLDER = 'الكل — ابحث بالاسم أو الرمز أو البراند';
const FAMILY_PLACEHOLDER = 'الكل — ابحث باسم المنتج';

/** غلاف صفحة الخادم الحقيقي — الطلب يحمل `page` فيُغلَّف الردّ. */
const paged = (rows: unknown[]) => ({
  count: rows.length, next: null, previous: null, results: rows,
});

const setup = async (page: Page) => {
  /** نداءات كل نقطة على حدة + استعلامات تشغيل التقرير — لا حوضٌ واحد يخلطها. */
  const calls = {
    productLookups: [] as string[],
    familyLookups: [] as string[],
    runs: [] as string[],
  };
  await page.addInitScript(() => {
    localStorage.setItem('token', 'reports-e2e-token');
    localStorage.setItem('userId', 'reports-e2e-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('lastActivityAt', String(Date.now()));
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    const search = (url.searchParams.get('search') ?? '').trim();

    /** حارسُ المحاكي لا عقدُ الخادم: الخادم يقبل الطلب بلا `search` ويعيد الكتالوج كلّه —
     *  وهي العلّة التي جاء المنقّي لإزالتها، فنداءٌ عارٍ هنا يُسقط الاختبار. */
    const needsSearch = async () => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'stub: search required' }),
      });
    };

    let body: unknown = [];
    if (path.endsWith('/hr/users/reports-e2e-user/')) {
      body = {
        id: 'reports-e2e-user', name: 'Reports Tester', role: 'manager',
        email: 'reports@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة التقارير', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = { role: 'manager', is_manager: true, permissions: [] };
    } else if (path.endsWith('/api/reports/')) {
      body = { categories: [{ key: 'sales', label: 'المبيعات', reports: [SUMMARY] }] };
    } else if (path.endsWith('/api/reports/sales-by-product/drill/')) {
      body = DRILL_RESULT;
    } else if (path.endsWith('/api/reports/sales-by-product/')) {
      calls.runs.push(url.search);
      body = RESULT;
    } else if (path.endsWith('/api/lookup/products/')) {
      calls.productLookups.push(url.search);
      if (!search) return needsSearch();
      body = paged(PRODUCT_ROWS);
    } else if (path.endsWith('/api/inventory/product-families/')) {
      calls.familyLookups.push(url.search);
      if (!search) return needsSearch();
      body = paged(FAMILY_ROWS);
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return calls;
};

const brandField = (page: Page) =>
  page.locator('.ktra-field', { hasText: 'البراند' }).getByRole('combobox');

const familyField = (page: Page) =>
  page.locator('.ktra-field', { hasText: 'المنتج' }).getByRole('combobox');

const optionsList = (page: Page) => page.getByRole('listbox');

const lastQuery = (search: string) => new URLSearchParams(search);

test('الفلتر يبحث في الخادم، والاختيار يشغّل التقرير، والمسح يعيد «الكل»', async ({ page }) => {
  const calls = await setup(page);

  await page.goto('/reports/sales-by-product');
  await expect(page.getByText('مقاس 195/85/15')).toBeVisible({ timeout: 20_000 });

  // لا كتالوجَ كاملاً عند الفتح — ولا حرفٌ واحد يخرج قبل أن يكتب المستخدم.
  expect(calls.productLookups).toHaveLength(0);
  await expect(brandField(page)).toHaveAttribute('placeholder', BRAND_PLACEHOLDER);

  await brandField(page).fill('TIRE');
  await expect.poll(() => calls.productLookups.length).toBeGreaterThan(0);
  const searched = lastQuery(calls.productLookups[calls.productLookups.length - 1]);
  expect(searched.get('search')).toBe('TIRE');
  // كل نداءٍ خرج حمل بحثاً — النداء العاري كان سيصطدم بحارس المحاكي (400).
  for (const call of calls.productLookups) {
    expect(lastQuery(call).get('search')).toBeTruthy();
  }

  await expect(optionsList(page).getByText('195/85/15 دانتير (دانتير)')).toBeVisible({ timeout: 20_000 });
  await expect(optionsList(page).getByText('TIRE-A · مقاس 195/85/15')).toBeVisible();

  // الاختيار يثبت اللافتة ويُشغّل التقرير بهذا البراند بعينه.
  await optionsList(page).getByText('195/85/15 دانتير (دانتير)').click();
  await expect(brandField(page)).toHaveValue('195/85/15 دانتير (دانتير)');
  await expect.poll(() => calls.runs.length).toBeGreaterThan(1);
  const pickedRun = lastQuery(calls.runs[calls.runs.length - 1]);
  expect(pickedRun.get('product')).toBe('7');
  expect(pickedRun.get('family_id')).toBeNull();

  // المسح يعيد الحقل إلى «الكل» صراحةً ويُشغّل التقرير بلا فلتر البراند.
  const clear = page.getByRole('button', { name: 'مسح الفلتر' });
  await expect(clear).toBeVisible();
  await clear.click();
  await expect(brandField(page)).toHaveValue('');
  await expect(brandField(page)).toHaveAttribute('placeholder', BRAND_PLACEHOLDER);
  await expect(clear).toHaveCount(0);
  await expect.poll(() => lastQuery(calls.runs[calls.runs.length - 1]).get('product')).toBeNull();
});

test('الموقوف يظهر بحثاً بلافتة «غير نشط» كما كان `<select>` يقول', async ({ page }) => {
  const calls = await setup(page);

  await page.goto('/reports/sales-by-product');
  await expect(page.getByText('مقاس 195/85/15')).toBeVisible({ timeout: 20_000 });

  await brandField(page).fill('قديم');
  await expect.poll(() => calls.productLookups.length).toBeGreaterThan(0);
  await expect(optionsList(page)).toContainText('195/85/15 قديم (دانتير) (غير نشط)');
});

test('فلتر «المنتج» يبحث عائلاتٍ باسمها ويُشغّل بـ`family_id`', async ({ page }) => {
  const calls = await setup(page);

  await page.goto('/reports/sales-by-product');
  await expect(page.getByText('مقاس 195/85/15')).toBeVisible({ timeout: 20_000 });

  await expect(familyField(page)).toHaveAttribute('placeholder', FAMILY_PLACEHOLDER);
  expect(calls.familyLookups).toHaveLength(0);

  await familyField(page).fill('مقاس');
  await expect.poll(() => calls.familyLookups.length).toBeGreaterThan(0);
  const searched = lastQuery(calls.familyLookups[calls.familyLookups.length - 1]);
  expect(searched.get('search')).toBe('مقاس');
  for (const call of calls.familyLookups) {
    expect(lastQuery(call).get('search')).toBeTruthy();
  }

  await optionsList(page).getByText('مقاس 195/85/15').click();
  await expect(familyField(page)).toHaveValue('مقاس 195/85/15');
  await expect.poll(() => calls.runs.length).toBeGreaterThan(1);
  const pickedRun = lastQuery(calls.runs[calls.runs.length - 1]);
  expect(pickedRun.get('family_id')).toBe('3');
  expect(pickedRun.get('product')).toBeNull();
});

test('سهم التوسيع يفتح البراندات', async ({ page }) => {
  await setup(page);

  await page.goto('/reports/sales-by-product');
  await expect(page.getByText('مقاس 195/85/15')).toBeVisible({ timeout: 20_000 });

  await page.getByRole('button', { name: 'افتح تفصيل السطر' }).first().click();

  const panel = page.locator('.ktra-sidepanel');
  await expect(panel.getByText('برندات هذا المنتج')).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByRole('cell', { name: 'TIRE-B', exact: true })).toBeVisible();
  await expect(panel.getByRole('cell', { name: 'أوتولوكس', exact: true })).toBeVisible();
});
