import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  quickBarOpenKey,
  readQuickBarOpen,
  writeQuickBarOpen,
} from './quickBarPref.ts';

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

test('المفتاح يخصّ المستخدم، وبلا معرّف يعود للمفتاح العام', () => {
  assert.equal(quickBarOpenKey('42'), 'ktra.quickBar.open:42');
  assert.equal(quickBarOpenKey(null), 'ktra.quickBar.open');
  assert.equal(quickBarOpenKey(undefined), 'ktra.quickBar.open');
  assert.equal(quickBarOpenKey('  '), 'ktra.quickBar.open');
});

test('الافتراضي مبسوط — بلا تفضيل محفوظ يظهر الشريط كما هو اليوم', () => {
  assert.equal(readQuickBarOpen(memoryStorage(), '42'), true);
});

test('الطيّ يُحفظ ويُقرأ، والبسط يعيده', () => {
  const storage = memoryStorage();
  writeQuickBarOpen(storage, '42', false);
  assert.equal(readQuickBarOpen(storage, '42'), false);
  writeQuickBarOpen(storage, '42', true);
  assert.equal(readQuickBarOpen(storage, '42'), true);
});

test('طيّ صاحب المحل لا يسلب موظّفه الشريط على الجهاز نفسه', () => {
  const storage = memoryStorage();
  writeQuickBarOpen(storage, 'owner', false);

  assert.equal(readQuickBarOpen(storage, 'owner'), false);
  assert.equal(readQuickBarOpen(storage, 'employee'), true);
  assert.deepEqual(storage.dump(), { 'ktra.quickBar.open:owner': '0' });
});

test('التخزين المحظور لا يطوي الشريط بصمت', () => {
  assert.equal(readQuickBarOpen(blockedStorage, '42'), true);
  assert.doesNotThrow(() => writeQuickBarOpen(blockedStorage, '42', false));
});

test('قيمة غريبة في التخزين تُقرأ مبسوطة — الطيّ لا يقع إلا بـ«0» صريحة', () => {
  assert.equal(readQuickBarOpen(memoryStorage({ 'ktra.quickBar.open:42': 'nonsense' }), '42'), true);
  assert.equal(readQuickBarOpen(memoryStorage({ 'ktra.quickBar.open:42': '0' }), '42'), false);
});
