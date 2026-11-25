/**
 * PICKER-COMPACT: التحقّق البصري والـDOM لقائمة بحث المنتج ذات السطرين في
 * فاتورتَي البيع والشراء، مع بقاء بقية منتقيات KitAutocomplete بسطرٍ واحد.
 */
import fs from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page, type Route, type TestInfo } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const shotPath = (testInfo: TestInfo, name: string): string => {
  const dir = process.env.E2E_SHOTS_DIR;
  if (dir) {
    fs.mkdirSync(dir, { recursive: true });
    return path.join(dir, name);
  }
  return testInfo.outputPath(name);
};

// إطاران متتاليان: يترك React والمتصفح يُنهيان ما أطلقه الحدث السابق قبل الحكم أو الكتابة
async function settleFrames(page: Page) {
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
}

// الاسم غير مقصوص رأسياً بقصّ السطرين (-webkit-line-clamp): المحتوى كلّه داخل صندوق العنصر
async function expectLabelNotClipped(label: Locator) {
  const h = await label.evaluate((el) => ({ scrollH: el.scrollHeight, clientH: el.clientHeight }));
  expect(h.scrollH).toBeLessThanOrEqual(h.clientH + 2);
}

// القائمة مثبّتة (position: fixed) على الشاشة: صندوقها كلّه داخل عرض النافذة، وحافّتها العليا داخل ارتفاعها
async function expectPopInViewport(page: Page, pop: Locator) {
  const box = await pop.boundingBox();
  const vp = page.viewportSize();
  expect(box).not.toBeNull();
  expect(vp).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(vp!.width);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeLessThan(vp!.height);
}

const LONG_TYRE_NAME = '225/35/19 (وسيط ابو عمار الايطالي الأصلي رياضي عالي الأداء)';

const PRODUCTS = [
  {
    id: 101,
    sku: 'TYRE-225',
    barcode: '6290000001011',
    name_ar: LONG_TYRE_NAME,
    name_en: '',
    display_name: LONG_TYRE_NAME,
    category: null,
    category_name: 'إطارات',
    min_stock_level: 5,
    quantity_on_hand: '14',
    reserved_quantity: '2',
    available_quantity: '12',
    avg_cost: '62',
    sale_price: '150',
    indicative_purchase_price: '75',
    indicative_purchase_price_source: 'أقل شراء (آخر ٥)',
    is_service: false,
    is_serialized: false,
    stock_status: 'in_stock',
  },
  {
    id: 102,
    sku: 'TYRE-195',
    barcode: '6290000001028',
    name_ar: '195/65/15 كونتيننتال اقتصادي',
    name_en: '',
    display_name: '195/65/15 كونتيننتال اقتصادي',
    category: null,
    category_name: 'إطارات',
    min_stock_level: 10,
    quantity_on_hand: '3',
    reserved_quantity: '0',
    available_quantity: '3',
    avg_cost: '41.25',
    sale_price: '110',
    indicative_purchase_price: '31.75',
    indicative_purchase_price_source: 'أقل شراء (آخر ٥)',
    is_service: false,
    is_serialized: false,
    stock_status: 'low_stock',
  },
];

const CUSTOMERS = [
  { id: 7, name: 'شركة النور للتجارة', partner_type: 'Customer', city: 'نابلس', is_active: true },
  { id: 8, name: 'عميل جديد بدون مبيعات', partner_type: 'Customer', city: 'الخليل', is_active: true },
  { id: 9, name: 'عميل مؤجّل الاستجابة', partner_type: 'Customer', city: 'أريحا', is_active: true },
];

const SUPPLIERS = [
  { id: 10, name: 'مورد الإطارات الرئيسي', partner_type: 'Supplier', city: 'رام الله', is_active: true },
  { id: 11, name: 'مورد مؤجّل الاستجابة', partner_type: 'Supplier', city: 'جنين', is_active: true },
  { id: 12, name: 'مورد يفشل جلبه', partner_type: 'Supplier', city: 'طولكرم', is_active: true },
];

