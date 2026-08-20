/**
 * THA-131 — فاتورة المبيعات: موضع قائمة الزبائن، وحالة الدفع المشتقّة.
 *
 * معيار المالك حرفياً: «فتح قائمة الزبائن في شاشة الفاتورة يعرضها محاذيةً يمين
 * الحقل، وإزالة التأشير عن «نقدي» يُظهر تاريخ الاستحقاق ويُخفي الصندوق فوراً
 * بلا حفظ.» — الشرطان مُختبَران هنا، كلٌّ في اختباره.
 *
 * الخادم مُقنَّع بالكامل: هذه الشاشة واجهةٌ خالصة في هذا المسار (لا حفظ ولا
 * ترحيل)، والمقنَّع يجعل الاختبار حاسماً بلا قاعدة بيانات.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** يفتح محرّر فاتورة مبيعات جديدة على افتراضاتٍ محلولة (نقدية + صندوق 10). */
const openNewInvoice = async (page: Page, uiMode: 'simple' | 'advanced' = 'advanced') => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'payment-type-token');
    localStorage.setItem('userId', 'payment-type-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/payment-type-user/')) {
      return json({
        id: 'payment-type-user', name: 'مختبِر حالة الدفع', role: 'manager',
        email: 'payment-type@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاختبار', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: uiMode,
        permissions: ['sales.invoice.view', 'sales.invoice.create', 'sales.customer.view'],
      });
    }
    if (url.pathname.endsWith('/accounting/currencies/')) {
      return json([{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل' }]);
    }
    if (url.pathname.endsWith('/accounting/accounts/')) {
      return json([
        { id: 10, code: '1101', name: 'الصندوق الرئيسي', account_type: 'Asset' },
        { id: 40, code: '4101', name: 'إيراد المبيعات', account_type: 'Revenue' },
      ]);
    }
    if (url.pathname.endsWith('/sales/settings/current/')) {
      return json({
        default_customer: null, default_currency: 1, default_payment_type: 'cash',
        default_cash_account: 10, default_revenue_account_product: 40,
        stock_on_post_default: true, default_vat_rate: null,
        prices_include_tax: false, auto_post_invoices: false,
        show_journal_preview: true,
      });
    }
    if (url.pathname.endsWith('/partners/lookup/')) {
      return json([
        { id: 8, name: 'زبون الاختبار', partner_type: 'Customer' },
        { id: 9, name: 'زبون آخر', partner_type: 'Customer' },
      ]);
    }
    if (url.pathname.endsWith('/sales/invoices/')) {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    return json([]);
  });
  await page.goto('/sales/invoices/new');
  // رأس التحرير — لا القائمة ولا العرض المستندي.
  await expect(page.getByText('بحث سريع / باركود (F6)', { exact: true }))
    .toBeVisible({ timeout: 15000 });
};

const paidBox = (page: Page) => page.getByRole('checkbox', { name: 'نقدي' });
const badge = (page: Page) => page.getByTestId('invoice-payment-type-badge');

test('قائمة الزبائن تُحاذي بداية السطر — يمين الشاشة في RTL لا يسارها', async ({ page }) => {
  await openNewInvoice(page);

  await page.getByPlaceholder('اختر عميلاً...').click();
  const picker = page.locator('.aseel-picker');
  await expect(picker).toBeVisible();
  await expect(page.getByText('فهرس الحسابات — العملاء', { exact: true })).toBeVisible();

  const box = (await picker.boundingBox())!;
  // `clientWidth` لا `viewportSize` — الأول يستبعد شريط التمرير كما يفعل
  // `position: fixed`، فلا يكسر الاختبارَ عرضُ شريطٍ يختلف بين البيئات.
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  // ملتصقةٌ بالحافة اليمنى — أي بداية السطر في صفحةٍ اتجاهها RTL.
  expect(Math.abs(box.x + box.width - clientWidth)).toBeLessThanOrEqual(1);
  // وليست على اليسار: بدايتها بعد منتصف الشاشة.
  expect(box.x).toBeGreaterThan(clientWidth / 2);
});

test('إزالة التأشير عن «نقدي» تُظهر الاستحقاق وتُخفي الصندوق فوراً بلا حفظ', async ({ page }) => {
  await openNewInvoice(page);

  // الحالة الافتتاحية: الإعدادات تقول نقدية.
  await expect(paidBox(page)).toBeChecked();
  await expect(badge(page)).toHaveText('نقدي');
  await expect(page.getByText('الصندوق', { exact: true })).toBeVisible();
  await expect(page.getByText('استحقاق', { exact: true })).toHaveCount(0);

  // إزالة التأشير — ولا نداء حفظ واحد بينهما.
  const saveCalls: string[] = [];
  page.on('request', (r) => {
    if (r.method() !== 'GET' && new URL(r.url()).pathname.includes('/sales/invoices')) {
      saveCalls.push(r.url());
    }
  });
  await paidBox(page).uncheck();

  await expect(badge(page)).toHaveText('آجل');
  await expect(page.getByText('استحقاق', { exact: true })).toBeVisible();
  await expect(page.getByText('الصندوق', { exact: true })).toHaveCount(0);
  expect(saveCalls).toEqual([]);

  // والعودة تعكس الحالتين — لا اتجاه واحد.
  await paidBox(page).check();
  await expect(badge(page)).toHaveText('نقدي');
  await expect(page.getByText('الصندوق', { exact: true })).toBeVisible();
  await expect(page.getByText('استحقاق', { exact: true })).toHaveCount(0);
});

test('الوضع السهل يُبقي الشارة ويطوي الصندوق — والآجلة تُظهر الاستحقاق', async ({ page }) => {
  await openNewInvoice(page, 'simple');

  // الشارة ليست حقلاً بل حالةٌ تُقرأ — تبقى تحت القناع. والصندوق حقلٌ متقدّم
  // افتراضُه محلول، فيطويه القناع كما يطوي العملة.
  await expect(badge(page)).toHaveText('نقدي');
  await expect(page.getByText('الصندوق', { exact: true })).toHaveCount(0);

  await paidBox(page).uncheck();
  await expect(badge(page)).toHaveText('آجل');
  await expect(page.getByText('استحقاق', { exact: true })).toBeVisible();
});
