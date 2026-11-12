import { expect, test, type Page } from '@playwright/test';

/**
 * بلاغُ المالك على «دفتر العميل» — عيبانِ يُريان في المتصفّح وحده.
 *
 * `tsc` لا يفحص خصائص JSX في هذا المستودع (لا `@types/react`)، فشاشةٌ جديدة
 * تُصرَّف نظيفةً وقد لا تُركَّب أصلاً. هذه الرحلة هي البرهان الوحيد على أن
 * `RevenueVouchersPage` تُرسَم فعلاً بأعمدتها ونموذجها.
 *
 * ١. **سند الإيراد بلا شاشة**: نقاطه الثلاث في الخادم منذ #80 وبلا مستدعٍ —
 *    يُكتب من الترميز الدفعي ثم لا يُرى في أي قائمة.
 * ٢. **وضع «حساب من الشجرة إلزاماً»**: خانةُ «أو اسم إيراد جديد» تختفي حين
 *    يُلزم الإعداد — فلا يكتب المستخدم فيها ثم يردّه الخادم.
 *
 * (العيبُ الثالث — طريق الخروج من دفتر العميل — سقط مع دفاتر العملاء المُدارة
 * في #291، فحُذف اختباره.)
 *
 * `test.setTimeout` صريحة — تحميلٌ باردٌ لصفحة lazy.
 */

test.use({ serviceWorkers: 'block' });

const USER = {
  id: 'rev-user',
  name: 'محاسب الإيرادات',
  role: 'manager',
  email: 'rev@example.test',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true,
};

const ACCOUNTS = [
  { id: 601, code: '1101', name: 'النقدية', parent: 11, account_type: 'Asset', sub_type: 'cash_box' },
  { id: 701, code: '4210', name: 'عمولات محصّلة', parent: 42, account_type: 'Revenue' },
];

const CURRENCIES = [{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل' }];

const VOUCHERS = [{
  id: 11, number: 7, date: '2026-06-10',
  revenue_account: 701, revenue_account_name: 'عمولات محصّلة', revenue_account_code: '4210',
  amount: '500.00', tax_amount: '0.00', currency: 1, currency_code: 'ILS',
  exchange_rate: '1.000000', payment_method: 'cash',
  cash_or_bank_account: 601, cash_or_bank_account_name: 'النقدية',
  payer_partner: null, payer_partner_name: null, payer_name: 'شركة الأفق',
  description: 'عمولة وساطة', attachment_url: '', journal: 3, is_posted: true,
  created_at: '2026-06-10T09:00:00Z',
}];

const COMPANY = {
  TenantID: 1, CompanyName: 'مكتب المحاسبة', SubscriptionPlan: 'Pro',
  Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
  template: 'accounting_office',
};

type Options = { entryMode?: 'free' | 'linked' };

async function stub(page: Page, options: Options = {}) {
  const { entryMode = 'free' } = options;

  await page.addInitScript((activeTenant) => {
    localStorage.setItem('token', 'rev-e2e-token');
    localStorage.setItem('userId', 'rev-user');
    localStorage.setItem('tenantId', String(activeTenant));
  }, COMPANY.TenantID);

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });

    if (path.endsWith('/hr/users/rev-user/')) return json(USER);
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1, tenant: COMPANY, role: 'manager', is_default: true,
        created_at: '2026-01-01T00:00:00Z', can_access_import: false,
      }]);
    }
    if (path.endsWith('/tenants/settings/current/')) {
      return json({
        company_name_primary: COMPANY.CompanyName,
        voucher_account_entry_mode: entryMode,
      });
    }
    if (path.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true,
        permissions: ['finance.revenue.create', 'finance.revenue.unpost'],
        modules: {}, template: 'accounting_office',
        terms: {}, shell: null, ui_mode: 'advanced',
      });
    }
    if (path.endsWith('/accounting/revenue-vouchers/')) return json(VOUCHERS);
    if (path.endsWith('/accounting/accounts/')) return json(ACCOUNTS);
    if (path.endsWith('/accounting/currencies/')) return json(CURRENCIES);
    return json([]);
  });
}

test('سندات الإيراد: الشاشة تُرسَم بقائمتها ونموذجها — لا نقاطٌ خادميةٌ بلا مستدعٍ', async ({ page }) => {
  test.setTimeout(90_000);
  await stub(page);

  await page.goto('/accounting/revenue-vouchers');
  await expect(page.getByLabel('breadcrumb').getByText('سندات الإيراد')).toBeVisible({ timeout: 30_000 });

  // القائمة تعرض السند القادم من الخادم بحسابه ودافعه — لا جدولٌ فارغ.
  await expect(page.getByText('4210 — عمولات محصّلة')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('شركة الأفق')).toBeVisible();
  await expect(page.getByText('عمولة وساطة')).toBeVisible();
  // الترحيل مرئيّ، ومعه طريق التراجع الذي لم يكن موجوداً إلا من دفتر اليومية.
  await expect(page.getByRole('button', { name: /إلغاء الترحيل/ })).toBeVisible();

  // النموذج يُفتح ويحمل خانة الاسم الحرّ في الوضع الافتراضي.
  await page.getByRole('button', { name: 'سند إيراد جديد' }).click();
  await expect(page.getByRole('heading', { name: 'سند إيراد جديد' })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('أو اسم إيراد جديد')).toBeVisible();

  // ومعاينةُ القيد **مقلوبةُ الاتجاه** عن سند المصروف: الصندوق مدين.
  await page.getByRole('spinbutton').first().fill('500');
  await expect(page.getByText(/القيد:\s*Dr/)).toBeVisible({ timeout: 15_000 });
});

test('وضع «حساب من الشجرة إلزاماً» يُخفي خانة الاسم الحرّ', async ({ page }) => {
  test.setTimeout(90_000);
  await stub(page, { entryMode: 'linked' });

  await page.goto('/accounting/revenue-vouchers');
  await expect(page.getByLabel('breadcrumb').getByText('سندات الإيراد')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'سند إيراد جديد' }).click();
  await expect(page.getByRole('heading', { name: 'سند إيراد جديد' })).toBeVisible({ timeout: 15_000 });

  // حقل الشجرة يبقى؛ خانةُ الاسم الحرّ وحدها تختفي.
  await expect(page.getByText('حساب الإيراد — ماذا قُبض *')).toBeVisible();
  await expect(page.getByText('أو اسم إيراد جديد')).toHaveCount(0);
});
