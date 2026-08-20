import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveActiveTabKey } from './tabSelection.ts';

const tab = (key: string) => ({ key });

test('بلا تبويبات → لا تبويب نشط', () => {
  assert.equal(resolveActiveTabKey([], 'x', 'y'), null);
});

test('بلا اختيار ولا طلب → أول تبويب', () => {
  assert.equal(resolveActiveTabKey([tab('a'), tab('b')]), 'a');
});

test('الطلب الخارجي يفوز حين لا اختيار للمستخدم', () => {
  assert.equal(resolveActiveTabKey([tab('a'), tab('b')], null, 'b'), 'b');
});

test('اختيار المستخدم أقوى من الطلب الخارجي', () => {
  assert.equal(resolveActiveTabKey([tab('a'), tab('b')], 'a', 'b'), 'a');
});

test('طلبٌ لتبويب غير موجود يسقط إلى الأول لا إلى فراغ', () => {
  assert.equal(resolveActiveTabKey([tab('a'), tab('b')], null, 'ghost'), 'a');
});

/** معيار النجاح: إضافة تبويب وقت التشغيل — في المنتصف — لا تغيّر التبويب النشط. */
test('إدراج تبويب في المنتصف لا يزيح المستخدم', () => {
  const before = [tab('general'), tab('lines'), tab('notes')];
  const active = resolveActiveTabKey(before, 'notes');
  assert.equal(active, 'notes');

  const after = [tab('general'), tab('serials'), tab('lines'), tab('notes')];
  assert.equal(resolveActiveTabKey(after, active), 'notes');
});

test('حذف التبويب النشط يسقط إلى الأول بلا لوحة فارغة', () => {
  const after = [tab('general'), tab('lines')];
  assert.equal(resolveActiveTabKey(after, 'notes'), 'general');
});

test('التبويب النشط يبقى نفسه ولو أُعيد ترتيب القائمة', () => {
  assert.equal(resolveActiveTabKey([tab('notes'), tab('general')], 'general'), 'general');
});
