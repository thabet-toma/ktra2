import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filterSettingsSections, normalizeSettingsSearch } from './settingsIndex.ts';

const SECTIONS = [
  { id: 'tax', title: 'الضرائب', description: 'نسبة الضريبة الافتراضية', keywords: ['خصم المصدر'] },
  { id: 'currency', title: 'العملات والدفع', description: 'العملة الافتراضية وطريقة الدفع', keywords: ['الصندوق / البنك'] },
  { id: 'shipping', title: 'الشحن المحلي', description: 'حساب إيراد الشحن' },
];
const ids = (query: string) => filterSettingsSections(SECTIONS, query).map((section) => section.id);

test('بحثٌ فارغ يعيد الأقسام كلّها بترتيبها', () => {
  assert.deepEqual(ids(''), ['tax', 'currency', 'shipping']);
  assert.deepEqual(ids('   '), ['tax', 'currency', 'shipping']);
});

test('يطابق العنوانَ والوصفَ وأسماءَ الحقول داخل القسم', () => {
  assert.deepEqual(ids('الضرائب'), ['tax']);
  assert.deepEqual(ids('طريقة الدفع'), ['currency']);
  assert.deepEqual(ids('البنك'), ['currency']);
  assert.deepEqual(ids('خصم المصدر'), ['tax']);
});

test('كلُّ كلمةٍ في البحث يجب أن تطابق — لا يكفي بعضُها', () => {
  assert.deepEqual(ids('الشحن الضريبة'), []);
  assert.deepEqual(ids('إيراد الشحن'), ['shipping']);
});

test('الهمزاتُ والتاءُ المربوطةُ والتشكيلُ لا تُسقط المطابقة', () => {
  assert.deepEqual(ids('ضريبه'), ['tax']);
  assert.deepEqual(ids('ايراد'), ['shipping']);
  assert.deepEqual(ids('العُملة'), ['currency']);
});

test('التطبيعُ نفسُه', () => {
  assert.equal(normalizeSettingsSearch('  أإآ ة ى ـ  '), 'ااا ه ي');
  assert.equal(normalizeSettingsSearch('ABC'), 'abc');
});
