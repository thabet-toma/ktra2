import { test, expect, type Locator, type Page } from '@playwright/test';
import {
  installItemsTreeApiStubs,
  type ItemsTreeCategory,
  type ItemsTreeProductRow,
} from './items-tree-stubs';
import { switchItemsToTable } from './items-view';

/**
 * C3 — نقل المنتج (فرداً وجماعةً) وإعادة ربط تصنيفٍ من شجرة المنتجات بكبسة يمين.
 *
 * خمسة أشياء لا تراها `npm test` (دوالُّ خالصة) ولا `pytest` (خادم):
 *   1. منتجٌ من الشجرة ⇒ «نقل إلى تصنيف…» ⇒ اختيار تصنيفٍ عميق بالبحث بمقطعٍ
 *      من منتصف المسار ⇒ جسم POST هو `{product_ids: [7], category: 14}` بالضبط
 *      ⇒ بعد إعادة الجلب يظهر المنتج تحت التصنيف الجديد.
 *   2. تصنيفٌ ⇒ «نقل تحت…» ⇒ خيارات النافذة تستبعد العقدة نفسها وأحفادها
 *      (تُثبَت بالبحث: «لا تطابق» لا خيار) ⇒ PATCH `{parent: 3}` ⇒ الشجرة
 *      تعرضه ابناً للأب الجديد.
 *   3. الجدول: «تحديد منتجات» ⇒ ثلاثة صفوف (أحدها بثلاثة براندات) ⇒ «نقل
 *      المحدَّد إلى تصنيف… (3)» ⇒ الجسم يحمل المعرّفات الثلاثة ⇒ شريط «نُقل 3
 *      منتجاً (ومعه 2 براند)» والتحديد ينتهي.
 *   4. بلا `inventory.item.manage`: لا بند نقلٍ في قائمتي الشجرة ولا زرّ نقلٍ
 *      في الجدول — الخادم يردّه 403 أصلاً، والواجهة لا تعرض ما سيُرفض.
 *   5. منتجٌ له 3 براندات: تحذير «ينتقل المنتج كلّه ببراندَاته الـ3» داخل النافذة
 *      قبل النقل.
 *
 * المحاكي `items-tree-stubs.ts` يرفض ما يرفضه الخادم (قائمة معرّفاتٍ فارغة أو
 * غير صحيحة، مفتاح `category` غائب، تصنيفٌ خارج الشجرة، والحلقة في الأب) ويحدّث
 * حالته الداخلية كي تُظهر إعادةُ الجلب النتيجة — محاكٍ يقبل كل شيء يُخفي عطباً.
 */

const CATEGORIES: ItemsTreeCategory[] = [
  { id: 11, name: 'قطع غيار', parent: null },
  { id: 12, name: 'محركات', parent: 11 },
  { id: 13, name: 'فلاتر', parent: 12 },
  { id: 14, name: 'فلتر زيت', parent: 13 },
  { id: 3, name: 'إطارات', parent: null },
];

/** منتجٌ له ثلاثة براندات — يُظهر تحذير النقل في النافذة. */
const FAMILY_PRODUCT: ItemsTreeProductRow = {
  id: 10, sku: 'SKU-10', name_ar: 'طقم إطارات', name_en: '',
  display_name: 'طقم إطارات — ميشلان', category: 3, category_name: 'إطارات',
  quantity_on_hand: '5', reserved_quantity: '0', available_quantity: '5',
  avg_cost: '10', sale_price: '20', min_stock_level: 1, stock_status: 'in_stock',
  has_group: true, group_key: 'طقم إطارات', family_brand_count: 3,
};

let bulkBodies: Array<Record<string, unknown>> = [];
let categoryPatches: Array<{ id: number; body: Record<string, unknown> }> = [];

const start = async (page: Page, permissions?: string[]): Promise<void> => {
  bulkBodies = [];
  categoryPatches = [];
  await installItemsTreeApiStubs(page, {
    // نسخةٌ جديدة في كل اختبار: المحاكي يعدّل التصنيفات والمنتجات في مكانها.
    categories: CATEGORIES.map((c) => ({ ...c })),
    extraProducts: [{ ...FAMILY_PRODUCT }],
    permissions,
    onBulkSetCategory: (body) => { bulkBodies.push(body); },
    onUpdateCategory: (id, body) => { categoryPatches.push({ id, body }); },
  });
};

const expandCategory = async (tree: Locator, name: string): Promise<void> => {
  const row = tree.locator('.ktra-tree-cat').filter({ hasText: name }).first();
  await row.locator('.ktra-tree-twisty').click();
};

const openTree = async (page: Page): Promise<Locator> => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  const tree = page.locator('.ktra-tree-panel');
  await expect(tree).toBeVisible();
  return tree;
};

