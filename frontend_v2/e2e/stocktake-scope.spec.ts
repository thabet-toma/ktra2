import { test, expect, type Locator, type Page } from '@playwright/test';
import { installStocktakeApiStubs } from './stocktake-stubs';

/**
 * K2 — الجرد من شجرة التصنيفات وورقة بلا كتالوج.
 *
 * المحاكي `stocktake-stubs.ts` يردّ بعقد `StocktakeSerializer` نفسه ويرفض ما
 * يرفضه الخادم (نطاق+بنود، نطاقٌ بلا منتجات، If-Match بائت، ترحيلٌ كلُّه غير
 * معدود بلا العلم). وكل الاختبارات هنا تقيس ما لا يراه `pytest` ولا `npm test`:
 * الطلب الفعلي، وبنية الشاشة، وسلوك 412 أمام المستخدم.
 */

const openNewModal = async (page: Page) => {
  await page.getByRole('button', { name: 'جرد جديد' }).click();
  const dialog = page.getByRole('dialog', { name: 'جرد جديد' });
  await expect(dialog).toBeVisible();
  return dialog;
};

const goToScopeStep = async (dialog: Locator) => {
  await dialog.getByRole('button', { name: /التالي/ }).click();
};

/** «سجل الجرد» مطويٌّ حين تكون ورقةٌ مفتوحة — يُفتح قبل النقر على صفٍّ منه. */
const openHistory = async (page: Page) => {
  const toggle = page.getByRole('region', { name: 'سجل الجرد' })
    .getByRole('button', { name: /السجل/ });
  if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
};

const openRow = async (page: Page, number: string) => {
  await openHistory(page);
  const row = page.locator('tbody tr').filter({ hasText: number }).first();
  await row.getByRole('button', { name: 'فتح' }).click();
};

const openFirstSheet = async (page: Page) => {
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');
  await openRow(page, 'JRD-0001');
  await expect(page.getByTestId('stocktake-sheet')).toBeVisible();
};

/** صفّ مسودّة الجرد من IndexedDB — الحمولة كما كتبتها الشاشة فعلاً. */
const readStocktakeDraft = async (page: Page, docId: string) => page.evaluate(async (id) => {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('ktra_offline');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise<Array<Record<string, unknown>>>((resolve, reject) => {
    const request = db.transaction('document_drafts', 'readonly')
      .objectStore('document_drafts').getAll();
    request.onsuccess = () => resolve(request.result as Array<Record<string, unknown>>);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const row = rows.find(
    (item) => item.doc_type === 'stocktake' && String(item.doc_id) === id,
  );
  if (!row) return null;
  return {
    updatedAt: row.updated_at as string,
    payload: JSON.parse(String(row.data)) as {
      v?: number;
      docId?: number;
      removedIds?: number[];
      lines?: Array<{ product: number; counted_quantity: string }>;
    },
  };
}, docId);

/** يكتب صفّ مسودّةٍ خاماً — لاختبار مسودّة الصفحة القديمة (بلا `v` ولا `docId`). */
const seedStocktakeDraft = async (page: Page, row: Record<string, unknown>) => {
  await page.evaluate(async (record) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('ktra_offline');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('document_drafts', 'readwrite');
      tx.objectStore('document_drafts').put(record);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  }, row);
};

test('جرد جديد من تصنيفين ⇒ الجسم يحمل معرّفيهما، والملخّص والبنود بالعدد نفسه', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await dialog.getByLabel('المستودع').selectOption('1');
  await goToScopeStep(dialog);

  // بحثٌ داخل الشجرة يفتح الفرع المطابق — لا حاجة لتوسيع الجذر يدوياً.
  await dialog.getByLabel('بحث التصنيفات').fill('محركات');
  await dialog.getByRole('checkbox', { name: 'تحديد محركات' }).check();
  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  await dialog.getByRole('checkbox', { name: 'تحديد إطارات' }).check();

  // «محركات» منتجها المباشر واحد، و«إطارات» ثلاثة ⇒ 4 منتجات في تصنيفين.
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 4 منتجات في تصنيفين');

  await dialog.getByRole('button', { name: 'إنشاء', exact: true }).click();

  await expect.poll(() => handle.createdBodies.length).toBe(1);
  const body = handle.createdBodies[0];
  expect((body.scope as Record<string, unknown>).categories).toEqual([12, 14]);
  expect((body.scope as Record<string, unknown>).all).toBe(false);
  expect(body.warehouse).toBe(1);

  // الورقة تُفتح على الجرد الجديد ببنوده الأربعة — لا كتالوج منزَّل.
  await expect(page.getByTestId('stocktake-line')).toHaveCount(4);
  await expect(page.getByTestId('stocktake-progress')).toHaveText(/^معدود\s*0\s*\/\s*4$/);
});

test('اختيارٌ بصفر منتجات يعطّل «إنشاء» ويقول السبب', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByLabel('بحث التصنيفات').fill('زيوت');
  await dialog.getByRole('checkbox', { name: 'تحديد زيوت' }).check();

  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 0 منتج في تصنيفٍ واحد');
  await expect(dialog.getByText('لا منتجات في هذا الاختيار')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'إنشاء', exact: true })).toBeDisabled();
});

/**
 * ST-2 — منتجاتٌ صريحة تحت كل تصنيف: تُجلب اللوحة كسولاً عند الطلب، وتُفتح
 * **بلا أيّ تأشير**، ويُختار منتجٌ منتجاً أو بالجملة داخل التصنيف وحده. الملخّص
 * يقول «منتجان في تصنيفٍ واحد» من المعرّفات وحدها (لا عدّاد تصنيفٍ مشمول)، والجسم
 * يحمل `products` ولا يحمل تصنيفاً.
 */
