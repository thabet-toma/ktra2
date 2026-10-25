import { test, expect, type Browser, type Page } from '@playwright/test';
import {
  installPublicCountStubs,
  installStocktakeApiStubs,
  type CountApiBackend,
} from './stocktake-stubs';

/**
 * K4 — رابط عدّ الموظف من طرفٍ إلى طرف.
 *
 * المحاكي يردّ بأشكال الخادم نفسها ويرفض ما يرفضه: اسم فارغ 400، أيام خارج
 * 1/3/7 ⇒ 400، سطرٌ خارج نطاق الرابط ⇒ `ignored` بلا خطأ، جردٌ مُرحَّل/رابطٌ
 * مُبطَل ⇒ 410. والصفحة العامة تُفتح في سياقٍ جديد **بلا جلسة** — لا توكن ولا
 * كوكيز — لأن الرابط وحده هو التصريح.
 */

const openSheet = async (page: Page, number: string) => {
  await page.goto('/stocktake');
  await page.waitForLoadState('networkidle');
  const row = page.locator('tbody tr').filter({ hasText: number }).first();
  await row.getByRole('button', { name: 'فتح' }).click();
  await expect(page.getByTestId('stocktake-sheet')).toBeVisible();
};

/** «سجل الجرد» مطويٌّ حين تكون ورقةٌ مفتوحة — يُفتح قبل النقر على صفٍّ منه. */
const openHistory = async (page: Page) => {
  const toggle = page.getByRole('region', { name: 'سجل الجرد' })
    .getByRole('button', { name: /السجل/ });
  if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
};

const openCountDialog = async (page: Page) => {
  await page.getByTestId('stocktake-count-links').click();
  const dialog = page.getByRole('dialog', { name: 'رابط للموظف' });
  await expect(dialog).toBeVisible();
  return dialog;
};

const createLink = async (page: Page, name = 'أحمد') => {
  const dialog = await openCountDialog(page);
  // القائمة تُجلب عند فتح النافذة؛ ننتظر انتهاء الجلب (صفوفاً كانت أو فراغاً)
  // قبل الإنشاء، فلا يختلط جلبُها الأول بدورةٍ تلقائية لاحقة في القياس.
  await expect(dialog.getByText('جارٍ تحميل الروابط…')).toHaveCount(0);
  // الاسم فارغ ⇒ الزر معطّل — لا رابطَ بلا اسم عادّ.
  await expect(dialog.getByTestId('count-link-create')).toBeDisabled();
  await dialog.getByTestId('count-link-counter-name').fill(name);
  await expect(dialog.getByTestId('count-link-create')).toBeEnabled();
  await dialog.getByTestId('count-link-create').click();
  await expect(dialog.getByTestId('count-link-created')).toBeVisible();
  const url = await dialog.getByTestId('count-link-url').inputValue();
  const token = new URL(url).pathname.split('/').pop() ?? '';
  expect(token).toMatch(/^count-token-\d+$/);
  return { dialog, token, url };
};

/** رابطٌ مقيَّد بتصنيف «قطع غيار» (11) — لا يشمل بند «إطار ميشلان» (14). */
const createScopedLink = async (page: Page, name = 'أحمد') => {
  const dialog = await openCountDialog(page);
  await expect(dialog.getByText('جارٍ تحميل الروابط…')).toHaveCount(0);
  await dialog.getByTestId('count-link-counter-name').fill(name);
  await dialog.getByRole('button', { name: 'تقسيم على أكثر من موظف؟' }).click();
  const tree = dialog.getByRole('tree', { name: 'شجرة تصنيفات الجرد' });
  await tree.getByRole('checkbox', { name: 'تحديد قطع غيار' }).check();
  await expect(dialog.getByTestId('count-link-create')).toBeEnabled();
  await dialog.getByTestId('count-link-create').click();
  await expect(dialog.getByTestId('count-link-created')).toBeVisible();
  const url = await dialog.getByTestId('count-link-url').inputValue();
  const token = new URL(url).pathname.split('/').pop() ?? '';
  expect(token).toMatch(/^count-token-\d+$/);
  return { dialog, token };
};

