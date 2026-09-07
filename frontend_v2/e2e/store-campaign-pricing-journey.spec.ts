import { expect, test, type Page } from '@playwright/test';

/**
 * THA-166 م٥ (تصحيحٌ بعد المراجعة) — الفجوة: نموذج الحملة في `StoreSettingsPage.tsx`
 * لم يكن يعرض `discount_percent`/`starts_at`/`ends_at` إطلاقاً، فلا أحد يقدر أن يُدخل
 * نسبة خصم رغم أن كل منطق الاشتقاق والقياس مبنيٌّ حولها منذ المراحل ٢ و٤ و٥.
 * وبطاقة المنتج في المتجر العام (`StoreProductCard.tsx`) لم تكن تعرض `original_price`/
 * `discount_percent` القادمين من العقد العام أصلاً — فحتى لو أُدخلت نسبة خصم، لا شيء
 * يُظهرها للزائر.
 *
 * هذا الاختبار يُثبت السلسلة كاملةً: إنشاء حملةٍ بخصمٍ ونافذةٍ سارية من لوحة الإدارة
 * ← ظهورُ المنتج في المتجر العام بسعرٍ مخفَّضٍ و`original_price` غير فارغ.
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react`) — فمرور المتصفح هو الدليل.
 * السابقة المُحتذاة: `frontend_v2/e2e/store-catalog-publish-journey.spec.ts`.
 */

const SLUG = 'pricing-journey-shop';
const CAMPAIGN_TITLE = 'حملة الخصم — اختبار السلسلة';
const PRODUCT_NAME = 'سمّاعة لاسلكية — اختبار سلسلة الخصم';

type Posted = { path: string; body: unknown };

async function stubApi(page: Page, posts: Posted[]) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'pricing166-token');
    localStorage.setItem('userId', 'pricing166-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const json = (body: unknown) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    const paged = (results: unknown[]) =>
      json({ count: results.length, next: null, previous: null, results });

    const path = url.pathname;

    // ── تمهيد الجلسة والصلاحيات — المدير يملك `store.pricing` صراحةً ─────
    if (path.endsWith('/hr/users/pricing166-user/')) {
      return json({
        id: 'pricing166-user', name: 'مالكٌ يسعّر حملته', role: 'manager',
        email: 'pricing166@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة سلسلة الخصم', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
          store_slug: SLUG,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (path.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true, modules: {}, ui_mode: 'advanced',
        permissions: ['store.manage', 'store.pricing'],
      });
    }

    // ── لوحة إدارة المتجر ───────────────────────────────────────────────
    if (path.endsWith('/store/admin/brands/')) return paged([]);
    if (path.endsWith('/store/admin/categories/')) return paged([]);
    if (path.endsWith('/store/admin/products/')) return paged([]);

    if (req.method() === 'POST' && path.endsWith('/store/admin/collections/')) {
      const body = JSON.parse(req.postData() || '{}');
      posts.push({ path, body });
      return json({
        id: 701,
        title: body.title ?? '',
        slug: body.slug ?? '',
        description: body.description ?? '',
        banner_image_url: null,
        badge_text: body.badge_text ?? '',
        featured_product: null,
        featured_store_product: null,
        is_active: body.is_active ?? true,
        sort_order: 0,
        discount_percent: body.discount_percent ?? '0',
        starts_at: body.starts_at ?? null,
        ends_at: body.ends_at ?? null,
        priority: body.priority ?? 0,
        items_count: 0,
        views_count: 0,
        orders_count: 0,
        conversion_rate: null,
        created_at: '2026-09-08T00:00:00Z',
      });
    }
    if (path.endsWith('/store/admin/collections/')) return json([]);

    // ── المتجر العام — المنتج يعود بسعرٍ مخفَّضٍ بعد إنشاء الحملة ─────────
    if (path === `/api/store/${SLUG}/`) {
      return json({
        slug: SLUG, name: 'شركة سلسلة الخصم', logo_url: null, phone: null,
        address: null, currency: '₪', show_prices: true,
        catalog_mode_default: 'grid', allow_cart: true,
      });
    }
    if (path === `/api/store/${SLUG}/products/`) {
      return paged([{
        id: 901, name_ar: PRODUCT_NAME, name_en: '', brand: null,
        category_name: '', uom_name: '', price: '80.00', availability: 'available',
        description: '', images: [], original_price: '100.00', discount_percent: 20,
      }]);
    }
    if (path === `/api/store/${SLUG}/collections/`) return paged([]);

    return json([]);
  });
}

