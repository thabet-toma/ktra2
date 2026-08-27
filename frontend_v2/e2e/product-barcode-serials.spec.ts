import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * T-SERIAL/م2 — كرت المنتج: توليد الباركود وطباعته وتتبّع الأرقام التسلسلية،
 * وإعدادا الشراء والبيع لنمط إدخال الرقم.
 *
 * الشاشات داخلية، فتلزمها نقاط الدخول الوهمية الثلاث (المستخدم/الشركات/الصلاحيات).
 * إعدادات الشركة هنا **مخزن قابل للكتابة**: الحفظ يكتب فيه والتحميل يقرأ منه، فيكون
 * «غيّر ← أعد التحميل ← ما زال محفوظاً» دورةً حقيقية لا تأكيداً على نفسه.
 */

const PRODUCT = {
  id: 42,
  sku: 'P-0042',
  barcode: '',
  name_ar: 'إطار 195/65/15',
  name_en: '',
  brand: 'روك بيلد',
  category: 7,
  category_name: 'إطارات',
  is_service: false,
  is_serialized: false,
  sale_price: '250',
  min_stock_level: 4,
  quantity_on_hand: 12,
  avg_cost: 180,
  stock_status: 'in_stock',
  attachments: [],
};

const PROFILE = {
  id: 42, sku: 'P-0042', name: 'إطار 195/65/15', category: 'إطارات',
  barcode: '', is_service: false, min_stock_level: 4,
  quantity_on_hand: '12', avg_cost: '180', inventory_valuation: '2160',
  purchased_qty: '20', purchased_value: '3600', sold_qty: '8', sold_value: '2000',
  effective_sale_price: '250', sale_price: '250', profit_per_unit: '70',
};

const SERIALS = [
  {
    id: 1, serial: 'SN-0098', status: 'in_stock', status_display: 'في المخزن',
    product: 42, product_name: 'إطار 195/65/15', product_sku: 'P-0042',
    purchase_invoice: 5, purchase_invoice_number: 'PI-5', supplier_name: 'مورد الإطارات',
    sales_invoice: null, sales_invoice_number: null, customer_name: null,
    created_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 2, serial: 'SN-0099', status: 'sold', status_display: 'مُباع',
    product: 42, product_name: 'إطار 195/65/15', product_sku: 'P-0042',
    purchase_invoice: 5, purchase_invoice_number: 'PI-5', supplier_name: 'مورد الإطارات',
    sales_invoice: 9, sales_invoice_number: 'SI-9', customer_name: 'زبون تجريبي',
    created_at: '2026-08-02T00:00:00Z',
  },
];

/** حالة الخادم الوهمي لهذه الجلسة — يكتب فيها الحفظ ويقرأ منها التحميل. */
type ServerState = {
  product: Record<string, unknown>;
  salesSettings: Record<string, unknown>;
  purchaseSettings: Record<string, unknown>;
  productPatches: Record<string, unknown>[];
  /** الأرقام التي أرسلها زر «تسجيل أرقام لمخزون قائم». */
  registered: string[];
};

const freshState = (): ServerState => ({
  product: { ...PRODUCT },
  salesSettings: {
    id: 1, default_customer: null, default_currency: null,
    default_revenue_account_product: null, default_revenue_account_service: null,
    default_cash_account: null, default_inventory_account: null, default_cogs_account: null,
    default_ar_account: null, default_payment_type: 'credit',
    stock_on_post_default: true, allow_negative_stock_default: false,
    default_vat_rate: null, prices_include_tax: false, auto_post_invoices: false,
    auto_post_payments: true, show_journal_preview: true, warn_on_duplicate_item: true,
    block_loss_invoices: false, dormant_customer_days: 30, quotation_valid_days: 14,
    order_reserve_days: 7, allow_document_delete: true, block_reserved_stock_sale: true,
    serial_entry_mode: 'off',
    default_shipping_origin: '', default_shipping_destination: '',
    delivery_doc_label: 'إرسالية بيع', standalone_delivery_label: 'سند تسليم',
    allow_standalone_delivery: true, allow_edit_delivery: true,
  },
  purchaseSettings: {
    purchase_default_price_strategy: 'LAST_PURCHASE', default_cash_account: null,
    receive_on_post: true, receipt_doc_label: 'إرسالية شراء',
    standalone_receipt_label: 'سند استلام', allow_standalone_receipt: true,
    allow_edit_receipt: true, serial_entry_mode: 'off',
  },
  productPatches: [],
  registered: [],
});

