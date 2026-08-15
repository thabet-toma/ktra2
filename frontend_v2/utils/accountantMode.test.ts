import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ACCOUNTANT_MODE_KEY,
  readAccountantMode,
  writeAccountantMode,
} from './accountantMode.ts';

const memoryStorage = (seed: Record<string, string> = {}) => {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => (map.has(key) ? map.get(key)! : null),
    setItem: (key: string, value: string) => { map.set(key, String(value)); },
    removeItem: (key: string) => { map.delete(key); },
    clear: () => map.clear(),
    key: () => null,
    length: 0,
  } as unknown as Storage;
};

const withLocalStorage = (seed: Record<string, string> = {}) => {
  const store = memoryStorage(seed);
  (globalThis as any).localStorage = store;
  return store;
};

/** متصفح يمنع التخزين (وضع خاص، أو إطار ثالث الطرف). */
const denyStorage = () => {
  (globalThis as any).localStorage = {
    getItem: () => { throw new Error('storage denied'); },
    setItem: () => { throw new Error('storage denied'); },
  } as unknown as Storage;
};

test('الوضع مطفأ لمن لم يشغّله قط — الترتيب الافتراضي هو الأصل', () => {
  withLocalStorage({});
  assert.equal(readAccountantMode(), false);
});

test('التشغيل يعيش عبر إعادة تحميل الصفحة', () => {
  const store = withLocalStorage({});
  writeAccountantMode(true);
  assert.equal(store.getItem(ACCOUNTANT_MODE_KEY), '1');

  // «إعادة التحميل» = قراءةٌ جديدة من نفس التخزين، بلا أي حالة باقية في الذاكرة.
  withLocalStorage({ [ACCOUNTANT_MODE_KEY]: store.getItem(ACCOUNTANT_MODE_KEY)! });
  assert.equal(readAccountantMode(), true);
});

test('الإطفاء يعيش عبر إعادة التحميل أيضاً — لا يعود الوضع من تلقائه', () => {
  const store = withLocalStorage({ [ACCOUNTANT_MODE_KEY]: '1' });
  writeAccountantMode(false);
  assert.equal(store.getItem(ACCOUNTANT_MODE_KEY), '0');

  withLocalStorage({ [ACCOUNTANT_MODE_KEY]: store.getItem(ACCOUNTANT_MODE_KEY)! });
  assert.equal(readAccountantMode(), false);
});

test('قيمة غريبة في التخزين تُقرأ إطفاءً لا تشغيلاً', () => {
  for (const junk of ['true', 'on', '', 'yes', '2']) {
    withLocalStorage({ [ACCOUNTANT_MODE_KEY]: junk });
    assert.equal(readAccountantMode(), false, `القيمة «${junk}» يجب ألا تُشغّل الوضع`);
  }
});

test('متصفح يمنع التخزين يبقى على الترتيب الافتراضي بلا انفجار', () => {
  denyStorage();
  assert.equal(readAccountantMode(), false);
  assert.doesNotThrow(() => writeAccountantMode(true));
});
