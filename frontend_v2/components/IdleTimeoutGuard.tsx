/**
 * DEF-009 — حارس مهلة الخمول.
 * بعد {@link IDLE_TIMEOUT_MS} من غياب أي نشاط (نقر/مفتاح/تمرير/لمس/تنقّل) يُبطل
 * الجلسة (يمسح التوكن) ويعرض مودال «تم إنهاء الجلسة» يعيد المستخدم إلى تسجيل
 * الدخول. أي نشاط قبل انتهاء المهلة يُعيد ضبط المؤقّت.
 *
 * قبل الانتهاء بـ {@link IDLE_WARNING_MS} يظهر تنبيه بعدّاد تنازلي يتيح للمستخدم
 * الضغط «متابعة الجلسة» لتمديدها دون فقد عمله (مهم لعمليات الجرد الطويلة).
 *
 * الخمول يُقاس على المستخدم لا على التبويب: النشاط يُسجَّل في localStorage
 * (utils/idleSession) فيقرأه كل تبويب، وإلا أنهى تبويبٌ متروك الجلسةَ على تبويب
 * يعمل فيه المستخدم فعلاً فتظهر «لم يتم تزويد بيانات الدخول» بلا تفسير.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { IDLE_WARNING_MS } from "../constants/session";
import { useSessionSettings } from "../contexts/SessionSettingsContext";
import { logoutUser } from "../services/authService";
import { ACTIVITY_KEY, idleRemainingMs, writeLastActivity } from "../utils/idleSession";
import { SESSION_EXPIRED_EVENT, USER_ACTIVITY_EVENT } from "../utils/sessionEvents";

interface Props {
  /** يُستدعى عند ضغط زر العودة — يُفترض أن يُفرّغ المستخدم الحالي (سياق المصادقة). */
  onLogout: () => void;
}