interface RouteControls {
  pendingSupplier11?: Promise<void>;
  pendingCustomer9?: Promise<void>;
}

async function installRoutes(page: Page, opts: { eyeOpen: boolean }, controls: RouteControls = {}) {
  await page.addInitScript((eyeOpen: boolean) => {
    localStorage.clear();
    localStorage.setItem('token', 'picker-compact-token');
    localStorage.setItem('userId', 'picker-compact-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('ktra_prices_visible', eyeOpen ? '1' : '0');
  }, opts.eyeOpen);

  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const p = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (p.endsWith('/hr/users/picker-compact-user/')) {
      return json({
        id: 'picker-compact-user', name: 'مختبر القوائم', role: 'manager',
        email: 'picker@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (p.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاختبار', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (p.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: [
          'sales.invoice.view', 'sales.invoice.create', 'sales.invoice.edit',
          'purchase.invoice.view', 'purchase.invoice.create', 'purchase.invoice.edit',
        ],
      });
    }
    if (p.endsWith('/inventory/products/') || p.endsWith('/lookup/products/')) {
      return json(PRODUCTS);
    }
    if (p.includes('/partners/')) {
      const pt = url.searchParams.get('partner_type') || '';
      if (pt === 'Customer') return json(CUSTOMERS);
      if (pt === 'Supplier') return json(SUPPLIERS);
      return json([...CUSTOMERS, ...SUPPLIERS]);
    }
    if (p.includes('/accounting/currencies')) {
      return json([{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل', Symbol: '₪', IsBaseCurrency: true }]);
    }
    if (p.includes('/accounting/accounts')) {
      return json([
        { id: 401, code: '4101', name: 'إيرادات المبيعات', account_type: 'Revenue', is_active: true },
        { id: 111, code: '1101', name: 'الصندوق', account_type: 'Asset', is_active: true },
      ]);
    }
    if (p.endsWith('/sales/settings/current/')) {
      return json({
        id: 1, default_customer: 7, default_currency: 1,
        default_payment_type: 'credit', stock_on_post_default: true,
        negative_stock_policy: 'block', prices_include_tax: false,
        serial_entry_mode: 'off',
      });
    }
    if (p.endsWith('/logistics/purchase-settings/current/')) {
      return json({
        id: 1, purchase_default_price_strategy: 'LAST_PURCHASE',
        receive_on_post: true, serial_entry_mode: 'off',
      });
    }
    if (p.endsWith('/sales/customer-price-list/')) {
      const cid = Number(url.searchParams.get('customer'));
      if (cid === 7) {
        return json([
          {
            product_id: 101, sku: 'TYRE-225', name: LONG_TYRE_NAME,
            price: '120.0000', source: 'last_invoice', source_label: 'آخر فاتورة',
            editable: false, invoice_number: 'SI-701',
            prices: [
              { label: 'آخر فاتورة', unit_price: '120.0000', source_type: 'SALES_INVOICE', kind: 'last', document_id: 701, invoice_number: 'SI-701' },
              { label: 'أقل سعر', unit_price: '80.0000', source_type: 'SALES_INVOICE', kind: 'lowest', document_id: 650, invoice_number: 'SI-650' },
            ],
          },
          {
            product_id: 102, sku: 'TYRE-195', name: '195/65/15 كونتيننتال اقتصادي',
            price: '110.0000', source: 'default', source_label: 'سعر عام (كرت المنتج)',
            editable: true, invoice_number: null,
            prices: [
              { label: 'سعر عام (كرت المنتج)', unit_price: '110.0000', source_type: 'PRODUCT', kind: 'card', document_id: null, invoice_number: null },
            ],
          },
        ]);
      }
      if (cid === 9) {
        if (controls.pendingCustomer9) {
          await controls.pendingCustomer9;
        }
        return json([
          {
            product_id: 101, sku: 'TYRE-225', name: LONG_TYRE_NAME,
            price: '95.0000', source: 'last_invoice', source_label: 'آخر فاتورة',
            editable: false, invoice_number: 'SI-901',
            prices: [
              { label: 'آخر فاتورة', unit_price: '95.0000', source_type: 'SALES_INVOICE', kind: 'last', document_id: 901, invoice_number: 'SI-901' },
            ],
          },
        ]);
      }
      return json([
        {
          product_id: 101, sku: 'TYRE-225', name: LONG_TYRE_NAME,
          price: '100.0000', source: 'quote', source_label: 'عرض السعر',
          editable: true, invoice_number: 'Q-9',
          prices: [
            { label: 'عرض السعر', unit_price: '100.0000', source_type: 'QUOTE', kind: 'quote', document_id: null, invoice_number: 'Q-9' },
          ],
        },
        {
          product_id: 102, sku: 'TYRE-195', name: '195/65/15 كونتيننتال اقتصادي',
          price: '110.0000', source: 'default', source_label: 'سعر عام (كرت المنتج)',
          editable: true, invoice_number: null,
          prices: [
            { label: 'سعر عام (كرت المنتج)', unit_price: '110.0000', source_type: 'PRODUCT', kind: 'card', document_id: null, invoice_number: null },
          ],
        },
      ]);
    }
    if (p.endsWith('/logistics/purchase-invoices/price-list/')) {
      const sid = Number(url.searchParams.get('supplier'));
      if (sid === 10) {
        return json([
          {
            product_id: 101, unit_price: '48.5000', source_type: 'PURCHASE_INVOICE',
            source_label: 'آخر شراء من المورد',
            prices: [
              { unit_price: '48.5000', source_type: 'PURCHASE_INVOICE', source_label: 'آخر شراء من المورد', kind: 'last', document_id: 501 },
              { unit_price: '75.0000', source_type: 'PURCHASE_INVOICE', source_label: 'أقل شراء (آخر ٥)', kind: 'lowest', document_id: 420 },
            ],
          },
          {
            product_id: 102, unit_price: '31.7500', source_type: 'PURCHASE_INVOICE',
            source_label: 'أقل شراء (آخر ٥)',
            prices: [
              { unit_price: '31.7500', source_type: 'PURCHASE_INVOICE', source_label: 'أقل شراء (آخر ٥)', kind: 'lowest', document_id: 430 },
            ],
          },
        ]);
      }
      if (sid === 11) {
        if (controls.pendingSupplier11) {
          await controls.pendingSupplier11;
        }
        return json([
          {
            product_id: 101, unit_price: '75.0000', source_type: 'PURCHASE_INVOICE',
            source_label: 'أقل شراء (آخر ٥)',
            prices: [
              { unit_price: '75.0000', source_type: 'PURCHASE_INVOICE', source_label: 'أقل شراء (آخر ٥)', kind: 'lowest', document_id: 420 },
            ],
          },
        ]);
      }
      if (sid === 12) {
        return json({ error: 'فشل جلب الأسعار' }, 500);
      }
      return json([]);
    }
    return json([]);
  });
}

test('فاتورة المبيعات (1280px): عميل له فاتورة + عميل جديد + إغلاق/فتح العين + الاسم كاملاً', async ({ page }, testInfo) => {
  let releaseCustomer9: (() => void) | null = null;
  const pendingCustomer9 = new Promise<void>((resolve) => {
    releaseCustomer9 = resolve;
  });

  await page.setViewportSize({ width: 1280, height: 800 });
  await installRoutes(page, { eyeOpen: true }, { pendingCustomer9 });
  await page.goto('/sales/invoices/new');
  await expect(page.getByPlaceholder('اكتب اسم المنتج…').first()).toBeVisible({ timeout: 20_000 });

  const prodInput = page.getByPlaceholder('اكتب اسم المنتج…').first();
  await prodInput.click();
  await prodInput.fill('225');

  const pop = page.locator('.ktra-autocomplete-pop');
  await expect(pop).toBeVisible();
  await expect(pop).toHaveClass(/ktra-autocomplete-pop--twoline/);
  await expectPopInViewport(page, pop);

  const firstOption = pop.getByRole('option').first();
  const labelEl = firstOption.locator('.ktra-autocomplete-label');
  await expect(labelEl).toHaveText(LONG_TYRE_NAME);

  const dims = await labelEl.evaluate((el) => ({
    scrollW: el.scrollWidth,
    clientW: el.clientWidth,
    scrollH: el.scrollHeight,
    clientH: el.clientHeight,
  }));
  expect(dims.scrollW).toBeLessThanOrEqual(dims.clientW + 1);
  expect(dims.scrollH).toBeLessThanOrEqual(dims.clientH + 2);

  // رقاقتان دقيقتان مع زرّ العين مفتوحاً: «آخر» (120) و«أقل شراء (آخر ٥)» (75)
  const priceChips = firstOption.locator('.ktra-autocomplete-price');
  await expect(priceChips).toHaveCount(2);
  const chipTexts = await priceChips.allTextContents();
  const lastChip = chipTexts.find((t) => t.includes('120'));
  const lowestChip = chipTexts.find((t) => t.includes('أقل شراء (آخر ٥)'));
  expect(lastChip).toBeDefined();
  expect(lastChip).toContain('آخر');
  expect(lastChip).not.toContain('أقل شراء');
  expect(lowestChip).toBeDefined();
  expect(lowestChip).toContain('75');

  const optText = (await firstOption.textContent()) || '';
  expect(optText).not.toContain('أقل سعر');
  expect(optText).not.toContain('سعر عام');
  expect(optText).not.toContain('150');
  await pop.screenshot({ path: shotPath(testInfo, 'sales-1280-known.png') });

  // إغلاق زرّ العين مع العميل نفسه (7): لا 120 ولا 75 ولا «آخر» ولا «أقل شراء» في الخيار
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'إخفاء الأسعار والأرباح' }).click();
  await prodInput.click();
  await prodInput.fill('225');
  const popClosed = page.locator('.ktra-autocomplete-pop');
  await expect(popClosed).toBeVisible();
  await expectPopInViewport(page, popClosed);
  const closedOptText = (await popClosed.getByRole('option').first().textContent()) || '';
  expect(closedOptText).not.toContain('120');
  expect(closedOptText).not.toContain('75');
  expect(closedOptText).not.toContain('آخر');
  expect(closedOptText).not.toContain('أقل شراء');
  await expect(popClosed.locator('[title*="أقل شراء"], [title*="75"]')).toHaveCount(0);

  // إعادة فتح العين ثم تبديل العميل إلى 9 (جلب مؤجّل) ⇒ لا يبقى «آخر» العميل 7 (120) أثناء الانتظار
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'إظهار الأسعار والأرباح' }).click();
  const custInput = page.getByPlaceholder('اكتب اسم العميل…');
  await custInput.click();
  await custInput.fill('مؤجّل');
  await page.locator('.ktra-autocomplete-pop').getByRole('option').first().click();

  await prodInput.click();
  await prodInput.fill('225');
  const popPending = page.locator('.ktra-autocomplete-pop');
  await expect(popPending).toBeVisible();
  await expectPopInViewport(page, popPending);
  const pendingCustText = (await popPending.getByRole('option').first().textContent()) || '';
  expect(pendingCustText).not.toContain('120');
  expect(pendingCustText).toContain('آخر —');

  // نترقّب الاستجابة قبل إطلاقها كي لا تفوتنا، ثم نترك React يُحدّث الخريطة قبل الحكم
  const customer9Response = page.waitForResponse(
    (r) => r.url().includes('/customer-price-list/') && r.url().includes('customer=9'),
  );
  releaseCustomer9!();
  await customer9Response;
  await settleFrames(page);
  const releasedCustText = (await popPending.getByRole('option').first().textContent()) || '';
  expect(releasedCustText).toContain('95');
  expect(releasedCustText).toContain('آخر');
  expect(releasedCustText).not.toContain('آخر —');
  expect(releasedCustText).not.toContain('120');

  // اختيار عميل جديد (8) وبقاء منتقي العميل بسطرٍ واحد
  await page.keyboard.press('Escape');
  await custInput.click();
  await custInput.fill('عميل جديد');
  const custPop = page.locator('.ktra-autocomplete-pop');
  await expect(custPop).toBeVisible();
  await expect(custPop).not.toHaveClass(/ktra-autocomplete-pop--twoline/);
  await custPop.screenshot({ path: shotPath(testInfo, 'customer-picker-unchanged.png') });
  await custPop.getByRole('option').first().click();

  await prodInput.click();
  await prodInput.fill('225');
  const popNew = page.locator('.ktra-autocomplete-pop');
  await expect(popNew).toBeVisible();
  await expectPopInViewport(page, popNew);
  const newOptText = (await popNew.getByRole('option').first().textContent()) || '';
  expect(newOptText).toContain('آخر —');
  expect(newOptText).toContain('أقل شراء (آخر ٥)');
  expect(newOptText).not.toContain('عرض السعر');
  expect(newOptText).not.toContain('100');
  expect(newOptText).not.toContain('150');
  await popNew.screenshot({ path: shotPath(testInfo, 'sales-1280-new.png') });
});