const install = async (page: Page, state: ServerState) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'serial-e2e-token');
    localStorage.setItem('userId', 'serial-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const isApi = url.port === '8000'
      || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = req.method();
    const json = (body: unknown) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });

    // ── نقاط الدخول الثلاث ──
    if (path.endsWith('/hr/users/serial-e2e-user/')) {
      return json({
        id: 'serial-e2e-user', name: 'Serial Tester', role: 'manager',
        email: 'serial@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الأرقام', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (path.endsWith('/permissions/me/')) {
      // `can()` بحثٌ صريح في المجموعة — الدور «مدير» وحده لا يفتح شاشةً مُفهرسة
      // في `VIEW_PERMISSIONS`، فتُذكر مفاتيح الشاشتين صراحةً.
      return json({
        role: 'manager',
        is_manager: true,
        permissions: ['sales.settings.manage', 'purchase.settings.manage', 'inventory.item.manage'],
      });
    }

    // ── كرت المنتج ──
    if (path.endsWith('/inventory/products/generate_barcode/') && method === 'POST') {
      return json({ barcode: '2000000000008' });
    }
    // ترقيم مخزون قائم — يكتب في حالة الجلسة فتُقرأ الوحدة الجديدة كما لو حُفظت.
    if (path.endsWith('/inventory/products/42/serials/register/') && method === 'POST') {
      const body = JSON.parse(req.postData() || '{}') as { serials?: string[] };
      state.registered.push(...(body.serials || []));
      const rows = (body.serials || []).map((serial, i) => ({
        id: 100 + i, serial, status: 'in_stock', status_display: 'في المخزن',
        product: 42, product_name: 'إطار 195/65/15', product_sku: 'P-0042',
        purchase_invoice: null, purchase_invoice_number: null, supplier_name: null,
        sales_invoice: null, sales_invoice_number: null, customer_name: null,
        created_at: '2026-08-05T00:00:00Z',
      }));
      return json({ created: rows.length, serials: [...SERIALS, ...rows] });
    }
    if (path.endsWith('/inventory/products/42/serials/')) {
      return json(SERIALS);
    }
    if (path.endsWith('/inventory/products/42/profile/')) {
      return json({ ...PROFILE, barcode: state.product.barcode });
    }
    if (path.endsWith('/inventory/products/42/stock-ledger/')) {
      return json({ results: [], count: 0 });
    }
    if (path.endsWith('/inventory/products/42/invoices/')) {
      return json([]);
    }
    if (path.endsWith('/inventory/products/42/')) {
      if (method === 'PATCH') {
        const patch = JSON.parse(req.postData() || '{}');
        state.productPatches.push(patch);
        state.product = { ...state.product, ...patch };
        return json(state.product);
      }
      return json(state.product);
    }

    // ── الإعدادات: مخزن حقيقي للدورة ──
    if (path.endsWith('/sales/settings/current/')) {
      if (method === 'PATCH') {
        state.salesSettings = { ...state.salesSettings, ...JSON.parse(req.postData() || '{}') };
      }
      return json(state.salesSettings);
    }
    if (path.endsWith('/logistics/purchase-settings/current/')) {
      if (method === 'PATCH') {
        state.purchaseSettings = { ...state.purchaseSettings, ...JSON.parse(req.postData() || '{}') };
      }
      return json(state.purchaseSettings);
    }

    return json([]);
  });
};

const barcodeField = (page: Page) =>
  page.locator('.ktra-field:has(span:text-is("الباركود (EAN-13)")) input').first();

const generalTab = async (page: Page) => {
  await page.getByRole('tab', { name: 'بيانات عامة' }).click();
};

// ══════════════════════════════════════════════════════════════════════════
// كرت المنتج — الباركود
// ══════════════════════════════════════════════════════════════════════════

test('«توليد تلقائي» يجلب باركوداً من الخادم ويرسمه، والحفظ يثبّته على المنتج', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.goto('/products/42');
  await page.waitForLoadState('networkidle');
  await generalTab(page);

  const field = barcodeField(page);
  await expect(field).toHaveValue('');
  // لا رسم ولا زرّ طباعة قبل وجود باركود صالح.
  await expect(page.getByRole('button', { name: 'طباعة ملصق' })).toHaveCount(0);

  await page.getByRole('button', { name: 'توليد تلقائي' }).click();
  await expect(field).toHaveValue('2000000000008');
  // الرسم ظهر (svg بعنوان الباركود) وزر الطباعة صار متاحاً.
  await expect(page.locator('svg[aria-label="باركود 2000000000008"]')).toBeVisible();
  await expect(page.getByRole('button', { name: 'طباعة ملصق' })).toBeVisible();

  await page.getByRole('button', { name: /تخزين/ }).click();
  await expect.poll(() => state.productPatches.length).toBeGreaterThan(0);
  const patch = state.productPatches[state.productPatches.length - 1];
  expect(patch.barcode).toBe('2000000000008');
  expect(state.product.barcode).toBe('2000000000008');
});

