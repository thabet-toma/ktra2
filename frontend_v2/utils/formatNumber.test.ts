import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatBalanceWithSide, formatPartyBalance } from './formatNumber.ts';

// عزلٌ اتّجاهيّ حول الرقم: بدونه يرسم RTL السالبَ في آخر الرقم («1,112-»).
const iso = (s: string) => `\u2066${s}\u2069`;

test('رصيد الأستاذ (مدين − دائن): المدين سالب ومسمّى، والدائن موجب ومسمّى', () => {
  assert.equal(formatBalanceWithSide(1888), `${iso('-1,888')} مدين`);
  assert.equal(formatBalanceWithSide(-1112), `${iso('1,112')} دائن`);
  assert.equal(formatBalanceWithSide('1234.56'), `${iso('-1,234.56')} مدين`);
  assert.equal(formatBalanceWithSide(-187.5), `${iso('187.5')} دائن`);
});

test('السالب محصورٌ داخل العزل فلا ينقلب لآخر الرقم في RTL', () => {
  const out = formatBalanceWithSide(500);
  assert.ok(out.startsWith('\u2066-'), out);
});

test('الصفر بلا جانب وبلا إشارة', () => {
  assert.equal(formatBalanceWithSide(0), '0');
  assert.equal(formatBalanceWithSide(-0), '0');
  assert.equal(formatBalanceWithSide(0.001), '0');
  assert.equal(formatBalanceWithSide(-0.004), '0');
});

test('المدخل غير الصالح يعيد الافتراضي', () => {
  assert.equal(formatBalanceWithSide(null), '0');
  assert.equal(formatBalanceWithSide(undefined), '0');
  assert.equal(formatBalanceWithSide(''), '0');
  assert.equal(formatBalanceWithSide('abc', '—'), '—');
});

test('رصيد العميل (إشارة الخادم: موجب = عليه لنا) يُعرض مديناً سالباً', () => {
  assert.equal(formatPartyBalance('24751.5', false), `${iso('-24,751.5')} مدين`);
  assert.equal(formatPartyBalance('-150', false), `${iso('150')} دائن`);
});

test('رصيد الطرف الدائن (مورّد/مخلّص — موجب = له علينا) يُعرض دائناً موجباً', () => {
  assert.equal(formatPartyBalance('4000', true), `${iso('4,000')} دائن`);
  assert.equal(formatPartyBalance('-2580.41', true), `${iso('-2,580.41')} مدين`);
});

test('القاعدة واحدة للطرفين: الجهة نفسها تُكتب بالإشارة نفسها', () => {
  // عميلٌ عليه 1000 ومورّدٌ علينا له… عكسه: مورّدٌ دفعنا له زيادةً 1000 — كلاهما «مدين».
  assert.equal(formatPartyBalance(1000, false), formatPartyBalance(-1000, true));
  assert.equal(formatPartyBalance(0, true), '0');
});