test('حملةٌ بخصمٍ ونافذةٍ سارية تُنشأ من اللوحة ← المنتج يظهر في المتجر العام بسعرٍ مخفَّض', async ({ page }) => {
  const posts: Posted[] = [];
  await stubApi(page, posts);

  await page.goto('/store-settings');
  await expect(page.getByText('إدارة وتخصيص المتجر الإلكتروني')).toBeVisible({ timeout: 20000 });

  await page.getByRole('button', { name: 'المجموعات والحملات الإعلانية' }).click();
  await page.getByRole('button', { name: 'إنشاء حملة جديدة' }).click();

  await page.getByPlaceholder('مثال: عروض العيد الحصرية').fill(CAMPAIGN_TITLE);
  // الحقل يُعبَّأ تلقائياً من العنوان — نتحقق أنه لم يبق فارغاً بدل الاعتماد على نصّه.
  await expect(page.getByPlaceholder('eid-offers')).not.toHaveValue('');

  // نسبةُ الخصم — الحقل الذي كان مفقوداً كلياً قبل هذا التصحيح.
  const discountInput = page.getByPlaceholder('مثال: 20 لخصمٍ ٢٠٪ — نسبةٌ لا مبلغٌ مطلق');
  await expect(discountInput).toBeEnabled();
  await discountInput.fill('20');

  // تواريخ السريان تُترك فارغة عمداً — «بلا بداية = سارية منذ الآن، بلا نهاية = بلا انتهاء».
  await expect(page.getByText('فارغةٌ = سارية منذ الآن (بلا بداية)')).toBeVisible();
  await expect(page.getByText('فارغةٌ = بلا انتهاء')).toBeVisible();

  await page.getByRole('button', { name: 'حفظ الحملة' }).click();

  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].body).toMatchObject({
    title: CAMPAIGN_TITLE,
    discount_percent: '20',
    starts_at: null,
    ends_at: null,
  });

  // الرحلة الحقيقية: الزائر يفتح المتجر العام فيرى المنتج مخفَّضاً — لا فرضية.
  await page.goto(`/store/${SLUG}`);
  await expect(page.getByText(PRODUCT_NAME).first()).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('خصم 20٪')).toBeVisible();
  await expect(page.getByText('80', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('100', { exact: false }).first()).toBeVisible();
});

test('من لا يملك `store.pricing` يرى حقول التسعير معطّلة، ويقدر مع ذلك أن يبني الحملة', async ({ page }) => {
  const posts: Posted[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'pricing166-token-2');
    localStorage.setItem('userId', 'pricing166-user-2');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    const paged = (results: unknown[]) =>
      json({ count: results.length, next: null, previous: null, results });
    const path = url.pathname;

    if (path.endsWith('/hr/users/pricing166-user-2/')) {
      return json({
        id: 'pricing166-user-2', name: 'مسوّقٌ بلا تسعير', role: 'staff',
        email: 'marketer166@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة سلسلة الخصم', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
          store_slug: SLUG,
        },
        role: 'staff', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (path.endsWith('/permissions/me/')) {
      // `store.manage` وحدها — بلا `store.pricing`.
      return json({
        role: 'staff', is_manager: false, modules: {}, ui_mode: 'advanced',
        permissions: ['store.manage'],
      });
    }
    if (path.endsWith('/store/admin/brands/')) return paged([]);
    if (path.endsWith('/store/admin/categories/')) return paged([]);
    if (path.endsWith('/store/admin/products/')) return paged([]);
    if (req.method() === 'POST' && path.endsWith('/store/admin/collections/')) {
      const body = JSON.parse(req.postData() || '{}');
      posts.push({ path, body });
      return json({
        id: 702, title: body.title ?? '', slug: body.slug ?? '', description: '',
        banner_image_url: null, badge_text: '', featured_product: null,
        featured_store_product: null, is_active: true, sort_order: 0,
        discount_percent: '0', starts_at: null, ends_at: null, priority: 0,
        items_count: 0, views_count: 0, orders_count: 0, conversion_rate: null,
        created_at: '2026-09-08T00:00:00Z',
      });
    }
    if (path.endsWith('/store/admin/collections/')) return json([]);
    return json([]);
  });

  await page.goto('/store-settings');
  await expect(page.getByText('إدارة وتخصيص المتجر الإلكتروني')).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: 'المجموعات والحملات الإعلانية' }).click();
  await page.getByRole('button', { name: 'إنشاء حملة جديدة' }).click();

  await expect(
    page.getByText('لا تملك صلاحية «التسعير في المتجر العام»'),
  ).toBeVisible();

  const discountInput = page.getByPlaceholder('مثال: 20 لخصمٍ ٢٠٪ — نسبةٌ لا مبلغٌ مطلق');
  await expect(discountInput).toBeDisabled();

  await page.getByPlaceholder('مثال: عروض العيد الحصرية').fill('حملة بلا خصم');
  await page.getByRole('button', { name: 'حفظ الحملة' }).click();

  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].body).toMatchObject({ title: 'حملة بلا خصم', discount_percent: '0' });
});
