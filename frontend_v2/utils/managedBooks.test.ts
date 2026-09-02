import assert from 'node:assert/strict';
import test from 'node:test';

import { orderOfficesByPreference, pickOfficeTenant } from './managedBooks.ts';

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

// ── بلاغ المالك: «الدخول للدفتر بوديني على شركتي الافتراضية» ─────────────────

test('داخل الدفتر: المكتب المكتوب لحظةَ الدخول يسبق أصغر معرّف', () => {
  const rows = [
    membership(3, 'manager', 'accounting_firm'),
    membership(9, 'manager', 'accounting_firm'),
  ];
  // الشركة النشطة هي الدفتر (99) وليست مكتباً، فبلا `bookOfficeId` كان يُختار
  // المكتب 3 — وقائمةُ دفاتره لا تحوي دفترنا ⇒ سقوطٌ على الشركة الافتراضية.
  const ordered = orderOfficesByPreference(rows, { bookOfficeId: 9, activeTenantId: 99 });
  assert.deepEqual(ordered.map((m) => m.tenant.TenantID), [9, 3]);
});

test('كل المكاتب تبقى مرشَّحةً بعد المفضَّل — فلا يضيع دفترٌ في مكتبٍ آخر', () => {
  const rows = [
    membership(3, 'manager', 'accounting_firm'),
    membership(9, 'manager', 'accounting_firm'),
    membership(5, 'manager', 'general'),
  ];
  assert.deepEqual(
    orderOfficesByPreference(rows, { activeTenantId: 9 }).map((m) => m.tenant.TenantID),
    [9, 3],
  );
});

test('مكتبُ الجلسة يُقبل ولو بلا قالب مكتب — الجلسة تشهد أننا جئنا منه', () => {
  const rows = [membership(5, 'manager', 'general')];
  assert.deepEqual(
    orderOfficesByPreference(rows, { bookOfficeId: 5 }).map((m) => m.tenant.TenantID),
    [5],
  );
  // بينما الشركة النشطة وحدها لا تفتح باباً لغير المكاتب — تفضيلُ ترتيبٍ لا شهادة.
  assert.deepEqual(orderOfficesByPreference(rows, { activeTenantId: 5 }), []);
});

test('عضوية غير مديرة لا تصير مكتباً ولو سمّتها الجلسة', () => {
  const rows = [membership(7, 'accountant', 'accounting_firm')];
  assert.deepEqual(orderOfficesByPreference(rows, { bookOfficeId: 7 }), []);
});
