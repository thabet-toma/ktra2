import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  addWarrantyMonths,
  deriveWarrantyEnd,
  warrantyRemainingText,
  warrantyStatusLabel,
} from './warranty.ts';

test('الشهور تقويمية لا 30 يوماً — واليوم يُثبَّت على آخر الشهر حين يقصر', () => {
  assert.equal(addWarrantyMonths('2026-01-31', 1), '2026-02-28');
  // سنة كبيسة: 29 فبراير موجود فلا يُقصّ إلى 28.
  assert.equal(addWarrantyMonths('2028-01-31', 1), '2028-02-29');
  assert.equal(addWarrantyMonths('2026-08-10', 12), '2027-08-10');
  // عبور رأس السنة يزيد السنة ولا يخلط الشهر صفراً.
  assert.equal(addWarrantyMonths('2026-12-15', 1), '2027-01-15');
  assert.equal(addWarrantyMonths('2026-08-10', 0), '2026-08-10');
});

test('التاريخ يُحسب على النص لا على Date المحلي', () => {
  // إنشاء Date من نص بلا منطقة زمنية يزيح اليوم على أجهزة شرق غرينتش —
  // هذا الاختبار يسقط لو عاد الحساب إلى `new Date(iso)`.
  assert.equal(addWarrantyMonths('2026-03-01', 1), '2026-04-01');
  assert.equal(addWarrantyMonths('2026-01-01', 24), '2028-01-01');
});

test('النص غير الصالح يعيد فراغاً بدل تاريخ مُلفَّق', () => {
  assert.equal(addWarrantyMonths('', 12), '');
  assert.equal(addWarrantyMonths('غير تاريخ', 12), '');
});

test('التاريخ الصريح يتقدّم على المشتقّ من المدة', () => {
  assert.equal(deriveWarrantyEnd('2026-08-10', 12), '2027-08-10');
  assert.equal(deriveWarrantyEnd('2026-08-10', 12, '2029-01-01'), '2029-01-01');
  // بلا مدة وبلا تاريخ صريح لا اشتقاق — الخادم هو من يرفض، والواجهة لا تخترع.
  assert.equal(deriveWarrantyEnd('2026-08-10', null), '');
  assert.equal(deriveWarrantyEnd('', 12), '');
});

test('نص التبقّي يقرأ المنتهية بإشارتها الصحيحة', () => {
  assert.equal(warrantyStatusLabel('active'), 'سارية');
  assert.equal(warrantyStatusLabel('expired'), 'منتهية');
  assert.match(warrantyRemainingText('active', 12), /^باقٍ /);
  assert.equal(warrantyRemainingText('active', 0), 'تنتهي اليوم');
  // −30 يوماً على بطاقة منتهية تُقرأ «منذ 30» لا «باقٍ −30».
  assert.match(warrantyRemainingText('expired', -30), /^انتهت منذ /);
  assert.ok(!warrantyRemainingText('expired', -30).includes('-'));
});
