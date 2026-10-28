import { test, expect, type Locator, type Page } from '@playwright/test';
import { switchItemsToTable } from './items-view';

/**
 * TASK-2b — موقع التخزين لكل مخزن، من كرت المنتج.
 *
 * ما يُثبَت هنا ولا تراه `npm test` (دوالُّ خالصة) ولا `pytest` (خادم):
 *   (أ) موقعان — «عمود وصف» في مخزن و«رمز قسم» في آخر — يُحفظان بجسمٍ يطابق
 *       عقد `PUT` حرفاً، ثم يظهران في كرت المنتج بصيغة الخادم (`label`).
 *   (ب) حفظٌ لا يمسّ المواقع لا يُرسل `PUT` — القسم لا يُعيد كتابة ما لم يتغيّر.
 *   (ج) سطر «عمود وصف» بلا صفّ يُرفض محلّياً برسالة الخادم نفسها، ولا طلبَ حفظ.
 *   (د) فشلُ `PUT` بعد نجاح المنتج: رسالةٌ صريحة، والمحرّر كما هو لإعادة المحاولة.
 *   (هـ) فشلُ `GET storage-locations` لا يمنع فتح النموذج ولا حفظ المنتج، ولا
 *       يُرسَل قسمٌ لم يُحمَّل.
 *   (و) المنتج الجديد: الإنشاء أولاً ثم `PUT` بمعرّفه الجديد.
 *   (ز) النصّ القديم غير المنقول (`Product.storage_location`) يبقى ظاهراً للقراءة.
 *
 * المحاكي في هذا الملف وحده (لا `items-tree-stubs.ts` — مهمّةٌ أخرى تعدّله)،
 * ويردّ بشكل الخادم الحقيقي ويرفض ما يرفضه: جسمٌ ليس قائمة، تكرارُ مخزن،
 * `grid` بلا عمودٍ أو صفّ، و`code` بلا رمز.
 */

const WAREHOUSES = [
  { id: 13, name: 'مخزن أ', is_active: true, is_default: true, code: '', location: '' },
  { id: 14, name: 'مخزن ب', is_active: true, is_default: false, code: '', location: '' },
  { id: 15, name: 'مخزن ج', is_active: false, is_default: false, code: '', location: '' },
];

const PRODUCT_7 = {
  id: 7, tenant: 1, sku: 'SKU-7', barcode: '6291000',
  name_ar: 'إطار 205/55', name_en: '', display_name: 'إطار 205/55 — ميشلان',
  variant_group: 'إطار رياضي', brand: 'ميشلان', category: 3, category_name: 'إطارات',
  uom_id: null, uom_name: null, uom2: null, uom2_factor: null, uom3: null, uom3_factor: null,
  description: null, storage_location: null, image_url: null,
  sale_account_override: null, sale_return_account_override: null,
  purchase_account_override: null, purchase_return_account_override: null,
  supplier_account_override: null, ending_inventory_account_override: null,
  price_tiers: [], weight_kg: null, volume_cbm: null, hs_code: null,
  min_stock_level: 2, max_stock_level: null, reorder_mode: 'manual',
  is_serialized: false, is_service: false, is_active: true,
  is_for_sale_online: false, online_price: null, online_description: null,
  quantity_on_hand: '12', reserved_quantity: '0', available_quantity: '12', avg_cost: '30',
  sale_price: '45', purchased_qty: '20', avg_monthly_sales: '4',
  indicative_purchase_price: null, indicative_purchase_price_source: null,
  stock_status: 'in_stock', group_key: null, has_group: true,
  family_id: 40, family_name: 'إطار 205/55', family_brand_count: 1,
  effective_min_stock_level: 2, effective_max_stock_level: null, serial_required_by: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-21T00:00:00Z',
  attachments: [],
};

/** منتجٌ بنصّ موقعٍ قديمٍ غير منقول — يبقى ظاهراً للقراءة (ز). */
const PRODUCT_9 = {
  ...PRODUCT_7,
  id: 9, sku: 'SKU-9', name_ar: 'بطارية 70A', display_name: 'بطارية 70A',
  brand: 'فارتا', family_id: 41, family_name: 'بطارية 70A',
  storage_location: 'A-3',
};

type StoredRow = {
  id: number; warehouse: number; kind: 'grid' | 'code';
  column: string; row: string; code: string;
};

