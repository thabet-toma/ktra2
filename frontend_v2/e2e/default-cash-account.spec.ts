import { test, expect } from '@playwright/test';
import { managerPermissionsBody } from './manager-permissions';

test('New Customer Payment modal selects default cash account from purchase settings', async ({ page }) => {
  const requestedPaths: string[] = [];

  await page.addInitScript(() => {
    localStorage.setItem('token', 'default-cash-account-e2e-token');
    localStorage.setItem('userId', 'default-cash-account-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000'
      || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    requestedPaths.push(url.pathname);
    let body: unknown = [];
    if (url.pathname.endsWith('/hr/users/default-cash-account-e2e-user/')) {
      body = {
        id: 'default-cash-account-e2e-user',
        name: 'Default Cash Account Tester',
        role: 'manager',
        email: 'default-cash-account@example.test',
        employmentStatus: 'active',
        isApproved: true,
        isEmailVerified: true,
      };
    } else if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      // بلا عضويةٍ يقف التطبيق على «لنُنشئ شركتك الأولى» فلا تُرسم الشاشة أصلاً.
      body = [{
        id: 1, role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
        tenant: {
          TenantID: 1, CompanyName: 'Default Cash Co', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
          template: 'general', managed_by: null,
        },
      }];
    } else if (url.pathname.endsWith('/permissions/me/')) {
      // مجموعةُ مديرٍ كاملة لا `[]`: الشاشة محروسة بـ`sales.payment.create`
      // (`utils/viewPermissions.ts`)، والفراغ يمنعها بصمت.
      body = managerPermissionsBody();
    } else if (url.pathname.endsWith('/accounting/accounts/')) {
      body = [
        { id: 411, code: '110001', name: 'صندوق احتياطي', account_type: 'cash' },
        { id: 412, code: '110002', name: 'الصندوق الافتراضي للاختبار', account_type: 'cash' },
      ];
    } else if (url.pathname.endsWith('/accounting/currencies/')) {
      body = [{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل' }];
    } else if (url.pathname.endsWith('/sales/settings/current/')) {
      // Force the page to exercise its documented purchase-settings fallback.
      body = { default_cash_account: null };
    } else if (url.pathname.endsWith('/logistics/purchase-settings/current/')) {
      body = {
        purchase_default_price_strategy: 'last_purchase',
        default_cash_account: 412,
      };
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  await page.goto('/sales/customer-payments');
  await expect.poll(() => requestedPaths, { timeout: 30_000 }).toContain('/api/sales/settings/current/');
  await expect.poll(() => requestedPaths).toContain('/api/logistics/purchase-settings/current/');

  // زرُّ شريط الأدوات في `SalesCustomerPaymentsPage.tsx` (`actions` — المفتاح `new`).
  await page.getByRole('button', { name: 'سند قبض جديد (Ctrl+Ins)', exact: true }).click();

  // حقلُ الصندوق صار `AccountTreeField` (زرٌّ يفتح شجرة الحسابات) لا `<select>`:
  // نصُّ الزرّ هو الحساب المختار (`accountLabel` — «الرمز — الاسم»). اسمُه
  // المتاح يأتي من `<label>` المحيط لا من نصّه، فالتأكيدُ على النصّ نفسه.
  const cashButton = page.getByText('الصندوق / البنك *', { exact: true })
    .locator('..')
    .locator('button.ktra-input');
  await expect(cashButton).toHaveText('110002 — الصندوق الافتراضي للاختبار');
});
