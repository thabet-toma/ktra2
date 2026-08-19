import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CARD_MIN_PX,
  MAX_SHOWS,
  didYouKnowKey,
  hasRoomForTip,
  hideTip,
  markTipShown,
  pickTip,
  readDidYouKnowState,
  type TipContext,
} from './didYouKnowPref.ts';
import { TIPS, type Tip } from '../constants/tips.ts';

const memoryStorage = (seed: Record<string, string> = {}) => {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    dump: () => Object.fromEntries(data),
  };
};

const blockedStorage = {
  getItem: () => { throw new Error('storage blocked'); },
  setItem: () => { throw new Error('storage blocked'); },
};

/** سياقٌ مسموحٌ فيه كل شيء — كل اختبار يضيّق ما يخصّه وحده. */
const ctx = (over: Partial<TipContext> = {}): TipContext => ({
  view: 'sales-invoices',
  can: () => true,
  modules: {},
  uiMode: 'advanced',
  ...over,
});

const tip = (over: Partial<Tip> & Pick<Tip, 'key' | 'view'>): Tip => ({
  title: 'عنوان',
  lines: ['سطر أول', 'سطر ثانٍ'],
  ...over,
});

// ── التخزين ───────────────────────────────────────────────────────────
test('المفتاح يخصّ المستخدم، وبلا معرّف لا مفتاح أصلاً', () => {
  assert.equal(didYouKnowKey('42'), 'ktra.didYouKnow:42');
  assert.equal(didYouKnowKey(null), null);
  assert.equal(didYouKnowKey('  '), null);
});

test('بلا معرّف مستخدم لا يُكتب شيء — لا إخفاء باسم لا أحد', () => {
  const storage = memoryStorage();
  hideTip(storage, null, 'sales.invoice-profits');
  markTipShown(storage, undefined, 'sales.invoice-profits');
  assert.deepEqual(storage.dump(), {});
});

test('سجلّ JSON فاسد يعود سجلاً فارغاً بلا رمي', () => {
  const storage = memoryStorage({ 'ktra.didYouKnow:42': '{ليس JSON' });
  assert.deepEqual(readDidYouKnowState(storage, '42'), {});
});

test('سجلّ بشكلٍ غريب لا يكسر شيئاً — كل مدخلٍ يُطبَّع', () => {
  const storage = memoryStorage({
    'ktra.didYouKnow:42': JSON.stringify({
      a: { hidden: 'نعم', shown: -3 },
      b: { shown: 99 },
      c: 'نصّ لا كائن',
    }),
  });
  const state = readDidYouKnowState(storage, '42');
  assert.deepEqual(state.a, { hidden: false, shown: 0 });
  assert.deepEqual(state.b, { hidden: false, shown: MAX_SHOWS });
  assert.equal(state.c, undefined);
});

test('التخزين المحظور لا يرمي — يعود للافتراضي ولا يُسقط الشاشة', () => {
  assert.deepEqual(readDidYouKnowState(blockedStorage, '42'), {});
  assert.doesNotThrow(() => hideTip(blockedStorage, '42', 'x'));
  assert.doesNotThrow(() => markTipShown(blockedStorage, '42', 'x'));
});

test('إخفاء مستخدمٍ لا يُخفي التلميح عن زميله على الجهاز نفسه', () => {
  const storage = memoryStorage();
  hideTip(storage, 'owner', 'store.public-link');
  assert.equal(readDidYouKnowState(storage, 'owner')['store.public-link']?.hidden, true);
  assert.equal(readDidYouKnowState(storage, 'employee')['store.public-link'], undefined);
});

// ── قاعدة الطيّ ───────────────────────────────────────────────────────
test('يُعرض مرّتين ثم يُطوى وحده', () => {
  const storage = memoryStorage();
  const tips = [tip({ key: 'a', view: 'sales-invoices' })];
  // السقف مثبَّت على رقمه لا على نفسه: حلقةٌ تدور `MAX_SHOWS` مرّة تنجح مهما
  // كانت قيمته، فلا تحرس «مرّة أو مرّتين» التي طلبها المالك.
  assert.equal(MAX_SHOWS, 2);

  for (let i = 0; i < MAX_SHOWS; i += 1) {
    const state = readDidYouKnowState(storage, '42');
    assert.equal(pickTip(tips, state, ctx())?.key, 'a', `الظهور رقم ${i + 1}`);
    markTipShown(storage, '42', 'a');
  }

  assert.equal(pickTip(tips, readDidYouKnowState(storage, '42'), ctx()), null);
});

test('العدّ لا يتجاوز السقف مهما تكرّر النداء', () => {
  const storage = memoryStorage();
  for (let i = 0; i < 10; i += 1) markTipShown(storage, '42', 'a');
  assert.equal(readDidYouKnowState(storage, '42').a?.shown, MAX_SHOWS);
});

test('«لا تُظهر مجدداً» يبقى بعد إعادة القراءة من نفس المخزن', () => {
  const storage = memoryStorage();
  const tips = [tip({ key: 'a', view: 'sales-invoices' })];
  hideTip(storage, '42', 'a');
  assert.equal(pickTip(tips, readDidYouKnowState(storage, '42'), ctx()), null);
});

