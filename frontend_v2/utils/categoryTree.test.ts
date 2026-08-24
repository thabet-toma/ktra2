import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildCategoryIndex,
  categoryDepth,
  categoryPath,
  categoryPathLabel,
  descendantIds,
  eligibleParents,
  sortCategoryRows,
  type CategoryNodeLike,
} from './categoryTree.ts';

const cat = (id: number, name: string, parent: number | null = null): CategoryNodeLike =>
  ({ id, name, parent });

/** شجرة مصغّرة: إطارات ← شاحنات ← ثقيلة، وبطاريات جذرٌ ثانٍ. */
const TREE: CategoryNodeLike[] = [
  cat(3, 'ثقيلة', 2),
  cat(1, 'إطارات'),
  cat(2, 'شاحنات', 1),
  cat(4, 'بطاريات'),
];

test('الفهرس يرتّب الأبناء بالاسم ويجمع الجذور تحت null', () => {
  const { childrenOf } = buildCategoryIndex(TREE);
  // المفاتيح نصّية دائماً كي يتساوى `3` و`"3"` — شاشاتُ المستودع تحمل أرقاماً
  // وشجرةُ الفاتورة تحمل نصوصاً.
  assert.deepEqual((childrenOf.get(null) ?? []).map((c) => c.name), ['إطارات', 'بطاريات']);
  assert.deepEqual((childrenOf.get('1') ?? []).map((c) => c.name), ['شاحنات']);
});

test('صفوف العرض بترتيب العمق مع علامة الأبناء', () => {
  const rows = sortCategoryRows(TREE);
  assert.deepEqual(rows.map((r) => [r.category.name, r.depth, r.hasChildren]), [
    ['إطارات', 0, true],
    ['شاحنات', 1, true],
    ['ثقيلة', 2, false],
    ['بطاريات', 0, false],
  ]);
});

test('اليتيم (أبوه خارج القائمة) يبقى جذراً ولا يختفي', () => {
  const rows = sortCategoryRows([cat(9, 'يتيم', 77)]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].depth, 0);
});

test('parent=0 القديم جذرٌ كما يعامله الخادم', () => {
  const rows = sortCategoryRows([cat(5, 'قديم', 0)]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].depth, 0);
});

test('العمق يُحسب من الجذر', () => {
  assert.equal(categoryDepth(TREE, 1), 0);
  assert.equal(categoryDepth(TREE, 2), 1);
  assert.equal(categoryDepth(TREE, 3), 2);
});

test('الأحفاد تشمل التصنيف نفسه', () => {
  assert.deepEqual(descendantIds(TREE, 1).sort(), [1, 2, 3]);
  assert.deepEqual(descendantIds(TREE, 3), [3]);
  assert.deepEqual(descendantIds(TREE, 999), []);
});

test('المسار من الجذر إلى العقدة', () => {
  assert.deepEqual(categoryPath(TREE, 3), ['إطارات', 'شاحنات', 'ثقيلة']);
  assert.equal(categoryPathLabel(TREE, 3), 'إطارات ‹ شاحنات ‹ ثقيلة');
  assert.equal(categoryPathLabel(TREE, null, 'بدون تصنيف'), 'بدون تصنيف');
});

test('الآباء الصالحون يستبعدون العقدة وأحفادها', () => {
  assert.deepEqual(eligibleParents(TREE, 1).map((c) => c.id), [4]);
  assert.deepEqual(eligibleParents(TREE, null).length, 4);
});

test('المعرّف النصّي والأب الرقمي يلتقيان (عُرف شجرة الفاتورة)', () => {
  // العقدة تحمل معرّفاً نصّياً وأباً رقمياً — لو لم تُطبَّع المفاتيح لصار كل
  // تصنيفٍ جذراً وانهارت الشجرة إلى قائمة مسطّحة.
  const mixed: CategoryNodeLike[] = [
    { id: '1', name: 'إطارات', parent: null },
    { id: '2', name: 'شاحنات', parent: 1 },
  ];
  const rows = sortCategoryRows(mixed);
  assert.deepEqual(rows.map((r) => [r.category.name, r.depth]), [['إطارات', 0], ['شاحنات', 1]]);
  assert.deepEqual(descendantIds(mixed, '1'), ['1', '2']);
  assert.equal(categoryPathLabel(mixed, '2'), 'إطارات ‹ شاحنات');
});

test('حلقةٌ في بياناتٍ قديمة لا تُجمّد الشاشة', () => {
  // أبٌ صار ابنَ ابنه — ممكنٌ في بياناتٍ سبقت حارس الخادم.
  const looped: CategoryNodeLike[] = [cat(1, 'أ', 2), cat(2, 'ب', 1)];
  assert.equal(sortCategoryRows(looped).length <= 2, true);
  assert.equal(descendantIds(looped, 1).length <= 2, true);
  assert.equal(categoryPath(looped, 1).length <= 2, true);
  assert.equal(categoryDepth(looped, 1) <= 2, true);
});
