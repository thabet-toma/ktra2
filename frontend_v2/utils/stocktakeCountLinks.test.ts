import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  canonicalQuantityText,
  countInputVariance,
  countLinkScopeLabel,
  countLinkStatusLabel,
  countUncounted,
  filterCountLines,
  filterCountLinkCategoryIds,
  groupCountLines,
  INVALID_COUNTED_MESSAGE,
  normalizeCountedInput,
  parseCountedInput,
  stocktakeCountScopeIds,
  THOUSANDS_SEPARATOR_MESSAGE,
} from './stocktakeCountLinks.ts';
import type { PublicStocktakeCountLine } from '../types/inventory.ts';

/**
 * K4 — منطق نافذة «رابط للموظف» وصفحة العدّ الجوالية: التقليم، تصفية ما يُرسل،
 * تسمية الحالة، وتحويل خانة الإدخال. كلّه دوالّ صرفة كي يُختبر بلا متصفّح.
 */

const CATEGORIES = [
  { id: 11, name: 'قطع غيار', parent: null },
  { id: 12, name: 'محركات', parent: 11 },
  { id: 13, name: 'فحمات', parent: 12 },
  { id: 14, name: 'إطارات', parent: null },
  { id: 15, name: 'زيوت', parent: null },
];

const line = (overrides: Partial<PublicStocktakeCountLine> = {}): PublicStocktakeCountLine => ({
  line_id: 1,
  sku: 'SP-1',
  name: 'فلتر زيت',
  brand: 'مان',
  category_path: 'قطع غيار ‹ محركات',
  uom: 'حبة',
  system_quantity: '10.0000',
  counted_quantity: null,
  counted_by_name: '',
  ...overrides,
});

test('التقليم: العقدة وأسلافها فقط — والأشقّاء لا يُعرضون', () => {
  const scope = stocktakeCountScopeIds(CATEGORIES, [13]);
  assert.deepEqual(scope.visible, [11, 12, 13]);
  assert.deepEqual(scope.direct, [13]);
});

test('التقليم: عدة تصنيفات مباشرة تُوحَّد وتُرتَّب', () => {
  const scope = stocktakeCountScopeIds(CATEGORIES, [14, 12, 12, 999]);
  assert.deepEqual(scope.visible, [11, 12, 14]);
  assert.deepEqual(scope.direct, [12, 14]);
});

test('تصفية المرسَل: التأشير على أبٍ لا يُرسل معرّفه بلا بنود مباشرة', () => {
  const scope = stocktakeCountScopeIds(CATEGORIES, [13, 14]);
  assert.deepEqual(
    filterCountLinkCategoryIds([11, 12, 13, 14, 15], scope.direct),
    [13, 14],
  );
});

test('تسمية الحالة: الخمس كما في التذكرة', () => {
  assert.equal(countLinkStatusLabel('active', 0), 'لم يبدأ');
  assert.equal(countLinkStatusLabel('active', 3), 'يعدّ');
  assert.equal(countLinkStatusLabel('finished', 5), 'أنهى');
  assert.equal(countLinkStatusLabel('expired', 0), 'منتهٍ');
  assert.equal(countLinkStatusLabel('revoked', 0), 'مُبطَل');
});

test('تسمية النطاق: كل الجرد أو عدد التصنيفات', () => {
  assert.equal(countLinkScopeLabel(null), 'كل الجرد');
  assert.equal(countLinkScopeLabel([12]), 'تصنيف واحد');
  assert.equal(countLinkScopeLabel([12, 14]), 'تصنيفان');
  assert.equal(countLinkScopeLabel([12, 14, 15]), '3 تصنيفات');
  assert.equal(countLinkScopeLabel([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]), '11 تصنيفاً');
});

test('تحويل الإدخال: أرقام عربية-هندية وفاصلة عشرية عربية وفاصلة ASCII', () => {
  assert.equal(normalizeCountedInput('١٢٫٥'), '12.5');
  assert.equal(normalizeCountedInput('۱۲٫۵'), '12.5');
  assert.equal(normalizeCountedInput('12,5'), '12.5');
  assert.equal(normalizeCountedInput('  7  '), '7');
});

test('تحويل الإدخال: فراغ ⇒ مسح، وصفرٌ كميةٌ حقيقية', () => {
  assert.deepEqual(parseCountedInput(''), { ok: true, value: null });
  assert.deepEqual(parseCountedInput('   '), { ok: true, value: null });
  assert.deepEqual(parseCountedInput('٠'), { ok: true, value: '0' });
  assert.deepEqual(parseCountedInput('1.2500'), { ok: true, value: '1.25' });
});

