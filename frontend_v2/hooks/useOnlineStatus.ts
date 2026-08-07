import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { API_BASE } from '../services/restApi';

const HEALTH_TIMEOUT_MS = 5_000;
const HEALTH_RETRY_DELAY_MS = 500;

type HealthResult = { ok: boolean };

// App, PendingMutationsPanel and some editors consume this hook concurrently.
// Share one probe so they cannot disagree about the same instant or multiply
// heartbeat traffic. The reference is cleared after every completed probe.
let healthCheckInFlight: Promise<HealthResult> | null = null;

async function probeHealth(method: 'HEAD' | 'GET'): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/health/`, {
      method,
      cache: 'no-store',
      signal: controller.signal,
    });
    return res.ok;
  } catch {
    return false;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

function checkApiHealth(): Promise<HealthResult> {
  if (healthCheckInFlight) return healthCheckInFlight;

  healthCheckInFlight = (async () => {
    if (await probeHealth('HEAD')) return { ok: true };

    // Shared-hosting proxies can drop or delay an isolated HEAD while normal
    // API traffic is healthy. Confirm with a small GET before showing offline UX.
    await new Promise((resolve) => globalThis.setTimeout(resolve, HEALTH_RETRY_DELAY_MS));
    return { ok: await probeHealth('GET') };
  })().finally(() => {
    healthCheckInFlight = null;
  });

  return healthCheckInFlight;
}

export interface OnlineStatus {
  online: boolean;
  /** رأي نظام التشغيل في الاتصال (navigator.onLine). إذا كان true بينما online=false
   *  فالمتصفح متصل بالشبكة لكن نبض الخادم يفشل ⇒ اتصال/كاش عالق (يستدعي «إصلاح الاتصال»). */
  browserOnline: boolean;
  lastOnline: Date;
}

/**
 * ⚠ هذا الـhook يُستهلك في `App` (شجرة التطبيق كلها) وفي محرّر فاتورة المبيعات.
 * كل `setState` فيه يُعيد رسم الشجرة الجالسة تحته — فلا يُخزَّن فيه إلا ما يتغيّر
 * تغيّراً ذا معنى. (كان يخزّن `latencyMs` وهو رقم جديد بعد كل نبضة ولا يقرؤه أحد
 * في الواجهة، فيُجبر التطبيق على إعادة رسم كاملة كل 30 ثانية بلا سبب.)
 */
export function useOnlineStatus(): OnlineStatus {
  const [online, setOnline] = useState(navigator.onLine);
  const [browserOnline, setBrowserOnline] = useState(navigator.onLine);
  const lastOnlineRef = useRef(new Date());
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const heartbeat = useCallback(async () => {
    const result = await checkApiHealth();
    // An OS/browser offline event that happened while the request was in flight
    // remains authoritative; a late cached response must not flip it back online.
    if (!navigator.onLine) {
      setBrowserOnline(false);
      setOnline(false);
      return;
    }
    if (result.ok) {
      setOnline(true);
      lastOnlineRef.current = new Date();
    } else {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    const goOnline = () => { setBrowserOnline(true); setOnline(true); lastOnlineRef.current = new Date(); };
    const goOffline = () => { setBrowserOnline(false); setOnline(false); };

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);

    intervalRef.current = setInterval(heartbeat, 30_000);
    heartbeat();

    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
      clearInterval(intervalRef.current);
    };
  }, [heartbeat]);

  // مرجع ثابت ما دامت الحالة ثابتة — كي لا يُبطِل الكائنُ الجديدُ تبعيات
  // `useEffect`/`useMemo` عند المستهلكين بعد كل رسم.
  return useMemo(
    () => ({ online, browserOnline, lastOnline: lastOnlineRef.current }),
    [online, browserOnline],
  );
}
