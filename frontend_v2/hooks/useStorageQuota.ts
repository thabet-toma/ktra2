import { useState, useEffect, useRef, useCallback } from 'react';

export interface StorageQuota {
  usagePercent: number;
  usageBytes: number;
  quotaBytes: number;
}

export function useStorageQuota(): StorageQuota {
  const [quota, setQuota] = useState<StorageQuota>({ usagePercent: 0, usageBytes: 0, quotaBytes: 0 });
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const check = useCallback(async () => {
    try {
      if (!navigator.storage?.estimate) return;
      const est = await navigator.storage.estimate();
      const usageBytes = est.usage ?? 0;
      const quotaBytes = est.quota ?? 1;
      setQuota({
        usageBytes,
        quotaBytes,
        usagePercent: Math.round((usageBytes / quotaBytes) * 100),
      });
    } catch {}
  }, []);

  useEffect(() => {
    check();
    intervalRef.current = setInterval(check, 3600_000);
    return () => clearInterval(intervalRef.current);
  }, [check]);

  return quota;
}
