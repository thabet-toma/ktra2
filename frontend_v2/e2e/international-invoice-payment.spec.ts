/**
 * 3ب: حالة دفع الفاتورة الدولية = تكاليفها الأربع مقابل دفعاتها الأربع.
 *
 * IMP-0034 دفعت صفقتُها كاملة (المورد مسدَّد) والشحن والتخليص والمحلي لا —
 * فهي «مدفوعة جزئياً» لا «مدفوعة»، وملخّص المورد (سندات الفاتورة) يقول
 * «مدفوعة». التمرير فوق الحالة يُظهر «مورد · شحن · تخليص · محلي».
 * حارس الخادم: `logistics/tests/test_import_invoice_settlement.py`.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const IMPORT_PAYMENT = {
  payment_status: 'partially_paid', payment_status_display: 'مدفوعة جزئياً',
  payable_total: '8579.85', amount_paid: '7115.50', remaining_balance: '1464.35',
  components: {
    supplier: { cost: '7000.00', paid: '7000.00', remaining: '0.00' },
    freight: { cost: '1199.88', paid: '0.00', remaining: '1199.88' },
    clearance: { cost: '229.98', paid: '115.50', remaining: '114.48' },
    local: { cost: '149.99', paid: '0.00', remaining: '149.99' },
  },
};
const TOOLTIP = 'مورد 7,000 / 7,000 · شحن 0 / 1,199.88 · تخليص 115.5 / 229.98 · محلي 0 / 149.99';

const BASE = {
  id: 34, invoice_number: 'IMP-0034', invoice_name: 'استيراد كوابل',
  invoice_date: '2026-07-02', partner: 4, partner_name: 'مصنع الكوابل',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 8579.85, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 8579.85, invoice_type: 'international', status: 'completed',
  deal: 7, shipment: 9, clearance: 3,
  is_posted: true, is_return: false, is_local: false,
  journal_id_display: 557,
  receipt_status: 'received', receipt_status_display: 'مستلمة',
  // جانب المورد: ما دائنه به الترحيل (البضاعة) ودفعة الصفقة سدّدته.
  fees_total: '0', payable_total: '7000.00', amount_paid: '7000.00', remaining_balance: '0.00',
  payment_status: 'paid', payment_status_display: 'مدفوعة بالكامل',
  import_payment: IMPORT_PAYMENT,
  created_at: '2026-07-02T00:00:00Z', updated_at: '2026-07-02T00:00:00Z',
};
const INVOICE = {
  ...BASE,
  items: [{
    id: 92, product: 72, product_name: 'كابل', name: 'كابل',
    quantity: '10.0000', received_quantity: '10.0000', remaining_quantity: '0.0000',
    unit_price: '857.9850', total_price: '8579.85',
    landed_unit_price_ils: '857.9850', landed_line_total_ils: '8579.85', serials: [],
  }],
  fees: [], payment_details: [],
};

const mockApi = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'imppay-token');
    localStorage.setItem('userId', 'imppay-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/imppay-user/')) {
      return json({
        id: 'imppay-user', name: 'مختبِر الاستيراد', role: 'manager',
        email: 'imppay@example.test', employmentStatus: 'active',
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
    if (/\/logistics\/purchase-invoices\/34\/$/.test(url.pathname)) return json(INVOICE);
    if (/\/logistics\/purchase-invoices\/$/.test(url.pathname)) {
      return json({ count: 1, results: [{ ...BASE, items_count: 1 }] });
    }
    return json([]);
  });
};

test('عرض الدولية: الحالة من التكاليف الأربع والتفصيل عند التمرير', async ({ page }) => {
  await mockApi(page);
  await page.goto('/purchase-invoices/34');
  await expect(page.getByText('IMP-0034').first()).toBeVisible({ timeout: 20000 });

  const status = page.getByTitle(TOOLTIP).first();
  await expect(status).toHaveText('مدفوعة جزئياً');
  await expect(page.getByText('إجمالي التكاليف').first()).toBeVisible();
  await expect(page.getByText('1,464.35').first()).toBeVisible();
  await status.hover();
  await page.screenshot({ path: 'e2e/receipt-remaining-shots/international-payment-detail.png', fullPage: true });
});

test('قائمة الفواتير: شارة الدولية جزئية لا «مدفوعة»', async ({ page }) => {
  await mockApi(page);
  await page.goto('/purchase-invoices');
  await expect(page.getByText('IMP-0034').first()).toBeVisible({ timeout: 20000 });
  const badge = page.getByTitle(TOOLTIP).first();
  await expect(badge).toContainText('مدفوعة جزئياً');
  await expect(page.getByText('7,115.5').first()).toBeVisible();
  // الإجمالي تكاليفها الأربع، وزرّ «مدفوعة» (سند المورد) غائب: حصّة المورد مسدَّدة.
  await expect(page.getByText('8,579.85').first()).toBeVisible();
  await expect(page.getByTitle('تسجيل الدفع بكامل المتبقّي')).toHaveCount(0);
  await page.screenshot({ path: 'e2e/receipt-remaining-shots/international-payment-list.png', fullPage: true });
});
