import { test } from 'node:test';
import assert from 'node:assert/strict';
import { defaultCurrency, isBaseCurrency, rateForPayload, usdRateForPayload, validateRate } from './paymentRate.ts';

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

test('العملة الأساسية: بالعلم أو بالرمز ILS، وغياب العملة أساسية', () => {
  assert.equal(isBaseCurrency(null), true);
  assert.equal(isBaseCurrency(undefined), true);
  assert.equal(isBaseCurrency({ Code: 'USD', IsBaseCurrency: true }), true, 'العلم يسبق الرمز');
  assert.equal(isBaseCurrency({ code: 'USD', is_base: true }), true);
  assert.equal(isBaseCurrency({ Code: 'USD', IsBaseCurrency: false }), false);
  assert.equal(isBaseCurrency({ Code: 'ILS', IsBaseCurrency: false }), false, 'العلم الصريح يسبق الرمز');
  assert.equal(isBaseCurrency({ Code: 'ILS' }), true, 'بلا علم: الرمز ILS');
  assert.equal(isBaseCurrency({ code: ' ils ' }), true);
  assert.equal(isBaseCurrency({ Code: 'USD' }), false);
  assert.equal(isBaseCurrency({}), false, 'كائن بلا رمز ولا علم: ليس أساسية');
});

test('validateRate: الفارغ وغير الرقم والصفر والسالب و1 مرفوضة', () => {
  assert.equal(validateRate(''), 'اكتب سعر الصرف');
  assert.equal(validateRate('   '), 'اكتب سعر الصرف');
  assert.ok(validateRate('abc'));
  assert.ok(validateRate('3,7'), 'الفاصلة العشرية غير مقبولة');
  assert.ok(validateRate('1e3'));
  assert.ok(validateRate('Infinity'));
  assert.ok(validateRate('-3.7'));
  assert.equal(validateRate('0'), 'سعر الصرف يجب أن يكون أكبر من صفر');
  assert.equal(validateRate('0.0'), 'سعر الصرف يجب أن يكون أكبر من صفر');
  assert.equal(validateRate('1'), 'سعر 1 لعملة أجنبية غير مقبول');
  assert.equal(validateRate('1.000'), 'سعر 1 لعملة أجنبية غير مقبول');
});

test('validateRate: الأسعار الصحيحة تمرّ، ويُقصّ الفراغ', () => {
  assert.equal(validateRate('3.7'), null);
  assert.equal(validateRate(' 3.71 '), null);
  assert.equal(validateRate('0.27'), null);
  assert.equal(validateRate('1.0001'), null);
  assert.equal(validateRate('4'), null);
});

test('rateForPayload: تُحذف للأساسية وتُقصّ للأجنبية', () => {
  assert.equal(rateForPayload(true, '3.7'), undefined);
  assert.equal(rateForPayload(true, ''), undefined);
  assert.equal(rateForPayload(false, ' 3.7 '), '3.7');
  assert.equal(rateForPayload(false, ''), '');
});

test('defaultCurrency: الأساسية صراحةً ولو لم تكن الأولى، وإلا الأولى', () => {
  const usd = { Code: 'USD', IsBaseCurrency: false };
  const ils = { Code: 'ILS', IsBaseCurrency: true };
  assert.equal(defaultCurrency([usd, ils]), ils);
  assert.equal(defaultCurrency([usd, { Code: 'EUR' }]), usd, 'لا أساسية: الأولى');
  assert.equal(defaultCurrency([]), undefined);
});
