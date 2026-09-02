import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deriveOfficeClientType } from './officeClientType.ts';

test('بلا الحقلين ⇒ زبونٌ غير مربوط', () => {
  assert.equal(deriveOfficeClientType(null, null), 'unlinked');
  assert.equal(deriveOfficeClientType(undefined, undefined), 'unlinked');
});

test('دفترٌ مُدار وحده ⇒ managed', () => {
  assert.equal(deriveOfficeClientType(7, null), 'managed');
});

test('ارتباطٌ وحده ⇒ engaged', () => {
  assert.equal(deriveOfficeClientType(null, 3), 'engaged');
});

test('الحقلان معاً ⇒ hybrid — لا يكذب أحدهما على الآخر', () => {
  assert.equal(deriveOfficeClientType(7, 3), 'hybrid');
});

test('صفرٌ قيمةٌ صالحة لا تُعامَل كغياب', () => {
  // معرّف 0 غير واقعي عملياً (AutoField يبدأ من 1) لكن الدالة لا تخلط بينه
  // وبين null/undefined — الفحص `!= null` صريح لا `!value`.
  assert.equal(deriveOfficeClientType(0, null), 'managed');
});