// ── الاختيار ──────────────────────────────────────────────────────────
test('لا يُعرض تلميح شاشةٍ أخرى', () => {
  const tips = [tip({ key: 'a', view: 'accounting-cheques' })];
  assert.equal(pickTip(tips, {}, ctx({ view: 'sales-invoices' })), null);
});

test('الأقلّ ظهوراً يفوز، وعند التساوي ترتيب التصريح', () => {
  const tips = [
    tip({ key: 'a', view: 'sales-invoices' }),
    tip({ key: 'b', view: 'sales-invoices' }),
  ];
  assert.equal(pickTip(tips, {}, ctx())?.key, 'a');
  assert.equal(
    pickTip(tips, { a: { hidden: false, shown: 1 } }, ctx())?.key,
    'b',
  );
});

test('تلميحٌ يَعِد بشاشةٍ تحجبها الصلاحية لا يُعرض', () => {
  const tips = [tip({ key: 'a', view: 'sales-invoices', targetView: 'invoice-profits' })];
  assert.equal(pickTip(tips, {}, ctx())?.key, 'a');
  assert.equal(
    pickTip(tips, {}, ctx({ can: (p) => p !== 'inventory.cost.view' })),
    null,
  );
});

test('تلميح شاشةٍ لا يملكها المستخدم لا يُعرض فوق لوحة السقوط', () => {
  // `App.tsx` يسقط على لوحة التحكم وتبقى `appView` على الشاشة المحجوبة.
  const tips = [tip({ key: 'a', view: 'accounting-cheques' })];
  const ctxOnCheques = ctx({ view: 'accounting-cheques' });
  assert.equal(pickTip(tips, {}, ctxOnCheques)?.key, 'a');
  assert.equal(
    pickTip(tips, {}, ctx({ view: 'accounting-cheques', can: (p) => p !== 'accounting.journal.view' })),
    null,
  );
});

test('الوضع السهل لا يحجب شرح الشاشة التي فتحها المستخدم فعلاً', () => {
  const tips = [tip({ key: 'a', view: 'accounting-cheques' })];
  assert.equal(
    pickTip(tips, {}, ctx({ view: 'accounting-cheques', uiMode: 'simple' }))?.key,
    'a',
  );
});

test('تلميحٌ يَعِد بشاشة وحدةٍ غير مرخّصة لا يُعرض', () => {
  const tips = [tip({ key: 'a', view: 'sales-invoices', targetView: 'after-sales' })];
  assert.equal(pickTip(tips, {}, ctx({ modules: { after_sales: true } }))?.key, 'a');
  assert.equal(pickTip(tips, {}, ctx({ modules: {} })), null);
});

test('في الوضع السهل لا يُدعى المستخدم إلى شاشةٍ يحجبها القناع', () => {
  const tips = [tip({ key: 'a', view: 'sales-invoices', targetView: 'invoice-profits' })];
  assert.equal(pickTip(tips, {}, ctx({ uiMode: 'simple' })), null);
  const inside = [tip({ key: 'b', view: 'sales-invoices', targetView: 'stock-levels' })];
  assert.equal(pickTip(inside, {}, ctx({ uiMode: 'simple' }))?.key, 'b');
});

// ── قاعدة المساحة ─────────────────────────────────────────────────────
test('البطاقة تظهر فقط إن بقي لها متّسع أسفل المحتوى', () => {
  assert.equal(hasRoomForTip(400, 800), true);
  assert.equal(hasRoomForTip(800 - CARD_MIN_PX, 800), true);
  assert.equal(hasRoomForTip(800 - CARD_MIN_PX + 1, 800), false);
  assert.equal(hasRoomForTip(2000, 800), false);
  assert.equal(hasRoomForTip(Number.NaN, 800), false);
});

// ── ملف النصوص ────────────────────────────────────────────────────────
test('التلميحات العشرة: مفاتيح فريدة وشكلٌ مستوفٍ', () => {
  assert.equal(TIPS.length, 10);
  assert.equal(new Set(TIPS.map((t) => t.key)).size, TIPS.length);
  for (const t of TIPS) {
    assert.ok(t.title.trim(), `عنوان فارغ: ${t.key}`);
    assert.equal(t.lines.length, 2, `سطران لا ثالث لهما: ${t.key}`);
    assert.ok(t.lines.every((line) => line.trim()), `سطر فارغ: ${t.key}`);
    assert.notEqual(t.targetView, t.view, `وجهةٌ هي الشاشة نفسها: ${t.key}`);
  }
});

test('كل تلميحات الملف مؤهَّلة فعلاً في شاشتها لمستخدمٍ كامل الصلاحية', () => {
  const modules = { after_sales: true, sensitive_devices: true, accountant_portal: true, import_file: true };
  for (const t of TIPS) {
    assert.equal(
      pickTip([t], {}, ctx({ view: t.view, modules }))?.key,
      t.key,
      `تلميحٌ لا يظهر أبداً: ${t.key}`,
    );
  }
});
