/**
 * حدث موحّد «انتهت الجلسة» — يُطلقه طبقة الـ API عند ردّ 401 ويلتقطه
 * IdleTimeoutGuard ليعرض شاشة «تم إنهاء الجلسة» بدل بانر خطأ خام.
 */
export const SESSION_EXPIRED_EVENT = "ktra:session-expired";

/**
 * نشاط مستخدم حقيقي وقع خارج أحداث الـ DOM (طلب كتابة مثلاً). حدث `storage`
 * لا يصل للتبويب الذي كتب القيمة، فنحتاج إشعاراً داخلياً ليعيد الحارس التسليح.
 */
export const USER_ACTIVITY_EVENT = "ktra:user-activity";
export const ENGAGEMENT_REVOKED_EVENT = "ktra:engagement-revoked";

/** يُعلن نشاطاً للحارس داخل هذا التبويب. */
export function emitUserActivity(): void {
  try {
    window.dispatchEvent(new Event(USER_ACTIVITY_EVENT));
  } catch {
    /* بيئة بلا window (اختبارات) — تجاهل */
  }
}

/** يُعلن انتهاء الجلسة لكل من يهمّه الأمر (بلا اعتماد على React). */
export function emitSessionExpired(): void {
  try {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  } catch {
    /* بيئة بلا window (اختبارات) — تجاهل */
  }
}

/** إلغاء ارتباط شركة لا ينهي جلسة المحاسب ولا يمس توكنه العام. */
export function emitEngagementRevoked(): void {
  try {
    window.dispatchEvent(new Event(ENGAGEMENT_REVOKED_EVENT));
  } catch {
    /* بيئة بلا window (اختبارات) — تجاهل */
  }
}