const openPublicPage = async (
  browser: Browser,
  backend: CountApiBackend,
  token: string,
  viewport?: { width: number; height: number },
  options: { clock?: boolean } = {},
) => {
  const context = await browser.newContext(viewport ? { viewport } : {});
  const page = await context.newPage();
  await installPublicCountStubs(page, backend);
  if (options.clock) await page.clock.install();
  await page.goto(`/count/${token}`);
  return { context, page };
};

const closeDialog = async (page: Page) => {
  await page.getByRole('dialog', { name: 'رابط للموظف' })
    .getByRole('button', { name: 'إغلاق', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'رابط للموظف' })).toHaveCount(0);
};

test('المدير ينشئ رابطاً — الموظف يعدّ برقمٍ عربي — الورقة تعرض الكميتين واسم العادّ', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');

  const { dialog, token, url } = await createLink(page, 'أحمد');
  expect(url).toBe(`${new URL(page.url()).origin}/count/${token}`);

  // الصف «لم يبدأ» وتقدّمه صفر — والحالة من `status` و`progress.counted`.
  const row = dialog.getByTestId('count-link-row').filter({ hasText: 'أحمد' });
  await expect(row).toBeVisible();
  await expect(row).toContainText('لم يبدأ');
  await expect(row).toContainText('0 / 3');
  await expect(row).toContainText('كل الجرد');
  await expect(row.getByRole('button', { name: 'نسخ' })).toBeVisible();
  await expect(row.getByRole('link', { name: 'واتساب' })).toBeVisible();

  await closeDialog(page);

  // المحاكي يُسرّب حقولاً مالية في الحمولة العامة: الصفحة ترسم قائمةً ثابتة
  // فما يصل لا يُعرض — لا حقلاً ولا رقماً.
  handle.countBackend.leakMoneyFields = true;
  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  // سياقٌ جديد بلا جلسة: لا توكن ولا كوكيز — الصفحة تعمل بالرابط وحده.
  expect(await context.cookies()).toEqual([]);
  expect(await publicPage.evaluate(() => localStorage.getItem('token'))).toBeNull();

  await expect(publicPage.getByText('العادّ:')).toContainText('أحمد');
  await expect(publicPage.getByText(/تكلفة|سعر|قيمة/)).toHaveCount(0);
  // الحمولة حملت الحقول فعلاً — الغياب في الشاشة قرارُ عرضٍ لا حظُّ حمولةٍ نظيفة.
  expect(handle.countBackend.publicLeaks).toBeGreaterThan(0);
  for (const money of ['9.99', '19.50', '99.00']) {
    await expect(publicPage.getByText(money)).toHaveCount(0);
  }
  await expect(publicPage.getByTestId('count-row-6')).toContainText('فلتر زيت');

  // رقمان معاً: واحدٌ عربي-هندي بفاصلة عشرية عربية، والآخر ASCII.
  await publicPage.getByTestId('count-input-6').fill('١٢٫٥');
  await publicPage.getByTestId('count-input-7').fill('7');

  await expect.poll(() => handle.countBackend.publicWrites.length).toBe(1);
  const write = handle.countBackend.publicWrites[0];
  expect(write.entries).toEqual([
    { line_id: 6, counted_quantity: '12.5' },
    { line_id: 7, counted_quantity: '7' },
  ]);
  await expect(publicPage.getByTestId('count-state-6')).toContainText('✓');
  await expect(publicPage.getByTestId('count-state-7')).toContainText('✓');

  // ورقة المدير: «تحديث» يقرأ عدّ الموظف ويختم السطر باسمه.
  await page.getByTestId('stocktake-sheet')
    .getByRole('button', { name: 'تحديث', exact: true }).click();
  await expect(page.getByTestId('stocktake-count-101')).toHaveValue('12.5');
  await expect(page.getByTestId('stocktake-count-102')).toHaveValue('7');
  const firstLine = page.getByTestId('stocktake-line').filter({ hasText: 'فلتر زيت' });
  await expect(firstLine).toContainText('أحمد');

  // النافذة تعيد جلب القائمة: «يعدّ» و«2 / 3».
  const reopened = await openCountDialog(page);
  const liveRow = reopened.getByTestId('count-link-row').filter({ hasText: 'أحمد' });
  await expect(liveRow).toContainText('يعدّ');
  await expect(liveRow).toContainText('2 / 3');

  await context.close();
});

