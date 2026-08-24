import { test, expect } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

/**
 * T-WIN — شريط الإجراءات القابل للإرساء: يمين افتراضاً، يُسحب فيُرسى يساراً أو
 * في شريط العنوان، والاختيار يبقى بعد إعادة التحميل.
 *
 * الشاشة مُصادَق عليها بحقن رمز في التخزين قبل الإقلاع — نفس حيلة إحصاء
 * التكافؤ (`feature-parity-census.spec.ts`)، فالشريط لا يظهر لزائر.
 */

const signIn = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'dock-e2e-token');
    localStorage.setItem('userId', 'dock-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  /* الخادم غير قائم في هذا الاختبار: كل نداء API يُردّ فارغاً عدا بطاقة
     المستخدم — بدونها يسقط التطبيق على صفحة الزائر فلا شريط أصلاً. */
  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith('/hr/users/dock-e2e-user/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'dock-e2e-user',
          name: 'Dock E2E Tester',
          role: 'manager',
          email: 'dock@example.test',
          employmentStatus: 'active',
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
    /* بلا عضوية شركة يعرض التطبيق شاشة «أنشئ شركتك الأولى» فلا غلاف ولا شريط. */
    if (url.pathname.includes('tenants/companies/my-companies/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{
          role: 'owner',
          isDefault: true,
          tenant: { TenantID: 1, Name: 'شركة الاختبار', plan: 'pro', isActive: true },
        }]),
      });
      return;
    }
    if (url.pathname.includes('/mapper/activityStatus/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ isCurrentlyActive: true }),
      });
      return;
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' });
  });
};

const gotoApp = async (page: Page) => {
  /* «/» صفحة الزائر التسويقية (task27) — لوحة التحكم هي أول شاشة داخل الغلاف. */
  await page.goto('/dashboard');
  await expect(page.locator('.app-shell')).toBeVisible({ timeout: 20000 });
};

const dockOf = (page: Page) => page.locator('[data-action-bar-dock]').first();

/** سحب المقبض إلى نقطة ثم إفلاته — الإرساء يُحسم بموضع الإفلات. */
const dragGripTo = async (page: Page, x: number, y: number) => {
  const grip = page.locator('[aria-label="تغيير موضع شريط الإجراءات"]').first();
  const box = (await grip.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(x, y, { steps: 6 });
  await expect(page.locator('[data-dockzone]').first()).toBeVisible();
  await page.mouse.move(x, y);
  await page.mouse.up();
};

test('الشريط يُرسى يميناً افتراضاً كرفٍّ عائم', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);
  const rail = page.getByTestId('action-bar-rail');
  await expect(rail).toBeVisible();
  await expect(rail).toHaveAttribute('data-action-bar-dock', 'right');
  /* الرفّ في النصف الأيمن من الشاشة فعلاً لا بالاسم وحده. */
  const box = (await rail.boundingBox())!;
  const width = page.viewportSize()!.width;
  expect(box.x + box.width / 2).toBeGreaterThan(width / 2);
});

test('سحب الشريط إلى اليسار يُرسيه هناك ويبقى بعد إعادة التحميل', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);
  const height = page.viewportSize()!.height;

  await dragGripTo(page, 30, height / 2);
  await expect(dockOf(page)).toHaveAttribute('data-action-bar-dock', 'left');
  expect(await page.evaluate(() => localStorage.getItem('ktra:actionBarDock'))).toBe('left');

  await page.reload();
  await expect(page.locator('.app-shell')).toBeVisible({ timeout: 20000 });
  await expect(dockOf(page)).toHaveAttribute('data-action-bar-dock', 'left');
  const box = (await page.getByTestId('action-bar-rail').boundingBox())!;
  expect(box.x + box.width / 2).toBeLessThan(page.viewportSize()!.width / 2);
});

test('السحب إلى الأعلى يُعيد الشريط أفقياً إلى شريط العنوان', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);
  const width = page.viewportSize()!.width;

  await dragGripTo(page, width / 2, 12);
  await expect(dockOf(page)).toHaveAttribute('data-action-bar-dock', 'top');
  await expect(page.getByTestId('action-bar-rail')).toHaveCount(0);
  /* في وضع الأعلى الشريط داخل شريط العنوان لا معلّقاً على الجسم. */
  await expect(page.locator('.aseel-app-chrome [data-action-bar-dock="top"]')).toBeVisible();
});

test('على الجوال يُفرض شريط العنوان ولا يظهر رفٌّ عائم', async ({ page }) => {
  await signIn(page);
  await page.addInitScript(() => localStorage.setItem('ktra:actionBarDock', 'right'));
  await page.setViewportSize({ width: 390, height: 780 });
  await gotoApp(page);
  await expect(page.getByTestId('action-bar-rail')).toHaveCount(0);
  /* التفضيل المحفوظ لم يُمسّ — الحاسوب يعود إلى اليمين. */
  expect(await page.evaluate(() => localStorage.getItem('ktra:actionBarDock'))).toBe('right');
});

/**
 * تكافؤ الشريط: إحصاء التكافؤ العام (`feature-parity-census.spec.ts`) معطّل منذ
 * 2026-07-22 لأسبابٍ سابقة لهذا التغيير (شاشة «أنشئ شركتك الأولى» دخلت بعد
 * تسجيل خط الأساس بيوم فتعلق كل شاشة عليها) — فالتكافؤ الذي يخصّ هذا التغيير
 * يُثبَت هنا مباشرةً: لا زرّ يسقط بتغيّر جهة الإرساء.
 */
const BAR_BUTTONS = ['إجراءات سريعة', 'طباعة', 'تحديث'];

for (const side of ['right', 'left', 'top'] as const) {
  test(`لا يسقط زرّ من الشريط في وضع «${side}»`, async ({ page }) => {
    await signIn(page);
    await page.addInitScript((s) => localStorage.setItem('ktra:actionBarDock', s), side);
    await gotoApp(page);
    await expect(dockOf(page)).toHaveAttribute('data-action-bar-dock', side);
    for (const label of BAR_BUTTONS) {
      await expect(
        page.locator(`[data-action-bar-dock] button[title="${label}"]`),
        `الزرّ «${label}» موجود في وضع ${side}`,
      ).toHaveCount(1);
    }
    /* الطيّ وإعادة الترتيب ميزتان قديمتان لا يجوز أن يبتلعهما الرفّ. */
    await page.locator('[data-action-bar-dock] button[title="إخفاء شريط الإجراءات السريعة"]').click();
    await expect(
      page.locator('[data-action-bar-dock] button[title="إظهار شريط الإجراءات السريعة"]'),
    ).toBeVisible();
  });
}
