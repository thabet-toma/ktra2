import { test, expect } from '@playwright/test';
import { installItemsTreeApiStubs } from './items-tree-stubs';
import { switchItemsToTable } from './items-view';

/**
 * العرض الشجري للمنتجات: الشجرة شريط 240px على اليمين، وبقية عرض الشاشة — التي
 * كانت بياضاً معطَّلاً — بطاقةُ المنتج المحدَّد. يثبّت الاختبار العقد: قبل الاختيار
 * دعوةٌ لاختيار منتج، وبعده تظهر البطاقة **في الصفحة نفسها** (لا تبويب جديد)
 * وتحتلّ المساحة الفارغة إلى يسار الشجرة.
 *
 * محاكي API والمنتجات في `items-tree-stubs.ts` (مشترك مع
 * `items-tree-context-menu.spec.ts`).
 */
test.beforeEach(async ({ page }) => {
  await installItemsTreeApiStubs(page);
});

test('الفراغ بجانب شجرة المنتجات يصير بطاقة المنتج عند النقر على منتج', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');

  // الشجرة هي الافتراضية (B3) — بلا تبديلٍ من الشريط.
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();

  const hint = page.getByText('اختر منتجاً من الشجرة لتظهر بطاقته هنا');
  await expect(hint).toBeVisible();

  const tree = page.locator('.ktra-tree-panel');
  await expect(tree).toBeVisible();

  // فتح التصنيف ثم النقر على المنتج.
  await tree.getByTitle('فتح').first().click();
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click();

  // البطاقة ظهرت في الصفحة نفسها — لا تبويب جديد.
  expect(page.context().pages()).toHaveLength(1);
  await expect(hint).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'نظرة عامة' })).toBeVisible();
  await expect(page.getByText('سعر البيع العام')).toBeVisible();
  await expect(page.getByRole('button', { name: /الكرت الكامل/ })).toBeVisible();

  // البطاقة تحتلّ المساحة التي كانت بيضاء: إلى يسار الشجرة وأعرض منها.
  const treeBox = (await tree.boundingBox())!;
  const paneBox = (await page.getByRole('tab', { name: 'نظرة عامة' })
    .locator('xpath=ancestor::div[contains(@class,"flex-1")][1]').boundingBox())!;
  expect(paneBox.x).toBeLessThan(treeBox.x);
  expect(paneBox.width).toBeGreaterThan(treeBox.width);
});

test('اختيار منتج آخر يبدّل البطاقة في مكانها', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();

  const tree = page.locator('.ktra-tree-panel');
  await tree.getByTitle('فتح').first().click();
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click();
  await expect(page.getByText('SKU-7').first()).toBeVisible();

  await tree.getByRole('button', { name: /بطارية 70A/ }).click();
  await expect(page.getByText('SKU-8').first()).toBeVisible();
  await expect(page.getByText('SKU-7')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /تعديل/ })).toBeVisible();
  expect(page.context().pages()).toHaveLength(1);
});

test('النقر على تصنيف يعرض كرته المجمّع في البطاقة نفسها — لا تبويب جديد', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();

  const tree = page.locator('.ktra-tree-panel');
  await tree.getByRole('button', { name: 'إطارات' }).click();

  expect(page.context().pages()).toHaveLength(1);
  await expect(page.getByRole('tab', { name: 'نظرة عامة (مجمّع)' })).toBeVisible();
  await expect(page.getByText('عدد البراندات')).toBeVisible();
  await expect(page.getByText('2 منتج')).toBeVisible();

  // الكبسة نفسها تفتح الفرع فتظهر أوراقه (اختيارٌ وكشفٌ بكبسة واحدة).
  await expect(tree.getByRole('button', { name: /بطارية 70A/ })).toBeVisible();

  // تبويب البراندات يسرد أعضاء المجموعة داخل البطاقة نفسها.
  await page.getByRole('tab', { name: 'البراندات' }).click();
  await expect(page.getByRole('button', { name: /بطارية 70A/ }).last()).toBeVisible();

  // ومنها إلى منتج مفرد: البطاقة تتبدّل في مكانها.
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click();
  await expect(page.getByRole('tab', { name: 'نظرة عامة', exact: true })).toBeVisible();
  expect(page.context().pages()).toHaveLength(1);
});

