import { test, expect } from '@playwright/test';
import { installItemsTreeApiStubs, UNCATEGORIZED_PRODUCT } from './items-tree-stubs';

/**
 * قائمة زرّ الماوس الأيمن في شجرة المنتجات: الكبسة على **منتج** كانت تفقّع إلى
 * جسم الشجرة فتُظهر قائمة «الفراغ» («إضافة تصنيف رئيسي» + «إضافة منتج هنا») —
 * والثانية تُنشئ منتجاً بلا تصنيف. صار للمنتج قائمته: فتح الكرت · إضافة منتج
 * في نفس التصنيف · نسخ الرمز. وقائمة التصنيف لم تتغيّر، وقائمة الفراغ كذلك.
 *
 * محاكي API والمنتجات في `items-tree-stubs.ts` (مشترك مع
 * `items-tree-card-pane.spec.ts`)؛ ومنتجٌ بلا تصنيف يُضاف هنا وحده.
 */

/** أجسام POST `/inventory/products/` كما أرسلتها الشاشة — يملؤها المحاكي. */
const createdBodies: Array<Record<string, unknown>> = [];

test.beforeEach(async ({ page }) => {
  createdBodies.length = 0;
  await installItemsTreeApiStubs(page, {
    extraProducts: [UNCATEGORIZED_PRODUCT],
    onCreateProduct: (body) => { createdBodies.push(body); },
  });
});

/** الشجرة مفتوحة على شاشة المنتجات، والتصنيف «إطارات» مفتوح بأوراقه. */
async function openTreeWithProducts(page: import('@playwright/test').Page) {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await page.getByTitle('عرض كشجرة تصنيفات').click();
  const tree = page.locator('.ktra-tree-panel');
  await expect(tree).toBeVisible();
  await tree.getByTitle('فتح').first().click();
  return tree;
}

test('كبسة يمين على منتج تفتح قائمة المنتج — لا قائمة الفراغ', async ({ page }) => {
  const tree = await openTreeWithProducts(page);

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });

  await expect(page.getByRole('button', { name: 'فتح الكرت' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'إضافة منتج في نفس التصنيف' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'نسخ الرمز' })).toBeVisible();

  // قائمة الفراغ لا تظهر على منتج — وهي التي كانت تُنشئ منتجاً بلا تصنيف.
  // (الفحص داخل بنود القائمة: شريط الشجرة نفسه يحمل زرّ «إضافة تصنيف رئيسي».)
  const menuItems = page.locator('.ktra-ctxmenu-item');
  await expect(menuItems.filter({ hasText: 'إضافة تصنيف رئيسي' })).toHaveCount(0);
  await expect(menuItems.filter({ hasText: 'إضافة منتج هنا' })).toHaveCount(0);
});

test('كبسة يمين على تصنيف تُبقي «إضافة منتج هنا»', async ({ page }) => {
  const tree = await openTreeWithProducts(page);

  await tree.getByRole('button', { name: 'إطارات' }).click({ button: 'right' });

  await expect(page.getByRole('button', { name: 'إضافة منتج هنا' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'إضافة تصنيف فرعي' })).toBeVisible();
});

test('«فتح الكرت» من قائمة المنتج تعرض بطاقته', async ({ page }) => {
  const tree = await openTreeWithProducts(page);
  await expect(page.getByText('اختر منتجاً من الشجرة لتظهر بطاقته هنا')).toBeVisible();

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'فتح الكرت' }).click();

  await expect(page.getByText('اختر منتجاً من الشجرة لتظهر بطاقته هنا')).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'نظرة عامة' })).toBeVisible();
  await expect(page.getByText('سعر البيع العام')).toBeVisible();
});

/**
 * D6 نفسه: كانت «إضافة منتج هنا» تُنشئ منتجاً بلا تصنيف لأنها تأخذ تصنيف
 * الفراغ. القائمة الجديدة تحمل تصنيف الورقة — يُثبته جسم الطلب لا الشاشة.
 */
test('«إضافة منتج في نفس التصنيف» ترسل تصنيف المنتج — لا null (D6)', async ({ page }) => {
  const tree = await openTreeWithProducts(page);

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'إضافة منتج في نفس التصنيف' }).click();

  // النافذة السريعة: حقل الاسم العربي وحده مطلوب.
  const dialog = page.getByRole('heading', { name: 'إضافة منتج سريع' }).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]');
  await expect(dialog).toBeVisible();
  await dialog.locator('input[type="text"]').first().fill('منتج من الشجرة');

  await page.getByRole('button', { name: /حفظ وإدراج/ }).click();

  await expect.poll(() => createdBodies.length).toBe(1);
  expect(createdBodies[0].name_ar).toBe('منتج من الشجرة');
  expect(createdBodies[0].category).toBe(3);
});

test('كبسة يمين على منتجٍ بلا تصنيف تُظهر «بدون تصنيف» لا «في نفس التصنيف»', async ({ page }) => {
  const tree = await openTreeWithProducts(page);

  await tree.getByRole('button', { name: /زيت محرك/ }).click({ button: 'right' });

  await expect(page.getByRole('button', { name: 'إضافة منتج بدون تصنيف' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'إضافة منتج في نفس التصنيف' })).toHaveCount(0);
});

/** صفّ «بدون تصنيف» ليس تصنيفاً — قائمته قائمة الفراغ، لا قائمة تصنيف. */
test('كبسة يمين على صفّ «بدون تصنيف» تُظهر قائمة الفراغ', async ({ page }) => {
  const tree = await openTreeWithProducts(page);

  await tree.getByText('بدون تصنيف', { exact: true }).click({ button: 'right' });

  await expect(page.getByRole('button', { name: 'إضافة منتج هنا' })).toBeVisible();
  // «إضافة تصنيف رئيسي» موجودٌ أيضاً في شريط الشجرة بزرٍّ أيقونيّ — الفحص داخل
  // بنود القائمة وحدها (نمط الاختبار الأول نفسه).
  await expect(page.locator('.ktra-ctxmenu-item').filter({ hasText: 'إضافة تصنيف رئيسي' })).toBeVisible();
  await expect(page.locator('.ktra-ctxmenu-item').filter({ hasText: 'فتح الكرت' })).toHaveCount(0);
});

test('«نسخ الرمز» ينسخ رمز المنتج إلى الحافظة', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const tree = await openTreeWithProducts(page);

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'نسخ الرمز' }).click();

  await expect(page.getByRole('alert').filter({ hasText: 'نُسخ الرمز' })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('SKU-7');
});