test('منتجان تحت تصنيف واحد: طلبٌ واحد للوحة، بلا تأشيرٍ مسبق، والجسم يحمل المعرّفين', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  // الشجرة لا تختار شيئاً من تلقاء نفسها.
  await expect(dialog.getByTestId('stocktake-scope-summary')).toHaveText('سيُجرد 0 منتج في 0 تصنيف');

  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  // الكسل قبل النقر: لا طلبَ منتجاتٍ واحد حتى يُفتح صنفٌ بعينه — ولو جُلبت كل
  // التصنيفات عند فتح النافذة لسقط هذا التأكيد.
  expect(handle.scopeProductRequests).toEqual([]);
  await dialog.getByRole('button', { name: 'منتجات إطارات' }).click();

  const panel = dialog.getByTestId('stocktake-scope-products');
  await expect(panel).toBeVisible();
  // تُفتح بلا أيّ تأشير: كلُّ منتجات التصنيف معروضة ولا واحد منها مشمول.
  await expect(panel.getByText('محدَّد 0 من 3')).toBeVisible();
  await expect(panel.getByRole('checkbox', { checked: true })).toHaveCount(0);

  // طلبٌ واحد للتصنيف — بالعلم نفسه الذي تُرسله الشجرة.
  const calls = handle.scopeProductRequests.filter(
    (url) => new URL(url).searchParams.get('category') === '14',
  );
  expect(calls).toHaveLength(1);
  expect(new URL(calls[0]).searchParams.get('include_inactive')).toBe('false');

  // البحث محليٌّ في المحمَّل: يرشّح الصفوف الظاهرة بلا طلبٍ جديد للخادم.
  await panel.getByLabel('ابحث في منتجات هذا التصنيف').fill('ميشلان');
  await expect(panel.getByText('ظاهر 1 من 3')).toBeVisible();
  await expect(panel.getByRole('checkbox')).toHaveCount(1);
  expect(handle.scopeProductRequests.filter(
    (url) => new URL(url).searchParams.get('category') === '14',
  )).toHaveLength(1);
  await panel.getByLabel('ابحث في منتجات هذا التصنيف').fill('');
  await expect(panel.getByRole('checkbox')).toHaveCount(3);

  await panel.getByRole('checkbox', { name: 'اختيار إطار 205/55 — ميشلان' }).check();
  await panel.getByRole('checkbox', { name: 'اختيار إطار 195/65 — بريدجستون' }).check();
  await expect(panel.getByText('محدَّد 2 من 3')).toBeVisible();
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد منتجان في تصنيفٍ واحد');

  await dialog.getByRole('button', { name: 'إنشاء', exact: true }).click();
  await expect.poll(() => handle.createdBodies.length).toBe(1);
  const scope = handle.createdBodies[0].scope as Record<string, unknown>;
  expect(scope.categories).toEqual([]);
  expect(scope.products).toEqual([105, 106]);
  expect(scope.uncategorized).toBe(false);

  // بندان في الورقة — لا ثلاثة.
  await expect(page.getByTestId('stocktake-line')).toHaveCount(2);
  // ولا كتالوجَ نُزّل في الطريق.
  expect(handle.productListCallsWithoutSearch).toEqual([]);
});

/**
 * عطبٌ حاجب أمسكته المراجعة: اللوحة تُرسم **داخل** `<ul role="tree" onKeyDown>`،
 * فكانت المسافة في بحثها تُلغى وتُؤشّر التصنيف النشط (فتُمحى المنتجات المختارة
 * صراحةً بـ`reconcileScopeProducts`)، والأسهم تخطف التركيز إلى الصفوف.
 */
test('لوحة المفاتيح: الكتابة في بحث اللوحة لا تُؤشّر التصنيف ولا تخطف التركيز', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  await dialog.getByRole('button', { name: 'منتجات إطارات' }).click();

  const panel = dialog.getByTestId('stocktake-scope-products');
  const search = panel.getByLabel('ابحث في منتجات هذا التصنيف');
  const categoryRow = dialog.getByRole('treeitem').filter({ hasText: 'إطارات' });

  await search.click();
  // مسافةٌ داخل النصّ: كانت تُلغى فلا تُكتب، وتُؤشّر التصنيف النشط.
  await search.pressSequentially('إطار 205');

  await expect(search).toHaveValue('إطار 205');
  await expect(categoryRow).toHaveAttribute('aria-checked', 'false');
  await expect(dialog.getByTestId('stocktake-scope-summary')).toHaveText('سيُجرد 0 منتج في 0 تصنيف');
  // والبحث عمل محلياً: صفٌّ واحد ظاهر من ثلاثة.
  await expect(panel.getByText('ظاهر 1 من 3')).toBeVisible();

  // الأسهم في الحقل لا تخطف التركيز إلى صفوف الشجرة.
  await search.press('ArrowDown');
  await search.press('Home');
  await expect(search).toBeFocused();

  // وEsc من زرّ «منتجات» تصل إلى النافذة فتُغلق: الإيقاف مقصورٌ على المسافة/Enter.
  await dialog.getByRole('button', { name: 'منتجات إطارات' }).focus();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
});

test('«تحديد الكل/مسح الكل» داخل التصنيف: تصنيفٌ واحد بلا منتجات، ثم لا منتجات أصلاً', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  await dialog.getByRole('button', { name: 'منتجات إطارات' }).click();
  const panel = dialog.getByTestId('stocktake-scope-products');
  await expect(panel.getByText('محدَّد 0 من 3')).toBeVisible();

  // «الكل» يرقّي الاختيار إلى التصنيف نفسه: لا منتجاتَ صريحة في الجسم.
  await panel.getByRole('button', { name: 'تحديد الكل' }).click();
  await expect(panel.getByText('محدَّد 3 من 3')).toBeVisible();
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 3 منتجات في تصنيفٍ واحد');

  await dialog.getByRole('button', { name: 'إنشاء', exact: true }).click();
  await expect.poll(() => handle.createdBodies.length).toBe(1);
  const scope = handle.createdBodies[0].scope as Record<string, unknown>;
  expect(scope.categories).toEqual([14]);
  expect('products' in scope).toBe(false);

  // و«المسح» يُلغي التصنيف نفسه: صفر منتجات ⇒ «إنشاء» معطّل والسبب ظاهر.
  const again = await openNewModal(page);
  await goToScopeStep(again);
  await again.getByLabel('بحث التصنيفات').fill('إطارات');
  await again.getByRole('button', { name: 'منتجات إطارات' }).click();
  const panelAgain = again.getByTestId('stocktake-scope-products');
  await panelAgain.getByRole('button', { name: 'تحديد الكل' }).click();
  await expect(again.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 3 منتجات في تصنيفٍ واحد');

  await panelAgain.getByRole('button', { name: 'مسح الكل' }).click();
  await expect(again.getByTestId('stocktake-scope-summary')).toHaveText('سيُجرد 0 منتج في 0 تصنيف');
  await expect(again.getByText('لا منتجات في هذا الاختيار')).toBeVisible();
  await expect(again.getByRole('button', { name: 'إنشاء', exact: true })).toBeDisabled();
});

