import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_FISCAL_GRANULARITY,
  FISCAL_GRANULARITY_OPTIONS,
  MAX_FISCAL_YEAR,
  MIN_FISCAL_YEAR,
  defaultFiscalStart,
  isValidFiscalStart,
  nextFiscalStart,
} from './fiscalYearChoice.ts';

test('الافتراض المعبّأ هو أول كانون الثاني من سنة اليوم', () => {
  assert.equal(defaultFiscalStart(new Date(2026, 8, 14, 10, 0, 0)), '2026-01-01');
  assert.equal(defaultFiscalStart(new Date(2031, 0, 1, 0, 0, 0)), '2031-01-01');
});

test('الافتراض يُبنى محلّياً لا عبر UTC — وإلا انزاح إلى السنة السابقة', () => {
  // أول كانون الثاني منتصف الليل في منطقة موجبة: `toISOString()` تُرجع 31/12.
  assert.equal(defaultFiscalStart(new Date(2026, 0, 1, 0, 30, 0)), '2026-01-01');
});

test('الافتراض شهري — لأن المحاسب يقفل شهراً بعد شهر', () => {
  assert.equal(DEFAULT_FISCAL_GRANULARITY, 'monthly');
  assert.deepEqual(
    FISCAL_GRANULARITY_OPTIONS.map((option) => option.key),
    ['monthly', 'yearly'],
  );
});

test('الحدّان يطابقان ما يفرضه الخادم', () => {
  assert.equal(MIN_FISCAL_YEAR, 2000);
  assert.equal(MAX_FISCAL_YEAR, 2100);
});

test('الغلط المطبعيّ يُردّ قبل رحلة الشبكة', () => {
  assert.equal(isValidFiscalStart(''), false);
  assert.equal(isValidFiscalStart('   '), false);
  assert.equal(isValidFiscalStart('2026'), false);
  assert.equal(isValidFiscalStart('2026-1-1'), false);
  assert.equal(isValidFiscalStart('01/01/2026'), false);
  assert.equal(isValidFiscalStart('abc'), false);
});

test('تاريخ يطابق الشكل ويستحيل تقويمياً يُردّ أيضاً', () => {
  assert.equal(isValidFiscalStart('2026-02-31'), false);
  assert.equal(isValidFiscalStart('2026-13-01'), false);
  assert.equal(isValidFiscalStart('2026-00-10'), false);
});

test('سنة خارج الحدّين تُردّ ولو كان التاريخ صالحاً', () => {
  assert.equal(isValidFiscalStart('1999-01-01'), false);
  assert.equal(isValidFiscalStart('2101-01-01'), false);
});

test('البدء من أيّ يوم مقبول — لا كانون الثاني وحده', () => {
  assert.equal(isValidFiscalStart('2026-01-01'), true);
  assert.equal(isValidFiscalStart(' 2026-07-01 '), true);
  assert.equal(isValidFiscalStart('2026-03-15'), true);
  assert.equal(isValidFiscalStart('2024-02-29'), true);
  assert.equal(isValidFiscalStart(`${MIN_FISCAL_YEAR}-01-01`), true);
  assert.equal(isValidFiscalStart(`${MAX_FISCAL_YEAR}-12-31`), true);
});

test('السنة التالية تبدأ في اليوم التالي لآخر فترة — لا في كانون الثاني', () => {
  // شركةٌ سنتُها تموزيّة: بلا هذا كانت تُمنَع من إنشاء سنتها الثانية أصلاً،
  // لأن كانون الثاني يتقاطع مع نصف سنتها القائمة فيردّه الخادم.
  assert.equal(
    nextFiscalStart(['2040-07-31', '2041-06-30', '2040-12-31']),
    '2041-07-01',
  );
});

test('آخرُ فترةٍ تُلتقط بالترتيب لا بترتيب وصولها من الخادم', () => {
  assert.equal(nextFiscalStart(['2041-06-30', '2040-07-31']), '2041-07-01');
});

test('نهايةُ سنةٍ تقويمية تعطي أول كانون الثاني التالي', () => {
  assert.equal(nextFiscalStart(['2026-12-31']), '2027-01-01');
});

test('اليومُ التالي لا يقفز عند نهايات الأشهر ولا في سنةٍ كبيسة', () => {
  assert.equal(nextFiscalStart(['2044-02-28']), '2044-02-29');
  assert.equal(nextFiscalStart(['2045-02-28']), '2045-03-01');
  assert.equal(nextFiscalStart(['2040-01-31']), '2040-02-01');
});

// ملاحظة صدق: قراءةُ النصّ بلا وقتٍ تُفسَّر UTC فتنزاح يوماً — لكنها لا تنزاح
// إلا في منطقةٍ زمنيّةٍ **سالبة**، والبوّابة تعمل في موجبة. فالحرزُ من ذلك
// لاحقةُ `T00:00:00` في الشيفرة وتعليقُها، لا تأكيدٌ هنا لا يستطيع السقوط.

test('بلا فتراتٍ بعد، الافتراضُ أول كانون الثاني كما في باب الإنشاء', () => {
  const now = new Date(2026, 8, 14, 10, 0, 0);
  assert.equal(nextFiscalStart([], now), '2026-01-01');
  assert.equal(nextFiscalStart(['', 'ليس تاريخاً', '2026-02-31'], now), '2026-01-01');
});
