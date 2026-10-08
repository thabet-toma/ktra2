import { test, expect } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

/**
 * T4 — إيقاف المنتج من قائمة المنتجات.
 *
 * يثبّت ما لا يراه فحص الأنواع ولا اختبارات `utils/*.test.ts` (دوالُّ خالصة لا تصيّر مكوّناً):
 *   1. الافتراضي «نشط»: الطلب يحمل `status=active` والموقوف لا يظهر.
 *   2. «إيقاف» لا يكتب شيئاً قبل التأكيد: نافذةٌ تعرض الرصيد والمسوّدات، والإلغاء لا يرسل `set-active`.
 *   3. التأكيد يرسل `set-active {is_active:false}` مرّةً واحدة.
 *   4. مرشّح «موقوف» يعرض الصفّ بشارة «غير نشط» وزرّ «تنشيط»، والتنشيط مباشر بلا نافذة.
 * الخادم مُحاكى بالكامل في الذاكرة (لا خادمَ حقيقياً هنا).
 */

interface MockProduct {
  id: number; sku: string; name_ar: string; name_en: string; display_name: string;
  category: number; category_name: string; quantity_on_hand: string; reserved_quantity: string;
  available_quantity: string; avg_cost: string; sale_price: string; min_stock_level: number;
  stock_status: string; has_group: boolean; group_key: null; is_active: boolean;
}

const product = (over: Partial<MockProduct>): MockProduct => ({
  id: 7, sku: 'SKU-7', name_ar: 'إطار 205/55', name_en: '', display_name: 'إطار 205/55',
  category: 3, category_name: 'إطارات', quantity_on_hand: '12', reserved_quantity: '0',
  available_quantity: '12', avg_cost: '30', sale_price: '45', min_stock_level: 2,
  stock_status: 'in_stock', has_group: false, group_key: null, is_active: true, ...over,
});

let products: MockProduct[] = [];
let listQueries: string[] = [];
let setActiveCalls: { id: number; body: Record<string, unknown> }[] = [];

test.beforeEach(async ({ page }) => {
  products = [product({ id: 7 }), product({ id: 8, sku: 'SKU-8', name_ar: 'بطارية', display_name: 'بطارية', is_active: false })];
  listQueries = [];
  setActiveCalls = [];
  await signIn(page);
});

const signIn = async (page: Page) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'deact-e2e-token');
    localStorage.setItem('userId', 'deact-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) return route.continue();
    const path = url.pathname;
    const method = route.request().method();
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });

    const setActive = path.match(/\/inventory\/products\/(\d+)\/set-active\/$/);
    if (setActive && method === 'POST') {
      const id = Number(setActive[1]);
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      setActiveCalls.push({ id, body });
      const row = products.find((p) => p.id === id)!;
      row.is_active = Boolean(body.is_active);
      return json({ id, is_active: row.is_active });
    }
    if (/\/inventory\/products\/\d+\/deactivation-impact\/$/.test(path)) {
      return json({
        quantity_on_hand: '12.0000',
        draft_documents_count: 2,
        draft_documents: [
          { kind: 'sales_invoice', kind_label: 'فاتورة بيع', id: 1, number: 'INV-1', date: '2026-10-01' },
          { kind: 'sales_order', kind_label: 'طلبية بيع', id: 2, number: 'SO-2', date: '2026-10-02' },
        ],
      });
    }
    if (path.endsWith('/hr/users/deact-e2e-user/')) {
      return json({
        id: 'deact-e2e-user', name: 'Deact Tester', role: 'manager', email: 'd@example.test',
        employmentStatus: 'active', isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة المنتجات', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z', can_access_import: false,
      }]);
    }
    if (path.endsWith('/permissions/me/')) {
      return json({ role: 'manager', is_manager: true, ui_mode: 'advanced', permissions: ['inventory.item.view', 'inventory.item.manage'] });
    }
    const detail = path.match(/\/inventory\/products\/(\d+)\/$/);
    if (detail && method === 'GET') return json(products.find((p) => p.id === Number(detail[1])) ?? {});
    if (/\/inventory\/products\/\d+\/(stock-ledger|invoices|serials)\/$/.test(path)) return json({ count: 0, results: [] });
    if (path.endsWith('/inventory/categories/')) return json([{ id: 3, name: 'إطارات', parent: null }]);
    if (path.endsWith('/inventory/products/')) {
      listQueries.push(url.search);
      const status = url.searchParams.get('status') || 'active';
      const rows = products.filter((p) => status === 'all' || (status === 'inactive' ? !p.is_active : p.is_active));
      return json({ count: rows.length, results: rows, next: null, previous: null });
    }
    return json([]);
  });
};

test('الافتراضي نشط، والإيقاف يطلب تأكيداً بالرصيد والمسوّدات، والإلغاء لا يكتب شيئاً', async ({ page }) => {
  await page.goto('/items');
  await expect(page.getByText('إطار 205/55').first()).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('بطارية')).toHaveCount(0);
  expect(listQueries.length).toBeGreaterThan(0);
  expect(new URLSearchParams(listQueries[0]).get('status')).toBe('active');

  await page.getByTestId('product-deactivate').first().click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('سيصبح «إطار 205/55» غير نشط');
  await expect(dialog).toContainText('الكمية الموجودة في المخزون');
  await expect(dialog).toContainText('مسوّدات تحمله: 2');
  await expect(dialog).toContainText('فاتورة بيع INV-1');
  expect(setActiveCalls).toHaveLength(0);

  await dialog.getByRole('button', { name: 'إلغاء' }).click();
  await expect(dialog).toHaveCount(0);
  expect(setActiveCalls).toHaveLength(0);
});

test('التأكيد يرسل set-active مرّةً واحدة، ومرشّح «موقوف» يعرض الصفّ بشارته وزرّ التنشيط', async ({ page }) => {
  await page.goto('/items');
  await expect(page.getByText('إطار 205/55').first()).toBeVisible({ timeout: 20000 });

  await page.getByTestId('product-deactivate').first().click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'إيقاف' }).click();
  await expect.poll(() => setActiveCalls.length).toBe(1);
  expect(setActiveCalls[0]).toEqual({ id: 7, body: { is_active: false } });

  await page.getByTestId('items-active-filter-inactive').click();
  await expect(page.getByText('بطارية').first()).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('إطار 205/55').first()).toBeVisible();
  await expect(page.getByText('غير نشط').first()).toBeVisible();
  expect(listQueries.some((q) => new URLSearchParams(q).get('status') === 'inactive')).toBe(true);

  // التنشيط مباشر: بلا نافذة تأكيد.
  await page.getByTestId('product-activate').first().click();
  await expect.poll(() => setActiveCalls.length).toBe(2);
  expect(setActiveCalls[1].body).toEqual({ is_active: true });
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
});

test('بطاقة المنتج الموقوف: شريط «غير نشط» وزرّ تنشيط، وتنشيطه يُخفي الشريط', async ({ page }) => {
  await page.goto('/items');
  await page.getByTestId('items-active-filter-inactive').click();
  await expect(page.getByText('بطارية').first()).toBeVisible({ timeout: 20000 });
  await page.getByTitle('تعديل', { exact: true }).first().click();

  const banner = page.getByText('هذا المنتج غير نشط — لا يظهر في المستندات الجديدة');
  await expect(banner).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: 'تنشيط' }).first().click();
  await expect.poll(() => setActiveCalls.length).toBe(1);
  expect(setActiveCalls[0]).toEqual({ id: 8, body: { is_active: true } });
  await expect(banner).toHaveCount(0);
});
