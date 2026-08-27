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
  SIMPLE_MASK,
  SIMPLE_HIDDEN_COLUMNS,
  showAdvanced,
  visibleColumns,
  type MaskKey,
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
    'items-management',
    'stock-levels',
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


/* ── T-SIMPL2 — قناع العناصر داخل الشاشات ───────────────────────────────── */

const MASK_KEYS = Object.keys(SIMPLE_MASK) as MaskKey[];

test('الوضع المتقدّم يعرض كل عنصرٍ مسجَّل — القناع لا يمسّه بشيء', () => {
  for (const key of MASK_KEYS) {
    assert.equal(showAdvanced(key, 'advanced'), true);
    // ولا حتى حين تقول الشاشة إن العنصر بلا قيمة.
    assert.equal(showAdvanced(key, 'advanced', false), true);
  }
});

test('الوضع السهل يطوي كل عنصرٍ مسجَّل ما لم يحمل قيمة', () => {
  for (const key of MASK_KEYS) {
    assert.equal(showAdvanced(key, 'simple'), false);
  }
});

test('قاعدة السقوط للظهور: ما حمل قيمةً فعلية يظهر رغم الوضع السهل', () => {
  // ضريبةٌ محسوبة أو استحقاقٌ مُدخَل — رقمٌ يغيّر مالاً لا يُخفى عن صاحبه.
  assert.equal(showAdvanced('doc.tax', 'simple', true), true);
  assert.equal(showAdvanced('doc.due-date', 'simple', true), true);
  assert.equal(showAdvanced('doc.line-discount', 'simple', true), true);
});

test('مفتاحٌ خارج السِّجل يُعرض — الفشل نحو الظهور لا نحو الإخفاء الصامت', () => {
  assert.equal(showAdvanced('doc.not-a-real-key' as MaskKey, 'simple'), true);
});

test('كل مفتاحٍ في السِّجل يحمل سببَ طيّه مكتوباً — لا إخفاءَ بلا تعليل', () => {
  assert.ok(MASK_KEYS.length > 0);
  for (const key of MASK_KEYS) {
    assert.equal(typeof SIMPLE_MASK[key], 'string');
    assert.ok(SIMPLE_MASK[key].length > 10, `المفتاح ${key} بلا سبب مكتوب`);
  }
});

const COLS = [
  { key: 'name' }, { key: 'reserved' }, { key: 'available' },
  { key: 'max' }, { key: 'grp' }, { key: 'status' },
];

test('الوضع المتقدّم يُبقي الأعمدة كما هي بترتيبها حرفياً', () => {
  assert.deepEqual(
    visibleColumns(COLS, 'stock-levels', 'advanced').map((c) => c.key),
    COLS.map((c) => c.key),
  );
});

test('الوضع السهل يقلّم أعمدة الشاشة المسجَّلة ولا يمسّ ترتيب الباقي', () => {
  assert.deepEqual(
    visibleColumns(COLS, 'stock-levels', 'simple').map((c) => c.key),
    ['name', 'status'],
  );
});

test('`keep` يعيد العمود رغم الوضع — حجزٌ قائمٌ لا يُخفى عن بائعه', () => {
  assert.deepEqual(
    visibleColumns(COLS, 'stock-levels', 'simple', ['reserved', 'available']).map((c) => c.key),
    ['name', 'reserved', 'available', 'status'],
  );
});

test('شاشةٌ بلا سِجلّ أعمدة تبقى كاملة — لا إخفاء بالمصادفة', () => {
  assert.deepEqual(
    visibleColumns(COLS, 'screen-with-no-mask', 'simple').map((c) => c.key),
    COLS.map((c) => c.key),
  );
});

test('التقليم لا يُعدّل المصفوفة الأصلية — الشاشة تبني أعمدتها مرّةً', () => {
  const before = COLS.map((c) => c.key);
  visibleColumns(COLS, 'stock-levels', 'simple');
  assert.deepEqual(COLS.map((c) => c.key), before);
});

test('كل شاشةٍ في سِجلّ الأعمدة هي شاشةٌ يراها الوضع السهل أصلاً', () => {
  // قناعُ أعمدةٍ لشاشةٍ لا تظهر في الوضع السهل شيفرةٌ ميتة تُوهم بأنها تعمل.
  for (const screen of Object.keys(SIMPLE_HIDDEN_COLUMNS)) {
    assert.equal(viewVisibleInSimpleMode(screen), true, `الشاشة ${screen} خارج SIMPLE_VIEWS`);
  }
});
