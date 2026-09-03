import { expect, test, type Page } from '@playwright/test';

/**
 * ISSUE #85 — شاشة الترميز الدفعي: ثلاثة صفوف بلوحة المفاتيح، اقتراحُ الحساب
 * من الطرف، تجاوزُه بلا سؤال، حفظٌ دفعيّ واحد، وصفٌّ خاطئ يبقى وحده.
 *
 * متابعة #85 — عمود «طريقة الدفع»: صفٌّ «على الحساب» وصفٌّ «نقد» في نفس
 * الحفظة، وكلاهما ينجح؛ صفّ النقد يحمل الصندوق الافتراضي المُستجلَب فعلاً.
 *
 * `test.setTimeout` صريحة — رحلةٌ متعدّدة الخطوات فوق تحميلٍ باردٍ لصفحة lazy
 * (نفس ملاحظة `e2e/office-client-book-door.spec.ts`).
 */

test.use({ serviceWorkers: 'block' });

const USER = {
  id: 'coding-user',
  name: 'محاسب الترميز',
  role: 'manager',
  email: 'coding@example.test',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true,
};

const ACCOUNTS = [
  { id: 501, code: '5203', name: 'كهرباء', parent: 52, account_type: 'Expense' },
  { id: 502, code: '5201', name: 'إيجار', parent: 52, account_type: 'Expense' },
];

const CURRENCIES = [{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل' }];

const PARTNERS = [{ id: 77, name: 'مورد الكهرباء' }];

const CODING_RULES = [{
  id: 9, partner: 77, partner_name: 'مورد الكهرباء',
  account: 501, account_name: 'كهرباء', account_code: '5203', updated_at: '2026-08-01T00:00:00Z',
}];

// متابعة #85: صندوق الشركة الافتراضي — يثبت أن صفّ «نقد» يُرفق به فعلاً لا
// بحدسٍ محلي في الاختبار وحده.
const CASH_BOXES = [{
  id: 1, external_id: 'box-1', name: 'الصندوق الرئيسي', currency_code: 'ILS',
  account_id: 601, account_code: '1101', is_default: true, is_active: true,
}];

const TENANT = {
  TenantID: 1, CompanyName: 'شركة اختبار الترميز', SubscriptionPlan: 'Enterprise',
  Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
  template: 'general', managed_by: null,
};

async function stub(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'coding-e2e-token');
    localStorage.setItem('userId', 'coding-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });

    if (path.endsWith('/hr/users/coding-user/')) return json(USER);
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1, tenant: TENANT, role: 'manager', is_default: true,
        created_at: '2026-01-01T00:00:00Z', can_access_import: false,
      }]);
    }
    if (path.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true,
        permissions: ['finance.expense.create', 'finance.revenue.create'],
        modules: {}, template: 'general', terms: {}, shell: null, ui_mode: 'advanced',
      });
    }
    if (path.endsWith('/accounting/accounts/')) return json(ACCOUNTS);
    if (path.endsWith('/accounting/currencies/')) return json(CURRENCIES);
    if (path.endsWith('/partners/lookup/')) return json(PARTNERS);
    if (path.endsWith('/accounting/coding-rules/')) return json(CODING_RULES);
    if (path.endsWith('/accounting/cash-box-accounts/')) return json(CASH_BOXES);
    if (path.includes('/accounting/expense-vouchers/') && path.endsWith('/unpost/')) {
      return json({ id: 1001, number: 1, is_posted: false });
    }
    if (path.endsWith('/accounting/vouchers/batch-save/') && request.method() === 'POST') {
      // الصفّان الأوّلان صحيحان، والثالث خاطئ عمداً — معيار القبول الأخير.
      return json({
        rows: [
          { index: 0, success: true, id: 1001, number: 1, direction: 'expense' },
          { index: 1, success: true, id: 1002, number: 2, direction: 'expense' },
          { index: 2, success: false, error: 'مبلغ المصروف يجب أن يكون أكبر من صفر.' },
        ],
        succeeded: 2, failed: 1,
      });
    }
    return json([]);
  });
}

