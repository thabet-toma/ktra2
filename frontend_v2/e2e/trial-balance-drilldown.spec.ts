import { test, expect, type Page } from '@playwright/test';

/**
 * A1 (THA-195) — التنقيب من ميزان المراجعة إلى المستند المصدر بثلاث نقرات.
 *
 * ما كان مكسوراً: صفوف ميزان المراجعة بلا نقر أصلاً، ورقم القيد في الأستاذ العام
 * نصّ جامد (`#5`). فكان الرقم في الميزان طريقاً مسدوداً — أول ما يختبر به محاسبٌ
 * أيَّ نظام. هذا الاختبار يمشي الطريق كاملاً ويعدّ النقرات: ثلاث، لا أكثر.
 */

const ACCOUNT_ID = 41;
const JOURNAL_ID = 5;
const INVOICE_ID = 12;

const TRIAL_BALANCE = {
  start_date: '2026-01-01',
  end_date: '2026-08-14',
  rows: [
    {
      id: ACCOUNT_ID, code: '1103', name: 'ذمم العملاء', account_type: 'أصول',
      total_debit: 1500, total_credit: 0, balance: 1500,
      period_debit: 1500, period_credit: 0,
      closing_debit: 1500, closing_credit: 0,
    },
  ],
  totals: {
    period_debit: 1500, period_credit: 0, closing_debit: 1500, closing_credit: 0,
    balanced: true, period_difference: 0, closing_difference: 0,
  },
};

const GENERAL_LEDGER = {
  account_code: '1103',
  account_name: 'ذمم العملاء',
  opening_balance: 0,
  closing_balance: 1500,
  transactions: [
    {
      journal_id: JOURNAL_ID, date: '2026-08-10', description: 'فاتورة مبيعات SI-0012',
      debit: 1500, credit: 0, balance: 1500,
    },
  ],
};

const JOURNAL = {
  id: JOURNAL_ID,
  transaction_date: '2026-08-10',
  description: 'فاتورة مبيعات SI-0012',
  reference_type: 'SALES_INVOICE',
  reference_id: INVOICE_ID,
  reference_summary: 'فاتورة مبيعات SI-0012 — عميل تجريبي',
  is_posted: true,
  currency: 1,
  currency_code: 'SYP',
  exchange_rate: '1',
  lines: [
    { id: 1, account: ACCOUNT_ID, debit: '1500.00', credit: '0.00', description: 'ذمم العملاء' },
    { id: 2, account: 90, debit: '0.00', credit: '1500.00', description: 'إيرادات المبيعات' },
  ],
};

/** المستند المصدر في نهاية الطريق — أدنى ما تحتاجه شاشة الفاتورة لتُرسَم. */
const SALES_INVOICE = {
  id: INVOICE_ID,
  invoice_number: 'SI-0012',
  invoice_date: '2026-08-10',
  customer: 3,
  customer_name: 'عميل تجريبي',
  is_posted: true,
  status: 'posted',
  currency: 1,
  currency_code: 'SYP',
  exchange_rate: '1',
  subtotal: '1500.00',
  tax_total: '0.00',
  grand_total: '1500.00',
  lines: [
    {
      id: 1, product: 1, product_name: 'صنف تجريبي', quantity: '1',
      unit_price: '1500.00', line_total: '1500.00',
    },
  ],
};

const ACCOUNTS = [
  { id: ACCOUNT_ID, code: '1103', name: 'ذمم العملاء', account_type: 'أصول', is_active: true, parent: null },
  { id: 90, code: '4101', name: 'إيرادات المبيعات', account_type: 'إيرادات', is_active: true, parent: null },
];

