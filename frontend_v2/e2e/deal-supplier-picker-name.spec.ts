/**
 * منتقي المورد في محرّر الصفقة — الاسم العربي كان يُبتلَع، والنطاق لم يكن يُمرَّر.
 *
 * `_mapPartnerToSupplier` كان يكتب `tradeName = legal_name || name`، فكلما وُجد
 * اسم قانوني صار `tradeName === alias` وسقط `name` من كائن `Supplier` كلياً:
 * المورد يُعرض باسمه الأجنبي، والبحث بالعربية يُرجع صفراً لأن المُرشِّح كان
 * يطابق سلسلتين متطابقتين. ومحرّر الصفقة كان يطلب كل الموردين بلا نطاق فيعرض
 * المحليين في شاشة استيراد.
 *
 * الخادم مُقنَّع بالكامل، والقناع يُحاكي فلترة `PartnerViewSet.get_queryset`:
 * النطاق المطلوب + غير المصنَّفين (`supplier_scope=''`).
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

/** مورد دولي أُدخل بعُرف المحرّر الجديد: الاسم عربي والقانوني أجنبي. */
const TV_SUPPLIER = {
  id: 304, name: 'مورد تلفزيونات', partner_type: 'Supplier',
  legal_name: 'Guangzhou Yitai Electronics Co., Ltd.', supplier_scope: 'international',
};
/** مورد قديم أُدخل بالعكس: الاسم أجنبي واللقب العربي في `legal_name`. */
const LEGACY_SUPPLIER = {
  id: 305, name: 'Chengdu Sunrise Electric', partner_type: 'Supplier',
  legal_name: 'مورد الانفيرتر الاخضر', supplier_scope: '',
};
/** مورد محلي — لا محلّ له في شاشة الاستيراد. */
const LOCAL_SUPPLIER = {
  id: 306, name: 'مورد البطاريات المحلي', partner_type: 'Supplier',
  legal_name: '', supplier_scope: 'local',
};

/** يفتح محرّر صفقة جديدة على خادمٍ مُقنَّع، ويعيد عناوين طلبات الموردين. */
const openNewDeal = async (page: Page) => {
  const lookupUrls: string[] = [];
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('token', 'deal-supplier-token');
    localStorage.setItem('userId', 'deal-supplier-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/deal-supplier-user/')) {
      return json({
        id: 'deal-supplier-user', name: 'مختبِر الموردين', role: 'manager',
        email: 'deal-supplier@example.test', employmentStatus: 'active',
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
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: ['import.deal.manage'],
      });
    }
    if (url.pathname.includes('/mapper/activityStatus/')) {
      return json({ isCurrentlyActive: true });
    }
    if (url.pathname.includes('/partners/lookup')) {
      lookupUrls.push(url.search);
      const scope = url.searchParams.get('supplier_scope') || '';
      const rows = [TV_SUPPLIER, LEGACY_SUPPLIER, LOCAL_SUPPLIER].filter(
        (p) => !scope || p.supplier_scope === scope || p.supplier_scope === '',
      );
      return json(rows);
    }
    return json([]);
  });
  await page.goto('/deals/new');
  await expect(page.getByRole('button', { name: 'إضافة سطر' }))
    .toBeVisible({ timeout: 15000 });
  return lookupUrls;
};

const supplierBox = (page: Page) => page.getByPlaceholder('ابحث عن مورد...');

test('البحث بالاسم العربي يجد المورد ولو كان له اسم قانوني أجنبي', async ({ page }) => {
  await openNewDeal(page);

  await supplierBox(page).fill('مورد تلفزيونات');
  // كان يُرجع «لا توجد نتائج»: الاسم العربي لم يكن يصل إلى كائن المورد أصلاً.
  await expect(page.getByText('مورد تلفزيونات', { exact: true })).toBeVisible();
  await expect(page.getByText('لا توجد نتائج')).toHaveCount(0);
});

test('اللقب العربي يبقى بارزاً واسم المصنع سطراً فرعياً — لا نسخة مكرّرة', async ({ page }) => {
  await openNewDeal(page);

  await supplierBox(page).fill('الانفيرتر');
  const row = page.locator('li', { hasText: 'مورد الانفيرتر الاخضر' });
  await expect(row).toBeVisible();
  // الاسمان مستقلان: اللقب معروضاً والاسم الرسمي تحته.
  await expect(row.getByText('Chengdu Sunrise Electric')).toBeVisible();

  // والبحث بالاسم الرسمي يجده أيضاً — الحقلان مقروءان معاً.
  await supplierBox(page).fill('Chengdu');
  await expect(page.locator('li', { hasText: 'مورد الانفيرتر الاخضر' })).toBeVisible();
});

test('شاشة الصفقة تطلب الموردين الدوليين وحدهم فلا يظهر مورد محلي', async ({ page }) => {
  const lookupUrls = await openNewDeal(page);

  expect(lookupUrls.some((s) => s.includes('supplier_scope=international'))).toBe(true);
  expect(lookupUrls.some((s) => s.includes('supplier_scope=local'))).toBe(false);

  await supplierBox(page).fill('مورد');
  await expect(page.getByText('مورد تلفزيونات', { exact: true })).toBeVisible();
  await expect(page.getByText('مورد البطاريات المحلي')).toHaveCount(0);
});
