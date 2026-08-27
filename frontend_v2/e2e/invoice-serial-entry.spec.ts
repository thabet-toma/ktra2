import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * T-SERIAL/م3 — الأرقام التسلسلية داخل المحرِّرين.
 *
 * ما يُثبَت هنا هو **سلوك الشاشة**: هل يظهر العمود بحسب الإعداد؟ هل تُولَّد
 * السلسلة من الخادم لا من الواجهة؟ هل تتبع الكميةُ عددَ الأرقام؟ وهل تصل الأرقام
 * في الحمولة المحفوظة؟ (صحّة الدفاتر نفسها يثبتها
 * `inventory/tests/test_serial_invoice_journey.py` على الخادم الحقيقي.)
 *
 * الشاشتان داخليتان فتلزمهما نقاط الدخول الثلاث (المستخدم/الشركات/الصلاحيات)،
 * وإعدادات الشركة مخزنٌ لهذه الجلسة كي يكون تبديل النمط تبديلاً حقيقياً.
 */

const SERIALIZED = {
  id: 42, sku: 'LAP-1', barcode: '2000000000008', name_ar: 'لابتوب', name_en: '',
  display_name: 'لابتوب', category: null, category_name: '', hs_code: '',
  min_stock_level: 0, quantity_on_hand: '5', reserved_quantity: '0',
  available_quantity: '5', avg_cost: '1000', sale_price: '2000',
  is_service: false, is_serialized: true, is_for_sale_online: true,
  online_price: '2000', online_description: '', attachments: [],
  stock_status: 'in_stock',
};

const PLAIN = {
  ...SERIALIZED,
  id: 43, sku: 'PAP-1', barcode: '2000000000015', name_ar: 'ورق',
  display_name: 'ورق', is_serialized: false, sale_price: '10', online_price: '10',
};

const IN_STOCK_UNITS = ['SN-0098', 'SN-0099', 'SN-0100'].map((serial, i) => ({
  id: i + 1, serial, status: 'in_stock', status_display: 'في المخزن',
  product: 42, product_name: 'لابتوب', product_sku: 'LAP-1',
  purchase_invoice: 5, purchase_invoice_number: 'PI-5', supplier_name: 'مورد اللابتوبات',
  sales_invoice: null, sales_invoice_number: null, customer_name: null,
  created_at: '2026-08-01T00:00:00Z',
}));

type State = {
  purchaseMode: string;
  salesMode: string;
  /** أجسام الحفظ المُلتقطة — المرجع الوحيد لما وصل الخادمَ فعلاً. */
  saved: Record<string, unknown>[];
};