test('سطرٌ سالب يُرفض محلياً ولا يُرسل — والآخر يُحفظ', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  await expect(publicPage.getByTestId('count-row-6')).toBeVisible();

  await publicPage.getByTestId('count-input-6').fill('3');
  await publicPage.getByTestId('count-input-8').fill('-5');

  await expect.poll(() => handle.countBackend.publicWrites.length).toBe(1);
  expect(handle.countBackend.publicWrites[0].entries).toEqual([
    { line_id: 6, counted_quantity: '3' },
  ]);
  await expect(publicPage.getByTestId('count-state-8')).toContainText('⚠');
  await expect(publicPage.getByTestId('count-input-8')).toHaveValue('-5');

  // لا إعادة إرسالٍ تلقائية للسطر الخاطئ — ينتظر تصحيح صاحبه. (2500ms أطول من
  // تأجيل الحفظ 1500ms، وإلا كان الانتظار أقصر من الدورة التي يفترض نفيها.)
  await publicPage.waitForTimeout(2_500);
  expect(handle.countBackend.publicWrites.length).toBe(1);

  // «انتهيت» مع سطرٍ خاطئ محلياً: الرسالة الصادقة، ولا `finished` يُرسل.
  await publicPage.getByTestId('count-finish').click();
  await publicPage.getByRole('alertdialog').getByRole('button', { name: 'إنهاء' }).click();
  await expect(publicPage.getByText('صحّح الأسطر المعلَّمة بخطأ أولاً، ثم أنهِ العدّ.')).toBeVisible();
  expect(handle.countBackend.publicAttempts.some((write) => write.finished)).toBe(false);

  await context.close();
});

test('إبطال الرابط من المدير ⇒ الموظف يرى 410', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const first = await createLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, first.token);
  await expect(publicPage.getByText('العادّ:')).toContainText('أحمد');

  const reopened = await openCountDialog(page);
  const row = reopened.getByTestId('count-link-row').filter({ hasText: 'أحمد' });
  await row.getByRole('button', { name: 'إبطال' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'إبطال' }).click();
  await expect(row).toContainText('مُبطَل');

  // (أ) GET بعد إعادة تحميل الصفحة.
  await publicPage.reload();
  await expect(publicPage.getByText('انتهى هذا الرابط')).toBeVisible();
  expect(await publicPage.evaluate(
    (key) => localStorage.getItem(key), `ktra.count.${first.token}`,
  )).toBeNull();
  await context.close();
  await closeDialog(page);

  // (ب) 410 على **كتابةٍ** أثناء الحفظ التلقائي، بلا إعادة تحميل: القيمة كانت
  // في النسخة المحلية فعلاً، وتُمسح مع شاشة الانتهاء.
  const second = await createLink(page, 'سامي');
  await closeDialog(page);
  const opened = await openPublicPage(browser, handle.countBackend, second.token);
  await expect(opened.page.getByTestId('count-row-6')).toBeVisible();
  const secondDialog = await openCountDialog(page);
  const secondRow = secondDialog.getByTestId('count-link-row').filter({ hasText: 'سامي' });
  await secondRow.getByRole('button', { name: 'إبطال' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'إبطال' }).click();
  await expect(secondRow).toContainText('مُبطَل');

  const storageKey = `ktra.count.${second.token}`;
  await opened.page.getByTestId('count-input-6').fill('4');
  // القيمة كانت محفوظةً محلياً فعلاً قبل 410 — وإلا كان `toBeNull` تالياً بلا معنى.
  const storedBefore = await opened.page.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(JSON.parse(String(storedBefore)).values['6']).toBe('4');
  await expect(opened.page.getByText('انتهى هذا الرابط')).toBeVisible();
  expect(await opened.page.evaluate((key) => localStorage.getItem(key), storageKey)).toBeNull();
  await opened.context.close();
  await closeDialog(page);
});

