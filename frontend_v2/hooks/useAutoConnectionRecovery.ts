/**
 * مراقبة الاتصال «العالق» (صيانة 2026-07).
 *
 * الحالة: browserOnline=true (المتصفح يرى شبكة) بينما نبض /api/health/ يفشل
 * (online=false) ⇒ قد يكون SW/كاش/اتصال QUIC عالقاً في ملف تعريف المتصفح.
 *
 * بعد استمرار الحالة ~45 ثانية (دورتا نبض) يسجّل الـ hook التشخيص مرة واحدة
 * فقط. لا يمسح الكاش ولا يعيد تحميل الصفحة تلقائياً لأن ذلك قد يقطع مستنداً غير
 * محفوظ. يبقى قرار «إصلاح الاتصال» للمستخدم عبر الزر اليدوي في OfflineBanner.
 */
import { useEffect, useRef } from 'react';
import type { OnlineStatus } from './useOnlineStatus';
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
    } catch { return; /* sessionStorage محجوب — لا تسجيل دوري بلا حارس */ }

    timerRef.current = setTimeout(() => {
      try {
        if (sessionStorage.getItem(GUARD_KEY) === '1') return;
        sessionStorage.setItem(GUARD_KEY, '1');
      } catch { return; }
      clientLogger.warn('connection.recovery.manual_required');
    }, CONFIRM_DELAY_MS);

    return () => clearTimeout(timerRef.current);
  }, [status.browserOnline, status.online]);
}
