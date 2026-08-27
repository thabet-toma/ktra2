import { test, expect, type Page } from '@playwright/test';

/**
 * T-SCAN — «ما الذي في يدي؟»: حقلٌ واحد يقبل كل الأشكال، وبطاقةٌ تُفتح بنداءٍ واحد.
 *
 * صحّةُ الأرقام نفسها يثبتها `core/tests/test_scan_lookup.py`؛ ما يُثبَت هنا
 * سلوكُ الشاشة وحده:
 *   1. زرّ البحث في الترويسة يفتح **حقلاً** — لا قائمة روابط كما كان.
 *   2. مسح IMEI (نُحاكيه بالكتابة، وهو نفس ما تفعله قراءةُ الكاميرا) يعرض
 *      العميل وتاريخ البيع وحالة الكفالة في اللوحة نفسها بلا نداءٍ ثانٍ.
 *   3. رقمٌ مجهول يقول «غير مسجَّل» ويعرض مخرجاً — لا شاشةً فارغة.
 *   4. **حارس HTTPS**: على اتصالٍ غير آمن يُعطَّل زرّ الكاميرا ويُكتب السبب
 *      قبل الضغط. هذا هو المكافئ القابل للأتمتة لبند «يُتحقّق منه ويُظهر رسالة
 *      صريحة بدل فشل صامت» — الكاميرا الحقيقية تلزمها يدُ إنسانٍ وجهاز.
 */

const IMEI = '356938035643809';
const UNKNOWN = '490154203237518';

const SCOPE = { units: true, products: true, devices: true, warranty: true, orders: true };

const SOLD_UNIT = {
  term: IMEI,
  kind: 'imei',
  unregistered: false,
  scope: SCOPE,
  matches: [
    {
      type: 'unit',
      id: 12,
      serial: IMEI,
      status: 'sold',
      status_display: 'مُباع',
      product: 3,
      product_name: 'هاتف ذكي 128 جيجا',
      product_sku: 'PH-001',
      purchase_invoice: 41,
      purchase_invoice_number: 'P-0041',
      supplier_name: 'مورد الأجهزة',
      purchase_unit_price: '1000.0000',
      purchase_date: '2026-06-11',
      sales_invoice: 77,
      sales_invoice_number: 'S-0077',
      customer: 9,
      customer_name: 'زبون الجهاز',
      customer_phone: '0599111222',
      sold_at: '2026-06-15',
      created_at: '2026-06-11T09:00:00',
      warranty: {
        covered: true,
        supplier_covered: true,
        cards: [{
          id: 5, serial: IMEI, device_name: 'هاتف ذكي', start_date: '2026-06-15',
          end_date: '2027-06-15', duration_months: 12, status: 'active',
          days_remaining: 298, customer_name: 'زبون الجهاز',
          supplier_warranty_end_date: '2028-06-11', supplier_warranty_active: true,
        }],
      },
      service_orders: [{
        id: 4, order_number: 'SV-0001', order_date: '2026-07-01',
        status: 'ready', status_display: 'جاهز للتسليم', complaint: 'الشاشة لا تستجيب',
      }],
    },
  ],
};

const NOT_FOUND = {
  term: UNKNOWN, kind: 'imei', matches: [], unregistered: true, scope: SCOPE,
};

