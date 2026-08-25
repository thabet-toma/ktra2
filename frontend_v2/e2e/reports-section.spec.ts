import { test, expect, type Page } from '@playwright/test';

/**
 * T-REPORTS2 — قسم التقارير: الفهرس يفتح التقرير، والتقرير يعرف مفتاحه.
 *
 * العطل الذي يثبّته هذا الاختبار: `App` مركّب على مسار splat (`/*`) بلا
 * `<Route>` فيه `:reportKey`، فكان `useParams()` يُرجع فارغاً وتطلب الشاشة
 * `/api/reports//` فتردّ 404 — أي أن كل تقرير في القسم كان يفتح على خطأ.
 * الاختبار يرصد كل نداءات الشبكة ويرفض أي نداء بمفتاح فارغ.
 */

const CATALOG = {
  categories: [
    {
      key: 'sales',
      label: 'المبيعات',
      reports: [
        {
          key: 'sales-invoices',
          title: 'سجل فواتير البيع',
          description: 'كل فاتورة بيع مرحّلة في الفترة.',
          permission: null,
          screen_path: null,
          row_link: '/sales/invoices/{id}',
          filters: [
            { key: 'from', label: 'من تاريخ', kind: 'date', options: [], default: null },
            { key: 'to', label: 'إلى تاريخ', kind: 'date', options: [], default: null },
          ],
          columns: [
            { key: 'invoice_number', header: 'رقم المستند', kind: 'text', total: false, width: null },
            { key: 'grand_total', header: 'الإجمالي', kind: 'money', total: true, width: null },
          ],
        },
      ],
    },
  ],
};

const RESULT = {
  key: 'sales-invoices',
  title: 'سجل فواتير البيع',
  category: 'sales',
  description: 'كل فاتورة بيع مرحّلة في الفترة.',
  row_link: '/sales/invoices/{id}',
  columns: CATALOG.categories[0].reports[0].columns,
  rows: [
    { id: 7, invoice_number: 'SI-0007', grand_total: '150.00' },
    { id: 8, invoice_number: 'SI-0008', grand_total: '250.00' },
  ],
  totals: { grand_total: '400.00' },
  total_rows: 2,
  truncated: false,
  generated_at: '2026-08-10T10:00:00',
};

/** كل نداءات `/api/` التي خرجت من الصفحة — لكشف المفتاح الفارغ. */
const setup = async (page: Page) => {
  const calls: string[] = [];
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
    calls.push(url.pathname);

    let body: unknown = [];
    const path = url.pathname;
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
      body = CATALOG;
    } else if (path.endsWith('/api/reports/sales-invoices/')) {
      body = RESULT;
    } else if (path === '/api/reports//') {
      // المفتاح الفارغ — كما كان الخادم يردّ قبل الإصلاح.
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{"error":"تقرير غير معروف."}' });
      return;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return calls;
};

test('فهرس التقارير يفتح التقرير بمفتاحه لا بمفتاح فارغ', async ({ page }) => {
  const calls = await setup(page);

  await page.goto('/reports');
  await expect(page.getByText('سجل فواتير البيع')).toBeVisible({ timeout: 20_000 });

  await page.getByText('سجل فواتير البيع').first().click();
  await expect(page).toHaveURL(/\/reports\/sales-invoices$/, { timeout: 20_000 });

  // العقد: صفوف التقرير تُعرض، وسطر الإجمالي معها — لا لافتة خطأ.
  await expect(page.getByText('SI-0007')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('SI-0008')).toBeVisible();
  await expect(page.locator('.ktra-banner--err')).toHaveCount(0);

  expect(calls.filter((c) => c === '/api/reports//')).toHaveLength(0);
  expect(calls.filter((c) => c === '/api/reports/sales-invoices/').length).toBeGreaterThan(0);
});

