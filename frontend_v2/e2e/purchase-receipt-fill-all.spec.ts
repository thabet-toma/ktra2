/**
 * T-PAYFULL/M1 — الإرسالية تُفتح مملوءة بكامل المتبقّي، لا فاضيةً بنداً بنداً.
 *
 * كان زرّ «استلام» في الفاتورة يفتح `/purchase-receipts/new?invoice=33` ثم
 * يعمل `setFormLines([])` بعد جلب البنود — فيرى المستخدم جدولاً فارغاً ويبني
 * الإرسالية سطراً سطراً حتى حين وصلت الشحنة كاملة (الحالة الغالبة).
 * الآن تُملأ من `receivable-lines` بالكمية المتبقّية لكل بند، وزرّ «استلام
 * الكل» يعيد التعبئة صراحةً بعد أي حذف.
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react` في المشروع) — فمرور المتصفح
 * هو الدليل الوحيد على أن الصفوف تُرسم فعلاً.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** بندان: الأول استُلم منه 550 من 1500 (باقٍ 950)، والثاني لم يصل منه شيء. */
const RECEIVABLE = {
  invoice_number: 'INV-0033',
  partner_name: 'مورّد الإطارات',
  invoice_date: '2026-06-11',
  receipt_status: 'partially_received',
  receipt_status_display: 'مستلمة جزئياً',
  is_local: true,
  is_posted: true,
  lines: [
    {
      item_id: 91, product: 71, product_name: 'إطار 205/55', name: 'إطار 205/55',
      unit_price: '10.0000', quantity: '1500.0000',
      received_quantity: '550.0000', remaining_quantity: '950.0000',
    },
    {
      item_id: 92, product: 72, product_name: 'إطار 225/45', name: 'إطار 225/45',
      unit_price: '10.0000', quantity: '600.0000',
      received_quantity: '0.0000', remaining_quantity: '600.0000',
    },
    // بندٌ استُلم بالكامل — يجب ألّا يظهر في الإرسالية الجديدة.
    {
      item_id: 93, product: 73, product_name: 'إطار 195/65', name: 'إطار 195/65',
      unit_price: '10.0000', quantity: '200.0000',
      received_quantity: '200.0000', remaining_quantity: '0.0000',
    },
  ],
};

const openReceiptEditor = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'fillall-token');
    localStorage.setItem('userId', 'fillall-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/fillall-user/')) {
      return json({
        id: 'fillall-user', name: 'مختبِر الاستلام', role: 'manager',
        email: 'fillall@example.test', employmentStatus: 'active',
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
          'purchase.invoice.receive',
        ],
      });
    }
    if (/\/purchase-invoices\/33\/receivable-lines\/$/.test(url.pathname)) {
      return json(RECEIVABLE);
    }
    if (url.pathname.endsWith('/logistics/purchase-settings/current/')) {
      return json({
        receipt_doc_label: 'إرسالية شراء',
        standalone_receipt_label: 'سند استلام',
        allow_standalone_receipt: true,
        allow_edit_receipt: true,
        receive_on_post: true,
      });
    }
    if (url.pathname.endsWith('/inventory/warehouses/')) {
      return json([
        { id: 5, name: 'المستودع الرئيسي', is_default: true, is_active: true },
        { id: 6, name: 'مستودع الفرع', is_default: false, is_active: true },
      ]);
    }
    if (url.pathname.endsWith('/logistics/goods-receipts/')) return json([]);
    if (url.pathname.endsWith('/logistics/purchase-invoices/')) {
      return json({ count: 0, results: [] });
    }
    return json([]);
  });
  await page.goto('/purchase-receipts/new?invoice=33');
  // شريط حالة المحرّر يحمل «المورد · حالة الاستلام» فور ربط الفاتورة.
  // (رقم الفاتورة نفسه في `input` — لا يُلتقط بـ`getByText`.)
  await expect(page.getByText('مورّد الإطارات').first()).toBeVisible({ timeout: 20000 });
};

/* اسم البند وكمّيته داخل `input` لا نصّاً — فالمطابقة بالقيمة لا بـ`hasText`. */
const rows = (page: Page) => page.locator('table.ktra-grid[data-variant="items"] tbody tr');
const productOf = (page: Page, i: number) =>
  rows(page).nth(i).locator('input[role="combobox"]');
const qtyOf = (page: Page, i: number) =>
  rows(page).nth(i).locator('input[inputmode="decimal"]');

test('الإرسالية تُفتح مملوءة بكل المتبقّي — والمستلَم بالكامل لا يدخلها', async ({ page }) => {
  await openReceiptEditor(page);

  // بندان لهما باقٍ ⇒ صفّان جاهزان بكمياتهما المتبقّية، والثالث (المستلَم
  // بالكامل) لا يُقحَم في إرسالية جديدة.
  await expect(rows(page)).toHaveCount(2);
  await expect(productOf(page, 0)).toHaveValue('إطار 205/55');
  await expect(qtyOf(page, 0)).toHaveValue('950');
  await expect(productOf(page, 1)).toHaveValue('إطار 225/45');
  await expect(qtyOf(page, 1)).toHaveValue('600');

  // والمستودع الافتراضي مُسنَد — لا صفٌّ يُرفض عند الحفظ لغياب مستودعه.
  await expect(rows(page).nth(0).locator('select')).toHaveValue('5');
  await expect(rows(page).nth(1).locator('select')).toHaveValue('5');

  await page.screenshot({
    path: 'e2e/receipt-remaining-shots/receipt-prefilled-from-invoice.png',
    fullPage: true,
  });
});

test('حذف صفٍّ يبقى محذوفاً، و«استلام الكل» يعيد بناء البنود بعد التأكيد', async ({ page }) => {
  await openReceiptEditor(page);
  await expect(rows(page)).toHaveCount(2);

  await rows(page).nth(1).getByTitle('حذف السطر').click();
  // لا effect يعيد تعبئته من خلف المستخدم.
  await expect(rows(page)).toHaveCount(1);
  await expect(productOf(page, 0)).toHaveValue('إطار 205/55');

  // «استلام الكل» صريحٌ: يؤكّد الاستبدال ثم يعيد الصفّين معاً.
  await page.getByTestId('receipt-fill-all').click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'استلام الكل' }).click();
  await expect(rows(page)).toHaveCount(2);
  await expect(productOf(page, 1)).toHaveValue('إطار 225/45');
});
