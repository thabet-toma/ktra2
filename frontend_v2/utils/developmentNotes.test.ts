import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  NOTE_PRIORITY_LABELS, NOTE_STATUS_LABELS, isNoteDone, sortDevelopmentNotes,
} from './developmentNotes.ts';

type Row = {
  id: number;
  status: string;
  priority?: string | null;
  created_at?: string | null;
};

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

test('الأولوية تسبق التاريخ: عالية حديثة فوق منخفضة أقدم', () => {
  const sorted = sortDevelopmentNotes([
    { id: 1, status: 'todo', priority: 'low', created_at: '2026-08-01T09:00:00Z' },
    { id: 2, status: 'todo', priority: 'medium', created_at: '2026-08-02T09:00:00Z' },
    { id: 3, status: 'todo', priority: 'high', created_at: '2026-08-03T09:00:00Z' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [3, 2, 1]);
});

test('داخل الأولوية الواحدة يبقى الأقدم أولاً', () => {
  const sorted = sortDevelopmentNotes([
    { id: 9, status: 'todo', priority: 'high', created_at: '2026-08-05T09:00:00Z' },
    { id: 4, status: 'in_progress', priority: 'high', created_at: '2026-08-02T09:00:00Z' },
    { id: 6, status: 'todo', priority: 'low', created_at: '2026-08-01T09:00:00Z' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [4, 9, 6]);
});

test('المكتملة تبقى أخيراً ولو كانت عالية الأولوية', () => {
  const sorted = sortDevelopmentNotes([
    { id: 1, status: 'done', priority: 'high', created_at: '2026-08-01T09:00:00Z' },
    { id: 2, status: 'todo', priority: 'low', created_at: '2026-08-02T09:00:00Z' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [2, 1]);
});

test('المكتملات فيما بينها تُرتَّب بالأولوية أيضاً', () => {
  const sorted = sortDevelopmentNotes([
    { id: 1, status: 'done', priority: 'low', created_at: '2026-08-01T09:00:00Z' },
    { id: 2, status: 'done', priority: 'high', created_at: '2026-08-02T09:00:00Z' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [2, 1]);
});

test('أولوية غائبة أو غير معروفة تُعامَل معاملة المنخفضة كما في الخادم', () => {
  const sorted = sortDevelopmentNotes([
    { id: 1, status: 'todo', priority: 'حرجة جداً', created_at: '2026-08-01T09:00:00Z' },
    { id: 2, status: 'todo', priority: 'low', created_at: '2026-08-02T09:00:00Z' },
    { id: 3, status: 'todo', created_at: '2026-08-03T09:00:00Z' },
    { id: 4, status: 'todo', priority: 'medium', created_at: '2026-08-04T09:00:00Z' },
  ]);
  assert.deepEqual(sorted.map((row) => row.id), [4, 1, 2, 3]);
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
