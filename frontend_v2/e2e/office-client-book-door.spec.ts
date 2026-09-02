import { expect, test, type Page } from '@playwright/test';

/**
 * ISSUE #65 — بابُ دفتر الزبون: فتحُه والدخول إليه والعودة منه.
 *
 * المحرّك كان جاهزاً منذ #52 وبلا مستدعٍ واحد في الواجهة، فكان صاحب المكتب
 * يستطيع أن يُصدر فاتورة أتعابٍ لزبونه ولا يستطيع أن يمسك دفاتره. هذه الرحلة
 * هي معيار القبول حرفياً: يفتح، ويدخل، ويعود — **بلا لمس عنوان URL يدوياً**.
 *
 * لماذا e2e وليس اختبار وحدة؟ لأن العطب الأصلي كان في الوصل لا في الحساب:
 * الدوالّ النقيّة تمرّ خضراء ولا شاشة تستدعيها.
 */

test.use({ serviceWorkers: 'block' });

const OFFICE_USER = {
  id: 'office-user',
  name: 'صاحب المكتب',
  role: 'manager',
  email: 'office@example.test',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true,
  accountType: 'legal_accountant',
  isSuperAdmin: false,
};

const OFFICE_TENANT = {
  TenantID: 1,
  CompanyName: 'مكتب المحاسبة',
  SubscriptionPlan: 'Enterprise',
  Status: 'Active',
  CreatedAt: '2026-08-01T00:00:00Z',
  import_enabled: false,
  template: 'accounting_firm',
  managed_by: null,
};

const CLIENT_BOOK = {
  TenantID: 41,
  CompanyName: 'محل أبو أحمد',
  SubscriptionPlan: 'Enterprise',
  Status: 'Active',
  CreatedAt: '2026-08-10T00:00:00Z',
  import_enabled: false,
  template: 'general',
  // العلامة التي يقرأها شريط «أنت داخل دفتر عميلك» — حقيقةٌ من الخادم لكل شركة.
  managed_by: 1,
};

const DASHBOARD = {
  period: { from: '2026-08-01', to: '2026-08-31' },
  is_new_company: false,
  financials: { revenue: 0, expenses: 0, net_profit: 0 },
  sales_invoices: { total: 0, posted: 0, draft: 0, recent: [] },
  purchase_invoices: { total: 0, posted: 0, draft: 0, recent: [] },
  inventory: {
    total_products: 0, in_stock: 0, low_stock: 0, out_of_stock: 0,
    inventory_value: 0, movements_this_month: 0, low_stock_items: [],
  },
  accounting: { journals_this_month: 0 },
  alerts: [],
};

async function stubOffice(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'office-token');
    localStorage.setItem('userId', 'office-user');
    // `addInitScript` تعمل عند **كل** تنقّل — فكتابة `tenantId` بلا شرط كانت
    // تُعيد المستخدم إلى المكتب في اللحظة التي يدخل فيها دفتر عميله، فيبدو
    // العطب في المنتج وهو في المُثبِّت.
    if (!localStorage.getItem('tenantId')) localStorage.setItem('tenantId', '1');
  });

  const books = [{ ...CLIENT_BOOK }];

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });

    if (path.endsWith('/hr/users/office-user/')) return json(OFFICE_USER);
    if (path.endsWith('/tenants/companies/my-companies/')) {
      // الدفتر **مستثنى** هنا عمداً (#52) — وهذا بالضبط ما جعل الدخول إليه
      // يُلغي نفسه قبل #65: الشركة النشطة كانت تُحسم من هذه القائمة وحدها.
      return json([{
        id: 1, tenant: OFFICE_TENANT, role: 'manager', is_default: true,
        created_at: '2026-08-01T00:00:00Z', can_access_import: false,
      }]);
    }
    if (path.endsWith('/tenants/companies/1/managed-books/')) {
      if (request.method() === 'POST') {
        const body = request.postDataJSON() as { CompanyName: string; template: string };
        const created = {
          ...CLIENT_BOOK, TenantID: 42,
          CompanyName: body.CompanyName, template: body.template,
        };
        books.push(created);
        return json(created, 201);
      }
      return json(books);
    }
    if (path.endsWith('/permissions/me/')) {
      const tenantId = request.headers()['x-tenant-id'] || '1';
      return json({
        role: 'manager', is_manager: true, permissions: [],
        // القالب يتبع الشركة النشطة: قناع المكتب على دفتر المكتب، وبلا قناع
        // داخل دفتر الزبون التجاري.
        template: tenantId === '1' ? 'accounting_firm' : 'general',
      });
    }
    // `/api/dashboard/` لا `endsWith('/dashboard/')`: الأخير يبتلع أيضاً
    // `/api/accountant/practice/dashboard/` فيصل المكتبَ حِملُ لوحةٍ تجارية.
    if (path.endsWith('/api/dashboard/')) return json(DASHBOARD);
    if (path.endsWith('/accountant/practice/dashboard/')) {
      return json({
        clients: [],
        deadlines: { items: [], totals: { count: 0, overdue: 0, due_soon: 0 } },
        unpaid_fees: { invoices: [], total: '0.00' },
      });
    }
    if (path.includes('/accountant/practice/')) {
      return json({ results: [], count: 0 });
    }
    return json([]);
  });
}

test('صاحب المكتب يفتح دفتراً لزبونه ويدخله ويعود — بلا لمس عنوان URL', async ({ page }) => {
  test.setTimeout(90_000);
  await stubOffice(page);

  // ١) قسم «دفاتر عملائي» في قشرة المكتب — كان غير موجود أصلاً.
  await page.goto('/office/books');
  // `level: 2` لأن عنوان القشرة (h1) يحمل النص نفسه — القسم هو المقصود هنا.
  await expect(page.getByRole('heading', { name: 'دفاتر عملائي', level: 2 }))
    .toBeVisible({ timeout: 30_000 });
  await expect(page.locator('li', { hasText: 'محل أبو أحمد' })).toBeVisible();

  // ٢) فتح دفترٍ جديد بالضغط — يمرّ بنقطة المكتب لا بإنشاء شركة عادية.
  await page.getByRole('button', { name: 'افتح دفتراً جديداً' }).click();
  await page.getByPlaceholder('اسم الزبون التجاري').fill('سوبرماركت النور');
  const created = page.waitForRequest((req) =>
    req.url().includes('/tenants/companies/1/managed-books/') && req.method() === 'POST');
  await page.getByRole('button', { name: 'افتح الدفتر' }).click();
  await created;
  // بطاقة الدفتر في القائمة لا رسالة التنبيه العابرة التي تحمل الاسم نفسه.
  await expect(page.locator('li', { hasText: 'سوبرماركت النور' })).toBeVisible();

  // ٣) الدخول إلى الدفتر: قشرةٌ تجارية كاملة على شركة الزبون.
  await page.locator('li', { hasText: 'محل أبو أحمد' })
    .getByRole('button', { name: 'ادخل إلى الدفتر' }).click();
  await page.waitForURL('**/dashboard', { timeout: 30_000 });
  const banner = page.getByTestId('managed-book-banner');
  await expect(banner).toBeVisible({ timeout: 30_000 });
  await expect(banner).toContainText('محل أبو أحمد');

  // ٤) طريق العودة الظاهر — لا مبدّل شركاتٍ لا يحوي الدفتر أصلاً، ولا رابط يدوي.
  await banner.getByRole('button', { name: 'العودة إلى المكتب' }).click();
  await page.waitForURL('**/office', { timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'لوحة المكتب' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('managed-book-banner')).toHaveCount(0);
});
