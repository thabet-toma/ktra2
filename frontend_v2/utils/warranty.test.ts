import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  addWarrantyMonths,
  dealWarrantyYearsToMonths,
  deriveWarrantyEnd,
  manufacturerWarrantyRemainingText,
  manufacturerWarrantyStatusLabel,
  purchaseLineWarrantyDiffers,
  purchaseLineWarrantyFromPolicy,
  purchaseLineWarrantyPayload,
  purchaseLineWarrantyProblem,
  serialImpactConfirmationLines,
  serialImpactNeedsConfirmation,
  warrantyCoveredQuantityLabel,
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

// #234: بطاقة «كفالة على الفاتورة» — الكمية المغطاة N من Q، بلا رقم تسلسلي.
test('#234 — warrantyCoveredQuantityLabel يكتب «الكمية المغطاة N من Q»', () => {
  assert.equal(warrantyCoveredQuantityLabel(4, 4), 'الكمية المغطاة 4 من 4');
  assert.equal(warrantyCoveredQuantityLabel(1, 4), 'الكمية المغطاة 1 من 4');
  assert.equal(warrantyCoveredQuantityLabel(0, 4), 'الكمية المغطاة 0 من 4');
});

// #235: كفالة المصنع على سطر الشراء.
const LINE_POLICY = { manufacturer_warrantor: 7, manufacturer_months: 24, supplier_months: 6 };

test('#235 — الصفقة بالسنوات تُحوَّل إلى أشهر، وغير الصالح صفر', () => {
  assert.equal(dealWarrantyYearsToMonths(2), 24);
  assert.equal(dealWarrantyYearsToMonths('1'), 12);
  assert.equal(dealWarrantyYearsToMonths(0), 0);
  assert.equal(dealWarrantyYearsToMonths(-1), 0);
  assert.equal(dealWarrantyYearsToMonths(undefined), 0);
  assert.equal(dealWarrantyYearsToMonths('abc'), 0);
});

test('#235 — القيمة الابتدائية من السياسة، وكفالة المورّد من الصفقة إن وُجدت', () => {
  assert.deepEqual(purchaseLineWarrantyFromPolicy(LINE_POLICY), {
    manufacturer_warrantor: 7,
    manufacturer_months: 24,
    supplier_months: 6,
  });
  assert.equal(purchaseLineWarrantyFromPolicy(LINE_POLICY, 2).supplier_months, 24);
  // صفقة بلا مدة لا تصفّر كفالة المورّد التي في السياسة.
  assert.equal(purchaseLineWarrantyFromPolicy(LINE_POLICY, 0).supplier_months, 6);
});

test('#235 — «يختلف عن السياسة» يقارن طبقة المصنع لا كفالة المورّد', () => {
  const same = purchaseLineWarrantyFromPolicy(LINE_POLICY);
  assert.equal(purchaseLineWarrantyDiffers(same, LINE_POLICY), false);
  assert.equal(purchaseLineWarrantyDiffers({ ...same, supplier_months: 99 }, LINE_POLICY), false);
  assert.equal(purchaseLineWarrantyDiffers({ ...same, manufacturer_months: 12 }, LINE_POLICY), true);
  assert.equal(purchaseLineWarrantyDiffers({ ...same, manufacturer_warrantor: 8 }, LINE_POLICY), true);
  assert.equal(
    purchaseLineWarrantyDiffers({ ...same, manufacturer_warrantor: null, manufacturer_months: 0 }, LINE_POLICY),
    true,
  );
});

test('#235 — الحمولة أعدادٌ صحيحة وكفالة المورّد الفارغة null', () => {
  assert.deepEqual(
    purchaseLineWarrantyPayload({ manufacturer_warrantor: 7, manufacturer_months: 24.9, supplier_months: null }),
    { manufacturer_warrantor: 7, manufacturer_months: 24, supplier_months: null },
  );
  assert.equal(
    purchaseLineWarrantyPayload({ manufacturer_warrantor: null, manufacturer_months: 0, supplier_months: 6 })
      .supplier_months,
    6,
  );
});

test('#235 — الفحص المبكّر يطابق قواعد الخادم', () => {
  const ok = { manufacturer_warrantor: 7, manufacturer_months: 24, supplier_months: 6 };
  assert.equal(purchaseLineWarrantyProblem(ok), null);
  assert.equal(
    purchaseLineWarrantyProblem({ manufacturer_warrantor: null, manufacturer_months: 0, supplier_months: null }),
    null,
  );
  assert.match(
    purchaseLineWarrantyProblem({ ...ok, manufacturer_warrantor: null }) ?? '',
    /بلا جهة كفالة مصنع/,
  );
  assert.match(purchaseLineWarrantyProblem({ ...ok, manufacturer_months: 0 }) ?? '', /حدّد مدتها/);
  assert.match(purchaseLineWarrantyProblem({ ...ok, manufacturer_months: 601 }) ?? '', /600/);
  assert.match(purchaseLineWarrantyProblem({ ...ok, supplier_months: 601 }) ?? '', /المورّد/);
  assert.equal(purchaseLineWarrantyProblem({ ...ok, manufacturer_months: 600 }), null);
});