test('ترميز دفعي: ثلاثة صفوف بلوحة المفاتيح، اقتراح وتجاوز، طريقتا دفع، حفظٌ واحد، وصفّ خاطئ يبقى وحده', async ({ page }) => {
  test.setTimeout(90_000);
  await stub(page);

  await page.goto('/accounting/document-coding');
  await expect(page.getByText('ترميز مستندات')).toBeVisible({ timeout: 30_000 });
  const grid = page.locator('.ktra-grid');
  await expect(grid).toBeVisible({ timeout: 30_000 });
  // انتظارُ وصول قواعد الترميز والأطراف فعلياً — تحميلٌ باردٌ لصفحة lazy قد
  // يترك الشبكة مرسومة قبل استقرار حالتها فتُخطئ أول كتابةٍ الاقتراح.
  await expect(page.locator('#ktra-coding-partners option[value="مورد الكهرباء"]')).toHaveCount(1, { timeout: 30_000 });

  const row = (i: number) => page.locator('.ktra-grid tbody tr').nth(i);

  // ── الصفّ الأول: بلوحة المفاتيح — طرفٌ بلا قاعدة ترميز سابقة (اسمٌ حرّ) ──
  // «طريقة الدفع» (العمود الثاني select) — بلوحة المفاتيح: تبديلٌ صريح عن
  // الافتراضي «نقد» إلى «على الحساب» عبر selectOption (لا نقر فأرة).
  await row(0).locator('select').nth(1).selectOption('on_account');
  await row(0).getByPlaceholder('اسم الطرف (اختياري)').fill('زبون مباشر');
  await row(0).getByPlaceholder('رقم الفاتورة/الإيصال').fill('F-1001');
  await row(0).getByPlaceholder('حساب المصروف/الإيراد').fill('5203 كهرباء');
  const amount0 = row(0).locator('input[type="number"]').first();
  await amount0.fill('100');
  // Enter تنزل صفّاً — تضيف الصفّ التالي تلقائياً وتنقل التركيز لعموده نفسه.
  await amount0.press('Enter');
  await expect(page.locator('.ktra-grid tbody tr')).toHaveCount(2, { timeout: 5000 });

  // ── الصفّ الثاني: اقتراح الحساب فور كتابة الطرف المرمَّز مسبقاً، وطريقة
  // الدفع «نقد» (الافتراضي) مُعاد اختيارها صراحةً بلوحة المفاتيح أيضاً ──
  await row(1).locator('select').nth(1).selectOption('cash');
  const accountInput1 = row(1).getByPlaceholder('حساب المصروف/الإيراد');
  await row(1).getByPlaceholder('اسم الطرف (اختياري)').fill('مورد الكهرباء');
  await expect(accountInput1).toHaveValue('5203 كهرباء');

  // تجاوز الاقتراح بلا سؤال ولا تحذير: كتابةٌ فوقه تُبدّل القيمة فوراً —
  // لو استُبدلت بحوارِ تأكيدٍ يعلّق الحالة لسقطت هذه المطابقة بمهلتها.
  await accountInput1.fill('5201 إيجار');
  await expect(accountInput1).toHaveValue('5201 إيجار');

  const docNumber1 = row(1).getByPlaceholder('رقم الفاتورة/الإيصال');
  await docNumber1.fill('F-1002');
  const amount1 = row(1).locator('input[type="number"]').first();
  await amount1.fill('200');
  await amount1.press('Enter');
  await expect(page.locator('.ktra-grid tbody tr')).toHaveCount(3, { timeout: 5000 });

  // ── الصفّ الثالث: سيرتدّه الخادم — لا مبلغ صالح ──
  await row(2).getByPlaceholder('رقم الفاتورة/الإيصال').fill('F-1003');

  // ── حفظٌ واحد للثلاثة معاً ──
  const saveRequest = page.waitForRequest((req) =>
    req.url().includes('/accounting/vouchers/batch-save/') && req.method() === 'POST');
  await page.getByRole('button', { name: 'حفظ', exact: true }).click();
  const request = await saveRequest;
  const body = request.postDataJSON() as {
    rows: Array<{ payment_method?: string; cash_or_bank_account?: number }>;
  };
  expect(body.rows).toHaveLength(3);

  // متابعة #85: صفٌّ «على الحساب» بلا صندوق، وصفٌّ «نقد» بصندوقه الافتراضي
  // المُستجلَب من الخادم — كلاهما في الحفظة نفسها.
  expect(body.rows[0].payment_method).toBe('on_account');
  expect(body.rows[0].cash_or_bank_account).toBeUndefined();
  expect(body.rows[1].payment_method).toBe('cash');
  expect(body.rows[1].cash_or_bank_account).toBe(601);

  // ── الصفّ الخاطئ يبقى وحده بعد الحفظ ──
  await expect(page.locator('.ktra-grid tbody tr')).toHaveCount(1, { timeout: 10_000 });
  await expect(page.locator('.ktra-grid tbody tr').first())
    .toContainText('مبلغ المصروف يجب أن يكون أكبر من صفر.');
  await expect(page.locator('.ktra-grid tbody tr').first().getByPlaceholder('رقم الفاتورة/الإيصال'))
    .toHaveValue('F-1003');

  // ── بلاغ المالك: «ما ببيّنو بنفس الصفحة» ──
  // الصفّان الناجحان مُسحا من الشبكة (صحيح: هي قائمةُ عملٍ لِما لم يُحفظ)،
  // والأثر الذي كان ناقصاً هو هذا السِجلّ — رقمُ كل سند وحسابه ومبلغه بلا
  // مغادرة الشاشة، وطريقُ تراجعٍ عن سطرٍ رُمِّز خطأً.
  const savedPanel = page.getByTestId('coding-saved-vouchers');
  await expect(savedPanel).toBeVisible({ timeout: 10_000 });
  await expect(savedPanel).toContainText('حُفظ في هذه الجلسة — 2 سند');
  await expect(page.getByTestId('coding-saved-expense:1001')).toContainText('#1');
  await expect(page.getByTestId('coding-saved-expense:1001')).toContainText('5203 كهرباء');
  // الصفّ الثاني تجاوز الاقتراح إلى «5201 إيجار» — السِجلّ يقول ما حُفظ فعلاً
  // لا ما اقترحه النظام، وهذا نصفُ فائدته.
  await expect(page.getByTestId('coding-saved-expense:1002')).toContainText('5201 إيجار');
  // والصفّ الفاشل لا يدخل السِجلّ — مكانه الشبكة برسالة خطئه (أعلاه).
  await expect(savedPanel.locator('tbody tr')).toHaveCount(2);
});