test('إلغاء منتج من تصنيف مؤشَّر: التصنيف «جزئي» والجسم يحمل الباقيات بلا تصنيفات', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  await dialog.getByRole('checkbox', { name: 'تحديد إطارات' }).check();
  const categoryRow = dialog.getByRole('treeitem').filter({ hasText: 'إطارات' });
  await expect(categoryRow).toHaveAttribute('aria-checked', 'true');

  await dialog.getByRole('button', { name: 'منتجات إطارات' }).click();
  const panel = dialog.getByTestId('stocktake-scope-products');
  await expect(panel.getByText('محدَّد 3 من 3')).toBeVisible();
  await panel.getByRole('checkbox', { name: 'اختيار إطار 215/60 — بيريللي' }).uncheck();

  // التصنيف ما عاد مشمولاً بكامله: مربّعٌ ناقص، والباقي منتجاتٌ صريحة.
  await expect(panel.getByText('محدَّد 2 من 3')).toBeVisible();
  await expect(categoryRow).toHaveAttribute('aria-checked', 'mixed');
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد منتجان في تصنيفٍ واحد');

  await dialog.getByRole('button', { name: 'إنشاء', exact: true }).click();
  await expect.poll(() => handle.createdBodies.length).toBe(1);
  const scope = handle.createdBodies[0].scope as Record<string, unknown>;
  expect(scope.categories).toEqual([]);
  expect(scope.products).toEqual([105, 106]);
});

test('منتج من «بدون تصنيف»: لوحةٌ بـcategory=none، والجسم يحمله بلا شمول التصنيف', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  // «غير الفعّالة» مشمولةٌ هنا: قائمة «بدون تصنيف» فيها صفٌّ معطَّل، فاختيار
  // منتجٍ واحدٍ لا يكمل القائمة فلا يُرقّى إلى شمول «بدون تصنيف» كلّه (ترقية ST-2A).
  await dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }).check();
  await dialog.getByRole('button', { name: 'منتجات بدون تصنيف' }).click();

  const panel = dialog.getByTestId('stocktake-scope-products');
  await expect(panel).toBeVisible();
  await expect(panel.getByText('محدَّد 0 من 2')).toBeVisible();
  // المنتج غير الفعّال معروضٌ بشارته لا مخفياً.
  await expect(panel).toContainText('غير فعّال');
  const noneCalls = handle.scopeProductRequests.filter(
    (url) => new URL(url).searchParams.get('category') === 'none',
  );
  expect(noneCalls).toHaveLength(1);
  expect(new URL(noneCalls[0]).searchParams.get('include_inactive')).toBe('true');

  await panel.getByRole('checkbox', { name: 'اختيار زيت محرك — موبيل' }).check();
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد منتجٌ واحد في تصنيفٍ واحد');

  await dialog.getByRole('button', { name: 'إنشاء', exact: true }).click();
  await expect.poll(() => handle.createdBodies.length).toBe(1);
  const scope = handle.createdBodies[0].scope as Record<string, unknown>;
  expect(scope.products).toEqual([108]);
  expect(scope.uncategorized).toBe(false);

  await expect(page.getByTestId('stocktake-line')).toHaveCount(1);
});

test('إطفاء «غير الفعّالة» يُسقط ما اختير منها صراحةً ويُعلن عدده', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  // بالعلم مشمولاً تُعرض «فلتر قديم» (103) — وهي غير فعّالة في اختيارها الصريح.
  await dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }).check();
  await dialog.getByLabel('بحث التصنيفات').fill('قطع غيار');
  await dialog.getByRole('button', { name: 'منتجات قطع غيار' }).click();
  const panel = dialog.getByTestId('stocktake-scope-products');
  await expect(panel.getByText('محدَّد 0 من 3')).toBeVisible();
  await panel.getByRole('checkbox', { name: 'اختيار فلتر قديم — مان' }).check();
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد منتجٌ واحد في تصنيفٍ واحد');

  // إطفاؤها: المنتج غير الفعّال يخرج من الاختيار، والقائمة تُعاد قراءتها نشطةً فقط.
  await dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }).uncheck();
  await expect(dialog.getByRole('status'))
    .toHaveText('استُبعد منتجٌ واحد غير فعّال من الاختيار');
  await expect(panel.getByText('محدَّد 0 من 2')).toBeVisible();
  await expect(dialog.getByTestId('stocktake-scope-summary')).toHaveText('سيُجرد 0 منتج في 0 تصنيف');
  await expect(dialog.getByRole('button', { name: 'إنشاء', exact: true })).toBeDisabled();

  // ولا اختيارَ صريحاً يُرسَل: لا إنشاء أصلاً.
  expect(handle.createdBodies).toHaveLength(0);
});

test('«تحديد الكل» في اللوحة يعمل على كل صفوف التصنيف ولو أخفى البحث بعضها', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  await dialog.getByRole('button', { name: 'منتجات إطارات' }).click();
  const panel = dialog.getByTestId('stocktake-scope-products');

  await panel.getByLabel('ابحث في منتجات هذا التصنيف').fill('ميشلان');
  await expect(panel.getByText('ظاهر 1 من 3')).toBeVisible();
  // «الكل» على التصنيف لا على المعروض: الصفّان المخفيّان مشمولان أيضاً.
  await panel.getByRole('button', { name: 'تحديد الكل' }).click();
  await expect(panel.getByText('محدَّد 3 من 3')).toBeVisible();
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 3 منتجات في تصنيفٍ واحد');
});

test('فشل جلب منتجات التصنيف: رسالةٌ ظاهرة و«إعادة المحاولة» تُنجحها', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  handle.setScopeProductFailure(500);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByLabel('بحث التصنيفات').fill('إطارات');
  await dialog.getByRole('button', { name: 'منتجات إطارات' }).click();

  const panel = dialog.getByTestId('stocktake-scope-products');
  await expect(panel.getByText(/تعذّر تحميل منتجات التصنيف/)).toBeVisible();
  await expect(panel.getByText('محدَّد 0 من 3')).not.toBeVisible();

  handle.setScopeProductFailure(null);
  await panel.getByRole('button', { name: 'إعادة المحاولة' }).click();
  await expect(panel.getByText('محدَّد 0 من 3')).toBeVisible();
  await expect(panel.getByRole('checkbox')).toHaveCount(3);
  // والاختيار ما زال صفراً: الفشل لم يُشّر شيئاً ولا أسقط شيئاً.
  await expect(dialog.getByTestId('stocktake-scope-summary')).toHaveText('سيُجرد 0 منتج في 0 تصنيف');
});

