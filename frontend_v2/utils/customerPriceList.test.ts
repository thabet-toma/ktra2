import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hasRecordedCustomerPrice } from './customerPriceList.ts';

test('سعرٌ صفريّ مسجَّل سعرٌ حقيقيّ — لا يُسقَط من خريطة الزبون', () => {
  assert.equal(hasRecordedCustomerPrice('0'), true);
  assert.equal(hasRecordedCustomerPrice('0.0000'), true);
  assert.equal(hasRecordedCustomerPrice(0), true);
});

test('سعرٌ موجب يبقى', () => {
  assert.equal(hasRecordedCustomerPrice('12.5000'), true);
  assert.equal(hasRecordedCustomerPrice(7), true);
});

test('الفارغ يبقى فارغاً — لا صفرَ مختلَق', () => {
  assert.equal(hasRecordedCustomerPrice(null), false);
  assert.equal(hasRecordedCustomerPrice(undefined), false);
  assert.equal(hasRecordedCustomerPrice(''), false);
  assert.equal(hasRecordedCustomerPrice('   '), false);
});