import {
  WARRANTY_VOID_REASONS,
  warrantyEventLabel,
  warrantyUndoReasonValid,
  warrantyVoidImpactLine,
  warrantyVoidProblem,
  warrantyVoidReasonLabel,
} from './warranty.ts';

test('#236 — «ملغاة» حالةٌ قائمة بذاتها لا «منتهية»', () => {
  assert.equal(warrantyStatusLabel('voided'), 'ملغاة');
  assert.notEqual(warrantyRemainingText('voided', 400), 'باقٍ 400 يوماً');
  assert.match(warrantyRemainingText('voided', -5), /أُلغيت/);
});

test('#236 — «أخرى» تستلزم ملاحظة والسبب من القائمة وحدها', () => {
  assert.equal(WARRANTY_VOID_REASONS.length, 6);
  assert.equal(warrantyVoidReasonLabel('liquid'), 'تعرّض لسوائل');
  assert.equal(warrantyVoidReasonLabel('nope'), '');
  assert.match(warrantyVoidProblem('', '') ?? '', /اختر/);
  assert.match(warrantyVoidProblem('nope', 'x') ?? '', /غير معروف/);
  assert.match(warrantyVoidProblem('other', '   ') ?? '', /ملاحظة/);
  assert.equal(warrantyVoidProblem('other', 'ختم مكسور'), null);
  assert.equal(warrantyVoidProblem('misuse', ''), null);
});

test('#236 — سبب التراجع خمسة أحرف فعلية بعد حذف الفراغ', () => {
  assert.equal(warrantyUndoReasonValid('    ab   '), false);
  assert.equal(warrantyUndoReasonValid('1234'), false);
  assert.equal(warrantyUndoReasonValid(' 12345 '), true);
});

test('#236 — التقصير لا يُقرأ «تمديداً» في السجلّ', () => {
  assert.equal(warrantyEventLabel('extend', 'shorten', 'تمديد'), 'تقصير');
  assert.equal(warrantyEventLabel('extend', '', 'تمديد'), 'تمديد');
  assert.equal(warrantyEventLabel('void', 'liquid', 'إلغاء كفالة التاجر'), 'إلغاء كفالة التاجر');
});

test('#236 — سطر المعاينة يسمّي القطع بلا سعر وعودة الأمر للموافقة', () => {
  const line = warrantyVoidImpactLine({
    order_number: 'SO-7',
    returns_to_approval: true,
    parts: [
      { product_name: 'شاشة', empty_price: false },
      { product_name: 'لوحة', empty_price: true },
    ],
  });
  assert.match(line, /^SO-7:/);
  assert.match(line, /بلا سعر/);
  assert.match(line, /انتظار الموافقة/);
  assert.match(
    warrantyVoidImpactLine({ order_number: 'SO-8', returns_to_approval: false, parts: [] }),
    /يفقد تغطية الكفالة/,
  );
});

import {
  countPrintableWarrantyCards,
  warrantyInvoicePrintLabel,
  warrantyRemovalMode,
} from './warranty.ts';
import { warrantyQrImageSrc } from './warranty.ts';

test('#237 — مصدر صورة الـQR data URI مُرمَّز لا يُحقَن كما هو', () => {
  const src = warrantyQrImageSrc('<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>');
  assert.ok(src.startsWith('data:image/svg+xml;charset=utf-8,'));
  assert.ok(!src.includes('<'));
  assert.equal(
    decodeURIComponent(src.slice('data:image/svg+xml;charset=utf-8,'.length)),
    '<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>',
  );
});

test('#238 — زرّ الفاتورة يعدّ القابلة للطباعة وحدها فيختفي عند الصفر', () => {
  assert.equal(countPrintableWarrantyCards([]), 0);
  assert.equal(countPrintableWarrantyCards([{ ended: true }, { ended: true }]), 0);
  assert.equal(countPrintableWarrantyCards([{ ended: false }, { ended: true }, { ended: false }]), 2);
  assert.equal(warrantyInvoicePrintLabel(3), 'اطبع كفالات الفاتورة (3)');
});

test('#238 — حذف لمن لم تصدر، سحب لمن صدرت، وتراجع لمن سُحبت', () => {
  const manual = { source: 'manual' as const, can_delete: true, ended: false, end_reason: '' };
  assert.equal(warrantyRemovalMode(manual), 'delete');
  assert.equal(warrantyRemovalMode({ ...manual, can_delete: false }), 'withdraw');
  assert.equal(
    warrantyRemovalMode({ ...manual, can_delete: false, ended: true, end_reason: 'withdrawn' }),
    'unwithdraw',
  );
});

