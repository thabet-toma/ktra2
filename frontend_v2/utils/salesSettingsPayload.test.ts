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
