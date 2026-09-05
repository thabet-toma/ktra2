/**
 * ISSUE #131 — «عروض وطلبيات دولية»: قبل هذه التذكرة كان الشريط الجانبي يعرض
 * «العروض والطلبيات» **مرّتين** بنصٍّ متطابق — مرّة تحت المشتريات ومرّة تحت
 * الاستيراد — فلا يميّز الناظر أيَّهما يفتح. بند الاستيراد وحده يتغيّر إلى
 * «عروض وطلبيات دولية»؛ بند الشراء المحلي يبقى «العروض والطلبيات» بلا مساس.
 * لا مسّ لمفتاح الشاشة `import-offers`/`price-offers` ولا لمسار الصلاحية
 * `import.deal.manage` — الاسم المعروض فقط تغيّر.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const mockAppWithImportEnabled = async (page: Page, userId: string) => {
  await page.addInitScript((id) => {
    localStorage.setItem('token', 'sidebar-import-token');
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
        id: userId, name: 'مختبِر الاستيراد', role: 'manager',
        email: 'sidebar-import@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      // import_enabled + role=manager: يفتحان `canAccessImport` (CompanyContext)
      // بصرف النظر عن أعلام الصلاحية الدقيقة — راجع contexts/CompanyContext.tsx.
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة استيراد الاختبار', SubscriptionPlan: 'pro',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: true,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: true,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true,
        modules: { import: true },
        ui_mode: 'advanced',
        permissions: [
          'purchase.invoice.view', 'import.deal.manage',
        ],
      });
    }
    if (url.pathname.endsWith('/health/')) {
      return route.fulfill({ status: 200, contentType: 'text/plain', body: 'OK' });
    }
    return json([]);
  });
};

test('بندا العروض والطلبيات مختلفان نصّياً حين تكون صلاحية الاستيراد مفعّلة', async ({ page }) => {
  await mockAppWithImportEnabled(page, 'sidebar-import-user');
  // شاشةٌ بسيطة بعيدة عن كلا القسمين (لا Dashboard تلافياً لتعقيد حمولته) —
  // القسمان يبقيان مطويّين افتراضياً فيُفتَحان يدوياً أدناه.
  await page.goto('/sales/invoices');
  await page.locator('main.app-content').waitFor({ state: 'visible', timeout: 15_000 });

  const sidebar = page.locator('aside.ktra-sidebar:visible').first();

  // القسمان («المشتريات» و«الاستيراد») مطويّان افتراضياً ما دامت الشاشة النشطة
  // خارجهما — يجب فتحهما قبل أن تظهر بنودهما.
  await sidebar.getByRole('button', { name: 'المشتريات', exact: true }).click();
  await sidebar.getByRole('button', { name: 'الاستيراد', exact: true }).click();

  // بند الشراء المحلي يبقى كما كان — بلا مساس.
  await expect(sidebar.getByText('العروض والطلبيات', { exact: true })).toBeVisible();

  // بند الاستيراد صار نصّاً مختلفاً — لا يتكرّر نصّ «العروض والطلبيات» على الشاشة.
  await expect(sidebar.getByText('عروض وطلبيات دولية', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('العروض والطلبيات', { exact: true })).toHaveCount(1);

  // حارس ارتداد: مفتاح الشاشة `import-offers` نفسه ما زال يفتح نفس المسار —
  // لو تغيّر المفتاح أو المسار لَفشل هذا النقر بصمت (Dashboard تبقى ظاهرة).
  await sidebar.getByText('عروض وطلبيات دولية', { exact: true }).click();
  await expect.poll(() => new URL(page.url()).pathname).toBe('/import-offers');
});
