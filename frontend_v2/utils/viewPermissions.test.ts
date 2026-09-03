import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  TEMPLATE_HIDDEN_VIEWS,
  VIEW_PERMISSIONS,
  templateHidesView,
} from './viewPermissions.ts';

/* ── ISSUE #51 — القناع الحيّ: قالب الشركة يخفي شاشات كاملة ─────────────── */

test('كل مفتاح في TEMPLATE_HIDDEN_VIEWS.accounting_firm موجود في خريطة الشاشات — لا مفاتيح ميتة', () => {
  for (const view of TEMPLATE_HIDDEN_VIEWS.accounting_firm) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(VIEW_PERMISSIONS, view),
      `مفتاح ميت: ${view} غير موجود في VIEW_PERMISSIONS`,
    );
  }
});

test('لا مفاتيح مكررة داخل قائمة القالب الواحد', () => {
  const views = TEMPLATE_HIDDEN_VIEWS.accounting_firm;
  assert.equal(new Set(views).size, views.length);
});

test('accounting_firm يخفي شاشات المخزون والاستيراد والمتجر وما بعد البيع والأجهزة الحساسة', () => {
  for (const view of [
    'stock-levels', 'items-management', 'warehouses', 'stocktake',
    'deals-management', 'shipments-management', 'import-flow',
    'store-settings', 'after-sales', 'service-orders', 'sensitive-devices',
  ]) {
    assert.equal(templateHidesView(view, 'accounting_firm'), true, view);
  }
});

test('accounting_firm يخفي شاشات البضاعة الساكنة داخل مجموعة المبيعات', () => {
  // هذه الثلاث تعيش تحت «المبيعات» لا تحت «المخزون»، فبقيت ظاهرةً لمكتبٍ بلا
  // مخزون رغم أن القناع أخفى مجموعة المخزون كاملةً.
  for (const view of ['sales-delivery-notes', 'invoice-profits', 'reserved-stock']) {
    assert.equal(templateHidesView(view, 'accounting_firm'), true, view);
  }
});

test('accounting_firm يخفي شاشات المشتريات — تتّكئ على حسابات أسقطتها البذرة', () => {
  for (const view of [
    'purchase-invoices', 'purchase-receipts', 'purchase-return', 'purchase-settings',
  ]) {
    assert.equal(templateHidesView(view, 'accounting_firm'), true, view);
  }
});

test('accounting_firm لا يخفي ما تبقيه التذكرة — المبيعات والشركاء والمحاسبة والتقارير وسند الصرف', () => {
  for (const view of [
    'sales-invoices', 'sales-customers', 'accounting-coa', 'accounting-journals',
    'accounting-cheques', 'sales-customer-payments', 'reports',
    // سند الصرف يبقى ولو كان مساره الخلفي تحت `/api/logistics/`.
    'supplier-payments',
    // issue #56 — سند المصروف مستندٌ محاسبيٌّ عام، يخدم مكتب المحاسبة أيضاً.
    'accounting-expense-vouchers',
  ]) {
    assert.equal(templateHidesView(view, 'accounting_firm'), false, view);
  }
});

/* ── ISSUE #81 — «دفتر عميل»: قناع accounting_firm + سطح البيع نفسه ────── */

test('كل مفتاح في TEMPLATE_HIDDEN_VIEWS.client_book موجود في خريطة الشاشات — لا مفاتيح ميتة', () => {
  for (const view of TEMPLATE_HIDDEN_VIEWS.client_book) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(VIEW_PERMISSIONS, view),
      `مفتاح ميت: ${view} غير موجود في VIEW_PERMISSIONS`,
    );
  }
});

test('لا مفاتيح مكررة داخل قائمة client_book', () => {
  const views = TEMPLATE_HIDDEN_VIEWS.client_book;
  assert.equal(new Set(views).size, views.length);
});

test('client_book يخفي كل ما يخفيه accounting_firm', () => {
  for (const view of TEMPLATE_HIDDEN_VIEWS.accounting_firm) {
    assert.equal(templateHidesView(view, 'client_book'), true, view);
  }
});

test('client_book يزيد فوق ذلك فواتير البيع وأوامر البيع وعروض الأسعار', () => {
  for (const view of ['sales-invoices', 'sales-quotations', 'sales-orders']) {
    assert.equal(templateHidesView(view, 'client_book'), true, view);
  }
});

