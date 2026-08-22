/**
 * T-SUPSKU · T-RECVOPT — الرقم الذي بيد المستخدم، والخيار الذي كان للشركة كلّها.
 *
 * (1) مطابقة فاتورة المورّد تجري برقم كتالوجه (מק"ט) لا برقمنا. منتقي بنود
 *     الفاتورة يجلب الكتالوج دفعةً واحدة ويبحث **موضعياً**، فبحث الخادم لا
 *     يبلغه — لذلك يعبر الرقم في `supplier_codes_text` ضمن عقد `view=lookup`.
 *     هنا يُثبَت أن كتابة رقم المورّد تجد الصنف فعلاً، وأن الرقم يُعرض كي يرى
 *     المستخدم **لماذا** طابق.
 *
 * (2) «الاستلام مع الترحيل» كان إعداداً على الشركة كلّها. يُثبَت أن الترحيل
 *     صار يسأل، وأن الجواب يصل الخادم في جسم الطلب.
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react`) — فمرور المتصفح هو الدليل.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** كتالوج المنتقي كما يعيده `view=lookup`. */
const LOOKUP = [
  {
    id: 71, sku: '001313', name_ar: 'إطار 205/55', display_name: 'إطار 205/55',
    category: null, category_name: 'إطارات', quantity_on_hand: '10',
    avg_cost: '10', sale_price: '20', is_service: false, is_serialized: false,
    supplier_codes_text: '3068.82',
  },
  {
    id: 72, sku: '001314', name_ar: 'إطار 225/45', display_name: 'إطار 225/45',
    category: null, category_name: 'إطارات', quantity_on_hand: '5',
    avg_cost: '10', sale_price: '20', is_service: false, is_serialized: false,
    supplier_codes_text: '',
  },
];

const DRAFT_INVOICE = {
  id: 44, invoice_number: 'INV-0044', invoice_date: '2026-06-11',
  partner: 4, partner_name: 'مورّد الإطارات',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 100, discount_amount: 0, tax_rate: 0, tax_amount: 0,
  grand_total: 100, invoice_type: 'local', status: 'incomplete',
  is_posted: false, is_return: false, is_local: true,
  receipt_status: 'not_received', receipt_status_display: 'غير مستلمة',
  amount_paid: 0, remaining_balance: 100,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '100',
  items: [{
    id: 81, product: 71, product_name: 'إطار 205/55', name: 'إطار 205/55',
    quantity: '10.0000', received_quantity: '0.0000', remaining_quantity: '10.0000',
    unit_price: '10.0000', total_price: '100.00', serials: [],
  }],
  fees: [], payment_details: [],
  created_at: '2026-06-11T00:00:00Z', updated_at: '2026-06-11T00:00:00Z',
};

type Posted = { body: unknown };

const openDraftInvoice = async (page: Page, receiveOnPost: boolean) => {
  const posts: Posted[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'supsku-token');
    localStorage.setItem('userId', 'supsku-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/supsku-user/')) {
      return json({
        id: 'supsku-user', name: 'مختبِر الأرقام', role: 'manager',
        email: 'supsku@example.test', employmentStatus: 'active',
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
        permissions: [
          'purchase.invoice.view', 'purchase.invoice.create',
          'purchase.invoice.edit', 'purchase.invoice.post',
        ],
      });
    }
    if (url.pathname.endsWith('/logistics/purchase-settings/current/')) {
      return json({
        purchase_default_price_strategy: 'last',
        default_cash_account: null,
        receive_on_post: receiveOnPost,
        receipt_doc_label: 'إرسالية شراء',
        standalone_receipt_label: 'سند استلام',
        allow_standalone_receipt: true, allow_edit_receipt: true,
        serial_entry_mode: 'off',
      });
    }
    if (url.pathname.endsWith('/post-to-accounting/')) {
      posts.push({ body: JSON.parse(route.request().postData() || '{}') });
      return json({ journal_id: 777, message: 'تم الترحيل بنجاح' });
    }
    if (/\/logistics\/purchase-invoices\/44\/$/.test(url.pathname)) return json(DRAFT_INVOICE);
    if (url.pathname.includes('/inventory/products/')) return json(LOOKUP);
    return json([]);
  });
  await page.goto('/purchase-invoices/44');
  await expect(page.getByText('INV-0044').first()).toBeVisible({ timeout: 20000 });
  return { posts };
};

test('منتقي البنود يجد الصنف برقم مورّده، ويُظهر الرقم الذي طابق', async ({ page }) => {
  await openDraftInvoice(page, true);

  // المسودّة تُفتح للعرض؛ «تحرير» يفتح الشبكة ومعها منتقي الأصناف.
  await page.getByRole('button', { name: /تحرير/ }).first().click();

  // فتح فهرس الأصناف من زرّ خليّة «رقم الصنف» في شبكة البنود.
  await page.getByTitle('فهرس الأصناف الكامل (+)').first().click();
  // النطاق نافذة «إضافة صنف» وحدها — شجرة الأصناف في الشريط الجانبي تسرد
  // الكتالوج كلّه، فمطابقةٌ على الصفحة كلّها تقيس الشجرة لا المنتقي.
  const picker = page.locator('div.fixed.inset-0').filter({ hasText: 'إضافة صنف' });
  await picker.getByPlaceholder(/بحث|ابحث/).first().fill('3068.82');

  // الصنف الصحيح ظهر، والذي لا يحمل الرقم اختفى.
  await expect(picker.getByText('إطار 205/55').first()).toBeVisible();
  await expect(picker.getByText('إطار 225/45')).toHaveCount(0);
  // ويُعرض الرقم كي يعرف المستخدم لماذا طابق.
  await expect(picker.getByText(/3068\.82/).first()).toBeVisible();
});

test('الترحيل يسأل عن الاستلام، والجواب يصل الخادم في جسم الطلب', async ({ page }) => {
  // الإعداد العام مطفأ ⇒ المربّع يبدأ فارغاً، والمستخدم يفعّله لهذه الفاتورة.
  const { posts } = await openDraftInvoice(page, false);

  await page.getByRole('button', { name: /^ترحيل/ }).first().click();

  const box = page.getByRole('checkbox');
  await expect(box).toBeVisible();
  await expect(box).not.toBeChecked();
  await box.check();
  await page.getByRole('button', { name: 'ترحيل', exact: true }).last().click();

  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].body).toEqual({ receive_on_post: true });
});
