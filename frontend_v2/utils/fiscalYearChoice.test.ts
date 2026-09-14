import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_FISCAL_GRANULARITY,
  FISCAL_GRANULARITY_OPTIONS,
  MAX_FISCAL_YEAR,
  MIN_FISCAL_YEAR,
  currentFiscalYear,
  isValidFiscalYear,
} from './fiscalYearChoice.ts';

test('الافتراض المعروض هو سنة اليوم', () => {
  assert.equal(currentFiscalYear(new Date('2026-09-14T10:00:00Z')), 2026);
  assert.equal(currentFiscalYear(new Date('2031-01-01T00:00:00Z')), 2031);
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
  assert.equal(isValidFiscalYear(202), false);
  assert.equal(isValidFiscalYear(20266), false);
  assert.equal(isValidFiscalYear(''), false);
  assert.equal(isValidFiscalYear('  '), false);
  assert.equal(isValidFiscalYear('2026.5'), false);
  assert.equal(isValidFiscalYear('abc'), false);
});

test('السنة الصالحة تمرّ رقماً كانت أو نصّاً', () => {
  assert.equal(isValidFiscalYear(2026), true);
  assert.equal(isValidFiscalYear(' 2026 '), true);
  assert.equal(isValidFiscalYear(MIN_FISCAL_YEAR), true);
  assert.equal(isValidFiscalYear(MAX_FISCAL_YEAR), true);
});
