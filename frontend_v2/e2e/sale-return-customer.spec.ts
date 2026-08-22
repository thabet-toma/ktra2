/**
 * T-RETPARTY — «مرجع البيع»: العميل مشتقٌّ من الفاتورة الأصلية لا مُختار.
 *
 * كان حقلاً حرّاً يُعبَّأ تلقائياً ثم يبقى مفتوحاً، والخادم بلا حارس: مرجع
 * فاتورة زيدٍ يُقيَّد على ذمم عمرو فيَنقص دينُ من لم يُرجِع شيئاً — خطأٌ مالي
 * صامت لا يظهر إلا في كشف حساب. الحارس الحقيقي في
 * `SalesInvoiceSerializer.validate` (يحرسه `sales/tests/test_sale_return_customer_integrity.py`)،
 * وهذا وجهه في الشاشة: لا يُعرَض إلا الجواب الواحد الصحيح.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const INVOICES = [
  { id: 501, invoice_number: 'INV-501', status: 'posted', customer: 8, customer_name: 'زبون الشمال' },
  { id: 502, invoice_number: 'INV-502', status: 'posted', customer: 9, customer_name: 'زبون الجنوب' },
];

type Created = { customer?: number; original_invoice?: number };

const openReturnEditor = async (page: Page) => {
  const creates: Created[] = [];
  const partnerListCalls: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ret-party-token');
    localStorage.setItem('userId', 'ret-party-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.includes('/partners/')) partnerListCalls.push(url.pathname + url.search);
    if (url.pathname.endsWith('/hr/users/ret-party-user/')) {
      return json({
        id: 'ret-party-user', name: 'مختبِر المرجع', role: 'manager',
        email: 'ret-party@example.test', employmentStatus: 'active',
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
        permissions: ['sales.invoice.view', 'sales.invoice.create'],
      });
    }
    if (url.pathname.endsWith('/sales/invoices/lookup/')) return json(INVOICES);
    if (/\/sales\/invoices\/50[12]\/$/.test(url.pathname)) {
      const id = Number(url.pathname.match(/(50[12])/)![1]);
      return json({
        ...INVOICES.find((i) => i.id === id),
        lines: [{ product: 71, product_name: 'صنف المرجع', quantity: '2', unit_price: '50' }],
      });
    }
    if (url.pathname.endsWith('/sales/invoices/') && route.request().method() === 'POST') {
      creates.push(JSON.parse(route.request().postData() || '{}'));
      return json({ id: 900, invoice_number: 'SR-900' });
    }
    if (url.pathname.includes('/inventory/products/')) {
      return json([{ id: 71, sku: 'RET-1', name_ar: 'صنف المرجع', unit_price: '50' }]);
    }
    return json([]);
  });
  await page.goto('/sales/returns');
  await expect(page.getByText('الفاتورة الأصلية *', { exact: true }))
    .toBeVisible({ timeout: 15000 });
  return { creates, partnerListCalls };
};

const customerBox = (page: Page) => page.getByTestId('return-customer');
const originalSelect = (page: Page) => page.locator('select').first();

test('العميل يتبع الفاتورة الأصلية، ويُبدَّل معها، ويُفرَغ بإفراغها', async ({ page }) => {
  await openReturnEditor(page);

  // قبل الاختيار: لا اسم، ولا خيار يُختار منه.
  await expect(customerBox(page)).toHaveValue('');
  await expect(customerBox(page)).toHaveAttribute('readonly', '');

  await originalSelect(page).selectOption('501');
  await expect(customerBox(page)).toHaveValue('زبون الشمال');

  // التبديل يُبدّله — لا يبقى عميلُ اختيارٍ سابق عالقاً.
  await originalSelect(page).selectOption('502');
  await expect(customerBox(page)).toHaveValue('زبون الجنوب');

  await originalSelect(page).selectOption('');
  await expect(customerBox(page)).toHaveValue('');
});

test('الحمولة تحمل مشتري الأصل — والشاشة لا تجلب قائمة عملاء أصلاً', async ({ page }) => {
  const { creates, partnerListCalls } = await openReturnEditor(page);

  await originalSelect(page).selectOption('502');
  await expect(customerBox(page)).toHaveValue('زبون الجنوب');
  // البنود تُنسخ من الأصل تلقائياً — فالحفظ لا يحتاج إدخالاً يدوياً.
  await expect(page.getByText('تم نسخ بنود الفاتورة الأصلية — عدّل الكميات المرتجعة.')).toBeVisible();

  await page.getByRole('button', { name: /حفظ/ }).first().click();
  await expect.poll(() => creates.length).toBe(1);
  expect(creates[0]).toMatchObject({ customer: 9, original_invoice: 502 });

  // العميل مشتقّ ⇒ لا قائمةَ عملاءَ تُحمَّل (كانت 500 صفّاً على كل إقلاع).
  expect(partnerListCalls).toEqual([]);
});
