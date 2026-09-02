import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveClientBookTenantId } from './clientBookAccess.ts';

test('بلا دفتر مُدار ولا ارتباط ⇒ لا دفتر', () => {
  assert.equal(
    resolveClientBookTenantId({ managedTenantId: null, linkedTenantId: null, linkedAccessible: false }),
    null,
  );
});

test('دفترٌ مُدار وحده ⇒ هو الدفتر', () => {
  assert.equal(
    resolveClientBookTenantId({ managedTenantId: 7, linkedTenantId: null, linkedAccessible: false }),
    7,
  );
});

test('ارتباطٌ نشط وحده ⇒ دفتر الارتباط', () => {
  assert.equal(
    resolveClientBookTenantId({ managedTenantId: null, linkedTenantId: 3, linkedAccessible: true }),
    3,
  );
});

test('ارتباطٌ غير نشط (معلّق/مرفوض) ⇒ لا دفتر رغم وجود tenant_id', () => {
  assert.equal(
    resolveClientBookTenantId({ managedTenantId: null, linkedTenantId: 3, linkedAccessible: false }),
    null,
  );
});

test('الحقلان معاً (hybrid) ⇒ الدفتر المُدار يفوز', () => {
  assert.equal(
    resolveClientBookTenantId({ managedTenantId: 7, linkedTenantId: 3, linkedAccessible: true }),
    7,
  );
});

test('صفرٌ قيمةٌ صالحة لدفتر مُدار — لا تُعامَل كغياب', () => {
  assert.equal(
    resolveClientBookTenantId({ managedTenantId: 0, linkedTenantId: null, linkedAccessible: false }),
    0,
  );
});
