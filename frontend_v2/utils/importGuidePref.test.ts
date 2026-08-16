import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  importGuideOpenKey,
  readImportGuideOpen,
  writeImportGuideOpen,
} from './importGuidePref.ts';

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
  assert.equal(importGuideOpenKey('42'), 'ktra.importGuide.open:42');
  assert.equal(importGuideOpenKey(null), 'ktra.importGuide.open');
  assert.equal(importGuideOpenKey('  '), 'ktra.importGuide.open');
});

test('الافتراضي مطويّ — بلا تفضيل محفوظ لا يُفتح اللوح', () => {
  assert.equal(readImportGuideOpen(memoryStorage(), '42'), false);
});

test('طيّ صاحب المحل لا يُخفي المرشد عن موظّفه على الجهاز نفسه', () => {
  const storage = memoryStorage();
  writeImportGuideOpen(storage, 'owner', true);
  writeImportGuideOpen(storage, 'owner', false);
  writeImportGuideOpen(storage, 'employee', true);

  assert.equal(readImportGuideOpen(storage, 'owner'), false);
  assert.equal(readImportGuideOpen(storage, 'employee'), true);
});

test('الحفظ والقراءة يدوران على نفس المفتاح', () => {
  const storage = memoryStorage();
  writeImportGuideOpen(storage, '7', true);
  assert.deepEqual(storage.dump(), { 'ktra.importGuide.open:7': '1' });
  assert.equal(readImportGuideOpen(storage, '7'), true);
});

test('المفتاح العام القديم لا يفتح لوح أي مستخدم', () => {
  const legacy = memoryStorage({ 'ktra.importGuide.open': '1' });
  assert.equal(readImportGuideOpen(legacy, '42'), false);
});

test('التخزين المحظور لا يرمي — يعود للافتراضي المطويّ', () => {
  assert.equal(readImportGuideOpen(blockedStorage, '42'), false);
  assert.doesNotThrow(() => writeImportGuideOpen(blockedStorage, '42', true));
});
