import { test } from 'node:test';
import assert from 'node:assert/strict';
import { usdRateForPayload } from './paymentRate.ts';

test('سعر موجب يُرسل كما هو', () => {
  assert.equal(usdRateForPayload(3.24), 3.24);
  assert.equal(usdRateForPayload('3.62'), 3.62);
});

test('لا صفر ولا قيمة افتراضية تُرسل بصمت', () => {
  for (const v of [0, '0', '', null, undefined, 'abc', -3.5, Number.NaN]) {
    assert.equal(usdRateForPayload(v), undefined, `value=${String(v)}`);
  }
});

test('المفتاح يغيب عن JSON فلا يمحو التعديلُ الجزئي سعراً محفوظاً', () => {
  const body = JSON.parse(JSON.stringify({ amount: 100, usd_to_ils: usdRateForPayload(0) }));
  assert.equal('usd_to_ils' in body, false);
});
