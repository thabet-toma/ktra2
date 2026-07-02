import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE } from '../services/restApi';

export interface OnlineStatus {
  online: boolean;
  /** رأي نظام التشغيل في الاتصال (navigator.onLine). إذا كان true بينما online=false
   *  فالمتصفح متصل بالشبكة لكن نبض الخادم يفشل ⇒ اتصال/كاش عالق (يستدعي «إصلاح الاتصال»). */
  browserOnline: boolean;
  lastOnline: Date;
  latencyMs: number;
}

export function useOnlineStatus(): OnlineStatus {
  const [online, setOnline] = useState(navigator.onLine);
  const [browserOnline, setBrowserOnline] = useState(navigator.onLine);
  const [latencyMs, setLatencyMs] = useState(0);
  const lastOnlineRef = useRef(new Date());
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const heartbeat = useCallback(async () => {
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/health/`, {
        method: 'HEAD',
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        setLatencyMs(Math.round(performance.now() - start));
        setOnline(true);
        lastOnlineRef.current = new Date();
      } else {
        setOnline(false);
      }
    } catch {
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

  return { online, browserOnline, lastOnline: lastOnlineRef.current, latencyMs };
}
