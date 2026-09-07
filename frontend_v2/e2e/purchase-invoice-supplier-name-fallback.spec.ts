/**
 * القضية #159 — اسمُ المورّد لا يظهر في محرِّر فاتورة الشراء.
 *
 * الخادمُ يُرسل `partner_name` فعلاً، والمُطابِق يضعه في `supplierSnapshot.tradeName`،
 * لكن `SupplierSearch` كان يعرض حصراً `suppliers.find((s) => s.id === selectedSupplierId)`
 * — فإن غاب الشريك عن ردّ `partners/lookup/` (سقف ٥٠٠ صفّ، أو فلتر النوع) ظهرت
 * الخانة فارغة ولو حملت الفاتورة اسماً صحيحاً. الإصلاح: العرض يسقط إلى الاسم
 * الذي تحمله الفاتورة نفسها حين يتعذّر إيجاد الشريك بالمعرِّف.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const DRAFT_INVOICE = {
  id: 44, invoice_number: 'INV-0044', invoice_date: '2026-06-11',
  partner: 4, partner_name: 'مورّد الزجاج النادر النائي',
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

const openDraftInvoice = async (
  page: Page,
  lookupSuppliers: unknown[],
  invoice: typeof DRAFT_INVOICE = DRAFT_INVOICE,
) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'supname-token');
    localStorage.setItem('userId', 'supname-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/supname-user/')) {
      return json({
        id: 'supname-user', name: 'مختبِر الأسماء', role: 'manager',
        email: 'supname@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الزجاج', SubscriptionPlan: 'basic',
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
        receive_on_post: false,
        receipt_doc_label: 'إرسالية شراء',
        standalone_receipt_label: 'سند استلام',
        allow_standalone_receipt: true, allow_edit_receipt: true,
        serial_entry_mode: 'off',
      });
    }
    if (/\/logistics\/purchase-invoices\/44\/$/.test(url.pathname)) return json(invoice);
    if (url.pathname.includes('/partners/lookup')) return json(lookupSuppliers);
    return json([]);
  });
  await page.goto('/purchase-invoices/44');
  await expect(page.getByText('INV-0044').first()).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: /تحرير/ }).first().click();
};

test('اسم المورّد الذي تحمله الفاتورة يظهر في المحرِّر ولو غاب عن partners/lookup', async ({ page }) => {
  // ردّ الخادم لا يحمل هذا المورّد إطلاقاً — تماماً كسقف الـ٥٠٠ صفّ أو فلتر النوع.
  await openDraftInvoice(page, []);

  await expect(page.getByText('مورّد الزجاج النادر النائي').first()).toBeVisible();
  // ولا يسقط إلى مربّع بحثٍ فارغ — الاسم معروضٌ لا مطلوبٌ اختياره من جديد.
  await expect(page.getByPlaceholder('ابحث عن مورد...')).toHaveCount(0);
});

test('الحالة العادية: الشريك موجود في القائمة فيُعرض اسمه من هناك كما كان', async ({ page }) => {
  await openDraftInvoice(page, [
    { id: 4, name: 'مورّد الزجاج المعتاد', partner_type: 'Supplier' },
  ]);

  await expect(page.getByText('مورّد الزجاج المعتاد').first()).toBeVisible();
  // اسم الفاتورة الاحتياطي لا يظهر — المصفوفة كانت كافيةً وحدها.
  await expect(page.getByText('مورّد الزجاج النادر النائي')).toHaveCount(0);
});

test('الاسمُ الاحتياطي هو partner_name (عبر supplierSnapshot.tradeName) لا factory_name حين يختلفان', async ({ page }) => {
  // `factory_name` حقلٌ خادميٌّ مستقلٌّ عن `partner_name` — القضيةُ تنصّ أن يتبع
  // العرضُ الاحتياطي ترتيب `InvoiceList`/`InvoicePrintView` (partner_name أولاً)
  // لا ترتيب `headerSupplierName` في الرأس الذي يقدّم `factoryName`.
  await openDraftInvoice(page, [], {
    ...DRAFT_INVOICE,
    factory_name: 'اسم مصنعٍ آخر تماماً',
  } as typeof DRAFT_INVOICE & { factory_name: string });

  await expect(page.getByText('مورّد الزجاج النادر النائي').first()).toBeVisible();
  await expect(page.getByText('اسم مصنعٍ آخر تماماً')).toHaveCount(0);
});
