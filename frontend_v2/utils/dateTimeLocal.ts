/**
 * تحويلُ القيم بين `<input type="datetime-local">` وطوابع ISO التي يرسلها الخادم.
 *
 * **ليست دوالَّ عرض** — العرضُ يمرّ بـ`utils/formatDate.ts` وحدَه. هذه قيمُ حقول
 * إدخالٍ بصيغة `YYYY-MM-DDTHH:mm` بتوقيت الجهاز، والحقلُ لا يقبل غيرَها.
 */

const pad = (value: number): string => String(value).padStart(2, '0');

/** طابعُ ISO من الخادم ← قيمةُ الحقل بتوقيت الجهاز. فارغٌ أو تالفٌ ← `''`. */
export function isoToDateTimeLocal(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * قيمةُ الحقل ← طابعُ ISO بتوقيت UTC للإرسال. فارغٌ أو تالفٌ ← `null`.
 * الصيغةُ بلا إزاحةٍ تُقرأ بتوقيت الجهاز في مواصفة JavaScript، وهو ما رآه المستخدم.
 */
export function dateTimeLocalToIso(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}
