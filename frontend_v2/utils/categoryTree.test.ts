import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ancestorIds,
  buildCategoryIndex,
  categoryDepth,
  categoryKey,
  categoryPath,
  categoryPathLabel,
  checkState,
  checkStates,
  descendantIds,
  eligibleParents,
  PATH_SEPARATOR,
  restrictCategories,
  restrictPathKeys,
  searchCategories,
  sortCategoryRows,
  toggleSubtree,
  visibleTreeRows,
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

// ─── C1: مجموعةٌ مؤشَّرة صريحة — كل عقدة مؤشَّرة تعني منتجاتها المباشرة ───

const setOf = (...ids: number[]): Set<number> => new Set(ids);

test('تأشير الأب يؤشّر كل أحفاده', () => {
  const next = toggleSubtree(TREE, setOf(), 1);
  assert.deepEqual([...next].sort(), [1, 2, 3]);
  assert.equal(checkState(TREE, next, 1), 'on');
  assert.equal(checkState(TREE, next, 3), 'on');
});

test('إلغاء ابن يجعل الأب جزئياً ويُبقي الأب نفسه مؤشَّراً', () => {
  const all = toggleSubtree(TREE, setOf(), 1);
  const next = toggleSubtree(TREE, all, 3);
  assert.equal(next.has(1), true); // منتجات الأب المباشرة تبقى مشمولة
  assert.equal(next.has(3), false);
  assert.equal(checkState(TREE, next, 1), 'partial');
  assert.equal(checkState(TREE, next, 2), 'partial');
  assert.equal(checkState(TREE, next, 3), 'off');
  // من «جزئي» يعيد التبديل الشجرة كاملة بدل أن يمحوها.
  assert.deepEqual([...toggleSubtree(TREE, next, 1)].sort(), [1, 2, 3]);
});

test('اليتيم (أبوه خارج القائمة) يتصرّف جذراً', () => {
  const orphans: CategoryNodeLike[] = [cat(9, 'يتيم', 77)];
  assert.equal(checkState(orphans, setOf(), 9), 'off');
  assert.equal(checkState(orphans, setOf(9), 9), 'on');
  assert.deepEqual([...toggleSubtree(orphans, setOf(), 9)], [9]);
});

test('حلقة بيانات (أ←ب←أ) لا تُعلّق الحالة ولا التبديل ولا البحث', () => {
  const looped: CategoryNodeLike[] = [cat(1, 'أ', 2), cat(2, 'ب', 1)];
  assert.equal(checkState(looped, setOf(), 1), 'off');
  const next = toggleSubtree(looped, setOf(), 1);
  assert.deepEqual([...next].sort(), [1, 2]);
  assert.equal(checkState(looped, next, 1), 'on');
  const hits = searchCategories(looped, 'أ');
  assert.equal(hits.length, 2);
  assert.equal(hits.every((h) => h.pathLabel.length > 0), true);
});

test('البحث يطابق مقطعاً وسط المسار ويعيد المسار الكامل مرتّباً', () => {
  const hits = searchCategories(TREE, 'شاحن');
  assert.deepEqual(hits, [
    { id: 2, pathLabel: 'إطارات ‹ شاحنات' },
    { id: 3, pathLabel: 'إطارات ‹ شاحنات ‹ ثقيلة' },
  ]);
  assert.deepEqual(searchCategories(TREE, '  ثقيلة '), [
    { id: 3, pathLabel: 'إطارات ‹ شاحنات ‹ ثقيلة' },
  ]);
});

test('البحث لا يفرّق بين حالة الأحرف والاستعلام الفارغ بلا نتائج', () => {
  const latin: CategoryNodeLike[] = [cat(1, 'Cars'), cat(2, 'SUV', 1)];
  assert.deepEqual(searchCategories(latin, 'suv'), [{ id: 2, pathLabel: 'Cars ‹ SUV' }]);
  assert.deepEqual(searchCategories(TREE, '   '), []);
});

test('الدوالّ لا تعدّل المجموعة المُدخلة', () => {
  const input = setOf(3);
  const next = toggleSubtree(TREE, input, 3);
  assert.deepEqual([...input], [3]);
  assert.deepEqual([...next], []);
});