test('فاتورة المبيعات (390px): عميل معروف وجديد وقائمة RTL بعرض 280px', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installRoutes(page, { eyeOpen: true });
  await page.goto('/sales/invoices/new');
  await expect(page.getByPlaceholder('اكتب اسم المنتج…').first()).toBeVisible({ timeout: 20_000 });

  const prodInput = page.getByPlaceholder('اكتب اسم المنتج…').first();
  await prodInput.click();
  await prodInput.fill('225');

  const pop = page.locator('.ktra-autocomplete-pop');
  await expect(pop).toBeVisible();
  await expect(pop).toHaveAttribute('dir', 'rtl');
  await expectPopInViewport(page, pop);
  await expectLabelNotClipped(pop.locator('.ktra-autocomplete-label').first());
  await pop.screenshot({ path: shotPath(testInfo, 'sales-390.png') });

  // اختيار عميل جديد عند 390px للتحقق من «آخر —» على الشاشة الضيّقة
  await page.keyboard.press('Escape');
  const custInput = page.getByPlaceholder('اكتب اسم العميل…');
  await custInput.click();
  await custInput.fill('عميل جديد');
  await page.locator('.ktra-autocomplete-pop').getByRole('option').first().click();

  await prodInput.click();
  await prodInput.fill('225');
  await expect(pop).toBeVisible();
  await expectPopInViewport(page, pop);
  expect((await pop.getByRole('option').first().textContent()) || '').toContain('آخر —');
  await expectLabelNotClipped(pop.locator('.ktra-autocomplete-label').first());
  await pop.screenshot({ path: shotPath(testInfo, 'sales-390-new.png') });

  // فرض عرض 280px صراحةً وإثبات تحقّق القيد، ثم فحص عرض الاسم وارتفاعه في RTL
  await pop.evaluate((el) => { el.style.width = '280px'; });
  const metrics = await pop.evaluate((el) => {
    const popRect = el.getBoundingClientRect();
    const main = el.querySelector('.ktra-autocomplete-main') as HTMLElement;
    const label = el.querySelector('.ktra-autocomplete-label') as HTMLElement;
    const mainStyle = getComputedStyle(main);
    const labelStyle = getComputedStyle(label);
    const mainContentW =
      main.clientWidth - parseFloat(mainStyle.paddingLeft || '0') - parseFloat(mainStyle.paddingRight || '0');
    const labelRect = label.getBoundingClientRect();
    const lineHeight = parseFloat(labelStyle.lineHeight) || parseFloat(labelStyle.fontSize) * 1.35;
    return {
      popWidth: popRect.width,
      mainContentW,
      labelWidth: labelRect.width,
      labelHeight: labelRect.height,
      labelScrollH: label.scrollHeight,
      labelClientH: label.clientHeight,
      lineHeight,
    };
  });
  expect(metrics.popWidth).toBeGreaterThanOrEqual(275);
  expect(metrics.popWidth).toBeLessThanOrEqual(285);
  expect(metrics.labelWidth).toBeGreaterThanOrEqual(metrics.mainContentW * 0.8);
  expect(metrics.labelHeight).toBeLessThanOrEqual(metrics.lineHeight * 2 + 2);
  expect(metrics.labelScrollH).toBeLessThanOrEqual(metrics.labelClientH + 2);
  await expectPopInViewport(page, pop);
  await pop.screenshot({ path: shotPath(testInfo, 'rtl-280.png') });
});

