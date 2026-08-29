/**
 * T-APPAY — لوحة الدفع داخل محرّر فاتورة الشراء.
 *
 * كان الدفع هنا نافذةً تُلزم بالترحيل أوّلاً ثم تفتح «سند صرف» — نداءان
 * منفصلان بمفرداتٍ تخالف جانب البيع، فبدا للمالك أن الميزة غائبةٌ أصلاً عن
 * المشتريات. اللوحة الآن هي **نفس مكوّن** لوحة التحصيل في فاتورة البيع
 * (`DocumentPaymentPanel`) بمفرداتِ جانب المورّد، وتنادي `pay/` مرّةً واحدة.
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react` في المشروع) — فمرور المتصفح
 * هو الدليل الوحيد على أن اللوحة تُرسَم وتُرسِل فعلاً لا أنها كُتبت فحسب.
 * حارس صحّة الحساب في الخادم: `logistics/tests/test_purchase_invoice_pay.py`.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** فاتورة شراء مرحّلة: إجمالي 100، لم يُدفع منها شيء بعد. */
const INVOICE = (overrides: Record<string, unknown> = {}) => ({
  id: 77, invoice_number: 'PINV-0077', invoice_name: 'فاتورة الدفع',
  invoice_date: '2026-08-10', partner: 4, partner_name: 'مورّد الدفع',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 100, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 100, invoice_type: 'local', status: 'completed',
  payment_type: 'credit',
  is_posted: true, is_return: false, is_local: true,
  journal_id_display: 900,
  receipt_status: 'not_received', receipt_status_display: 'غير مستلمة',
  amount_paid: 0, remaining_balance: 100,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '100',
  items: [], fees: [], payment_details: [],
  created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z',
  ...overrides,
});

type Calls = { pay: Array<Record<string, unknown>> };