test('#238 — التلقائية والمنتهية بغير السحب بلا حذف ولا سحب', () => {
  const auto = { source: 'auto_sale' as const, can_delete: false, ended: false, end_reason: '' };
  assert.equal(warrantyRemovalMode(auto), null);
  assert.equal(warrantyRemovalMode({ ...auto, source: 'manual', ended: true, end_reason: 'returned' }), null);
});


// ── #240: الاستقبال الموحّد ────────────────────────────────────────────────
import {
  intakeVerdictLabel,
  intakeVerdictTone,
  phoneKeyOf,
  type IntakeVerdict,
} from './warranty.ts';

test('#240 — مفتاح الهاتف آخر تسعة أرقام: 0599 و+970599 و00970599 مفتاحٌ واحد', () => {
  const key = phoneKeyOf('0599123456');
  assert.equal(key, '599123456');
  assert.equal(phoneKeyOf('+970599123456'), key);
  assert.equal(phoneKeyOf('00970599123456'), key);
  assert.equal(phoneKeyOf('(059) 912-3456'), key);
});

test('#240 — الأرقام الهندية والفارسية تُحوَّل قبل أخذ آخر تسعة', () => {
  assert.equal(phoneKeyOf('٠٥٩٩١٢٣٤٥٦'), '599123456');
  assert.equal(phoneKeyOf('۰۵۹۹۱۲۳۴۵۶'), '599123456');
  assert.equal(phoneKeyOf('٠٥٩٩-١٢٣٤٥٦'), phoneKeyOf('0599123456'));
});

test('#240 — أقصر من تسعة أرقام فراغٌ لا مفتاحٌ ناقص', () => {
  assert.equal(phoneKeyOf('12345678'), '');
  assert.equal(phoneKeyOf('١٢٣٤٥٦٧٨'), '');
  assert.equal(phoneKeyOf(''), '');
  assert.equal(phoneKeyOf(null), '');
  assert.equal(phoneKeyOf('غير رقم'), '');
});

test('#240 — لكل حكمٍ اسمٌ عربيّ ولونٌ: الأخضر للتغطية والإحالة والأحمر للملغاة', () => {
  const tones: Record<IntakeVerdict, string> = {
    dealer: 'green',
    referral: 'green',
    ended: 'grey',
    expired_paid: 'grey',
    voided_paid: 'red',
  };
  for (const [verdict, tone] of Object.entries(tones)) {
    assert.equal(intakeVerdictTone(verdict as IntakeVerdict), tone, verdict);
    assert.notEqual(intakeVerdictLabel(verdict as IntakeVerdict), '', verdict);
  }
  // حكمٌ مجهول من خادمٍ أحدث لا يُلوَّن أخضر بالخطأ.
  assert.equal(intakeVerdictTone('future' as IntakeVerdict), 'grey');
  assert.equal(intakeVerdictLabel('future' as IntakeVerdict), '');
});

import { duplicateOpenOrderOf, duplicateReasonValid } from './warranty.ts';

test('#240 — 409 التكرار يُستخرج منه الأمر القائم، وغيره من الأخطاء null', () => {
  const existing = { id: 7, order_number: 'SO-7', status: 'received', status_display: 'مُستلَم' };
  const duplicate = { status: 409, data: { code: 'duplicate_open_order', existing_order: existing } };
  assert.deepEqual(duplicateOpenOrderOf(duplicate), existing);
  assert.equal(duplicateOpenOrderOf({ status: 409, data: { code: 'other' } }), null);
  assert.equal(duplicateOpenOrderOf({ status: 400, data: { code: 'duplicate_open_order', existing_order: existing } }), null);
  assert.equal(duplicateOpenOrderOf(new Error('x')), null);
  assert.equal(duplicateOpenOrderOf(null), null);
});

test('#240 — سبب الفتح المكرَّر خمسة أحرف فعلية بعد حذف الفراغ', () => {
  assert.equal(duplicateReasonValid('    '), false);
  assert.equal(duplicateReasonValid('عطل'), false);
  assert.equal(duplicateReasonValid('عطلٌ آخر'), true);
});

import { looksLikeWarrantyScan } from './warranty.ts';

test('#240 — رابط QR والرمز المجرّد يُحلّان بالمسح، والتسلسلي والفاتورة والهاتف لا', () => {
  const token = 'Abc123_-Abc123_-Abc123';
  assert.equal(token.length, 22);
  assert.equal(looksLikeWarrantyScan(token), true);
  assert.equal(looksLikeWarrantyScan(`https://x.example/api/w/${token}`), true);
  assert.equal(looksLikeWarrantyScan(` https://x.example/api/w/${token}/ `), true);
  assert.equal(looksLikeWarrantyScan('SN-12345'), false);
  assert.equal(looksLikeWarrantyScan('0599123456'), false);
  assert.equal(looksLikeWarrantyScan('356938035643809'), false);
  assert.equal(looksLikeWarrantyScan(''), false);
});
