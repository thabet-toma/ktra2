/**
 * T-QUICKPARTY — حقل العميل في فاتورة المبيعات: الكتابة تُنشئ.
 *
 * معيار المالك حرفياً: «كتابة اسم غير موجود ثم اختيار «إضافة» تُنشئ العميل
 * وتربطه بالفاتورة بلا خطوة يدوية إضافية». يُثبَت هنا بمسارٍ كامل: كتابة →
 * سطر الإنشاء في القائمة نفسها → نافذة بالاسم معبّأً → حفظ → الحقل يحمل
 * العميل والتركيز انتقل إلى حقل البند التالي.
 *
 * ويُثبَت معه ما زِيد فوق الطلب: تحذير التكرار قبل الحفظ (اسمٌ قريب موجود ⇒
 * «اختره» بدل نسخةٍ ثانية) وسطر الإنشاء داخل فهرس الحسابات.
 *
 * الخادم مُقنَّع بالكامل، وقناع `partners/lookup/` يحترم `search` كما يفعل
 * `PartnerViewSet.get_queryset` — بدونه لبدا كلُّ اسمٍ جديدٍ مكرَّراً.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const EXISTING = [
  { id: 8, name: 'زبون الاختبار', partner_type: 'Customer', phone: '0599000000' },
  { id: 9, name: 'زبون آخر', partner_type: 'Customer' },
  { id: 12, name: 'مؤسسة النور للتوريدات', partner_type: 'Supplier' },
];

/** نداءات إنشاء الأطراف — الاختبار يحكم بها لا بالشاشة وحدها. */
type Created = { name: string; partner_type: string };

const openNewInvoice = async (page: Page) => {
  const creates: Created[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'quick-party-token');
    localStorage.setItem('userId', 'quick-party-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/quick-party-user/')) {
      return json({
        id: 'quick-party-user', name: 'مختبِر إضافة العميل', role: 'manager',
        email: 'quick-party@example.test', employmentStatus: 'active',
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
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
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
      return json({
        default_customer: null, default_currency: 1, default_payment_type: 'cash',
        default_cash_account: 10, default_revenue_account_product: 40,
        stock_on_post_default: true, default_vat_rate: null,
        prices_include_tax: false, auto_post_invoices: false,
        show_journal_preview: true,
      });
    }
    if (url.pathname.endsWith('/partners/lookup/')) {
      // يحاكي فلترة الخادم: بحثٌ جزئي في الاسم عبر كل الأنواع.
      const search = (url.searchParams.get('search') || '').trim();
      return json(search ? EXISTING.filter((p) => p.name.includes(search)) : EXISTING);
    }
    if (url.pathname.endsWith('/partners/') && route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() || '{}') as Created;
      creates.push(body);
      return json({ id: 77, name: body.name, partner_type: 'Customer', credit_limit: null });
    }
    if (url.pathname.endsWith('/sales/invoices/')) {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    return json([]);
  });
  await page.goto('/sales/invoices/new');
  await expect(page.getByText('بحث سريع / باركود (F6)', { exact: true }))
    .toBeVisible({ timeout: 15000 });
  return creates;
};

const customerField = (page: Page) => page.getByPlaceholder('اكتب اسم العميل…');

test('اسمٌ غير موجود: «إضافة» تُنشئ العميل وتربطه بالفاتورة والتركيز يمضي للبند', async ({ page }) => {
  const creates = await openNewInvoice(page);

  await customerField(page).click();
  await customerField(page).fill('مؤسسة النور للتجارة');

  // سطر الإنشاء في القائمة نفسها — لا زرّ في مكان آخر يبحث عنه المستخدم.
  const createRow = page.getByRole('option', { name: /إضافة «مؤسسة النور للتجارة» كعميل جديد/ });
  await expect(createRow).toBeVisible();
  await createRow.click();

  // النافذة تُفتح بالاسم معبّأً — لا يُكتب مرتين.
  const nameInput = page.getByPlaceholder("اسم العميل", { exact: true });
  await expect(nameInput).toHaveValue('مؤسسة النور للتجارة');

  await page.getByTestId('quick-add-save').click();

  // العميل مربوط بالفاتورة بلا خطوة يدوية إضافية.
  await expect(customerField(page)).toHaveValue('#77 - مؤسسة النور للتجارة');
  expect(creates).toEqual([
    expect.objectContaining({ name: 'مؤسسة النور للتجارة', partner_type: 'Customer' }),
  ]);
  // والتركيز في محطة الإدخال التالية.
  await expect(page.locator('[data-aseel-field="barcode"]')).toBeFocused();
});

test('اسمٌ قريب من طرف قائم: تحذيرٌ قبل الحفظ و«اختره» يربط القائم بلا إنشاء', async ({ page }) => {
  const creates = await openNewInvoice(page);

  await customerField(page).click();
  await customerField(page).fill('زبون الاختبار الجديد');
  await page.getByRole('option', { name: /إضافة «زبون الاختبار الجديد» كعميل جديد/ }).click();

  // «زبون الاختبار» موجود — يظهر تحذيراً لا منعاً.
  const banner = page.getByTestId('quick-add-similar');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('#8 — زبون الاختبار');

  await banner.getByRole('button', { name: 'اختره' }).click();

  await expect(customerField(page)).toHaveValue('#8 - زبون الاختبار');
  expect(creates).toEqual([]);
});

test('المورد المطابق بالاسم يظهر في التحذير ولا يُختار — ليس عميلاً', async ({ page }) => {
  await openNewInvoice(page);

  await customerField(page).click();
  await customerField(page).fill('مؤسسة النور للتوريدات');
  await page.getByRole('option', { name: /إضافة «مؤسسة النور للتوريدات» كعميل جديد/ }).click();

  const banner = page.getByTestId('quick-add-similar');
  await expect(banner).toContainText('#12 — مؤسسة النور للتوريدات');
  await expect(banner).toContainText('ليس عميلاً');
  await expect(banner.getByRole('button', { name: 'اختره' })).toHaveCount(0);
});

test('فهرس الحسابات: بحثٌ بلا نتيجة يصير سطرَ إنشاء يحمل ما كُتب', async ({ page }) => {
  await openNewInvoice(page);

  await page.getByRole('button', { name: 'فهرس الحسابات — العملاء' }).click();
  await expect(page.locator('.aseel-picker')).toBeVisible();
  await page.getByPlaceholder(/بحث…/).fill('شركة الأمل');

  const createRow = page.getByRole('button', { name: 'إضافة «شركة الأمل» كعميل جديد' });
  await expect(createRow).toBeVisible();
  await createRow.click();

  await expect(page.getByPlaceholder("اسم العميل", { exact: true })).toHaveValue('شركة الأمل');
});
