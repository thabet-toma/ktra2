import React, { createContext, useContext, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { clientLogger } from '../services/logger';
import { apiGetObject, apiPatchObject } from '../services/restApi';
import { resolveTenantId } from '../utils/tenantContext';
import { IDLE_TIMEOUT_MS } from '../constants/session';
import {
  IDLE_MIN_MINUTES,
  IDLE_MAX_MINUTES,
  DEFAULT_IDLE_MINUTES,
  clampIdleMinutes,
} from '../utils/sessionTimeout';

/**
 * تفضيل الجلسة — مهلة الخمول قبل إنهاء الجلسة (بالدقائق). مصدر الحقيقة هو الخادم
 * (TenantSettings.idle_timeout_minutes) لكل شركة: يُحفَظ per-company فيثبت عبر
 * الأجهزة ولا يرجع للافتراضي عند إعادة فتح الموقع، ومعزول لكل شركة. يُبقى cache
 * محلي مفتاحه رقم الشركة للتطبيق الفوري قبل رد الخادم. يستهلكه {@link IdleTimeoutGuard}
 * بدل الثابت المبرمج، ويُضبط من صفحة الإعدادات (قسم «الجلسة والخمول»).
 */
const IDLE_KEY = 'ktra_idle_timeout_minutes';
const idleCacheKey = (tid: number) => `${IDLE_KEY}::${tid}`;

// الحدود/القصّ منطق نقيّ مشترك (utils/sessionTimeout) — يُعاد تصديره للمستهلكين.
export { IDLE_MIN_MINUTES, IDLE_MAX_MINUTES, DEFAULT_IDLE_MINUTES };
const clampMinutes = clampIdleMinutes;

interface SessionSettingsValue {
  idleTimeoutMinutes: number;
  /** المهلة بالمللي ثانية — يستهلكها الحارس مباشرة. */
  idleTimeoutMs: number;
  setIdleTimeoutMinutes: (v: number) => void;
}

const SessionSettingsContext = createContext<SessionSettingsValue | null>(null);

/** يقرأ التفضيل من cache الشركة ثم الافتراضي. */
const readCached = (tid: number): number => {
  try {
    const v = localStorage.getItem(idleCacheKey(tid));
    const n = v ? Number(v) : NaN;
    return Number.isFinite(n) ? clampMinutes(n) : DEFAULT_IDLE_MINUTES;
  } catch {
    return DEFAULT_IDLE_MINUTES;
  }
};

const writeCache = (tid: number, v: number): void => {
  try { localStorage.setItem(idleCacheKey(tid), String(v)); } catch { /* الذاكرة تكفي */ }
};

const hasToken = (): boolean => {
  try { return !!localStorage.getItem('token'); } catch { return false; }
};

export const SessionSettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // الشركة النشطة تُثبَّت عند التركيب؛ تبديل الشركة يعيد تحميل الصفحة بالكامل.
  const tenantId = resolveTenantId();
  const [idleTimeoutMinutes, setIdleState] = useState<number>(() => readCached(tenantId));

  /** حفظ التفضيل خادمياً (per-company). غير حظري — لا يُعطّل الواجهة. */
  const persist = useCallback((minutes: number) => {
    if (!hasToken()) return; // زائر — cache محلي فقط
    void apiPatchObject('tenants/settings/current/', { idle_timeout_minutes: minutes }, { tenantId })
      .catch((e) => clientLogger.warn('session.idle_persist_failed', { error: String(e) }));
  }, [tenantId]);

  // مزامنة أوّلية من الخادم (مصدر الحقيقة per-company). تعمل مرة لكل تركيب.
  const syncedRef = useRef(false);
  useEffect(() => {
    if (syncedRef.current || !hasToken()) return;
    syncedRef.current = true;
    void (async () => {
      try {
        const s = await apiGetObject<{ idle_timeout_minutes?: number }>(
          'tenants/settings/current/', { tenantId },
        );
        const srv = Number(s?.idle_timeout_minutes);
        if (Number.isFinite(srv)) {
          const clamped = clampMinutes(srv);
          setIdleState(clamped);
          writeCache(tenantId, clamped);
        }
      } catch (e) {
        clientLogger.warn('session.idle_sync_failed', { error: String(e) });
      }
    })();
  }, [tenantId]);

  const setIdleTimeoutMinutes = useCallback((v: number) => {
    const clamped = clampMinutes(v);
    setIdleState(clamped);
    writeCache(tenantId, clamped);
    persist(clamped);
    clientLogger.info('session.idle_timeout_changed', { minutes: clamped });
  }, [tenantId, persist]);

  const value = useMemo<SessionSettingsValue>(
    () => ({
      idleTimeoutMinutes,
      idleTimeoutMs: idleTimeoutMinutes * 60000,
      setIdleTimeoutMinutes,
    }),
    [idleTimeoutMinutes, setIdleTimeoutMinutes],
  );

  return <SessionSettingsContext.Provider value={value}>{children}</SessionSettingsContext.Provider>;
};

export function useSessionSettings(): SessionSettingsValue {
  const ctx = useContext(SessionSettingsContext);
  // افتراضات آمنة عند غياب المزوّد (لا نرمي استثناءً).
  return (
    ctx ?? {
      idleTimeoutMinutes: DEFAULT_IDLE_MINUTES,
      idleTimeoutMs: IDLE_TIMEOUT_MS,
      setIdleTimeoutMinutes: () => {},
    }
  );
}
