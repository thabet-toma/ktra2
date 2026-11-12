import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveModuleGate } from './homeScreen.ts';

test('بوابة الترخيص: أثناء التحميل تبقى معلَّقة بصرف النظر عن العَلَم', () => {
  assert.equal(resolveModuleGate(true, undefined), 'loading');
  assert.equal(resolveModuleGate(true, true), 'loading');
});

test('بوابة الترخيص تفشل مغلقةً: false أو غياب المفتاح = غير مرخَّصة', () => {
  assert.equal(resolveModuleGate(false, false), 'unlicensed');
  assert.equal(resolveModuleGate(false, undefined), 'unlicensed');
});

test('بوابة الترخيص: true صريحة وحدها تفتح الشاشة', () => {
  assert.equal(resolveModuleGate(false, true), 'ready');
});
