import { test } from 'node:test';
import assert from 'node:assert/strict';
import { firstMatchRange, rankOptions } from './autocompleteRank.ts';

const CATALOG = [
  { label: 'اطار ميشلان 17', sub: 'الرصيد: 4', keywords: 'mch-17 6291041500213' },
  { label: 'اطار برجستون 16', sub: 'الرصيد: 0', keywords: 'brg-16 6291041500220' },
  { label: 'زيت محرك 5w30', sub: 'الرصيد: 12', keywords: 'oil-5w30 1234567890123' },
];

test('يجد المنتج برقمه (SKU) وهو غير معروض في القائمة', () => {
  const { matches } = rankOptions(CATALOG, 'mch-17', 8);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].label, 'اطار ميشلان 17');
});

test('يجد المنتج بجزء من الباركود', () => {
  const { matches } = rankOptions(CATALOG, '1500220', 8);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].label, 'اطار برجستون 16');
});

test('كلمتان متباعدتان في الاسم تطابقان — لا يشترط التجاور', () => {
  const { matches } = rankOptions(CATALOG, 'اطار 17', 8);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].label, 'اطار ميشلان 17');
});

test('كلمة واحدة لا تطابق ⇒ يسقط الصفّ كلّه', () => {
  const { matches } = rankOptions(CATALOG, 'اطار زيت', 8);
  assert.equal(matches.length, 0);
});

test('البادئة تسبق الاحتواء في الترتيب', () => {
  const rows = [
    { label: 'زيت فرامل' },
    { label: 'مصفاة زيت' },
  ];
  const { matches } = rankOptions(rows, 'زيت', 8);
  assert.equal(matches[0].label, 'زيت فرامل');
});

test('يُبلّغ عن العدد الكلّي فتعرف الشاشة كم أخفى السقف', () => {
  const rows = Array.from({ length: 25 }, (_, i) => ({ label: `اطار ${i}` }));
  const { matches, total } = rankOptions(rows, 'اطار', 8);
  assert.equal(matches.length, 8);
  assert.equal(total, 25);
});

test('استعلام فارغ يعيد الكلّ مقصوصاً بلا ترشيح', () => {
  const { matches, total } = rankOptions(CATALOG, '   ', 2);
  assert.equal(matches.length, 2);
  assert.equal(total, 3);
});

test('الخيار بلا keywords يسلك كما كان قبل الحقل', () => {
  const rows = [{ label: 'اطار ميشلان 17', sub: 'الرصيد: 4' }];
  assert.equal(rankOptions(rows, 'ميشلان', 8).matches.length, 1);
  assert.equal(rankOptions(rows, 'mch-17', 8).matches.length, 0);
});

test('موضع التظليل هو أول كلمة تطابق', () => {
  assert.deepEqual(firstMatchRange('اطار ميشلان 17', 'ميشلان'), { start: 5, end: 11 });
  assert.equal(firstMatchRange('اطار ميشلان 17', 'زيت'), null);
});