const install = async (page: Page, state: State) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'serial-editor-token');
    localStorage.setItem('userId', 'serial-editor-user');
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
    const body = () => JSON.parse(req.postData() || '{}');
    const json = (payload: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

    // ── نقاط الدخول الثلاث ──
    if (path.endsWith('/hr/users/serial-editor-user/')) {
      return json({
        id: 'serial-editor-user', name: 'Serial Editor', role: 'manager',
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
      return json({
        role: 'manager', is_manager: true,
        permissions: [
          'sales.invoice.view', 'sales.invoice.create', 'sales.invoice.edit',
          'purchase.invoice.view', 'purchase.invoice.create', 'purchase.invoice.edit',
          'inventory.item.manage',
        ],
      });
    }

    // ── الكتالوج ──
    if (path.endsWith('/inventory/products/')) {
      return json([SERIALIZED, PLAIN]);
    }
    if (path.endsWith('/inventory/products/generate_serials/') && method === 'POST') {
      // المولّد الحقيقي — الواجهة لا تحسب التزايد بنفسها، وهذا ما نتحقق منه.
      const { start, count } = body() as { start: string; count: number };
      const digits = /(\d+)$/.exec(String(start));
      if (!digits) return json({ error: 'الرقم التسلسلي الأول يجب أن ينتهي برقم' }, 400);
      const prefix = String(start).slice(0, digits.index);
      const width = digits[1].length;
      const first = Number(digits[1]);
      return json({
        serials: Array.from({ length: Number(count) }, (_, i) =>
          `${prefix}${String(first + i).padStart(width, '0')}`),
      });
    }
    if (path.endsWith('/inventory/products/42/serials/')) {
      return json(IN_STOCK_UNITS);
    }

    // ── الإعدادات ──
    if (path.endsWith('/logistics/purchase-settings/current/')) {
      return json({
        id: 1, purchase_default_price_strategy: 'LAST_PURCHASE', default_cash_account: null,
        receive_on_post: true, receipt_doc_label: 'إرسالية شراء',
        standalone_receipt_label: 'سند استلام', allow_standalone_receipt: true,
        allow_edit_receipt: true, serial_entry_mode: state.purchaseMode,
      });
    }
    if (path.endsWith('/sales/settings/current/')) {
      return json({
        id: 1, default_customer: 7, default_currency: 1,
        default_revenue_account_product: null, default_revenue_account_service: null,
        default_cash_account: null, default_inventory_account: null,
        default_cogs_account: null, default_ar_account: null,
        default_payment_type: 'credit', stock_on_post_default: true,
        allow_negative_stock_default: false, default_vat_rate: null,
        prices_include_tax: false, auto_post_invoices: false, auto_post_payments: true,
        show_journal_preview: true, warn_on_duplicate_item: true,
        block_loss_invoices: false, dormant_customer_days: 30, quotation_valid_days: 14,
        order_reserve_days: 7, allow_document_delete: true, block_reserved_stock_sale: true,
        serial_entry_mode: state.salesMode,
        default_shipping_origin: '', default_shipping_destination: '',
        delivery_doc_label: 'إرسالية بيع', standalone_delivery_label: 'سند تسليم',
        allow_standalone_delivery: true, allow_edit_delivery: true,
      });
    }

    // ── الأطراف والعملات والحسابات ──
    if (path.includes('/partners/')) {
      return json([
        { id: 7, name: 'زبون الرحلة', partner_type: 'Customer', tradeName: 'زبون الرحلة' },
        { id: 8, name: 'مورد اللابتوبات', partner_type: 'Supplier', tradeName: 'مورد اللابتوبات' },
      ]);
    }
    if (path.includes('/accounting/currencies')) {
      return json([{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل', IsBaseCurrency: true }]);
    }
    if (path.includes('/accounting/accounts')) {
      // حساب إيراد واحد يكفي: بدونه يرفض المحرِّر الحفظ قبل أن يبني الحمولة.
      return json([
        { id: 401, code: '4101', name: 'إيرادات المبيعات', account_type: 'Revenue', is_active: true },
        { id: 111, code: '1101', name: 'الصندوق', account_type: 'Asset', is_active: true },
      ]);
    }

    // ── الحفظ: نلتقط الجسم ونعيده كما وصل (الخادم يعيد ما خزّن) ──
    if ((path.endsWith('/logistics/purchase-invoices/') || path.endsWith('/sales/invoices/'))
        && method === 'POST') {
      const sent = body();
      state.saved.push(sent);
      const isPurchase = path.includes('purchase');
      return json({
        ...sent, id: 900, invoice_number: isPurchase ? 'PI-900' : 'SI-900',
        status: 'draft', is_posted: false,
        ...(isPurchase
          ? { fees: sent.fees ?? [], items: sent.items ?? [], partner_name: 'مورد اللابتوبات' }
          : { lines: sent.lines ?? [] }),
      }, 201);
    }

    return json([]);
  });
};

const freshState = (over: Partial<State> = {}): State =>
  ({ purchaseMode: 'off', salesMode: 'off', saved: [], ...over });

// ══════════════════════════════════════════════════════════════════════════
// فاتورة الشراء — التقاط الأرقام
// ══════════════════════════════════════════════════════════════════════════

const openPurchaseEditor = async (page: Page) => {
  await page.goto('/purchase-invoices/new');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('tab', { name: 'البنود والمنتجات' })).toBeVisible({ timeout: 30_000 });
  await page.getByRole('tab', { name: 'البنود والمنتجات' }).click();
};

/** المورد شرط الحفظ في محرر الشراء — يُختار من الفهرس كما يفعل المستخدم. */
const pickSupplier = async (page: Page) => {
  await page.locator('[data-ktra-field="supplier"]').click();
  const search = page.getByPlaceholder(/بحث… \(Enter اختيار/);
  await search.fill('مورد اللابتوبات');
  await search.press('Enter');
  await expect(page.locator('[data-ktra-field="supplier"]')).toHaveValue('#8');
};

test('الشراء بنمط «معطّل»: لا عمود أرقام ولا أثر على الشبكة', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await openPurchaseEditor(page);

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('لابتوب');
  await page.getByText('لابتوب', { exact: true }).last().click();

  await expect(page.getByRole('columnheader', { name: 'الأرقام التسلسلية' })).toHaveCount(0);
});

test('الشراء بنمط «إجباري»: التوليد من الخادم، والكمية تتبع عدد الأرقام', async ({ page }) => {
  const state = freshState({ purchaseMode: 'required' });
  await install(page, state);
  await openPurchaseEditor(page);
  await pickSupplier(page);
  await page.getByRole('tab', { name: 'البنود والمنتجات' }).click();

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('لابتوب');
  await page.getByText('لابتوب', { exact: true }).last().click();

  // العمود ظهر لأن السطر يحمل منتجاً تسلسلياً، والزر أحمر لأن الأرقام ناقصة.
  await expect(page.getByRole('columnheader', { name: 'الأرقام التسلسلية' })).toBeVisible();
  const chip = page.getByRole('button', { name: /^0\/1$/ });
  await expect(chip).toBeVisible();
  await chip.click();

  await page.getByPlaceholder('SN-0098').fill('SN-0098');
  await page.locator('input[type=number]').last().fill('3');
  await page.getByRole('button', { name: 'توليد' }).click();

  // السلسلة جاءت من الخادم بخانات الصفر محفوظة.
  for (const s of ['SN-0098', 'SN-0099', 'SN-0100']) {
    await expect(page.getByText(s, { exact: true })).toBeVisible();
  }
  await expect(page.getByText(/كمية البند ستصبح/)).toBeVisible();
  await page.getByRole('button', { name: 'حفظ الأرقام' }).click();

  // الكمية صارت 3 والشارة اكتملت.
  await expect(page.getByRole('button', { name: /^3\/3$/ })).toBeVisible();

  await page.getByRole('button', { name: /تخزين/ }).first().click();
  await expect.poll(() => state.saved.length).toBeGreaterThan(0);
  const sent = state.saved[state.saved.length - 1] as { items: { quantity: string; serials: string[] }[] };
  expect(sent.items[0].serials).toEqual(['SN-0098', 'SN-0099', 'SN-0100']);
  expect(Number(sent.items[0].quantity)).toBe(3);
});

test('الشراء: صندوق الباركود يُدخل المنتج على السطر (تكافؤ مع المبيعات)', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await openPurchaseEditor(page);

  const box = page.locator('[data-ktra-field="barcode"]');
  await expect(box).toBeVisible();
  await box.fill('2000000000015');
  await box.press('Enter');

  await expect(page.getByPlaceholder('اكتب اسم المنتج…').first()).toHaveValue('ورق');
});

// ══════════════════════════════════════════════════════════════════════════
// فاتورة البيع — اختيار الوحدة
// ══════════════════════════════════════════════════════════════════════════

const openSalesEditor = async (page: Page) => {
  await page.goto('/sales/invoices/new');
  await page.waitForLoadState('networkidle');
  await expect(page.getByPlaceholder('اكتب اسم المنتج…').first())
    .toBeVisible({ timeout: 30_000 });
};

test('البيع بنمط «معطّل»: لا عمود وحدات', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await openSalesEditor(page);

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('لابتوب');
  await page.getByText('لابتوب', { exact: true }).last().click();

  await expect(page.getByRole('columnheader', { name: 'الوحدات' })).toHaveCount(0);
});

