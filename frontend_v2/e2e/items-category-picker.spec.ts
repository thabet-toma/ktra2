import { test, expect, type Locator, type Page } from '@playwright/test';
import { installItemsTreeApiStubs } from './items-tree-stubs';
import { switchItemsToTable } from './items-view';

/**
 * C2 — اختيار تصنيف المنتج واضحٌ ومهنيٌّ في كل أسطح الإنشاء/التعديل.
 *
 * ثمانية أشياء تُثبَت هنا، وكلُّها ممّا لا تراه `npm test` (دوالُّ خالصة) ولا
 * `pytest` (خادم):
 *   1. الإنشاء من «منتج جديد»: اختيار تصنيفٍ **عميق** بالبحث بمقطعٍ من منتصف
 *      المسار ⇒ الجسم يُرسل معرّفه ⇒ المنتج يظهر تحت ذلك التصنيف في الشجرة.
 *   2. التعديل: منتجٌ له 3 براندات يُظهر تحذير «سينتقل معه 3 براند» عند تغيير
 *      التصنيف، ومنتجٌ ببراندٍ واحد لا يُظهره — والجسم يحمل التصنيف الجديد.
 *   3. شارة الشريط تعرض المسار وتقفز بحقل «بيانات عامة» (حقلٌ واحد لا اثنان).
 *   4. التحرير السريع: المنتقي يُفتح فوق النافذة، وجسم PATCH هو `{category: 14}`
 *      وحده — فرقُ ما تغيّر لا الحقول كلها.
 *   5. الإنشاء السريع من الشجرة: المنتقي مملوءٌ بتصنيف العقدة، وإفراغُه لا
 *      يُرسل مفتاح `category` أصلاً.
 *   6. بلا `inventory.item.manage`: لا «إنشاء تصنيف» داخل المنتقي ولا
 *      «إدارة التصنيفات» بجانبه.
 *   7. الفتحُ الأوّل — بلا كتابةٍ ولا تغييرِ حالة — يُقاس عند تركيب اللوحة:
 *      على شاشةٍ قصيرة وحقلٍ في نصفها الأسفل تبقى اللوحة ملاصقةً للحقل وداخل
 *      الشاشة، لا معلّقةً في أعلاها (فلا يُحكَم عليها بلا قياس).
 *   8. فشلُ تحميل التصنيفات: رسالةٌ وزرُّ «إعادة المحاولة» بدل منتقٍ بقائمةٍ
 *      فارغةٍ يُظهر «—» — ثم يعود المنتقي بالمسار عند نجاح المحاولة.
 *
 * المحاكي هو `items-tree-stubs.ts` (نفس عقد الخادم)، ويرفض تصنيفاً غير صالح
 * بـ400 كما يرفضه DRF — محاكٍ يقبل كل شيء يُخفي عطباً حقيقياً.
 */

const CATEGORIES = [
  { id: 11, name: 'قطع غيار', parent: null },
  { id: 12, name: 'محركات', parent: 11 },
  { id: 13, name: 'فلاتر', parent: 12 },
  { id: 14, name: 'فلتر زيت', parent: 13 },
  { id: 3, name: 'إطارات', parent: null },
];

