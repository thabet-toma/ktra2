import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  NOTE_PRIORITY_LABELS, NOTE_STATUS_LABELS, isNoteDone, sortDevelopmentNotes,
} from './developmentNotes.ts';

type Row = { id: number; status: string; created_at?: string | null };

/** ملاحظات بترتيب إنشاء تصاعدي — الرقم والتاريخ يتفقان ما لم يُقلبا عمداً. */
const rows = (...statuses: string[]): Row[] =>
  statuses.map((status, index) => ({
    id: index + 1,
    status,
    created_at: `2026-08-0${index + 1}T09:00:00Z`,
  }));

test('المكتملة تُزاح لآخر القائمة', () => {
  const sorted = sortDevelopmentNotes(rows('done', 'todo', 'in_progress'));
  assert.deepEqual(sorted.map((row) => row.id), [2, 3, 1]);
});

test('غير المكتملة تُرتَّب من الأقدم للأحدث مهما وصلت مبعثرة', () => {
  const sorted = sortDevelopmentNotes([
    { id: 7, status: 'todo', created_at: '2026-08-03T09:00:00Z' },
    { id: 2, status: 'in_progress', created_at: '2026-08-01T09:00:00Z' },
    { id: 5, status: 'todo', created_at: '2026-08-02T09:00:00Z' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [2, 5, 7]);
});

test('المكتملات فيما بينها تبقى بترتيب الأقدم فالأحدث', () => {
  const sorted = sortDevelopmentNotes(rows('done', 'done', 'todo'));
  assert.deepEqual(sorted.map((row) => row.id), [3, 1, 2]);
});

test('بلا تاريخ إنشاء يسقط الترتيب على الرقم', () => {
  const sorted = sortDevelopmentNotes([
    { id: 3, status: 'todo' },
    { id: 1, status: 'todo', created_at: null },
    { id: 2, status: 'todo', created_at: 'ليس تاريخاً' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [1, 2, 3]);
});

test('الفرز لا يعدّل القائمة الأصلية', () => {
  const original = rows('done', 'todo');
  sortDevelopmentNotes(original);
  assert.deepEqual(original.map((row) => row.id), [1, 2]);
});

test('حالة الإنجاز تُعرَف من done وحدها', () => {
  assert.equal(isNoteDone({ id: 1, status: 'done' }), true);
  assert.equal(isNoteDone({ id: 1, status: 'in_progress' }), false);
  assert.equal(isNoteDone({ id: 1, status: 'todo' }), false);
});

test('لكل حالة وأولوية تسمية عربية معروضة', () => {
  assert.deepEqual(Object.keys(NOTE_STATUS_LABELS), ['todo', 'in_progress', 'done']);
  assert.deepEqual(Object.keys(NOTE_PRIORITY_LABELS), ['low', 'medium', 'high']);
});