test('الشجرة: نقل منتج إلى تصنيفٍ عميق بالبحث — والجسم بالضبط، ثم يظهر تحته', async ({ page }) => {
  await start(page);
  const tree = await openTree(page);
  await expandCategory(tree, 'إطارات');

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'نقل إلى تصنيف…' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('combobox', { name: 'التصنيف' }).click();
  // «محركات» مقطعٌ في منتصف المسار لا اسم الهدف — البحث يطابق أيّ مقطع.
  await page.getByLabel('بحث التصنيفات').fill('محركات');
  await page.getByRole('option', { name: 'قطع غيار ‹ محركات ‹ فلاتر ‹ فلتر زيت' }).click();

  const refetched = page.waitForResponse((response) =>
    response.url().includes('/inventory/products/') && response.request().method() === 'GET');
  await dialog.getByRole('button', { name: 'نقل', exact: true }).click();

  await expect.poll(() => bulkBodies.length).toBe(1);
  expect(bulkBodies[0]).toEqual({ product_ids: [7], category: 14 });
  expect(categoryPatches).toEqual([]);

  // إعادة الجلب بعد النقل تجعل المنتج تحت التصنيف الجديد فعلاً.
  await refetched;
  for (const name of ['قطع غيار', 'محركات', 'فلاتر', 'فلتر زيت']) {
    await expandCategory(tree, name);
  }
  const targetRow = tree.locator('.ktra-tree-cat').filter({ hasText: 'فلتر زيت' }).first();
  await expect(targetRow).toBeVisible();
  // المنتج **تحت** التصنيف الجديد لا مجرّد ظاهرٍ في الشجرة (كان ظاهراً تحت
  // «إطارات» قبل النقل، و«ظاهرٌ ما دام الأب مفتوحاً» لا يثبت شيئاً).
  const targetNode = targetRow.locator('xpath=..');
  await expect(targetNode.getByRole('button', { name: /إطار 205\/55 — ميشلان/ })).toBeVisible();
});

test('Esc داخل المنتقي يغلق القائمة وحدها، والثانية تغلق نافذة النقل', async ({ page }) => {
  await start(page);
  const tree = await openTree(page);
  await expandCategory(tree, 'إطارات');

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'نقل إلى تصنيف…' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('combobox', { name: 'التصنيف' }).click();

  // التركيز في البحث — ↓ ينزل إلى أوّل صفٍّ في الشجرة، فـEsc يقع داخل الصفّ.
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('treeitem').first()).toBeFocused();
  await page.keyboard.press('Escape');

  // القائمة وحدها أُغلقت: كانت Esc تُغلق النافذة معها فيضيع ما اختاره المستخدم.
  await expect(page.getByRole('tree')).toHaveCount(0);
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
});

test('الشجرة: «نقل تحت…» يستبعد العقدة وأحفادها، والنقل يعيد الربط', async ({ page }) => {
  await start(page);
  const tree = await openTree(page);

  await tree.getByRole('button', { name: 'قطع غيار' }).click({ button: 'right' });
  await page.getByRole('button', { name: 'نقل تحت…' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('combobox', { name: 'التصنيف' }).click();
  const search = page.getByLabel('بحث التصنيفات');

  // العقدة نفسها ليست أباً لنفسها…
  await search.fill('قطع غيار');
  await expect(page.getByText('لا تطابق')).toBeVisible();
  // …ولا أحد أحفادها — بأي عمق: الابن المباشر والابن الأوسط.
  for (const descendant of ['محركات', 'فلاتر', 'فلتر زيت']) {
    await search.fill(descendant);
    await expect(page.getByText('لا تطابق')).toBeVisible();
  }

  // أبٌ صالح: «إطارات» جذرٌ آخر لا علاقة له بالعقدة.
  await search.fill('إطارات');
  await page.getByRole('option', { name: 'إطارات' }).click();

  const patched = page.waitForResponse((response) =>
    response.url().includes('/inventory/categories/11/') && response.request().method() === 'PATCH');
  const catsRefetched = page.waitForResponse((response) =>
    response.url().endsWith('/inventory/categories/') && response.request().method() === 'GET');
  await dialog.getByRole('button', { name: 'نقل', exact: true }).click();

  await expect.poll(() => categoryPatches.length).toBe(1);
  expect(categoryPatches[0]).toEqual({ id: 11, body: { parent: 3 } });
  expect(bulkBodies).toEqual([]);
  await patched;
  await catsRefetched;

  // صار ابناً: لا يُرى حتى يُفتح الأب، ثم يظهر تحته.
  await expect(tree.getByRole('button', { name: 'قطع غيار' })).toHaveCount(0);
  await expandCategory(tree, 'إطارات');
  await expect(tree.getByRole('button', { name: 'قطع غيار' })).toBeVisible();
});

test('الجدول: تحديد ثلاثة منتجات (أحدها بثلاثة براندات) — الجسم يحملها والشريط يذكر المرافقين', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await switchItemsToTable(page);

  await page.getByRole('button', { name: 'تحديد منتجات' }).click();
  const boxes = page.getByRole('checkbox');
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  // الصفّ الثالث هو المنتج ذو البراندات الثلاثة — نقله يحرّك براندَيه الآخرين.
  await boxes.nth(2).check();

  await page.getByRole('button', { name: /نقل المحدَّد إلى تصنيف… \(3\)/ }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('combobox', { name: 'التصنيف' }).click();
  // اللوحة بوّابةٌ على `body` خارج النافذة — تُنتقى من الصفحة لا من عنصر الحوار.
  await page.getByRole('treeitem', { name: 'قطع غيار' }).click();

  await dialog.getByRole('button', { name: 'نقل', exact: true }).click();

  await expect.poll(() => bulkBodies.length).toBe(1);
  const sent = bulkBodies[0] as { product_ids: number[]; category: number };
  expect(new Set(sent.product_ids)).toEqual(new Set([7, 8, 10]));
  expect(sent.category).toBe(11);

  await expect(page.getByText('نُقل 3 منتجاً (ومعه 2 براند)')).toBeVisible();
  // التحديد انتهى: المربّعات اختفت وزرّ التبديل عاد إلى صيغته الأولى.
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'تحديد منتجات' })).toBeVisible();
});