test('فاتورة الشراء (1280px): «آخر شراء» من المورد فقط + العين + مسح السعر عند تبديل المورد وعدم بقاء سعرٍ قديم بعد فشل الجلب', async ({ page }, testInfo) => {
  let releaseSupplier11: (() => void) | null = null;
  const pendingSupplier11 = new Promise<void>((resolve) => {
    releaseSupplier11 = resolve;
  });

  await page.setViewportSize({ width: 1280, height: 800 });
  await installRoutes(page, { eyeOpen: true }, { pendingSupplier11 });
  await page.goto('/purchase-invoices/new');
  await expect(page.getByPlaceholder('اكتب اسم المورّد…')).toBeVisible({ timeout: 20_000 });

  const supInput = page.getByPlaceholder('اكتب اسم المورّد…');
  await supInput.click();
  await supInput.fill('مورد الإطارات');
  const supPop = page.locator('.ktra-autocomplete-pop');
  await expect(supPop).toBeVisible();
  await expect(supPop).not.toHaveClass(/ktra-autocomplete-pop--twoline/);
  await expect(supPop.getByText('#10 · رام الله')).toBeVisible();
  await supPop.screenshot({ path: shotPath(testInfo, 'supplier-picker-unchanged.png') });
  await supPop.getByRole('option').first().click();

  await page.getByRole('tab', { name: 'البنود والمنتجات' }).click();
  const prodInput = page.getByPlaceholder('اكتب اسم المنتج…').first();
  await prodInput.click();
  await prodInput.fill('');

  const prodPop = page.locator('.ktra-autocomplete-pop');
  await expect(prodPop).toBeVisible();
  await expect(prodPop).toHaveClass(/ktra-autocomplete-pop--twoline/);
  await expectPopInViewport(page, prodPop);

  const firstOpt = prodPop.getByRole('option').nth(0);
  const firstChips = firstOpt.locator('.ktra-autocomplete-price');
  await expect(firstChips).toHaveCount(1);
  const firstChipText = (await firstChips.first().textContent()) || '';
  expect(firstChipText).toContain('48.5');
  expect(firstChipText).toContain('آخر شراء');
  const firstOptText = (await firstOpt.textContent()) || '';
  expect(firstOptText).not.toContain('أقل شراء');
  expect(firstOptText).not.toContain('75');

  // المنتج الثاني بلا شراء سابق من هذا المورد و«أقل شراء» عامّ فقط (kind=lowest) ⇒ «آخر —»
  const secondOptText = (await prodPop.getByRole('option').nth(1).textContent()) || '';
  expect(secondOptText).toContain('آخر —');
  expect(secondOptText).not.toContain('أقل شراء');
  expect(secondOptText).not.toContain('31.75');
  await prodPop.screenshot({ path: shotPath(testInfo, 'purchase-1280.png') });

  // إغلاق العين في الشراء ⇒ غياب 48.5 و«آخر» من القائمة
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'إخفاء الأسعار والأرباح' }).click();
  await prodInput.click();
  await expect(prodPop).toBeVisible();
  const closedPurchaseText = (await prodPop.getByRole('option').nth(0).textContent()) || '';
  expect(closedPurchaseText).not.toContain('48.5');
  expect(closedPurchaseText).not.toContain('آخر');

  // إعادة فتح العين ثم تبديل المورد إلى 11 (جلب مؤجّل) ⇒ مسح 48.5 فوراً أثناء الانتظار
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'إظهار الأسعار والأرباح' }).click();
  await page.getByRole('tab').first().click();
  await supInput.click();
  await supInput.fill('مؤجّل');
  await page.locator('.ktra-autocomplete-pop').getByRole('option').first().click();

  await page.getByRole('tab', { name: 'البنود والمنتجات' }).click();
  await prodInput.click();
  await prodInput.fill('225');
  await expect(prodPop).toBeVisible();
  await expectPopInViewport(page, prodPop);
  const pendingText = (await prodPop.getByRole('option').first().textContent()) || '';
  expect(pendingText).not.toContain('48.5');
  expect(pendingText).toContain('آخر —');

  // نترقّب الاستجابة قبل إطلاقها كي لا تفوتنا، ثم نترك React يُحدّث الخريطة قبل الحكم
  const supplier11Response = page.waitForResponse(
    (r) => r.url().includes('/price-list/') && r.url().includes('supplier=11'),
  );
  releaseSupplier11!();
  await supplier11Response;
  await settleFrames(page);
  const settledText = (await prodPop.getByRole('option').first().textContent()) || '';
  expect(settledText).not.toContain('48.5');
  expect(settledText).not.toContain('75');
  expect(settledText).toContain('آخر —');

  // تبديل المورد إلى 12 (فشل 500) ⇒ لا يبقى سعرٌ قديم بعد فشل الجلب وتظهر «آخر —».
  // الـeffect يمسح الخريطة قبل كل جلب، فهذه الخطوة تثبت غياب السعر القديم لا مسح `.catch` وحده.
  await page.keyboard.press('Escape');
  await page.getByRole('tab').first().click();
  await supInput.click();
  await supInput.fill('يفشل');
  await page.locator('.ktra-autocomplete-pop').getByRole('option').first().click();

  await page.getByRole('tab', { name: 'البنود والمنتجات' }).click();
  await prodInput.click();
  await prodInput.fill('225');
  await expect(prodPop).toBeVisible();
  const failedText = (await prodPop.getByRole('option').first().textContent()) || '';
  expect(failedText).toContain('آخر —');
  expect(failedText).not.toContain('48.5');
});

