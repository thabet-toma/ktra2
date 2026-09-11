/**
 * دوالٌّ خالصةٌ لاستهلاك باقة المنصة (#207 م٨).
 *
 * بلا شبكةٍ ولا متصفّح — تُختبَر بـ`node --test`، وهي بوّابةُ الواجهة الوحيدة هنا.
 */
import { formatNumber } from './formatNumber.ts';

/** من هذه النسبة فما فوق يُقال للزبون إنّه يقترب من حدّ باقته. */
export const QUOTA_NEAR_LIMIT_PERCENT = 80;

export type QuotaTone = 'unmetered' | 'comfortable' | 'near_limit' | 'over_limit';

/**
 * موقعُ الشركة من حدّ باقتها. `usage_percent` يصل `null` حين لا عملياتَ مشمولة
 * أصلاً (كلُّ عمليّةٍ زائدة) — فلا نسبةَ تُحسب ولا «ضمن الباقة» يُقال كذباً.
 */
export function quotaTone(usagePercent: number | null | undefined): QuotaTone {
  if (usagePercent === null || usagePercent === undefined || !Number.isFinite(usagePercent)) {
    return 'unmetered';
  }
  if (usagePercent > 100) return 'over_limit';
  if (usagePercent >= QUOTA_NEAR_LIMIT_PERCENT) return 'near_limit';
  return 'comfortable';
}

export interface QuotaToneMeta {
  label: string;
  /**
   * لونُ امتلاء عنصر `<progress>` — أصنافُ العنصر الزائف لا `bg-*` على `div` بعرضٍ
   * محسوب: العرضُ المحسوبُ يلزمه `style` مضمَّن، و`CLAUDE.md` يمنعه.
   */
  barClass: string;
  textClass: string;
}

export function quotaToneMeta(tone: QuotaTone): QuotaToneMeta {
  switch (tone) {
    case 'over_limit':
      return {
        label: 'تجاوزتَ الباقة',
        barClass: '[&::-webkit-progress-value]:bg-rose-500 [&::-moz-progress-bar]:bg-rose-500',
        textClass: 'text-rose-700 dark:text-rose-300',
      };
    case 'near_limit':
      return {
        label: 'تقترب من الحد',
        barClass: '[&::-webkit-progress-value]:bg-amber-500 [&::-moz-progress-bar]:bg-amber-500',
        textClass: 'text-amber-700 dark:text-amber-300',
      };
    case 'comfortable':
      return {
        label: 'ضمن الباقة',
        barClass: '[&::-webkit-progress-value]:bg-emerald-500 [&::-moz-progress-bar]:bg-emerald-500',
        textClass: 'text-emerald-700 dark:text-emerald-300',
      };
    default:
      return {
        label: 'بلا عمليات مشمولة',
        barClass: '[&::-webkit-progress-value]:bg-slate-400 [&::-moz-progress-bar]:bg-slate-400',
        textClass: 'text-slate-600 dark:text-slate-400',
      };
  }
}

/** عرضُ شريط الاستهلاك مقصوصاً إلى ٠–١٠٠ — التجاوزُ يُقال بلونٍ ونصٍّ لا بشريطٍ يخرج من إطاره. */
export function quotaBarPercent(usagePercent: number | null | undefined): number {
  if (usagePercent === null || usagePercent === undefined || !Number.isFinite(usagePercent)) return 0;
  return Math.min(100, Math.max(0, usagePercent));
}

/** «٣٠ من ١٠٠ عملية» بأرقام المنصّة. */
export function quotaHeadline(consumed: number, included: number): string {
  return `${formatNumber(consumed)} من ${formatNumber(included)} عملية`;
}

/** جملةُ التجاوز وكلفتِه، أو `null` إن لم يُتجاوَز الحدّ. المبلغُ نصٌّ عشريٌّ من الخادم. */
export function quotaOverageNotice(overageUnits: number, overageFee: string | number): string | null {
  if (!(overageUnits > 0)) return null;
  return `تجاوزتَ الباقة بـ${formatNumber(overageUnits)} عملية تُضاف إلى فاتورة هذه الدورة بقيمة ${formatNumber(overageFee)}.`;
}
