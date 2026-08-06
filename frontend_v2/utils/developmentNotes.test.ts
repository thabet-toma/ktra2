import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isNoteDone, sortDevelopmentNotes } from './developmentNotes.ts';

type Row = { id: number; status: string };

const rows = (...statuses: string[]): Row[] =>
  statuses.map((status, index) => ({ id: index + 1, status }));

test('المكتملة تُزاح لآخر القائمة', () => {
  const sorted = sortDevelopmentNotes(rows('done', 'todo', 'in_progress'));
  assert.deepEqual(sorted.map((row) => row.id), [2, 3, 1]);
});

test('ترتيب غير المكتملة يبقى كما جاء من الخادم', () => {
  const sorted = sortDevelopmentNotes(rows('in_progress', 'todo', 'done', 'todo'));
  assert.deepEqual(sorted.map((row) => row.id), [1, 2, 4, 3]);
});

test('ترتيب المكتملات فيما بينها ثابت أيضاً', () => {
  const sorted = sortDevelopmentNotes(rows('done', 'done', 'todo'));
  assert.deepEqual(sorted.map((row) => row.id), [3, 1, 2]);
});

test('الفرز لا يعدّل القائمة الأصلية', () => {
  const original = rows('done', 'todo');
  sortDevelopmentNotes(original);
  assert.deepEqual(original.map((row) => row.id), [1, 2]);
});

test('حالة الإنجاز تُعرَف من done وحدها', () => {
  assert.equal(isNoteDone({ status: 'done' }), true);
  assert.equal(isNoteDone({ status: 'in_progress' }), false);
  assert.equal(isNoteDone({ status: 'todo' }), false);
});