test('فاتورة الشراء (390px): «آخر شراء» من المورد على الشاشة الضيّقة', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installRoutes(page, { eyeOpen: true });
  await page.goto('/purchase-invoices/new');
  await expect(page.getByPlaceholder('اكتب اسم المورّد…')).toBeVisible({ timeout: 20_000 });

  const supInput = page.getByPlaceholder('اكتب اسم المورّد…');
  await supInput.click();
  await supInput.fill('مورد الإطارات');
  await page.locator('.ktra-autocomplete-pop').getByRole('option').first().click();

  await page.getByRole('tab', { name: 'البنود والمنتجات' }).click();
  const prodInput = page.getByPlaceholder('اكتب اسم المنتج…').first();
  // الحقل داخل حاوية أفقية على 390px: نُظهره ونُركّز عليه ونترك التمرير يستقرّ قبل الكتابة،
  // لأن أي تمرير بعد فتح القائمة يُغلقها ويمسح الاستعلام (`KitAutocomplete`).
  await prodInput.scrollIntoViewIfNeeded();
  await settleFrames(page);
  await prodInput.click();
  await settleFrames(page);
  await prodInput.pressSequentially('225');

  const pop = page.locator('.ktra-autocomplete-pop');
  await expect(pop).toBeVisible();
  await expect(pop).toHaveClass(/ktra-autocomplete-pop--twoline/);
  await expectPopInViewport(page, pop);
  const firstOptText = (await pop.getByRole('option').first().textContent()) || '';
  expect(firstOptText).toContain('آخر شراء');
  expect(firstOptText).toContain('48.5');
  expect(firstOptText).not.toContain('أقل شراء');
  await pop.screenshot({ path: shotPath(testInfo, 'purchase-390.png') });
});
