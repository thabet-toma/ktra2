import assert from 'node:assert/strict';
import test from 'node:test';

import { USER_ROLE_LABEL, userRoleLabel } from './userRoleLabel.ts';

test('الدورُ الغالبُ في النظام له اسمٌ عربيّ — وهو بلاغُ المالك نفسُه', () => {
  // ‏`hr/auth_api.py`: كلُّ من ليس سوبر أدمن ولا مديرَ عضويّةٍ يصله `employee`.
  assert.equal(userRoleLabel('employee'), 'موظف');
});

test('لا مفتاحَ إنجليزيٌّ يصل الشاشة مهما كان الدور', () => {
  for (const role of ['employee', 'store_guest', 'field_staff', 'ess', 'viewer']) {
    assert.equal(/[A-Za-z_]/.test(userRoleLabel(role)), false, role);
  }
});

test('دورٌ لا نعرفه يُعرَض «مستخدم» لا رمزَه', () => {
  assert.equal(userRoleLabel('brand_new_role'), 'مستخدم');
  assert.equal(userRoleLabel(undefined), 'مستخدم');
  assert.equal(userRoleLabel(null), 'مستخدم');
  assert.equal(userRoleLabel(''), 'مستخدم');
});

test('أدوارُ العضويّة التسعةُ لا يشترك اثنان منها في اسم', () => {
  // اسمان متطابقان يعيدان العيبَ الأوّل بصيغةٍ أخفى: القارئُ لا يميّز من أمامه.
  const membership = [
    'manager', 'accountant', 'legal_accountant', 'sales',
    'procurement', 'staff', 'ess', 'field_staff', 'viewer',
  ];
  const labels = membership.map((role) => USER_ROLE_LABEL[role]);
  assert.equal(new Set(labels).size, membership.length, labels.join(' · '));
});