export const IdleTimeoutGuard: React.FC<Props> = ({ onLogout }) => {
  // مهلة الخمول قابلة للتهيئة per-company (SessionSettings). تُقرأ عبر ref كي تبقى
  // دوال المؤقّتات مستقرة، وتُعاد التسليح فوراً عند تغييرها من الإعدادات.
  const { idleTimeoutMs } = useSessionSettings();
  const idleTimeoutMsRef = useRef(idleTimeoutMs);
  const [expired, setExpired] = useState(false);
  // ثوانٍ متبقية حتى الانتهاء أثناء التنبيه؛ null = لا تنبيه معروض.
  const [warnSeconds, setWarnSeconds] = useState<number | null>(null);
  const warnTimerRef = useRef<number | null>(null);
  const expireTimerRef = useRef<number | null>(null);
  const countdownRef = useRef<number | null>(null);
  const expiredRef = useRef(false);

  const clearTimers = () => {
    if (warnTimerRef.current != null) window.clearTimeout(warnTimerRef.current);
    if (expireTimerRef.current != null) window.clearTimeout(expireTimerRef.current);
    if (countdownRef.current != null) window.clearInterval(countdownRef.current);
    warnTimerRef.current = expireTimerRef.current = countdownRef.current = null;
  };

  const handleExpire = useCallback(() => {
    if (expiredRef.current) return;
    expiredRef.current = true;
    clearTimers();
    // إبطال الجلسة فوراً (مسح التوكن) — أي نداء API بعدها غير مُصرَّح به.
    void logoutUser();
    setExpired(true);
  }, []);

  /**
   * إظهار شاشة «تم إنهاء الجلسة» دون إعادة تسجيل خروج — تُستخدم حين انتهت الجلسة
   * خارج هذا التبويب (تبويب آخر أنهاها، أو ردّ 401 من الخادم).
   */
  const showExpiredOnly = useCallback(() => {
    if (expiredRef.current) return;
    expiredRef.current = true;
    clearTimers();
    setExpired(true);
  }, []);

  // بدء التنبيه بعدّاد تنازلي يُحدَّث كل ثانية حتى الانتهاء.
  // `leftMs` = ما تبقّى فعلياً (قد يقلّ عن IDLE_WARNING_MS عند فتح تبويب متأخر).
  const startWarning = useCallback((leftMs: number = IDLE_WARNING_MS) => {
    if (expiredRef.current) return;
    const deadline = Date.now() + leftMs;
    setWarnSeconds(Math.ceil(leftMs / 1000));
    if (countdownRef.current != null) window.clearInterval(countdownRef.current);
    countdownRef.current = window.setInterval(() => {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setWarnSeconds(left);
    }, 1000);
  }, []);

  /**
   * يعيد تسليح المؤقّتات على ما تبقّى من المهلة بحسب آخر نشاط في **أي** تبويب،
   * لا على مهلة كاملة محلية.
   */
  const rearm = useCallback(() => {
    if (expiredRef.current) return;
    clearTimers();
    setWarnSeconds(null);
    const remaining = idleRemainingMs(localStorage, Date.now(), idleTimeoutMsRef.current);
    if (remaining <= 0) {
      handleExpire();
      return;
    }
    if (remaining > IDLE_WARNING_MS) {
      warnTimerRef.current = window.setTimeout(startWarning, remaining - IDLE_WARNING_MS);
    } else {
      startWarning(remaining);
    }
    expireTimerRef.current = window.setTimeout(handleExpire, remaining);
  }, [handleExpire, startWarning]);

  // تغيير المهلة من الإعدادات يسري فوراً: حدّث الـref ثم أعِد تسليح المؤقّتات.
  useEffect(() => {
    idleTimeoutMsRef.current = idleTimeoutMs;
    rearm();
  }, [idleTimeoutMs, rearm]);

  /** نشاط فعلي من المستخدم في هذا التبويب: يُسجَّل للجميع ثم يُعاد التسليح. */
  const reset = useCallback(() => {
    if (expiredRef.current) return;
    writeLastActivity(localStorage, Date.now());
    rearm();
  }, [rearm]);

  useEffect(() => {
    // throttle: لا نعيد ضبط المؤقّت أكثر من مرة كل ثانية لتفادي ضغط الأحداث.
    let last = 0;
    const onActivity = () => {
      const now = Date.now();
      if (now - last < 1000) return;
      last = now;
      reset();
    };
    // أوسع ما يدل على وجود المستخدم: حتى تحريك الفأرة أو الكتابة في حقل دون
    // ضغط زر. الخانق (1ث) يمنع أي كلفة من mousemove/input المتكررين.
    const events: (keyof WindowEventMap)[] = [
      "mousedown", "mousemove", "keydown", "input", "change",
      "scroll", "wheel", "touchstart", "touchmove", "pointerdown", "focus",
    ];
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true, capture: true }));

    // مزامنة بين التبويبات: نشاط في تبويب آخر يمدّد المهلة هنا (ويخفي التنبيه)،
    // وحذف التوكن من تبويب آخر يعرض شاشة «تم إنهاء الجلسة» بدل ترك هذا التبويب
    // يعمل بلا توكن فيصطدم برسالة «لم يتم تزويد بيانات الدخول».
    const onStorage = (e: StorageEvent) => {
      if (e.key === ACTIVITY_KEY) {
        rearm();
        return;
      }
      if (e.key === "token" && e.newValue === null) showExpiredOnly();
    };
    window.addEventListener("storage", onStorage);
    // نشاط سجّلته طبقة الـ API (طلب كتابة) — `storage` لا يصل لنفس التبويب.
    window.addEventListener(USER_ACTIVITY_EVENT, rearm);
    // 401 من الخادم (توكن محذوف/غير صالح) — نفس الشاشة بدل بانر خطأ غامض.
    window.addEventListener(SESSION_EXPIRED_EVENT, showExpiredOnly);

    // لا نُصفّر عدّاد النشاط عند كل تحميل صفحة: تحديث الصفحة ليس نشاطاً بمعنى
    // «المستخدم موجود»، والقراءة المشتركة تكفي لتحديد ما تبقّى.
    if (localStorage.getItem(ACTIVITY_KEY) == null) writeLastActivity(localStorage, Date.now());
    rearm();
    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity, { capture: true } as any));
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(USER_ACTIVITY_EVENT, rearm);
      window.removeEventListener(SESSION_EXPIRED_EVENT, showExpiredOnly);
      clearTimers();
    };
  }, [reset, rearm, showExpiredOnly]);

  // تنبيه ما قبل الانتهاء — يظهر فقط عند الخمول قبل الانتهاء، وأي نشاط يخفيه.
  if (!expired && warnSeconds != null) {
    const mm = String(Math.floor(warnSeconds / 60)).padStart(2, "0");
    const ss = String(warnSeconds % 60).padStart(2, "0");
    return createPortal(
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label="تنبيه انتهاء الجلسة"
        style={{
          position: "fixed", inset: 0, zIndex: 100000,
          background: "rgba(0,0,0,0.45)", display: "flex",
          alignItems: "center", justifyContent: "center", padding: 16,
        }}
      >
        <div
          dir="rtl"
          style={{
            width: "100%", maxWidth: 400, background: "#fff", borderRadius: 8,
            boxShadow: "0 10px 40px rgba(0,0,0,.3)", padding: 24, textAlign: "center",
            fontFamily: "inherit",
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 700, color: "#b45309", marginBottom: 8 }}>
            ستنتهي الجلسة قريباً
          </div>
          <p style={{ fontSize: 14, color: "#444", margin: "0 0 6px" }}>
            بسبب عدم النشاط، ستُنهى الجلسة خلال
          </p>
          <div style={{ fontSize: 30, fontWeight: 800, color: "#b91c1c", margin: "0 0 16px", direction: "ltr", letterSpacing: 1 }}>
            {mm}:{ss}
          </div>
          <button
            type="button"
            onClick={reset}
            style={{
              width: "100%", padding: "10px 16px", background: "#2563eb", color: "#fff",
              border: "none", borderRadius: 6, fontWeight: 700, cursor: "pointer", fontSize: 14,
            }}
          >
            متابعة الجلسة
          </button>
        </div>
      </div>,
      document.body,
    );
  }

  if (!expired) return null;

  return createPortal(
    <div
      role="alertdialog"
      aria-modal="true"
      aria-label="تم إنهاء الجلسة"
      style={{
        position: "fixed", inset: 0, zIndex: 100000,
        background: "rgba(0,0,0,0.55)", display: "flex",
        alignItems: "center", justifyContent: "center", padding: 16,
      }}
    >
      <div
        dir="rtl"
        style={{
          width: "100%", maxWidth: 380, background: "#fff", borderRadius: 8,
          boxShadow: "0 10px 40px rgba(0,0,0,.3)", padding: 24, textAlign: "center",
          fontFamily: "inherit",
        }}
      >
        <div style={{ fontSize: 18, fontWeight: 700, color: "#b91c1c", marginBottom: 8 }}>
          تم إنهاء الجلسة
        </div>
        <p style={{ fontSize: 14, color: "#444", margin: "0 0 18px" }}>
          انتهت الجلسة بسبب عدم النشاط. الرجاء تسجيل الدخول من جديد للمتابعة.
        </p>
        <button
          type="button"
          onClick={onLogout}
          style={{
            width: "100%", padding: "10px 16px", background: "#2563eb", color: "#fff",
            border: "none", borderRadius: 6, fontWeight: 700, cursor: "pointer", fontSize: 14,
          }}
        >
          العودة إلى تسجيل الدخول
        </button>
      </div>
    </div>,
    document.body,
  );
};

export default IdleTimeoutGuard;
