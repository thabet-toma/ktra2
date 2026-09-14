import { formatNumber } from './formatNumber.ts';

/**
 * ستاتستكس الرقم الواحد — قراءتُها بالكلمات (212-R4).
 *
 * الأرقامُ تأتي مجمَّعةً من الخادم (`crm/services.py::lead_contact_stats`) لأنّ
 * سجلَّ التواصل مُصفَّحٌ بخمسين صفّاً، فعدٌّ يُحسَب من الصفحة المحمَّلة يكذب على
 * رقمٍ طويل. وما هنا هو **الحكمُ على تلك الأرقام وحدَه**: متى يُقال «راكد»،
 * وكيف يُنطَق «منذ كم» بعربيّةٍ سليمة.
 */

export type CrmFollowUpState = 'overdue' | 'due_today' | 'upcoming' | 'none';
export type LeadAttentionLevel = 'ok' | 'watch' | 'stalled';

/** الحقولُ التي يقرؤها الحكمُ — لا كلُّ الحمولة، كي يبقى الاختبارُ مقروءاً. */
export interface LeadAttentionInput {
  contact_attempts: number;
  days_since_last_contact: number | null;
  days_in_status: number;
  age_days: number;
  follow_up_state: CrmFollowUpState;
}

/**
 * عتبتا الركود — **رقمان معرَّفان مرّةً واحدة** لا رقمٌ مكرَّرٌ في كلّ شرط.
 *
 * أسبوعٌ بلا كلامٍ يستحقّ نظرة، وأسبوعان يستحقّان تدخّلاً. والمرجعُ سلوكُ
 * Pipedrive في «تعفين» الصفقة الساكنة، إلّا أنّ العدَّ هنا **من آخر تواصلٍ فعليّ**
 * لا من آخر أيّ حركةٍ على الصفّ.
 */
export const STALL_WATCH_DAYS = 7;
export const STALL_ALERT_DAYS = 14;

/**
 * صيغةُ عددِ الأيّام بعد «منذ» — مفردٌ ومثنّى وجمعُ قلّةٍ وتمييزٌ منصوب.
 *
 * «منذ 2 أيام» و«منذ 3 يوماً» عربيّةُ مترجِمٍ آليّ؛ والشاشةُ يقرؤها موظّفٌ كلَّ يوم.
 */
export function arabicDayCount(days: number): string {
  const whole = Math.max(0, Math.trunc(days));
  if (whole === 0) return 'أقلَّ من يوم';
  if (whole === 1) return 'يوم واحد';
  if (whole === 2) return 'يومين';
  if (whole <= 10) return `${formatNumber(whole)} أيّام`;
  return `${formatNumber(whole)} يوماً`;
}

/** «آخرُ تواصل» بالكلمات — و`null` تعني أنّه لم يُكلَّم قطّ، لا أنّه كُلِّم اليوم. */
export function contactRecencyLabel(daysSinceLastContact: number | null): string {
  if (daysSinceLastContact === null) return 'لم يُسجَّل تواصلٌ بعد';
  if (daysSinceLastContact === 0) return 'اليوم';
  if (daysSinceLastContact === 1) return 'أمس';
  return `منذ ${arabicDayCount(daysSinceLastContact)}`;
}

/**
 * حكمُ الانتباه على الرقم.
 *
 * **الصمتُ هو ما يدقّ الجرس، لا طولُ المرحلة.** رقمٌ كُلِّم أمسِ وهو في «مهتمّ»
 * منذ شهرٍ يستحقّ نظرةً لا إنذاراً: صاحبُه يعمل عليه. ورقمٌ لم يُكلَّم منذ أسبوعين
 * مهجورٌ مهما بدت حالتُه. ومتابعةٌ فات موعدُها إنذارٌ بذاتها — الموظّفُ وعد بتاريخٍ
 * ومضى.
 *
 * ورقمٌ **لم يُكلَّم قطّ** ليس هادئاً: مدّةُ صمتِه عمرُه كلُّه.
 */
export function leadAttentionLevel(stats: LeadAttentionInput): LeadAttentionLevel {
  if (stats.follow_up_state === 'overdue') return 'stalled';
  const silence = stats.days_since_last_contact === null ? stats.age_days : stats.days_since_last_contact;
  if (silence >= STALL_ALERT_DAYS) return 'stalled';
  if (silence >= STALL_WATCH_DAYS || stats.days_in_status >= STALL_ALERT_DAYS) return 'watch';
  return 'ok';
}

export interface LeadAttentionBadge {
  level: LeadAttentionLevel;
  label: string;
  className: string;
}

/** الشارةُ كاملةً — النصُّ والطبقةُ من مصدرٍ واحدٍ كي لا يفترقا. */
export function leadAttentionBadge(stats: LeadAttentionInput): LeadAttentionBadge {
  const level = leadAttentionLevel(stats);
  if (level === 'stalled') {
    return {
      level,
      label: stats.follow_up_state === 'overdue' ? 'متابعةٌ فات موعدُها' : 'راكدٌ بلا تواصل',
      className: 'border-rose-400/40 bg-rose-400/15 text-rose-200',
    };
  }
  if (level === 'watch') {
    return { level, label: 'يحتاج متابعة', className: 'border-amber-400/40 bg-amber-400/15 text-amber-200' };
  }
  return { level, label: 'المتابعة منتظمة', className: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200' };
}
