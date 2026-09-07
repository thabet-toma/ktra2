import { expect, test, type Page } from '@playwright/test';

/**
 * THA-166 م٦ — كتلُ الصفحة الرئيسية: رحلةٌ حقيقية من لوحة الإدارة إلى
 * الصفحة الرئيسية العامة. `tsc` لا يفحص خصائص JSX هنا (لا `@types/react`)
 * — فمرور المتصفح هو الدليل (نفس نمط `store-catalog-publish-journey.spec.ts`).
 */

const SLUG = 'home-blocks-shop';
const BLOCK_TITLE = 'تخفيضات الصيف — اختبار الكتل';

type Posted = { path: string; body: unknown };

async function stubApi(page: Page, posts: Posted[]) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'home166-token');
    localStorage.setItem('userId', 'home166-user');
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

    // ── تمهيد الجلسة والصلاحيات ────────────────────────────────────────
    if (path.endsWith('/hr/users/home166-user/')) {
      return json({
        id: 'home166-user', name: 'تاجرٌ يختبر الكتل', role: 'manager',
        email: 'home166@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة كتل الصفحة', SubscriptionPlan: 'Enterprise',
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
        permissions: ['store.manage'],
      });
    }

    // ── لوحة إدارة المتجر ───────────────────────────────────────────────
    if (path.endsWith('/store/admin/brands/')) return paged([]);
    if (path.endsWith('/store/admin/categories/')) return paged([]);
    if (path.endsWith('/store/admin/collections/')) return json([]);

    if (req.method() === 'POST' && path.endsWith('/store/admin/home-blocks/')) {
      const body = JSON.parse(req.postData() || '{}');
      posts.push({ path, body });
      return json({
        id: 901,
        kind: body.kind ?? 'hero',
        title: body.title ?? '',
        subtitle: body.subtitle ?? '',
        image_url: body.image_url ?? '',
        image_url_mobile: body.image_url_mobile ?? '',
        link_kind: body.link_kind ?? 'none',
        link_id: body.link_id ?? null,
        link_url: body.link_url ?? '',
        source_id: body.source_id ?? null,
        limit: body.limit ?? 12,
        sort_order: body.sort_order ?? 0,
        is_active: body.is_active ?? true,
        created_at: '2026-09-08T00:00:00Z',
        updated_at: '2026-09-08T00:00:00Z',
      });
    }
    if (path.endsWith('/store/admin/home-blocks/')) return paged([]);

    // ── المتجر العام — نفس الكتلة التي أُنشئت من اللوحة يجب أن تظهر هنا ───
    if (path === `/api/store/${SLUG}/`) {
      return json({
        slug: SLUG, name: 'شركة كتل الصفحة', logo_url: null, phone: null,
        address: null, currency: '₪', show_prices: true,
        catalog_mode_default: 'grid', allow_cart: true,
      });
    }
    if (path === `/api/store/${SLUG}/products/`) return paged([]);
    if (path === `/api/store/${SLUG}/collections/`) return paged([]);
    if (path === `/api/store/${SLUG}/home/`) {
      return json({
        blocks: [{
          id: 901, kind: 'hero', title: BLOCK_TITLE, subtitle: '',
          image_url: null, image_url_mobile: null,
          link: { kind: 'none', target: null, url: null },
          products: [], campaigns: [],
        }],
      });
    }

    return json([]);
  });
}

test('كتلةٌ تُنشأ من لوحة إدارة المتجر فتظهر في الصفحة الرئيسية العامة', async ({ page }) => {
  const posts: Posted[] = [];
  await stubApi(page, posts);

  await page.goto('/store-settings');
  await expect(page.getByText('إدارة وتخصيص المتجر الإلكتروني')).toBeVisible({ timeout: 20000 });

  await page.getByRole('button', { name: 'الصفحة الرئيسية' }).click();
  await expect(page.getByText('كتلُ الصفحة الرئيسية')).toBeVisible();
  await expect(page.getByText('0 / 10 كتلٍ مفعَّلة')).toBeVisible();

  await page.getByRole('button', { name: 'إضافة كتلة' }).click();
  await page.getByPlaceholder('مثال: تخفيضات الصيف').fill(BLOCK_TITLE);
  await page.getByRole('button', { name: 'حفظ الكتلة' }).click();

  // الطلب وصل الخادم على `/api/store/admin/home-blocks/` بنوعٍ افتراضيّ «hero».
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].body).toMatchObject({ kind: 'hero', title: BLOCK_TITLE });

  // والكتلة ظهرت في قائمة اللوحة فوراً.
  await expect(page.getByText(BLOCK_TITLE).first()).toBeVisible();

  // الرحلة الحقيقية: نفس الكتلة تظهر الآن في الصفحة الرئيسية العامة.
  await page.goto(`/store/${SLUG}`);
  await expect(page.getByText(BLOCK_TITLE).first()).toBeVisible({ timeout: 20000 });
});

test('متجرٌ بلا كتلٍ يعرض الشبكة الافتراضية بلا أي أثرٍ للميزة الجديدة', async ({ page }) => {
  const posts: Posted[] = [];
  await stubApi(page, posts);

  // نفس الشركة، لكن `/home/` يردّ بلا كتلٍ — قاعدة السقوط (قسم ب).
  await page.route(`**/api/store/${SLUG}/home/`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ blocks: [] }),
    });
  });

  await page.goto(`/store/${SLUG}`);
  await expect(page.getByText('لا توجد منتجات معروضة بعد')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText(BLOCK_TITLE)).toHaveCount(0);
});
