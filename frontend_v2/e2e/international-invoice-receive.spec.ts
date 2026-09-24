/**
 * الفاتورة الدولية تُستلَم كالمحلية — بلاغ المالك: «مرحّلة ومستلمة ومكتوب
 * عليها غير مستلمة»، والشاشة تخفي أعمدة الاستلام وزرّه عن الدولية.
 *
 * فاتورة IMP-0033 دولية (صفقة + شحنة) مرحّلة، استُلم منها 4 من 10. الشاشة
 * يجب أن تعرض «مستلَم / باقي الاستلام» وملخّص الرأس وزرّي «استلام» و«إرسالية
 * جديدة» كالفاتورة المحلية. حارس الخادم:
 * `logistics/tests/test_import_invoice_receive.py`.
 *
 * `tsc` لا يفحص خصائص JSX هنا — مرور المتصفح هو الدليل على أن الأعمدة تُرسم.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const ITEMS = [
  {
    id: 91, product: 71, product_name: 'إطار مستورد', name: 'إطار مستورد',
    quantity: '10.0000', received_quantity: '4.0000', remaining_quantity: '6.0000',
    unit_price: '100.0000', total_price: '1000.00',
    landed_unit_price_ils: '600.0000', landed_line_total_ils: '6000.00', serials: [],
  },
];

const INVOICE = {
  id: 33, invoice_number: 'IMP-0033', invoice_name: 'استيراد إطارات',
  invoice_date: '2026-07-02', partner: 4, partner_name: 'مصنع صيني',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 6000, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 6000, invoice_type: 'international', status: 'completed',
  deal: 7, shipment: 9, clearance: null,
  is_posted: true, is_return: false, is_local: false,
  journal_id_display: 556,
  receipt_status: 'partially_received', receipt_status_display: 'مستلمة جزئياً',
  receipt_progress: {
    ordered: '10.0000', received: '4.0000', remaining: '6.0000',
    lines_total: 1, lines_remaining: 1,
  },
  amount_paid: 0, remaining_balance: 6000,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '6000',
  items: ITEMS, fees: [], payment_details: [],
  created_at: '2026-07-02T00:00:00Z', updated_at: '2026-07-02T00:00:00Z',
};

const openInvoice = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'imprcv-token');
    localStorage.setItem('userId', 'imprcv-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/imprcv-user/')) {
      return json({
        id: 'imprcv-user', name: 'مختبِر الاستيراد', role: 'manager',
        email: 'imprcv@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاستيراد', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: true,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: true,
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
  // المسار الدولي يلزمه صلاحية استيراد؛ الشاشة واحدة والطابع الدولي من بيانات الفاتورة.
  await page.goto('/purchase-invoices/33');
  await expect(page.getByText('IMP-0033').first()).toBeVisible({ timeout: 20000 });
};

test('الدولية المرحّلة تعرض المستلَم والباقي وزرّ الاستلام كالمحلية', async ({ page }) => {
  await openInvoice(page);

  await expect(page.getByText('استُلم 4 من 10 — باقي 6').first()).toBeVisible();
  await expect(page.getByText('مستلَم', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('باقي الاستلام', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'استلام', exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'إرسالية جديدة' }).first()).toBeVisible();

  await page.screenshot({
    path: 'e2e/receipt-remaining-shots/international-partially-received.png',
    fullPage: true,
  });
});
