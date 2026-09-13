import { formatNumber } from './formatNumber.ts';

/**
 * ثوانيَ الحضورِ إلى `ساعات:دقائق` (#212 212-D).
 *
 * **دالّةٌ واحدةٌ لثلاثة مواضع**: شريطُ الموظّف العلويّ، وبطاقتُه في طاولة
 * المدير، وسجلُّه اليوميّ. ونسخةٌ ثانيةٌ من هذا التحويل تعني أن يعرض موضعٌ
 * `2:05` وآخرُ `2:5` للرقم نفسِه.
 *
 * والأرقامُ تمرّ بـ`formatNumber` كقاعدة المستودع — لا `toLocaleString` فهي
 * بالعربية تُخرج أرقاماً هندية في سياقٍ يُقرأ ساعةً.
 */
export const formatPresenceClock = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '00:00';
  const totalMinutes = Math.floor(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const part = (value: number) => formatNumber(value, { maxDecimals: 0 }).padStart(2, '0');
  return `${part(hours)}:${part(minutes)}`;
};

/**
 * نصُّ الرقاقة — **وغيابُ الحقل ليس صفراً** (212-N2).
 *
 * صفرُ ثوانٍ خبرٌ («لم يحضر اليوم»)، وغيابُ الحقل حمولةٌ لا تحمل العدّاد. ولو
 * وُحِّدا لقالت البطاقةُ «لم يحضر» عن موظّفٍ لا تعرف عنه شيئاً.
 */
export const presenceClockLabel = (seconds: number | undefined): string =>
  seconds === undefined ? '--:--' : formatPresenceClock(seconds);

/** نبرةُ الرقاقة — أربعُ حالاتٍ لا لونان. */
export type PresenceTone = 'unknown' | 'met' | 'partial' | 'absent';

/**
 * قياسُ اليومِ على عتبته (212-N2).
 *
 * كانت هذه السلسلةُ الثلاثيّةُ مكتوبةً داخل `EmployeeCard.tsx`، ولمّا لزمت
 * الطاولةَ أيضاً كانت ستصير نسختين تفترقان عند أوّل تعديلٍ للعتبة. فصارت
 * دالّةً خالصةً يختبرها `npm test` — و`tsc` لا يفحص منطقاً ولا يصيّر مكوّناً.
 *
 * وعتبةُ صفرٍ تعني «الأثرُ مُطفأ» في السياسة، فيقرأ `0 >= 0` اكتفاءً: لا عتبةَ
 * تُخالَف فلا لومَ يُعرَض. وهذا سلوكُ البطاقة قبل الاستخراج نفسُه، مُثبَّتاً
 * باختبارٍ كي يصير أيُّ تغييرٍ له قراراً لا انزلاقاً.
 */
export const presenceToneOf = (
  seconds: number | undefined,
  targetHours: number,
): PresenceTone => {
  if (seconds === undefined || !Number.isFinite(seconds)) return 'unknown';
  if (seconds >= targetHours * 3600) return 'met';
  if (seconds > 0) return 'partial';
  return 'absent';
};

/**
 * ثوانٍ إلى ساعاتٍ عشريّةٍ بمنزلتين — لمقارنةِ العتبة لا للعرض.
 *
 * منفصلةٌ عن `formatPresenceClock` عن قصد: `02:30` نصُّ عرضٍ لا يُقارَن بعتبةٍ،
 * ومقارنةُ نصوصٍ هنا كانت ستجعل `10:00` أصغرَ من `2:00`.
 */
export const presenceHours = (seconds: number): number => {
  if (!Number.isFinite(seconds) || seconds <= 0) return 0;
  return Math.round((seconds / 3600) * 100) / 100;
};
