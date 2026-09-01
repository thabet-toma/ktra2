import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildMergePreview, findBrandCollisions, type MergeCandidate } from './productMerge.ts';

const c = (over: Partial<MergeCandidate>): MergeCandidate => ({
  id: 1, name: 'منتج', brand: '', uomId: 1, isSerialized: false, ...over,
});

test('الهدف غائبٌ عن المُحدَّدين ⇒ null بدل معاينة مضلِّلة', () => {
  const preview = buildMergePreview([c({ id: 1 }), c({ id: 2 })], 99);
  assert.equal(preview, null);
});

test('توافقٌ كامل: كل الأعضاء تنتقل وتُعاد تسميتها لاسم الهدف', () => {
  const target = c({ id: 1, name: '195/85/15' });
  const a = c({ id: 2, name: '195/85/15 دانتير' });
  const b = c({ id: 3, name: '195/85/15 أوتولوكس' });
  const preview = buildMergePreview([target, a, b], 1);
  assert.ok(preview);
  assert.equal(preview!.target.id, 1);
  assert.equal(preview!.renamedTo, '195/85/15');
  assert.equal(preview!.movable.length, 2);
  assert.deepEqual(preview!.movable.map((m) => m.id), [2, 3]);
  assert.equal(preview!.blocked.length, 0);
});

test('اختلاف الوحدة يُمنع باسم العضو وسببه', () => {
  const target = c({ id: 1, uomId: 10 });
  const mismatched = c({ id: 2, name: 'صندوق مختلف', uomId: 20 });
  const preview = buildMergePreview([target, mismatched], 1);
  assert.equal(preview!.movable.length, 0);
  assert.equal(preview!.blocked.length, 1);
  assert.equal(preview!.blocked[0].id, 2);
  assert.equal(preview!.blocked[0].name, 'صندوق مختلف');
  assert.match(preview!.blocked[0].reason, /وحدة القياس/);
});

test('اختلاف التتبّع التسلسلي يُمنع باسم العضو وسببه', () => {
  const target = c({ id: 1, isSerialized: false });
  const mismatched = c({ id: 2, name: 'مسلسل مختلف', isSerialized: true });
  const preview = buildMergePreview([target, mismatched], 1);
  assert.equal(preview!.movable.length, 0);
  assert.equal(preview!.blocked.length, 1);
  assert.match(preview!.blocked[0].reason, /التسلسلي/);
});

test('لا مانع مخترَع: اختلاف حقولٍ أخرى لا يمنع الضمّ', () => {
  // فقط الوحدة والتتبّع التسلسلي يُفحصان — لا حقل ثالث، حتى لو اختلف الاسم كليّاً.
  const target = c({ id: 1, name: 'اسمٌ ما' });
  const other = c({ id: 2, name: 'اسمٌ مختلف كلياً' });
  const preview = buildMergePreview([target, other], 1);
  assert.equal(preview!.movable.length, 1);
  assert.equal(preview!.blocked.length, 0);
});

test('خليط: بعضهم يُضَمّ وبعضهم يُرفَض في نفس المعاينة', () => {
  const target = c({ id: 1, uomId: 1, isSerialized: false });
  const ok = c({ id: 2, uomId: 1, isSerialized: false });
  const badUom = c({ id: 3, uomId: 2, isSerialized: false });
  const badSerial = c({ id: 4, uomId: 1, isSerialized: true });
  const preview = buildMergePreview([target, ok, badUom, badSerial], 1);
  assert.deepEqual(preview!.movable.map((m) => m.id), [2]);
  assert.deepEqual(preview!.blocked.map((b) => b.id), [3, 4]);
});

// ── findBrandCollisions: يمنع صفوفاً متطابقةً بلا وسيلة تمييز في المنتقي ──

test('فراغان يتصادمان — «بلا براند» حالةٌ حقيقية تُرى لا تُخفى', () => {
  const collisions = findBrandCollisions([
    { id: 1, brand: '' }, { id: 2, brand: '' },
  ]);
  assert.equal(collisions.length, 1);
  assert.equal(collisions[0].brand, '');
  assert.deepEqual(collisions[0].ids.sort(), [1, 2]);
});

test('نفس البراند حرفياً على عضوين يتصادم', () => {
  const collisions = findBrandCollisions([
    { id: 1, brand: 'دانتير' }, { id: 2, brand: 'دانتير' }, { id: 3, brand: 'أوتولوكس' },
  ]);
  assert.equal(collisions.length, 1);
  assert.equal(collisions[0].brand, 'دانتير');
  assert.deepEqual(collisions[0].ids.sort(), [1, 2]);
});

test('برانداتٌ كلّها مختلفة ⇒ لا تصادم', () => {
  const collisions = findBrandCollisions([
    { id: 1, brand: 'دانتير' }, { id: 2, brand: 'أوتولوكس' }, { id: 3, brand: 'ميشلان' },
  ]);
  assert.equal(collisions.length, 0);
});

test('القصّ يطابق ما يفعله الخادم — مسافاتٌ زائدة لا تنجّي من التصادم', () => {
  const collisions = findBrandCollisions([
    { id: 1, brand: ' دانتير ' }, { id: 2, brand: 'دانتير' },
  ]);
  assert.equal(collisions.length, 1);
  assert.deepEqual(collisions[0].ids.sort(), [1, 2]);
});

test('عضوٌ واحد لا يتصادم مع نفسه', () => {
  assert.equal(findBrandCollisions([{ id: 1, brand: '' }]).length, 0);
});

test('تصادمٌ واحد وسط أعضاءَ فريدين — يُبلَّغ عنه وحده', () => {
  const collisions = findBrandCollisions([
    { id: 1, brand: 'أ' }, { id: 2, brand: 'ب' }, { id: 3, brand: 'ب' }, { id: 4, brand: 'ج' },
  ]);
  assert.equal(collisions.length, 1);
  assert.deepEqual(collisions[0].ids.sort(), [2, 3]);
});
