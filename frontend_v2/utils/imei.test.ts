import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  IMEI_LENGTH,
  imeiDigits,
  imeiState,
  isValidImei,
  isValidPhone,
  luhnIsValid,
  normalizePhone,
} from './imei.ts';

// أرقام IMEI حقيقية البنية تجتاز Luhn على خمس عشرة خانة.
const VALID = ['490154203237518', '356938035643809', '352099001761481'];

test('IMEI صحيح البنية وخانة التحقق يمرّ', () => {
  for (const imei of VALID) assert.equal(isValidImei(imei), true, imei);
});

test('تغيير خانة واحدة يُسقط IMEI صحيحاً — الاختبار يفشل لو غاب Luhn', () => {
  // 490154203237518 صحيح؛ 490154203237519 يخالفه بخانة التحقق وحدها.
  assert.equal(isValidImei('490154203237519'), false);
  assert.equal(isValidImei('490154203237511'), false);
});

test('الطول والحروف يُرفضان قبل Luhn', () => {
  assert.equal(isValidImei('49015420323751'), false);   // 14 خانة
  assert.equal(isValidImei('4901542032375180'), false); // 16 خانة
  assert.equal(isValidImei('49015420323751A'), false);  // حرف
  assert.equal(isValidImei(''), false);
  assert.equal(isValidImei(null), false);
  assert.equal(isValidImei(undefined), false);
});

test('imeiDigits يُسقط ما ليس رقماً ويقصّ عند خمس عشرة خانة', () => {
  assert.equal(imeiDigits(' 490-154 203/237518 '), '490154203237518');
  assert.equal(imeiDigits('4901542032375189999'), '490154203237518');
  assert.equal(imeiDigits('abc').length, 0);
  assert.equal(imeiDigits(null), '');
  assert.equal(IMEI_LENGTH, 15);
});

test('luhnIsValid لا يقبل سلسلة غير رقمية', () => {
  assert.equal(luhnIsValid('12a4'), false);
  assert.equal(luhnIsValid(''), false);
  assert.equal(luhnIsValid('18'), true); // 1*1 + 8*... مثال قصير معروف
});

test('حالة الحقل تفرّق بين «يكتب الآن» و«خطأ»', () => {
  assert.equal(imeiState(''), 'empty');
  assert.equal(imeiState('4901542'), 'partial');
  assert.equal(imeiState('49015420323751'), 'partial');
  assert.equal(imeiState('490154203237519'), 'invalid');
  assert.equal(imeiState('490154203237518'), 'valid');
  // نصف رقم لا يُلوَّن أحمر — الخطأ يظهر عند اكتمال الخانة الخامسة عشرة فقط.
  assert.notEqual(imeiState('49015'), 'invalid');
});

test('الهاتف يُطبَّع كما يُطبِّعه الخادم قبل التحقق', () => {
  assert.equal(normalizePhone('0599-123 456'), '0599123456');
  assert.equal(normalizePhone(' +970 59 912 3456 '), '+970599123456');
  assert.equal(isValidPhone('0599-123 456'), true);
  assert.equal(isValidPhone('+970599123456'), true);
  assert.equal(isValidPhone('12345'), false);      // أقصر من 7
  assert.equal(isValidPhone('05991234567890123'), false); // أطول من 15
  assert.equal(isValidPhone('05x9912345'), false);
  assert.equal(isValidPhone(''), false);
});
