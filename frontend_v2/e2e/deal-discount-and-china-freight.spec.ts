/**
 * الخصم و«شحن داخل الصين» في محرّر الصفقة — نقطتا كتابة كانتا مفقودتين.
 *
 * المعادلة (ج8) موجودة في الطرفين منذ البداية: إجمالي الصفقة =
 * بضاعة − خصم + شحن داخل الصين، خادمياً في
 * `_apply_lines_subtotal_and_grand_total` وواجهةً في `recalculateTotals`.
 * لكن refactor سابق أسقط `onUpdateFinancial` مع `ItemsTableSection`، فبقي
 * الحقلان يُقرآن في ستة مواضع بلا نقطة كتابة واحدة — أي صفراً أبداً.
 *
 * الاختبار يثبّت **وجود نقطة الكتابة وأثرها على الإجمالي**، لا شكل الحقل:
 * لو أُعيد الرصيف عرضاً محضاً مرةً أخرى سقط هذا الاختبار فوراً.
 *
 * الخادم مُقنَّع بالكامل — الحساب واجهيّ خالص في هذا المسار (لا حفظ ولا ترحيل).
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** يفتح محرّر صفقة جديدة على خادمٍ مُقنَّع بالكامل. */
const openNewDeal = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('token', 'deal-discount-token');
    localStorage.setItem('userId', 'deal-discount-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/deal-discount-user/')) {
      return json({
        id: 'deal-discount-user', name: 'مختبِر الخصم', role: 'manager',
        email: 'deal-discount@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاختبار', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: true,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: true,
      }]);
    }
    // إلزامي: القناع العام `[]` يجعل `res.permissions` غير معرّفة، فتصير
    // `can()` كاذبةً لكل مفتاح ويردّ `canView` شاشةَ الصفقات إلى لوحة التحكم.
    // والمفتاح `import.deal.manage` بعينه (`utils/viewPermissions.ts`).
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: ['import.deal.manage'],
      });
    }
    if (url.pathname.includes('/mapper/activityStatus/')) {
      return json({ isCurrentlyActive: true });
    }
    return json([]);
  });
  await page.goto('/deals/new');
  await expect(page.getByRole('button', { name: 'إضافة سطر' }))
    .toBeVisible({ timeout: 15000 });
};

const discountInput = (page: Page) => page.getByTestId('deal-discount-input');
const freightInput = (page: Page) => page.getByTestId('deal-china-freight-input');
const grandTotal = (page: Page) =>
  page.locator('.aseel-total-row--grand .aseel-total-value');

/** يضيف بنداً واحداً بكمية وسعر معلومين ⇒ مجموع بنود = 1000. */
const addLineWorth1000 = async (page: Page) => {
  await page.getByRole('button', { name: 'إضافة سطر' }).click();
  await page.locator('#aseel-grid-input-0-quantity').fill('10');
  await page.locator('#aseel-grid-input-0-unitPrice').fill('100');
  await expect(grandTotal(page)).toHaveText('1,000');
};

test('الخصم يُدخَل من رصيف الإجماليات ويخفض إجمالي الصفقة فوراً', async ({ page }) => {
  await openNewDeal(page);
  await addLineWorth1000(page);

  // نقطة الكتابة نفسها — كانت غائبة تماماً قبل الإصلاح.
  await expect(discountInput(page)).toBeVisible();

  await discountInput(page).fill('250');
  await expect(grandTotal(page)).toHaveText('750');

  // والعودة تعكس الأثر — لا اتجاه واحد.
  await discountInput(page).fill('0');
  await expect(grandTotal(page)).toHaveText('1,000');
});

test('الخصم لا يهبط بالإجمالي تحت الصفر مهما كبر', async ({ page }) => {
  await openNewDeal(page);
  await addLineWorth1000(page);

  // نفس الحدّ الخادمي في `_apply_lines_subtotal_and_grand_total` (يقصّ عند الصفر).
  await discountInput(page).fill('4000');
  await expect(grandTotal(page)).toHaveText('0');
});

test('«شحن داخل الصين» يُدخَل ويُضاف بعد الخصم، ويختفي حين تشمله الأسعار', async ({ page }) => {
  await openNewDeal(page);
  await addLineWorth1000(page);

  await discountInput(page).fill('250');
  await freightInput(page).fill('300');
  // بضاعة 1000 − خصم 250 + شحن 300.
  await expect(grandTotal(page)).toHaveText('1,050');

  // المفتاح يُلغي الشحن من الإجمالي بلا مسح القيمة المُدخَلة.
  await page.getByRole('tab', { name: 'بيانات أخرى' }).click();
  await page.getByText('الأسعار تشمل الشحن داخل الصين').click();
  await expect(grandTotal(page)).toHaveText('750');
});
