import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  getHealthStatusMeta,
  isStarFilled,
  canEditRating,
  formatActivityCountNotice,
  formatRatingSampleNotice,
  formatReworkDiagnosticNotice,
} from './agentBooks.ts';

test('getHealthStatusMeta يعيد الفئات والعناوين الصحيحة للحالات الثلاث', () => {
  const excellent = getHealthStatusMeta('excellent');
  assert.equal(excellent.label, 'ممتاز');
  assert.match(excellent.colorClass, /emerald/);

  const good = getHealthStatusMeta('good');
  assert.equal(good.label, 'جيد');
  assert.match(good.colorClass, /blue/);

  const needsAttention = getHealthStatusMeta('needs_attention');
  assert.equal(needsAttention.label, 'يحتاج انتباه');
  assert.match(needsAttention.colorClass, /amber/);

  const unknown = getHealthStatusMeta('unknown_state');
  assert.equal(unknown.label, 'غير محدد');

  const nullCase = getHealthStatusMeta(null);
  assert.equal(nullCase.label, 'غير محدد');
});

test('isStarFilled يعالج النجوم والأرقام والقيم الفارغة بدقة', () => {
  assert.equal(isStarFilled(1, 4), true);
  assert.equal(isStarFilled(4, 4), true);
  assert.equal(isStarFilled(5, 4), false);

  assert.equal(isStarFilled(1, null), false);
  assert.equal(isStarFilled(1, undefined), false);
  assert.equal(isStarFilled(1, 0), false);
  assert.equal(isStarFilled(0, 4), false);
  assert.equal(isStarFilled(1, NaN), false);
});

test('canEditRating يفحص قواعد التعديل الصارمة لمرة واحدة', () => {
  // لم يقيّم بعد -> لا يمكن التعديل
  assert.equal(canEditRating(false, false), false);

  // قُيّم ولم يُعدّل بعد -> يمكن التعديل
  assert.equal(canEditRating(true, false), true);

  // قُيّم وعُدّل مرة واحدة -> لا يمكن التعديل ثانية
  assert.equal(canEditRating(true, true), false);

});

test('formatActivityCountNotice يعرض الإشعار فقط عند تجاوز السقف', () => {
  assert.equal(formatActivityCountNotice(50, 50), null);
  assert.equal(formatActivityCountNotice(20, 50), null);
  assert.equal(formatActivityCountNotice(75, 50), 'تُعرَض آخرُ 50 حركةٍ من أصل 75');
});

test('formatRatingSampleNotice يصيغ تنبيه اكتمال العينة ودخولها في التقييم', () => {
  const sufficient = formatRatingSampleNotice(5, 5, true);
  assert.match(sufficient, /مكتملة/);
  // النصُّ يسمّي ما يقيسه: درجةَ صحّة الخدمة لا أداءَ الموظف — حدّاهما مختلفان.
  assert.match(sufficient, /درجة صحة الخدمة/);
  assert.doesNotMatch(sufficient, /تقييم الموظف/);

  const insufficient = formatRatingSampleNotice(2, 5, false);
  assert.match(insufficient, /غير مكتملة/);
  assert.match(insufficient, /لا تدخل درجة صحة الخدمة/);
});

test('formatReworkDiagnosticNotice يصيغ التنبيه فقط عند وجود أوامر ملغاة', () => {
  assert.equal(formatReworkDiagnosticNotice(0), null);
  assert.equal(formatReworkDiagnosticNotice(-1), null);
  assert.match(formatReworkDiagnosticNotice(3) || '', /3 أمر عمل ملغى/);
  // التشخيصُ يقول صراحةً إنّه لا يُخصَم — قرارُ المواصفة §٨.
  assert.match(formatReworkDiagnosticNotice(3) || '', /لا يُخصَم/);
});
