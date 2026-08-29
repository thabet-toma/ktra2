/**
 * T-PAYFULL2 — الزرّ الأساسي على مسودّة فاتورة الشراء.
 *
 * شكوى المالك حرفياً: «كبست مدفوعة … حطيت حفظ وترحيل بقلي يجب اختيار صندوق»
 * ثم «لما احط مدفوعة لازم المبلغ … يتسجل لحالو بالدفع تحت ولما احط حفظ
 * وترحيل تتسجل الدفعة». عطلان مستقلّان اجتمعا على شاشةٍ واحدة:
 *
 * 1. **«نقدي» كانت طريقاً مسدوداً.** `cash_or_bank_account` حقلٌ يشترطه
 *    المُسلسِل، ويقرؤه بناءُ الحمولة، ويملأه المُطابِق من الخادم — ولا موضع
 *    واحد في المحرّر يكتبه. فعلامةٌ في الرأس تُنتج رفضاً لا مخرج له على
 *    الشاشة. (جانب البيع يملأ نظيره بالسلّم نفسه منذ T-CASHBOX.)
 * 2. **«حفظ وترحيل» كان يبتلع المبلغ المعبّأ.** اللوحة مملوءة والزرّ الأساسي
 *    يحفظ ويرحّل ويمضي — فتُرحَّل الفاتورة غير مدفوعة والرقم يبقى معلّقاً في
 *    شاشةٍ تبدو كأنها نفّذته.
 *
 * و**T-PAYFULL3** بعدهما: «مدفوعة» على المسودة صارت **تسجّل دفعةً غير مرحّلة**
 * (نيّةً تتجسّد سنداً عند الترحيل) لا تعبئةَ خانةٍ فحسب — قرار المالك.
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react`) — فمرور المتصفّح هو الدليل
 * الوحيد على أن حقل الصندوق يُرسَم فعلاً وأن الزرّ يسلك المسار الجديد.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** مسودّة فاتورة شراء: إجمالي 100، مورّد محدَّد، بندٌ واحد، لم تُرحَّل بعد. */
const DRAFT = (overrides: Record<string, unknown> = {}) => ({
  id: 88, invoice_number: 'PINV-0088', invoice_name: 'مسودّة الدفع',
  invoice_date: '2026-08-20', partner: 4, partner_name: 'مورّد الإطارات',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 100, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 100, invoice_type: 'local', status: 'draft',
  payment_type: 'credit', cash_or_bank_account: null,
  is_posted: false, is_return: false, is_local: true,
  receipt_status: 'not_received', receipt_status_display: 'غير مستلمة',
  amount_paid: 0, remaining_balance: 100,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '100',
  items: [{
    id: 501, product: 9, product_name: 'إطار 225/45', quantity: '1',
    unit_price: '100', line_total: '100', description: '',
  }],
  fees: [], payment_details: [], cheques: [],
  created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z',
  ...overrides,
});

type Calls = {
  pay: Array<Record<string, unknown>>;
  attach: Array<Record<string, unknown>>;
  patch: Array<Record<string, unknown>>;
  post: number;
};

/**
 * يفتح مسودّة الفاتورة بموجِّهٍ يحاكي الخادم: الدفع يخصم فعلاً ويعيد الفاتورة
 * مرحّلةً مدفوعة — لولا ذلك لكذّبت `reloadInvoice` الشاشةَ بعد النجاح.
 */