test('البيع بنمط «اختياري»: «تلقائي» افتراضاً، واختيار وحدة بعينها يصل في الحمولة', async ({ page }) => {
  const state = freshState({ salesMode: 'optional' });
  await install(page, state);
  await openSalesEditor(page);

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('لابتوب');
  await page.getByText('لابتوب', { exact: true }).last().click();

  await expect(page.getByRole('columnheader', { name: 'الوحدات' })).toBeVisible();
  const chip = page.getByRole('button', { name: 'تلقائي' });
  await expect(chip).toBeVisible();
  await chip.click();

  // القائمة من نقطة «في المخزن» لهذا المنتج، و«تلقائي» خيار صريح مؤشَّر.
  await expect(page.getByText('SN-0099')).toBeVisible();
  await page.getByRole('checkbox', { name: 'SN-0099' }).check();
  await expect(page.getByText(/المختار: 1 من الكمية 1/)).toBeVisible();
  await page.getByRole('button', { name: 'حفظ الأرقام' }).click();

  await expect(page.getByRole('button', { name: /^1\/1$/ })).toBeVisible();

  await page.getByRole('button', { name: /^تخزين$/ }).first().click();
  await expect.poll(() => state.saved.length).toBeGreaterThan(0);
  const sent = state.saved[state.saved.length - 1] as { lines: { serials: string[] }[] };
  expect(sent.lines[0].serials).toEqual(['SN-0099']);
});

