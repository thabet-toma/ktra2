import { expect, test, type Page } from '@playwright/test';

/**
 * THA-166 م٧ — الفلترةُ بعدّاداتٍ سياقيّة في واجهة المتجر العام.
 *
 * لازمةٌ يجب معرفتها قبل قراءة هذا الملف: الاستثناءُ الانفصاليّ يعني أنّ
 * اختيار ماركةٍ يُحدِّث عدّادات الفئات (تُحسَب **داخل** الماركة المختارة)
 * بينما تبقى عدّاداتُ بقيّة الماركات كما هي (تُحسَب في عالمٍ لا فلتر ماركةٍ
 * فيه) — هذا الاختبار يُثبت الاستثناء مرئياً في الواجهة، لا في الخادم فقط
 * (`store/tests/test_store_facets.py` يغطّي الخادم).
 *
 * لا مصادقة هنا: `/store/<slug>` مسارٌ عامٌّ بلا `AuthProvider`.
 */

const SLUG = 'facet-shop';

const PROFILE = {
  slug: SLUG, name: 'متجر الفلاتر', logo_url: null, phone: null,
  address: null, currency: '₪', show_prices: true,
  catalog_mode_default: 'grid', allow_cart: true,
};

const PRODUCT = (id: number, name: string, brand: string, brandId: number, categoryName: string, categoryId: number) => ({
  id, name_ar: name, name_en: '', brand, brand_id: brandId, category_name: categoryName,
  uom_name: '', price: '100.00', availability: 'available', description: '',
  images: ['https://picsum.photos/seed/facet-shop/200'],
  categories: [{ id: categoryId, name: categoryName, slug: `cat-${categoryId}` }],
});

const DEFAULT_RESPONSE = {
  count: 3, next: null, previous: null,
  results: [
    PRODUCT(1, 'هاتف سامسونج', 'سامسونج', 1, 'هواتف', 10),
    PRODUCT(2, 'هاتف أبل', 'أبل', 2, 'هواتف', 10),
    PRODUCT(3, 'لابتوب سامسونج', 'سامسونج', 1, 'لابتوبات', 11),
  ],
  facets: {
    categories: [
      { id: 10, name: 'هواتف', parent_id: null, count: 2 },
      { id: 11, name: 'لابتوبات', parent_id: null, count: 1 },
    ],
    brands: [
      { id: 1, name: 'سامسونج', count: 2 },
      { id: 2, name: 'أبل', count: 1 },
    ],
    flags: { on_sale: 0, is_new: 3, in_stock: 3 },
  },
  price_range: { min: '100.00', max: '100.00' },
};

// اختيارُ سامسونج (brand=1): عدّادُ الفئات يُحسَب **داخل** سامسونج (هواتف=1،
// لابتوبات=1)، وعدّادُ الماركات يبقى **كاملاً** (أبل تبقى ١ لا صفراً).
const SAMSUNG_FILTERED_RESPONSE = {
  count: 2, next: null, previous: null,
  results: [
    PRODUCT(1, 'هاتف سامسونج', 'سامسونج', 1, 'هواتف', 10),
    PRODUCT(3, 'لابتوب سامسونج', 'سامسونج', 1, 'لابتوبات', 11),
  ],
  facets: {
    categories: [
      { id: 10, name: 'هواتف', parent_id: null, count: 1 },
      { id: 11, name: 'لابتوبات', parent_id: null, count: 1 },
    ],
    brands: [
      { id: 1, name: 'سامسونج', count: 2 },
      { id: 2, name: 'أبل', count: 1 },
    ],
    flags: { on_sale: 0, is_new: 2, in_stock: 2 },
  },
  price_range: { min: '100.00', max: '100.00' },
};

const EMPTY_RESPONSE = {
  count: 0, next: null, previous: null, results: [],
  facets: { categories: [], brands: [], flags: { on_sale: 0, is_new: 0, in_stock: 0 } },
  price_range: { min: null, max: null },
};

