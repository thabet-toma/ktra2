import { test, expect, type Page } from '@playwright/test';

/**
 * THA-401 (T119-3) — شاشة الأرصدة الافتتاحية على عقد الخادم الحقيقي.
 *
 * `tsc` لا يفحص خصائص JSX في هذا المستودع، فبناءٌ أخضر لا يثبت أن الشاشة حيّة.
 * هذا الاختبار يفتح المسار من التنقّل نفسه ويمشي المسار: التبويبات الثلاثة،
 * تاريخ القيد المشتقّ، صافي حقوق الملكية، الترحيل خلف التأكيد، ثم خطأ الفترة
 * المالية بزرّه القابل للفعل. الحمولات المموّهة نسخةُ ما يُرجعه
 * `OpeningBalanceViewSet._payload` حرفياً — المبالغ نصوص والتواريخ ISO.
 */

const DRAFT = {
  id: 1,
  start_date: '2026-03-01',
  entry_date: '2026-02-28',
  status: 'draft' as const,
  journal: null,
  posted_at: null,
  account_lines: [
    {
      id: 1, account: 41, account_code: '1101', account_name: 'الصندوق',
      debit: '5000.00', credit: '0.00', notes: 'رصيد الصندوق عند البدء',
    },
    {
      id: 2, account: 55, account_code: '2103', account_name: 'قروض قصيرة الأجل',
      debit: '0.00', credit: '2000.00', notes: '',
    },
  ],
  stock_lines: [
    {
      id: 1, product: 7, product_sku: 'P-007', product_name: 'إطار 255/65/15',
      warehouse: 2, warehouse_name: 'المستودع الرئيسي',
      quantity: '10.0000', unit_cost: '300.0000', value: '3000.00',
    },
  ],
  partners: [
    {
      id: 3, name: 'عميل تجريبي', partner_type: 'Customer',
      opening_balance: '1200.00', opening_balance_date: '2026-02-28',
      linked_account: 88, is_posted: true, journal: 9, posted_amount: '1200.00',
    },
    {
      id: 4, name: 'مورّد تجريبي', partner_type: 'Supplier',
      opening_balance: '-500.00', opening_balance_date: null,
      linked_account: 89, is_posted: false, journal: null, posted_amount: null,
    },
  ],
  // منتجاتٌ متتبَّعة تسلسلياً: فارغة هنا — الشاشة غير المرحّلة لا تعرض اللوحة أصلاً.
  serial_items: [] as Array<{
    product: number; product_sku: string; product_name: string;
    quantity: number; serials_registered: number;
  }>,
  totals: {
    accounts_debit: '5000.00', accounts_credit: '2000.00',
    stock_value: '3000.00', equity_plug: '6000.00',
  },
  offset_account_code: '3300',
};

const POSTED = {
  ...DRAFT,
  status: 'posted' as const,
  journal: 77,
  posted_at: '2026-08-17T10:00:00Z',
};

/**
 * THA-411 — افتتاحٌ مرحّل يحمل منتجاً متتبَّعاً ناقصَ الترقيم: 2 مُسجَّلة من 10.
 * هذه هي الحالة التي تُصدَم فيها الشركة عند أول بيع بنمط «إجباري».
 */
const POSTED_SERIALS = {
  ...POSTED,
  serial_items: [{
    product: 7, product_sku: 'P-007', product_name: 'إطار 255/65/15',
    quantity: 10, serials_registered: 2,
  }],
};

/** كرت المنتج الذي يهبط عليه رابط اللوحة — متتبَّع، فتبويب الأرقام موجود. */
const PRODUCT_7 = {
  id: 7, sku: 'P-007', name_ar: 'إطار 255/65/15', name_en: '', brand: '',
  is_serialized: true, is_service: false, sale_price: '420.00',
  category: null, category_name: 'إطارات', uom_primary: 'عدد',
};

const PRODUCT_7_PROFILE = {
  id: 7, name: 'إطار 255/65/15', quantity_on_hand: '10.0000',
  available_quantity: '10.0000', avg_cost: '300.0000',
  effective_sale_price: '420.00', profit_per_unit: '120.00',
};

const ACCOUNTS = [
  { id: 41, code: '1101', name: 'الصندوق', account_type: 'Asset', sub_type: null, is_active: true, parent: null },
  { id: 55, code: '2103', name: 'قروض قصيرة الأجل', account_type: 'Liability', sub_type: null, is_active: true, parent: null },
  // ممنوعة في تبويب «حسابات»: ذمم، مخزون، حساب الموازنة، وحساب مربوط بطرف.
  { id: 60, code: '1103', name: 'المدينون التجاريون', account_type: 'Asset', sub_type: 'receivable', is_active: true, parent: null },
  { id: 61, code: '1104', name: 'المخزون', account_type: 'Asset', sub_type: 'inventory', is_active: true, parent: null },
  { id: 62, code: '3300', name: 'أرصدة افتتاحية', account_type: 'Equity', sub_type: null, is_active: true, parent: null },
  { id: 88, code: '110301', name: 'عميل تجريبي', account_type: 'Asset', sub_type: null, is_active: true, parent: null },
];

