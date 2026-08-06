import { test, expect, type Page } from '@playwright/test';

/**
 * T-EXTACCT — بلاغ المالك: «فتحت فاتورة مبيعات جديدة فتحت واجهة المحاسب القانوني».
 *
 * الحساب الذي له ملف محاسب مهني (`accountType = legal_accountant`) كان يفتح قشرة
 * المكتب لكل مسار، فالرابط يقول «فاتورة مبيعات» والشاشة تعرض «لوحة المكتب».
 */

const OFFICE_USER = {
  id: 'accountant-user',
  name: 'ثابت طعمه',
  role: 'manager',
  email: 'accountant@example.test',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true,
  accountType: 'legal_accountant',
  isSuperAdmin: true,
};

async function stubAccountantSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'accountant-shell-token');
    localStorage.setItem('userId', 'accountant-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.hostname === 'api.smart.ktragroup.com'
      || url.port === '8000'
      || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    let body: unknown = [];
    const path = url.pathname;
    if (path.endsWith('/hr/users/accountant-user/')) {
      body = OFFICE_USER;
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة النور', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = { role: 'manager', is_manager: true, permissions: [] };
    } else if (path.endsWith('/accounting/currencies/')) {
      body = [{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل', Symbol: '₪', IsBaseCurrency: true }];
    } else if (path.endsWith('/accountant/practice/overview/')) {
      body = {
        period_from: '2026-08-01', period_to: '2026-08-31', clients: [],
        totals: { clients: 0, vat_due: '0', profit: '0', draft_documents: 0, needs_attention: 0 },
      };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test('رابط فاتورة المبيعات يفتح شاشة الفاتورة لا لوحة المكتب', async ({ page }) => {
  await stubAccountantSession(page);
  await page.goto('/sales/invoices/new');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('لوحة المكتب')).toHaveCount(0);
  await expect(page.getByText('واجهة المحاسب القانوني', { exact: false })).toHaveCount(0);
  // شاشة الشركة التجارية هي التي تُعرض (الشريط الجانبي للشركة).
  await expect(page.getByText('فواتير المبيعات').first()).toBeVisible();
  expect(new URL(page.url()).pathname).toBe('/sales/invoices/new');
});

test('بيت المكتب يبقى للمكتب — لا تسرّب للقشرة التجارية', async ({ page }) => {
  await stubAccountantSession(page);
  await page.goto('/office');
  await page.waitForLoadState('networkidle');

  // علامة ثابتة في شريط المكتب (بلا انتظار بيانات) — والمهلة أطول لأن قشرة
  // المكتب تُحمَّل كسولاً (lazy chunk) وأول ترجمة في dev تتجاوز المهلة الافتراضية.
  await expect(page.getByText('مكتب المحاسبة القانونية').first()).toBeVisible({ timeout: 20000 });
});