test('انقطاع الشبكة: القيمة تبقى في نسخة الجهاز وتُرسل حين يعود المحاكي', async ({ page, browser }) => {
  // إعادة المحاولة بعد 10 ث ثم انتظار 20 ث: ميزانية 30 ث الافتراضية تضيق تحت الحمل.
  test.setTimeout(60_000);
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  handle.setPublicWriteFailure(503);
  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  await expect(publicPage.getByTestId('count-row-6')).toBeVisible();

  await publicPage.getByTestId('count-input-6').fill('4.5');
  await expect(publicPage.getByText('حاول بعد قليل — عدّك محفوظ على هذا الجهاز')).toBeVisible();

  const storageKey = `ktra.count.${token}`;
  const stored = await publicPage.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(stored).not.toBeNull();
  expect(JSON.parse(String(stored)).values['6']).toBe('4.5');

  await publicPage.reload();
  await expect(publicPage.getByTestId('count-input-6')).toHaveValue('4.5');
  await expect(publicPage.getByText('حاول بعد قليل — عدّك محفوظ على هذا الجهاز')).toBeVisible();

  // المحاكي يعود: إعادة المحاولة التلقائية بعد 10 ث ترسل القيمة وتفرّغ النسخة.
  handle.setPublicWriteFailure(null);
  await expect.poll(() => handle.countBackend.publicWrites.length, { timeout: 20_000 }).toBeGreaterThan(0);
  expect(handle.countBackend.publicWrites.at(-1)?.entries).toEqual([
    { line_id: 6, counted_quantity: '4.5' },
  ]);
  await expect.poll(
    () => publicPage.evaluate((key) => localStorage.getItem(key), storageKey),
  ).toBeNull();

  await context.close();
});

test('مسحُ عدٍّ لم يصل يُحفظ فارغاً ويعود ويُرسل null', async ({ page, browser }) => {
  // الإعادة بعد 10 ث ثم انتظار 20 ث: ميزانية 30 ث الافتراضية تضيق تحت الحمل.
  test.setTimeout(60_000);
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  await publicPage.getByTestId('count-input-6').fill('4.5');
  await expect.poll(() => handle.countBackend.publicWrites.length).toBe(1);
  await expect(publicPage.getByTestId('count-state-6')).toContainText('✓');

  // المسح لا يصل: يبقى «فارغاً» في نسخة الجهاز، لا يُسقَط لأن نصّه فارغ.
  handle.setPublicWriteFailure(503);
  await publicPage.getByTestId('count-input-6').fill('');
  await expect(publicPage.getByText('حاول بعد قليل — عدّك محفوظ على هذا الجهاز')).toBeVisible();

  const storageKey = `ktra.count.${token}`;
  const stored = await publicPage.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(JSON.parse(String(stored)).values['6']).toBe('');

  await publicPage.reload();
  await expect(publicPage.getByTestId('count-input-6')).toHaveValue('');

  handle.setPublicWriteFailure(null);
  await expect.poll(() => handle.countBackend.publicWrites.length, { timeout: 20_000 }).toBeGreaterThan(1);
  expect(handle.countBackend.publicWrites.at(-1)?.entries).toEqual([
    { line_id: 6, counted_quantity: null },
  ]);
  await expect.poll(
    () => publicPage.evaluate((key) => localStorage.getItem(key), storageKey),
  ).toBeNull();

  await context.close();
});

