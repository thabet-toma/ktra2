import { test, expect } from '@playwright/test';

test('New Customer Payment modal selects default cash account from purchase settings', async ({ page }) => {
  const requestedPaths: string[] = [];

  await page.addInitScript(() => {
    localStorage.setItem('token', 'default-cash-account-e2e-token');
    localStorage.setItem('userId', 'default-cash-account-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.hostname === 'api.smart.ktragroup.com'
      || url.port === '8000'
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
  await expect.poll(() => requestedPaths).toContain('/api/sales/settings/current/');
  await expect.poll(() => requestedPaths).toContain('/api/logistics/purchase-settings/current/');

  await page.getByRole('button', { name: 'دفعة جديدة', exact: true }).click();

  const cashSelect = page.getByText('الصندوق / البنك *', { exact: true })
    .locator('..')
    .locator('select');
  await expect(cashSelect).toHaveValue('412');
  await expect(cashSelect.locator('option:checked')).toHaveText('110002 الصندوق الافتراضي للاختبار');
});
