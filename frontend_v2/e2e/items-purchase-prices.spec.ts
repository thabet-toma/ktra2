import { test, expect, type Locator, type Page } from '@playwright/test';
import { switchItemsToTable } from './items-view';
import {
  installItemsTreeApiStubs,
  PRODUCTS,
  type ItemsTreeProductRow,
} from './items-tree-stubs';

/**
 * ITEM-PURCHASE-DISPLAY — الرقم الأساسي في قائمة المنتجات «آخر سعر شراء» لا
 * «أقلّ شراء (آخر ٥)»، والأقلّ خلف «تفاصيل السعر» في الخليّة نفسها، ورأس كرت
 * المنتج يعرض القيم الثلاث (آخر · أقلّ · متوسط تكلفة المخزون) قبل أي تبويب.
 *
 * ما لا يمسكه غيرُه: `npm test` دوالُّ خالصة (لا تصيير)، و`pytest` لا يصيّر
 * الواجهة، و`tsc` لا يفحص خصائص JSX (لا `@types/react`). فيبقى الاختبار الذي
 * يفتح الجدول فعلاً ويرى الخليّة ورأسَ الكرت هو الحارس الوحيد.
 *
 * الأرقام في المحاكي متمايزة عمداً: متوسط ٣٠ · أقلّ ٢٠ · آخر ٤٠ — فأيّ توصيلٍ
 * خاطئ (قراءة الأقلّ بدل الآخِر، أو السقوط إلى متوسط التكلفة) يسقط برقمٍ ظاهر.
 */

const PRODUCT_DETAIL_7 = {
  ...PRODUCTS[0],
  tenant: 1,
  brand: 'ميشلان',
  uom_id: null, uom_name: 'حبة', uom2: null, uom2_factor: null, uom3: null, uom3_factor: null,
  description: null, storage_location: null, image_url: null,
  sale_account_override: null, sale_return_account_override: null,
  purchase_account_override: null, purchase_return_account_override: null,
  supplier_account_override: null, ending_inventory_account_override: null,
  price_tiers: [], weight_kg: null, volume_cbm: null, hs_code: null,
  max_stock_level: null, reorder_mode: 'manual', is_serialized: false, is_service: false,
  is_active: true, is_for_sale_online: false, online_price: null, online_description: null,
  purchased_qty: '20', avg_monthly_sales: '4',
  family_id: null, family_name: null, family_brand_count: 1,
  effective_min_stock_level: 2, effective_max_stock_level: null, serial_required_by: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-21T00:00:00Z',
  attachments: [],
};

/** بلا شراء مرحَّل: متوسط تكلفته ٥٥ — تُكشف أيّ سلسلةِ احتياطٍ تعرضها سعراً. */
const PRODUCT_DETAIL_8 = {
  ...PRODUCT_DETAIL_7,
  id: 8, sku: 'SKU-8', name_ar: 'بطارية 70A', name_en: '',
  display_name: 'بطارية 70A', brand: 'فارتا', avg_cost: '55', sale_price: '80',
  last_purchase_price: null, indicative_purchase_price: null,
  indicative_purchase_price_source: null,
};

const FAMILY_ANCHOR: ItemsTreeProductRow = {
  id: 70, sku: 'OIL-70', name_ar: 'زيت محرك', name_en: '', display_name: 'زيت محرك — شل',
  brand: 'شل', category: 3, category_name: 'إطارات',
  quantity_on_hand: '4', reserved_quantity: '0', available_quantity: '4',
  avg_cost: '45', sale_price: '70', min_stock_level: 1, stock_status: 'in_stock',
  has_group: true, group_key: 'زيت محرك',
  family_id: 40, family_name: 'زيت محرك', family_brand_count: 2,
  last_purchase_price: '60', indicative_purchase_price: '50',
  indicative_purchase_price_source: 'أقل شراء (آخر ٥)',
};

/** براندٌ ثانٍ للمنتج نفسه: سعرٌ مختلف (٧٠) — الصفّ المجمّع لا يجمع الأسعار. */
const FAMILY_SIBLING: ItemsTreeProductRow = {
  ...FAMILY_ANCHOR,
  id: 71, sku: 'OIL-71', display_name: 'زيت محرك — موبيل', brand: 'موبيل',
  quantity_on_hand: '2', avg_cost: '65', last_purchase_price: '70',
  indicative_purchase_price: '55',
};

test.beforeEach(async ({ page }) => {
  await installItemsTreeApiStubs(page, {
    extraProducts: [FAMILY_ANCHOR, FAMILY_SIBLING],
    productDetails: { 7: PRODUCT_DETAIL_7, 8: PRODUCT_DETAIL_8 },
  });
});

/** خليّة سعر الشراء لصفٍّ بعينه — الخليّة وحدها، لا عمودٌ ثانٍ. */
const priceCell = (page: Page, rowText: string): Locator =>
  page.locator('tbody tr', { hasText: rowText }).getByTestId('purchase-price-cell');

/**
 * لا يزحم محتوى الخليّة الأعمدةَ المجاورة: سطر «تفاصيل السعر» الطويل (وسطر
 * البراند المرجعي في الصفّ المجمّع) يلتفّ داخل عرض العمود لا يفرض عرضه عليه.
 */