test('«إكمال» يحسب خانة التحقق لرقم مكتوب، والرقم المعطوب يُنبَّه عليه', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.goto('/products/42');
  await page.waitForLoadState('networkidle');
  await generalTab(page);

  const field = barcodeField(page);
  // 12 خانة → تُضاف خانة التحقق (400638133393 ⇒ 4006381333931).
  await field.fill('400638133393');
  await expect(page.getByText(/ليس باركود EAN-13 صالحاً/)).toBeVisible();
  await page.getByRole('button', { name: 'إكمال' }).click();
  await expect(field).toHaveValue('4006381333931');
  await expect(page.locator('svg[aria-label="باركود 4006381333931"]')).toBeVisible();

  // خانة تحقق خاطئة تُصحَّح ويُقال ذلك.
  await field.fill('5901234123450');
  await page.getByRole('button', { name: 'إكمال' }).click();
  await expect(field).toHaveValue('5901234123457');
  await expect(page.getByText(/خانة التحقق كانت 0 والصحيح 7/)).toBeVisible();

  await page.getByRole('button', { name: /تخزين/ }).click();
  await expect.poll(() => state.productPatches.length).toBeGreaterThan(0);
  expect(state.productPatches[state.productPatches.length - 1].barcode).toBe('5901234123457');
});

test('باركود مكرّر: رسالة الخادم تصل للمستخدم بدل «‎: 400»', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.route('**/inventory/products/42/', async (route) => {
    if (route.request().method() !== 'PATCH') return route.fallback();
    await route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ barcode: ['الباركود «4006381333931» مستخدم للمنتج «بطارية 70 أمبير».'] }),
    });
  });
  await page.goto('/products/42');
  await page.waitForLoadState('networkidle');
  await generalTab(page);

  await barcodeField(page).fill('4006381333931');
  await page.getByRole('button', { name: /تخزين/ }).click();
  await expect(page.getByText(/مستخدم للمنتج «بطارية 70 أمبير»/)).toBeVisible();
});

// ══════════════════════════════════════════════════════════════════════════
// كرت المنتج — تبويب الأرقام التسلسلية
// ══════════════════════════════════════════════════════════════════════════

test('تبويب الأرقام التسلسلية يظهر بالتفعيل وحده، ويسرد الوحدات ومستنداتها ويبحث فيها', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.goto('/products/42');
  await page.waitForLoadState('networkidle');

  // منتج غير متتبَّع: لا تبويب أصلاً (لا تبويب فارغ يوحي بعطل).
  await expect(page.getByRole('tab', { name: 'الأرقام التسلسلية' })).toHaveCount(0);

  await generalTab(page);
  await page.locator('.ktra-field:has(span:text-is("تتبّع بالرقم التسلسلي")) input[type=checkbox]').check();

  const tab = page.getByRole('tab', { name: 'الأرقام التسلسلية' });
  await expect(tab).toBeVisible();
  await tab.click();

  await expect(page.getByText('SN-0098')).toBeVisible();
  await expect(page.getByText('SN-0099')).toBeVisible();
  await expect(page.getByText('مورد الإطارات').first()).toBeVisible();
  await expect(page.getByText('زبون تجريبي')).toBeVisible();
  await expect(page.getByText(/1 في المخزن/)).toBeVisible();
  await expect(page.getByText(/1 مُباعة/)).toBeVisible();

  // البحث يشمل الرقم والطرف معاً.
  const search = page.getByPlaceholder('بحث برقم الوحدة أو الفاتورة أو الطرف…');
  await search.fill('SN-0098');
  await expect(page.getByText('SN-0099')).toHaveCount(0);
  await search.fill('زبون');
  await expect(page.getByText('SN-0099')).toBeVisible();
  await expect(page.getByText('SN-0098')).toHaveCount(0);

  // التفعيل يُحفَظ على المنتج.
  await page.getByRole('button', { name: /تخزين/ }).click();
  await expect.poll(() => state.productPatches.length).toBeGreaterThan(0);
  expect(state.productPatches[state.productPatches.length - 1].is_serialized).toBe(true);
});

