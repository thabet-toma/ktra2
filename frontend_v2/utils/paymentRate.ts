/**
 * سعر الدولار للشيكل في حمولة دفعة الاستيراد (دفعة صفقة / دفعة وكيل الشحن).
 *
 * كانت المُحوِّلات تكتب `?? 3.5` (و`|| 3.6` في شاشة المستند) فتُحفظ الدفعة بسعرٍ لم
 * يُدخله أحد ثم تُرحَّل به — 101 من 137 دفعة على الإنتاج بـ3.5 بالزبط. الآن: سعرٌ
 * موجب يُرسَل كما هو، وغيره (فارغ، صفر، غير رقم) يُحذف مفتاحه من الحمولة — فالإنشاء
 * يحفظ «بلا سعر» والخادم يرفض الترحيل بسبب مقروء، والتعديل الجزئي (PATCH) لا يمحو
 * سعراً محفوظاً.
 */
export function usdRateForPayload(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

/* ───────────────────────────────────────────────────────────────────────────
 * سعر الصرف في الدفعات بعملةٍ غير الأساسية — قاعدة المالك: كل دفعة بعملة غير
 * الشيكل تحمل سعراً كتبه المستخدم بنفسه. لا افتراضي 1 صامتاً، ولا سعر لم يره.
 * وبالشيكل لا يتغيّر شيء: لا حقل، ولا نقرة زائدة، ولا تحقّق جديد.
 *
 * مصدر واحد تستهلكه كل الشاشات ومكوّن `components/shared/ExchangeRateField.tsx`.
 * الخادم هو الحارس الأخير. (غير `usdRateForPayload` أعلاه: تلك لدفعات الاستيراد
 * بحقل `usd_to_ils` العددي، وهذه لحقل `exchange_rate` النصّي في بقية الدفعات.)
 * ─────────────────────────────────────────────────────────────────────────── */

export interface CurrencyLike {
  Code?: string | null;
  code?: string | null;
  IsBaseCurrency?: boolean | null;
  is_base?: boolean | null;
}

/** رمز العملة الأساسية عند غياب العلم من الخادم. */
const BASE_FALLBACK_CODE = "ILS";

/** أساسية إن حملت العلم صراحةً، وإلا بالرمز ILS. غياب العملة = أساسية. */
export function isBaseCurrency(currency: CurrencyLike | null | undefined): boolean {
  if (!currency) return true;
  if (currency.IsBaseCurrency === true || currency.is_base === true) return true;
  if (currency.IsBaseCurrency === false || currency.is_base === false) return false;
  const code = currency.Code ?? currency.code ?? "";
  return String(code).trim().toUpperCase() === BASE_FALLBACK_CODE;
}

const DOT_DECIMAL = /^\d+(\.\d+)?$/;

/** خطأٌ عربي أو `null`. فاصلة عشرية بنقطة فقط، بعد قصّ الفراغات. */
export function validateRate(raw: string): string | null {
  const text = (raw ?? "").trim();
  if (!text) return "اكتب سعر الصرف";
  if (!DOT_DECIMAL.test(text)) return "سعر الصرف رقم بنقطة عشرية (مثل 3.7)";
  const n = Number(text);
  if (!Number.isFinite(n)) return "سعر الصرف رقم بنقطة عشرية (مثل 3.7)";
  if (n <= 0) return "سعر الصرف يجب أن يكون أكبر من صفر";
  if (n === 1) return "سعر 1 لعملة أجنبية غير مقبول";
  return null;
}

/** قيمة `exchange_rate` في الحمولة: تُحذف للأساسية، وللأجنبية النص المقصوص. */
export function rateForPayload(currencyIsBase: boolean, raw: string): string | undefined {
  if (currencyIsBase) return undefined;
  return (raw ?? "").trim();
}

/** العملة الافتراضية لنموذج جديد: الأساسية صراحةً، وإلا الأولى — لا «الأولى» وحدها. */
export function defaultCurrency<T extends CurrencyLike>(currencies: readonly T[]): T | undefined {
  return currencies.find((c) => isBaseCurrency(c)) ?? currencies[0];
}