test('فتح الصفحة وفتح جردٍ لا يطلبان قائمة المنتجات بلا بحث', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  await expect(page.getByTestId('stocktake-line')).toHaveCount(3);
  // الكمية تُعرض نصّاً مطبَّعاً: «4.0000» من الخادم ⇒ «4».
  await expect(page.getByTestId('stocktake-count-105')).toHaveValue('4');
  // ولا زرَّ ترحيلٍ في صفّ القائمة: «فتح» وحده، والترحيل من الورقة بعد الحفظ.
  await expect(page.locator('tbody tr').filter({ hasText: 'JRD-0001' })
    .getByRole('button', { name: 'ترحيل' })).toHaveCount(0);
  // لا `getAllProducts` ولا أي تنزيل كتالوج: البنود من بطاقة الجرد وحدها.
  expect(handle.productListCallsWithoutSearch).toEqual([]);
});

test('412 عند الحفظ ⇒ «حدّث» ⇒ التعديل المحلي باقٍ والحفظ التالي يحمل التوكن الجديد', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  const originalEtag = handle.currentEtag();
  await page.getByTestId('stocktake-count-101').fill('7');

  // طرفٌ آخر حفظ قبلنا: التوكن تحرّك وبندٌ آخر تغيّر على الخادم.
  handle.setServerCounted(105, '9.0000');

  await page.getByTestId('stocktake-save').click();

  const stale = page.getByRole('dialog', { name: 'تغيّر الجرد منذ فتحته — حدّث' });
  await expect(stale).toBeVisible();
  await stale.getByRole('button', { name: 'تحديث' }).click();

  // تعديل المدير لم يُفقد، وقيمة الطرف الآخر ظهرت، والرسالة تقول ما جرى.
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');
  await expect(page.getByTestId('stocktake-count-105')).toHaveValue('9');
  await expect(page.getByText(/أُعيد تطبيق تعديلاتك على بندٍ واحد/)).toBeVisible();
  // الخاتم يتبع القيمة: المعدَّل محلياً «تعديلك»، وغيرُ المعدَّل خاتمُ العامل بالتاريخ والوقت.
  const editedRow = page.getByTestId('stocktake-line').filter({ hasText: 'فلتر زيت' });
  await expect(editedRow).toContainText('تعديلك — غير محفوظ');
  const workerRow = page.getByTestId('stocktake-line').filter({ hasText: 'ميشلان' });
  await expect(workerRow).toContainText('مدير آخر');
  await expect(workerRow).toContainText(/\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/);

  const etagAfterRefresh = handle.currentEtag();
  await page.getByTestId('stocktake-save').click();
  await expect.poll(() => handle.saveRequests.length).toBe(2);

  // الأوّل رُفض بالتوكن الأصلي، والثاني يحمل توكن النسخة التي رآها المستخدم.
  expect(handle.saveRequests[0].ifMatch).toBe(originalEtag);
  expect(handle.saveRequests[1].ifMatch).toBe(etagAfterRefresh);
  expect(handle.saveRequests[1].body.lines).toEqual([
    { product: 101, counted_quantity: '7' },
  ]);
});

test('«تحديث»: ملاحظات الخادم الجديدة تصل، وعدُّ المستخدم المعدَّل يبقى ويُحفظ معها', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  await page.getByTestId('stocktake-count-101').fill('7');
  // المستخدم لم يلمس الرأس: ملاحظاتُ الخادم الجديدة هي الحاكمة.
  handle.setServerNotes('ملاحظات محدَّثة على الخادم');

  await page.locator('[data-testid="stocktake-sheet"]')
    .getByRole('button', { name: 'تحديث', exact: true }).click();

  await expect(page.getByTestId('stocktake-notes')).toHaveValue('ملاحظات محدَّثة على الخادم');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');

  await page.getByTestId('stocktake-save').click();
  await expect.poll(() => handle.saveRequests.length).toBe(1);
  expect(handle.saveRequests[0].body.notes).toBe('ملاحظات محدَّثة على الخادم');
});

test('نافذة الترحيل تعرض غير المعدود، والجسم يحمل uncounted_as_zero عند اختياره', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  await page.getByTestId('stocktake-post').click();

  const dialog = page.getByRole('dialog', { name: 'ترحيل الجرد' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('post-uncounted-count')).toHaveText('2');

  await dialog.getByRole('checkbox', { name: /اعتبرها صفراً/ }).check();
  await dialog.getByRole('button', { name: 'ترحيل', exact: true }).click();

  await expect.poll(() => handle.postRequests.length).toBe(1);
  expect(handle.postRequests[0]).toEqual({ uncounted_as_zero: true });
});

test('البحث و«غير المعدود فقط» يرشّحان البنود الظاهرة، والإضافة تبحث في الخادم', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  await expect(page.getByTestId('stocktake-line')).toHaveCount(3);

  await page.getByTestId('stocktake-search').fill('إطار');
  await expect(page.getByTestId('stocktake-line')).toHaveCount(2);

  await page.getByTestId('stocktake-filter').selectOption('uncounted');
  await expect(page.getByTestId('stocktake-line')).toHaveCount(1);
  await expect(page.getByTestId('stocktake-line')).toContainText('بريدجستون');

  // منتقي الإضافة لا يفلتر كتالوجاً محلياً: الكتابة تُطلق بحثاً خادمياً بالنصّ نفسه.
  await page.getByPlaceholder('اكتب الاسم أو الرمز…').fill('فلتر');
  await expect.poll(() => handle.productListCallsWithSearch.some(
    (url) => new URL(url).searchParams.get('search') === 'فلتر',
  )).toBe(true);
});

test('كمية غير صالحة: الخانة مُعلَّمة والزرّان معطّلان والسبب ظاهر', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  const input = page.getByTestId('stocktake-count-101');
  await input.fill('-3');
  await expect(input).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('stocktake-invalid-lines'))
    .toHaveText('بندٌ واحد بكمية غير صالحة');
  await expect(page.getByTestId('stocktake-save')).toBeDisabled();
  await expect(page.getByTestId('stocktake-post')).toBeDisabled();
});

