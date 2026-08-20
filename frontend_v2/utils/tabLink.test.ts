import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  TAB_HANDOFF_KEY_PREFIX,
  TAB_HANDOFF_TTL_MS,
  isInternalPath,
  withHandoffToken,
  readHandoffToken,
  searchWithoutHandoff,
  isFreshHandoff,
  writeHandoff,
  takeHandoff,
  sweepStaleHandoffs,
  type HandoffStore,
} from './tabLink.ts';

/** تخزينٌ في الذاكرة — المناولة تُختبر بلا متصفح. يقلّد `key`/`length` لتُختبر الكنسة. */
const memoryStore = () => {
  const map = new Map<string, string>();
  return {
    map,
    get length() { return map.size; },
    key: (i: number) => [...map.keys()][i] ?? null,
    getItem: (k: string) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k: string, v: string) => { map.set(k, v); },
    removeItem: (k: string) => { map.delete(k); },
  } satisfies HandoffStore & { map: Map<string, string>; length: number; key(i: number): string | null };
};

test('الرمز يُلحق بالمسارات الداخلية وحدها', () => {
  assert.equal(isInternalPath('/sales/invoices/12'), true);
  assert.equal(isInternalPath('//evil.example/x'), false);
  assert.equal(isInternalPath('https://alibaba.com/order'), false);
  assert.equal(isInternalPath('blob:abc'), false);
  assert.equal(withHandoffToken('https://alibaba.com/order', 'tok'), 'https://alibaba.com/order');
});

test('الإلحاق يحترم وجود معاملات سابقة', () => {
  assert.equal(withHandoffToken('/products/5', 'tok'), '/products/5?_ktab=tok');
  assert.equal(withHandoffToken('/products/5?tab=serials', 'tok'), '/products/5?tab=serials&_ktab=tok');
});

test('المرساة تبقى في الذيل بعد الإلحاق', () => {
  assert.equal(withHandoffToken('/deals/9#lines', 'tok'), '/deals/9?_ktab=tok#lines');
});

test('قراءة الرمز ثم تنظيف الرابط', () => {
  assert.equal(readHandoffToken('?tab=serials&_ktab=abc'), 'abc');
  assert.equal(readHandoffToken('?tab=serials'), null);
  assert.equal(readHandoffToken(''), null);
  assert.equal(searchWithoutHandoff('?tab=serials&_ktab=abc'), '?tab=serials');
  assert.equal(searchWithoutHandoff('?_ktab=abc'), '');
});

test('المناولة تُستهلَك مرّة واحدة — التحديث لا يُعيد المؤشّر', () => {
  const store = memoryStore();
  const now = 1_700_000_000_000;
  writeHandoff(store, 'tok', { openerId: 'opener', openerLabel: 'فواتير المبيعات', at: now });

  const first = takeHandoff(store, 'tok', now + 500);
  assert.deepEqual(first, { openerId: 'opener', openerLabel: 'فواتير المبيعات', at: now });

  assert.equal(takeHandoff(store, 'tok', now + 600), null);
  assert.equal(store.map.size, 0, 'السجلّ يُمسح ولا يتراكم في التخزين');
});

test('سجلٌّ متقادم يُهمَل ويُمسح', () => {
  const store = memoryStore();
  const now = 1_700_000_000_000;
  writeHandoff(store, 'tok', { openerId: 'opener', openerLabel: 'الأصناف', at: now });
  assert.equal(takeHandoff(store, 'tok', now + TAB_HANDOFF_TTL_MS + 1), null);
  assert.equal(store.map.size, 0);
});

test('سجلٌّ مشوَّه لا يُسقط الالتقاط', () => {
  const store = memoryStore();
  store.setItem(`${TAB_HANDOFF_KEY_PREFIX}tok`, '{ليس JSON');
  assert.equal(takeHandoff(store, 'tok', Date.now()), null);
});

test('حارس شكل السجلّ', () => {
  const now = 1_700_000_000_000;
  assert.equal(isFreshHandoff(null, now), false);
  assert.equal(isFreshHandoff({ openerId: 'a' }, now), false);
  assert.equal(isFreshHandoff({ openerId: 'a', openerLabel: 'x', at: now }, now), true);
  // ساعةٌ متقدّمة في تبويب آخر: سجلٌّ «من المستقبل» يُرفض بدل أن يبقى أبداً.
  assert.equal(isFreshHandoff({ openerId: 'a', openerLabel: 'x', at: now + 5_000 }, now), false);
});

/**
 * معيار النجاح (الشقّ المتصفّحي): تحضير الفتح لا يمسّ التبويب الحالي —
 * لا يغيّر مساره ولا معاملاته، أثرُه كلّه سجلٌّ ورمزٌ في الرابط الوجهة.
 */
test('تحضير المناولة لا يلمس رابط التبويب الفاتح', () => {
  const store = memoryStore();
  const before = '/sales/invoices?page=2';
  const target = withHandoffToken('/products/5', 'tok');
  writeHandoff(store, 'tok', { openerId: 'me', openerLabel: 'فواتير المبيعات', at: Date.now() });

  assert.equal(before, '/sales/invoices?page=2', 'رابط الفاتح كما هو');
  assert.equal(target, '/products/5?_ktab=tok');
  assert.equal(readHandoffToken(before.slice(before.indexOf('?'))), null, 'الفاتح بلا رمز مناولة');
});

test('الكنسة تُزيل سجلّات التبويبات التي لم تُفتح، وتُبقي الطازج ولا تمسّ غيره', () => {
  const store = memoryStore();
  const now = 1_700_000_000_000;
  writeHandoff(store, 'fresh', { openerId: 'a', openerLabel: 'الأصناف', at: now });
  writeHandoff(store, 'stale', { openerId: 'b', openerLabel: 'الصفقات', at: now - TAB_HANDOFF_TTL_MS - 1 });
  store.setItem(`${TAB_HANDOFF_KEY_PREFIX}broken`, 'ليس JSON');
  store.setItem('ktra.uiLogLevel', 'warn');

  assert.equal(sweepStaleHandoffs(store, now), 2);
  assert.deepEqual([...store.map.keys()].sort(), [
    'ktra.tabHandoff:fresh',
    'ktra.uiLogLevel',
  ]);
});
