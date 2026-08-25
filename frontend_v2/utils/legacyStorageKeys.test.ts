import { test } from 'node:test';
import assert from 'node:assert/strict';
import { migrateLegacyStorageKeys, type MigratableStore } from './legacyStorageKeys.ts';

const store = (seed: Record<string, string> = {}): MigratableStore & { dump: () => Record<string, string> } => {
  const data = new Map(Object.entries(seed));
  return {
    get length() { return data.size; },
    key: (i: number) => Array.from(data.keys())[i] ?? null,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => { data.set(k, v); },
    removeItem: (k: string) => { data.delete(k); },
    dump: () => Object.fromEntries(data),
  };
};

test('عروض الأعمدة التي ضبطها المستخدم تنتقل ولا تضيع', () => {
  const s = store({ 'aseel_table_widths_/items_name,qty': '{"name":220}' });
  assert.equal(migrateLegacyStorageKeys(s), 1);
  assert.deepEqual(s.dump(), { 'ktra_table_widths_/items_name,qty': '{"name":220}' });
});

test('كل المفاتيح تُنقل — لا يُتخطّى واحد بسبب التعديل أثناء المرور', () => {
  const s = store({
    'aseel_table_widths_a': '1',
    'aseel_table_row_heights_b': '2',
    'aseel_calc_history': '3',
    'unrelated': 'x',
  });
  assert.equal(migrateLegacyStorageKeys(s), 3);
  assert.deepEqual(s.dump(), {
    unrelated: 'x',
    ktra_table_widths_a: '1',
    ktra_table_row_heights_b: '2',
    ktra_calc_history: '3',
  });
});

test('المفتاح الجديد الموجود رأيٌ أحدث فلا يُدهس، والقديم يُنظَّف', () => {
  const s = store({ aseel_calc_history: 'قديم', ktra_calc_history: 'جديد' });
  assert.equal(migrateLegacyStorageKeys(s), 0);
  assert.deepEqual(s.dump(), { ktra_calc_history: 'جديد' });
});

test('الترحيل مرّةً واحدة: تشغيلٌ ثانٍ لا يفعل شيئاً', () => {
  const s = store({ 'aseel_table_widths_a': '1' });
  migrateLegacyStorageKeys(s);
  const after = s.dump();
  assert.equal(migrateLegacyStorageKeys(s), 0);
  assert.deepEqual(s.dump(), after);
});

test('التخزين المحظور لا يُسقط الإقلاع', () => {
  const blocked: MigratableStore = {
    get length(): number { throw new Error('blocked'); },
    key: () => { throw new Error('blocked'); },
    getItem: () => { throw new Error('blocked'); },
    setItem: () => { throw new Error('blocked'); },
    removeItem: () => { throw new Error('blocked'); },
  };
  assert.doesNotThrow(() => migrateLegacyStorageKeys(blocked));
  assert.equal(migrateLegacyStorageKeys(blocked), 0);
});
