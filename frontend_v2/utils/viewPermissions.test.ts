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

test('general: صفر تغيير — لا شاشة مخفية مهما كانت', () => {
  for (const view of TEMPLATE_HIDDEN_VIEWS.accounting_firm) {
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
