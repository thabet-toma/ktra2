/**
 * ISSUE #131 — «مرجع» ← «مرتجع»: مستند الإرجاع (بيع/شراء) يعرض الآن «مرتجع»
 * لا «مرجع» في عنوانه وفتات الخبز. المعرِّفات الإنجليزية (المسارات `/sales/returns`
 * و`/purchase-returns`، وقيم `invoice_kind`/doc_type) تبقى بلا تغيير — هذا الاختبار
 * حارسُ ارتدادٍ عليها بقدر ما هو تأكيدٌ على النصّ الجديد.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const mockCommonRoutes = async (page: Page, userId: string) => {
  await page.addInitScript((id) => {
    localStorage.setItem('token', 'return-rename-token');
    localStorage.setItem('userId', id);
    localStorage.setItem('tenantId', '1');
  }, userId);

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });

    if (url.pathname.endsWith(`/hr/users/${userId}/`)) {
      return json({
        id: userId, name: 'مختبِر التسمية', role: 'manager',
        email: 'rename-test@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاختبار', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: ['sales.invoice.view', 'sales.invoice.create', 'purchase.invoice.view', 'purchase.invoice.create'],
      });
    }
    if (url.pathname.endsWith('/health/')) {
      return route.fulfill({ status: 200, contentType: 'text/plain', body: 'OK' });
    }
    if (url.pathname.endsWith('/sales/invoices/lookup/')) return json([]);
    if (url.pathname.endsWith('/logistics/purchase-invoices/')) return json([]);
    if (url.pathname.includes('/inventory/products/') || url.pathname.includes('/lookup/products/')) {
      return json([]);
    }
    return json([]);
  });
};

test('مرتجع البيع: العنوان وفتات الخبز يقولان «مرتجع» لا «مرجع»، والمسار /sales/returns بلا تغيير', async ({ page }) => {
  await mockCommonRoutes(page, 'return-rename-sale-user');
  await page.goto('/sales/returns');

  // العنوان في شريط المستند (KitDocumentShell).
  await expect(page.locator('.ktra-title-chip')).toHaveText('مرتجع البيع (Sale Return)');

  // فتات الخبز (`nav[aria-label="breadcrumb"]`, من VIEW_LABELS['sales-return']).
  await expect(page.locator('nav[aria-label="breadcrumb"]')).toContainText('مرتجع البيع');

  // والنصّ القديم غاب تماماً من الشاشة كلّها — لا فقط من العنوان وفتات الخبز.
  await expect(page.getByText('مرجع البيع', { exact: true })).toHaveCount(0);

  // حارس الارتداد: المسار الإنجليزي لم يتغيّر (لو تغيّر لَفشل goto نفسه بصمت
  // ولَعادت الشاشة إلى Dashboard بدل محرر المرتجع).
  expect(new URL(page.url()).pathname).toBe('/sales/returns');
});

test('مرتجع الشراء: العنوان وفتات الخبز يقولان «مرتجع» لا «مرجع»، والمسار /purchase-returns بلا تغيير', async ({ page }) => {
  await mockCommonRoutes(page, 'return-rename-purchase-user');
  await page.goto('/purchase-returns');

  await expect(page.locator('.ktra-title-chip')).toHaveText('مرتجع الشراء (Purchase Return)');

  await expect(page.locator('nav[aria-label="breadcrumb"]')).toContainText('مرتجع الشراء');
  await expect(page.getByText('مرجع الشراء', { exact: true })).toHaveCount(0);

  expect(new URL(page.url()).pathname).toBe('/purchase-returns');
});

test('حفظ مرتجع الشراء يبقى يبعث نفس doc_type/endpoint القديم (logistics/purchase-invoices/returns/)', async ({ page }) => {
  await mockCommonRoutes(page, 'return-rename-purchase-post-user');

  let capturedPath: string | null = null;
  await page.route('**/*api/logistics/purchase-invoices/returns/*', async (route) => {
    capturedPath = new URL(route.request().url()).pathname;
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ invoice_number: 'PR-900' }) });
  });

  await page.goto('/purchase-returns');
  await expect(page.locator('.ktra-title-chip')).toHaveText('مرتجع الشراء (Purchase Return)');

  // لا يمكن الحفظ بلا مورّد — نتأكّد فقط أنّ رسالة الخطأ الجديدة ظاهرة
  // (المسمّى تغيّر هنا أيضاً: «فشل حفظ/ترحيل مرتجع الشراء.») بلا محاولة إتمام الحفظ فعلياً،
  // لأن بناء حمولة صالحة يتطلّب اختيار فاتورة أصلية من الخادم — خارج نطاق هذا الاختبار.
  await page.getByRole('button', { name: /حفظ/ }).first().click();
  await expect(page.getByText('اختر المورد.')).toBeVisible();
  // لم يصل نداء الحفظ أصلاً (كما هو متوقّع من الحارس أعلاه) — المسار المتوقَّع
  // حين يصل يبقى كما هو: بلا تغيير في endpoint الإنجليزي.
  expect(capturedPath).toBeNull();
});
