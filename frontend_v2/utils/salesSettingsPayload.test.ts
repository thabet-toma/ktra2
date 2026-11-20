import { test } from 'node:test';
import assert from 'node:assert/strict';
import { salesSettingsWritablePayload } from './salesSettingsPayload.ts';
import type { SalesSettings } from '../services/salesApi';

const base = {
  id: 7,
  updated_at: '2026-09-30T09:00:00Z',
  default_customer: 3,
  default_customer_name: 'زبون نقدي',
  default_currency: 1,
  default_currency_code: 'ILS',
  default_payment_type: 'cash',
  delivery_doc_label: 'إرسالية',
  standalone_delivery_label: 'سند تسليم',
  allow_standalone_delivery: false,
  allow_edit_delivery: false,
} as unknown as SalesSettings;

test('قسم «مستند التسليم» يُرسَل عند الحفظ — كان يسقط بصمت', () => {
  const payload = salesSettingsWritablePayload(base);
  assert.equal(payload.delivery_doc_label, 'إرسالية');
  assert.equal(payload.standalone_delivery_label, 'سند تسليم');
  assert.equal(payload.allow_standalone_delivery, false);
  assert.equal(payload.allow_edit_delivery, false);
});

test('الحقول المقروءة فقط لا تُرسَل', () => {
  const payload = salesSettingsWritablePayload(base) as Record<string, unknown>;
  for (const key of ['id', 'updated_at', 'default_customer_name', 'default_currency_code']) {
    assert.equal(key in payload, false, key);
  }
  assert.equal(payload.default_customer, 3);
});

test('سياسة ترحيل ما لم يوافق عليه الزبون تُرسَل عند الحفظ', () => {
  const payload = salesSettingsWritablePayload({
    ...base, customer_approval_post_policy: 'save_only',
  } as SalesSettings);
  assert.equal(payload.customer_approval_post_policy, 'save_only');
});

test('عمود السعر في جدول المنتجات يُرسَل عند الحفظ', () => {
  const payload = salesSettingsWritablePayload({
    ...base, product_price_column: 'inventory_avg',
  } as SalesSettings);
  assert.equal(payload.product_price_column, 'inventory_avg');
});

test('طريقة تكلفة المبيعات وحساب الفروقات يُرسلان عند الحفظ بينما يسقط الاسم المقروء فقط', () => {
  const payload = salesSettingsWritablePayload({
    ...base,
    cogs_cost_method: 'standard',
    cost_variance_account: 5190,
    cost_variance_account_name: 'فروقات تكلفة المبيعات',
  } as SalesSettings) as Record<string, unknown>;
  assert.equal(payload.cogs_cost_method, 'standard');
  assert.equal(payload.cost_variance_account, 5190);
  assert.equal('cost_variance_account_name' in payload, false);
});
