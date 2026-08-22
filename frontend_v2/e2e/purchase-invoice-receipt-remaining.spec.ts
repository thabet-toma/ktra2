/**
 * T-RECVIS — الفاتورة تقول بنفسها كم انطلب وكم وصل وكم باقي.
 *
 * فاتورة INV-0033 مرحّلة استُلم منها 550 من 2100 على إرسالية واحدة، والباقي
 * 1550 على بندين. كان المستخدم يفتحها فلا يجد إلا «الكمية»، فيضطر إلى تقرير
 * البواقي أو إلى حسبةٍ باليد لكل بند.
 *
 * تُشترى الأرقام هنا من الخادم كما هي (`receipt_progress` و`remaining_quantity`)
 * ولا تُطرح في الشاشة — لذلك يُغذّي هذا الاختبار حمولةً **متسقة داخلياً** ثم
 * يتحقّق أن الشاشة تعرضها كما هي. حارس صحّة الحساب نفسه في الخادم:
 * `logistics/tests/test_purchase_receipt_visibility.py`.
 *
 * ويحرس أيضاً فكّ التباس «المتبقي»: المال صار «المتبقي للدفع» بعد أن صارت
 * الكلمة تعني رقمين على شاشةٍ واحدة.
 *
 * `tsc` هنا لا يفحص خصائص JSX (لا `@types/react` في المشروع) — فمرور المتصفح
 * هو الدليل الوحيد على أن الأعمدة تُرسم فعلاً لا أنها كُتبت فحسب.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const ITEMS = [
  {
    id: 91, product: 71, product_name: 'إطار 205/55', name: 'إطار 205/55',
    quantity: '1500.0000', received_quantity: '550.0000',
    remaining_quantity: '950.0000',
    unit_price: '10.0000', total_price: '15000.00', serials: [],
  },
  {
    id: 92, product: 72, product_name: 'إطار 225/45', name: 'إطار 225/45',
    quantity: '600.0000', received_quantity: '0.0000',
    remaining_quantity: '600.0000',
    unit_price: '10.0000', total_price: '6000.00', serials: [],
  },
];

const INVOICE = {
  id: 33, invoice_number: 'INV-0033', invoice_name: 'إطارات دفعة أولى',
  invoice_date: '2026-06-11', partner: 4, partner_name: 'مورّد الإطارات',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 21000, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 21000, invoice_type: 'local', status: 'completed',
  is_posted: true, is_return: false, is_local: true,
  journal_id_display: 555,
  receipt_status: 'partially_received', receipt_status_display: 'مستلمة جزئياً',
  receipt_progress: {
    ordered: '2100.0000', received: '550.0000', remaining: '1550.0000',
    lines_total: 2, lines_remaining: 2,
  },
  amount_paid: 0, remaining_balance: 21000,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '21000',
  items: ITEMS, fees: [], payment_details: [],
  created_at: '2026-06-11T00:00:00Z', updated_at: '2026-06-11T00:00:00Z',
};

const openInvoice = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'recvis-token');
    localStorage.setItem('userId', 'recvis-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/recvis-user/')) {
      return json({
        id: 'recvis-user', name: 'مختبِر الاستلام', role: 'manager',
        email: 'recvis@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الإطارات', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: ['purchase.invoice.view', 'purchase.invoice.create'],
      });
    }
    if (/\/logistics\/purchase-invoices\/33\/$/.test(url.pathname)) return json(INVOICE);
    return json([]);
  });
  await page.goto('/purchase-invoices/33');
  await expect(page.getByText('INV-0033').first()).toBeVisible({ timeout: 20000 });
};

test('بنود الفاتورة تعرض المستلَم والباقي، ورأسُها «استُلم 550 من 2100 — باقي 1550»', async ({ page }) => {
  await openInvoice(page);

  // الملخّص في الرأس — بلا فتح تقرير آخر ولا حسبةٍ يدوية.
  await expect(page.getByText('استُلم 550 من 2100 — باقي 1550').first())
    .toBeVisible();
  await expect(page.getByText('مستلمة جزئياً').first()).toBeVisible();

  // العمودان على الجدول.
  await expect(page.getByText('مستلَم', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('باقي الاستلام', { exact: true }).first()).toBeVisible();

  // صفّ البند الأول: 1500 مطلوب / 550 مستلَم / 950 باقٍ.
  const firstRow = page.locator('tr', { hasText: 'إطار 205/55' }).first();
  await expect(firstRow).toContainText('1500');
  await expect(firstRow).toContainText('550');
  await expect(firstRow).toContainText('950');

  // والبند الذي لم يصل منه شيء: كامل كميته باقية.
  const secondRow = page.locator('tr', { hasText: 'إطار 225/45' }).first();
  await expect(secondRow).toContainText('600');

  // لقطة للسجلّ — نفس عادة `collect-panel-shots` و`parity-shots`.
  await page.screenshot({
    path: 'e2e/receipt-remaining-shots/invoice-partially-received.png',
    fullPage: true,
  });
});

test('«المتبقي» المالي صار «المتبقي للدفع» — فلا كلمةَ واحدة لرقمين', async ({ page }) => {
  await openInvoice(page);

  await expect(page.getByText('المتبقي للدفع').first()).toBeVisible();
  // ولا تسميةَ «المتبقي» مجرّدةً على الشاشة نفسها.
  await expect(page.getByText('المتبقي', { exact: true })).toHaveCount(0);
});
