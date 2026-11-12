/**
 * ISSUE #87 — بوابة ترخيص `accountant_portal`.
 *
 * #291: شاشتا البداية القديمتان (`office-dashboard` لقالب `accounting_firm`،
 * و`financial-position` لقالب `client_book`) حُذفتا مع طبقة المكتب القديمة —
 * فلم يبقَ في هذا الملفّ قرارُ «أيّ شاشة تُرسَم»، بل بوابةُ ترخيصٍ فقط.
 *
 * تفشل البوابة إغلاقاً بصريح لا صمتاً: `false` أو غياب المفتاح = غير مرخَّصة
 * (نفس منطق `moduleAllowsView` في `utils/viewPermissions.ts`) — لا افتراض نجاح.
 */
export type ModuleGateStatus = "loading" | "unlicensed" | "ready";

export function resolveModuleGate(
  loading: boolean,
  moduleEnabled: boolean | undefined,
): ModuleGateStatus {
  if (loading) return "loading";
  if (moduleEnabled !== true) return "unlicensed";
  return "ready";
}