test('«انتهيت»: يُفرغ المتّسخ أولاً ثم يرسل finished ويظهر الشارة', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  // ساعةٌ مثبّتة على صفحة الموظف: تأجيل الحفظ 1500ms لا يُطلق إطلاقاً، فأوّل
  // إرسالٍ لا يكون إلا من «انتهيت» نفسها — والترتيب يُقاس لا يُفترض.
  const { context, page: publicPage } = await openPublicPage(
    browser, handle.countBackend, token, undefined, { clock: true },
  );
  await publicPage.getByTestId('count-input-6').fill('5');
  // الساعة مثبّتة: تأجيل الحفظ 1500ms لم يُطلق، ولا محاولة قبل «انتهيت».
  expect(handle.countBackend.publicAttempts).toEqual([]);
  await publicPage.getByTestId('count-finish').click();

  const confirm = publicPage.getByRole('alertdialog');
  await expect(confirm).toContainText('بقي');
  await confirm.getByRole('button', { name: 'إنهاء' }).click();

  await expect.poll(() => handle.countBackend.publicWrites.length).toBe(2);
  expect(handle.countBackend.publicWrites[0].entries).toEqual([
    { line_id: 6, counted_quantity: '5' },
  ]);
  expect(handle.countBackend.publicWrites[1]).toEqual({ entries: [], finished: true });
  await expect(publicPage.getByTestId('count-finished')).toBeVisible();
  await expect(publicPage.getByTestId('count-finish')).toBeDisabled();

  await context.close();
});

test('عرض 360px بلا تمرير أفقي', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(
    browser, handle.countBackend, token, { width: 360, height: 800 },
  );
  await expect(publicPage.getByTestId('count-progress')).toBeVisible();
  await expect(publicPage.getByTestId('count-row-6')).toBeVisible();

  const scrollWidth = await publicPage.evaluate(
    () => document.documentElement.scrollWidth,
  );
  expect(scrollWidth).toBeLessThanOrEqual(360);

  await context.close();
});

test('تحديث تلقائي كل 30 ث مع رابطٍ حيّ — ولا جلب بلا رابط', async ({ page }) => {
  await page.clock.install();
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');

  // بلا رابط: لا دورة تحديث — لا جلب بطاقةٍ ولا جلب روابط. ننتظر جلب القائمة
  // الأوّل (يُطلق مع فتح الجرد) قبل تثبيت خطّ الأساس، وإلا حسبناه دورةً.
  await expect.poll(() => handle.countBackend.adminReads).toBeGreaterThan(0);
  const quietBefore = handle.stocktakeGetCount;
  const quietLinksBefore = handle.countBackend.adminReads;
  await page.clock.fastForward(31_000);
  await page.waitForTimeout(600);
  expect(handle.stocktakeGetCount).toBe(quietBefore);
  expect(handle.countBackend.adminReads).toBe(quietLinksBefore);

  const { token } = await createLink(page, 'أحمد');
  expect(token).toMatch(/^count-token-\d+$/);
  await closeDialog(page);

  const before = handle.stocktakeGetCount;
  const linksBefore = handle.countBackend.adminReads;
  await page.clock.fastForward(31_000);
  await expect.poll(() => handle.stocktakeGetCount, { timeout: 8_000 }).toBeGreaterThan(before);
  // والروابط تُعاد قراءتها مع كل دورة (حالة الرابط تحكم استمرار المؤقّت).
  await expect.poll(() => handle.countBackend.adminReads, { timeout: 8_000 }).toBeGreaterThan(linksBefore);

  // الانتقال إلى جردٍ بلا روابط يوقف المؤقّت (cleanup عند تغيير الجرد).
  await page.waitForTimeout(500);
  const linksBeforeSwitch = handle.countBackend.adminReads;
  await openHistory(page);
  const secondRow = page.locator('tbody tr').filter({ hasText: 'JRD-0002' }).first();
  await secondRow.getByRole('button', { name: 'فتح' }).click();
  await expect(page.getByTestId('stocktake-sheet')).toBeVisible();
  // جلب قائمة الجرد الجديد يُطلق مع فتحه — يُنتظر قبل تثبيت خطّ الأساس.
  await expect.poll(() => handle.countBackend.adminReads).toBeGreaterThan(linksBeforeSwitch);
  const otherBefore = handle.stocktakeGetCount;
  const otherLinksBefore = handle.countBackend.adminReads;
  await page.clock.fastForward(31_000);
  await page.waitForTimeout(600);
  expect(handle.stocktakeGetCount).toBe(otherBefore);
  expect(handle.countBackend.adminReads).toBe(otherLinksBefore);
});

