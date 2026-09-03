import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveHomeScreen, resolveModuleGate } from './homeScreen.ts';

test('قالب مكتب المحاسبة يفتح على لوحة المكتب', () => {
  assert.equal(resolveHomeScreen('accounting_firm'), 'office-dashboard');
});

test('قالب دفتر العميل يفتح على الوضع المالي', () => {
  assert.equal(resolveHomeScreen('client_book'), 'financial-position');
});

test('القالب العام والمجهول والغائب تبقى على اللوحة الافتراضية', () => {
  assert.equal(resolveHomeScreen('general'), 'default');
  assert.equal(resolveHomeScreen(undefined), 'default');
  assert.equal(resolveHomeScreen(null), 'default');
  assert.equal(resolveHomeScreen('unknown_template'), 'default');
});

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
