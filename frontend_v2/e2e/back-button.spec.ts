import { test, expect, type Page } from '@playwright/test';

/**
 * زرّ «رجوع» العامّ — عقدُه مختبَراً في متصفّح حقيقي.
 *
 * كان `navigate(-1)` عمياء: في تبويبٍ فُتح على صفحةٍ مباشرةً لا سابقة فيه،
 * فالضغطة إمّا بلا أثر أو تقذف المستخدم خارج التطبيق. الآن الزرّ يسمّي وجهته
 * حين لا سابقة، ويعود عودةً حقيقية حين توجد. القاعدة الصرفة في
 * `utils/backTarget.ts` وبرهانها `utils/backTarget.test.ts`؛ وهذا يثبت الوصل.
 */

const seed = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'back-button-e2e-token');
    localStorage.setItem('userId', 'back-button-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });

    if (url.pathname.endsWith('/hr/users/back-button-e2e-user/')) {
      return json({
        id: 'back-button-e2e-user',
        name: 'Back Button Tester',
        role: 'manager',
        email: 'back-button@example.test',
        employmentStatus: 'active',
        isApproved: true,
        isEmailVerified: true,
      });
    }
    // بلا عضوية شركة يعرض التطبيق شاشة «أنشئ شركتك الأولى» بلا شريط أدوات
    // أصلاً — وهو سبب موت هذا الاختبار قبلاً.
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'KTRA', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-08-01T00:00:00Z',
        },
        role: 'manager', is_default: true, created_at: '2026-08-01T00:00:00Z',
      }]);
    }
    return route.fulfill({ contentType: 'application/json', body: '[]' });
  });
};

/** الزرّ الوحيد الذي اسمه المتاح يبدأ بـ«رجوع» في شريط الأدوات. */
const backButton = (page: Page) => page.getByRole('button', { name: /^رجوع/ });

test.describe('Global Back Button', () => {
  test('بلا سابقة في التبويب: الزرّ يسمّي وجهته وينقل إليها فعلاً', async ({ page }) => {
    await seed(page);
    await page.goto('/sales/customers');

    const back = backButton(page);
    await expect(back).toBeVisible({ timeout: 15000 });
    // المستخدم هبط هنا مباشرةً: لا صفحة سابقة، فالزرّ يقول إلى أين يأخذه.
    await expect(back).toHaveAttribute('title', /لا توجد صفحة سابقة/);
    await expect(back).toContainText('الرئيسية');

    await back.click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test('مع سابقة: الزرّ يعود عودةً حقيقية', async ({ page }) => {
    await seed(page);
    await page.goto('/sales/customers');

    const back = backButton(page);
    await expect(back).toBeVisible({ timeout: 15000 });
    await back.click();
    await expect(page).toHaveURL(/\/dashboard$/);

    // صارت في التبويب سابقة، فالزرّ يستعيد نصّه ووظيفته المعتادين.
    await expect(back).toContainText('رجوع');
    await expect(back).toHaveAttribute('title', 'رجوع للصفحة السابقة');
    await back.click();
    await expect(page).toHaveURL(/\/sales\/customers$/);
  });
});
