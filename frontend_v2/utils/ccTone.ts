/**
 * CcTone: نظامُ تدرّجاتِ ونغماتِ مركز القيادة (Command Center).
 * دوالٌّ خالصةٌ خاليةٌ من أيّ نداءات أو استيرادات من React.
 */

export type CcTone = "neutral" | "accent" | "success" | "warning" | "danger" | "violet";

/** نغماتُ سطحِ البطاقة — النغمةُ تُلوّن الحدَّ وحدَه فوق سطحٍ واحد، كي تبقى
 *  البطاقاتُ صفّاً واحداً بصريّاً وتقرأ الحالةَ من حافّتها لا من أرضيّتها. */
export type CcSurfaceTone = CcTone | "default" | "raised";

const SURFACE_CLASSES: Record<CcSurfaceTone, string> = {
  default: "bg-cc-surface border-cc-border text-cc-text",
  raised: "bg-cc-surface-2 border-cc-border-strong text-cc-text",
  neutral: "bg-cc-surface border-cc-border text-cc-text",
  accent: "bg-cc-surface border-sky-500/30 text-cc-text",
  success: "bg-cc-surface border-emerald-500/30 text-cc-text",
  warning: "bg-cc-surface border-amber-500/30 text-cc-text",
  danger: "bg-cc-surface border-rose-500/30 text-cc-text",
  violet: "bg-cc-surface border-purple-500/30 text-cc-text",
};

/** **المصدرُ الوحيد** لأصنافِ سطحِ البطاقة — `CcCard` يستدعيها ولا ينسخها.
 *  (كانت نسخةٌ ثانيةٌ داخل `CcCard` بقيمٍ مخالفة، فكان المختبَرُ غيرَ المعروض.) */
export function ccSurfaceClasses(tone: CcSurfaceTone): string {
  return SURFACE_CLASSES[tone] || SURFACE_CLASSES.default;
}

const PILL_CLASSES: Record<CcTone, string> = {
  neutral: "bg-cc-surface-2 text-cc-text-muted border border-cc-border",
  accent: "bg-sky-500/15 text-sky-400 border border-sky-500/30",
  success: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  warning: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  danger: "bg-rose-500/15 text-rose-400 border border-rose-500/30",
  violet: "bg-purple-500/15 text-purple-400 border border-purple-500/30",
};

export function ccPillClasses(tone: CcTone): string {
  return PILL_CLASSES[tone] || PILL_CLASSES.neutral;
}

/**
 * تقييمُ الدرجةِ المركّبةِ 0..100:
 * null/undefined => "neutral"
 * >= 85 => "success"
 * >= 70 => "accent"
 * >= 50 => "warning"
 * دون ذلك (< 50) => "danger"
 * القيم خارج 0..100 تُقصّ إلى المدى قبل التصنيف.
 */
export function ccScoreTone(score: number | null | undefined): CcTone {
  if (score === null || score === undefined || typeof score !== "number" || !Number.isFinite(score)) {
    return "neutral";
  }
  const clamped = Math.min(100, Math.max(0, score));
  if (clamped >= 85) return "success";
  if (clamped >= 70) return "accent";
  if (clamped >= 50) return "warning";
  return "danger";
}

/**
 * تحديدُ حالةِ الحضور:
 * الاجتماع يغلب الاتصال عند اجتماعهما.
 */
export function ccPresenceTone(
  isActiveNow?: boolean,
  isInMeeting?: boolean
): "online" | "meeting" | "offline" {
  if (isInMeeting) return "meeting";
  if (isActiveNow) return "online";
  return "offline";
}