const expectNoHorizontalOverflow = async (cell: Locator): Promise<void> => {
  const overflow = await cell.evaluate(
    (el) => el.scrollWidth - el.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
};

const openCard = async (page: Page, sku: string) => {
  await page.goto('/items');
  await switchItemsToTable(page);
  await page.getByTitle(sku).first().dblclick();
  await page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' }).waitFor();
};

/** حقلٌ في شريط الرأس — خارج كل التبويبات (`.ktra-headband`). */
const headerField = (page: Page, label: string): Locator =>
  page.locator('.ktra-headband label.ktra-field', { hasText: label });

test('الرقم الأساسي آخر سعر شراء، والأقلّ داخل تفاصيل مغلقة تُفتح بطلب', async ({ page }) => {
  await page.goto('/items');
  await switchItemsToTable(page);

  // العمود الأساسي صار «آخر سعر شراء» — ولا عمود ثانٍ للأقلّ.
  await expect(page.getByRole('columnheader', { name: 'آخر سعر شراء' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: /أقلّ شراء/ })).toHaveCount(0);

  const cell = priceCell(page, 'إطار 205/55 — ميشلان');
  await expect(cell.getByTestId('purchase-last-price')).toHaveText('40');

  // التفاصيل مغلقة افتراضياً، والأقلّ (٢٠) غير ظاهرٍ قبل الفتح.
  const details = cell.locator('details');
  expect(await details.evaluate((el: HTMLDetailsElement) => el.open)).toBe(false);
  await expect(cell.getByTestId('purchase-lowest-price')).not.toBeVisible();

  await cell.getByText('تفاصيل السعر').click();

  expect(await details.evaluate((el: HTMLDetailsElement) => el.open)).toBe(true);
  await expect(cell.getByTestId('purchase-lowest-price')).toContainText('أقلّ شراء (آخر ٥): 20');
  // والرقم الأساسي لم يتغيّر بفتح التفاصيل (لا عمودان يعرضان رقمين متبادلين).
  await expect(cell.getByTestId('purchase-last-price')).toHaveText('40');
  await expect(cell).not.toContainText('30');
  await expectNoHorizontalOverflow(cell);

  await page.screenshot({ path: test.info().outputPath('table-details-open.png'), fullPage: true });
});

test('رأس كرت المنتج يعرض القيم الثلاث قبل أي تبديل تبويب', async ({ page }) => {
  await openCard(page, 'SKU-7');

  // لا تبديل تبويب: النظرة العامة هي الافتراضية والرأس خارجها.
  await expect(page.getByRole('tab', { name: 'نظرة عامة', selected: true })).toBeVisible();
  await expect(headerField(page, 'آخر سعر شراء').locator('input')).toHaveValue('40');
  await expect(headerField(page, 'أقلّ شراء (آخر ٥)').locator('input')).toHaveValue('20');
  await expect(headerField(page, 'متوسط تكلفة المخزون').locator('input')).toHaveValue('30');
  // الحقول القائمة لم تُمَسّ.
  await expect(headerField(page, 'سعر البيع').locator('input')).toHaveValue('45');
  await expect(headerField(page, 'الرصيد').locator('input')).toHaveValue('12');

  await page.screenshot({ path: test.info().outputPath('card-header.png'), fullPage: true });
});

test('منتج بلا تاريخ شراء: شرطة لا متوسط التكلفة — في الجدول والكرت', async ({ page }) => {
  await page.goto('/items');
  await switchItemsToTable(page);

  const cell = priceCell(page, 'بطارية 70A');
  await expect(cell.getByTestId('purchase-last-price')).toHaveText('—');
  await expect(cell).not.toContainText('55');

  await page.getByTitle('SKU-8').first().dblclick();
  await page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' }).waitFor();
  await expect(headerField(page, 'آخر سعر شراء').locator('input')).toHaveValue('—');
  await expect(headerField(page, 'أقلّ شراء (آخر ٥)').locator('input')).toHaveValue('—');
  // متوسط التكلفة الحقيقي يبقى ظاهراً — الشرطة على سعر الشراء وحده.
  await expect(headerField(page, 'متوسط تكلفة المخزون').locator('input')).toHaveValue('55');
});

test('الصفّ المجمّع يحتفظ بمعنى البراند المرجعي ولا يجمّع الأسعار', async ({ page }) => {
  await page.goto('/items');
  await switchItemsToTable(page);

  // الصفّ المجمّع (المنتج ٤٠) — البراند المرجعي أصغر معرّفاً (٧٠ · «شل» · ٦٠).
  const row = page.locator('tbody tr', { hasText: 'زيت محرك' }).first();
  await expect(row.getByTestId('purchase-last-price')).toHaveText('60');
  // لا مجموع (١٣٠) ولا متوسط (٦٥): التجميع كما كان — السعر لبراندٍ واحد.
  await expect(row).not.toContainText('130');
  await expect(row).not.toContainText('65');

  await row.getByText('تفاصيل السعر').click();
  await expect(row.getByTestId('purchase-lowest-price')).toContainText('أقلّ شراء (آخر ٥): 50');
  // مصدر الصفّ المجمّع يُسمّى صراحةً: سعر براندٍ مرجعيٍّ لا يغطّي إخوته.
  await expect(row.getByTestId('purchase-price-anchor-hint')).toContainText('شل');
  await expect(row.getByTestId('purchase-price-anchor-hint')).toContainText('2');
  // وأطول سطرٍ في الخليّة (وسم البراند) لا يدفع الأعمدة المجاورة.
  await expectNoHorizontalOverflow(row.getByTestId('purchase-price-cell'));

  // الكشف القائم لم يُمَسّ: البراند الثاني ما زال صفّاً مستقلاً بسعره هو.
  await row.getByRole('button', { name: /إظهار البراندات/ }).click();
  const sibling = page.locator('tbody tr', { hasText: 'زيت محرك — موبيل' });
  await expect(sibling.getByTestId('purchase-last-price')).toHaveText('70');

  await page.screenshot({ path: test.info().outputPath('grouped-row-details.png'), fullPage: true });
});
