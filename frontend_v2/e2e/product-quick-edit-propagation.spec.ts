/**
 * T-PRODUCT M4 — تعديل منتجٍ من داخل مستند: النتيجة تصل السطر، لا تُبتلَع.
 *
 * ثلاثة أعطالٍ مؤكَّدة كان هذا الملف ليكشفها لو وُجد قبل اليوم:
 *   1. فاتورة البيع — المُرشّح `!known.has(p.id)` يُسقط كل منتجٍ **موجود**، أي
 *      كلَّ ما يمسّه التعديل؛ فلم تعمل المزامنة المحلية يوماً للتعديل.
 *   2. فاتورة الشراء — الاسم ملتقَطٌ نسخةً على السطر، وترقيع الكتالوج وحده
 *      يتركه قديماً **إلى الأبد** (لا مشترِك حدثٍ هنا يُنقذه).
 *   3. البطاقة — «تعديل سريع» من داخلها كان يُحدّث البطاقة وحدها ولا يبلّغ
 *      مستدعيها أبداً.
 *
 * **مسار جلب الكتالوج مثبَّتٌ على الاسم القديم عمداً**: لولا ذلك لنجح الاختبار
 * مصادفةً بالجلب الثقيل الذي يُطلقه حدث `products`، بدل أن يُثبت الآلية المحلية.
 */
import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

const OLD_NAME = 'لابتوب قديم';
const NEW_NAME = 'لابتوب مُعدَّل';

/** المنتج كما يراه الكتالوج **دائماً** — لا يتغيّر مهما جرى تعديل. */
const CATALOG_PRODUCT = {
  id: 42, sku: 'P-42', name_ar: OLD_NAME, name_en: '', display_name: OLD_NAME,
  barcode: '', category: null, uom_id: null, is_service: false, is_serialized: false,
  quantity_on_hand: '9', reserved_quantity: '0', available_quantity: '9',
  avg_cost: '80', sale_price: '100', stock_status: 'in_stock',
  has_group: false, group_key: null,
};

type Ctx = { patches: Record<string, unknown>[] };

/** التوجيه المشترك: هوية + صلاحيات + كتالوج ثابت + تعديلٌ يردّ الاسم الجديد. */
async function baseRoutes(page: Page, user: string, perms: string[]): Promise<Ctx> {
  const ctx: Ctx = { patches: [] };
  await page.addInitScript((u) => {
    localStorage.setItem('token', `${u}-token`);
    localStorage.setItem('userId', u);
    localStorage.setItem('tenantId', '1');
    localStorage.setItem('ktra_ui_mode::1', 'advanced');
  }, user);

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    const method = route.request().method();
    const json = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });

    // التعديل السريع — الردّ وحده يحمل الاسم الجديد.
    if (/\/inventory\/products\/42\/$/.test(path) && method === 'PATCH') {
      ctx.patches.push((route.request().postDataJSON() ?? {}) as Record<string, unknown>);
      return json({ ...CATALOG_PRODUCT, name_ar: NEW_NAME, display_name: NEW_NAME });
    }
    // القراءة تبقى على الاسم القديم — بما فيها إعادة جلب الكتالوج بعد الحدث.
    if (/\/inventory\/products\/42\/$/.test(path)) return json(CATALOG_PRODUCT);
    if (/\/inventory\/products\/42\/profile\/$/.test(path)) {
      return json({ id: 42, sku: 'P-42', name: OLD_NAME, quantity_on_hand: '9', avg_cost: '80', sale_price: '100' });
    }
    if (/\/inventory\/products\/42\/(stock-ledger|invoices|serials)\/$/.test(path)) {
      return json({ count: 0, results: [] });
    }
    if (path.endsWith('/inventory/products/')) return json([CATALOG_PRODUCT]);
    if (path.endsWith('/inventory/uoms/')) return json([]);
    if (path.endsWith('/inventory/categories/')) return json([]);

    if (path.endsWith(`/hr/users/${user}/`)) {
      return json({
        id: user, name: 'مُحرِّر المستند', role: 'manager', email: `${user}@example.test`,
        employmentStatus: 'active', isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الانتشار', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-01-01T00:00:00Z',
        can_access_import: false,
      }]);
    }
    if (path.endsWith('/permissions/me/')) {
      return json({ role: 'manager', is_manager: true, ui_mode: 'advanced', permissions: perms });
    }
    return json([]);
  });
  return ctx;
}

/** النافذة العائمة الفعّالة — المطابقة بالاسم وحدها تلتقط أزرار الشبكة خلف القناع. */
const floatWin = (page: Page, titlePart: string) =>
  page.locator('.ktra-float-win').filter({ has: page.locator('.ktra-float-win__title', { hasText: titlePart }) });

/** تعديل الاسم في نافذة «تعديل سريع» ثم الحفظ. */
async function renameInQuickEdit(page: Page, next: string) {
  const win = floatWin(page, 'تعديل سريع');
  await expect(win).toBeVisible();
  const nameInput = win.locator('label:has-text("اسم المنتج") input').first();
  await expect(nameInput).toBeVisible();
  await nameInput.fill(next);
  await win.getByRole('button', { name: 'حفظ', exact: true }).click();
  await expect(win).toHaveCount(0);
}

/* ───────────────────────── فاتورة البيع ───────────────────────── */

const SALES_INVOICE = {
  id: 301, invoice_number: 'SI-301', invoice_date: '2026-08-10', due_date: '2026-09-10',
  customer: 8, customer_name: 'زبون الانتشار', invoice_type: 'credit', invoice_kind: 'sale',
  status: 'draft', currency: 1, exchange_rate: '1',
  subtotal_excl_tax: '100.00', invoice_discount: '0.00', tax_amount: '0.00',
  grand_total: '100.00', amount_paid: '0.00', remaining_balance: '100.00',
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  journal: null, stock_on_post: true, payment_details: [],
  lines: [{ id: 1, product: 42, quantity: '1', unit_price: '100', line_discount: '0', tax_rate: null }],
};

