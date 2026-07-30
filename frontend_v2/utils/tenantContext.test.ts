import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pickActiveMembership } from './tenantContext.ts';

const member = (id: number, isDefault = false) => ({
  tenant: { TenantID: id },
  is_default: isDefault,
});

test('الاختيار الصريح المخزَّن في المتصفح يتقدّم على الافتراضية', () => {
  const rows = [member(1), member(7, true)];
  assert.equal(pickActiveMembership(rows, 1)?.tenant.TenantID, 1);
});

test('بلا اختيار صريح تُفتح الشركة الافتراضية لا أوّل شركة', () => {
  // العيب الأصلي: بعد الدخول (والخروج يمحو المفتاح) كان الرقم المُلفَّق 1
  // يُقرأ كاختيار، فتُفتح الشركة 1 بدل الافتراضية.
  const rows = [member(1), member(7, true)];
  assert.equal(pickActiveMembership(rows, null)?.tenant.TenantID, 7);
});

test('شركة مخزَّنة لم يبقَ المستخدم عضواً فيها تسقط على الافتراضية', () => {
  const rows = [member(1), member(7, true)];
  assert.equal(pickActiveMembership(rows, 99)?.tenant.TenantID, 7);
});

test('بلا افتراضية تُفتح أول شركة، وبلا شركات تُعاد null', () => {
  assert.equal(pickActiveMembership([member(4), member(9)], null)?.tenant.TenantID, 4);
  assert.equal(pickActiveMembership([], null), null);
});