const setup = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'drilldown-e2e-token');
    localStorage.setItem('userId', 'drilldown-e2e-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('lastActivityAt', String(Date.now()));
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;

    let body: unknown = [];
    if (path.endsWith('/hr/users/drilldown-e2e-user/')) {
      body = {
        id: 'drilldown-e2e-user', name: 'Drilldown Tester', role: 'manager',
        email: 'drill@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة التنقيب', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      // `can()` يقرأ القائمة حرفياً (لا استثناء للمدير) — فبقائمة فارغة تسقط
      // شاشة الفاتورة إلى لوحة التحكم وتبدو القفزة الثالثة مكسورة وهي سليمة.
      body = {
        role: 'manager', is_manager: true,
        permissions: ['accounting.report.view', 'accounting.journal.view',
                      'accounting.journal.create', 'sales.invoice.view'],
      };
    } else if (path.endsWith('/accounting/trial-balance/')) {
      body = TRIAL_BALANCE;
    } else if (path.endsWith('/accounting/general-ledger/')) {
      body = GENERAL_LEDGER;
    } else if (path.endsWith('/accounting/accounts/')) {
      body = ACCOUNTS;
    } else if (path.endsWith('/accounting/currencies/')) {
      body = [{ CurrencyID: 1, Code: 'SYP', IsBaseCurrency: true }];
    } else if (path.endsWith(`/accounting/journals/${JOURNAL_ID}/`)) {
      body = JOURNAL;
    } else if (path.endsWith(`/sales/invoices/${INVOICE_ID}/`)) {
      body = SALES_INVOICE;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
};

test('من ميزان المراجعة إلى الفاتورة في ثلاث نقرات', async ({ page }) => {
  await setup(page);

  // ── الشاشة: ميزان المراجعة ──
  await page.goto('/accounting/trial-balance');
  const accountRow = page.getByRole('row').filter({ hasText: 'ذمم العملاء' });
  await expect(accountRow).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/a1-1-trial-balance.png', fullPage: true });

  // ── النقرة الأولى: صف الحساب ← الأستاذ العام مفلتراً عليه ──
  await accountRow.click();
  await expect(page).toHaveURL(/\/accounting\/general-ledger$/, { timeout: 20_000 });
  // الكشف نفسه مُحمَّل، لا حقل الحساب وحده: الرصيد الختامي سطر لا يظهر قبل الجلب.
  await expect(page.getByText(/رصيد ختامي/)).toBeVisible({ timeout: 20_000 });
  const journalLink = page.getByRole('button', { name: `#${JOURNAL_ID}` });
  await expect(journalLink).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/a1-2-general-ledger.png', fullPage: true });

  // ── النقرة الثانية: رقم القيد ← القيد نفسه ──
  await journalLink.click();
  await expect(page).toHaveURL(new RegExp(`/accounting/journals/${JOURNAL_ID}$`), { timeout: 20_000 });
  await expect(page.getByText(/مصدر القيد:/)).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/a1-3-journal.png', fullPage: true });

  // ── النقرة الثالثة: «فتح المستند» ← الفاتورة المصدر ──
  const sourceLink = page.getByRole('button', { name: /فتح المستند/ });
  await expect(sourceLink).toBeVisible({ timeout: 20_000 });
  await sourceLink.click();
  await expect(page).toHaveURL(new RegExp(`/sales/invoices/${INVOICE_ID}$`), { timeout: 20_000 });
  // شاشة الفاتورة محمَّلة فعلاً: `toHaveURL` وحدها تمرّ قبل أن تصل حزمة الشاشة الكسولة.
  await expect(page.getByText(/مصدر القيد:/)).toBeHidden({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/a1-4-source-invoice.png', fullPage: true });
});

test('الرجوع من القيد يعيد الأستاذ العام على الحساب نفسه لا على شاشة فارغة', async ({ page }) => {
  await setup(page);

  await page.goto('/accounting/trial-balance');
  await page.getByRole('row').filter({ hasText: 'ذمم العملاء' }).click();
  await expect(page.getByRole('button', { name: `#${JOURNAL_ID}` })).toBeVisible({ timeout: 20_000 });

  await page.getByRole('button', { name: `#${JOURNAL_ID}` }).click();
  await expect(page).toHaveURL(new RegExp(`/accounting/journals/${JOURNAL_ID}$`), { timeout: 20_000 });

  // «خروج» كان يعيد إلى دفتر اليومية — وهي شاشة لم يأتِ منها المستخدم أصلاً.
  // (الاسم مقيَّد بشريط أدوات المستند: «تسجيل الخروج» في الشريط العلوي يطابقه جزئياً.)
  await page.getByRole('toolbar').getByRole('button', { name: 'خروج', exact: true }).click();
  await expect(page).toHaveURL(/\/accounting\/general-ledger$/, { timeout: 20_000 });
  await expect(page.getByRole('button', { name: `#${JOURNAL_ID}` })).toBeVisible({ timeout: 20_000 });
});