test('سطرٌ يخرج من نطاق الرابط: لا «✓»، شريط إعادة تحميل، والنسخة المحلية باقية ثم تُسقط', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createScopedLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  await expect(publicPage.getByTestId('count-row-7')).toBeVisible();

  // بعد فتح الصفحة نُخرج السطر من النطاق: منتجه صار في تصنيفٍ آخر، والخادم
  // يتجاهل السطر بلا خطأ (`ignored`).
  handle.moveLineOutOfScope(7);
  await publicPage.getByTestId('count-input-7').fill('5');

  await expect.poll(() => handle.countBackend.publicWrites.length).toBe(1);
  expect(handle.countBackend.publicWrites[0]).toEqual({
    entries: [{ line_id: 7, counted_quantity: '5' }],
    finished: false,
  });
  await expect(publicPage.getByTestId('count-state-7')).not.toContainText('✓');
  await expect(publicPage.getByText('تغيّر نطاق الجرد — أعد تحميل الصفحة')).toBeVisible();

  const storageKey = `ktra.count.${token}`;
  const stored = await publicPage.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(JSON.parse(String(stored)).values['7']).toBe('5');

  await publicPage.getByRole('button', { name: 'إعادة التحميل' }).click();
  await expect(publicPage.getByTestId('count-row-7')).toHaveCount(0);
  await expect(publicPage.getByTestId('count-row-6')).toBeVisible();
  await expect.poll(
    () => publicPage.evaluate((key) => localStorage.getItem(key), storageKey),
  ).toBeNull();

  await context.close();
});

test('400 ذرّي على سطرٍ واحد: ⚠ عليه وحده، وتصحيحه يعيد إرسال الدفعة كاملة', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  await expect(publicPage.getByTestId('count-row-6')).toBeVisible();

  handle.countBackend.rejectLineIds = [7];
  await publicPage.getByTestId('count-input-6').fill('3');
  await publicPage.getByTestId('count-input-7').fill('4');

  await expect.poll(() => handle.countBackend.publicAttempts.length).toBe(1);
  // الخادم ذرّي: لا سطر في الدفعة حُفظ — ولا حتى السليم.
  expect(handle.countBackend.publicWrites).toEqual([]);
  await expect(publicPage.getByTestId('count-state-7')).toContainText('⚠');
  await expect(publicPage.getByTestId('count-state-7')).toContainText('كمية غير صالحة');
  await expect(publicPage.getByTestId('count-state-6')).not.toContainText('✓');

  handle.countBackend.rejectLineIds = [];
  await publicPage.getByTestId('count-input-7').fill('5');
  await expect.poll(() => handle.countBackend.publicWrites.length).toBe(1);
  expect(handle.countBackend.publicWrites[0].entries).toEqual([
    { line_id: 6, counted_quantity: '3' },
    { line_id: 7, counted_quantity: '5' },
  ]);
  await expect(publicPage.getByTestId('count-state-6')).toContainText('✓');
  await expect(publicPage.getByTestId('count-state-7')).toContainText('✓');

  await context.close();
});

