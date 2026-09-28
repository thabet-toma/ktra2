import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  addWarrantyMonths,
  deriveWarrantyEnd,
  manufacturerWarrantyRemainingText,
  manufacturerWarrantyStatusLabel,
  serialImpactConfirmationLines,
  serialImpactNeedsConfirmation,
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

test('#222 — بطاقة منتهية بواقعة لا تُعرض سارية أبداً حتى بأيامٍ موجبة', () => {
  assert.equal(warrantyStatusLabel('ended'), 'غير سارية');
  assert.notEqual(warrantyStatusLabel('ended'), 'سارية');
  // نهايتها قد تبقى في المستقبل (جهازٌ أُرجع قبل انقضاء مدّته) — أيامٌ موجبة
  // ومع ذلك النص لا يُشتقّ منها بحساب «باقٍ» أو «منذ».
  assert.equal(warrantyRemainingText('ended', 200), 'لم تعد سارية');
});

test('#232 — طبقة المصنع: `null` من الخادم يعني «لا يوجد» صراحةً', () => {
  assert.equal(manufacturerWarrantyStatusLabel(null), 'لا يوجد');
  assert.equal(manufacturerWarrantyRemainingText(null, null), 'لا يوجد');
  // بلا جهة كفالة مصنع لا تُقرأ «منتهية» ولا أي حالةٍ أخرى من طبقة التاجر.
  assert.notEqual(manufacturerWarrantyStatusLabel(null), warrantyStatusLabel('expired'));
});

test('#232 — طبقة المصنع بجهة: نفس مفردات طبقة التاجر حرفياً', () => {
  assert.equal(manufacturerWarrantyStatusLabel('active'), 'سارية');
  assert.equal(manufacturerWarrantyStatusLabel('expired'), 'منتهية');
  assert.equal(manufacturerWarrantyStatusLabel('ended'), 'غير سارية');
  assert.match(manufacturerWarrantyRemainingText('active', 45), /^باقٍ /);
  assert.equal(manufacturerWarrantyRemainingText('ended', 30), 'لم تعد سارية');
});

test('#233 — لا تأكيد لازم بلا إخوة وبلا وحدات غير مرقَّمة', () => {
  assert.equal(serialImpactNeedsConfirmation({ siblingCount: 0, unitsRows: [] }), false);
  assert.equal(
    serialImpactNeedsConfirmation({
      siblingCount: 0, unitsRows: [{ productName: 'أ', count: 0 }],
    }),
    false,
  );
});

test('#233 — إخوةٌ فقط، أو وحداتٌ فقط، كلٌّ منهما يكفي للتأكيد', () => {
  assert.equal(
    serialImpactNeedsConfirmation({ siblingCount: 1, unitsRows: [] }), true,
  );
  assert.equal(
    serialImpactNeedsConfirmation({
      siblingCount: 0, unitsRows: [{ productName: 'أ', count: 3 }],
    }),
    true,
  );
});

test('#233 — رسالة التأكيد تسمّي الإخوة وتُدرج وحدات كل منتجٍ له رصيد فقط', () => {
  const lines = serialImpactConfirmationLines({
    siblingNames: ['تي بي لينك', 'نتغير'],
    unitsRows: [
      { productName: 'الأصلي', count: 4 },
      { productName: 'بلا رصيد', count: 0 },
    ],
  });
  assert.equal(lines.length, 2);
  assert.match(lines[0], /تي بي لينك، نتغير/);
  assert.match(lines[1], /الأصلي/);
  assert.match(lines[1], /4/);
  assert.ok(!lines.some((l) => l.includes('بلا رصيد')));
});

test('#233 — بلا إخوة وبلا رصيدٍ لأي منتج، لا سطور إطلاقاً', () => {
  assert.deepEqual(
    serialImpactConfirmationLines({
      siblingNames: [],
      unitsRows: [{ productName: 'أ', count: 0 }],
    }),
    [],
  );
});