test('التراجع عن سندٍ رُمِّز خطأً — من نفس الشاشة، ويبقى مشطوباً لا يختفي', async ({ page }) => {
  test.setTimeout(90_000);
  await stub(page);

  await page.goto('/accounting/document-coding');
  const grid = page.locator('.ktra-grid');
  await expect(grid).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('#ktra-coding-partners option[value="مورد الكهرباء"]')).toHaveCount(1, { timeout: 30_000 });

  const row0 = page.locator('.ktra-grid tbody tr').nth(0);
  await row0.getByPlaceholder('رقم الفاتورة/الإيصال').fill('F-2001');
  await row0.getByPlaceholder('حساب المصروف/الإيراد').fill('5203 كهرباء');
  await row0.locator('input[type="number"]').first().fill('100');

  await page.getByRole('button', { name: 'حفظ', exact: true }).click();
  const saved = page.getByTestId('coding-saved-expense:1001');
  await expect(saved).toBeVisible({ timeout: 15_000 });

  // نقطةُ الإلغاء تُستدعى بالاتجاه الصحيح — سند **مصروف** لا إيراد.
  const unpost = page.waitForRequest((req) =>
    req.url().includes('/accounting/expense-vouchers/1001/unpost/') && req.method() === 'POST');
  await saved.getByRole('button', { name: /تراجع/ }).click();
  await page.getByRole('button', { name: 'ألغِ الترحيل' }).click();
  await unpost;

  // يبقى ظاهراً مشطوباً: اختفاؤه يُنسي المستخدمَ فعلَه فيعيد ترميز السند.
  await expect(saved).toBeVisible();
  await expect(saved).toContainText('أُلغي ترحيله');
  await expect(page.getByTestId('coding-saved-vouchers')).toContainText('حُفظ في هذه الجلسة — 0 سند');
});