const PARTNERS = [
  { id: 3, name: 'عميل تجريبي', partner_type: 'Customer', linked_account: 88 },
  { id: 4, name: 'مورّد تجريبي', partner_type: 'Supplier', linked_account: 89 },
];

const PRODUCTS = {
  count: 1,
  results: [{ id: 7, sku: 'P-007', name_ar: 'إطار 255/65/15', display_name: 'إطار 255/65/15' }],
};

const WAREHOUSES = [{ id: 2, name: 'المستودع الرئيسي' }];

type Options = { postFails?: string; serialsPending?: boolean };

const setup = async (page: Page, options: Options = {}) => {
  // الترحيل الثاني يُرجع رقم قيد مختلفاً: هكذا يفرّق المشي بين «الشاشة لم تتغيّر»
  // و«قيد جديد فعلاً» بعد إلغاء الترحيل.
  let postCount = 0;
  await page.addInitScript(() => {
    localStorage.setItem('token', 'opening-e2e-token');
    localStorage.setItem('userId', 'opening-e2e-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('lastActivityAt', String(Date.now()));
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;

    if (path.endsWith('/accounting/opening-balance/post/')) {
      if (options.postFails) {
        return route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: [options.postFails] }),
        });
      }
      postCount += 1;
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ...POSTED, journal: postCount === 1 ? 77 : 78 }),
      });
    }

    if (path.endsWith('/accounting/opening-balance/unpost/')) {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(DRAFT) });
    }

    let body: unknown = [];
    if (path.endsWith('/hr/users/opening-e2e-user/')) {
      body = {
        id: 'opening-e2e-user', name: 'Opening Tester', role: 'manager',
        email: 'opening@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الافتتاح', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = {
        role: 'manager', is_manager: true,
        permissions: ['accounting.journal.create', 'accounting.journal.post',
                      'accounting.journal.unpost', 'accounting.journal.view'],
      };
    } else if (path.endsWith('/accounting/opening-balance/lines/')) {
      body = DRAFT;
    } else if (path.endsWith('/accounting/opening-balance/')) {
      // الحالة المرحّلة تُقرأ من الخادم كما هي: اللوحة تعرض ما يقوله الخادم لا حساباً محلياً.
      body = options.serialsPending ? POSTED_SERIALS : DRAFT;
    } else if (path.endsWith('/inventory/products/7/profile/')) {
      body = PRODUCT_7_PROFILE;
    } else if (path.endsWith('/inventory/products/7/serials/')) {
      body = [];
    } else if (path.endsWith('/inventory/products/7/stock-ledger/')) {
      body = { results: [], count: 0 };
    } else if (path.endsWith('/inventory/products/7/invoices/')) {
      body = [];
    } else if (path.endsWith('/inventory/products/7/')) {
      body = PRODUCT_7;
    } else if (path.endsWith('/accounting/accounts/')) {
      body = ACCOUNTS;
    } else if (path.endsWith('/partners/lookup/')) {
      body = PARTNERS;
    } else if (path.endsWith('/inventory/products/')) {
      body = PRODUCTS;
    } else if (path.endsWith('/inventory/warehouses/')) {
      body = WAREHOUSES;
    } else if (path.endsWith('/accounting/currencies/')) {
      body = [{ CurrencyID: 1, Code: 'ILS', IsBaseCurrency: true }];
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
};

test('الشاشة تُفتح من الشريط الجانبي وتعرض التبويبات الثلاثة وتاريخ القيد وصافي حقوق الملكية', async ({ page }) => {
  await setup(page);
  // شاشة محاسبية هادئة كنقطة انطلاق: لوحة التحكم تعيد الرسم دورياً فينفصل زرّ
  // الشريط الجانبي من الـDOM أثناء النقر (تقلّب في الاختبار لا في الشاشة).
  await page.goto('/accounting/fiscal-periods');
  await expect(page.getByText('الفترات المالية').first()).toBeVisible({ timeout: 20_000 });

  // من التنقّل نفسه لا بالرابط المباشر: فخّ JSX هو أن الشاشة مسجَّلة ولا تُرسم.
  // مجموعة «المحاسبة» مفتوحة أصلاً على أي شاشة محاسبية (`Sidebar` يفتحها بـ
  // `activeView`)، فالنقر عليها هنا كان يطويها.
  const navLink = page.getByRole('button', { name: 'الأرصدة الافتتاحية' }).first();
  await expect(navLink).toBeVisible({ timeout: 20_000 });
  await navLink.click();
  await expect(page).toHaveURL(/\/accounting\/opening-balances$/, { timeout: 20_000 });

  await expect(page.getByText('تاريخ بدء التشغيل')).toBeVisible({ timeout: 20_000 });
  // التاريخ مشتقّ في الواجهة كما في الخادم: 2026-03-01 − 1 = 2026-02-28.
  await expect(page.getByText('28/02/2026')).toBeVisible();
  await expect(page.getByText('صافي حقوق الملكية الافتتاحية')).toBeVisible();
  await expect(page.getByText('6,000', { exact: false }).first()).toBeVisible();

  await expect(page.getByRole('tab', { name: /حسابات \(2\)/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /أطراف \(2\)/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /مخزون \(1\)/ })).toBeVisible();
  // بنود الحسابات وصلت فعلاً: الحساب في منتقي الشجرة، ومبلغه في خانته.
  await expect(page.getByRole('button', { name: '1101 — الصندوق' })).toBeVisible();
  await expect(page.getByRole('button', { name: '2103 — قروض قصيرة الأجل' })).toBeVisible();
  const cashRow = page.getByRole('row').filter({ hasText: '1101 — الصندوق' });
  await expect(cashRow.getByRole('spinbutton').first()).toHaveValue('5000.00');
  await page.screenshot({ path: 'e2e/parity-shots/t119-3-1-accounts.png', fullPage: true });

  // تبويب الأطراف: شارة المرحَّل مع رقم قيده وزرّ العكس، وغير المرحَّل بزر الحفظ.
  await page.getByRole('tab', { name: /أطراف/ }).click();
  await expect(page.getByText('مرحّل #9')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('button', { name: /إلغاء الترحيل/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /حفظ وترحيل/ })).toBeVisible();
  await page.screenshot({ path: 'e2e/parity-shots/t119-3-2-partners.png', fullPage: true });

  // تبويب المخزون: المنتج والمستودع والقيمة المحسوبة (10 × 300).
  await page.getByRole('tab', { name: /مخزون/ }).click();
  await expect(page.getByText('إطار 255/65/15')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('قيمة بضاعة أول المدة')).toBeVisible();
  await expect(page.getByText('3,000', { exact: false }).first()).toBeVisible();
  await page.screenshot({ path: 'e2e/parity-shots/t119-3-3-stock.png', fullPage: true });
});

test('الترحيل خلف تأكيد يذكر تاريخ القيد وصافي حقوق الملكية، ثم تصير الشاشة مرحّلة', async ({ page }) => {
  await setup(page);
  await page.goto('/accounting/opening-balances');
  await expect(page.getByText('صافي حقوق الملكية الافتتاحية')).toBeVisible({ timeout: 20_000 });

  await page.getByRole('button', { name: /ترحيل القيد الافتتاحي/ }).click();
  // لا `window.confirm` — حوار الموقع الموحّد، ويقول ما سيحدث قبل حدوثه.
  await expect(page.getByText('تاريخ القيد:')).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/t119-3-4-post-confirm.png', fullPage: true });
  await page.getByRole('button', { name: 'رحّل', exact: true }).click();

  await expect(page.getByText('مرحّل — قيد #77')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('button', { name: /إلغاء الترحيل/ })).toBeVisible();
  await page.screenshot({ path: 'e2e/parity-shots/t119-3-5-posted.png', fullPage: true });
});

test('فترة مالية مغلقة عند تاريخ القيد ⇒ رسالة الخادم مع زرّ يفتح الفترات المالية', async ({ page }) => {
  await setup(page, {
    postFails: 'الفترة المالية «2026-02» مغلقة. افتحها من إدارة الفترات المالية قبل ترحيل قيود بتاريخ 2026-02-28.',
  });
  await page.goto('/accounting/opening-balances');
  await expect(page.getByText('صافي حقوق الملكية الافتتاحية')).toBeVisible({ timeout: 20_000 });

  await page.getByRole('button', { name: /ترحيل القيد الافتتاحي/ }).click();
  await page.getByRole('button', { name: 'رحّل', exact: true }).click();

  await expect(page.getByText(/مغلقة/)).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/t119-3-6-period-error.png', fullPage: true });
  await page.getByRole('button', { name: /افتح الفترات المالية/ }).click();
  await expect(page).toHaveURL(/\/accounting\/fiscal-periods$/, { timeout: 20_000 });
});

/**
 * THA-402 (T119-4) — الرِجل الأخيرة من المشي: بعد الترحيل يبقى للمستخدم مخرج.
 * إلغاء الترحيل يعيد الشاشة مسودةً **قابلة للتحرير**، وإعادة الترحيل تُنتج قيداً
 * جديداً لا القديم — وهذا ما يمنع الحالةَ التي لا يخرج منها المستخدم.
 */
test('إلغاء الترحيل يعيد الشاشة مسودة قابلة للتحرير، وإعادة الترحيل تُنتج قيداً جديداً', async ({ page }) => {
  await setup(page);
  await page.goto('/accounting/opening-balances');
  await expect(page.getByText('صافي حقوق الملكية الافتتاحية')).toBeVisible({ timeout: 20_000 });

  const cashDebit = page.getByRole('row')
    .filter({ hasText: '1101 — الصندوق' })
    .getByRole('spinbutton').first();

  await page.getByRole('button', { name: /ترحيل القيد الافتتاحي/ }).click();
  await page.getByRole('button', { name: 'رحّل', exact: true }).click();
  await expect(page.getByText('مرحّل — قيد #77')).toBeVisible({ timeout: 20_000 });
  // المرحَّل مقفل: لا يُحرَّر رقمٌ صار في الدفاتر.
  await expect(cashDebit).toBeDisabled();

  await page.getByRole('button', { name: 'إلغاء الترحيل', exact: true }).first().click();
  await expect(page.getByText(/سيُحذف القيد الافتتاحي/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'ألغِ الترحيل', exact: true }).click();

  await expect(page.getByRole('button', { name: /ترحيل القيد الافتتاحي/ })).toBeVisible({ timeout: 20_000 });
  await expect(cashDebit).toBeEnabled();
  await page.screenshot({ path: 'e2e/parity-shots/t119-4-1-unposted.png', fullPage: true });

  await page.getByRole('button', { name: /ترحيل القيد الافتتاحي/ }).click();
  await page.getByRole('button', { name: 'رحّل', exact: true }).click();
  // قيد جديد (#78) لا القديم (#77) — الإعادة ترحيلٌ فعليّ لا إحياءٌ للمحذوف.
  await expect(page.getByText('مرحّل — قيد #78')).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: 'e2e/parity-shots/t119-4-2-reposted.png', fullPage: true });
});

