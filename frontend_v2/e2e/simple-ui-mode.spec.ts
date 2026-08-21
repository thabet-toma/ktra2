import { test, expect } from '@playwright/test';
import { SIMPLE_HINTS } from '../constants/simpleHints';

/**
 * THA-110 — «الواجهة السهلة»: قناع عرضٍ فوق نفس القائمة، لا قائمة ثانية.
 *
 * ثلاثة وعود يحرسها هذا الاختبار، وكلها غير مرئية حتى تنكسر:
 *  1. الوضع السهل يعرض الأساسيات الثمانية **مسطّحة** بلا مجموعات، ومرشّحة
 *     بالصلاحيات كما هي — الوضع يُرتّب ولا يمنح.
 *  2. زر العودة **ظاهر في الوضعين** ويعمل بالاتجاهين، والاختيار يعيش بعد
 *     إعادة تحميل الصفحة.
 *  3. **الوضع المتقدم لا يتغيّر بشيء**: ترتيب القائمة بعد جولة ذهاب وإياب
 *     مطابقٌ حرفياً لما كان قبلها — لا بندٌ تحرّك ولا بندٌ اختفى.
 *
 * الشبكة موقوفة كما في `accountant-mode.spec.ts` — لا خادم ولا قاعدة بيانات:
 * موضوع الفحص هو الشريط الجانبي وحده.
 */

const SIMPLE_ITEMS = [
  'الرئيسية',
  'فواتير المبيعات',
  'فواتير الشراء',
  'أرصدة المخزون',
  'الأصناف',
  'الموردين',
  'العملاء',
  'الإعدادات',
];

/**
 * خادمٌ موقوف لكنه **يتذكّر**: `set-ui-mode/` يخزّن القيمة و`permissions/me/`
 * يعيدها. الخادم مصدر الحقيقة في التطبيق الحقيقي (`UserCompanyMembership.ui_mode`)،
 * فمحاكاته بردٍّ ثابت كانت ستُثبت العكس تماماً — أن الوضع لا يعيش.
 */
const asManager = async (page: import('@playwright/test').Page) => {
  const server = { uiMode: 'advanced' as string, writes: [] as string[] };
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui-mode-token');
    localStorage.setItem('userId', 'ui-mode-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    if (url.pathname.endsWith('/hr/users/ui-mode-user/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'ui-mode-user',
          name: 'UI Mode Tester',
          role: 'manager',
          email: 'ui-mode@example.test',
          employmentStatus: 'active',
          isApproved: true,
          isEmailVerified: true,
        }),
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{
          id: 1,
          tenant: {
            TenantID: 1,
            CompanyName: 'شركة الاختبار',
            SubscriptionPlan: 'basic',
            Status: 'active',
            CreatedAt: '2026-01-01T00:00:00Z',
            import_enabled: false,
          },
          role: 'manager',
          is_default: true,
          created_at: '2026-01-01T00:00:00Z',
          can_access_import: false,
        }]),
      });
    }
    if (url.pathname.endsWith('/tenants/companies/set-ui-mode/')) {
      const sent = JSON.parse(route.request().postData() || '{}');
      server.uiMode = sent.ui_mode;
      server.writes.push(sent.ui_mode);
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ui_mode: server.uiMode }),
      });
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      // الخادم مصدر الحقيقة، ويبدأ الجميع على «متقدم» — لا تجربة تتبدّل صامتاً.
      // الصلاحيات هنا تغطي البنود الثمانية كلها كي يُفحَص القناع لا الصلاحية.
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          role: 'manager',
          is_manager: true,
          permissions: [
            'sales.invoice.view',
            'sales.customer.view',
            'purchase.invoice.view',
            'purchase.supplier.view',
            'inventory.item.view',
            'accounting.account.manage',
          ],
          modules: {},
          ui_mode: server.uiMode,
        }),
      });
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' });
  });
  return server;
};

const desktopSidebar = (page: import('@playwright/test').Page) =>
  page.locator('aside.aseel-sidebar.hidden');

