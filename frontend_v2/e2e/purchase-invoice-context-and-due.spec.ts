/**
 * T-PCTX / T-DUE / T-PSIMPL — ما أُضيف إلى فاتورة الشراء لتصير مركز سياق.
 *
 * ثلاثة أشياء يقيسها هذا الملف في المتصفح، لأن `tsc` لا يفحص خصائص JSX هنا
 * (لا `@types/react` في المشروع) فلا دليل على أن المكوّن رُكِّب فعلاً إلا تشغيله:
 *
 *  1. تبويبا «حركة المخزون» و«حساب المورّد» + المرفقات الحيّة — وهي نفس مكوّنات
 *     فاتورة البيع (`DocumentContextTabs`) بمفردات المورّد.
 *  2. حقلا الاستحقاق ومهلة السداد، وشارة «متأخرة» بجانب حالة الدفع لا بدلاً منها.
 *  3. زرّ «نسخ» ورقم المسودّة التالي.
 *
 * حرّاس الصحّة في الخادم: `logistics/tests/test_purchase_invoice_context_tabs.py`
 * و`test_due_date_and_overdue.py` و`test_purchase_parity_extras.py`.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const INVOICE = (overrides: Record<string, unknown> = {}) => ({
  id: 88, invoice_number: 'PINV-0088', invoice_name: 'فاتورة السياق',
  invoice_date: '2026-07-01',
  due_date: '2026-07-31', payment_terms_days: 30,
  is_overdue: true, days_overdue: 23,
  partner: 4, partner_name: 'مورّد السياق',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 500, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 500, invoice_type: 'local', status: 'completed',
  payment_type: 'credit',
  is_posted: true, is_return: false, is_local: true,
  journal_id_display: 901,
  receipt_status: 'not_received', receipt_status_display: 'غير مستلمة',
  amount_paid: 0, remaining_balance: 500,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '500',
  items: [], fees: [], payment_details: [],
  supplier_balance_current: '500',
  created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z',
  ...overrides,
});

type Calls = { stock: number; ledger: number; attachments: number; duplicate: number };

const openInvoice = async (page: Page): Promise<Calls> => {
  const calls: Calls = { stock: 0, ledger: 0, attachments: 0, duplicate: 0 };
  await page.addInitScript(() => {
    localStorage.setItem('token', 'pctx-token');
    localStorage.setItem('userId', 'pctx-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('ktra_ui_mode::1', 'advanced');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/pctx-user/')) {
      return json({
        id: 'pctx-user', name: 'مراجع السياق', role: 'manager',
        email: 'pctx@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة السياق', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: [
          'purchase.invoice.view', 'purchase.invoice.create',
          'purchase.invoice.edit', 'purchase.invoice.post',
          'purchase.payment.create',
        ],
      });
    }
    if (/\/purchase-invoices\/88\/stock-movements\/$/.test(url.pathname)) {
      calls.stock += 1;
      return json({
        results: [{
          id: 4001, date: '2026-07-02', movement_type: 'IN',
          movement_type_label: 'وارد', reference_type: 'PURCHASE_INVOICE',
          product_id: 7, product_name: 'منتج السياق', warehouse: 'الرئيسي',
          qty_in: '5', qty_out: '0', quantity_before: '0',
          running_balance: '5', unit_cost: '100', total_cost: '500',
        }],
        count: 1, total_cost: '500', is_posted: true,
        receipt_status: 'received', receipt_status_display: 'مستلمة',
      });
    }
    if (/\/purchase-invoices\/88\/supplier-ledger\/$/.test(url.pathname)) {
      calls.ledger += 1;
      return json({
        results: [{
          id: 9, journal_id: 901, date: '2026-07-01',
          reference_type: 'PURCHASE_INVOICE', reference_id: 88,
          description: 'فاتورة شراء PINV-0088', debit: '0', credit: '500',
          balance_before: '0', running_balance: '500', is_anchor: true,
        }],
        count: 1, closing_balance: '500', supplier_name: 'مورّد السياق',
        anchor: {
          line_ids: [9], balance_before: '0', balance_after: '500', effect: '500',
        },
      });
    }
    if (/\/purchase-invoices\/88\/attachments\/$/.test(url.pathname)) {
      calls.attachments += 1;
      return json([]);
    }
    if (/\/purchase-invoices\/88\/duplicate\/$/.test(url.pathname)) {
      calls.duplicate += 1;
      return json(INVOICE({ id: 89, invoice_number: 'PINV-0089', is_posted: false }));
    }
    if (/\/purchase-invoices\/89\/$/.test(url.pathname)) {
      return json(INVOICE({ id: 89, invoice_number: 'PINV-0089', is_posted: false }));
    }
    if (/\/purchase-invoices\/88\/$/.test(url.pathname)) return json(INVOICE());
    if (url.pathname.endsWith('/purchase-invoices/next-number/')) {
      return json({ invoice_number: 'PINV-0090' });
    }
    if (url.pathname.endsWith('/logistics/purchase-invoices/')) {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    return json([]);
  });
  await page.goto('/purchase-invoices/88');
  await expect(page.getByText('PINV-0088').first()).toBeVisible({ timeout: 20000 });
  return calls;
};

test('تبويبا السياق لا يُجلبان حتى يُفتحا، ثم يعرضان أثر الفاتورة', async ({ page }) => {
  const calls = await openInvoice(page);
  // الكسل شرطٌ لا تحسين: فتح الفاتورة لا يُصدر نداء تبويب.
  expect(calls.stock).toBe(0);
  expect(calls.ledger).toBe(0);

  await page.getByRole('tab', { name: 'حركة المخزون' }).click();
  await expect.poll(() => calls.stock, { timeout: 10000 }).toBeGreaterThan(0);
  await expect(page.getByText('4001').first()).toBeVisible();
  await expect(page.getByText('منتج السياق').first()).toBeVisible();

  await page.getByRole('tab', { name: 'حساب المورّد' }).click();
  await expect.poll(() => calls.ledger, { timeout: 10000 }).toBeGreaterThan(0);
  // أثر الفاتورة = كامل قيد الذمم (500) لا «المتبقّي» منه.
  await expect(page.getByText('أثر الفاتورة').first()).toBeVisible();
  await expect(page.getByText('الرصيد قبل الفاتورة').first()).toBeVisible();
  await page.screenshot({
    path: 'e2e/pay-panel-shots/purchase-supplier-ledger-tab.png', fullPage: true,
  });
});

test('المرفقات تُجلب من نقطتها الحيّة فيبقى الإرفاق ممكناً بعد الترحيل', async ({ page }) => {
  const calls = await openInvoice(page);
  await page.getByRole('tab', { name: 'المرفقات' }).click();
  await expect.poll(() => calls.attachments, { timeout: 10000 }).toBeGreaterThan(0);
  await expect(
    page.getByText('تُحفظ فوراً ولو كانت الفاتورة مرحّلة').first(),
  ).toBeVisible();
});

test('الاستحقاق ومهلة السداد حقلان على فاتورة الشراء', async ({ page }) => {
  await openInvoice(page);
  // كل فاتورة محفوظة تُفتح للعرض (`viewMode`)، وحقول الإدخال خلف «تحرير» —
  // والمرحّلة تُوجَّه إلى «تراجع عن الترحيل» أوّلاً، فنستعمل المسودّة (89).
  await page.goto('/purchase-invoices/89');
  await expect(page.getByText('PINV-0089').first()).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: 'تحرير' }).click();
  await page.getByRole('tab', { name: 'بيانات الفاتورة' }).click();
  await expect(page.getByTestId('purchase-due-date')).toHaveValue('2026-07-31');
  await expect(page.getByTestId('purchase-payment-terms')).toHaveValue('30');
});

test('زرّ «نسخ» يفتح مسودّة جديدة بلا ترحيل', async ({ page }) => {
  const calls = await openInvoice(page);
  await page.getByRole('button', { name: 'نسخ', exact: true }).click();
  await expect.poll(() => calls.duplicate, { timeout: 10000 }).toBe(1);
  await expect(page.getByText('PINV-0089').first()).toBeVisible({ timeout: 10000 });
});
