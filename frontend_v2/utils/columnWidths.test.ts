import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MIN_COLUMN_WIDTH,
  MIN_ROW_HEIGHT,
  autoFitColumnWidth,
  columnWidthsKey,
  nextColumnWidth,
  nextRowHeight,
  readSizes,
  rowHeightsKey,
  writeSizes,
} from './columnWidths.ts';

const memoryStorage = (seed: Record<string, string> = {}) => {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    dump: () => Object.fromEntries(data),
  };
};

test('مفتاح الحفظ يجمع نطاق الجدول وأعمدته', () => {
  assert.equal(
    columnWidthsKey('/super-admin/development-notes', ['title', 'status']),
    'ktra_table_widths_/super-admin/development-notes_title,status',
  );
});

test('السحب لليمين يوسّع العمود في LTR، ولليسار في RTL', () => {
  assert.equal(nextColumnWidth(120, 30, false), 150);
  assert.equal(nextColumnWidth(120, -30, true), 150);
});

test('العرض لا ينزل تحت الحد الأدنى مهما سُحب', () => {
  assert.equal(nextColumnWidth(60, -500, false), MIN_COLUMN_WIDTH);
});

test('الحفظ والقراءة يدوران على نفس المفتاح، والقيم غير الرقمية تُهمَل', () => {
  const storage = memoryStorage();
  writeSizes('k', { title: 220, status: 90 }, storage);
  assert.deepEqual(readSizes('k', storage), { title: 220, status: 90 });

  const dirty = memoryStorage({ k: '{"title":220,"status":"wide","bad":null}' });
  assert.deepEqual(readSizes('k', dirty), { title: 220 });
});

test('قراءة مخزون تالف لا ترمي — تُعيد فارغاً', () => {
  assert.deepEqual(readSizes('k', memoryStorage({ k: 'not-json' })), {});
  assert.deepEqual(readSizes('k', memoryStorage()), {});
});

test('العرض التلقائي يكبر مع أطول نص ويحترم الحدّين', () => {
  const short = autoFitColumnWidth('الحالة', ['تم']);
  const long = autoFitColumnWidth('الوصف', ['كلمة'.repeat(30)]);
  assert.ok(long > short, 'النص الأطول يعطي عموداً أعرض');
  assert.ok(short >= 80, 'لا ينكمش تحت الحد الأدنى');
  assert.ok(long <= 420, 'لا يتجاوز الحد الأقصى');
});

test('مفتاح ارتفاعات الصفوف مستقل عن مفتاح الأعمدة', () => {
  const scope = '/super-admin/development-notes';
  assert.notEqual(rowHeightsKey(scope), columnWidthsKey(scope, ['title']));
  assert.match(rowHeightsKey(scope), /development-notes$/);
});

test('سحب حدّ الصف لأسفل يزيد ارتفاعه، ولأعلى ينقصه بلا اختفاء', () => {
  assert.equal(nextRowHeight(80, 40), 120);
  assert.equal(nextRowHeight(80, -40), 40);
  assert.equal(nextRowHeight(80, -500), MIN_ROW_HEIGHT);
});

test('العرض التلقائي يقيس أطول سطر لا مجموع الأسطر', () => {
  assert.equal(
    autoFitColumnWidth('الوصف', ['سطر قصير\nسطر أطول بكثير من سابقه هنا']),
    autoFitColumnWidth('الوصف', ['سطر أطول بكثير من سابقه هنا']),
  );
});