test('«تسجيل أرقام لمخزون قائم» يرقّم الوحدات غير المتتبَّعة من الكرت نفسه', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.goto('/products/42');
  await page.waitForLoadState('networkidle');
  await generalTab(page);
  await page.locator('.ktra-field:has(span:text-is("تتبّع بالرقم التسلسلي")) input[type=checkbox]').check();
  await page.getByRole('tab', { name: 'الأرقام التسلسلية' }).click();

  // الرصيد 12 ومنه وحدة واحدة مُرقَّمة «في المخزن» ⇒ 11 بلا ترقيم.
  await expect(page.getByText(/11 بلا ترقيم/)).toBeVisible();
  await page.getByRole('button', { name: 'تسجيل أرقام لمخزون قائم' }).click();

  // نفس نافذة الإدخال (وضع الالتقاط) لا نسخة ثانية منها.
  const scan = page.getByPlaceholder('امسح الباركود أو اكتب الرقم ⏎');
  await scan.fill('OLD-1');
  await scan.press('Enter');
  await scan.fill('OLD-2');
  await scan.press('Enter');
  await page.getByRole('button', { name: 'حفظ الأرقام' }).click();

  await expect.poll(() => state.registered).toEqual(['OLD-1', 'OLD-2']);
  await expect(page.getByText('OLD-1')).toBeVisible();
  await expect(page.getByText('OLD-2')).toBeVisible();
  // الوحدات الجديدة صارت مُرقَّمة ⇒ الباقي بلا ترقيم نقص إلى 9.
  await expect(page.getByText(/9 بلا ترقيم/)).toBeVisible();
});

test('رفض الخادم لتسجيل فوق الرصيد يصل للمستخدم بنصّه', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.route('**/inventory/products/42/serials/register/', async (route) => {
    await route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        error: 'المنتج «إطار 195/65/15»: رصيد المخزن 12 وحدة ومنها 12 مُرقَّمة — لا مكان لتسجيل رقم إضافي.',
      }),
    });
  });
  await page.goto('/products/42');
  await page.waitForLoadState('networkidle');
  await generalTab(page);
  await page.locator('.ktra-field:has(span:text-is("تتبّع بالرقم التسلسلي")) input[type=checkbox]').check();
  await page.getByRole('tab', { name: 'الأرقام التسلسلية' }).click();
  await page.getByRole('button', { name: 'تسجيل أرقام لمخزون قائم' }).click();

  const scan = page.getByPlaceholder('امسح الباركود أو اكتب الرقم ⏎');
  await scan.fill('OLD-9');
  await scan.press('Enter');
  await page.getByRole('button', { name: 'حفظ الأرقام' }).click();

  await expect(page.getByText(/لا مكان لتسجيل رقم إضافي/)).toBeVisible();
});

// ══════════════════════════════════════════════════════════════════════════
// الإعدادات — دورة كاملة على الجانبين
// ══════════════════════════════════════════════════════════════════════════

test('إعدادات البيع: تغيير نمط الأرقام يُحفَظ ويبقى بعد إعادة التحميل', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.goto('/sales/settings');
  await page.waitForLoadState('networkidle');
  // الشاشة chunk كسول على خادم التطوير — انتظرها بدل افتراض أنها جاهزة.
  await expect(page.getByRole('button', { name: /حفظ الإعدادات/ })).toBeVisible({ timeout: 30_000 });

  const select = page.locator('label:has(span:text-is("إدخال الأرقام التسلسلية في فاتورة البيع")) select');
  await expect(select).toHaveValue('off');
  await expect(page.getByText(/إجباري = لا تُرحَّل الفاتورة بدون الأرقام/).first()).toBeVisible();

  await select.selectOption('required');
  await page.getByRole('button', { name: /حفظ الإعدادات/ }).click();
  await expect.poll(() => state.salesSettings.serial_entry_mode).toBe('required');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(
    page.locator('label:has(span:text-is("إدخال الأرقام التسلسلية في فاتورة البيع")) select'),
  ).toHaveValue('required', { timeout: 30_000 });
});

test('إعدادات الشراء: تغيير نمط الأرقام يُحفَظ ويبقى بعد إعادة التحميل', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await page.goto('/purchase-settings');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('إدخال الأرقام التسلسلية في فاتورة الشراء')).toBeVisible({ timeout: 30_000 });

  const select = page.locator('select').filter({ hasText: 'اختياري' }).first();
  await expect(select).toHaveValue('off');
  await expect(page.getByText(/إجباري = لا تُرحَّل الفاتورة بدون الأرقام/).first()).toBeVisible();

  await select.selectOption('optional');
  await page.getByRole('button', { name: /حفظ/ }).first().click();
  await expect.poll(() => state.purchaseSettings.serial_entry_mode).toBe('optional');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('select').filter({ hasText: 'اختياري' }).first())
    .toHaveValue('optional', { timeout: 30_000 });
});
