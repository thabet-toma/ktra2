import { test, expect } from '@playwright/test';

/**
 * B3 — قلب التذكرة: «زبائني» قائمة واحدة من مصدرين، والربط يجعل الزبون الواحد
 * صفّاً واحداً ببابين (دفاتر الشركة · ملف المكتب) لا صفّين متكرّرين.
 *
 * يفترض عند المحاسب ارتباطاً نشطاً واحداً على الأقل وزبوناً خارجياً غير مربوط.
 */
const EMAIL = process.env.OFFICE_EMAIL || 'office.walk@ktra.test';
const PASSWORD = process.env.OFFICE_PASSWORD || 'Walk!2026#office';
const PRACTICE_CLIENT_ID = process.env.OFFICE_CLIENT_ID || '3';
const SHOTS = 'e2e/office-walk-shots';

test('القائمة الموحّدة تجمع شركات المنصة وزبائن المكتب، والربط يدمج الصفّين في صفّ', async ({ page }) => {
  test.setTimeout(120_000);

  await page.goto('/');
  await page.getByRole('button', { name: /تسجيل الدخول|دخول/ }).first().click();
  await page.getByPlaceholder('example@email.com').fill(EMAIL);
  await page.getByPlaceholder('••••••••').fill(PASSWORD);
  await page.getByRole('button', { name: /تسجيل الدخول/ }).first().click();
  await expect(page.getByRole('heading', { name: 'لوحة المكتب' })).toBeVisible({ timeout: 40_000 });

  await page.getByRole('button', { name: 'زبائني' }).first().click();
  await expect(page.getByRole('heading', { name: /^زبائني/ })).toBeVisible({ timeout: 20_000 });
  // المصدران معاً في قائمة واحدة، كلٌّ بوسمه.
  await expect(page.getByText('على المنصة').first()).toBeVisible();
  await expect(page.getByText('خارجي').first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/16-unified-before-link.png`, fullPage: true });

  // الربط من ملف الزبون الخارجي.
  await page.goto(`/office/practice/${PRACTICE_CLIENT_ID}`);
  // انتظر تحميل الملف فعلاً: قراءة العنوان قبله تلتقط عنوان القشرة لا اسم الزبون.
  await expect(page.getByRole('heading', { name: 'الشركة على المنصة' })).toBeVisible({ timeout: 30_000 });
  // القشرة تحمل `h1` لعنوان القسم والصفحة `h1` لاسم الزبون — الثاني هو المقصود.
  const name = await page.getByRole('heading', { level: 1 }).last().innerText();
  // الربط فعلٌ لا رجعة له من الواجهة، فالاختبار يعيد التحقّق من النتيجة إن كان
  // الزبون مربوطاً من تشغيلٍ سابق بدل أن يفشل على حالةٍ صحيحة.
  const linkButton = page.getByRole('button', { name: 'اربطه بشركة على المنصة' });
  if (await linkButton.isVisible()) {
    await linkButton.click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('الشركة', { exact: true }).selectOption({ index: 1 });
    await dialog.getByRole('button', { name: 'اربط' }).click();
  }
  // بعد الربط: الشركة تُذكر بالاسم، والسبب يُقال حين لا تُفتح دفاترها.
  await expect(page.getByText(/^مربوط بـ«/)).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/17-linked-client-file.png`, fullPage: true });

  // الصفّ واحد لا صفّان — الزبون المربوط لم يعد يظهر مرتين.
  await page.getByRole('button', { name: 'زبائني' }).first().click();
  await expect(page.getByRole('heading', { name: /^زبائني/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('heading', { level: 4, name: name.trim() })).toHaveCount(1);
  // والصفّ يحمل وسم المنصة الآن لا وسم «خارجي».
  const card = page.getByRole('article').filter({ hasText: name.trim() });
  await expect(card.getByText('على المنصة')).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/18-unified-after-link.png`, fullPage: true });
});