test('الجدول: «إزالة التصنيف» تنقل إلى بدون تصنيف — الجسم category: null والشريط يظهر', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await switchItemsToTable(page);

  await page.getByRole('button', { name: 'تحديد منتجات' }).click();
  const boxes = page.getByRole('checkbox');
  await boxes.nth(0).check();
  await boxes.nth(1).check();

  await page.getByRole('button', { name: /نقل المحدَّد إلى تصنيف… \(2\)/ }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // اختيارٌ مختلط: لا تصنيفَ حالٍّ واحد، فالخانة معروضة والمنتقي يُعطَّل بها.
  await dialog.getByRole('checkbox', { name: 'إزالة التصنيف (بدون تصنيف)' }).check();
  await expect(dialog.getByRole('combobox', { name: 'التصنيف' })).toHaveAttribute('tabindex', '-1');

  await dialog.getByRole('button', { name: 'نقل', exact: true }).click();

  await expect.poll(() => bulkBodies.length).toBe(1);
  const sent = bulkBodies[0] as { product_ids: number[]; category: number | null };
  expect(new Set(sent.product_ids)).toEqual(new Set([7, 8]));
  expect(sent.category).toBeNull();

  await expect(page.getByText('نُقل 2 منتجاً')).toBeVisible();
});

test('منتج مصنَّف: إفراغ المنتقي وحده لا ينقل إلى «بدون تصنيف»', async ({ page }) => {
  await start(page);
  const tree = await openTree(page);
  await expandCategory(tree, 'إطارات');

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'نقل إلى تصنيف…' }).click();
  const dialog = page.getByRole('dialog');
  const move = dialog.getByRole('button', { name: 'نقل', exact: true });

  // لا تغيير بعد ⇒ معطّل، والإزالة معروضة لأن للمنتج تصنيفاً.
  await expect(move).toBeDisabled();
  await dialog.getByRole('button', { name: 'مسح التصنيف' }).click();
  // مسحةٌ عابرة لا تُنتج نقلاً إلى «بدون تصنيف»: القرار يحتاج تأشير الخانة.
  await expect(move).toBeDisabled();
  await dialog.getByRole('checkbox', { name: 'إزالة التصنيف (بدون تصنيف)' }).check();
  await expect(move).toBeEnabled();
});

test('بلا inventory.item.manage: لا بند نقلٍ في الشجرة ولا زرّ نقلٍ في الجدول', async ({ page }) => {
  await start(page, ['inventory.item.view']);
  const tree = await openTree(page);
  await expandCategory(tree, 'إطارات');

  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await expect(page.getByRole('button', { name: 'فتح الكرت' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'نقل إلى تصنيف…' })).toHaveCount(0);
  await page.keyboard.press('Escape');

  await tree.getByRole('button', { name: 'إطارات', exact: true }).click({ button: 'right' });
  await expect(page.getByRole('button', { name: 'إضافة منتج هنا' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'نقل تحت…' })).toHaveCount(0);

  await switchItemsToTable(page);
  await page.getByRole('button', { name: 'تحديد منتجات' }).click();
  await page.getByRole('checkbox').first().check();
  await expect(page.getByRole('button', { name: /نقل المحدَّد إلى تصنيف/ })).toHaveCount(0);
});

test('منتجٌ له 3 براندات يُحذَّر قبل النقل: «ينتقل المنتج كلّه ببراندَاته الـ3»', async ({ page }) => {
  await start(page);
  const tree = await openTree(page);
  await expandCategory(tree, 'إطارات');

  await tree.getByRole('button', { name: /طقم إطارات — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'نقل إلى تصنيف…' }).click();

  await expect(
    page.getByText('ينتقل المنتج كلّه ببراندَاته الـ3 — التصنيف للمنتج لا لهذا البراند وحده'),
  ).toBeVisible();
});
