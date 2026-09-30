/**
 * G1 (أولوية قصوى — مطلوبة مراراً): مُنسّق أرقام موحّد لكل الواجهة.
 *
 * يحذف الأصفار العشرية غير الدالّة: يُظهر العدد الصحيح عندما يكون الكسر صفراً،
 * ويُظهر الكسر الدالّ فقط فيما عدا ذلك.
 *   30490.00 → "30490" · 105.00 → "105" · 187.50 → "187.5" · 187.55 → "187.55"
 *
 * مصدر حقيقة واحد — كل عرض رقمي في النظام يمرّ عبر هذه الدالة (لا حِيَل لكل حقل).
 */
export interface FormatNumberOptions {
  /** أقصى عدد منازل عشرية قبل قص الأصفار (افتراضي 2 للمبالغ، 4 للكميات/الأسعار) */
  maxDecimals?: number;
  /** فاصل آلاف (افتراضي false مطابقةً للمثال الحرفي في G1: 30490 وليس 30,490) */
  group?: boolean;
  /** النص المُعاد عند تعذّر التحويل (افتراضي "") */
  fallback?: string;
}

export function formatNumber(value: unknown, options: FormatNumberOptions = {}): string {
  const { maxDecimals = 2, group = false, fallback = "" } = options;
  const n = typeof value === "number" ? value : Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n)) {
    return fallback;
  }
  const decimals = Math.max(0, Math.trunc(maxDecimals));
  // قص إلى أقصى منازل (يطابق سلوك toFixed) ثم حذف الأصفار غير الدالّة
  const fixed = n.toFixed(decimals); // "30490.00" / "-187.50"
  const negative = fixed.startsWith("-");
  const absFixed = negative ? fixed.slice(1) : fixed;
  const dot = absFixed.indexOf(".");
  let intPart = dot === -1 ? absFixed : absFixed.slice(0, dot);
  let fracPart = dot === -1 ? "" : absFixed.slice(dot + 1).replace(/0+$/, "");
  if (group) {
    intPart = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  const body = fracPart ? `${intPart}.${fracPart}` : intPart;
  return negative && body !== "0" ? `-${body}` : body;
}

/** اختصار للمبالغ المالية مع فاصل الآلاف (يطابق احتفاظ الواجهة الحالية بالتجميع). */
export function formatMoney(value: unknown, fallback = "0"): string {
  return formatNumber(value, { maxDecimals: 2, group: true, fallback });
}

/** اختصار للكميات/أسعار الوحدة (حتى 4 منازل، بلا تجميع). */
export function formatQuantity(value: unknown, fallback = ""): string {
  return formatNumber(value, { maxDecimals: 4, group: false, fallback });
}

/**
 * رصيد محاسبي بإشارته وجانبه معاً: «-1,888 مدين» / «1,112 دائن».
 *
 * المدخل بإشارة الأستاذ (الرصيد = مدين − دائن). المعروض بقرار المالك
 * (2026-09-30، #33/#69): **المدين سالب** والدائن موجب، والكلمة بجانب الرقم دائماً
 * فلا تكون الإشارة وحدها الدليل. والصفر بلا جانب.
 *
 * الرقم محصورٌ في عزلٍ اتّجاهيٍّ LTR (U+2066…U+2069): بدونه يرسم المتصفح في واجهة
 * RTL السالبَ في نهاية الرقم («1,888-») — وهي الشكوى التي أسقطت الإشارة سابقاً.
 */
export function formatBalanceWithSide(value: unknown, fallback = "0"): string {
  const n = typeof value === "number" ? value : Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n)) {
    return fallback;
  }
  if (Math.abs(n) < 0.005) return formatMoney(0);
  return `\u2066${formatMoney(-n)}\u2069 ${n > 0 ? "مدين" : "دائن"}`;
}

/**
 * رصيد طرف (عميل/مورّد/مخلّص…) بإشارة الخادم إلى القاعدة الموحّدة أعلاه.
 *
 * الخادم يعطي رصيد الطرف بإشارةٍ تختلف بنوعه (`partners/models.py` — `is_creditor_party`):
 * العميل مدين − دائن، والطرف الدائن دائن − مدين. `isCreditor` يأتي من الخادم نفسه
 * (`is_creditor` في الـprofile والكشف) — لا يُشتقّ من نوع الطرف في الواجهة.
 */
export function formatPartyBalance(value: unknown, isCreditor: boolean, fallback = "0"): string {
  const n = typeof value === "number" ? value : Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n)) {
    return fallback;
  }
  return formatBalanceWithSide(isCreditor ? -n : n, fallback);
}
