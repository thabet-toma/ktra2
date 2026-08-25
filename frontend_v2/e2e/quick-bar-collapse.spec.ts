import { test, expect } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

/**
 * شريط الوصول السريع — يُطوى بضغطة (أو `Ctrl+F1`) ويبقى مطويّاً بعد إعادة
 * التحميل، ويبقى له **لسانٌ مرئي** يعيده: لا حالة لا يُخرَج منها.
 *
 * البرهان e2e لا `tsc`: هذا المستودع بلا `@types/react`، فالمترجم لا يفحص
 * خصائص JSX أصلاً — زرٌّ لا يُركَّب أو خاصيّة لا تصل تمرّ خضراء عنده.
 *
 * الشاشة مُصادَق عليها بحقن رمز في التخزين قبل الإقلاع — نفس حيلة
 * `action-bar-dock.spec.ts`، فالغلاف لا يُرسم لزائر.
 */

const signIn = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'quickbar-e2e-token');
    localStorage.setItem('userId', 'quickbar-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith('/hr/users/quickbar-e2e-user/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'quickbar-e2e-user',
          name: 'QuickBar E2E Tester',
          role: 'manager',
          email: 'quickbar@example.test',
          employmentStatus: 'active',
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
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
  /* «/» صفحة الزائر التسويقية (task27) — لوحة التحكم أول شاشة داخل الغلاف. */
  await page.goto('/dashboard');
  await expect(page.locator('.app-shell')).toBeVisible({ timeout: 20000 });
};

const bar = (page: Page) => page.locator('[data-quick-bar]');
const region = (page: Page) => page.locator('#quick-access-bar');

test('الافتراضي مبسوط: الشريط ظاهر وزرّ «رجوع» في متناول اليد', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);

  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'open');
  await expect(region(page).getByRole('button', { name: /رجوع/ })).toBeVisible();
  await expect(page.getByTestId('quick-bar-collapse')).toBeVisible();
  /* اللسان لا يزاحم الشريط المبسوط بسطرٍ ثانٍ. */
  await expect(page.getByTestId('quick-bar-lip')).toHaveCount(0);
});

test('ضغطةٌ واحدة تطوي الشريط، ويبقى اللسان يعيده', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);

  const before = (await region(page).boundingBox())!;
  expect(before.height).toBeGreaterThan(20);

  await page.getByTestId('quick-bar-collapse').click();

  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'collapsed');
  /* الطيّ ارتفاعٌ صفر فعلاً لا اسمٌ على الحالة. */
  await expect.poll(async () => (await region(page).boundingBox())!.height).toBeLessThan(2);
  /* ولا يُترك المستخدم بلا مخرج. */
  const lip = page.getByTestId('quick-bar-lip');
  await expect(lip).toBeVisible();

  await lip.click();
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'open');
  await expect.poll(async () => (await region(page).boundingBox())!.height).toBeGreaterThan(20);
});

test('الطيّ يُحفظ لصاحبه ويبقى بعد إعادة التحميل', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);

  await page.getByTestId('quick-bar-collapse').click();
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'collapsed');
  expect(await page.evaluate(() => localStorage.getItem('ktra.quickBar.open:quickbar-e2e-user')))
    .toBe('0');

  await page.reload();
  await expect(page.locator('.app-shell')).toBeVisible({ timeout: 20000 });
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'collapsed');
  await expect(page.getByTestId('quick-bar-lip')).toBeVisible();
});

test('Ctrl+F1 يطوي ويبسط — وتر Office نفسه', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);

  await page.keyboard.press('Control+F1');
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'collapsed');

  await page.keyboard.press('Control+F1');
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'open');
});

test('المطويّ خارج مسار Tab: لا تركيز على أزرارٍ لا تُرى', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);

  await page.getByTestId('quick-bar-collapse').click();
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'collapsed');

  await expect(region(page)).toHaveAttribute('aria-hidden', 'true');
  /* `inert` هو ما يمنع القفز إلى «رجوع» المخفيّ فعلاً. */
  expect(await region(page).evaluate((el) => (el as HTMLElement).inert)).toBe(true);
});

test('مرسى «مرشد الرحلة» يبقى في الشجرة مطويّاً — البوابة لا تُقطع', async ({ page }) => {
  await signIn(page);
  await gotoApp(page);

  await page.getByTestId('quick-bar-collapse').click();
  await expect(bar(page)).toHaveAttribute('data-quick-bar', 'collapsed');
  /* العقدة موجودة (عدد 1) وإن كانت بارتفاع صفر — حذفها يترك
     `ImportJourneyGuide` يصبّ في عقدةٍ منفصلة فيضيع زرّه إلى الأبد. */
  await expect(page.locator('#import-guide-slot')).toHaveCount(1);

  await page.getByTestId('quick-bar-lip').click();
  await expect(page.locator('#import-guide-slot')).toHaveCount(1);
});
