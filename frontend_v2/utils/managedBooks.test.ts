import assert from 'node:assert/strict';
import test from 'node:test';

import { pickOfficeTenant } from './managedBooks.ts';

const membership = (id: number, role: string, template?: string) => ({
  role,
  tenant: { TenantID: id, template },
});

test('لا مكتب ⇒ لا باب: شركة تجارية يديرها المستخدم ليست مكتباً', () => {
  const rows = [membership(1, 'manager', 'general'), membership(2, 'manager')];
  assert.equal(pickOfficeTenant(rows, 1), null);
});

test('عضوية غير مديرة في مكتب لا تفتح دفاتره', () => {
  const rows = [membership(4, 'accountant', 'accounting_firm')];
  assert.equal(pickOfficeTenant(rows, 4), null);
});

test('المكتب الوحيد يُختار مهما كانت الشركة النشطة', () => {
  const rows = [membership(1, 'manager', 'general'), membership(7, 'manager', 'accounting_firm')];
  // الشركة النشطة هنا **دفتر عميل** ليس في القائمة أصلاً — وهي الحالة الفعلية
  // بعد الدخول إلى دفتر: لو رجعت null لاختفى زرّ العودة إلى المكتب.
  assert.equal(pickOfficeTenant(rows, 99)?.tenant.TenantID, 7);
});

test('من يدير مكتبين يفتح دفاتر المكتب الذي يعمل عليه الآن', () => {
  const rows = [
    membership(3, 'manager', 'accounting_firm'),
    membership(9, 'manager', 'accounting_firm'),
  ];
  assert.equal(pickOfficeTenant(rows, 9)?.tenant.TenantID, 9);
});

test('بلا شركة نشطة ⇒ أصغر معرّف لا أوّل ما وصل من الخادم', () => {
  const rows = [
    membership(9, 'manager', 'accounting_firm'),
    membership(3, 'manager', 'accounting_firm'),
  ];
  assert.equal(pickOfficeTenant(rows, null)?.tenant.TenantID, 3);
  assert.equal(pickOfficeTenant([...rows].reverse(), null)?.tenant.TenantID, 3);
});