test('تحويل الإدخال: سالب وغير رقمي وأكثر من أربع منازل ⇒ خطأ محلي', () => {
  for (const raw of ['-5', '1.23456', 'نص', '1,2,3', '12.٣٤٥٦٧']) {
    const parsed = parseCountedInput(raw);
    assert.equal(parsed.ok, false, raw);
  }
});

test('الدقّة: 14 رقماً صحيحاً بأربعة كسور تبقى نصّاً حرفياً — لا Number', () => {
  assert.deepEqual(parseCountedInput('12345678901234.5678'), {
    ok: true,
    value: '12345678901234.5678',
  });
});

test('الدقّة: 15 رقماً صحيحاً تتجاوز عمود الخادم ⇒ خطأ محلي', () => {
  assert.deepEqual(parseCountedInput('123456789012345.6'), {
    ok: false,
    error: INVALID_COUNTED_MESSAGE,
  });
});

test('الشكل المرسَل: أصفارٌ زائدة ونقطةٌ يتيمة تُحذف بلا Number', () => {
  assert.equal(canonicalQuantityText('.5'), '0.5');
  assert.equal(canonicalQuantityText('5.'), '5');
  assert.equal(canonicalQuantityText('007.50'), '7.5');
  assert.equal(canonicalQuantityText('0.0000'), '0');
  assert.equal(canonicalQuantityText('١٢٫٥'), '12.5');
  assert.equal(canonicalQuantityText('12345678901234.5678'), '12345678901234.5678');
  assert.equal(canonicalQuantityText(''), '');
});

test('فاصلة الآلاف: «1,250» خطأٌ محلي لا كسر 1.25', () => {
  for (const raw of ['1,250', '1,250,000', '١,٢٥٠']) {
    assert.deepEqual(parseCountedInput(raw), {
      ok: false,
      error: THOUSANDS_SEPARATOR_MESSAGE,
    });
  }
  // فاصلةٌ عشرية عادية (لا ثلاث خانات بعدها) تبقى كسراً.
  assert.deepEqual(parseCountedInput('2,5'), { ok: true, value: '2.5' });
});

test('الفرق: المعدود − النظام حين يصحّ الرقم، وإلا لا فرق', () => {
  assert.equal(countInputVariance('10.0000', '12.5'), 2.5);
  assert.equal(countInputVariance('10', '4'), -6);
  assert.equal(countInputVariance('10', '10'), 0);
  assert.equal(countInputVariance('10', ''), null);
  assert.equal(countInputVariance('10', '-1'), null);
});

test('التجميع: بالمسار، و«بدون تصنيف» أخيراً', () => {
  const groups = groupCountLines([
    line({ line_id: 1, name: 'أ', category_path: 'زيوت' }),
    line({ line_id: 2, name: 'ب', category_path: '' }),
    line({ line_id: 3, name: 'ج', category_path: 'إطارات' }),
    line({ line_id: 4, name: 'د', category_path: 'زيوت' }),
  ]);
  assert.deepEqual(groups.map((group) => group.label), ['إطارات', 'زيوت', 'بدون تصنيف']);
  assert.deepEqual(groups[1].lines.map((row) => row.line_id), [1, 4]);
});

test('الفلترة: بحثٌ في الاسم والرمز والبراند، و«غير المعدود فقط» يقرأ القيم المحلية', () => {
  const rows = [
    line({ line_id: 1, name: 'فلتر زيت', sku: 'SP-101', brand: 'مان', counted_quantity: '3' }),
    line({ line_id: 2, name: 'طرمبة ماء', sku: 'SP-104', brand: 'بوش' }),
    line({ line_id: 3, name: 'إطار', sku: 'SP-105', brand: 'ميشلان' }),
  ];
  assert.deepEqual(
    filterCountLines(rows, { query: 'بوش', uncountedOnly: false, values: {} })
      .map((row) => row.line_id),
    [2],
  );
  assert.deepEqual(
    filterCountLines(rows, { query: '', uncountedOnly: true, values: { 3: '١٢' } })
      .map((row) => row.line_id),
    [2],
  );
});

test('عدّ الباقي بلا عدّ يقرأ القيم المحلية ويعدّ الصفر معدوداً', () => {
  const rows = [line({ line_id: 1 }), line({ line_id: 2 }), line({ line_id: 3 })];
  assert.equal(countUncounted(rows, {}), 3);
  assert.equal(countUncounted(rows, { 1: '0', 2: '4' }), 1);
  // القيمة غير الصالحة ليست عدّاً — تُحتسب «بلا عدّ» في تحذير الإنهاء.
  assert.equal(countUncounted(rows, { 1: '-5', 2: '4' }), 2);
});