test('client_book لا يخفي سند القبض ولا سند الصرف ولا سند المصروف ولا المحاسبة', () => {
  for (const view of [
    'sales-customer-payments', 'supplier-payments', 'accounting-expense-vouchers',
    'accounting-coa', 'accounting-journals', 'sales-customers',
  ]) {
    assert.equal(templateHidesView(view, 'client_book'), false, view);
  }
});

test('accounting_firm لا يخفي فواتير البيع — الفرق الوحيد بينه وبين client_book', () => {
  assert.equal(templateHidesView('sales-invoices', 'accounting_firm'), false);
  assert.equal(templateHidesView('sales-invoices', 'client_book'), true);
});

test('general: صفر تغيير — لا شاشة مخفية مهما كانت', () => {
  for (const view of TEMPLATE_HIDDEN_VIEWS.accounting_firm) {
    assert.equal(templateHidesView(view, 'general'), false, view);
  }
  for (const view of TEMPLATE_HIDDEN_VIEWS.client_book) {
    assert.equal(templateHidesView(view, 'general'), false, view);
  }
});

test('غياب القالب (undefined أو null) يعامَل كـgeneral — بلا إخفاء', () => {
  assert.equal(templateHidesView('stock-levels', undefined), false);
  assert.equal(templateHidesView('stock-levels', null), false);
});

test('قالب مجهول لا يطابق أي إدخال فيسقط بلا إخفاء (فشل مفتوح آمن هنا: القالب نفسه غير معروف)', () => {
  assert.equal(templateHidesView('stock-levels', 'not-a-real-template'), false);
});

/* ── ISSUE #62 — قناتان لا تتّفقان: رابط الشاشة محكوم بالصلاحية، والشاشة نفسها
   كانت محكومة بالدور (`currentUser!.role !== "manager"` في `App.tsx`). كل شاشة
   في هذه القائمة صار حارسها `canView` — أي هذا المفتاح نفسه — فلا يعود دور
   المحاسب وعداً ميتاً. القائمة مأخوذة حرفياً من موقع الحارس القديم قبل الإصلاح. */
test('ISSUE #62: كل شاشة كانت محكومة بالدور صار لها مفتاح في VIEW_PERMISSIONS', () => {
  const formerlyRoleGatedScreens = [
    // شؤون الموظفين والإدارة
    'users', 'activity-log', 'team-time-report', 'employee-notes', 'points-management',
    // المحاسبة
    'accounting-coa', 'accounting-journals', 'accounting-journal-entry',
    'accounting-cheques', 'accounting-banks', 'accounting-bank-reconciliation',
    'accounting-general-ledger', 'accounting-trial-balance', 'accounting-vat-report',
    'accounting-landed-cost', 'accounting-fiscal-periods', 'accounting-exchange-rates',
    'accounting-balance-sheet', 'accounting-income-statement', 'accounting-vat-statements',
    'accounting-year-end-close', 'accounting-opening-balances', 'accounting-expense-vouchers',
  ];
  for (const view of formerlyRoleGatedScreens) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(VIEW_PERMISSIONS, view),
      `مفتاح مفقود: ${view} كانت محكومة بالدور ويجب أن تملك مفتاحاً الآن`,
    );
  }
});

/* «دفاتر عملائي» (`client-books`) وشاشات SQL الداخلية (`sql-products`
   وأخواتها) بقيت على حارس الدور عمداً — رابطها في `Sidebar.tsx` نفسه محكوم
   بالدور مباشرةً (`isManager` / `roles: [...]`) لا بـ`VIEW_PERMISSIONS`، فلا
   قناتين مختلفتين هناك أصلاً. إضافة مفتاح هنا بلا تحريك ذلك الرابط كانت
   ستفتح بابين متعارضين. */
test('ISSUE #62: دفاتر العملاء وشاشات SQL خارج القائمة — رابطها في Sidebar محكوم بالدور مباشرةً لا بالصلاحية', () => {
  for (const view of ['client-books', 'sql-products', 'sql-partners', 'sql-deals', 'sql-shipments']) {
    assert.equal(
      Object.prototype.hasOwnProperty.call(VIEW_PERMISSIONS, view),
      false,
      `${view} ليست جزءاً من إصلاح #62 — لا تُضِف لها مفتاحاً بلا نقل حارس الرابط في Sidebar.tsx`,
    );
  }
});