/** كرت منتجٍ بشكله الحقيقي (`ProductSerializer`) — الحقول التي يقرؤها الكرت. */
const cardFor = (overrides: Record<string, unknown>) => ({
  id: 7, tenant: 1, sku: 'SKU-7', barcode: null,
  name_ar: 'إطار 205/55', name_en: '', display_name: 'إطار 205/55 — ميشلان',
  variant_group: '', brand: 'ميشلان', category: 3, category_name: 'إطارات',
  uom_id: null, uom_name: null, uom2: null, uom2_factor: null, uom3: null, uom3_factor: null,
  description: null, storage_location: null, image_url: '',
  sale_account_override: null, sale_return_account_override: null,
  purchase_account_override: null, purchase_return_account_override: null,
  supplier_account_override: null, ending_inventory_account_override: null,
  price_tiers: [], weight_kg: null, volume_cbm: null, hs_code: null,
  min_stock_level: 2, max_stock_level: null, reorder_mode: 'manual',
  is_serialized: false, is_service: false, is_active: true,
  is_for_sale_online: false, online_price: null, online_description: null,
  quantity_on_hand: '12', reserved_quantity: '0', available_quantity: '12', avg_cost: '30',
  sale_price: '45', purchased_qty: '20', avg_monthly_sales: '4',
  indicative_purchase_price: null, indicative_purchase_price_source: null,
  stock_status: 'in_stock', group_key: null, has_group: true,
  family_id: 40, family_name: 'إطار 205/55', family_brand_count: 3,
  effective_min_stock_level: 2, effective_max_stock_level: null, serial_required_by: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-21T00:00:00Z',
  attachments: [],
  ...overrides,
});

const DETAIL_7 = cardFor({});
const DETAIL_8 = cardFor({
  id: 8, sku: 'SKU-8', name_ar: 'بطارية 70A', display_name: 'بطارية 70A',
  brand: 'فارتا', family_id: 41, family_name: 'بطارية 70A', family_brand_count: 1,
  has_group: false,
});

/** أجسام POST/PATCH كما أرسلتها الشاشة — يملؤها المحاكي. */
let createdBodies: Array<Record<string, unknown>> = [];
let patchedBodies: Array<{ id: number; body: Record<string, unknown> }> = [];

const start = async (
  page: Page, permissions?: string[],
): Promise<void> => {
  createdBodies = [];
  patchedBodies = [];
  await installItemsTreeApiStubs(page, {
    categories: CATEGORIES,
    productDetails: { 7: DETAIL_7, 8: DETAIL_8 },
    permissions,
    onCreateProduct: (body) => { createdBodies.push(body); },
    onUpdateProduct: (id, body) => { patchedBodies.push({ id, body }); },
  });
};

/** حقل التصنيف الوحيد في الكرت — `CategoryTreeSelect` يعلن نفسه `combobox`. */
const categoryCombo = (root: Page | Locator) =>
  root.getByRole('combobox', { name: 'التصنيف' }).first();

/** فتح لوحة المنتقي واختيار تصنيفٍ بالبحث عن مقطعٍ من مساره. */
const pickCategoryBySearch = async (
  root: Page, segment: string, targetLabel: string,
): Promise<void> => {
  await categoryCombo(root).click();
  const search = root.getByLabel('بحث التصنيفات');
  await search.fill(segment);
  await root.getByRole('option', { name: targetLabel }).click();
};

const expandCategory = async (tree: Locator, name: string): Promise<void> => {
  const row = tree.locator('.ktra-tree-cat').filter({ hasText: name }).first();
  await row.locator('.ktra-tree-twisty').click();
};

test('الإنشاء: تصنيفٌ عميق بالبحث بمقطعٍ من منتصف المسار ⇒ الجسم يحمله والمنتج تحته', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');

  await page.getByTitle('منتج جديد (Ctrl+Ins)').click();
  await page.getByPlaceholder('اسم المنتج').first().fill('فلتر زيت تويوتا');

  // «محركات» ليست اسم الهدف بل مقطعٌ في منتصف مساره — الهدف «فلتر زيت» (14).
  await pickCategoryBySearch(page, 'محركات', 'قطع غيار ‹ محركات ‹ فلاتر ‹ فلتر زيت');
  await expect(categoryCombo(page)).toContainText('قطع غيار ‹ محركات ‹ فلاتر ‹ فلتر زيت');

  await page.getByRole('button', { name: /تخزين/ }).click();

  await expect.poll(() => createdBodies.length).toBe(1);
  expect(createdBodies[0].category).toBe(14);
  expect(createdBodies[0].name_ar).toBe('فلتر زيت تويوتا');

  // الشجرة تعود بعد الحفظ — المنتج الجديد يظهر تحت التصنيف الذي اختير له.
  const tree = page.locator('.ktra-tree-panel');
  await expect(tree).toBeVisible();
  await expandCategory(tree, 'قطع غيار');
  await expandCategory(tree, 'محركات');
  await expandCategory(tree, 'فلاتر');
  await expandCategory(tree, 'فلتر زيت');
  await expect(tree.getByRole('button', { name: /فلتر زيت تويوتا/ })).toBeVisible();
});

