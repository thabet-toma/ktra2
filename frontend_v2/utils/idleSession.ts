/**
 * DEF-009 — حالة الخمول مشتركة بين كل تبويبات المتصفح (نفس الأصل).
 *
 * السبب: IdleTimeoutGuard كان يحتفظ لكل تبويب بمؤقّته الخاص. تبويب متروك مفتوحاً
 * بلا نشاط يُنهي الجلسة (logoutUser يحذف التوكن من الخادم ومن localStorage
 * المشترك) بينما المستخدم يعمل في تبويب آخر — فيفقد ذاك التبويب التوكن دون أن
 * يظهر له مودال «تم إنهاء الجلسة»، ويصطدم برسالة «لم يتم تزويد بيانات الدخول».
 * الخمول يجب أن يُقاس على المستخدم لا على التبويب.
 */

/** مفتاح آخر نشاط — يُقرأ ويُكتب من كل التبويبات. */
export const ACTIVITY_KEY = "lastActivityAt";

/** أقل ما نحتاجه من localStorage — يسهّل الاختبار ويحتمل غيابه. */
export interface ActivityStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** يسجّل لحظة النشاط الأخيرة. فشل التخزين (وضع الخصوصية) لا يعطّل الحارس. */
export function writeLastActivity(store: ActivityStore, now: number): void {
  try {
    store.setItem(ACTIVITY_KEY, String(now));
  } catch {
    /* التخزين غير متاح — يبقى المؤقّت المحلي وحده */
  }
}

/** آخر نشاط مسجَّل، أو null إذا غاب أو كان تالفاً. */
export function readLastActivity(store: ActivityStore): number | null {
  try {
    const raw = store.getItem(ACTIVITY_KEY);
    if (!raw) return null;
    const ts = Number(raw);
    return Number.isFinite(ts) ? ts : null;
  } catch {
    return null;
  }
}

/**
 * ما تبقّى من مهلة الخمول، محسوباً على آخر نشاط في **أي** تبويب.
 * غياب السجل أو تلفه أو طابع زمني مستقبلي ⇒ المهلة كاملة (لا ننهي جلسة بالشك).
 */
export function idleRemainingMs(
  store: ActivityStore,
  now: number,
  timeoutMs: number,
): number {
  const last = readLastActivity(store);
  if (last === null || last > now) return timeoutMs;
  return Math.max(0, timeoutMs - (now - last));
}

/**
 * هل يُحتسب هذا الطلب نشاطاً للمستخدم؟
 *
 * طلبات الكتابة (POST/PUT/PATCH/DELETE) لا تخرج إلا بأمر المستخدم ⇒ نشاط.
 * أما GET/HEAD فتُخرجها مؤقتات خلفية بلا مستخدم (heartbeat الاتصال كل 30ث،
 * polling الصفقات/الشحنات، المهام النشطة) — لو عُدّت نشاطاً لما انتهت مهلة
 * الخمول أبداً على أي تبويب مفتوح، أي لأُلغيت الميزة عملياً.
 */
export function isUserActivityRequest(method: string | undefined): boolean {
  const m = (method || "GET").toUpperCase();
  return m !== "GET" && m !== "HEAD" && m !== "OPTIONS";
}