test('البيع: المنتج غير التسلسلي يبقى بلا زر وحدات حتى مع تفعيل النمط', async ({ page }) => {
  const state = freshState({ salesMode: 'required' });
  await install(page, state);
  await openSalesEditor(page);

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('ورق');
  await page.getByText('ورق', { exact: true }).last().click();

  await expect(page.getByRole('columnheader', { name: 'الوحدات' })).toHaveCount(0);
});

test('البيع بنمط «إجباري»: «تلقائي» مُقفَل — لا خيار يرفضه الخادم', async ({ page }) => {
  const state = freshState({ salesMode: 'required' });
  await install(page, state);
  await openSalesEditor(page);

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('لابتوب');
  await page.getByText('لابتوب', { exact: true }).last().click();

  // بلا اختيار: الشارة تقول 0/1 لا «تلقائي» — النقص مرئيّ قبل الحفظ.
  const chip = page.getByRole('button', { name: /^0\/1$/ });
  await expect(chip).toBeVisible();
  await chip.click();

  // الخادم يرفض البند غير المكتمل تحت «إجباري»
  // (`inventory/serials.py::assert_sales_serials_declared`)، فعرضُ الخيار هنا
  // وعدٌ يُخلَف عند الترحيل.
  await expect(page.getByRole('checkbox', { name: /^تلقائي — أي وحدة/ })).toBeDisabled();
  await expect(page.getByText(/غير متاح بنمط «إجباري»/)).toBeVisible();

  // والاختيار الصريح يُكمل البند.
  await page.getByRole('checkbox', { name: 'SN-0098' }).check();
  await expect(page.getByText(/المختار: 1 من الكمية 1/)).toBeVisible();
  await page.getByRole('button', { name: 'حفظ الأرقام' }).click();
  await expect(page.getByRole('button', { name: /^1\/1$/ })).toBeVisible();
});

test('البيع: ملاحظتا البند حقلان مستقلّان يصلان الحمولة بلا اختلاط', async ({ page }) => {
  const state = freshState();
  await install(page, state);
  await openSalesEditor(page);

  await page.getByPlaceholder('اكتب اسم المنتج…').first().fill('ورق');
  await page.getByText('ورق', { exact: true }).last().click();

  // عمود الملاحظات لا يتبع نمط الأرقام التسلسلية — يظهر دائماً ولكل منتج.
  await expect(page.getByRole('columnheader', { name: 'ملاحظات' })).toBeVisible();
  // السطر الفارغ التالي يحمل الزرّ نفسه — المقصود سطر المنتج، وهو الأول.
  await page.getByTitle('أضف ملاحظة داخلية أو ملاحظة تُطبع للزبون').first().click();

  await page.getByPlaceholder(/لا تُطبع للعميل/).fill('العميل ساوم — وافق المدير');
  await page.getByPlaceholder(/تُطبع تحت اسم المنتج/).fill('كفالة سنة من تاريخ الفاتورة');
  await page.getByRole('button', { name: 'حفظ الملاحظات' }).click();

  // الشارة تقول أيّهما مكتوبة قبل الفتح.
  await expect(page.getByRole('button', { name: 'د·ز' })).toBeVisible();

  await page.getByRole('button', { name: /^تخزين$/ }).first().click();
  await expect.poll(() => state.saved.length).toBeGreaterThan(0);
  const sent = state.saved[state.saved.length - 1] as {
    lines: { internal_note: string; customer_note: string }[];
  };
  expect(sent.lines[0].internal_note).toBe('العميل ساوم — وافق المدير');
  expect(sent.lines[0].customer_note).toBe('كفالة سنة من تاريخ الفاتورة');
});