test('التعديل: 3 براندات ⇒ تحذير «سينتقل معه 3 براند»، والجسم يحمل التصنيف الجديد', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await switchItemsToTable(page);
  await page.getByTitle('SKU-7').first().dblclick();
  await page.getByRole('tab', { name: 'بيانات عامة' }).click();

  await pickCategoryBySearch(page, 'فلاتر', 'قطع غيار ‹ محركات ‹ فلاتر ‹ فلتر زيت');

  await expect(page.getByText('سينتقل معه 3 براند — التصنيف للمنتج كلّه لا لهذا البراند وحده'))
    .toBeVisible();

  await page.getByRole('button', { name: /تخزين/ }).click();
  await expect.poll(() => patchedBodies.length).toBe(1);
  expect(patchedBodies[0].id).toBe(7);
  expect(patchedBodies[0].body.category).toBe(14);
});

test('التعديل: براندٌ واحد ⇒ لا تحذير، والجسم يحمل التصنيف الجديد', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await switchItemsToTable(page);
  await page.getByTitle('SKU-8').first().dblclick();
  await page.getByRole('tab', { name: 'بيانات عامة' }).click();

  await pickCategoryBySearch(page, 'فلاتر', 'قطع غيار ‹ محركات ‹ فلاتر ‹ فلتر زيت');

  await expect(page.getByText(/سينتقل معه/)).toHaveCount(0);

  await page.getByRole('button', { name: /تخزين/ }).click();
  await expect.poll(() => patchedBodies.length).toBe(1);
  expect(patchedBodies[0].id).toBe(8);
  expect(patchedBodies[0].body.category).toBe(14);
});

test('شارة الشريط تعرض المسار وتقفز بحقل «بيانات عامة» — وحقلٌ واحد لا اثنان', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await switchItemsToTable(page);
  await page.getByTitle('SKU-7').first().dblclick();
  await page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' }).waitFor();

  // الكرت يفتح على «نظرة عامة»: الشريط شارةُ مسار، لا منتقياً ثانياً.
  const band = page.locator('.ktra-headband');
  const badge = band.getByRole('button', { name: /إطارات/ });
  await expect(badge).toBeVisible();
  await expect(band.getByRole('combobox', { name: 'التصنيف' })).toHaveCount(0);

  // شارةٌ لا حقلٌ ممدود: عرضُ الزرّ أقلُّ من عرض المساحة غير المعنونة في الحقل
  // (بعد عنوانه والفجوة). كان الزرّ ابناً مباشراً للحقل فيمتدّ `flex:1 1 auto`
  // إلى حافة الحقل ويقرأ كحقل إدخالٍ ثانٍ.
  const badgeField = badge.locator('xpath=ancestor::div[contains(@class,"ktra-field")][1]');
  const badgeBox = await badge.boundingBox();
  const fieldBox = await badgeField.boundingBox();
  const fieldLabelBox = await badgeField.locator('.ktra-field-label').boundingBox();
  expect(badgeBox).not.toBeNull();
  expect(fieldBox).not.toBeNull();
  expect(fieldLabelBox).not.toBeNull();
  const fieldContentWidth = fieldBox!.width - fieldLabelBox!.width - 4; // فجوة .ktra-field
  expect(
    badgeBox!.width,
    `الشارة ممدودة: badge=${badgeBox!.width} content=${fieldContentWidth}`,
  ).toBeLessThan(fieldContentWidth - 1);

  await badge.click();

  await expect(page.getByRole('tab', { name: 'بيانات عامة' })).toHaveAttribute('aria-selected', 'true');
  await expect(categoryCombo(page)).toBeFocused();

  // وحقل «بيانات عامة»: العنوان بمحاذاة صفّ المنتقي لا في وسطه — `.ktra-field`
  // توسّطه `align-items:center` مقابل منتقٍ + سطر حساباته، فينزلق العنوان تحته.
  const generalField = categoryCombo(page)
    .locator('xpath=ancestor::div[contains(@class,"ktra-field")][1]');
  const labelBox = await generalField.locator('.ktra-field-label').boundingBox();
  const comboBox = await categoryCombo(page).boundingBox();
  expect(labelBox).not.toBeNull();
  expect(comboBox).not.toBeNull();
  const labelCentre = labelBox!.y + labelBox!.height / 2;
  expect(
    labelCentre,
    `عنوان الحقل خارج صفّ المنتقي: labelCentre=${labelCentre} combo=${JSON.stringify(comboBox)}`,
  ).toBeGreaterThanOrEqual(comboBox!.y);
  expect(labelCentre).toBeLessThanOrEqual(comboBox!.y + comboBox!.height);
});

