import { useEffect, useState } from 'react';

export default function UpdatePrompt() {
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    let registration: ServiceWorkerRegistration | null = null;
    const handler = () => setWaiting(true);

    navigator.serviceWorker?.ready.then((reg) => {
      registration = reg;
      if (reg.waiting) handler();
      reg.addEventListener('updatefound', () => {
        const newSW = reg.installing;
        if (newSW) {
          newSW.addEventListener('statechange', () => {
            if (newSW.state === 'installed' && navigator.serviceWorker.controller) {
              handler();
            }
          });
        }
      });
    });

    return () => {
      registration?.removeEventListener('updatefound', handler);
    };
  }, []);

  const applyUpdate = () => {
    navigator.serviceWorker.ready.then((reg) => {
      reg.waiting?.postMessage({ type: 'SKIP_WAITING' });
      setWaiting(false);
      window.location.reload();
    });
  };

  if (!waiting) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-[var(--color-surface)] border border-blue-200 rounded-xl shadow-lg px-5 py-3 flex items-center gap-4 text-sm"
    >
      <span className="text-[var(--color-text)]">توفّر تحديث للنظام</span>
      <button
        onClick={applyUpdate}
        className="bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
      >
        أعِد التحميل
      </button>
    </div>
  );
}
