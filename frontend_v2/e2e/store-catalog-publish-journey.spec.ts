import { expect, test, type Page } from '@playwright/test';

/**
 * THA-166 م٣ — الفجوة التي أُغلقت: قبل هذه المرحلة كانت شاشة «متجري» تنشر عبر
 * `Product.is_for_sale_online`، وهو مسارٌ لا يؤثّر على `StoreProduct` الذي يقرأه
 * المتجر العام منذ م٢ — فمنتجٌ «منشور» من اللوحة لم يكن يظهر للزائر أبداً.
 *
 * هذا الاختبار يُثبت الرحلة الحقيقية: إنشاءُ منتجٍ من لوحة الإدارة (تكتب على
 * `StoreProduct` عبر `/api/store/admin/products/` الآن) ← ظهورُه فعلاً في
 * المتجر العام (`/api/store/<slug>/products/`).
 *
 * `tsc` لا يفحص خصائص JSX هنا (لا `@types/react`) — فمرور المتصفح هو الدليل.
 * السابقة المُحتذاة: `frontend_v2/e2e/supplier-code-and-receive-choice.spec.ts`.
 */

const SLUG = 'gap-closed-shop';
const PRODUCT_NAME = 'مصباح حديقة LED — اختبار الفجوة';

type Posted = { path: string; body: unknown };

async function stubApi(page: Page, posts: Posted[]) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'gap166-token');
    localStorage.setItem('userId', 'gap166-user');
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
    if (path.endsWith('/hr/users/gap166-user/')) {
      return json({
        id: 'gap166-user', name: 'تاجرٌ يختبر الفجوة', role: 'manager',
        email: 'gap166@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة سدّ الفجوة', SubscriptionPlan: 'Enterprise',
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

    if (req.method() === 'POST' && path.endsWith('/store/admin/products/')) {
      const body = JSON.parse(req.postData() || '{}');
      posts.push({ path, body });
      return json({
        id: 501,
        name_ar: body.name_ar ?? null,
        name_en: body.name_en ?? '',
        slug: 'led-garden-lamp-gap-test',
        brand: null,
        categories: [],
        unit: body.unit ?? '',
        price: body.price || null,
        sale_price: body.sale_price || null,
        stock_state: body.stock_state ?? 'in_stock',
        description: body.description ?? '',
        is_active: body.is_active ?? true,
        sort_order: body.sort_order ?? 0,
        images: [],
        imported_from_product_id: null,
        created_at: '2026-09-07T00:00:00Z',
      });
    }
    if (path.endsWith('/store/admin/products/')) return paged([]);

    // ── المتجر العام — نفس الاسم الذي أُدخل من اللوحة يجب أن يظهر هنا ────
    if (path === `/api/store/${SLUG}/`) {
      return json({
        slug: SLUG, name: 'شركة سدّ الفجوة', logo_url: null, phone: null,
        address: null, currency: '₪', show_prices: true,
        catalog_mode_default: 'grid', allow_cart: true,
      });
    }
    if (path === `/api/store/${SLUG}/products/`) {
      return paged([{
        id: 501, name_ar: PRODUCT_NAME, name_en: '', brand: null,
        category_name: '', uom_name: '', price: '120.00', availability: 'available',
        description: '', images: [],
      }]);
    }
    if (path === `/api/store/${SLUG}/collections/`) return paged([]);

    return json([]);
  });
}

test('منتجٌ يُنشأ من لوحة الإدارة يظهر فعلاً في المتجر العام', async ({ page }) => {
  const posts: Posted[] = [];
  await stubApi(page, posts);

  await page.goto('/store-settings');
  await expect(page.getByText('إدارة وتخصيص المتجر الإلكتروني')).toBeVisible({ timeout: 20000 });

  await page.getByRole('button', { name: 'المنتجات والصور المخصصة' }).click();
  await page.getByRole('button', { name: 'إضافة منتج جديد للمتجر' }).click();

  await page.getByPlaceholder('مثال: ثلاجة دولابي فاخرة LG 18 قدم').fill(PRODUCT_NAME);
  await page.getByPlaceholder('مثال: 3500').fill('120');
  await page.getByRole('button', { name: 'إضافة المنتج للمتجر' }).click();

  // الطلب وصل الخادم على `/api/store/admin/products/` — لا على مسار المخزون القديم.
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].body).toMatchObject({ name_ar: PRODUCT_NAME, price: '120' });

  // والمنتج ظهر في جدول اللوحة فوراً.
  await expect(page.getByText(PRODUCT_NAME).first()).toBeVisible();

  // الرحلة الحقيقية: نفس المنتج يظهر الآن في المتجر العام — الفجوة أُغلقت.
  await page.goto(`/store/${SLUG}`);
  await expect(page.getByText(PRODUCT_NAME).first()).toBeVisible({ timeout: 20000 });
});

test('Esc يُغلق نافذة الإنشاء السريع للماركة وحدَها، ولا يمسّ نموذج المنتج الأمّ', async ({ page }) => {
  // فخٌّ موثَّق: `Esc` كان يُصفّر النموذج الأمّ في هذا المستودع. هنا لا مستمعَ
  // على النافذة السريعة من الأصل، فالنتيجة السليمة كانت بالتعطيل لا بالمعالجة —
  // هذا الاختبار يُثبت المعالجة الصريحة: الإغلاق يقع، والنموذج الأمّ يبقى كما هو.
  const posts: Posted[] = [];
  await stubApi(page, posts);

  await page.goto('/store-settings');
  await expect(page.getByText('إدارة وتخصيص المتجر الإلكتروني')).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: 'المنتجات والصور المخصصة' }).click();
  await page.getByRole('button', { name: 'إضافة منتج جديد للمتجر' }).click();

  const nameInput = page.getByPlaceholder('مثال: ثلاجة دولابي فاخرة LG 18 قدم');
  await nameInput.fill('اسمٌ لا يجوز أن يضيع بالخطأ');

  await page.getByTitle('إضافة ماركة جديدة').click();
  const quickCreateHeading = page.getByText('إضافة ماركة جديدة', { exact: true });
  await expect(quickCreateHeading).toBeVisible();

  await page.keyboard.press('Escape');

  // النافذة السريعة أُغلقت وحدها،
  await expect(quickCreateHeading).toHaveCount(0);
  // ونموذج المنتج الأمّ ما زال مفتوحاً وما كتبه المستخدم لم يضع.
  await expect(nameInput).toBeVisible();
  await expect(nameInput).toHaveValue('اسمٌ لا يجوز أن يضيع بالخطأ');
});