test('فشل تحميل التصنيفات: رسالةٌ وزرُّ إعادة محاولة — لا منتقٍ فارغٌ يُظهر «—»', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await switchItemsToTable(page);

  // `ItemForm` يجلب التصنيفات لنفسه عند تركيب الكرت؛ ننتظره أوّلاً كي يقع
  // الفشل على طلب الغلاف وحده (أوّل طلبٍ بعد تسجيل المسار)، لا على طلب الكرت.
  const cardCategories = page.waitForResponse((response) =>
    response.url().includes('/inventory/categories/') && response.status() === 200);
  await page.getByTitle('SKU-7').first().dblclick();
  await cardCategories;
  await page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' }).waitFor();

  // مسارٌ يُسجَّل بعد `start` فيغلب محاكيه (الأحدث أولاً): طلباتُ الغلاف كلُّها
  // تفشل 500 حتى تُضغط «إعادة المحاولة» ثم تعود البيانات الحقيقية — تماماً
  // كعطبٍ عابرٍ في الشبكة. لا يكفي فشلُ أوّل طلبٍ حرفياً: `StrictMode` في
  // التطوير يعيد تشغيل أثر التحميل مرّتين فينجح الثاني ويمحو حالة الخطأ.
  // والمسار سُجِّل بعد استقرار جلب الكرت، فكلُّ طلبٍ يليه طلبُ الغلاف وحده.
  let categoryCalls = 0;
  let failing = true;
  const categoryStatuses: number[] = [];
  await page.route('**/inventory/categories/', async (route) => {
    categoryCalls += 1;
    if (failing) {
      categoryStatuses.push(500);
      await route.fulfill({
        status: 500, contentType: 'application/json',
        body: JSON.stringify({ detail: 'تعذّر الجلب' }),
      });
      return;
    }
    categoryStatuses.push(200);
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(CATEGORIES),
    });
  });

  await page.getByRole('tab', { name: 'بيانات عامة' }).click();

  // فشلُ الجلب كان يُنهي التحميل بقائمةٍ فارغة، فيُعرض المنتقي الفعلي و«—»
  // مكان مسار التصنيف المحفوظ. المطلوب: رسالةٌ صريحة وزرُّ محاولة.
  await expect(page.getByText('تعذّر تحميل التصنيفات')).toBeVisible();
  await expect(categoryCombo(page)).toHaveCount(0);
  expect(categoryStatuses.length).toBeGreaterThan(0);
  expect(categoryStatuses.every((status) => status === 500)).toBe(true);
  const callsBeforeRetry = categoryCalls;

  failing = false;
  await page.getByRole('button', { name: 'إعادة المحاولة' }).click();
  await expect(categoryCombo(page)).toContainText('إطارات');
  expect(categoryCalls).toBeGreaterThan(callsBeforeRetry);
  expect(categoryStatuses[categoryStatuses.length - 1]).toBe(200);
});