/** أبناء `nav` المباشرون — بنود القائمة المتقدمة المفردة (لا مجموعة لها). */
const flatItems = async (page: import('@playwright/test').Page) =>
  desktopSidebar(page)
    .locator('nav > button[title]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('title')));

/**
 * بنود الوضع السهل. صار لكل بندٍ غلافٌ (T5) لأن «؟» شقيقةُ الزرّ لا ابنته —
 * زرٌّ داخل زرٍّ لا يصحّ. الغلاف موسوم `data-simple-nav` كي يبقى الفحص على
 * البنود نفسها لا على شكل الشجرة.
 */
const simpleItems = async (page: import('@playwright/test').Page) =>
  desktopSidebar(page)
    .locator('nav > div[data-simple-nav] > button[title]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('title')));

/** بصمة القائمة المتقدمة كاملةً: المجموعات وأبناء `nav` المباشرون بترتيبهم. */
const advancedFingerprint = async (page: import('@playwright/test').Page) => ({
  groups: await desktopSidebar(page)
    .locator('nav > div > button[title]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('title'))),
  items: await flatItems(page),
});

const modeToggle = (page: import('@playwright/test').Page, name: string) =>
  desktopSidebar(page).getByRole('button', { name, exact: true });

test('«الواجهة السهلة» تُقلّم القائمة، تعيش بعد إعادة التحميل، وتعود بضغطة بلا أثر', async ({ page }) => {
  const server = await asManager(page);
  // شاشة ساكنة عمداً: المطلوب فحصه هو الشريط الجانبي وحده.
  await page.goto('/about-us');

  // 1) الافتراضي متقدم: الزر يدعو للسهل، ولا شارة، و«وضع المحاسب» في مكانه.
  const toSimple = modeToggle(page, 'الواجهة السهلة');
  await expect(toSimple).toBeVisible({ timeout: 15000 });
  await expect(toSimple).toHaveAttribute('aria-pressed', 'false');
  await expect(desktopSidebar(page).getByText('الوضع السهل')).toHaveCount(0);
  await expect(desktopSidebar(page).getByRole('button', { name: 'وضع المحاسب' })).toBeVisible();
  const before = await advancedFingerprint(page);
  expect(before.groups).toContain('المبيعات');
  expect(before.groups).toContain('المحاسبة');

  // 2) التبديل للسهل: ثمانية بنود مسطّحة، بلا مجموعة واحدة، والشارة تظهر.
  await toSimple.click();
  const toAdvanced = modeToggle(page, 'الواجهة المتقدمة');
  await expect(toAdvanced).toBeVisible();
  await expect(toAdvanced).toHaveAttribute('aria-pressed', 'true');
  await expect(desktopSidebar(page).getByText('الوضع السهل')).toBeVisible();
  expect(await simpleItems(page)).toEqual(SIMPLE_ITEMS);
  // ولا مجموعةً واحدة: كل ما في القائمة أغلفةُ البنود المسطّحة.
  await expect(desktopSidebar(page).locator('nav > div:not([data-simple-nav]) > button[title]')).toHaveCount(0);
  // «وضع المحاسب» يختفي — ترتيبُ قائمةٍ لا وجود لها.
  await expect(desktopSidebar(page).getByRole('button', { name: 'وضع المحاسب' })).toHaveCount(0);

  // 3) الاختيار يعيش بعد إعادة التحميل (cache الشركة قبل ردّ الخادم).
  await page.reload();
  const afterReload = modeToggle(page, 'الواجهة المتقدمة');
  await expect(afterReload).toBeVisible({ timeout: 15000 });
  await expect(afterReload).toHaveAttribute('aria-pressed', 'true');
  expect(await simpleItems(page)).toEqual(SIMPLE_ITEMS);

  // 4) العودة بضغطة واحدة — والقائمة المتقدمة كما كانت حرفياً، لا بندٌ تحرّك.
  await afterReload.click();
  const backToSimple = modeToggle(page, 'الواجهة السهلة');
  await expect(backToSimple).toBeVisible();
  await expect(backToSimple).toHaveAttribute('aria-pressed', 'false');
  expect(await advancedFingerprint(page)).toEqual(before);

  // 5) وكل تبديلٍ وصل الخادم فعلاً — لا وضعٌ يعيش في هذا المتصفح وحده.
  expect(server.writes).toEqual(['simple', 'advanced']);
});

/**
 * قناع محرّر فاتورة البيع (T4). المشي نفسه في الاتجاهين على **نفس** الشاشة:
 * ما يختفي في السهل يظهر في المتقدّم كما كان — فالوضع المتقدّم يُفحَص هنا لا
 * يُفترَض. أمّا أن الإخفاء لا يغيّر قيداً فيُسمَّر خادمياً في
 * `sales/tests/test_simple_mode_journal_parity.py` — المتصفح لا يُثبت قيداً.
 */
const withInvoiceScreen = async (page: import('@playwright/test').Page, uiMode: string) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui-mode-token');
    localStorage.setItem('userId', 'ui-mode-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/ui-mode-user/')) {
      return json({
        id: 'ui-mode-user', name: 'UI Mode Tester', role: 'manager',
        email: 'ui-mode@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاختبار', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: uiMode,
        permissions: ['sales.invoice.view', 'sales.invoice.create', 'sales.customer.view'],
      });
    }
    if (url.pathname.endsWith('/accounting/currencies/')) {
      return json([{ CurrencyID: 1, Code: 'ILS', Name: 'شيكل' }]);
    }
    if (url.pathname.endsWith('/accounting/accounts/')) {
      return json([
        { id: 10, code: '1101', name: 'الصندوق الرئيسي', account_type: 'Asset' },
        { id: 40, code: '4101', name: 'إيراد المبيعات', account_type: 'Revenue' },
      ]);
    }
    if (url.pathname.endsWith('/sales/settings/current/')) {
      // كل الافتراضيات محلولة ⇒ لا يفرض شيءٌ ظهورَه رغم القناع.
      // وعميلٌ افتراضي **مقصود**: «رصيد العميل» صفٌّ لا وجود له بلا عميل
      // مختار (انظر التعليق على ALWAYS_VISIBLE)، وشاشةٌ بلا عميل كانت تُفحَص
      // بينما نصفُ ما تدّعي حراستَه غائبٌ لا مخفيّ.
      return json({
        default_customer: 8, default_currency: 1, default_payment_type: 'cash',
        default_cash_account: 10, default_revenue_account_product: 40,
        stock_on_post_default: true, default_vat_rate: null,
        prices_include_tax: false, auto_post_invoices: false,
        show_journal_preview: true,
      });
    }
    if (url.pathname.endsWith('/partners/lookup/')) {
      return json([{ id: 8, name: 'عميل الوضع السهل', partner_type: 'Customer' }]);
    }
    // مصدر «رصيد العميل» في لوحة المجاميع — بلا ردٍّ منه يبقى `creditHint`
    // فارغاً فلا يُرسَم الصفّ أصلاً، في الوضعين معاً.
    if (url.pathname.endsWith('/sales/invoices/credit-preview/')) {
      return json({
        credit_limit: null, open_balance: '250.00', proposed_total: '0.00',
        projected_balance: '250.00', would_exceed: false,
      });
    }
    if (url.pathname.endsWith('/sales/invoices/')) {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    return json([]);
  });
  // «فاتورة جديدة» تفتح تبويباً جديداً على هذا المسار — نقصده مباشرةً.
  await page.goto('/sales/invoices/new');
  // البحث/الباركود لا يظهر إلا في رأس المحرّر المفتوح للتحرير — لا في القائمة
  // ولا في وضع العرض المستندي، فهو الدليل أن الشاشة المقصودة هي المفتوحة.
  await expect(page.getByText('بحث سريع / باركود (F6)', { exact: true }))
    .toBeVisible({ timeout: 15000 });
  /* THA-131: الرأس يُرسَم قبل وصول `sales/settings/current/`، وحقولٌ عدّة تتبع
     الافتراضيات (العملة · نوع الدفع · الاستحقاق). فمَن يلتقط الشاشة عند ظهور
     الباركود وحده يلتقطها أحياناً **قبل** تطبيق الافتراضيات، فيرى «عملة»
     و«استحقاق» ثم يفشل بلا عطلٍ في المنتج — تذبذبٌ قديم أخفاه الحظّ. الشرط
     المفقود يُقال هنا صراحةً: خانة «نقدي» مؤشَّرة = الافتراضيات وصلت وطُبِّقت. */
  await expect(page.getByRole('checkbox', { name: 'نقدي' })).toBeChecked();
};