test('مسودّة أقدم من الخادم: شريط «تغيّر المستند» ثم «استعرض مسودتي» يُعيدها على بنود الخادم', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  // مسودّةٌ محلية: تعديل على 101 وحذف 106.
  await page.getByTestId('stocktake-count-101').fill('7');
  await page.getByTestId('stocktake-line').filter({ hasText: 'بريدجستون' })
    .getByRole('button', { name: /حذف بند/ }).click();
  await expect(page.getByTestId('draft-saved-indicator')).toBeVisible();
  // الكتابة مؤجَّلة 500ms بعد آخر تغيير: ننتظر وصول الحذف فعلاً إلى IndexedDB،
  // لا مجرّد ظهور مؤشّر الكتابة الأولى.
  await expect.poll(async () => {
    const draft = await readStocktakeDraft(page, '900');
    if (!draft) return 'missing';
    const line = draft.payload.lines?.find((item) => item.product === 101);
    return `${draft.payload.v}|${draft.payload.docId}`
      + `|${(draft.payload.removedIds ?? []).join(',')}|${line?.counted_quantity ?? ''}`;
  }).toBe('3|900|106|7');

  // وبينهما عدّ عاملٌ آخر البند 105 على الخادم: ختمُ المستند وتوكنُه تحرّكا معه
  // (الخادم يشتقّ ETag من `updated_at`)، فالمسودّة لم تعد مؤهَّلةً لاستعادةٍ صامتة.
  handle.setServerCounted(105, '9.0000');

  await openFirstSheet(page);
  const banner = page.getByTestId('draft-restored-banner');
  await expect(banner).toContainText('تغيّر المستند بعد مسودتك');
  await expect(page.getByTestId('stocktake-count-105')).toHaveValue('9');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('');

  // «استعرض مسودتي» يعيدها على لقطة الخادم لا على مرجعياتها القديمة (105 كان 4).
  await page.getByTestId('draft-stale-preview').click();
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');
  await expect(page.getByTestId('stocktake-count-105')).toHaveValue('9');
  await expect(page.getByText(/أُعيد تطبيق تعديلاتك على بندين/)).toBeVisible();
  await expect(page.getByTestId('stocktake-line')).toHaveCount(2);

  await page.getByTestId('stocktake-save').click();
  await expect.poll(() => handle.saveRequests.length).toBe(1);
  const body = handle.saveRequests[0].body;
  expect(body.replace_lines).toBe(true);
  const lines = body.lines as Array<{ product: number; counted_quantity: string | null }>;
  expect(lines).toContainEqual({ product: 101, counted_quantity: '7' });
  // قيمة العامل الجديدة — لا قيمة المسودّة القديمة (4).
  expect(lines).toContainEqual({ product: 105, counted_quantity: '9' });
  expect(lines).not.toContainEqual({ product: 105, counted_quantity: '4' });
  expect(lines.some((line) => line.product === 106)).toBe(false);
});

test('استعراض مسودّةٍ عدّلت بنداً فقط: ملاحظات الخادم الجديدة تبقى وعدّ المسودّة يعود', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-count-101').fill('7');
  await expect.poll(async () => {
    const draft = await readStocktakeDraft(page, '900');
    return draft?.payload.lines?.find((item) => item.product === 101)?.counted_quantity ?? '';
  }).toBe('7');

  // المسودّة كتبت الرأس كما كان (المستخدم لم يمسّه)، ثم تغيّر على الخادم.
  handle.setServerNotes('ملاحظات محدَّثة على الخادم');
  await openFirstSheet(page);

  await expect(page.getByTestId('draft-restored-banner'))
    .toContainText('تغيّر المستند بعد مسودتك');
  await expect(page.getByTestId('stocktake-notes')).toHaveValue('ملاحظات محدَّثة على الخادم');

  await page.getByTestId('draft-stale-preview').click();
  // الرأس غير المعدَّل يأخذ قيمة الخادم، والبند الذي عدّله المستخدم يعود.
  await expect(page.getByTestId('stocktake-notes')).toHaveValue('ملاحظات محدَّثة على الخادم');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');
});

test('«استعرض مسودتي» مع تعديلٍ غير محفوظ يسأل قبل الاستبدال', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-count-101').fill('7');
  await expect.poll(async () => (await readStocktakeDraft(page, '900'))?.payload.lines
    ?.find((item) => item.product === 101)?.counted_quantity).toBe('7');

  handle.setServerCounted(105, '9.0000');
  await openFirstSheet(page);
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible();

  // تعديلٌ جديد في هذه الجلسة: استعراض المسودّة يستبدله — سؤالٌ صريح أولاً.
  await page.getByTestId('stocktake-count-101').fill('8');
  await page.getByTestId('draft-stale-preview').click();

  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('استعراض هذه المسودّة يستبدله');
  await dialog.getByRole('button', { name: 'إلغاء' }).click();
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('8');
});

test('مسودّة أحدث من الخادم تُستعاد تلقائياً عند إعادة الفتح', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-count-101').fill('7');
  await expect.poll(async () => {
    const draft = await readStocktakeDraft(page, '900');
    return draft?.payload.lines?.find((item) => item.product === 101)?.counted_quantity ?? '';
  }).toBe('7');

  await openFirstSheet(page);
  // الخادم لم يتغيّر: الاستعادة صامتة، والشريط يخبر أنّها مسودّة.
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');
  await expect(page.getByTestId('draft-restored-banner'))
    .toContainText('استُعيدت مسودةٌ غير محفوظة');
});