test('طيّ الشجرة يسلّم عرضها للبطاقة — شريط لا لوحة فارغة', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();
  await page.locator('.ktra-tree-panel').getByRole('button', { name: 'إطارات' }).click();

  const paneBefore = (await page.getByRole('tablist').boundingBox())!;
  await page.getByTitle('طيّ اللوحة').click();

  const rail = page.locator('.ktra-tree-rail');
  const railBox = (await rail.boundingBox())!;
  expect(railBox.width).toBeLessThan(60);
  await expect(page.locator('.ktra-tree-panel')).toHaveCount(0);

  const paneAfter = (await page.getByRole('tablist').boundingBox())!;
  expect(paneAfter.width).toBeGreaterThan(paneBefore.width);

  // ولا طريق مسدود: الشريط يعيد الشجرة.
  await rail.click();
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();
});

/**
 * الشكل الحاليّ للرابط: التصنيف وحده — الخادم يشتقّ منتجاته وأحفاده. تعدادُ
 * المعرّفات لتصنيفٍ فيه ~1500 منتج كان يُنتج رابطاً ~7.5KB فيردّه nginx (414)
 * قبل أن تُقلع الواجهة أصلاً.
 */
test('الكرت المجمّع بالتصنيف (/product-group?category=) يعرض التبويبات', async ({ page }) => {
  await page.goto('/product-group?category=3&name=%D8%A5%D8%B7%D8%A7%D8%B1%D8%A7%D8%AA');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('كرت مجمّع: إطارات')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'نظرة عامة (مجمّع)' })).toBeVisible();
});

/** الصفحة الكاملة صارت غلافاً فوق نفس الخطّاف — فلتبقَ حيّة بتبويباتها.
 *  و`?ids=` يبقى مفهوماً: روابط قديمة محفوظة عند المستخدمين. */
test('الكرت المجمّع الكامل (/product-group) يعرض التبويبات نفسها', async ({ page }) => {
  await page.goto('/product-group?ids=7,8&name=%D8%A5%D8%B7%D8%A7%D8%B1%D8%A7%D8%AA');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('كرت مجمّع: إطارات')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'نظرة عامة (مجمّع)' })).toBeVisible();
  await expect(page.getByText('عدد البراندات')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'حركة المخزون (مجمّعة)' })).toBeVisible();
});

/**
 * B3: الشجرة افتراضيةٌ (بطلب المالك 2026-10-21)، وآخرُ اختيارٍ يُحفظ في
 * المتصفح فلا يعيد المستخدمُ التبديل كلَّ مرّة. لسانُ الحالة لقبُ زرّ التبديل:
 * «عرض كجدول» في الشجرة، و«عرض كشجرة تصنيفات» في الجدول.
 */
test('الافتراضي شجرة، والاختيار يُحفظ بعد إعادة التحميل', async ({ page }) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.ktra-tree-panel')).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('ktra.items.displayMode'))).toBeNull();

  await switchItemsToTable(page);
  await expect(page.locator('.ktra-tree-panel')).toHaveCount(0);
  await expect(page.getByTitle('نقرتان أو F2 لتعديل الاسم').first()).toBeVisible();

  expect(await page.evaluate(() => localStorage.getItem('ktra.items.displayMode'))).toBe('table');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTitle('عرض كشجرة تصنيفات')).toBeVisible();
  await expect(page.getByTitle('نقرتان أو F2 لتعديل الاسم').first()).toBeVisible();
  await expect(page.locator('.ktra-tree-panel')).toHaveCount(0);
});
