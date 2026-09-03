import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  PROCUREMENT_KIND_LABELS,
  canConvertImportOffer,
  isOfferStruckThrough,
  isProcurementDocClosed,
  isReservationActive,
  offerSuitability,
  procurementDocKind,
  procurementStatusLabel,
} from './documentBadges.ts';

test('نوع المستند يُشتقّ من معرّف الواجهة الموحّد', () => {
  assert.equal(procurementDocKind('order-7'), 'order');
  assert.equal(procurementDocKind('quote-12'), 'quotation');
  assert.equal(PROCUREMENT_KIND_LABELS.order, 'طلبية شراء');
  assert.equal(PROCUREMENT_KIND_LABELS.quotation, 'عرض سعر');
});

test('«محوَّل» يعني شيئين مختلفين بحسب نوع المستند', () => {
  assert.equal(procurementStatusLabel('order', 'converted'), 'محوَّلة إلى فاتورة');
  assert.equal(procurementStatusLabel('quotation', 'converted'), 'محوَّل إلى طلبية');
});

test('حالة الطلبية المؤكَّدة تختلف عن المحوَّلة (كانتا نصاً واحداً)', () => {
  const confirmed = procurementStatusLabel('order', 'confirmed');
  const converted = procurementStatusLabel('order', 'converted');
  assert.equal(confirmed, 'مؤكَّدة');
  assert.notEqual(confirmed, converted);
});

test('حالة مجهولة تسقط على البديل ثم على المفتاح نفسه', () => {
  assert.equal(procurementStatusLabel('order', 'weird', 'غير معروف'), 'غير معروف');
  assert.equal(procurementStatusLabel('order', 'weird'), 'weird');
  assert.equal(procurementStatusLabel('order', undefined), '—');
});

test('المستند المنتهي دورته لا يقبل إجراءات', () => {
  assert.equal(isProcurementDocClosed('converted'), true);
  assert.equal(isProcurementDocClosed('cancelled'), true);
  assert.equal(isProcurementDocClosed('confirmed'), false);
  assert.equal(isProcurementDocClosed(undefined), false);
});

test('عرض الاستيراد يُقرأ بلغة الملاءمة لا بلغة الإرسال', () => {
  assert.equal(procurementDocKind('quote-3', 'import'), 'import_quotation');
  assert.equal(procurementDocKind('quote-3'), 'quotation');
  assert.equal(procurementDocKind('order-3', 'import'), 'order');
  assert.equal(PROCUREMENT_KIND_LABELS.import_quotation, 'عرض استيراد');
  assert.equal(procurementStatusLabel('import_quotation', 'accepted'), 'ملائم');
  assert.equal(procurementStatusLabel('import_quotation', 'rejected'), 'غير ملائم');
  // نفس المفتاح، ثلاث دلالات مختلفة بحسب النوع
  assert.equal(procurementStatusLabel('import_quotation', 'converted'), 'محوَّل إلى صفقة');
  assert.equal(procurementStatusLabel('quotation', 'converted'), 'محوَّل إلى طلبية');
  assert.equal(procurementStatusLabel('order', 'converted'), 'محوَّلة إلى فاتورة');
});

/**
 * T-OFFERSTATE: «بانتظار معلومات» و«قيد المناقشة» كانتا تُسقَطان على `sent`،
 * فتقرأ القائمة «مُرسَل للمورد» مهما اخترتَ داخل العرض. الحالة المعروضة يجب أن
 * تكون هي المخزَّنة — وهما ليستا قراراً بعد (لا ملائم ولا غير ملائم).
 */
test('حالتا الانتظار والمناقشة تُعرضان باسميهما لا كـ«مُرسَل للمورد»', () => {
  assert.equal(procurementStatusLabel('import_quotation', 'pending_info'), 'بانتظار معلومات');
  assert.equal(procurementStatusLabel('import_quotation', 'under_discussion'), 'قيد المناقشة');
  assert.equal(procurementStatusLabel('quotation', 'pending_info'), 'بانتظار معلومات');
  assert.equal(procurementStatusLabel('quotation', 'under_discussion'), 'قيد المناقشة');

  assert.equal(offerSuitability('pending_info'), 'undecided');
  assert.equal(offerSuitability('under_discussion'), 'undecided');
  assert.equal(isOfferStruckThrough('pending_info'), false);
  assert.equal(isProcurementDocClosed('pending_info'), false);
  // الانتظار ليس قبولاً — لا يُحوَّل إلى صفقة.
  assert.equal(canConvertImportOffer('pending_info'), false);
});