/**
 * THA-411 (T119-5) — بضاعة الافتتاح المتتبَّعة تسلسلياً: الافتتاح يُدخل الكمية ولا
 * يُنشئ رقماً تسلسلياً واحداً، فالبيع بنمط «إجباري» يرفضها. اللوحة تقول المُسجَّل
 * والمطلوب، ورابطها يهبط على تبويب الأرقام التسلسلية في كرت المنتج — لا على أول
 * تبويب فيه (التبويب يُلحق متأخراً بعد وصول `is_serialized`، وهو الفخّ نفسه).
 */
test('الافتتاح المرحّل يعرض المسجَّل/المطلوب للمنتجات المتتبَّعة ورابطه يفتح تبويب الأرقام التسلسلية', async ({ page }) => {
  await setup(page, { serialsPending: true });
  await page.goto('/accounting/opening-balances');
  await expect(page.getByText('مرحّل — قيد #77')).toBeVisible({ timeout: 20_000 });

  await page.getByRole('tab', { name: /مخزون/ }).click();
  await expect(page.getByText('منتجات تتتبّع أرقاماً تسلسلية في بضاعة أول المدة')).toBeVisible({ timeout: 20_000 });

  // الصفّ يقول الرقمين وما ينقص بينهما — لا «خطأ» بلا مقدار.
  const row = page.getByRole('row').filter({ hasText: 'إطار 255/65/15 — P-007' });
  await expect(row.getByRole('cell', { name: '2', exact: true })).toBeVisible();
  await expect(row.getByRole('cell', { name: '10', exact: true })).toBeVisible();
  await expect(row.getByText('ناقص 8')).toBeVisible();
  await page.screenshot({ path: 'e2e/parity-shots/t119-5-1-serial-gap.png', fullPage: true });

  await row.getByRole('button', { name: /رقّم وحدات هذا المنتج/ }).click();
  await expect(page).toHaveURL(/\/products\/7\?tab=serials$/, { timeout: 20_000 });

  // الهبوط على التبويب المقصود فعلاً، لا مجرّد وصول الرابط.
  const serialsTab = page.getByRole('tab', { name: 'الأرقام التسلسلية' });
  await expect(serialsTab).toBeVisible({ timeout: 20_000 });
  await expect(serialsTab).toHaveAttribute('aria-selected', 'true');
  // ومخرج الترقيم حاضر: 10 في المخزن بلا وحدة مُرقَّمة واحدة.
  await expect(page.getByRole('button', { name: /تسجيل أرقام لمخزون قائم/ })).toBeVisible();
  await page.screenshot({ path: 'e2e/parity-shots/t119-5-2-product-serials-tab.png', fullPage: true });
});
