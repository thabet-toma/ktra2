/**
 * عدّادُ انتهاء الحملة — منطقٌ خالصٌ بلا React كي يُختبَر وحده.
 *
 * قرارا مواصفةٍ صريحان: لا `starts_at` يُعرَض أبداً («بدأ قبل شهر» يقول
 * للزبون إن هذا معروضٌ قديم)، والعدّادُ يختفي حين تتجاوز المدّةُ حدّاً
 * معقولاً («يبقى ٢٧٠ يوماً» يُبطل معنى الإلحاح). `COUNTDOWN_MAX_DAYS`
 * أسبوعان — حكمٌ تصميميٌّ (لا رقم مواصفةٍ حرفيّ)، هو الحدُّ الشائع الذي
 * يبقى فيه «عرضٌ محدودُ المدّة» معقولاً قبل أن يفقد معناه.
 */

export const COUNTDOWN_MAX_DAYS = 14;

export interface CampaignCountdownParts {
  days: number;
  hours: number;
  minutes: number;
}

/**
 * `null` في ثلاث حالات: لا `ends_at`، أو انتهت الحملة فعلاً، أو تجاوزت
 * `COUNTDOWN_MAX_DAYS` — الواجهة لا تعرض عدّاداً في أيٍّ منها.
 */
export function campaignCountdown(
  endsAt: string | null | undefined,
  now: number = Date.now(),
): CampaignCountdownParts | null {
  if (!endsAt) return null;
  const end = new Date(endsAt).getTime();
  if (!Number.isFinite(end)) return null;

  const remainingMs = end - now;
  if (remainingMs <= 0) return null;

  const totalMinutes = Math.floor(remainingMs / 60_000);
  const days = Math.floor(totalMinutes / (60 * 24));
  if (days > COUNTDOWN_MAX_DAYS) return null;

  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  return { days, hours, minutes };
}
