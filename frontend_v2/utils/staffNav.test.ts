import assert from 'node:assert/strict';
import test from 'node:test';

import { staffNav, staffRouteForPath, staffRouteForKey } from './staffNav.ts';

test('يعيد جدول الموظف المسار الصحيح لكل مفتاح', () => {
  for (const item of staffNav) {
    assert.equal(staffRouteForKey(item.key), item.path);
  }
});

test('يعيد المسار الافتراضي لمسار موظف مجهول', () => {
  assert.equal(staffRouteForPath('/staff/unknown'), '/staff/home');
});

test('لا يكرر جدول الموظف مفاتيح أو مسارات', () => {
  assert.equal(new Set(staffNav.map((item) => item.key)).size, staffNav.length);
  assert.equal(new Set(staffNav.map((item) => item.path)).size, staffNav.length);
});

test('يعرض جدول الموظف تبويب العملاء في مساره الصحيح', () => {
  assert.deepEqual(staffNav.find((item) => item.key === 'crm')?.path, '/staff/crm');
});
