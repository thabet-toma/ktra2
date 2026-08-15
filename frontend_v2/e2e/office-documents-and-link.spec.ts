import { test, expect, type Page } from '@playwright/test';

/**
 * B3 — ما لا يغطّيه المشي الكامل: رفع مستند، وحوار «اربطه بشركة على المنصة»،
 * والأرشفة كحالةٍ لها طريق عودة.
 *
 * كل اختبار هنا **ينشئ زبونه بنفسه** كي يعمل على أي قاعدة، مرّةً بعد مرّة.
 * الرفع يحتاج اعتماد Cloudinary على الخادم؛ حين يغيب، الاختبار يتحقّق أن الفشل
 * **يُقال** للمحاسب بدل أن يُبتلع — وهذا هو السلوك المطلوب في الحالتين.
 */
const EMAIL = process.env.OFFICE_EMAIL || 'office.walk@ktra.test';
const PASSWORD = process.env.OFFICE_PASSWORD || 'Walk!2026#office';
const SHOTS = 'e2e/office-walk-shots';

async function login(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: /تسجيل الدخول|دخول/ }).first().click();
  await page.getByPlaceholder('example@email.com').fill(EMAIL);
  await page.getByPlaceholder('••••••••').fill(PASSWORD);
  await page.getByRole('button', { name: /تسجيل الدخول/ }).first().click();
  await expect(page.getByRole('heading', { name: 'لوحة المكتب' })).toBeVisible({ timeout: 40_000 });
}

async function addClient(page: Page, label: string) {
  const name = `${label} ${Date.now()}`;
  await page.getByRole('button', { name: 'زبائني' }).first().click();
  await page.getByRole('button', { name: 'إضافة زبون' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(/الاسم التجاري/).fill(name);
  await dialog.getByRole('button', { name: 'حفظ' }).click();
  await expect(page.getByRole('heading', { name: 'الشركة على المنصة' })).toBeVisible({ timeout: 30_000 });
  return name;
}

test('رفع مستند: ينجح فيُدرَج، أو يفشل فيُقال السبب — ولا يُبتلع', async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  await addClient(page, 'زبون المستندات');

  await page.getByRole('button', { name: 'مستندات', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'رفع مستند' })).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('الملف').setInputFiles({
    name: 'عقد-الخدمة.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('عقد تقديم خدمات محاسبية'),
  });
  await page.getByLabel('الاسم', { exact: true }).fill('عقد تقديم الخدمة');

  const pending = page.waitForResponse((res) => res.url().includes('/accountant/practice/documents/upload/'));
  await page.getByRole('button', { name: 'ارفع' }).click();
  const response = await pending;

  if (response.ok()) {
    const link = page.getByRole('link', { name: 'عقد تقديم الخدمة' });
    await expect(link).toBeVisible({ timeout: 20_000 });
    await page.getByRole('button', { name: 'حذف عقد تقديم الخدمة' }).click();
    await expect(page.getByText(/سيُحذف «عقد تقديم الخدمة»/)).toBeVisible();
    await page.getByRole('button', { name: 'حذف', exact: true }).click();
    await expect(page.getByText('لا مستندات بعد')).toBeVisible({ timeout: 20_000 });
    return;
  }
  // الفشل مرئيّ ومفهوم — لا شاشة صامتة ولا صفّ نصف مكتوب.
  await expect(page.getByText(/Cloudinary|تعذّر رفع المستند/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('لا مستندات بعد')).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/19-upload-failure-is-legible.png`, fullPage: true });
});

test('«اربطه بشركة على المنصة» يفتح الطريقين: ارتباط قائم أو طلب جديد', async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  await addClient(page, 'زبون الربط');

  await page.getByRole('button', { name: 'اربطه بشركة على المنصة' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'شركة مرتبطة بمكتبك أصلاً' })).toBeVisible({ timeout: 20_000 });
  await expect(dialog.getByRole('heading', { name: 'شركة جديدة على المنصة' })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/14-link-to-platform.png`, fullPage: true });
  // الخروج مضمون: Escape يغلق الحوار.
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
});

test('الأرشفة ليست طريقاً مسدوداً — الاسترجاع من داخل الملف', async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  await addClient(page, 'زبون الأرشفة');

  await page.getByRole('button', { name: 'أرشفة' }).click();
  await page.getByRole('button', { name: 'أرشف', exact: true }).click();
  await expect(page.getByText(/هذا الملف مؤرشف/)).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/15-archived-with-way-back.png`, fullPage: true });

  await page.getByRole('button', { name: 'استرجاع' }).click();
  await expect(page.getByText(/هذا الملف مؤرشف/)).toBeHidden({ timeout: 20_000 });
});