test('التحرير السريع: المنتقي يعمل فوق النافذة (بوّابة z-[10000] ← نافذة 81)، والتصنيف يُحفظ', async ({ page }) => {
  await start(page);
  // ملخّص حركة المخزون الذي تطلبه شاشة الأرصدة — المسار الأخير المسجَّل يغلب المحاكي العام.
  await page.route('**/inventory/stock-movements/summary/**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ total_products_in_stock: 1, total_inventory_value: '360' }),
  }));

  await page.goto('/stock-levels');
  await page.waitForLoadState('networkidle');
  await page.getByTitle('تعديل سريع للمنتج').first().click();

  const win = page.locator('.ktra-float-win')
    .filter({ has: page.locator('.ktra-float-win__title', { hasText: 'تعديل سريع' }) });
  await expect(win).toBeVisible();

  // النقر على عنوان الحقل لا يمسح الاختيار (المنتقي أزرارٌ داخل حقلٍ ليس <label>).
  await win.getByText('التصنيف', { exact: true }).click();
  await expect(categoryCombo(win)).toContainText('إطارات');

  // اللوحة بوّابةٌ على `body` خارج النافذة — تُفتح وتُنتقى منها بلا قصّ.
  await categoryCombo(win).click();
  await page.getByLabel('بحث التصنيفات').fill('فلاتر');
  await page.getByRole('option', { name: 'قطع غيار ‹ محركات ‹ فلاتر ‹ فلتر زيت' }).click();

  await win.getByRole('button', { name: 'حفظ', exact: true }).click();
  await expect(win).toHaveCount(0);

  await expect.poll(() => patchedBodies.length).toBe(1);
  // فرقُ ما تغيّر وحده — لا الاسم ولا البراند ولا سعر البيع.
  expect(patchedBodies[0].body).toEqual({ category: 14 });
});

test('الإنشاء السريع: المنتقي مملوءٌ بتصنيف العقدة، وإفراغُه لا يُرسل مفتاح category', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');

  // نفس مسار `items-tree-context-menu.spec.ts`: الشجرة ← كبسة يمين على منتجٍ
  // مصنَّف ← «إضافة منتج في نفس التصنيف» — وهي التي تفتح النافذة بـ`categoryId`.
  const tree = page.locator('.ktra-tree-panel');
  await expect(tree).toBeVisible();
  await tree.getByTitle('فتح').first().click();
  await tree.getByRole('button', { name: /إطار 205\/55 — ميشلان/ }).click({ button: 'right' });
  await page.getByRole('button', { name: 'إضافة منتج في نفس التصنيف' }).click();

  const dialog = page.getByRole('heading', { name: 'إضافة منتج سريع' })
    .locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]');
  await expect(dialog).toBeVisible();

  // مملوءٌ مسبقاً بمسار تصنيف العقدة (3 = «إطارات») — لا منتقٍ فارغ.
  await expect(categoryCombo(dialog)).toContainText('إطارات');

  // إفراغُه عمداً ⇒ «بلا تصنيف»، ولا يبقى تصنيفُ العقدة على المنتج.
  await dialog.getByRole('button', { name: 'مسح التصنيف' }).click();
  await expect(categoryCombo(dialog)).toContainText('بدون تصنيف');

  await dialog.locator('input[type="text"]').first().fill('منتج بلا تصنيف');
  await page.getByRole('button', { name: /حفظ وإدراج/ }).click();

  await expect.poll(() => createdBodies.length).toBe(1);
  expect(createdBodies[0].name_ar).toBe('منتج بلا تصنيف');
  expect('category' in createdBodies[0]).toBe(false);
});

