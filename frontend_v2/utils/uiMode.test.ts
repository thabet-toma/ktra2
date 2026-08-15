import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_UI_MODE,
  SIMPLE_VIEWS,
  normalizeUiMode,
  readUiModeCache,
  uiModeCacheKey,
  viewVisibleInSimpleMode,
  writeUiModeCache,
  type UiMode,
} from './uiMode.ts';

/**
 * `localStorage` مزيّف: بيئة `node --test` بلا متصفح، ودوال الـcache تُقرأ هنا
 * كما تُقرأ هناك. `store` يُمرَّر من الاختبار كي يفحص المكتوب فعلاً.
 */
const withStorage = (store: Record<string, string>, fn: () => void): void => {
  const g = globalThis as { localStorage?: Storage };
  const previous = g.localStorage;
  g.localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { for (const k of Object.keys(store)) delete store[k]; },
    key: () => null,
    length: 0,
  } as unknown as Storage;
  try { fn(); } finally { g.localStorage = previous; }
};

test('قائمة الوضع السهل هي الشاشات الثمانية المتفق عليها، لا أكثر', () => {
  assert.deepEqual([...SIMPLE_VIEWS], [
    'dashboard',
    'sales-invoices',
    'purchase-invoices',
    'stock-levels',
    'items-management',
    'supplier-management',
    'sales-customers',
    'settings',
  ]);
});

test('الشاشة المُدرَجة تظهر في الوضع السهل وغير المُدرَجة لا تظهر', () => {
  for (const view of SIMPLE_VIEWS) {
    assert.equal(viewVisibleInSimpleMode(view), true);
  }
  // شاشات متقدمة — مخفيّة لا محذوفة: الرابط المباشر يبقى يعمل.
  assert.equal(viewVisibleInSimpleMode('cheques'), false);
  assert.equal(viewVisibleInSimpleMode('journal-entries'), false);
  assert.equal(viewVisibleInSimpleMode(''), false);
});

test('الافتراضي «متقدم» — التبسيط اختيار صريح لا سلوك صامت', () => {
  assert.equal(DEFAULT_UI_MODE, 'advanced');
  assert.equal(normalizeUiMode('simple'), 'simple');
  assert.equal(normalizeUiMode('advanced'), 'advanced');
});

test('قيمة غير صالحة (من الخادم أو الـcache) تسقط على «متقدم» لا على وضعٍ مبسّط مفاجئ', () => {
  for (const bad of ['SIMPLE', 'basic', '', null, undefined, 0, {}, []]) {
    assert.equal(normalizeUiMode(bad), 'advanced');
  }
});

test('قيمة cache فاسدة تسقط على «متقدم»', () => {
  const store: Record<string, string> = { [uiModeCacheKey(7)]: 'not-a-mode' };
  withStorage(store, () => {
    assert.equal(readUiModeCache(7), 'advanced');
  });
});

test('غياب المفتاح يعطي «متقدم»، والقيمة الصالحة تُقرأ كما كُتبت', () => {
  const store: Record<string, string> = {};
  withStorage(store, () => {
    assert.equal(readUiModeCache(3), 'advanced');
    writeUiModeCache(3, 'simple');
    assert.equal(store[uiModeCacheKey(3)], 'simple');
    assert.equal(readUiModeCache(3), 'simple');
  });
});

test('المفتاح مرقوم بالشركة — وضع شركةٍ لا يسري على أخرى', () => {
  const store: Record<string, string> = {};
  withStorage(store, () => {
    writeUiModeCache(1, 'simple');
    assert.equal(readUiModeCache(1), 'simple');
    assert.equal(readUiModeCache(2), 'advanced');
  });
  assert.notEqual(uiModeCacheKey(1), uiModeCacheKey(2));
});

test('متصفح يمنع التخزين لا يكسر شيئاً — قراءة وكتابة بلا رمي', () => {
  const g = globalThis as { localStorage?: Storage };
  const previous = g.localStorage;
  g.localStorage = {
    getItem: () => { throw new Error('SecurityError'); },
    setItem: () => { throw new Error('QuotaExceededError'); },
  } as unknown as Storage;
  try {
    assert.equal(readUiModeCache(1), 'advanced');
    assert.doesNotThrow(() => writeUiModeCache(1, 'simple' as UiMode));
  } finally {
    g.localStorage = previous;
  }
});
