import { test, expect, type Page } from '@playwright/test';

/**
 * T-BANKS / T-JRNLUX — دليلان بصريان على شكوى المالك:
 *  1) القيد يبدأ بسطرين لا ثلاثة، والبيان يتولد من الحسابات تلقائياً.
 *  2) شاشة البنوك موجودة فعلاً وتعرض البنوك والفروع والحسابات البنكية.
 */

const ACCOUNTS = [
  { id: 11, code: '1101', name: 'النقدية (Cash)', account_type: 'Asset', is_active: true },
  { id: 41, code: '4101', name: 'مبيعات المنتجات', account_type: 'Revenue', is_active: true },
];

const BANKS = [
  {
    id: 1, name: 'بنك فلسطين', code: null, swift_code: 'PALSPS22', country: null,
    notes: null, is_active: true, accounts_count: 1,
    branches: [
      { id: 5, bank: 1, name: 'فرع رام الله', branch_code: '902', address: null, phone: null, is_active: true },
    ],
  },
];

const BANK_ACCOUNTS = [
  {
    id: 3, bank: 1, bank_name: 'بنك فلسطين', branch: 5, branch_name: 'فرع رام الله',
    name: 'جاري شيكل', account_number: '12345', iban: null, currency: 1, currency_code: 'ILS',
    account: 900, account_code: '1102K0001', is_default: true, is_active: true,
    notes: null, balance: '1500.00',
  },
];

async function stubApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'banks-e2e-token');
    localStorage.setItem('userId', 'banks-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000'
      || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    let body: unknown = [];
    const path = url.pathname;
    if (path.endsWith('/hr/users/banks-e2e-user/')) {
      body = {
        id: 'banks-e2e-user', name: 'Banks Tester', role: 'manager',
        email: 'banks@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة البنوك', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = { role: 'manager', is_manager: true, permissions: [] };
    } else if (path.endsWith('/accounting/accounts/')) {
      body = ACCOUNTS;
    } else if (path.endsWith('/accounting/currencies/')) {
      body = [{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل', Symbol: '₪', IsBaseCurrency: true }];
    } else if (path.endsWith('/accounting/banks/')) {
      body = BANKS;
    } else if (path.endsWith('/accounting/bank-accounts/')) {
      body = BANK_ACCOUNTS;
    } else if (path.endsWith('/accounting/bank-branches/')) {
      body = BANKS[0].branches;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test('قيد جديد يبدأ بسطرين ويولّد البيان من الحسابات', async ({ page }) => {
  await stubApi(page);
  await page.goto('/accounting/journals/new');
  await page.waitForLoadState('networkidle');

  // سطران فقط في شبكة القيد (كان ثلاثة).
  const accountCells = page.locator('.aseel-cell-picker');
  await expect(accountCells).toHaveCount(2);

  // البيان الإجمالي يبدأ فارغاً ومعلّماً «تلقائي».
  const narration = page.locator('input[placeholder="يتولد تلقائياً: من ح/ … إلى ح/ …"]');
  await expect(narration).toHaveValue('');
  await expect(page.getByText('البيان الإجمالي (تلقائي)')).toBeVisible();

  // اختيار حساب مدين من الفهرس + مبلغ.
  await accountCells.first().click();
  await page.locator('.aseel-picker tbody tr', { hasText: '1101' }).first().dblclick();
  await page.locator('input[data-side="debit"][data-line-idx="0"]').fill('500');

  // اختيار حساب دائن + مبلغ.
  await page.locator('.aseel-cell-picker').nth(1).click();
  await page.locator('.aseel-picker tbody tr', { hasText: '4101' }).first().dblclick();
  await page.locator('input[data-side="credit"][data-line-idx="1"]').fill('500');

  // البيان تولّد بصيغة «من ح/ … إلى ح/ …» بلا كتابة يدوية.
  await expect(narration).toHaveValue('من ح/ النقدية إلى ح/ مبيعات المنتجات');

  // وبيان كل سطر يتبع حسابه هو (لا يكرّر صيغة «من ح/ … إلى ح/ …»).
  const grid = page.locator('.aseel-grid tbody tr');
  await expect(grid.nth(0).locator('input').first()).toHaveValue('النقدية');
  await expect(grid.nth(1).locator('input').first()).toHaveValue('مبيعات المنتجات');

  // كتابة بيان إجمالي يدوي تنتقل إلى السطور، وتفريغه يعيد التوليد التلقائي.
  await narration.fill('تحصيل دفعة نقدية');
  await expect(grid.nth(0).locator('input').first()).toHaveValue('تحصيل دفعة نقدية');
  await narration.fill('');
  await expect(narration).toHaveValue('من ح/ النقدية إلى ح/ مبيعات المنتجات');
});

test('شاشة البنوك تعرض البنوك والفروع والحسابات البنكية', async ({ page }) => {
  await stubApi(page);
  await page.goto('/accounting/banks');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('البنوك وفروعها').first()).toBeVisible();
  await expect(page.getByText('بنك فلسطين').first()).toBeVisible();

  await page.getByRole('tab', { name: 'الفروع', exact: true }).click();
  await expect(page.getByText('فرع رام الله').first()).toBeVisible();

  await page.getByRole('tab', { name: 'الحسابات البنكية', exact: true }).click();
  await expect(page.getByText('جاري شيكل').first()).toBeVisible();
  // حساب الشجرة المُنشأ تلقائياً تحت «1102 البنوك» ظاهر في الجدول.
  await expect(page.getByText('1102K0001').first()).toBeVisible();
});
