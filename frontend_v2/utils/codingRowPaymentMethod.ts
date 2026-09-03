/**
 * issue #85 متابعة — عمود «طريقة الدفع» في شاشة الترميز الدفعي.
 *
 * كل صفٍّ كان يُحجَز `on_account` بلا سؤال (قرار سابق)، فكلّ مصروفٍ — حتى
 * النقديّ — يفتح ذمّةً على 2101 لا تُسدَّد أبداً. القيمة الافتراضية هنا `cash`
 * بعد تحقّق: `resolve_cash_account` (`accounting/services.py`) يحلّ صندوقاً
 * (الكود 1101 المزروع في شجرة `client_book`) لدفترٍ طازج بلا صندوقٍ مسجَّل
 * ولا إعدادات — بلا رمي — ولا حارس رصيدٍ سالبٍ يمنع الترحيل في هذه الوحدة.
 * فـ«نقد» يعمل بلا تعثّرٍ من اليوم الأول.
 */

export type CodingPaymentMethod = "cash" | "on_account";

/** أغلب ما في رزمة الورق نقديّ — وهو سبب هذا العمود أصلاً. */
export const DEFAULT_CODING_PAYMENT_METHOD: CodingPaymentMethod = "cash";

export const CODING_PAYMENT_METHODS: { value: CodingPaymentMethod; label: string }[] = [
  { value: "cash", label: "نقد" },
  { value: "on_account", label: "على الحساب" },
];

/** قلبٌ بين الحالتين — تبديل العمود بلوحة المفاتيح لا يحتاج أكثر من هذا. */
export function togglePaymentMethod(current: CodingPaymentMethod): CodingPaymentMethod {
  return current === "cash" ? "on_account" : "cash";
}

/**
 * حقلا الدفع في حمولة الحفظ الدفعي (#84): «نقد» يُرفق بصندوقٍ صريحٍ إن عُرف
 * افتراضياً — و«على الحساب» لا يحمل حقلاً إضافياً كما كان دوماً. صندوقٌ غير
 * معروف على صفّ نقديّ لا يُسقِط الحقل مزوَّراً؛ يُترك للخادم (`resolve_cash_account`)
 * ليحلّه بسلّمه نفسه — تماماً كما تفعل شاشة سند المصروف اليوم.
 */
export function paymentFieldsForRow(
  method: CodingPaymentMethod,
  defaultCashAccountId: number | null,
): { payment_method: CodingPaymentMethod; cash_or_bank_account?: number } {
  if (method === "cash" && defaultCashAccountId != null) {
    return { payment_method: "cash", cash_or_bank_account: defaultCashAccountId };
  }
  return { payment_method: method };
}