async function stubStoreApi(page: Page) {
  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const json = (body: unknown) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    const path = url.pathname;

    if (path === `/api/store/${SLUG}/`) return json(PROFILE);
    if (path === `/api/store/${SLUG}/home/`) return json({ blocks: [] });
    if (path === `/api/store/${SLUG}/collections/`) {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    if (path === `/api/store/${SLUG}/products/`) {
      const q = (url.searchParams.get('q') || '').trim();
      const brand = url.searchParams.get('brand');
      if (q) return json(EMPTY_RESPONSE);
      if (brand === '1') return json(SAMSUNG_FILTERED_RESPONSE);
      return json(DEFAULT_RESPONSE);
    }
    return json({ count: 0, next: null, previous: null, results: [] });
  });
}

test('اختيارُ ماركةٍ يحدِّث عدّادات الفئات، وتبقى الماركاتُ الأخرى ظاهرةً بأعدادها، ورقاقةٌ تُنزَع ومسحٌ للكلّ', async ({ page }) => {
  await stubStoreApi(page);
  await page.goto(`/store/${SLUG}`);

  const sidebar = page.locator('aside');
  await expect(sidebar.getByText('سامسونج')).toBeVisible({ timeout: 20000 });

  // العدّاداتُ الابتدائية: هواتف (2)، لابتوبات (1)، سامسونج (2)، أبل (1).
  await expect(sidebar.getByText('هواتف')).toBeVisible();
  await expect(page.getByText('(2)').first()).toBeVisible();

  // اختيارُ سامسونج.
  await sidebar.getByText('سامسونج').click();

  // عدّادُ الفئات تحدَّث إلى (1) لكلٍّ منهما (الاستثناء الانفصالي: محسوبٌ
  // داخل سامسونج وحدَها الآن)، وأبل — الماركةُ غيرُ المختارة — بقيت ظاهرةً
  // بعددها الحقيقي (1) لا صفراً ولا مخفيّة.
  await expect(sidebar.getByText('أبل')).toBeVisible();
  await expect.poll(async () => (await sidebar.locator('label:has-text("هواتف")').textContent()) || '')
    .toContain('(1)');

  // رقاقةُ الفلتر المطبَّق ظهرت فوق الشبكة، وإزالتها تعيد الحالة الافتراضية.
  const chip = page.getByRole('button', { name: 'سامسونج', exact: true });
  await expect(chip).toBeVisible();
  await chip.click();

  await expect.poll(async () => (await sidebar.locator('label:has-text("هواتف")').textContent()) || '')
    .toContain('(2)');

  // اختيارٌ جديد ثم «مسح الكل».
  await sidebar.getByText('سامسونج').click();
  await expect(page.getByRole('button', { name: 'سامسونج', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'مسح الكل' }).click();
  await expect(page.getByRole('button', { name: 'سامسونج', exact: true })).toHaveCount(0);
  await expect.poll(async () => (await sidebar.locator('label:has-text("هواتف")').textContent()) || '')
    .toContain('(2)');
});

test('لا نتائج ⇒ زرّ «امسح الفلاتر» يعمل فعلاً ويعيد عرض المنتجات', async ({ page }) => {
  await stubStoreApi(page);
  await page.goto(`/store/${SLUG}`);

  await expect(page.getByRole('heading', { name: 'هاتف سامسونج' })).toBeVisible({ timeout: 20000 });

  await page.getByPlaceholder('ابحث بالاسم أو الماركة…').fill('لا-يوجد-منتج-بهذا-الاسم');

  await expect(page.getByText('لا نتائج مطابقة')).toBeVisible({ timeout: 5000 });
  const clearButton = page.getByRole('button', { name: 'امسح الفلاتر' });
  await expect(clearButton).toBeVisible();

  await clearButton.click();

  await expect(page.getByRole('heading', { name: 'هاتف سامسونج' })).toBeVisible({ timeout: 20000 });
  await expect(page.getByPlaceholder('ابحث بالاسم أو الماركة…')).toHaveValue('');
});