async function openSalesInvoice(page: Page): Promise<Ctx> {
  const ctx = await baseRoutes(page, 'prop-sales-user', [
    'sales.invoice.view', 'sales.invoice.edit', 'sales.invoice.create',
    'inventory.item.view', 'inventory.item.manage',
  ]);
  await page.route('**/sales/invoices/301/**', (r) => r.fulfill({
    contentType: 'application/json', body: JSON.stringify(SALES_INVOICE),
  }));
  await page.route('**/sales/invoices/301/', (r) => r.fulfill({
    contentType: 'application/json', body: JSON.stringify(SALES_INVOICE),
  }));
  await page.route('**/partners/lookup/**', (r) => r.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{ id: 8, name: 'زبون الانتشار', partner_type: 'Customer' }]),
  }));
  await page.goto('/sales/invoices/301');
  await page.waitForLoadState('networkidle');
  // نمط المستودع: فتح المستند = عرضٌ للقراءة، والتحرير من داخله بزرّ صريح.
  await page.getByRole('button', { name: 'تحرير' }).first().click();
  return ctx;
}

test('فاتورة البيع: تعديل الاسم من القلم يصل السطر فوراً — ولا يُكرّر المنتج في القائمة', async ({ page }) => {
  const ctx = await openSalesInvoice(page);

  const lineName = page.getByPlaceholder('اكتب اسم المنتج…').first();
  await expect(lineName).toHaveValue(OLD_NAME);

  await page.getByTitle('تعديل سريع للمنتج').first().click();
  await renameInQuickEdit(page, NEW_NAME);

  // السطر يحمل الاسم الجديد رغم أن كل قراءةٍ من الخادم ما زالت تردّ القديم.
  await expect(lineName).toHaveValue(NEW_NAME);
  expect(ctx.patches).toEqual([{ name_ar: NEW_NAME }]);

  // ولا تكرار: القائمة تُبنى من المصفوفة، فتجاوزٌ لا إلحاق.
  await lineName.click();
  await expect(page.getByRole('option', { name: new RegExp(NEW_NAME) })).toHaveCount(1);
});

/* ───────────────────────── فاتورة الشراء ───────────────────────── */

const PURCHASE_INVOICE = {
  id: 88, invoice_number: 'PINV-0088', invoice_name: 'فاتورة الانتشار',
  invoice_date: '2026-07-01', due_date: '2026-07-31', payment_terms_days: 30,
  partner: 4, partner_name: 'مورّد الانتشار',
  currency: 1, currency_code: 'ILS', exchange_rate: 1,
  subtotal: 100, discount_amount: 0, tax_rate: 0, tax_amount: 0, grand_total: 100,
  invoice_type: 'local', status: 'draft', payment_type: 'credit',
  is_posted: false, is_return: false, is_local: true,
  receipt_status: 'not_received', receipt_status_display: 'غير مستلمة',
  amount_paid: 0, remaining_balance: 100,
  payment_status: 'unpaid', payment_status_display: 'غير مدفوعة',
  fees_total: '0', payable_total: '100',
  items: [{ id: 11, product: 42, item_id: 42, name: OLD_NAME, quantity: 1, unit_price: 100, total_price: 100 }],
  fees: [], payment_details: [],
  created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z',
};

async function openPurchaseInvoice(page: Page): Promise<Ctx> {
  const ctx = await baseRoutes(page, 'prop-purch-user', [
    'purchase.invoice.view', 'purchase.invoice.create', 'purchase.invoice.edit',
    'inventory.item.view', 'inventory.item.manage',
  ]);
  await page.route('**/purchase-invoices/88/', (r) => r.fulfill({
    contentType: 'application/json', body: JSON.stringify(PURCHASE_INVOICE),
  }));
  await page.goto('/purchase-invoices/88');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: 'تحرير' }).first().click();
  return ctx;
}

test('فاتورة الشراء: الاسم الملتقَط على السطر يُعاد تطبيقه بعد التعديل', async ({ page }) => {
  const ctx = await openPurchaseInvoice(page);

  const lineName = page.getByPlaceholder('اكتب اسم المنتج…').first();
  await expect(lineName).toHaveValue(OLD_NAME);

  await page.getByTitle('تعديل سريع للمنتج').first().click();
  await renameInQuickEdit(page, NEW_NAME);

  await expect(lineName).toHaveValue(NEW_NAME);
  expect(ctx.patches).toEqual([{ name_ar: NEW_NAME }]);
});

test('فاتورة الشراء: البطاقة تُبلِّغ مستدعيها — «تعديل سريع» من داخلها يصل السطر', async ({ page }) => {
  const ctx = await openPurchaseInvoice(page);

  const lineName = page.getByPlaceholder('اكتب اسم المنتج…').first();
  await expect(lineName).toHaveValue(OLD_NAME);

  // (i) → البطاقة، ثم «تعديل سريع» من داخلها: الطريق الذي كان يبتلع نتيجته.
  await page.getByTitle('بطاقة المنتج').first().click();
  const card = floatWin(page, 'بطاقة المنتج');
  await card.getByRole('button', { name: 'تعديل سريع', exact: true }).click();
  await renameInQuickEdit(page, NEW_NAME);

  await expect(lineName).toHaveValue(NEW_NAME);
  expect(ctx.patches).toEqual([{ name_ar: NEW_NAME }]);
});
