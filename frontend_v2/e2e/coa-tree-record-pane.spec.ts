import { test, expect, type Page } from '@playwright/test';

/** حقل البطاقة من نصّ تسميته — «نوع الحساب» لا يبتلع «نوع الحساب الختامي». */
const field = (page: Page, label: string) =>
  page.locator(`.aseel-field:has(label:text-is("${label}"))`).locator('input, select');

/**
 * شجرة الحسابات على نمط الأصيل: شريط شجرة مضغوط على اليمين + بطاقة الحساب
 * المحدَّد على اليسار — بلا نافذة منبثقة لكل تعديل. يثبّت الاختبار العقد:
 * الاختيار من الشجرة يملأ البطاقة، والحقول المشتقّة تُعرض، و«جديد» يقترح كوداً.
 */
const ACCOUNTS = [
  { id: 1, code: '1', name: 'الأصول', parent: null, account_type: 'Asset', is_active: true },
  { id: 2, code: '11', name: 'الأصول المتداولة', parent: 1, account_type: 'Asset', is_active: true },
  { id: 3, code: '1101', name: 'النقدية', parent: 2, account_type: 'Asset', is_active: true },
  { id: 4, code: '110101', name: 'الصندوق الرئيسي', parent: 3, account_type: 'Asset', is_active: true },
  { id: 5, code: '2', name: 'الخصوم', parent: null, account_type: 'Liability', is_active: true },
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'coa-tree-e2e-token');
    localStorage.setItem('userId', 'coa-tree-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000'
      || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    let body: unknown = [];
    const path = url.pathname;
    if (path.endsWith('/hr/users/coa-tree-e2e-user/')) {
      body = {
        id: 'coa-tree-e2e-user',
        name: 'COA Tester',
        role: 'manager',
        email: 'coa@example.test',
        employmentStatus: 'active',
        isApproved: true,
        isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الشجرة', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = { role: 'manager', is_manager: true, permissions: [] };
    } else if (path.endsWith('/accounting/accounts/')) {
      body = ACCOUNTS;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
});

test('الشجرة شريط جانبي والبطاقة تعرض الحساب المحدَّد بحقوله المشتقّة', async ({ page }) => {
  await page.goto('/accounting/coa');
  await page.waitForLoadState('networkidle');

  const tree = page.getByRole('tree');
  await expect(tree).toBeVisible();
  // المستويان الأعلى مفتوحان عند الفتح.
  await expect(tree.getByText('الأصول المتداولة')).toBeVisible();

  // لا بطاقة قبل الاختيار.
  await expect(page.getByText('اختر حساباً من الشجرة')).toBeVisible();

  await tree.getByText('النقدية').click();

  await expect(field(page, 'رقم الحساب')).toHaveValue('1101');
  await expect(field(page, 'وصف الحساب')).toHaveValue('النقدية');
  // الحقول المشتقّة من النوع — تُعرض ولا تُدخَل يدوياً.
  await expect(field(page, 'نوع الحساب الختامي')).toHaveValue('ميزانية');
  await expect(field(page, 'نوع الحساب الختامي')).toHaveJSProperty('readOnly', true);
  await expect(field(page, 'طبيعة الحساب')).toHaveValue('مدين');
  // موقع الحساب في الشجرة نصّاً.
  await expect(field(page, 'يتبع حساب')).toHaveValue('الأصول ← الأصول المتداولة');
  // البطاقة للقراءة قبل «تعديل».
  await expect(field(page, 'رقم الحساب')).toHaveJSProperty('readOnly', true);
});

test('«جديد» يفتح بطاقة فارغة بكودٍ مقترح تحت الحساب المحدَّد', async ({ page }) => {
  await page.goto('/accounting/coa');
  await page.waitForLoadState('networkidle');

  const tree = page.getByRole('tree');
  await tree.getByText('النقدية').click();
  await page.getByRole('button', { name: /جديد F2/ }).click();

  // 1101 له ابن واحد 110101 ⇒ التالي 110102.
  await expect(field(page, 'رقم الحساب')).toHaveValue('110102');
  await expect(field(page, 'رقم الحساب')).toHaveJSProperty('readOnly', false);
  await expect(page.getByText('حساب جديد')).toBeVisible();
  // الحفظ متاح والتعديل معطّل أثناء الإنشاء.
  await expect(page.getByRole('button', { name: /حفظ F5/ })).toBeEnabled();
  await expect(page.getByRole('button', { name: /تعديل F3/ })).toBeDisabled();
});

test('شريط الحالة يعدّ السجلات على نمط «الحساب 1 من N»', async ({ page }) => {
  await page.goto('/accounting/coa');
  await page.waitForLoadState('networkidle');
  await page.getByRole('tree').getByText('الأصول', { exact: true }).click();
  await expect(page.getByText(/الحساب 1 من \d+/)).toBeVisible();
});
