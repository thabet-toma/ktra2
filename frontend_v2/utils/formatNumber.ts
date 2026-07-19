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
 * رصيد محاسبي بجانبه صريحاً: «1,112 دائن» بدل «1,112-».
 *
 * الإشارة وحدها ملتبسة في واجهة RTL — المتصفح يرسم السالب في نهاية الرقم بصرياً
 * («1,112-») فلا يعرف القارئ أمدينٌ هو أم دائن. الاصطلاح: موجب = مدين، سالب = دائن
 * (الرصيد = مدين − دائن)، والصفر بلا جانب.
 */
export function formatBalanceWithSide(value: unknown, fallback = "0"): string {
  const n = typeof value === "number" ? value : Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n)) {
    return fallback;
  }
  const body = formatMoney(Math.abs(n));
  if (Math.abs(n) < 0.005) return body;
  return `${body} ${n > 0 ? "مدين" : "دائن"}`;
}