test('تعديل سطرٍ أثناء طلبٍ مرفوضٍ مؤخَّر: لا ⚠ عليه، ويُرسَل بقيمته الجديدة', async ({ page, browser }) => {
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  const { context, page: publicPage } = await openPublicPage(browser, handle.countBackend, token);
  await expect(publicPage.getByTestId('count-row-6')).toBeVisible();

  handle.countBackend.rejectLineIds = [6];
  handle.countBackend.delayWritesMs = 1_200;
  await publicPage.getByTestId('count-input-6').fill('4');

  // الطلب وصل وما زال معلّقاً؛ الموظف صحّح القيمة قبل وصول الردّ. والرفض لقطةٌ
  // عند وصول الطلب، فإزالتُه الآن لا تُلغي ردّ الطلب الأول.
  await expect.poll(
    () => handle.countBackend.publicAttempts.length, { intervals: [100] },
  ).toBe(1);
  await publicPage.getByTestId('count-input-6').fill('9');
  handle.countBackend.rejectLineIds = [];

  // الرفض يخصّ «4» لا «9»: القيمة الجديدة لا تُحجب وتُرسل في الدورة التالية.
  await expect.poll(
    () => handle.countBackend.publicWrites.length, { timeout: 10_000 },
  ).toBe(1);
  // الردّ المرفوض وصل فعلاً قبل النجاح (الطابور متسلسل: الثاني بعد الأول).
  expect(handle.countBackend.publicRejects).toBe(1);
  expect(handle.countBackend.publicWrites[0].entries).toEqual([
    { line_id: 6, counted_quantity: '9' },
  ]);
  await expect(publicPage.getByTestId('count-state-6')).toContainText('✓');
  await expect(publicPage.getByTestId('count-state-6')).not.toContainText('⚠');

  await context.close();
});

test('التحديث التلقائي لا يعطّل خانة المدير ولا يمحو ما يكتبه', async ({ page }) => {
  await page.clock.install();
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  expect(token).toMatch(/^count-token-\d+$/);
  await closeDialog(page);

  const input = page.getByTestId('stocktake-count-101');
  await input.click();
  await input.fill('7');

  // عدٌّ وصل من الموظف على سطرٍ آخر في «الخادم».
  const server = handle.countBackend.stocktakes.find((row) => row.number === 'JRD-0003');
  const other = server?.lines.find((row) => row.id === 7);
  if (other) {
    other.counted = '3.0000';
    other.by = 'أحمد';
    other.at = new Date().toISOString();
  }

  // التركيز داخل الورقة: الدورة تمرّ ولا تجلب — والخانة تبقى حيّة بقيمتها.
  const before = handle.stocktakeGetCount;
  await page.clock.fastForward(31_000);
  await page.waitForTimeout(600);
  expect(handle.stocktakeGetCount).toBe(before);
  await expect(input).toBeEnabled();
  await expect(input).toHaveValue('7');

  // خارج الورقة وبعد أكثر من 5 ث من آخر تعديل: الدورة التالية تجلب، وتعديله
  // باقٍ فوق اللقطة الجديدة، وعدّ الموظف على سطرٍ آخر ظاهر.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.clock.fastForward(31_000);
  await expect.poll(() => handle.stocktakeGetCount, { timeout: 8_000 }).toBeGreaterThan(before);
  await expect(input).toHaveValue('7');
  await expect(page.getByTestId('stocktake-count-102')).toHaveValue('3');
  await expect(
    page.getByTestId('stocktake-line').filter({ hasText: 'فلتر هواء' }),
  ).toContainText('أحمد');
});

test('التحديث التلقائي يستمر بعد أن ينهي الموظف', async ({ page }) => {
  await page.clock.install();
  const handle = await installStocktakeApiStubs(page);
  await openSheet(page, 'JRD-0003');
  const { token } = await createLink(page, 'أحمد');
  await closeDialog(page);

  // الموظف أنهى (نفس أثر `finished` على الخادم)، والورقة قرأت الحالة الجديدة.
  const link = handle.countBackend.links.find((row) => row.token === token);
  if (link) link.finished_at = new Date().toISOString();
  const reopened = await openCountDialog(page);
  await expect(
    reopened.getByTestId('count-link-row').filter({ hasText: 'أحمد' }),
  ).toContainText('أنهى');
  await closeDialog(page);

  const before = handle.stocktakeGetCount;
  await page.clock.fastForward(31_000);
  await expect.poll(() => handle.stocktakeGetCount, { timeout: 8_000 }).toBeGreaterThan(before);
});
