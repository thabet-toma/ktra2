import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getPickerFieldVisibility } from './pickerFieldVisibility.ts';

test('شراء + عين مفتوحة: السعر التقديري ومصدره ظاهران', () => {
  const v = getPickerFieldVisibility('purchase', true);
  assert.equal(v.indicativePurchasePrice, true);
});

test('بيع + عين مفتوحة: ظاهر أيضاً — البائع مسموح له أن يراه', () => {
  const v = getPickerFieldVisibility('sale', true);
  assert.equal(v.indicativePurchasePrice, true);
});

test('بيع + عين مغلقة: غائب', () => {
  const v = getPickerFieldVisibility('sale', false);
  assert.equal(v.indicativePurchasePrice, false);
});

test('طباعة/تصدير: السعر غائبٌ بصرف النظر عن حالة العين — كلتا الحالتين صراحةً', () => {
  const withEyeOpen = getPickerFieldVisibility('print', true);
  const withEyeClosed = getPickerFieldVisibility('print', false);
  assert.equal(withEyeOpen.indicativePurchasePrice, false);
  assert.equal(withEyeClosed.indicativePurchasePrice, false);
});

test('شارة المخزون والمتاح بعد الحجز ظاهران في كلا سياقَي المستند (شراء وبيع)', () => {
  for (const ctx of ['purchase', 'sale'] as const) {
    for (const eye of [true, false]) {
      const v = getPickerFieldVisibility(ctx, eye);
      assert.equal(v.stockBadge, true, `${ctx}/${eye}: stockBadge يجب أن يظهر`);
      assert.equal(v.availableAfterReservation, true, `${ctx}/${eye}: availableAfterReservation يجب أن يظهر`);
    }
  }
});

test('الطباعة/التصدير: شارة المخزون والمتاح بعد الحجز غائبان أيضاً — لا بيانات مستند حيّة على الورقة', () => {
  for (const eye of [true, false]) {
    const v = getPickerFieldVisibility('print', eye);
    assert.equal(v.stockBadge, false);
    assert.equal(v.availableAfterReservation, false);
  }
});

test('حارس التسرّب: شراء + عين مغلقة أيضاً يخفي السعر — نفس عين البيع', () => {
  const v = getPickerFieldVisibility('purchase', false);
  assert.equal(v.indicativePurchasePrice, false);
});
