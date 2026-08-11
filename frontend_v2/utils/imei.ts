/**
 * THA-45 M2 — قاعدة IMEI للعرض الفوري داخل نموذج استقبال الجهاز.
 *
 * القاعدة نفسها الموجودة في `device_registry/models.py::imei_is_valid`: خمس عشرة
 * خانة رقمية تجتاز Luhn على الخانات **كاملةً** (mod 10 = 0) — لا أربع عشرة وخانة
 * تحقق منفصلة. الخادم يبقى المرجع عند الحفظ (يرفض بـ400)، وهذه نسخة العرض
 * الفوري لا بديلٌ عنها: الموظف عند الكاونتر يجب أن يرى الخطأ قبل الضغط على
 * «تسجيل» لا بعده.
 *
 * وحدة نقية بلا `window` ولا شبكة — تُستورَد في اختبارات Node بلا متصفّح.
 */

export const IMEI_LENGTH = 15;

/**
 * أرقام فقط، مقصوصة عند خمس عشرة خانة. الماسح الضوئي والنسخ من الملصق يأتيان
 * بمسافات وشرطات، وإدخالٌ أطول من العدّاد كان يمرّ ثم يُرفض من الخادم.
 */
export const imeiDigits = (value: string | null | undefined): string =>
  String(value ?? "").replace(/\D/g, "").slice(0, IMEI_LENGTH);

/** Luhn على كامل السلسلة الرقمية: مضاعفة الخانات الفردية من اليمين. */
export function luhnIsValid(digits: string): boolean {
  if (!/^\d+$/.test(digits)) return false;
  let total = 0;
  for (let index = 0; index < digits.length; index++) {
    let digit = Number(digits[digits.length - 1 - index]);
    if (index % 2) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  }
  return total % 10 === 0;
}

/** IMEI سليم بنيةً وخانةَ تحقق. أي شكل آخر (حروف، طول مختلف، فارغ) = false. */
export function isValidImei(value: string | null | undefined): boolean {
  const raw = String(value ?? "").trim();
  if (!/^\d{15}$/.test(raw)) return false;
  return luhnIsValid(raw);
}

/**
 * حالة الحقل كما تُعرض للمستخدم:
 * - `empty` لا شيء بعد — لا رسالة ولا لون.
 * - `partial` يكتب الآن — العدّاد وحده، بلا خطأ أحمر على نصف رقم.
 * - `invalid` اكتملت الخمس عشرة خانة وسقطت في Luhn — خطأ فوري.
 * - `valid` جاهز — علامة خضراء، وعندها فقط يُسأل الخادم عن التكرار.
 */
export type ImeiState = "empty" | "partial" | "invalid" | "valid";

export function imeiState(value: string | null | undefined): ImeiState {
  const digits = imeiDigits(value);
  if (digits.length === 0) return "empty";
  if (digits.length < IMEI_LENGTH) return "partial";
  return luhnIsValid(digits) ? "valid" : "invalid";
}

/**
 * صيغة الهاتف كما يقبلها الخادم بعد تطبيعه
 * (`device_registry/models.py::validate_phone`): من 7 إلى 15 رقماً مع مقدمة
 * دولية اختيارية. التطبيع هنا هو تطبيع الخادم نفسه — فراغات وشرطات تسقط — كي لا
 * يرى المستخدم «رقم غير صالح» على رقمٍ سيقبله الخادم فعلاً.
 */
export const normalizePhone = (value: string | null | undefined): string =>
  String(value ?? "").trim().replace(/[\s-]/g, "");

export function isValidPhone(value: string | null | undefined): boolean {
  return /^\+?\d{7,15}$/.test(normalizePhone(value));
}