test('مسودّة الإصدار الثاني (قبل رفع الإصدار) لا تُطبَّق على الجرد', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page); // ينشئ قاعدة IndexedDB
  await seedStocktakeDraft(page, {
    key: '1:stocktake:doc:900',
    tenant_id: 1,
    doc_type: 'stocktake',
    doc_id: '900',
    tab_id: 'legacy-tab',
    doc_updated_at: '2026-10-20T08:00:00Z',
    updated_at: '2026-10-20T08:10:00.000Z',
    data: JSON.stringify({
      v: 2,
      docId: 900,
      date: '2026-10-20',
      warehouse: '',
      notes: 'مسودّة قديمة',
      lines: [{
        product: 101, product_name: 'فلتر زيت — مان', product_sku: 'SP-101',
        product_category: 11, product_quantity_on_hand: '10.0000',
        product_is_active: true, counted_quantity: '77', counted_by_name: '',
        counted_at: null, system_quantity: null, variance: null,
      }],
      removedIds: [],
    }),
  });

  await openFirstSheet(page);
  // الحمولة القديمة لا تُطبَّق **ولا تُعرض**: الإصدار الحالي وحده يُعتمد،
  // فلا يرى المستخدم «استعرض مسودتي» لشيءٍ لن يُطبَّق.
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('');
  await expect(page.getByTestId('stocktake-count-105')).toHaveValue('4');
  await expect(page.getByTestId('draft-restored-banner')).toHaveCount(0);
});

test('شريط مسودّة جردٍ سابق لا يبقى فوق الجرد التالي', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-count-101').fill('7');
  await expect.poll(async () => (await readStocktakeDraft(page, '900'))?.payload.v).toBe(3);
  handle.setServerCounted(105, '9.0000');

  await openFirstSheet(page);
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible();
  await openRow(page, 'JRD-0002');

  // الشريط يخصّ A — لا يبقى فوق B، ولا بيانات A على ورقة B.
  await expect(page.getByTestId('stocktake-sheet')).toContainText('تعديل مسودة جرد #950');
  await expect(page.getByTestId('draft-restored-banner')).toHaveCount(0);
  await expect(page.getByTestId('stocktake-line')).toHaveCount(2);
  await expect(page.getByTestId('stocktake-count-101')).toHaveCount(0);
  await expect(page.getByTestId('stocktake-count-107')).toHaveValue('2');
});

test('فتح جردٍ آخر أو «جرد جديد» مع تعديلاتٍ غير محفوظة يسأل أولاً', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-count-101').fill('7');

  // صفٌّ آخر: سؤالٌ صريح، والإلغاء يُبقي الورقة كما هي.
  await openHistory(page);
  await page.locator('tbody tr').filter({ hasText: 'JRD-0002' })
    .getByRole('button', { name: 'فتح' }).click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('لديك تعديلات غير محفوظة على هذا الجرد — تجاهلها والمتابعة؟');
  await dialog.getByRole('button', { name: 'إلغاء' }).click();
  await expect(page.getByTestId('stocktake-sheet')).toContainText('تعديل مسودة جرد #900');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');

  // و«جرد جديد» كذلك قبل فتح نافذته.
  await page.getByRole('button', { name: 'جرد جديد' }).click();
  await expect(page.getByRole('alertdialog')).toBeVisible();
  await page.getByRole('alertdialog').getByRole('button', { name: 'إلغاء' }).click();
  await expect(page.getByRole('dialog', { name: 'جرد جديد' })).toHaveCount(0);
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');

  // والمتابعة تفتح الجرد الآخر فعلاً.
  await openHistory(page);
  await page.locator('tbody tr').filter({ hasText: 'JRD-0002' })
    .getByRole('button', { name: 'فتح' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'تجاهلها والمتابعة' }).click();
  await expect(page.getByTestId('stocktake-sheet')).toContainText('تعديل مسودة جرد #950');
  await expect(page.getByTestId('stocktake-count-101')).toHaveCount(0);
});

test('فشل العدّادات: الشريط في الوضعين، واليدوي مسموح، وخانة «غير الفعّالة» واحدة', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  handle.setScopeCountsFailure(true);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);

  // الوضع الافتراضي «تصنيفات محدّدة»: الخطأ ظاهر مع «إعادة المحاولة».
  await expect(dialog.getByRole('button', { name: /إعادة المحاولة/ })).toBeVisible();
  await expect(dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }))
    .toHaveCount(1);

  // و«كل المنتجات»: الشريط نفسه، والنصّ التعريفي صادق، والخانة ما زالت واحدة.
  await dialog.getByRole('radio', { name: /كل المنتجات/ }).check();
  await expect(dialog.getByRole('button', { name: /إعادة المحاولة/ })).toBeVisible();
  await expect(dialog.getByText(/كل منتجٍ غير خدمي — النشطة فقط/)).toBeVisible();
  await expect(dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }))
    .toHaveCount(1);
  await expect(dialog.getByRole('button', { name: 'إنشاء', exact: true })).toBeDisabled();

  // واليدوي لا يعتمد على العدّادات إطلاقاً.
  await dialog.getByRole('radio', { name: /يدوي/ }).check();
  await expect(dialog.getByRole('button', { name: /إعادة المحاولة/ })).toBeHidden();
  await expect(dialog.getByRole('button', { name: 'إنشاء', exact: true })).toBeEnabled();
});

test('ردّ العدّادات المتأخّر لا يغلب الأحدث، و«إنشاء» معطّل أثناء التحميل', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  // طلبان حقيقيّان متأخّران — أوّلُهما عند فتح الخطوة (ومع StrictMode طلبُ
  // التركيب الثاني أيضاً)، والثاني بهزّة «غير الفعّالة» الأولى. والطلب الثالث
  // فوريّ فيسبقهما؛ فلا يعتمد الاختبار على تركيب المكوّن مرّتين.
  handle.delayNextScopeCounts(2500);
  handle.delayNextScopeCounts(2500);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const dialog = await openNewModal(page);
  await goToScopeStep(dialog);
  await dialog.getByRole('radio', { name: /كل المنتجات/ }).check();
  // طلبٌ متأخّر ما زال معلّقاً: لا «إنشاء» على عدّاداتٍ لم تصل.
  await expect(dialog.getByRole('button', { name: 'إنشاء', exact: true })).toBeDisabled();

  await dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }).check();
  await dialog.getByRole('checkbox', { name: 'شمل المنتجات غير الفعّالة' }).uncheck();

  // الطلب الأخير (بلا غير الفعّالة) حكم: 7 منتجات في 4 تصنيفات.
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 7 منتجات في 4 تصنيفات');
  await expect(dialog.getByRole('button', { name: 'إنشاء', exact: true })).toBeEnabled();

  // ننتظر هبوط الردّين المتأخّرين فعلاً (لا مهلةً زمنية): الأحدث يبقى الحاكم.
  await expect.poll(() => handle.scopeCountsDelayedAnswered).toBe(2);
  await expect(dialog.getByTestId('stocktake-scope-summary'))
    .toHaveText('سيُجرد 7 منتجات في 4 تصنيفات');
});

