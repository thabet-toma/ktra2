import { test, expect } from '@playwright/test';

/**
 * T-PRODUCT M2 — اسم المنتج في الجدول: نصٌّ يُحرَّر في مكانه، لا رابطٌ يُنقَل عنه.
 *
 * يثبّت الاختبار أربعة أشياء لا يراها فحص الأنواع (المستودع بلا `@types/react`،
 * فخصائص JSX غير مفحوصة أصلاً):
 *   1. الاسم لم يعد يحمل شكل الرابط، والنقرة المفردة لا تنقُل.
 *   2. نقرتان تفتحان حقلاً — ولا تفتحان الكرت الكامل معه (فخّ نقرتَي الصفّ).
 *   3. Enter يرسل **طلباً واحداً** حمولته `{name_ar}` وحدها — لا الحمولة كاملةً.
 *   4. Esc لا يرسل شيئاً، والفشل يُبقي المسوّدة مكانها.
 *
 * الشبكة موقوفة بالكامل: موضوع الفحص هو الخلية، لا الخادم.
 */

const PRODUCTS = [
  {
    id: 7, sku: 'SKU-7', name_ar: 'إطار 205/55', name_en: '', display_name: 'إطار 205/55',
    category: 3, category_name: 'إطارات', quantity_on_hand: '12', reserved_quantity: '0',
    available_quantity: '12', avg_cost: '30', sale_price: '45', min_stock_level: 2,
    stock_status: 'in_stock', has_group: false, group_key: null,
  },
  {
    id: 8, sku: 'SKU-8', name_ar: 'بطارية 70A', name_en: '', display_name: 'بطارية 70A',
    category: 3, category_name: 'إطارات', quantity_on_hand: '0', reserved_quantity: '0',
    available_quantity: '0', avg_cost: '55', sale_price: '80', min_stock_level: 1,
    stock_status: 'out_of_stock', has_group: false, group_key: null,
  },
];

type Patch = { id: number; body: Record<string, unknown> };

/** الطلبات التي وصلت الخادم فعلاً — مصدر الحكم في «كم طلباً» و«بأي حمولة». */
let patches: Patch[] = [];
/** لقلب ردّ التعديل إلى 400 في اختبار الفشل وحده. */
let rejectNextPatch: string | null = null;

test.beforeEach(async ({ page }) => {
  patches = [];
  rejectNextPatch = null;

  await page.addInitScript(() => {
    localStorage.setItem('token', 'items-name-e2e-token');
    localStorage.setItem('userId', 'items-name-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = route.request().method();

    const detail = path.match(/\/inventory\/products\/(\d+)\/$/);
    if (detail && method === 'PATCH') {
      const id = Number(detail[1]);
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      patches.push({ id, body });
      if (rejectNextPatch) {
        const message = rejectNextPatch;
        rejectNextPatch = null;
        return route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ name_ar: [message] }),
        });
      }
      const base = PRODUCTS.find((p) => p.id === id)!;
      const name = String(body.name_ar ?? base.name_ar);
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ...base, name_ar: name, display_name: name }),
      });
    }

    let body: unknown = [];
    if (path.endsWith('/hr/users/items-name-e2e-user/')) {
      body = {
        id: 'items-name-e2e-user', name: 'Name Tester', role: 'manager',
        email: 'name@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة المنتجات', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = {
        role: 'manager', is_manager: true, ui_mode: 'advanced',
        permissions: ['inventory.item.view', 'inventory.item.manage'],
      };
    } else if (path.endsWith('/inventory/categories/')) {
      body = [{ id: 3, name: 'إطارات', parent: null }];
    } else if (/\/inventory\/products\/\d+\/profile\/$/.test(path)) {
      body = { id: 7, sku: 'SKU-7', name: 'إطار 205/55', category: 'إطارات' };
    } else if (/\/inventory\/products\/\d+\/(stock-ledger|invoices|serials)\/$/.test(path)) {
      body = { count: 0, results: [] };
    } else if (detail) {
      body = PRODUCTS.find((p) => p.id === Number(detail[1])) ?? {};
    } else if (path.endsWith('/inventory/products/')) {
      body = { count: PRODUCTS.length, results: PRODUCTS, next: null, previous: null };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
});

const openItems = async (page: import('@playwright/test').Page) => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
};

