/**
 * إصلاح تلقائي للاتصال «العالق» (صيانة 2026-07).
 *
 * الحالة: browserOnline=true (المتصفح يرى شبكة) بينما نبض /api/health/ يفشل
 * (online=false) ⇒ SW/كاش/اتصال QUIC عالق في ملف تعريف المتصفح. الحل موجود
 * أصلاً في recoverConnection() (مكافئ التصفح الخفي) لكنه كان يدوياً — زر
 * «إصلاح الاتصال» في OfflineBanner لا يلاحظه المستخدم غالباً.
 *
 * هذا الـ hook يستدعيه تلقائياً بعد استمرار الحالة ~45 ثانية (دورتا نبض —
 * يستبعد التذبذب اللحظي)، مع حارس sessionStorage يضمن محاولة واحدة لكل «نوبة»:
 * - sessionStorage ينجو من location.reload() داخل نفس التبويب ⇒ لا حلقة تحميل.
 * - يُعاد التسليح فقط بعد عودة الاتصال فعلياً ⇒ نوبة لاحقة منفصلة تُعالَج أيضاً.
 * الزر اليدوي في OfflineBanner يبقى كخيار احتياطي دائم.
 */
import { useEffect, useRef } from 'react';
import type { OnlineStatus } from './useOnlineStatus';
import { recoverConnection } from '../utils/connectionRecovery';
import { clientLogger } from '../services/logger';

const GUARD_KEY = 'ktra_conn_recovery_done';
// نبض useOnlineStatus كل 30 ثانية ⇒ 45 ثانية = فشل نبضتين متتاليتين على الأقل.
const CONFIRM_DELAY_MS = 45_000;

export function useAutoConnectionRecovery(status: OnlineStatus): void {
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (status.online) {
      // عاد الاتصال طبيعياً — أعد تسليح الحارس لنوبة انقطاع مستقبلية منفصلة.
      try { sessionStorage.removeItem(GUARD_KEY); } catch { /* تجاهل */ }
    }
  }, [status.online]);

  useEffect(() => {
    const stuck = status.browserOnline && !status.online;
    if (!stuck) {
      clearTimeout(timerRef.current);
      return;
    }
    try {
      if (sessionStorage.getItem(GUARD_KEY) === '1') return;
    } catch { return; /* sessionStorage محجوب — لا إصلاح تلقائي بلا حارس */ }

    timerRef.current = setTimeout(() => {
      try {
        if (sessionStorage.getItem(GUARD_KEY) === '1') return;
        sessionStorage.setItem(GUARD_KEY, '1');
      } catch { return; }
      clientLogger.warn('connection.recovery.auto_trigger');
      void recoverConnection();
    }, CONFIRM_DELAY_MS);

    return () => clearTimeout(timerRef.current);
  }, [status.browserOnline, status.online]);
}