const openDraft = async (
  page: Page, invoiceOverrides: Record<string, unknown> = {},
): Promise<Calls> => {
  const calls: Calls = { pay: [], attach: [], patch: [], post: 0 };
  let settled = 0;
  /** نيّة الدفع المعلَّقة على المسودة — غير مرحّلة حتى يُرحَّل المستند. */
  let intent = 0;
  let posted = false;
  const current = () => DRAFT({
    ...invoiceOverrides,
    is_posted: posted,
    status: posted ? 'completed' : 'draft',
    ...(posted ? { journal_id_display: 901 } : {}),
    amount_paid: settled,
    remaining_balance: Math.max(100 - settled, 0),
    payment_status: settled >= 100 ? 'paid' : settled > 0 ? 'partially_paid' : 'unpaid',
    payment_status_display: settled >= 100
      ? 'مدفوعة بالكامل' : settled > 0 ? 'مدفوعة جزئياً' : 'غير مدفوعة',
    payment_details: settled > 0
      ? [{ id: 556, paymentDate: '2026-08-21', amount: String(settled), isPosted: true }]
      : [],
    attached_cash_amount: String(intent),
    attached_cash_account: intent > 0 ? 10 : null,
    pending_payment_total: String(intent),
  });

  await page.addInitScript(() => {
    localStorage.setItem('token', 'payfull2-token');
    localStorage.setItem('userId', 'payfull2-user');
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('ktra_ui_mode::1', 'advanced');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const method = route.request().method();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });

    if (url.pathname.endsWith('/hr/users/payfull2-user/')) {
      return json({
        id: 'payfull2-user', name: 'أمين الصرف', role: 'manager',
        email: 'payfull2@example.test', employmentStatus: 'active',
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
        { id: 10, code: '1101', name: 'الصندوق الرئيسي', account_type: 'Asset', is_active: true },
        { id: 21, code: '2101', name: 'ذمم الموردين', account_type: 'Liability', is_active: true },
      ]);
    }
    if (url.pathname.endsWith('/accounting/cash-box-accounts/my-default/')) {
      return json({ cash_box: 1, cash_box_name: 'الصندوق الرئيسي' });
    }
    if (url.pathname.endsWith('/accounting/cash-box-accounts/')) {
      return json([{
        id: 1, name: 'الصندوق الرئيسي', account_id: 10, account_code: '1101',
        currency_code: 'ILS', is_default: true, is_active: true,
      }]);
    }
    if (/\/logistics\/purchase-invoices\/88\/pay\/$/.test(url.pathname)) {
      const body = route.request().postDataJSON();
      calls.pay.push(body);
      if (body.post_invoice) posted = true;
      settled = Number(body.cash || 0)
        + (body.cheques || []).reduce(
          (s: number, c: { amount?: string }) => s + Number(c.amount || 0), 0);
      return json({ invoice: current(), payment_id: 556 });
    }
    if (/\/logistics\/purchase-invoices\/88\/attach-payment\/$/.test(url.pathname)) {
      const body = route.request().postDataJSON();
      calls.attach.push(body);
      intent = Number(body.cash_amount || 0);
      return json(current());
    }
    if (/\/logistics\/purchase-invoices\/88\/post-to-accounting\/$/.test(url.pathname)) {
      calls.post += 1;
      posted = true;
      // الخادم يجسّد النيّة سندَ صرفٍ واحداً داخل معاملة الترحيل.
      settled += intent;
      intent = 0;
      return json(current());
    }
    if (/\/logistics\/purchase-invoices\/88\/$/.test(url.pathname)) {
      if (method === 'PATCH' || method === 'PUT') {
        calls.patch.push(route.request().postDataJSON());
      }
      return json(current());
    }
    return json([]);
  });
  await page.goto('/purchase-invoices/88');
  await expect(page.getByTestId('document-payment-panel')).toBeVisible({ timeout: 20000 });
  return calls;
};

/** T-RECVOPT: كل ترحيلٍ لفاتورة محلية غير مستلَمة يسأل عن دخول البضاعة أوّلاً. */
const confirmPost = async (page: Page) => {
  await page.getByRole('alertdialog').getByRole('button', { name: 'ترحيل' })
    .click({ timeout: 20000 });
};

