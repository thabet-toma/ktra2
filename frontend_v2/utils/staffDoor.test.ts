import assert from 'node:assert/strict';
import test from 'node:test';

import { isStaffPreview, staffDoorFor } from './staffDoor.ts';

test('المالكُ يرى باباً إلى مساحة الموظّف — وهو ما كان مفقوداً', () => {
  const door = staffDoorFor({ isSuperAdmin: true, isPlatformEmployee: false });
  assert.notEqual(door, null);
  assert.equal(door?.preview, true);
});

test('بابُ المالك يقول «معاينة» لا «مساحتي»', () => {
  // اسمٌ واحدٌ للبابين كان سيجعل المالكَ يقرأ لوحاتِه الفارغةَ عطباً في حسابه.
  const owner = staffDoorFor({ isSuperAdmin: true, isPlatformEmployee: false });
  const staff = staffDoorFor({ isSuperAdmin: false, isPlatformEmployee: true });
  assert.notEqual(owner?.label, staff?.label);
  assert.equal(staff?.preview, false);
});

test('موظّفُ المنصّة يذهب إلى مساحته هو ولو كان سوبر أدمن أيضاً', () => {
  const door = staffDoorFor({ isSuperAdmin: true, isPlatformEmployee: true });
  assert.equal(door?.preview, false);
});

test('من ليس موظّفَ منصّةٍ ولا سوبر أدمن لا بابَ له', () => {
  assert.equal(staffDoorFor({ isSuperAdmin: false, isPlatformEmployee: false }), null);
});

test('«معاينة» لا تُعلَن قبل حسمِ ملفّ الموظّف', () => {
  assert.equal(isStaffPreview({ isSuperAdmin: true, profileSettled: false, hasProfile: false }), false);
  assert.equal(isStaffPreview({ isSuperAdmin: true, profileSettled: true, hasProfile: false }), true);
});

test('سوبر أدمن له ملفُّ موظّفٍ حقيقيٌّ ليس معايناً', () => {
  assert.equal(isStaffPreview({ isSuperAdmin: true, profileSettled: true, hasProfile: true }), false);
});

test('الموظّفُ العاديُّ لا يُقال له «أنت تعاين»', () => {
  assert.equal(isStaffPreview({ isSuperAdmin: false, profileSettled: true, hasProfile: false }), false);
});
