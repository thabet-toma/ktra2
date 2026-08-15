import { test, expect } from '@playwright/test';

/**
 * B3 — الزبون المربوط بشركة **مفتوحة الدفاتر**: صفٌّ واحد ببابين، والباب الأول
 * يفتح ملف الشركة الحقيقي (قوائم ومستندات)، والثاني ملفَّ المكتب.
 *
 * يفترض ارتباطاً نشطاً على شركة مفعَّلة لوحدة `accountant_portal`، وزبوناً
 * خارجياً مربوطاً به.
 */
const EMAIL = process.env.OFFICE_EMAIL || 'office.walk@ktra.test';
const PASSWORD = process.env.OFFICE_PASSWORD || 'Walk!2026#office';
const SHOTS = 'e2e/office-walk-shots';

test('الزبون المربوط: باب دفاتر الشركة وباب ملف المكتب، كلاهما يعمل', async ({ page }) => {
  test.setTimeout(120_000);

  await page.goto('/');
  await page.getByRole('button', { name: /تسجيل الدخول|دخول/ }).first().click();
  await page.getByPlaceholder('example@email.com').fill(EMAIL);
  await page.getByPlaceholder('••••••••').fill(PASSWORD);
  await page.getByRole('button', { name: /تسجيل الدخول/ }).first().click();
  await expect(page.getByRole('heading', { name: 'لوحة المكتب' })).toBeVisible({ timeout: 40_000 });

  await page.getByRole('button', { name: 'زبائني' }).first().click();
  await expect(page.getByRole('heading', { name: /^زبائني/ })).toBeVisible({ timeout: 20_000 });

  const books = page.getByRole('button', { name: 'افتح دفاتر الشركة' });
  await expect(books).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'ملف المكتب', exact: true })).toHaveCount(1);
  await page.screenshot({ path: `${SHOTS}/20-linked-two-doors.png`, fullPage: true });

  // الباب الأول: دفاتر الشركة على المنصة.
  await books.click();
  await expect(page.getByRole('navigation', { name: 'أقسام ملف الزبون' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'إقرار الضريبة' })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/21-platform-books.png`, fullPage: true });

  // الباب الثاني: ملف المكتب لنفس الزبون.
  await page.getByRole('button', { name: 'زبائني' }).first().click();
  await page.getByRole('button', { name: 'ملف المكتب', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'الشركة على المنصة' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/^مربوط بـ«كترا»/)).toBeVisible();
  await expect(page.getByRole('button', { name: /افتح دفاتر الشركة/ })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/22-office-file-of-linked-client.png`, fullPage: true });
});