test('تبديل معرّفٍ غير موجود يعيد نسخةً كما هي بلا معرّف شبح', () => {
  const input = setOf(2);
  const next = toggleSubtree(TREE, input, 999);
  assert.deepEqual([...next], [2]);
  assert.notEqual(next, input); // نسخةٌ جديدة لا المجموعة نفسها
});

// ─── C1 (جولة التصليح): خوارزميات المكوّن انتقلت إلى هنا ────────────────────

/** سلسلةٌ ثلاثية: أ ← ب ← ج. */
const CHAIN: CategoryNodeLike[] = [cat(1, 'أ'), cat(2, 'ب', 1), cat(3, 'ج', 2)];

test('الفاصل واحد: المسار والبحث يستعملان PATH_SEPARATOR نفسه', () => {
  assert.equal(PATH_SEPARATOR, ' ‹ ');
  assert.equal(categoryPathLabel(TREE, 3), ['إطارات', 'شاحنات', 'ثقيلة'].join(PATH_SEPARATOR));
  assert.equal(searchCategories(TREE, 'ثقيلة')[0].pathLabel.split(PATH_SEPARATOR).length, 3);
});

test('categoryKey يوحّد الرقم والنصّ', () => {
  assert.equal(categoryKey(3), '3');
  assert.equal(categoryKey('3'), categoryKey(3));
});

test('ancestorIds من الأب حتى الجذر، ويتوقّف عند اليتيم والحلقة', () => {
  assert.deepEqual(ancestorIds(TREE, 3), [2, 1]);
  assert.deepEqual(ancestorIds(TREE, 1), []);
  assert.deepEqual(ancestorIds([cat(9, 'يتيم', 77)], 9), []);
  const looped: CategoryNodeLike[] = [cat(1, 'أ', 2), cat(2, 'ب', 1)];
  assert.equal(ancestorIds(looped, 1).length <= 1, true);
});

test('restrictTo: الأب يُعاد ربطه بأقرب أبٍ مسموح، فإلغاء التأشير ممكن دائماً', () => {
  const restricted = restrictCategories(CHAIN, [1, 3]);
  assert.deepEqual(restricted.map((c) => [c.id, c.parent]), [[1, null], [3, 1]]);

  // أ ⟵ ب ⟵ ج والمسموح {أ, ج}: من {} بتبديل أ ⇒ {أ, ج} وأ 'on'.
  let checked = toggleSubtree(restricted, setOf(), 1);
  assert.deepEqual([...checked].sort(), [1, 3]);
  assert.equal(checkState(restricted, checked, 1), 'on');
  // وتبديل أ ثانيةً يمحوها ⇒ {} — لا يمنع الإلغاءَ أبٌ خارج النطاق.
  checked = toggleSubtree(restricted, checked, 1);
  assert.deepEqual([...checked], []);
  // من {أ, ج} تبديل ج ⇒ {أ} و أ 'partial' (منتجاتها المباشرة وحدها).
  const onlyA = toggleSubtree(restricted, setOf(1, 3), 3);
  assert.deepEqual([...onlyA], [1]);
  assert.equal(checkState(restricted, onlyA, 1), 'partial');
  // ومن 'partial' تبديل أ يعيد الاثنين.
  assert.deepEqual([...toggleSubtree(restricted, onlyA, 1)].sort(), [1, 3]);
});

test('visibleTreeRows: المطوي جذورٌ فقط، وفتح الجذر يُظهر أبناءه بعمق 1', () => {
  const collapsed = visibleTreeRows(TREE, { expanded: new Set() });
  assert.deepEqual(collapsed.map((r) => [r.id, r.depth]), [[1, 0], [4, 0]]);
  const opened = visibleTreeRows(TREE, { expanded: new Set(['1']) });
  assert.deepEqual(opened.map((r) => [r.id, r.depth]), [[1, 0], [2, 1], [4, 0]]);
});

test('visibleTreeRows: restrictTo يُبقي صفوف المسار غير قابلةٍ للاختيار', () => {
  const rows = visibleTreeRows(CHAIN, { expanded: new Set(['1', '2']), restrictTo: [3] });
  assert.deepEqual(
    rows.map((r) => [r.id, r.depth, r.selectable]),
    [[1, 0, false], [2, 1, false], [3, 2, true]],
  );
});