test('الشطب علامة «غير ملائم» لا علامة انتهاء دورة', () => {
  assert.equal(offerSuitability('rejected'), 'unsuitable');
  assert.equal(offerSuitability('expired'), 'unsuitable');
  assert.equal(offerSuitability('accepted'), 'suitable');
  assert.equal(offerSuitability('converted'), 'suitable');
  assert.equal(offerSuitability('draft'), 'undecided');
  assert.equal(offerSuitability(undefined), 'undecided');

  assert.equal(isOfferStruckThrough('rejected'), true);
  // المحوَّل إلى صفقة منتهي الدورة لكنه ليس مشطوباً — نجاحٌ لا رفض.
  assert.equal(isProcurementDocClosed('converted'), true);
  assert.equal(isOfferStruckThrough('converted'), false);
  assert.equal(isOfferStruckThrough('draft'), false);
});

test('ISSUE #113: الطلبية (rfq-) نوعٌ رابع بلا تفريق محلي/استيراد', () => {
  assert.equal(procurementDocKind('rfq-5'), 'rfq');
  assert.equal(procurementDocKind('rfq-5', 'import'), 'rfq');
  assert.equal(PROCUREMENT_KIND_LABELS.rfq, 'طلبية');
  assert.equal(procurementStatusLabel('rfq', 'draft'), 'مسودة');
  assert.equal(procurementStatusLabel('rfq', 'sent'), 'مُرسَلة');
  assert.equal(procurementStatusLabel('rfq', 'awarded'), 'مُرساة');
  assert.equal(procurementStatusLabel('rfq', 'cancelled'), 'ملغاة');
  assert.equal(isProcurementDocClosed('awarded'), true);
});

test('التحويل إلى صفقة متاح للملائم فقط ومرة واحدة', () => {
  assert.equal(canConvertImportOffer('accepted'), true);
  assert.equal(canConvertImportOffer('converted'), false);
  assert.equal(canConvertImportOffer('draft'), false);
  assert.equal(canConvertImportOffer('rejected'), false);
  assert.equal(canConvertImportOffer(undefined), false);
});

test('الحجز سارٍ فقط للطلبية المؤكَّدة التي لم ينتهِ تاريخها', () => {
  assert.equal(isReservationActive('confirmed', '2026-08-02', '2026-07-30'), true);
  // اليوم الأخير محسوب ضمن الحجز
  assert.equal(isReservationActive('confirmed', '2026-07-30', '2026-07-30'), true);
  // انتهت المدّة
  assert.equal(isReservationActive('confirmed', '2026-07-29', '2026-07-30'), false);
  // ملغاة/محوَّلة/مسودة لا تحجز ولو بقي التاريخ
  assert.equal(isReservationActive('cancelled', '2026-08-02', '2026-07-30'), false);
  assert.equal(isReservationActive('converted', '2026-08-02', '2026-07-30'), false);
  assert.equal(isReservationActive('draft', '2026-08-02', '2026-07-30'), false);
  // بلا تاريخ حجز (الحجز معطّل بالإعدادات)
  assert.equal(isReservationActive('confirmed', null, '2026-07-30'), false);
});

/**
 * حارس ارتداد: أسماء توكنات المسافات في `@theme` تخطف مقاييس العرض في Tailwind v4.
 * `--spacing-sm: .25rem` جعل `max-w-sm` = 4px فانطوت كل النوافذ التي تستعمله
 * (منها نافذة العربون: النص يتكسّر حرفاً حرفاً فيبدو السعر مشوَّهاً).
 */
test('توكنات @theme لا تخطف مقاييس عرض Tailwind (max-w-sm…)', () => {
  const css = readFileSync(new URL('../styles/index.css', import.meta.url), 'utf8');
  const collidingNames = ['xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl'];
  const found = collidingNames.filter((name) =>
    new RegExp(`^\\s*--spacing-${name}\\s*:`, 'm').test(css),
  );
  assert.deepEqual(
    found,
    [],
    `توكن --spacing-${found.join('/--spacing-')} يخطف max-w-${found.join('/max-w-')}؛ `
      + 'استعمل اسماً رقمياً أو توكناً خارج نطاق spacing.',
  );
});