/* THA-131: «استحقاق» خرج من هذه القائمة لأنه لم يعد حقلاً متقدّماً — صار يتبع
   نوع الدفع في الوضعين معاً (آجلة ⇒ يظهر، نقدية ⇒ يحلّ الصندوق مكانه). يحرسه
   اختبارُ المعيار أدناه لا قناعُ الوضع السهل. */
const ADVANCED_ONLY = [
  'عملة',
  'شامل الضريبة',
  'الحسابات / مركز التكلفة',
  'بيانات أخرى',
];

/* THA-128: «أرصدة العميل» خرج من هذه القائمة — كان تبويباً يعيد رقمين تعرضهما
   لوحة المجاميع أصلاً، فحُذف التبويب وبقي «رصيد العميل» في اللوحة حيث يُقرأ.

   وهنا كان الخلل: بديلُه ليس نظيرَه. «أرصدة العميل» كان **عنوان تبويب** يُرسَم
   دائماً، أمّا «رصيد العميل» فصفٌّ في لوحة المجاميع مشروطٌ بـ`creditHint` —
   ولا يُجلَب هذا إلّا بعد اختيار عميل. فبقي الاختبار أحمر منذ THA-128 لأن
   الشاشة لا عميل فيها، لا لأن الصفّ مخفيّ: القناع لا يمسّه في الوضعين.
   العلاج اختيارُ عميل في الشاشة المفحوصة (`default_customer` + ردّ
   `credit-preview/`) لا حذفُ السطر — الحذف كان سيُطفئ حراسةَ وعدٍ قائم.

   ملاحظة تمييز: THA-132 أزال من لوحة المجاميع سطرَي «رصيد العميل قبل احتساب
   المتبقي…» و«…الحالي بعد احتسابه» لأنهما كانا رقماً كاذباً، وهما نصّان آخران
   لا يطابقهما `exact: 'رصيد العميل'` أصلاً — فلا صلة لتلك الإزالة بهذا الفشل. */