test('restrictTo: مفاتيح المسار المزروعة تُظهر المسموح بلا فتح الجذور يدوياً', () => {
  // أ ⟵ ب ⟵ ج والمسموح {ج}: بلا بذرٍ يبقى العرض جذرَ «أ» وحده فيختفي النطاق.
  assert.deepEqual([...restrictPathKeys(CHAIN, [3])].sort(), ['1', '2']);
  const rows = visibleTreeRows(CHAIN, { expanded: restrictPathKeys(CHAIN, [3]), restrictTo: [3] });
  assert.deepEqual(
    rows.map((r) => [r.id, r.depth, r.selectable]),
    [[1, 0, false], [2, 1, false], [3, 2, true]],
  );
  assert.deepEqual(visibleTreeRows(CHAIN, { expanded: new Set(), restrictTo: [3] }).map((r) => r.id), [1]);
});

test('visibleTreeRows: البحث يُظهر مسار النتيجة مفتوحاً', () => {
  const rows = visibleTreeRows(CHAIN, { expanded: new Set(), query: 'ج' });
  assert.deepEqual(
    rows.map((r) => [r.id, r.depth, r.selectable]),
    [[1, 0, true], [2, 1, true], [3, 2, true]],
  );
});

test('visibleTreeRows: restrictTo مع البحث تقاطعٌ لا اتحاد — المسموح المطابق ومساره وحدهما', () => {
  // أ ← ب ← ج، وشقيقٌ د تحت أ مباشرةً. المسموح {أ, ج, د}: البحث عن «ج» يُبقي
  // ج ومسارها (أ، ب) ويسقط د — مع أنها مسموحة — لأنها ليست مطابقةً ولا مساراً.
  const tree: CategoryNodeLike[] = [cat(1, 'أ'), cat(2, 'ب', 1), cat(3, 'ج', 2), cat(4, 'د', 1)];
  const rows = visibleTreeRows(tree, {
    expanded: new Set(), restrictTo: [1, 3, 4], query: 'ج',
  });
  assert.deepEqual(
    rows.map((r) => [r.id, r.depth, r.selectable]),
    [[1, 0, true], [2, 1, false], [3, 2, true]],
  );
});

test('visibleTreeRows: restrictTo مع البحث — مطابقةٌ خارج النطاق وحدها تُفرغ الصفوف', () => {
  // «هدف» اسمٌ فريد لعقدةٍ خارج النطاق، فأصلها المسموح لا يُجرّ إلى العرض.
  const tree: CategoryNodeLike[] = [
    cat(1, 'أ'), cat(2, 'ب', 1), cat(3, 'ج', 2), cat(4, 'د', 1), cat(5, 'هدف', 2),
  ];
  const rows = visibleTreeRows(tree, { expanded: new Set(), restrictTo: [1, 3, 4], query: 'هدف' });
  assert.deepEqual(rows, []);
});

test('visibleTreeRows: حلقة البيانات لا تُعلّق الرسم', () => {
  const looped: CategoryNodeLike[] = [cat(1, 'أ', 2), cat(2, 'ب', 1)];
  const rows = visibleTreeRows(looped, { expanded: new Set(['1', '2']) });
  assert.equal(rows.length <= 2, true);
});

test('checkStates يعطي كل عقدةٍ ما يعطيه checkState منفردةً', () => {
  const cases: Array<[CategoryNodeLike[], Array<Set<number>>]> = [
    [TREE, [setOf(), setOf(1), setOf(1, 2), setOf(1, 2, 3), setOf(2), setOf(4)]],
    [[cat(1, 'أ', 2), cat(2, 'ب', 1)], [setOf(), setOf(1), setOf(2), setOf(1, 2)]],
  ];
  for (const [categories, checkedSets] of cases) {
    for (const checked of checkedSets) {
      const states = checkStates(categories, checked);
      for (const category of categories) {
        assert.equal(
          states.get(categoryKey(category.id)),
          checkState(categories, checked, category.id),
          `عقدة ${category.id} مع {${[...checked]}}`,
        );
      }
    }
  }
});
