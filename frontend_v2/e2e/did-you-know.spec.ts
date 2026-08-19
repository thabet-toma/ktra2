import { test, expect } from '@playwright/test';
import { TIPS } from '../constants/tips';

/**
 * THA-121 — «هل تعلم»: بطاقةٌ تسكن الفراغ أسفل الشاشة الحالية.
 *
 * أربعة وعود، كلها غير مرئية حتى تنكسر:
 *  1. **سياقية**: تلميح شاشةٍ يظهر في شاشته وحدها، لا في كل مكان.
 *  2. **لا تزيح شيئاً**: موضع محتوى الشاشة واحدٌ سواء ظهرت البطاقة أو لا.
 *  3. **الإخفاء يبقى** بعد إعادة التحميل (وبعد دخولٍ جديد بنفس المستخدم).
 *  4. **بلا متّسع لا تظهر أصلاً** — لا تطفو ولا تزاحم.
 *
 * والاختبار يمسك أيضاً فخّ هذا المستودع: `tsc` لا يفحص خصائص JSX، فمكوّنٌ لا
 * يعرضه مستدعيه يبقى البناء عنده أخضر. ظهور البطاقة هنا هو الدليل الوحيد على
 * أن `App.tsx` يركّبها فعلاً.
 *
 * الشبكة موقوفة كما في `simple-ui-mode.spec.ts` — لا خادم ولا قاعدة بيانات.
 */

/**
 * شاشة الشيكات: تلميحٌ واحد بلا وجهة، وشاشةٌ قِيس محتواها فبقي أسفلها فراغ
 * حقيقيّ في نافذةٍ عادية. شاشة الفواتير أطول من النافذة أصلاً فلا بطاقة فيها —
 * وهذا القاعدة تعمل لا تنكسر.
 */
const CHEQUE_TIP = TIPS.find((t) => t.view === 'accounting-cheques')!;

const card = (page: import('@playwright/test').Page) =>
  page.getByTestId('did-you-know');

/**
 * محتوى الشاشة نفسه. `AppLayout` له `<main>` خارجيّ يحوي `<main>` الشاشة، فمرساةٌ
 * على الخارجيّ تمسك لوحاتٍ ثابتة لا محتوى الشاشة.
 */
const screenContent = (page: import('@playwright/test').Page) =>
  page.locator('main main').locator('> *').first();

const asManager = async (page: import('@playwright/test').Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'tips-token');
    localStorage.setItem('userId', 'tips-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    if (url.pathname.endsWith('/hr/users/tips-user/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'tips-user',
          name: 'Tips Tester',
          role: 'manager',
          email: 'tips@example.test',
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
          permissions: ['accounting.journal.view', 'sales.invoice.view', 'inventory.item.view'],
          modules: {},
          ui_mode: 'advanced',
        }),
      });
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' });
  });
};

test.setTimeout(120000);

/** نافذةٌ عادية يبقى فيها أسفل شاشة الشيكات متّسعٌ للبطاقة (قِيس فعلياً). */
const ROOMY = { width: 1440, height: 900 };

test('التلميح سياقيّ، لا يزيح المحتوى، وإخفاؤه يبقى بعد إعادة التحميل', async ({ page }) => {
  await asManager(page);
  await page.setViewportSize(ROOMY);

  // 1) في شاشته: البطاقة تظهر — وهذا وحده دليلٌ أن `App.tsx` يركّب المكوّن.
  await page.goto('/accounting/cheques');
  await expect(card(page)).toBeVisible({ timeout: 20000 });
  await expect(card(page)).toHaveAttribute('data-tip-key', CHEQUE_TIP.key);
  await expect(card(page)).toContainText(CHEQUE_TIP.title);

  // 2) لا تزيح شيئاً: موضع محتوى الشاشة قبل إخفائها وبعده واحد.
  const content = screenContent(page);
  const before = await content.boundingBox();
  await page.getByRole('button', { name: 'لا تُظهر هذا مجدداً' }).first().click();
  await expect(card(page)).toHaveCount(0);
  const after = await content.boundingBox();
  expect(after?.y).toBe(before?.y);

  // 3) الإخفاء يبقى بعد إعادة تحميل الصفحة — لا يُسأل المستخدم مرّتين.
  await page.reload();
  await expect(screenContent(page)).toBeVisible({ timeout: 20000 });
  await expect(card(page)).toHaveCount(0);
});

test('تلميح شاشةٍ لا يظهر في شاشةٍ أخرى', async ({ page }) => {
  await asManager(page);
  await page.setViewportSize(ROOMY);
  await page.goto('/about-us');
  await expect(screenContent(page)).toBeVisible({ timeout: 20000 });
  await expect(card(page)).toHaveCount(0);
});

test('بلا متّسع أسفل المحتوى لا تظهر البطاقة أصلاً', async ({ page }) => {
  await asManager(page);
  await page.setViewportSize({ width: 1440, height: 300 });
  await page.goto('/accounting/cheques');
  await expect(screenContent(page)).toBeVisible({ timeout: 20000 });
  await expect(card(page)).toHaveCount(0);

  // ونفس الجلسة نفسها تُظهرها فور اتّساع النافذة — الغياب ضيق مكانٍ لا عطل.
  await page.setViewportSize(ROOMY);
  await expect(card(page)).toBeVisible({ timeout: 15000 });
});
