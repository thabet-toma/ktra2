import { test, expect } from '@playwright/test';

/**
 * A5 — «وضع المحاسب»: ترتيبُ عرضٍ محفوظ لكل متصفح. ما يحرسه هذا الاختبار هو
 * الوعد الذي لا يراه أحد حتى ينكسر: **الحالة تعيش بعد إعادة تحميل الصفحة**.
 * ولا يحرس صلاحية ولا مساراً — الوضع لا يغيّر ما يصل إليه المستخدم.
 */

const asManager = async (page: import('@playwright/test').Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'accountant-mode-token');
    localStorage.setItem('userId', 'accountant-mode-user');
    localStorage.setItem('tenantId', '1');
    // لا نمسح `accountantMode` هنا: هذا السكربت يعمل مع كل تحميل، وإعادة التحميل
    // نفسها هي موضوع الاختبار. السياق الجديد يبدأ فارغاً أصلاً.
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    if (url.pathname.endsWith('/hr/users/accountant-mode-user/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'accountant-mode-user',
          name: 'Accountant Mode Tester',
          role: 'manager',
          email: 'accountant-mode@example.test',
          employmentStatus: 'active',
          isApproved: true,
          isEmailVerified: true,
        }),
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{
          id: 1,
          tenant: {
            TenantID: 1,
            CompanyName: 'شركة الاختبار',
            SubscriptionPlan: 'basic',
            Status: 'active',
            CreatedAt: '2026-01-01T00:00:00Z',
            import_enabled: false,
          },
          role: 'manager',
          is_default: true,
          created_at: '2026-01-01T00:00:00Z',
          can_access_import: false,
        }]),
      });
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          role: 'manager',
          is_manager: true,
          permissions: ['sales.invoice.view', 'accounting.account.manage'],
          modules: {},
        }),
      });
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' });
  });
};

/** الشريط الجانبي لسطح المكتب — الجوّال يُصيَّر أيضاً في نفس الصفحة. */
const desktopSidebar = (page: import('@playwright/test').Page) =>
  page.locator('aside.ktra-sidebar.hidden');

/** ترتيب مجموعات التنقّل كما تظهر فعلاً في الشريط. */
const groupOrder = async (page: import('@playwright/test').Page) =>
  desktopSidebar(page)
    .locator('nav > div > button[title]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('title')));

test('«وضع المحاسب» يقدّم المحاسبة، ويعيش بعد إعادة تحميل الصفحة', async ({ page }) => {
  await asManager(page);
  // شاشة ساكنة عمداً: المطلوب فحصه هو الشريط الجانبي وحده، لا لوحة المؤشرات.
  await page.goto('/about-us');

  const toggle = desktopSidebar(page).getByRole('button', { name: 'وضع المحاسب' });
  await expect(toggle).toBeVisible({ timeout: 15000 });

  // 1) الافتراضي: مطفأ، والمحاسبة في موضعها المعتاد بعد المبيعات.
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  const before = await groupOrder(page);
  expect(before.indexOf('المبيعات')).toBeGreaterThanOrEqual(0);
  expect(before.indexOf('المحاسبة')).toBeGreaterThan(before.indexOf('المبيعات'));

  // 2) التشغيل: المحاسبة تصعد للأول وتُفتح، والمبيعات تُطوى.
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  const after = await groupOrder(page);
  expect(after.indexOf('المحاسبة')).toBeLessThan(after.indexOf('المبيعات'));
  await expect(desktopSidebar(page).getByTitle('شجرة الحسابات', { exact: true })).toBeVisible();
  await expect(desktopSidebar(page).getByTitle('فواتير المبيعات', { exact: true })).toHaveCount(0);

  // 3) الوعد نفسه: إعادة التحميل لا تُرجع الترتيب الافتراضي.
  await page.reload();
  const reloaded = desktopSidebar(page).getByRole('button', { name: 'وضع المحاسب' });
  await expect(reloaded).toBeVisible({ timeout: 15000 });
  await expect(reloaded).toHaveAttribute('aria-pressed', 'true');
  const afterReload = await groupOrder(page);
  expect(afterReload.indexOf('المحاسبة')).toBeLessThan(afterReload.indexOf('المبيعات'));

  // 4) والإطفاء يعيش أيضاً — لا يعود الوضع من تلقائه.
  await reloaded.click();
  await expect(reloaded).toHaveAttribute('aria-pressed', 'false');
  await page.reload();
  const offAgain = desktopSidebar(page).getByRole('button', { name: 'وضع المحاسب' });
  await expect(offAgain).toBeVisible({ timeout: 15000 });
  await expect(offAgain).toHaveAttribute('aria-pressed', 'false');
  const restored = await groupOrder(page);
  expect(restored.indexOf('المحاسبة')).toBeGreaterThan(restored.indexOf('المبيعات'));
});