test('فتح التقرير مباشرةً من الرابط يقرأ المفتاح من المسار', async ({ page }) => {
  const calls = await setup(page);

  await page.goto('/reports/sales-invoices');
  await expect(page.getByText('SI-0007')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.ktra-banner--err')).toHaveCount(0);
  expect(calls.filter((c) => c === '/api/reports//')).toHaveLength(0);
});

/**
 * T-DIM — التنقيب: نقر السطر يفتح الحركات التي كوّنته، والمقارنة معروضة.
 *
 * ما يُثبَت هنا سلوكُ الشاشة: هل تُرسِل مفاتيح الصفّ كما أعلنها الخادم مع
 * **نفس** فلاتر التشغيل؟ وهل تقول للمستخدم إن المجموع طابق الرقم أم خالفه؟
 * (صحّة الرقمين نفسها يثبتها `core/tests/test_reports_stock_dimension.py`.)
 */
const DIM_COLUMNS = [
  { key: 'dim_label', header: 'المورد', kind: 'text', total: false, width: null },
  { key: 'sku', header: 'الرمز', kind: 'text', total: false, width: null },
  { key: 'product_name', header: 'الصنف', kind: 'text', total: false, width: null },
  { key: 'qty_in', header: 'الوارد', kind: 'number', total: true, width: null },
  { key: 'qty_out', header: 'الصادر', kind: 'number', total: true, width: null },
];

const DIM_DRILL_COLUMNS = [
  { key: 'movement_date', header: 'التاريخ', kind: 'date', total: false, width: null },
  { key: 'document', header: 'المستند', kind: 'text', total: false, width: null },
  { key: 'qty_in', header: 'الوارد', kind: 'number', total: true, width: null },
  { key: 'qty_out', header: 'الصادر', kind: 'number', total: true, width: null },
];

const DIM_SUMMARY = {
  key: 'stock-by-dimension',
  title: 'حركة المخزون حسب بُعد',
  description: 'ما دخل وما خرج وبكم.',
  permission: null,
  screen_path: null,
  row_link: null,
  filters: [
    { key: 'from', label: 'من تاريخ', kind: 'date', options: [], default: null },
    { key: 'to', label: 'إلى تاريخ', kind: 'date', options: [], default: null },
    {
      key: 'group_by', label: 'جمِّع حسب', kind: 'select',
      options: [{ value: 'supplier', label: 'المورد' }, { value: 'customer', label: 'الزبون' }],
      default: 'supplier',
    },
  ],
  columns: DIM_COLUMNS,
};

const DIM_RESULT = {
  key: 'stock-by-dimension',
  title: 'حركة المخزون حسب بُعد',
  category: 'inventory',
  description: 'ما دخل وما خرج وبكم.',
  row_link: null,
  drill: {
    title: 'الحركات المكوِّنة للسطر',
    keys: ['dim_key', 'row_product'],
    columns: DIM_DRILL_COLUMNS,
  },
  columns: DIM_COLUMNS,
  rows: [
    {
      dim_label: 'مورد ألف', sku: 'LAP', product_name: 'لابتوب',
      qty_in: '5', qty_out: '1', dim_key: '3', row_product: '9',
    },
  ],
  totals: { qty_in: '5', qty_out: '1' },
  total_rows: 1,
  truncated: false,
  generated_at: '2026-08-10T10:00:00',
};

const DIM_DRILL_RESULT = {
  key: 'stock-by-dimension',
  title: 'الحركات المكوِّنة للسطر',
  columns: DIM_DRILL_COLUMNS,
  rows: [
    { movement_date: '2026-06-10', document: 'فاتورة شراء #11', qty_in: '3', qty_out: '0' },
    { movement_date: '2026-06-12', document: 'فاتورة شراء #12', qty_in: '2', qty_out: '0' },
    { movement_date: '2026-06-15', document: 'مرتجع خارج #13', qty_in: '0', qty_out: '1' },
  ],
  totals: { qty_in: '5', qty_out: '1' },
  total_rows: 3,
  truncated: false,
};

const setupDim = async (page: Page) => {
  const drillCalls: string[] = [];
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
      // الفهرس يحمل فلاتر التقرير — منه تبني الشاشة قيمها الابتدائية، وبدونه
      // يُشغَّل التقرير بلا نطاق فلا يبقى ما يُثبَت أن التنقيب يرثه.
      body = { categories: [{ key: 'inventory', label: 'المخزون', reports: [DIM_SUMMARY] }] };
    } else if (path.endsWith('/api/reports/stock-by-dimension/drill/')) {
      drillCalls.push(url.search);
      body = DIM_DRILL_RESULT;
    } else if (path.endsWith('/api/reports/stock-by-dimension/')) {
      body = DIM_RESULT;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return drillCalls;
};

test('التنقيب: نقر السطر يفتح حركاته ويقول إن المجموع يطابق الرقم', async ({ page }) => {
  const drillCalls = await setupDim(page);

  await page.goto('/reports/stock-by-dimension');
  await expect(page.getByText('مورد ألف')).toBeVisible({ timeout: 20_000 });

  await page.getByText('مورد ألف').first().click();

  // اللوحة فتحت على الحركات المكوِّنة، وهويّة السطر مكتوبة عليها.
  await expect(page.getByText('الحركات المكوِّنة للسطر')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('مورد ألف — LAP — لابتوب')).toBeVisible();
  await expect(page.getByText('فاتورة شراء #11')).toBeVisible();
  await expect(page.getByText('مرتجع خارج #13')).toBeVisible();

  // المقارنة معروضة صراحةً: رقم السطر ومعه علامة التطابق.
  await expect(page.getByTitle('مجموع الحركات يساوي رقم السطر').first()).toBeVisible();
  await expect(page.getByTitle('مجموع الحركات يخالف رقم السطر')).toHaveCount(0);

  // العقد مع الخادم: مفاتيح الصفّ **ومعها** فلاتر التشغيل نفسها.
  expect(drillCalls.length).toBeGreaterThan(0);
  const sent = new URLSearchParams(drillCalls[drillCalls.length - 1]);
  expect(sent.get('dim_key')).toBe('3');
  expect(sent.get('row_product')).toBe('9');
  expect(sent.get('from')).toBeTruthy();
  expect(sent.get('to')).toBeTruthy();
});
