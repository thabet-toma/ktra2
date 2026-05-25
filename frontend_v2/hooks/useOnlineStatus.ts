import { useState, useEffect, useRef, useCallback } from 'react';

export interface OnlineStatus {
  online: boolean;
  lastOnline: Date;
  latencyMs: number;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function useOnlineStatus(): OnlineStatus {
  const [online, setOnline] = useState(navigator.onLine);
  const [latencyMs, setLatencyMs] = useState(0);
  const lastOnlineRef = useRef(new Date());
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const heartbeat = useCallback(async () => {
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/api/health/`, {
        method: 'HEAD',
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        setLatencyMs(Math.round(performance.now() - start));
        setOnline(true);
        lastOnlineRef.current = new Date();
      }
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    const goOnline = () => { setOnline(true); lastOnlineRef.current = new Date(); };
    const goOffline = () => setOnline(false);

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

  return { online, lastOnline: lastOnlineRef.current, latencyMs };
}