test('الفتح الأول: اللوحة تُقاس عند التركيب — ملاصقةٌ للحقل ولا تخرج عن الشاشة', async ({ page }) => {
  // شاشةٌ قصيرة تُنزل حقل «بيانات عامة» في نصفها الأسفل: ما تحت الحقل أضيقُ من
  // اللوحة وما فوقه أوسع — الحالة التي يُحكَم فيها على اللوحة بلا قياسٍ فتُسقَط
  // في أعلى الشاشة منفصلةً عن الحقل (قياسٌ قبل التركيب يقرأ ارتفاعاً صفراً).
  const VIEWPORT_HEIGHT = 520;
  await page.setViewportSize({ width: 1280, height: VIEWPORT_HEIGHT });
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await switchItemsToTable(page);
  await page.getByTitle('SKU-7').first().dblclick();
  await page.getByRole('tab', { name: 'بيانات عامة' }).click();

  const combo = categoryCombo(page);
  // إلى أسفل الشاشة، ثم الشرط المسبق صريحاً قبل فتح اللوحة.
  await combo.evaluate((el) => el.scrollIntoView({ block: 'end' }));
  await expect.poll(async () => (await combo.boundingBox())?.y ?? 0)
    .toBeGreaterThan(VIEWPORT_HEIGHT / 2);

  // بلا كتابةٍ ولا تغييرِ حالة: الفتح وحده.
  await combo.click();
  const search = page.getByLabel('بحث التصنيفات');
  await expect(search).toBeVisible();
  // اللوحة هي عنصر البوّابة الذي يشير إليه `aria-controls` — ربطٌ صريح لا
  // صنفُ طبقةٍ (`z-[10000]`) قد يتغيّر.
  const panelId = await combo.getAttribute('aria-controls');
  expect(panelId).not.toBeNull();
  const panel = page.locator(`[id="${panelId}"]`);
  await expect(panel).toHaveCount(1);

  const field = await combo.boundingBox();
  const box = await panel.boundingBox();
  expect(field).not.toBeNull();
  expect(box).not.toBeNull();
  const fieldBottom = field!.y + field!.height;
  const panelBottom = box!.y + box!.height;
  // ملاصقة: فوق الحقل بفجوةٍ ≤ 6px أو تحته كذلك — ومتداخلةٌ معه أبداً.
  const adjacentAbove = panelBottom <= field!.y + 1 && field!.y - panelBottom <= 6;
  const adjacentBelow = box!.y >= fieldBottom - 1 && box!.y - fieldBottom <= 6;
  expect(
    adjacentAbove || adjacentBelow,
    `اللوحة غير ملاصقة للحقل: panel=${JSON.stringify(box)} field=${JSON.stringify(field)}`,
  ).toBe(true);
  // وداخل الشاشة كاملةً.
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(panelBottom).toBeLessThanOrEqual(VIEWPORT_HEIGHT + 1);

  // والصفّ الأخير الظاهر — الأقرب إلى حافة اللوحة الملاصقة للحقل — يُنقر،
  // فيغلق اللوحة ويظهر اسمه في الحقل.
  const lastRow = panel.getByRole('treeitem').last();
  const lastLabel = ((await lastRow.textContent()) ?? '').trim();
  expect(lastLabel).not.toBe('');
  await lastRow.click();
  await expect(panel).toHaveCount(0);
  await expect(combo).toContainText(lastLabel);
});

test('بلا inventory.item.manage: لا «إنشاء تصنيف» ولا «إدارة التصنيفات»', async ({ page }) => {
  await start(page, ['inventory.item.view']);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');

  await page.getByTitle('منتج جديد (Ctrl+Ins)').click();
  await page.getByRole('tab', { name: 'بيانات عامة' }).click();

  await categoryCombo(page).click();
  await expect(page.getByLabel('بحث التصنيفات')).toBeVisible();
  await expect(page.getByRole('button', { name: 'إنشاء تصنيف' })).toHaveCount(0);
  await expect(page.getByTitle('إدارة التصنيفات (شجرة)')).toHaveCount(0);
});
