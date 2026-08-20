import { test, expect, type Page, type BrowserContext } from '@playwright/test';

/**
 * وعي التبويبات — معيار نجاح المهمة في متصفّح حقيقي بتبويبين حقيقيين:
 *
 * 1. فتح تبويب جديد **لا يغيّر التبويب النشط للمستخدم** — التبويب الفاتح يبقى
 *    على مساره وحالته كما هو.
 * 2. التبويب الفاتح يعلن الفتح (بلا إعلانٍ يظنّ المستخدم أن الضغطة لم تعمل حين
 *    يفتح المتصفّح التبويب في الخلفية).
 * 3. التبويب الجديد يعلن عن نفسه **مرّة واحدة**، ورابطه نظيف من رمز المناولة.
 * 4. ضغط «رجوع» في التبويب الجديد يذكّر بالتبويب الآخر — لمحةً واحدة لا نافذة.
 */

const seedRoutes = async (target: Page | BrowserContext) => {
  await target.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });

    if (url.pathname.endsWith('/hr/users/tabs-e2e-user/')) {
      return json({
        id: 'tabs-e2e-user',
        name: 'Tabs Tester',
        role: 'manager',
        email: 'tabs@example.test',
        employmentStatus: 'active',
        isApproved: true,
        isEmailVerified: true,
      });
    }
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

test('فتح تبويب جديد: الفاتح لا يتزحزح، والجديد يعلن عن نفسه مرّةً', async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('token', 'tabs-e2e-token');
    localStorage.setItem('userId', 'tabs-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await seedRoutes(context);

  const opener = await context.newPage();
  await opener.goto('/sales/customers');
  await expect(opener.getByRole('button', { name: /^رجوع/ })).toBeVisible({ timeout: 15000 });

  const duplicate = opener.getByRole('button', { name: 'تكرار الصفحة' });
  await expect(duplicate).toBeVisible();

  const [child] = await Promise.all([
    context.waitForEvent('page'),
    duplicate.click(),
  ]);

  // (1) معيار النجاح: التبويب الفاتح كما هو — لا مساره تغيّر ولا شاشته.
  await expect(opener).toHaveURL(/\/sales\/customers$/);
  await expect(opener.getByRole('navigation', { name: 'breadcrumb' })).toContainText('العملاء');

  // (2) وأعلن الفتح لمن ضغط.
  await expect(opener.getByRole('alert')).toContainText('فُتح في تبويب جديد');

  // (3) التبويب الجديد: مؤشّرٌ واحد، ورابطٌ نظيف من رمز المناولة.
  await child.waitForLoadState('domcontentloaded');
  const chip = child.getByRole('status').filter({ hasText: 'تبويب جديد' });
  await expect(chip).toHaveCount(1, { timeout: 15000 });
  await expect(chip).toContainText('العملاء');
  expect(child.url()).not.toContain('_ktab');

  // (4) «رجوع» في التبويب الجديد يذكّر بالتبويب الآخر — مرّةً واحدة.
  await child.getByRole('button', { name: /^رجوع/ }).click();
  const hint = child.getByRole('status').filter({ hasText: 'لديك أيضاً' });
  await expect(hint).toBeVisible({ timeout: 10000 });
  await expect(hint).toContainText('العملاء');
});