const openInvoice = async (page: Page): Promise<Calls> => {
  const calls: Calls = { pay: [] };
  /** ما سُدِّد حتى الآن في هذه الجلسة — يجعل الموجِّه يحاكي الخادم لا لقطةً جامدة. */
  let settled = 0;
  const paidInvoice = () => INVOICE({
    amount_paid: settled,
    remaining_balance: Math.max(100 - settled, 0),
    payment_status: settled >= 100 ? 'paid' : settled > 0 ? 'partially_paid' : 'unpaid',
    payment_status_display: settled >= 100
      ? 'مدفوعة بالكامل' : settled > 0 ? 'مدفوعة جزئياً' : 'غير مدفوعة',
    payment_details: settled > 0
      ? [{ id: 555, paymentDate: '2026-08-11', amount: String(settled), isPosted: true }]
      : [],
  });
  await page.addInitScript(() => {
    localStorage.setItem('token', 'appay-token');
    localStorage.setItem('userId', 'appay-user');
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
    if (url.pathname.endsWith('/hr/users/appay-user/')) {
      return json({
        id: 'appay-user', name: 'أمين الصرف', role: 'manager',
        email: 'appay@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الدفع', SubscriptionPlan: 'basic',
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
    if (url.pathname.endsWith('/accounting/accounts/')) {
      return json([
        { id: 10, code: '1101', name: 'الصندوق الرئيسي', account_type: 'Asset' },
        { id: 21, code: '2101', name: 'ذمم الموردين', account_type: 'Liability' },
      ]);
    }
    /* T-CASHBOX M1: الصندوق الافتراضي صار يُحلّ من **الصناديق المسجَّلة** لا من
       أوّل حساب نقدي في الشجرة — فبلا هذين المُوجِّهَين تبقى اللوحة بلا صندوق
       ويرفض زرُّ الدفع الإرسال. */
    if (url.pathname.endsWith('/accounting/cash-box-accounts/my-default/')) {
      return json({ cash_box: 1, cash_box_name: 'الصندوق الرئيسي' });
    }
    if (url.pathname.endsWith('/accounting/cash-box-accounts/')) {
      return json([{
        id: 1, name: 'الصندوق الرئيسي', account_id: 10, account_code: '1101',
        currency_code: 'ILS', is_default: true, is_active: true,
      }]);
    }
    // سلفة مرحّلة للمورّد بقي منها 25 «على الحساب».
    if (url.pathname.endsWith('/logistics/supplier-payments/')) {
      return json({
        count: 1, next: null, previous: null,
        results: [{
          id: 91, partner: 4, payment_date: '2026-08-01', amount: '25.00',
          allocated_amount: '0.00', unallocated_amount: '25.00', is_posted: true,
        }],
      });
    }
    if (/\/logistics\/purchase-invoices\/77\/pay\/$/.test(url.pathname)) {
      const body = route.request().postDataJSON();
      calls.pay.push(body);
      // الخادم يخصم المدفوع فعلاً — والمحرّر يُعيد الجلب بعد الدفع
      // (`reloadInvoice`)، فلو بقي الموجِّه يعيد الفاتورة غيرَ مدفوعة لكذّبت
      // الشاشةُ نفسَها. الحالة هنا تُحاكي الخادم بعد السند.
      settled = Number(body.cash || 0)
        + (body.cheques || []).reduce(
          (s: number, c: { amount?: string }) => s + Number(c.amount || 0), 0)
        + (body.from_on_account || []).reduce(
          (s: number, r: { amount?: string }) => s + Number(r.amount || 0), 0);
      return json({ invoice: paidInvoice(), payment_id: 555 });
    }
    if (/\/logistics\/purchase-invoices\/77\/$/.test(url.pathname)) return json(paidInvoice());
    return json([]);
  });
  await page.goto('/purchase-invoices/77');
  await expect(page.getByTestId('document-payment-panel')).toBeVisible({ timeout: 20000 });
  return calls;
};

test('اللوحة تظهر داخل فاتورة الشراء بمفردات المورّد', async ({ page }) => {
  await openInvoice(page);

  await expect(page.getByText('دفع الفاتورة', { exact: false }).first()).toBeVisible();
  // مفردات جانب المورّد لا جانب العميل — سلفةٌ لا رصيدُ عميل.
  await expect(page.getByText('من رصيد المورّد (سلف)').first()).toBeVisible();
  await expect(page.getByText('من رصيد العميل')).toHaveCount(0);
  // والزرّ باسمٍ واحد على الجانبين.
  await expect(page.getByTestId('payment-submit')).toContainText('تسجيل دفعة');

  // لقطتان: الشاشة كاملةً واللوحة وحدها — للسجلّ كما في `collect-panel-shots`.
  await page.screenshot({
    path: 'e2e/pay-panel-shots/purchase-invoice-pay-panel.png', fullPage: true,
  });
  await page.getByTestId('document-payment-panel').screenshot({
    path: 'e2e/pay-panel-shots/pay-panel-only.png',
  });
});

test('تقسيم 60 نقداً و40 شيكاً يُنزل «المتبقي» إلى صفر حيّاً', async ({ page }) => {
  await openInvoice(page);

  await expect(page.getByTestId('payment-remaining')).toHaveText('100');
  await page.getByTestId('payment-cash').fill('60');
  await expect(page.getByTestId('payment-remaining')).toHaveText('40');

  await page.getByRole('button', { name: 'شيك' }).click();
  await page.getByLabel('رقم الشيك 1').fill('CHQ-1');
  await page.getByLabel('استحقاق الشيك 1').fill('2026-09-01');
  await page.getByLabel('مبلغ الشيك 1').fill('40');

  await expect(page.getByTestId('payment-cheques-total')).toHaveText('40');
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');
  await expect(page.getByTestId('payment-overpay-note')).toHaveCount(0);
});

test('زرّ الدفع يُطلق نداء pay/ واحداً بالحمولة المتوقّعة', async ({ page }) => {
  const calls = await openInvoice(page);

  await page.getByTestId('payment-cash').fill('60');
  await page.getByRole('button', { name: 'شيك' }).click();
  await page.getByLabel('رقم الشيك 1').fill('CHQ-9');
  await page.getByLabel('استحقاق الشيك 1').fill('2026-09-01');
  await page.getByLabel('مبلغ الشيك 1').fill('40');
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');

  await page.getByTestId('payment-submit').click();
  await expect.poll(() => calls.pay.length, { timeout: 15000 }).toBe(1);

  const body = calls.pay[0] as {
    cash: string;
    cheques: Array<{ cheque_number: string; amount: string; due_date: string }>;
    post_invoice: boolean;
  };
  expect(body.cash).toBe('60');
  expect(body.cheques).toHaveLength(1);
  expect(body.cheques[0].cheque_number).toBe('CHQ-9');
  expect(body.cheques[0].amount).toBe('40');
  expect(body.cheques[0].due_date).toBe('2026-09-01');
  // الفاتورة مرحّلة سلفاً ⇒ لا يُطلب ترحيلها ثانيةً.
  expect(body.post_invoice).toBe(false);
});

test('سلفة المورّد تُطبَّق من داخل الفاتورة بلا سند جديد', async ({ page }) => {
  const calls = await openInvoice(page);

  await expect(page.getByText('المتاح على الحساب', { exact: false }).first()).toBeVisible();
  await page.getByTestId('payment-from-balance').fill('25');
  await page.getByTestId('payment-cash').fill('75');
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');

  await page.getByTestId('payment-submit').click();
  await expect.poll(() => calls.pay.length, { timeout: 15000 }).toBe(1);

  const body = calls.pay[0] as {
    from_on_account: Array<{ payment_id: number; amount: string }>;
  };
  expect(body.from_on_account).toHaveLength(1);
  expect(body.from_on_account[0].payment_id).toBe(91);
  expect(body.from_on_account[0].amount).toBe('25');
});

test('تجاوز المتبقّي يُظهر تنبيه «الفائض يُسجَّل دفعة على الحساب»', async ({ page }) => {
  await openInvoice(page);

  await page.getByTestId('payment-cash').fill('150');
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');
  await expect(page.getByTestId('payment-overpay-note')).toContainText('50');
});

/* ── T-PAYFULL: التسديد الكامل بلا كتابة رقم ──────────────────────────────
   كان على المستخدم أن يقرأ المتبقّي ثم يكتبه بيده في كل تسديدٍ تام — وهو
   الحالة الغالبة. زرّ «مدفوعة» في الشريط، و«المتبقي كاملاً» في اللوحة،
   يعبّئان الخانة والإرسال يبقى بزرّ «تسجيل دفعة» (قرار المالك: لا سند
   يُرحَّل بنقرةٍ واحدة بلا مراجعة الصندوق والمبلغ). */

test('«المتبقي كاملاً» في اللوحة يملأ النقد بالمتبقّي ويُنزل المتبقي إلى صفر', async ({ page }) => {
  await openInvoice(page);

  await expect(page.getByTestId('payment-cash')).toHaveValue('');
  await expect(page.getByTestId('payment-remaining')).toHaveText('100');

  await page.getByTestId('payment-fill-full').click();

  await expect(page.getByTestId('payment-cash')).toHaveValue('100.00');
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');
});

test('زرّ «مدفوعة» في الشريط يعبّئ اللوحة، والإرسال يُنتج سند صرف بكامل المبلغ', async ({ page }) => {
  const calls = await openInvoice(page);

  await page.getByRole('button', { name: 'مدفوعة', exact: true }).click();
  await expect(page.getByTestId('payment-cash')).toHaveValue('100.00');
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');
  // تعبئةٌ لا إرسال — لا نداء قبل ضغط «تسجيل دفعة».
  expect(calls.pay).toHaveLength(0);

  await page.getByTestId('payment-submit').click();
  await expect.poll(() => calls.pay.length, { timeout: 15000 }).toBe(1);

  const body = calls.pay[0] as {
    cash: string;
    cheques: unknown[];
    from_on_account: unknown[];
    post_invoice: boolean;
  };
  expect(body.cash).toBe('100.00');
  expect(body.cheques).toHaveLength(0);
  expect(body.from_on_account).toHaveLength(0);
  expect(body.post_invoice).toBe(false);

  // وبعد الردّ: الحالة تنقلب فوراً — «مسدَّدة» في الشريط واللوحة تنسحب.
  await expect(page.getByRole('button', { name: 'مسدَّدة', exact: true }).first())
    .toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('document-payment-panel')).toHaveCount(0);
});

test('الفتح بـ`?pay=full` من القائمة يصل واللوحة معبّأة سلفاً', async ({ page }) => {
  await openInvoice(page);
  await page.goto('/purchase-invoices/77?pay=full');

  await expect(page.getByTestId('payment-cash')).toHaveValue('100.00', { timeout: 20000 });
  await expect(page.getByTestId('payment-remaining')).toHaveText('0');
});