test('«مدفوعة» على مسودّة تسجّل دفعةً غير مرحّلة، والترحيل يجسّدها سنداً', async ({ page }) => {
  const calls = await openDraft(page);

  await expect(page.getByTestId('payment-cash')).toHaveValue('');
  await page.getByRole('button', { name: 'مدفوعة', exact: true }).click();

  // نيّةٌ تُحفظ على الفاتورة — لا سند ولا قيد ولا ترحيل.
  await expect.poll(() => calls.attach.length, { timeout: 20000 }).toBe(1);
  const attached = calls.attach[0] as { cash_amount: string; cash_account_id: number };
  expect(attached.cash_amount).toBe('100.00');
  expect(attached.cash_account_id).toBe(10);
  expect(calls.pay).toHaveLength(0);
  expect(calls.post).toBe(0);
  // والمبلغ محسوبٌ من الشاشة، فالحفظُ يسبق التعليق كي يطابق المخزَّن.
  expect(calls.patch.length).toBeGreaterThan(0);

  // «لازم في حركة»: المستند يوسَم «مدفوعة — غير مرحّلة» في مكانه.
  await expect(page.getByText('مدفوعة — غير مرحّلة').first())
    .toBeVisible({ timeout: 20000 });

  // ضغطةٌ ثانية لا تُضاعف الدفعة: الأساس `remainingAfterIntent`.
  await page.getByRole('button', { name: 'مدفوعة', exact: true }).click();
  await expect(page.getByText('لا متبقٍّ', { exact: false }).first()).toBeVisible();
  expect(calls.attach).toHaveLength(1);

  // ثم الترحيل العادي — الخادم يجسّد النيّة سندَ صرفٍ واحداً داخل معاملته.
  await page.getByRole('button', { name: /^حفظ وترحيل$/ }).click();
  await confirmPost(page);
  await expect.poll(() => calls.post, { timeout: 20000 }).toBe(1);
  expect(calls.pay).toHaveLength(0);
  await expect(page.getByRole('button', { name: 'مسدَّدة', exact: true }).first())
    .toBeVisible({ timeout: 20000 });
});

test('مبلغٌ يُكتب في اللوحة يدوياً يبقى يمرّ من «حفظ وترحيل» بنداء pay/ واحد', async ({ page }) => {
  const calls = await openDraft(page);

  // لا «مدفوعة» هنا — الكتابة اليدوية في اللوحة (دفعة جزئية مثلاً).
  await page.getByTestId('payment-cash').fill('40');
  await page.getByRole('button', { name: /^حفظ وترحيل$/ }).click();
  await confirmPost(page);
  await expect.poll(() => calls.pay.length, { timeout: 20000 }).toBe(1);

  const body = calls.pay[0] as { cash: string; post_invoice: boolean };
  expect(body.cash).toBe('40');
  // الترحيل داخل النداء نفسه — لا مسار ترحيلٍ ثانٍ ينفصل عن المال.
  expect(body.post_invoice).toBe(true);
  expect(calls.post).toBe(0);
  // و«حفظ» في اسم الزرّ وعدٌ يُوفى: `pay/` يدفع ويرحّل ولا يحفظ بنداً.
  expect(calls.patch.length).toBeGreaterThan(0);
});

test('«حفظ وترحيل» بلوحةٍ فارغة يبقى ترحيلاً عادياً بلا سند', async ({ page }) => {
  const calls = await openDraft(page);

  await page.getByRole('button', { name: /^حفظ وترحيل$/ }).click();
  await confirmPost(page);
  await expect.poll(() => calls.post, { timeout: 20000 }).toBe(1);
  expect(calls.pay).toHaveLength(0);
});

test('الفاتورة النقدية تعرض صندوقها معبّأً وترسله مع الحفظ', async ({ page }) => {
  const calls = await openDraft(page);

  // المستند يُفتح عرضاً؛ الرأس (ومعه علامة «نقدي») في وضع التحرير.
  await page.getByRole('button', { name: 'تحرير', exact: true }).click();
  // العلامة في الرأس — وحقل الصندوق يظهر معها معبّأً بالصندوق المسجَّل.
  await page.getByTestId('purchase-payment-type').check();
  const cashField = page.getByTestId('purchase-cash-account');
  await expect(cashField).toBeVisible();
  await expect(cashField).toContainText('الصندوق الرئيسي');

  await page.getByRole('button', { name: /^حفظ وترحيل$/ }).click();
  await expect.poll(() => calls.patch.length, { timeout: 20000 }).toBeGreaterThan(0);
  await confirmPost(page);
  // الحقل الميت صار يُرسَل — وبدونه كان المُسلسِل يردّ
  // «الدفع النقدي يتطلب اختيار حساب صندوق/بنك» بلا حقلٍ يُصلحه.
  expect(calls.patch[0].payment_type).toBe('cash');
  expect(calls.patch[0].cash_or_bank_account).toBe(10);
});
