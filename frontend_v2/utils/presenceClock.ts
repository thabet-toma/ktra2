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
 * ثوانٍ إلى ساعاتٍ عشريّةٍ بمنزلتين — لمقارنةِ العتبة لا للعرض.
 *
 * منفصلةٌ عن `formatPresenceClock` عن قصد: `02:30` نصُّ عرضٍ لا يُقارَن بعتبةٍ،
 * ومقارنةُ نصوصٍ هنا كانت ستجعل `10:00` أصغرَ من `2:00`.
 */
export const presenceHours = (seconds: number): number => {
  if (!Number.isFinite(seconds) || seconds <= 0) return 0;
  return Math.round((seconds / 3600) * 100) / 100;
};