const ALWAYS_VISIBLE = ['العميل', 'نقدي', 'تاريخ', 'ملاحظات', 'رصيد العميل'];

test('محرّر الفاتورة في الوضع المتقدّم يعرض كل ما كان يعرضه', async ({ page }) => {
  await withInvoiceScreen(page, 'advanced');
  for (const label of [...ALWAYS_VISIBLE, ...ADVANCED_ONLY]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
});

test('الوضع السهل يطوي متقدّم المحرّر ويُبقي جوهر الفاتورة', async ({ page }) => {
  await withInvoiceScreen(page, 'simple');
  for (const label of ALWAYS_VISIBLE) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  for (const label of ADVANCED_ONLY) {
    await expect(page.getByText(label, { exact: true })).toHaveCount(0);
  }
});

/**
 * T5 — طبقة «؟». ثلاثة وعود يحرسها ما يلي:
 *  1. «؟» بجانب كل بندٍ وحقلٍ رئيسي **في الوضع السهل وحده** — صفرٌ منها في
 *     المتقدّم (ضجيجٌ على المحترف).
 *  2. النصّ المعروض هو نصّ `constants/simpleHints.ts` حرفاً بحرف — لا نسخةَ
 *     ثانية تسكن مكوّناً وتفترق عنه.
 *  3. الأيقونة تشرح ولا تفعل: ضغطتُها لا تفتح شاشةً ولا تُبدّل خانةً.
 */
const hintKeys = async (page: import('@playwright/test').Page, scope: string) =>
  page.locator(`${scope} [data-field-hint]`)
    .evaluateAll((els) => els.map((el) => el.getAttribute('data-field-hint')).sort());

test('«؟» تشرح بنود القائمة في الوضع السهل، وتغيب تماماً عن المتقدّم', async ({ page }) => {
  await asManager(page);
  await page.goto('/about-us');
  await expect(modeToggle(page, 'الواجهة السهلة')).toBeVisible({ timeout: 15000 });

  // 1) الوضع المتقدّم: لا أيقونة شرحٍ واحدة في الشاشة كلها.
  await expect(page.locator('[data-field-hint]')).toHaveCount(0);

  // 2) الوضع السهل: لكل بندٍ من الثمانية «؟» خاصته.
  await modeToggle(page, 'الواجهة السهلة').click();
  expect(await hintKeys(page, 'aside.aseel-sidebar.hidden')).toEqual([
    'nav.dashboard',
    'nav.items-management',
    'nav.purchase-invoices',
    'nav.sales-customers',
    'nav.sales-invoices',
    'nav.settings',
    'nav.stock-levels',
    'nav.supplier-management',
  ]);

  // 3) النصّ من ملف النصوص حرفياً — والضغطة تشرح ولا تنقل الشاشة.
  const urlBefore = page.url();
  await desktopSidebar(page).locator('[data-field-hint="nav.settings"]').click();
  const bubble = desktopSidebar(page).getByRole('tooltip');
  await expect(bubble).toBeVisible();
  for (const line of SIMPLE_HINTS['nav.settings'].lines) {
    await expect(bubble).toContainText(line);
  }
  expect(page.url()).toBe(urlBefore);

  // 4) Escape يغلق — ومَن فتح شرحاً يجد مخرجه بلوحة المفاتيح وحدها.
  await page.keyboard.press('Escape');
  await expect(desktopSidebar(page).getByRole('tooltip')).toHaveCount(0);

  // 5) العودة للمتقدّم تمحوها كلها.
  await modeToggle(page, 'الواجهة المتقدمة').click();
  await expect(page.locator('[data-field-hint]')).toHaveCount(0);
});

test('«؟» تشرح حقول الفاتورة الظاهرة في السهل — ولا تشرح ما أخفاه القناع', async ({ page }) => {
  await withInvoiceScreen(page, 'simple');
  // الحقول الظاهرة وحدها: لا «؟» للعملة ولا للاستحقاق — العملة افتراضُها محلول،
  // والفاتورة نقدية فالاستحقاق لا محلّ له. والصندوق حقلٌ متقدّم يطويه القناع.
  // التلميح يتبع ما يُعرَض فعلاً لا يعانده.
  expect(await hintKeys(page, '#sales-invoice-print')).toEqual([
    'invoice.barcode',
    'invoice.customer',
    'invoice.date',
    'invoice.lines',
    'invoice.notes',
    'invoice.paid',
    'invoice.total',
  ]);

  // «نقدي» أدقّ الحالات: «؟» تسكن بجوار خانة اختيار، فضغطُها يجب أن يشرح
  // لا أن يقلب نوع الفاتورة من نقدية إلى آجلة.
  const paidBox = page.locator('#sales-invoice-print input[type="checkbox"]').first();
  const wasChecked = await paidBox.isChecked();
  await page.locator('[data-field-hint="invoice.paid"]').click();
  await expect(page.locator('#sales-invoice-print').getByRole('tooltip'))
    .toContainText(SIMPLE_HINTS['invoice.paid'].lines[0]);
  expect(await paidBox.isChecked()).toBe(wasChecked);
});

test('محرّر الفاتورة في الوضع المتقدّم بلا أيقونة شرحٍ واحدة', async ({ page }) => {
  await withInvoiceScreen(page, 'advanced');
  await expect(page.locator('[data-field-hint]')).toHaveCount(0);
});

test('الوضع السهل لا يمنح ما منعته الصلاحية', async ({ page }) => {
  await asManager(page);
  // نفس المستخدم بلا صلاحيتَي الشراء والمخزون: بنوده أقل من ثمانية.
  await page.route('**/permissions/me/', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        role: 'manager',
        is_manager: true,
        permissions: ['sales.invoice.view', 'sales.customer.view'],
        modules: {},
        ui_mode: 'simple',
      }),
    });
  });
  await page.goto('/about-us');

  await expect(modeToggle(page, 'الواجهة المتقدمة')).toBeVisible({ timeout: 15000 });
  expect(await simpleItems(page)).toEqual([
    'الرئيسية',
    'فواتير المبيعات',
    'العملاء',
    'الإعدادات',
  ]);
});