type StubOptions = {
  /** مواقع محفوظة مسبقاً لكل منتج — تُحمَّل عند فتح الكرت. */
  storage?: Record<number, Array<Omit<StoredRow, 'id'>>>;
  /** فشلُ `GET storage-locations` (هـ). */
  failStorageGet?: boolean;
  /** رفضُ `PUT` بـ400 كما يرفضه الخادم لمخزنٍ زال بين التحميل والحفظ (د). */
  rejectStoragePut?: boolean;
};

let putBodies: Array<{ id: number; body: unknown }> = [];
let patchBodies: Array<{ id: number; body: Record<string, unknown> }> = [];
let postBodies: Array<Record<string, unknown>> = [];

const warehouseName = (id: number): string =>
  WAREHOUSES.find((w) => w.id === id)?.name ?? '';

/** صيغة الخادم حرفاً: `ProductStorageLocation.label`. */
const labelOf = (r: Omit<StoredRow, 'id'>): string =>
  r.kind === 'grid' ? `عمود ${r.column} · صف ${r.row}` : r.code;

const start = async (page: Page, options: StubOptions = {}): Promise<void> => {
  putBodies = [];
  patchBodies = [];
  postBodies = [];

  let nextRowId = 100;
  const details: Record<number, Record<string, unknown>> = {
    7: { ...PRODUCT_7 },
    9: { ...PRODUCT_9 },
  };
  const storage = new Map<number, StoredRow[]>();
  for (const [productId, rows] of Object.entries(options.storage ?? {})) {
    storage.set(Number(productId), rows.map((r) => ({ ...r, id: nextRowId++ })));
  }

  const listed = (productId: number) => [...(storage.get(productId) ?? [])]
    .sort((a, b) => warehouseName(a.warehouse).localeCompare(warehouseName(b.warehouse), 'ar')
      || a.id - b.id)
    .map((r) => ({
      id: r.id, warehouse: r.warehouse, warehouse_name: warehouseName(r.warehouse),
      kind: r.kind, column: r.column, row: r.row, code: r.code, label: labelOf(r),
    }));

  await page.addInitScript(() => {
    localStorage.setItem('token', 'items-storage-e2e-token');
    localStorage.setItem('userId', 'items-storage-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = route.request().method();
    const storagePath = path.match(/\/inventory\/products\/(\d+)\/storage-locations\/$/);
    const detailPath = path.match(/\/inventory\/products\/(\d+)\/$/);

    // ── مواقع التخزين: GET/PUT بالعقد الحقيقي ──
    if (storagePath) {
      const productId = Number(storagePath[1]);
      if (method === 'GET') {
        if (options.failStorageGet) {
          await route.fulfill({
            status: 500, contentType: 'application/json',
            body: JSON.stringify({ error: 'تعذّر قراءة مواقع التخزين' }),
          });
          return;
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(listed(productId)) });
        return;
      }
      if (method === 'PUT') {
        const body = route.request().postDataJSON();
        putBodies.push({ id: productId, body });
        if (options.rejectStoragePut) {
          await route.fulfill({
            status: 400, contentType: 'application/json',
            body: JSON.stringify({ 0: { warehouse: ['Invalid pk "13" - object does not exist.'] } }),
          });
          return;
        }
        if (!Array.isArray(body)) {
          await route.fulfill({
            status: 400, contentType: 'application/json',
            body: JSON.stringify({ error: 'جسم الطلب يجب أن يكون قائمةَ مواقع' }),
          });
          return;
        }
        if (body.length > 200) {
          await route.fulfill({
            status: 400, contentType: 'application/json',
            body: JSON.stringify({ error: 'الحدّ الأقصى 200 موقعاً في الطلب الواحد' }),
          });
          return;
        }
        const rows: StoredRow[] = [];
        for (const [index, raw] of body.entries()) {
          const item = raw as Record<string, unknown>;
          if (!WAREHOUSES.some((w) => w.id === Number(item.warehouse))) {
            await route.fulfill({
              status: 400, contentType: 'application/json',
              body: JSON.stringify({ [index]: { warehouse: ['Invalid pk - object does not exist.'] } }),
            });
            return;
          }
          const kind = item.kind === 'code' ? 'code' : 'grid';
          const column = String(item.column ?? '').trim();
          const row = String(item.row ?? '').trim();
          const code = String(item.code ?? '').trim();
          if (kind === 'grid' && !column) {
            await route.fulfill({
              status: 400, contentType: 'application/json',
              body: JSON.stringify({ [index]: { column: ['عمود الموقع مطلوب لنوع «عمود وصف»'] } }),
            });
            return;
          }
          if (kind === 'grid' && !row) {
            await route.fulfill({
              status: 400, contentType: 'application/json',
              body: JSON.stringify({ [index]: { row: ['صفّ الموقع مطلوب لنوع «عمود وصف»'] } }),
            });
            return;
          }
          if (kind === 'code' && !code) {
            await route.fulfill({
              status: 400, contentType: 'application/json',
              body: JSON.stringify({ [index]: { code: ['رمز القسم مطلوب لنوع «رمز القسم»'] } }),
            });
            return;
          }
          rows.push({
            id: -1, warehouse: Number(item.warehouse), kind,
            column: kind === 'grid' ? column : '',
            row: kind === 'grid' ? row : '',
            code: kind === 'code' ? code : '',
          });
        }
        const seen = new Set<number>();
        for (const row of rows) {
          if (seen.has(row.warehouse)) {
            await route.fulfill({
              status: 400, contentType: 'application/json',
              body: JSON.stringify({
                error: [`المخزن «${warehouseName(row.warehouse)}» مكرَّر في القائمة — `
                  + 'موقعٌ واحد لكل منتجٍ في المخزن'],
              }),
            });
            return;
          }
          seen.add(row.warehouse);
        }
        // الباقي يُحدَّث في مكانه والغائب يُحذف — كما يفعل الخادم.
        const existing = new Map((storage.get(productId) ?? []).map((r) => [r.warehouse, r]));
        storage.set(productId, rows.map((r) => ({
          ...r, id: existing.get(r.warehouse)?.id ?? nextRowId++,
        })));
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(listed(productId)) });
        return;
      }
    }

    if (detailPath && method === 'PATCH') {
      const id = Number(detailPath[1]);
      const patch = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      patchBodies.push({ id, body: patch });
      details[id] = { ...(details[id] ?? {}), ...patch };
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(details[id]) });
      return;
    }

    let body: unknown = [];
    if (path.endsWith('/hr/users/items-storage-e2e-user/')) {
      body = {
        id: 'items-storage-e2e-user', name: 'Storage Tester', role: 'manager',
        email: 'storage@example.test', employmentStatus: 'active',
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
    } else if (path.endsWith('/inventory/warehouses/')) {
      body = url.searchParams.get('active_only') === 'true'
        ? WAREHOUSES.filter((w) => w.is_active)
        : WAREHOUSES;
    } else if (path.endsWith('/inventory/products/brands/')) {
      body = ['ميشلان', 'تويو'];
    } else if (path.endsWith('/inventory/products/groups/')) {
      body = ['إطار رياضي'];
    } else if (path.endsWith('/inventory/categories/')) {
      body = [{ id: 3, name: 'إطارات', parent: null }];
    } else if (path.endsWith('/inventory/stock-movements/summary/')) {
      body = { total_products_in_stock: 2, total_inventory_value: '720' };
    } else if (/\/inventory\/products\/\d+\/profile\/$/.test(path)) {
      const id = Number(path.split('/').filter(Boolean).at(-2));
      const detail = details[id] ?? PRODUCT_7;
      body = {
        id, sku: detail.sku, name: detail.display_name, brand: detail.brand,
        uom: 'حبة', category: 'إطارات', family_id: detail.family_id,
        is_service: false,
        quantity_on_hand: '12', reserved_quantity: '0', available_quantity: '12',
        avg_cost: '30', inventory_valuation: '360', sale_price: '45',
        effective_sale_price: '45', profit_per_unit: '15', profit_margin_pct: '33.33',
        purchased_qty: '20', purchased_value: '600', sold_qty: '4', sold_value: '180',
        storage_locations: listed(id).map((r) => ({
          warehouse_id: r.warehouse, warehouse_name: r.warehouse_name, kind: r.kind,
          column: r.column, row: r.row, code: r.code, label: r.label,
        })),
      };
    } else if (/\/inventory\/products\/\d+\/(stock-ledger|invoices|serials)\/$/.test(path)) {
      body = { count: 0, results: [] };
    } else if (detailPath) {
      body = details[Number(detailPath[1])] ?? PRODUCT_7;
    } else if (path.endsWith('/inventory/products/') && method === 'POST') {
      const post = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      postBodies.push(post);
      details[91] = {
        ...PRODUCT_7, id: 91, sku: 'SKU-91', name_ar: String(post.name_ar ?? ''),
        display_name: String(post.name_ar ?? ''), brand: String(post.brand ?? ''),
        family_id: null, family_name: null, storage_location: null,
      };
      await route.fulfill({
        status: 201, contentType: 'application/json', body: JSON.stringify(details[91]),
      });
      return;
    } else if (path.endsWith('/inventory/products/')) {
      // بلا `page` → مصفوفة (OptionalPageNumberPagination).
      body = [details[7], details[9]];
    } else if (/\/inventory\/products\/\d+\/available-brands\/$/.test(path)) {
      body = [];
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
};

/**
 * الجدول صار الوضعَ المحفوظ في `localStorage` بعد أول تبديل داخل الاختبار —
 * فزرُّ «عرض كجدول» لا يُوجد حين نعود إلى الشاشة وهنالك أصلاً.
 */
const ensureTable = async (page: Page): Promise<void> => {
  await page.waitForLoadState('networkidle');
  if (await page.getByTitle('عرض كجدول').count() === 0) return;
  await switchItemsToTable(page);
};

const openItemCard = async (page: Page, sku = 'SKU-7'): Promise<void> => {
  await page.goto('/items');
  await page.waitForLoadState('networkidle');
  await ensureTable(page);
  await page.getByTitle(sku).first().dblclick();
  await page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' }).waitFor();
};

const openOtherTab = async (page: Page): Promise<void> => {
  await page.getByRole('tab', { name: 'بيانات أخرى' }).click();
};

const section = (page: Page) => page.getByTestId('storage-locations');
const rowAt = (page: Page, index: number) => page.getByTestId(`storage-row-${index}`);
const addRow = (page: Page) => section(page).getByRole('button', { name: 'إضافة موقع' }).click();
const pickKind = (row: Locator, kind: 'عمود وصف' | 'رمز القسم') =>
  row.getByRole('radio', { name: kind }).check();
const save = (page: Page) => page.getByRole('button', { name: /تخزين/ }).click();

test('(أ) موقعان بمخزنين — الجسم يطابق العقد، والكرت يعرض صيغة الخادم', async ({ page }) => {
  await start(page);
  await openItemCard(page);
  await openOtherTab(page);

  await addRow(page);
  // أول سطر يُقترح فيه المخزن الافتراضي.
  await expect(rowAt(page, 0).getByLabel('المخزن')).toHaveValue('13');
  await rowAt(page, 0).getByLabel('العمود', { exact: true }).fill('B');
  await rowAt(page, 0).getByLabel('الصف', { exact: true }).fill('7');

  await addRow(page);
  // المخزن المختار في سطرٍ لا يظهر خياراً في سطرٍ آخر ⇒ التالي هو «مخزن ب».
  await expect(rowAt(page, 1).getByLabel('المخزن')).toHaveValue('14');
  await pickKind(rowAt(page, 1), 'رمز القسم');
  await rowAt(page, 1).getByPlaceholder('مثال: A86').fill('A86');

  await save(page);
  await expect.poll(() => putBodies.length).toBe(1);
  expect(putBodies[0].id).toBe(7);
  expect(putBodies[0].body).toEqual([
    { warehouse: 13, kind: 'grid', column: 'B', row: '7', code: '' },
    { warehouse: 14, kind: 'code', column: '', row: '', code: 'A86' },
  ]);

  // الكرت يُقرأ من ردّ الخادم: الاسم المخزني و`label` كلٌّ في بطاقته.
  await openItemCard(page);
  const storageSection = page.locator('section')
    .filter({ has: page.getByText('موقع التخزين', { exact: true }) });
  await expect(storageSection.getByText('مخزن أ', { exact: true })).toBeVisible();
  await expect(storageSection.getByText('عمود B · صف 7', { exact: true })).toBeVisible();
  await expect(storageSection.getByText('مخزن ب', { exact: true })).toBeVisible();
  await expect(storageSection.getByText('A86', { exact: true })).toBeVisible();
});

test('(ب) حفظٌ لا يمسّ المواقع لا يُرسل PUT', async ({ page }) => {
  await start(page, {
    storage: { 7: [{ warehouse: 13, kind: 'grid', column: 'B', row: '7', code: '' }] },
  });
  await openItemCard(page);
  await openOtherTab(page);

  await expect(rowAt(page, 0).getByLabel('المخزن')).toHaveValue('13');
  await expect(rowAt(page, 0).getByLabel('العمود', { exact: true })).toHaveValue('B');
  await expect(rowAt(page, 0).getByLabel('الصف', { exact: true })).toHaveValue('7');

  await save(page);
  await expect.poll(() => patchBodies.length).toBe(1);
  expect(putBodies).toHaveLength(0);
});

test('(ج) «عمود وصف» بلا صفّ — رسالةٌ عند الحقل ولا حفظ', async ({ page }) => {
  await start(page);
  await openItemCard(page);
  await openOtherTab(page);

  await addRow(page);
  await rowAt(page, 0).getByLabel('العمود', { exact: true }).fill('B');

  await save(page);
  await expect(section(page).getByText('صفّ الموقع مطلوب لنوع «عمود وصف»')).toBeVisible();
  expect(patchBodies).toHaveLength(0);
  expect(putBodies).toHaveLength(0);
});

test('(د) فشلُ PUT بعد نجاح المنتج — رسالةٌ صريحة والمحرّر باقٍ', async ({ page }) => {
  await start(page, {
    storage: { 7: [{ warehouse: 13, kind: 'grid', column: 'B', row: '7', code: '' }] },
    rejectStoragePut: true,
  });
  await openItemCard(page);
  await openOtherTab(page);

  await addRow(page);
  await pickKind(rowAt(page, 1), 'رمز القسم');
  await rowAt(page, 1).getByPlaceholder('مثال: A86').fill('A86');

  await save(page);
  await expect.poll(() => patchBodies.length).toBe(1);
  await expect.poll(() => putBodies.length).toBe(1);

  // المنتج حُفظ فعلاً — الرسالة تقول ذلك ولا تدّعي نجاح المواقع.
  await expect(page.locator('.ktra-banner--err')).toContainText('حُفظ المنتج، وتعذّر حفظ موقع التخزين');
  // المحرّر كما هو: الكرت مفتوح والسطر الثاني بقيمته ليُعاد الإرسال.
  await expect(page.locator('.ktra-title-chip', { hasText: 'كرت المنتج' })).toBeVisible();
  await expect(rowAt(page, 1).getByPlaceholder('مثال: A86')).toHaveValue('A86');
  await expect(rowAt(page, 1).getByRole('radio', { name: 'رمز القسم' })).toBeChecked();
});

test('(هـ) فشلُ جلب المواقع لا يمنع فتح النموذج ولا حفظ المنتج', async ({ page }) => {
  await start(page, { failStorageGet: true });
  await openItemCard(page);
  await openOtherTab(page);

  await expect(section(page)).toContainText('تعذّر تحميل مواقع التخزين');

  await save(page);
  await expect.poll(() => patchBodies.length).toBe(1);
  expect(putBodies).toHaveLength(0);
});

test('(و) المنتج الجديد: الإنشاء ثم PUT بمعرّفه الجديد', async ({ page }) => {
  await start(page);
  await page.goto('/items');
  await page.waitForLoadState('networkidle');

  await page.getByTitle('منتج جديد (Ctrl+Ins)').click();
  await page.getByPlaceholder('اسم المنتج').first().fill('فلتر زيت تويوتا');
  await openOtherTab(page);

  await addRow(page);
  await expect(rowAt(page, 0).getByLabel('المخزن')).toHaveValue('13');
  await rowAt(page, 0).getByLabel('العمود', { exact: true }).fill('B');
  await rowAt(page, 0).getByLabel('الصف', { exact: true }).fill('7');

  await save(page);
  await expect.poll(() => postBodies.length).toBe(1);
  await expect.poll(() => putBodies.length).toBe(1);
  expect(putBodies[0].id).toBe(91);
  expect(putBodies[0].body).toEqual([
    { warehouse: 13, kind: 'grid', column: 'B', row: '7', code: '' },
  ]);
});

test('(ز) النصّ القديم غير المنقول يبقى ظاهراً للقراءة، وحقلُه القديم أُزيل', async ({ page }) => {
  await start(page);
  await openItemCard(page, 'SKU-9');
  await openOtherTab(page);

  await expect(page.getByText('موقع التخزين (رفّ/ممر)')).toHaveCount(0);
  await expect(section(page).getByTestId('legacy-storage-location'))
    .toContainText('موقع قديم (نص): A-3 — أضفه لمخزنٍ ليُحفظ بالشكل الجديد');
});