/** يُرجع مسارات `/api/` التي خرجت — لإثبات أن البطاقة تصل بنداءٍ **واحد**. */
const setup = async (page: Page) => {
  const calls: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'scan-e2e-token');
    localStorage.setItem('userId', 'scan-e2e-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('lastActivityAt', String(Date.now()));
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    calls.push(path + (path === '/api/scan/' ? `?q=${url.searchParams.get('q')}` : ''));

    let body: unknown = [];
    if (path.endsWith('/hr/users/scan-e2e-user/')) {
      body = {
        id: 'scan-e2e-user', name: 'Scan Tester', role: 'manager',
        email: 'scan@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'متجر الهواتف', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = { role: 'manager', is_manager: true, permissions: [] };
    } else if (path === '/api/scan/') {
      body = url.searchParams.get('q') === IMEI ? SOLD_UNIT : NOT_FOUND;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return calls;
};

const openPanel = async (page: Page) => {
  await page.goto('/items');
  const button = page.getByTestId('global-search-button');
  await expect(button).toBeVisible({ timeout: 20_000 });
  await button.click();
  await expect(page.getByTestId('scan-input')).toBeVisible({ timeout: 20_000 });
};

test('زرّ البحث يفتح حقلاً واحداً يقبل كل الأشكال — لا قائمة روابط', async ({ page }) => {
  await setup(page);
  await openPanel(page);

  // العقد الظاهر للمستخدم: الحقل يعلن ما يقبله، فلا يسأل نفسه «أي نوع هذا؟».
  await expect(page.getByTestId('scan-input')).toHaveAttribute(
    'placeholder', /باركود.*تسلسلي.*IMEI.*رمز المنتج/,
  );
  // والروابط السريعة لم تُفقَد — صارت حالةَ الفراغ داخل اللوحة.
  await expect(
    page.getByTestId('scan-panel').getByRole('button', { name: 'فواتير المبيعات' }),
  ).toBeVisible();
});

test('مسح IMEI جهاز مباع يفتح بطاقته: العميل وتاريخ البيع وحالة الكفالة', async ({ page }) => {
  const calls = await setup(page);
  await openPanel(page);

  await page.getByTestId('scan-input').fill(IMEI);

  // ① العميل — بالاسم وبالهاتف.
  await expect(page.getByText('زبون الجهاز')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('0599111222')).toBeVisible();
  // ② تاريخ البيع، وفاتورته رابطاً يُفتح في تبويب.
  await expect(page.getByRole('button', { name: 'S-0077' })).toBeVisible();
  // ③ حالة الكفالة.
  await expect(page.getByTestId('scan-warranty')).toContainText('الكفالة سارية');
  // ورحلة القطعة: من أين جاءت.
  await expect(page.getByText('مورد الأجهزة')).toBeVisible();
  // وسجلّ صيانتها السابق — «مسح الرقم يستدعي سجلّ القطعة كاملاً».
  await expect(page.getByText('الشاشة لا تستجيب')).toBeVisible();

  // القياس لا الثقة: البطاقة كلّها وصلت بنداءٍ **واحد** على `/api/scan/`.
  const scans = calls.filter((c) => c.startsWith('/api/scan/?q='));
  expect(scans).toEqual([`/api/scan/?q=${IMEI}`]);
});

test('رقم غير معروف يقول «غير مسجَّل» ويعرض مخرجاً — لا شاشة فارغة', async ({ page }) => {
  await setup(page);
  await openPanel(page);

  await page.getByTestId('scan-input').fill(UNKNOWN);

  const banner = page.getByTestId('scan-unregistered');
  await expect(banner).toBeVisible({ timeout: 20_000 });
  await expect(banner).toContainText('غير مسجَّل');
  await expect(banner.getByRole('button', { name: 'سجّله جهازاً حسّاساً' })).toBeVisible();
});

test('على اتصال غير آمن يُعطَّل زرّ الكاميرا ويُكتب السبب قبل الضغط', async ({ page }) => {
  await setup(page);
  // `isSecureContext` تُحسب من الأصل ولا تُضبط، فنُغطّيها قبل إقلاع التطبيق —
  // وهو ما يراه المستخدم فعلاً حين يفتح النظام على `http://` عبر شبكة المحل.
  await page.addInitScript(() => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
  });
  await openPanel(page);

  await expect(page.getByTestId('scan-camera')).toBeDisabled();
  await expect(page.getByText(/الكاميرا تتطلّب HTTPS/)).toBeVisible();
  // والمخرج مذكور: الحقل نفسه يعمل على أي اتصال.
  await expect(page.getByText(/الكتابة والماسح اليدوي يعملان/)).toBeVisible();
});
