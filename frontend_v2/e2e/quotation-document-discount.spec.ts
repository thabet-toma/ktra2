import { test, expect, type Page } from '@playwright/test';

/**
 * عرض سعر البيع بعد T-QUOTE-DISC: «الخصم» في صندوق الإجماليات صار خصم **المستند**
 * (يُكتب ويسبق الضريبة)، وبند العرض صار له زرّ بطاقةٍ تُظهر تكلفة الصنف وأسعاره.
 *
 * يثبّت الاختبار الثلاثةَ التي طلبها المالك: الخصم يُحرَّر في الأسفل، وهو خصم
 * فاتورة لا خصم بند (الضريبة تُحسب بعده)، والتكلفة مرئية من داخل العرض.
 */

const PRODUCT = {
  id: 7,
  sku: 'TR-195',
  name_ar: 'إطار 195/70',
  name_en: '',
  quantity_on_hand: '20',
  available_quantity: '20',
  sale_price: '100',
};

const TAX = {
  id: 3, name: 'ض.ق.م', code: 'VAT16', rate: '16.00',
  tax_account: 41, direction: 'sales', is_active: true,
};

const PROFILE = {
  id: PRODUCT.id,
  name: PRODUCT.name_ar,
  sku: PRODUCT.sku,
  barcode: '',
  avg_cost: '62.5',
  effective_sale_price: '100',
  sale_price_source: 'product',
  profit_per_unit: '37.5',
  profit_margin_pct: '37.5',
  last_sale_price: null,
  last_purchase_price: '62.5',
  quantity_on_hand: '20',
  available_quantity: '20',
  reserved_quantity: '0',
  inventory_valuation: '1250',
  sale_valuation: '2000',
  purchased_qty: '20',
  purchased_value: '1250',
  sold_qty: '0',
  sold_value: '0',
  is_service: false,
};

/** قيمة صفٍّ في صندوق الإجماليات بعنوانه الحرفي. */
const totalRow = (page: Page, label: string) =>
  page.locator(`.ktra-total-row:has(span:text-is("${label}"))`).locator('.ktra-total-value');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'quote-disc-e2e-token');
    localStorage.setItem('userId', 'quote-disc-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    let body: unknown = [];
    const path = url.pathname;
    if (path.endsWith('/hr/users/quote-disc-e2e-user/')) {
      body = {
        id: 'quote-disc-e2e-user', name: 'Quote Tester', role: 'manager',
        email: 'quote@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة العروض', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-08-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-08-01T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = { role: 'manager', is_manager: true, permissions: [] };
    } else if (path.endsWith('/inventory/products/') || path.endsWith('/inventory/products')) {
      body = [PRODUCT];
    } else if (path.endsWith(`/inventory/products/${PRODUCT.id}/profile/`)) {
      body = PROFILE;
    } else if (path.endsWith('/accounting/tax-rates/')) {
      body = [TAX];
    } else if (path.endsWith('/sales/settings/current/')) {
      body = { quotation_valid_days: 14, allow_document_delete: true };
    } else if (path.endsWith('/sales/quotations/')) {
      body = { count: 0, results: [] };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
});

test('خصم العرض يُكتب في الأسفل ويسبق الضريبة، وبطاقة الصنف تُظهر تكلفته', async ({ page }) => {
  await page.goto('/sales/quotations');
  await page.waitForLoadState('networkidle');

  await page.getByRole('button', { name: 'عرض جديد' }).click();
  await expect(page.getByText('عرض سعر بيع')).toBeVisible();

  // بندٌ واحد: 10 × 100 بضريبة 16% ⇒ 1,160 قبل أي خصم.
  await page.getByRole('button', { name: 'اختر منتجاً…' }).click();
  await page.getByRole('button', { name: new RegExp(PRODUCT.name_ar) }).first().click();
  const qty = page.locator('#ktra-grid-input-0-quantity');
  await qty.fill('10');
  await qty.blur();
  await page.locator('table.ktra-grid select').first().selectOption(String(TAX.id));

  await expect(totalRow(page, 'مجموع البنود')).toHaveText('1,000');
  await expect(totalRow(page, 'الضريبة')).toHaveText('160');
  await expect(totalRow(page, 'إجمالي العرض')).toHaveText('1,160');

  // «الخصم» في الأسفل مُدخَل — لا رقمٌ للقراءة — وهو خصم المستند لا خصم البند.
  const documentDiscount = page
    .locator('.ktra-total-row:has(span:text-is("الخصم"))')
    .locator('input');
  await expect(documentDiscount).toBeEditable();
  await documentDiscount.fill('200');

  // الضريبة تُحسب على 800 لا على 1,000 ⇒ 128، والإجمالي 928.
  await expect(totalRow(page, 'بعد الخصم')).toHaveText('800');
  await expect(totalRow(page, 'الضريبة')).toHaveText('128');
  await expect(totalRow(page, 'إجمالي العرض')).toHaveText('928');

  // خصم البند يبقى عموداً مستقلاً في الشبكة (لا يُخلط بخصم العرض).
  await expect(page.getByRole('columnheader', { name: 'خصم البند' })).toBeVisible();

  // تكلفة الصنف وأسعاره من داخل العرض — البطاقة المشتركة نفسها.
  await page.getByTitle('بطاقة المنتج — التكلفة والأسعار').click();
  await expect(page.getByText('سعر التكلفة (متوسط)')).toBeVisible();
  await expect(page.getByText('62.5').first()).toBeVisible();
});