test('«تحديث» يعطّل خانات العدّ والحذف والإضافة وحقول الرأس حتى ينتهي الطلب', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  const deleteButton = page.getByTestId('stocktake-line').first()
    .getByRole('button', { name: /حذف بند/ });

  handle.delayNextStocktakeGet(1200);
  await page.locator('[data-testid="stocktake-sheet"]')
    .getByRole('button', { name: 'تحديث', exact: true }).click();

  // الرأس بدوره معطَّل: الدمج يقرأ الحالة مرّةً واحدة فلا يقع تعديلٌ بين القراءة والتطبيق.
  const sheet = page.getByTestId('stocktake-sheet');
  const notesField = page.getByTestId('stocktake-notes');
  const dateField = sheet.locator('input[type="date"]');
  const warehouseField = sheet.locator('select').first();
  const addPicker = page.getByPlaceholder('اكتب الاسم أو الرمز…');
  await expect(page.getByTestId('stocktake-count-101')).toBeDisabled();
  await expect(deleteButton).toBeDisabled();
  await expect(notesField).toBeDisabled();
  await expect(dateField).toBeDisabled();
  await expect(warehouseField).toBeDisabled();
  await expect(addPicker).toBeDisabled();
  await expect(page.getByTestId('stocktake-count-101')).toBeEnabled();
  await expect(deleteButton).toBeEnabled();
  await expect(notesField).toBeEnabled();
  await expect(dateField).toBeEnabled();
  await expect(warehouseField).toBeEnabled();
  await expect(addPicker).toBeEnabled();
});

test('ردّ «تحديث» المتأخّر لجردٍ تُرك لا يكتب فوق الجرد المفتوح بعده', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page); // A = 900
  const sheet = page.getByTestId('stocktake-sheet');
  const refreshButton = sheet.getByRole('button', { name: 'تحديث', exact: true });

  handle.delayNextStocktakeGet(1500);
  await refreshButton.click();
  await expect(refreshButton).toBeDisabled();

  // قراءة A معلّقة: صفوف القائمة لا يعطّلها `sheetBusy` — نفتح B (950).
  await openRow(page, 'JRD-0002');
  await expect(sheet).toContainText('تعديل مسودة جرد #950');
  await expect(page.getByTestId('stocktake-line')).toHaveCount(2);

  // زرّ «تحديث» يعود بعد أن يُعالَج ردّ A (يُفكّ العلم في كل الأحوال) — بلا مهلة زمنية.
  await expect(refreshButton).toBeEnabled();

  // بعد وصول ردّ A: الورقة ما زالت B — رقمها وملاحظاتها وبنودها وتوكنها.
  await expect(sheet).toContainText('تعديل مسودة جرد #950');
  await expect(page.getByTestId('stocktake-notes')).toHaveValue('');
  await expect(page.getByTestId('stocktake-line')).toHaveCount(2);
  await expect(page.getByTestId('stocktake-count-101')).toHaveCount(0);
  await expect(page.getByTestId('stocktake-count-107')).toHaveValue('2');
  await expect(page.getByText('✓ حُدِّث الجرد')).toHaveCount(0);

  const tokenOfB = handle.currentEtag(950);
  await page.getByTestId('stocktake-count-107').fill('5');
  await page.getByTestId('stocktake-save').click();
  await expect.poll(() => handle.saveRequests.length).toBe(1);
  // الحفظ يحمل توكن B الذي رآه المستخدم، لا توكن A.
  expect(handle.saveRequests[0].ifMatch).toBe(tokenOfB);
  expect(tokenOfB).not.toBe(handle.currentEtag(900));
});

test('«تحديث» ثم «استعرض مسودتي» أثناء القراءة: رأس المسودّة لا يُكتب فوقه رأسُ ما قبل الطلب', async ({ page }) => {
  const handle = await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-notes').fill('ملاحظاتي المحلية');
  await page.getByTestId('stocktake-count-101').fill('7');
  await expect.poll(async () => {
    const draft = await readStocktakeDraft(page, '900');
    return draft?.payload.lines?.find((item) => item.product === 101)?.counted_quantity ?? '';
  }).toBe('7');

  // تغيّر المستند بعد مسودّتي (ملاحظات الخادم) ⇒ شريط «تغيّر المستند» لا استعادة صامتة.
  handle.setServerNotes('ملاحظات الخادم الأحدث');
  await openFirstSheet(page);
  await expect(page.getByTestId('draft-restored-banner'))
    .toContainText('تغيّر المستند بعد مسودتك');
  await expect(page.getByTestId('stocktake-notes')).toHaveValue('ملاحظات الخادم الأحدث');

  const sheet = page.getByTestId('stocktake-sheet');
  const refreshButton = sheet.getByRole('button', { name: 'تحديث', exact: true });
  handle.delayNextStocktakeGet(1500);
  await refreshButton.click();
  await expect(refreshButton).toBeDisabled();
  // «استعرض مسودتي» غير معطَّل أثناء القراءة: الرأس والبنود تتبدّل قبل وصول الردّ.
  await page.getByTestId('draft-stale-preview').click();
  await expect(page.getByTestId('stocktake-notes')).toHaveValue('ملاحظاتي المحلية');

  await expect(refreshButton).toBeEnabled();
  // الردّ المتأخّر يدمج على الحالة الحيّة: ملاحظات المسودّة المعدَّلة تبقى كالبنود.
  await expect(page.getByTestId('stocktake-notes')).toHaveValue('ملاحظاتي المحلية');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');
});

