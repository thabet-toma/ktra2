import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  compareBaselines,
  missingValues,
  normalise,
  sortedBaseline,
  toCategory,
  type ParityBaseline,
  type ViewCensus,
} from './parityCensus.ts';

const view = (over: Partial<Record<string, string[]>> = {}): ViewCensus => ({
  path: '/x',
  buttons: toCategory(over.buttons ?? ['حفظ', 'إلغاء']),
  fields: toCategory(over.fields ?? ['name=q']),
  tabs: toCategory(over.tabs ?? []),
  tableHeaders: toCategory(over.tableHeaders ?? ['التاريخ', 'المبلغ']),
  toolbarItems: toCategory(over.toolbarItems ?? ['طباعة']),
});

const baseline = (views: Record<string, ViewCensus>): ParityBaseline => ({
  schemaVersion: 1,
  viewport: { width: 1440, height: 900 },
  views,
  skipped: {},
});

test('حصيلةٌ مطابقة تمرّ خضراء بلا نقصان ولا زيادة', () => {
  const b = baseline({ dashboard: view() });
  const result = compareBaselines(b, baseline({ dashboard: view() }));
  assert.deepEqual(result.failures, []);
  assert.deepEqual(result.additions, []);
});

test('**سقوط زرٍّ واحد يُحمِر الحارس** — وهذا هو سبب وجوده', () => {
  const before = baseline({ dashboard: view({ buttons: ['حفظ', 'إلغاء'] }) });
  const after = baseline({ dashboard: view({ buttons: ['حفظ'] }) });

  const { failures } = compareBaselines(before, after);
  assert.equal(failures.length, 1);
  assert.match(failures[0], /^dashboard\.buttons: missing /);
  assert.match(failures[0], /إلغاء/);
});

test('سقوط عمود أو تبويب أو حقل يُحمِر كذلك — لا فئة بلا حراسة', () => {
  const before = baseline({
    s: view({ tableHeaders: ['التاريخ', 'المبلغ'], tabs: ['عام', 'مرفقات'], fields: ['name=q', 'name=note'] }),
  });
  const after = baseline({
    s: view({ tableHeaders: ['التاريخ'], tabs: ['عام'], fields: ['name=q'] }),
  });

  const { failures } = compareBaselines(before, after);
  const categories = failures.map((f) => f.split(':')[0]);
  assert.deepEqual(categories.sort(), ['s.fields', 's.tableHeaders', 's.tabs']);
});

test('اختفاء الشاشة كلها فشلٌ صريح لا صمت', () => {
  const { failures } = compareBaselines(baseline({ a: view(), b: view() }), baseline({ a: view() }));
  assert.deepEqual(failures, ['b: entire view census is missing']);
});

test('الزيادة تحذيرٌ لا فشل — الميزة الجديدة ليست عطلاً', () => {
  const before = baseline({ dashboard: view({ buttons: ['حفظ'] }) });
  const after = baseline({ dashboard: view({ buttons: ['حفظ', 'طيّ الشريط'] }) });

  const { failures, additions } = compareBaselines(before, after);
  assert.deepEqual(failures, []);
  assert.equal(additions.length, 1);
  assert.match(additions[0], /طيّ الشريط/);
});

test('شاشةٌ جديدة كلياً زيادةٌ لا فشل', () => {
  const { failures, additions } = compareBaselines(baseline({ a: view() }), baseline({ a: view(), z: view() }));
  assert.deepEqual(failures, []);
  assert.deepEqual(additions, ['z: new view census']);
});

test('التكرار محسوب: عمودان بنفس العنوان يلزمهما عمودان', () => {
  assert.deepEqual(missingValues(['المبلغ', 'المبلغ'], ['المبلغ']), ['المبلغ']);
  assert.deepEqual(missingValues(['المبلغ', 'المبلغ'], ['المبلغ', 'المبلغ']), []);
});

test('التوحيد يُسقط فروق المسافات وحدها', () => {
  assert.equal(normalise('  تاريخ   الاستحقاق \n'), 'تاريخ الاستحقاق');
  assert.equal(normalise(null), '');
  /* ...ولا يُسقط زخرفةً ملتصقة: لذلك تُخفى بـaria-hidden عند المصدر لا هنا. */
  assert.equal(normalise('تاريخ الاستحقاق▼'), 'تاريخ الاستحقاق▼');
});

test('الفرز مستقرّ فيخرج نفس الملفّ من تشغيلين', () => {
  const messy = baseline({ zeta: view(), alpha: view() });
  messy.skipped = { zulu: 'x', alfa: 'y' };
  const once = JSON.stringify(sortedBaseline(messy));
  const twice = JSON.stringify(sortedBaseline(JSON.parse(once) as ParityBaseline));
  assert.equal(once, twice);
  assert.deepEqual(Object.keys(sortedBaseline(messy).views), ['alpha', 'zeta']);
  assert.deepEqual(Object.keys(sortedBaseline(messy).skipped), ['alfa', 'zulu']);
});
