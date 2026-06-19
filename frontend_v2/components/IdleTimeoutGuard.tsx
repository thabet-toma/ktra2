/**
 * DEF-009 — حارس مهلة الخمول.
 * بعد {@link IDLE_TIMEOUT_MS} من غياب أي نشاط (نقر/مفتاح/تمرير/لمس/تنقّل) يُبطل
 * الجلسة (يمسح التوكن) ويعرض مودال «تم إنهاء الجلسة» يعيد المستخدم إلى تسجيل
 * الدخول. أي نشاط قبل انتهاء المهلة يُعيد ضبط المؤقّت.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { IDLE_TIMEOUT_MS } from "../constants/session";
import { logoutUser } from "../services/authService";

interface Props {
  /** يُستدعى عند ضغط زر العودة — يُفترض أن يُفرّغ المستخدم الحالي (سياق المصادقة). */
  onLogout: () => void;
}

export const IdleTimeoutGuard: React.FC<Props> = ({ onLogout }) => {
  const [expired, setExpired] = useState(false);
  const timerRef = useRef<number | null>(null);
  const expiredRef = useRef(false);

  const handleExpire = useCallback(() => {
    if (expiredRef.current) return;
    expiredRef.current = true;
    // إبطال الجلسة فوراً (مسح التوكن) — أي نداء API بعدها غير مُصرَّح به.
    void logoutUser();
    setExpired(true);
  }, []);

  const reset = useCallback(() => {
    if (expiredRef.current) return;
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(handleExpire, IDLE_TIMEOUT_MS);
  }, [handleExpire]);

  useEffect(() => {
    // throttle: لا نعيد ضبط المؤقّت أكثر من مرة كل ثانية لتفادي ضغط الأحداث.
    let last = 0;
    const onActivity = () => {
      const now = Date.now();
      if (now - last < 1000) return;
      last = now;
      reset();
    };
    const events: (keyof WindowEventMap)[] = [
      "mousedown", "keydown", "scroll", "wheel", "touchstart", "pointerdown", "focus",
    ];
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true, capture: true }));
    reset();
    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity, { capture: true } as any));
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    };
  }, [reset]);

  if (!expired) return null;

  return createPortal(
    <div
      data-skin="aseel"
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
