/**
 * ISSUE #54 — حالة طلب تسليم الدفتر الفعلية (نمط Xero).
 *
 * الخادم لا يُثبِّت `expired` إلا عند محاولة قبولٍ فعلية (`tenants.services`
 * `accept_handover_request`) — طلبٌ فات وقته وبقي بلا أحد يقبله يظل `pending`
 * في الصفّ. الواجهة تحتاج الحقيقة فوراً (تعطيل زرّ القبول، شارة «منتهي») بلا
 * انتظار تلك المحاولة، فتشتقّها هنا من `expires_at` مباشرة — مرآة الفحص
 * الخادمي `request.status == 'pending' and request.expires_at <= now`.
 */

export type HandoverRequestStatus = 'pending' | 'accepted' | 'expired' | 'cancelled';

export function effectiveHandoverStatus(
  status: HandoverRequestStatus,
  expiresAtIso: string,
  nowIso?: string,
): HandoverRequestStatus {
  if (status !== 'pending') return status;
  const now = nowIso != null ? new Date(nowIso).getTime() : Date.now();
  const expiresAt = new Date(expiresAtIso).getTime();
  return expiresAt <= now ? 'expired' : 'pending';
}