test('«إغلاق» مع تعديلٍ غير محفوظ يسأل، وتأكيد التجاهل يمحو المسودّة المحلية', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  const sheet = page.getByTestId('stocktake-sheet');
  const closeButton = sheet.getByRole('button', { name: 'إغلاق', exact: true });

  await page.getByTestId('stocktake-count-101').fill('7');
  // المسودّة وصلت IndexedDB فعلاً — كي يكون «محوها» لاحقاً قياساً لا غياباً أصلياً.
  await expect.poll(async () => (await readStocktakeDraft(page, '900'))?.payload.lines
    ?.find((item) => item.product === 101)?.counted_quantity).toBe('7');

  // الإلغاء يُبقي الورقة والقيمة.
  await closeButton.click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('لديك تعديلات غير محفوظة على هذا الجرد — تجاهلها والمتابعة؟');
  await dialog.getByRole('button', { name: 'إلغاء' }).click();
  await expect(sheet).toBeVisible();
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('7');

  // والتأكيد يغلق الورقة ويمحو مسودّتها.
  await closeButton.click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'تجاهلها والمتابعة' }).click();
  await expect(sheet).toHaveCount(0);
  await expect.poll(() => readStocktakeDraft(page, '900')).toBeNull();

  // إعادة فتح الجرد نفسه: قيمة الخادم، ولا شريط مسودّة.
  await openRow(page, 'JRD-0001');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('');
  await expect(page.getByTestId('stocktake-count-105')).toHaveValue('4');
  await expect(page.getByTestId('draft-restored-banner')).toHaveCount(0);
});

test('«إغلاق» بلا تعديل يغلق مباشرةً بلا سؤال', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  await page.getByTestId('stocktake-sheet').getByRole('button', { name: 'إغلاق', exact: true }).click();
  await expect(page.getByTestId('stocktake-sheet')).toHaveCount(0);
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
});

test('فتح جردٍ آخر أو «جرد جديد» بعد تأكيد التجاهل يمحو مسودّة الجرد المتروك', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);
  const draftValue = async () => (await readStocktakeDraft(page, '900'))?.payload.lines
    ?.find((item) => item.product === 101)?.counted_quantity ?? null;

  // صفٌّ آخر.
  await page.getByTestId('stocktake-count-101').fill('7');
  await expect.poll(draftValue).toBe('7');
  await openRow(page, 'JRD-0002');
  await page.getByRole('alertdialog').getByRole('button', { name: 'تجاهلها والمتابعة' }).click();
  await expect(page.getByTestId('stocktake-sheet')).toContainText('تعديل مسودة جرد #950');
  await expect.poll(draftValue).toBeNull();

  // و«جرد جديد»: تُمحى عند استبدال الورقة فعلاً (الإنشاء) لا عند السؤال وحده.
  await openRow(page, 'JRD-0001');
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('');
  await page.getByTestId('stocktake-count-101').fill('8');
  await expect.poll(draftValue).toBe('8');
  await page.getByRole('button', { name: 'جرد جديد' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'تجاهلها والمتابعة' }).click();
  const dialog = page.getByRole('dialog', { name: 'جرد جديد' });
  await expect(dialog).toBeVisible();
  await goToScopeStep(dialog);
  await dialog.getByRole('radio', { name: /يدوي/ }).check();
  await dialog.getByRole('button', { name: 'إنشاء', exact: true }).click();
  await expect(page.getByTestId('stocktake-sheet')).toContainText('تعديل مسودة جرد #901');
  await expect.poll(draftValue).toBeNull();
});

test('حقل البحث يأخذ عرض الشاشة الضيّقة بدل أن يُقتطع', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await installStocktakeApiStubs(page);
  await openFirstSheet(page);

  const box = await page.getByTestId('stocktake-search').boundingBox();
  expect(box).not.toBeNull();
  // w-56 القديمة = 224px؛ العرض الكامل داخل الورقة أكبر من ذلك بكثير.
  expect(box?.width ?? 0).toBeGreaterThan(280);
});

/**
 * TKT-ST-3 — الجرود القديمة كانت تُقرأ بنوداً للجرد المفتوح: تُلصق تحته بلا
 * عنوان. القائمة صارت قسماً بعنوانه «سجل الجرد»، مطويّاً حين تُفتح ورقة، وزرُّه
 * يقلب الافتراض حتى **حدث** الانتقال التالي: فتحُ ورقة — ولو كانت الثانية —
 * أو إغلاقُها. والجدول نفسه لم يتغيّر: نفس الصفوف والأعمدة والنصوص.
 */
test('«سجل الجرد» قسمٌ مستقلّ: مفتوحٌ بلا ورقة، مطويٌّ حين تُفتح، وزرُّه يغلب الافتراض', async ({ page }) => {
  await installStocktakeApiStubs(page);
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');

  const history = page.getByRole('region', { name: 'سجل الجرد' });
  const toggle = history.getByRole('button', { name: /السجل/ });
  const firstRow = history.locator('tbody tr').first();

  // بلا ورقة مفتوحة: قسمٌ بعنوانه وعدده وتلميحه، وقائمته ظاهرة.
  await expect(history).toBeVisible();
  await expect(history.getByRole('heading', { name: /سجل الجرد/ })).toContainText('(3)');
  await expect(history).toContainText('الأحدث أولاً');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(toggle).toHaveText('طيّ السجل');
  await expect(firstRow).toContainText('#900');

  // فتح جرد ⇒ الافتراضي مطويّ، وصفوف السجل غير مرئية فلا تُقرأ بنوداً للورقة.
  await openRow(page, 'JRD-0001');
  await expect(page.getByTestId('stocktake-sheet')).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toHaveText('إظهار السجل');
  await expect(firstRow).toBeHidden();

  // نقرُ الزرّ يفتحها — واختيارُ المستخدم يغلب الافتراضي ما دامت الورقة مفتوحة.
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(toggle).toHaveText('طيّ السجل');
  await expect(firstRow).toBeVisible();

  // فتحُ ورقةٍ **ثانية** حدثٌ ثانٍ يُصفّر الاختيار — وإلا بقي السجل مفتوحاً تحت
  // الورقة الجديدة، وهو العطب نفسه الذي جاءت التذكرة لإصلاحه.
  await openRow(page, 'JRD-0002');
  await expect(page.getByTestId('stocktake-sheet')).toContainText('تعديل مسودة جرد #950');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(firstRow).toBeHidden();

  // وطِيُّه بالزرّ ثم «إغلاق» الورقة: حدثُ الإغلاق يُصفّر اختيارَ «مطوي» فيعود
  // الافتراضي «مفتوحاً» — لا أن يبقى ما اختاره المستخدم الورقةَ السابقة.
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await page.getByTestId('stocktake-sheet')
    .getByRole('button', { name: 'إغلاق', exact: true }).click();
  await expect(page.getByTestId('stocktake-sheet')).toHaveCount(0);
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(firstRow).toBeVisible();
});