const nameCell = (page: import('@playwright/test').Page) =>
  page.getByTitle('نقرتان أو F2 لتعديل الاسم').first();

test('اسم المنتج لا يحمل شكل الرابط، والنقرة المفردة لا تفتح شيئاً', async ({ page }) => {
  await openItems(page);

  const name = nameCell(page);
  await expect(name).toBeVisible();
  await expect(name).toHaveText('إطار 205/55');

  // لا تسطير ولا لون رابط — الشرط الذي طلبه المالك حرفياً.
  const cls = (await name.getAttribute('class')) ?? '';
  expect(cls).not.toContain('underline');
  expect(cls).not.toContain('ktra-accent');
  expect(await name.evaluate((el) => getComputedStyle(el).textDecorationLine)).toBe('none');

  // النقرة المفردة تُركِّز فقط: لا كرت، ولا مغادرة للجدول.
  await name.click();
  await expect(page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' })).toHaveCount(0);
  await expect(name).toBeVisible();
});

test('نقرتان تفتحان حقلاً في مكانه — ولا تفتحان الكرت الكامل معه', async ({ page }) => {
  await openItems(page);

  await nameCell(page).dblclick();

  const input = page.getByLabel('تعديل اسم المنتج');
  await expect(input).toBeVisible();
  await expect(input).toHaveValue('إطار 205/55');
  // فخّ الانتشار: نقرتا الصفّ تفتحان الكرت الكامل، فلولا إيقاف الانتشار لأُلغي
  // تركيب الحقل في نفس اللحظة التي وُلد فيها.
  await expect(page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' })).toHaveCount(0);
});

test('Enter يحفظ بطلبٍ واحد حمولته اسمٌ فقط، ويُحدّث الصفّ', async ({ page }) => {
  await openItems(page);

  await nameCell(page).dblclick();
  const input = page.getByLabel('تعديل اسم المنتج');
  await input.fill('إطار 205/55 مُعدَّل');
  await input.press('Enter');

  await expect(page.getByLabel('تعديل اسم المنتج')).toHaveCount(0);
  await expect(nameCell(page)).toHaveText('إطار 205/55 مُعدَّل');

  // طلبٌ واحد لا اثنان: تعطيل الحقل بعد Enter يُطلق `blur` أيضاً.
  expect(patches).toHaveLength(1);
  expect(patches[0].id).toBe(7);
  // الحمولة فرقُ ما تغيّر وحده — لا `category` ولا `sale_price` تُكتبان معه.
  expect(patches[0].body).toEqual({ name_ar: 'إطار 205/55 مُعدَّل' });
});

test('Esc يلغي بلا أي طلب، ويعيد الاسم الأصلي', async ({ page }) => {
  await openItems(page);

  await nameCell(page).dblclick();
  const input = page.getByLabel('تعديل اسم المنتج');
  await input.fill('اسمٌ لن يُحفظ');
  await input.press('Escape');

  await expect(page.getByLabel('تعديل اسم المنتج')).toHaveCount(0);
  await expect(nameCell(page)).toHaveText('إطار 205/55');
  expect(patches).toHaveLength(0);
});

test('رفض الخادم يُبقي الحقل مفتوحاً بالمسوّدة وبرسالة الخادم', async ({ page }) => {
  await openItems(page);
  rejectNextPatch = 'الاسم مستخدم لمنتجٍ آخر.';

  await nameCell(page).dblclick();
  const input = page.getByLabel('تعديل اسم المنتج');
  await input.fill('اسمٌ مكرّر');
  await input.press('Enter');

  // لا شيء يُعدَّل محلياً قبل الردّ — فلا شيء يُتراجَع عنه: المسوّدة كما تركها.
  await expect(input).toBeVisible();
  await expect(input).toHaveValue('اسمٌ مكرّر');
  await expect(input).toHaveAttribute('title', /الاسم مستخدم لمنتجٍ آخر/);
  expect(patches).toHaveLength(1);
});

test('نقرتان على خليةٍ أخرى ما زالتا تفتحان الكرت الكامل', async ({ page }) => {
  await openItems(page);

  // خلية رقم المنتج في نفس الصفّ — المنفذ القديم للكرت لم يُمَسّ.
  await page.getByTitle('SKU-7').first().dblclick();

  await expect(page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' })).toBeVisible();
  expect(patches).toHaveLength(0);
});
