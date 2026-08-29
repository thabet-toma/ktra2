/**
 * T-PAYFULL/M5 — إرسالية البيع تُفتح مملوءة، مرآةُ إرسالية الشراء.
 *
 * نفس العطل كان على الجانبين: `pickInvoice` يجلب `delivery-lines` كاملةً ثم
 * `setFormLines([])`، فيرى المستخدم جدولاً فارغاً ويبني الإرسالية سطراً سطراً
 * والبنود بيد الشاشة أصلاً.
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react`) — فمرور المتصفح هو الدليل.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** بندان لهما باقٍ، وثالثٌ سُلّم بالكامل فلا يدخل إرساليةً جديدة. */
const DELIVERY_LINES = {
  invoice_number: 'SI-0044',
  delivery_status: 'partially_delivered',
  delivery_status_display: 'مسلَّمة جزئياً',
  stock_on_post: false,
  lines: [
    {
      line_id: 11, product: 71, product_name: 'إطار 205/55',
      quantity: '100.0000', delivered_quantity: '40.0000',
      remaining_quantity: '60.0000',
    },
    {
      line_id: 12, product: 72, product_name: 'إطار 225/45',
      quantity: '25.0000', delivered_quantity: '0.0000',
      remaining_quantity: '25.0000',
    },
    {
      line_id: 13, product: 73, product_name: 'إطار 195/65',
      quantity: '10.0000', delivered_quantity: '10.0000',
      remaining_quantity: '0.0000',
    },
  ],
};

const openDeliveryEditor = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'dlvfill-token');
    localStorage.setItem('userId', 'dlvfill-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/dlvfill-user/')) {
      return json({
        id: 'dlvfill-user', name: 'مختبِر التسليم', role: 'manager',
        email: 'dlvfill@example.test', employmentStatus: 'active',
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
        permissions: ['sales.invoice.view', 'sales.invoice.create'],
      });
    }
    if (/\/sales\/invoices\/44\/delivery-lines\/$/.test(url.pathname)) {
      return json(DELIVERY_LINES);
    }
    if (url.pathname.endsWith('/sales/settings/')) {
      return json({
        delivery_doc_label: 'إرسالية بيع',
        standalone_delivery_label: 'سند تسليم',
        allow_standalone_delivery: true,
        allow_edit_delivery: true,
      });
    }
    if (url.pathname.endsWith('/inventory/warehouses/')) {
      return json([
        { id: 5, name: 'المستودع الرئيسي', is_default: true, is_active: true },
        { id: 6, name: 'مستودع الفرع', is_default: false, is_active: true },
      ]);
    }
    if (url.pathname.endsWith('/sales/delivery-notes/')) return json([]);
    return json([]);
  });
  await page.goto('/sales/delivery-notes/new?invoice=44');
  // شريط حالة المحرّر يحمل حالة التسليم فور ربط الفاتورة.
  await expect(page.getByText('مسلَّمة جزئياً').first()).toBeVisible({ timeout: 20000 });
};

/* اسم البند وكمّيته داخل `input` لا نصّاً — المطابقة بالقيمة لا بـ`hasText`. */
const rows = (page: Page) => page.locator('table.ktra-grid[data-variant="items"] tbody tr');
const productOf = (page: Page, i: number) =>
  rows(page).nth(i).locator('input[role="combobox"]');
const qtyOf = (page: Page, i: number) =>
  rows(page).nth(i).locator('input[inputmode="decimal"]');

test('إرسالية البيع تُفتح مملوءة بكل المتبقّي — والمسلَّم بالكامل لا يدخلها', async ({ page }) => {
  await openDeliveryEditor(page);

  await expect(rows(page)).toHaveCount(2);
  await expect(productOf(page, 0)).toHaveValue('إطار 205/55');
  await expect(qtyOf(page, 0)).toHaveValue('60');
  await expect(productOf(page, 1)).toHaveValue('إطار 225/45');
  await expect(qtyOf(page, 1)).toHaveValue('25');
  await expect(rows(page).nth(0).locator('select')).toHaveValue('5');
});

test('حذف صفٍّ يبقى محذوفاً، و«تسليم الكل» يعيد بناء البنود بعد التأكيد', async ({ page }) => {
  await openDeliveryEditor(page);
  await expect(rows(page)).toHaveCount(2);

  await rows(page).nth(1).getByTitle('حذف السطر').click();
  await expect(rows(page)).toHaveCount(1);

  await page.getByTestId('delivery-fill-all').click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'تسليم الكل' }).click();
  await expect(rows(page)).toHaveCount(2);
  await expect(productOf(page, 1)).toHaveValue('إطار 225/45');
});
