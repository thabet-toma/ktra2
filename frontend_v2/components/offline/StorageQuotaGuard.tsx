import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useStorageQuota } from '../../hooks/useStorageQuota';
import { cleanOldCache } from '../../services/offline/cacheCleaner';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function StorageQuotaGuard() {
  const quota = useStorageQuota();
  const [blocked, setBlocked] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (quota.usagePercent > 95) {
      setBlocked(true);
    }
  }, [quota.usagePercent]);

  if (typeof window === 'undefined') return null;

  return (
    <>
      {quota.usagePercent > 80 && quota.usagePercent <= 95 && !dismissed && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-4 right-4 z-50 bg-yellow-50 border border-yellow-200 rounded-xl shadow-lg px-4 py-3 max-w-sm text-sm"
        >
          <div className="flex items-start gap-3">
            <span className="text-yellow-600 text-lg">⚠️</span>
            <div className="flex-1">
              <p className="font-medium text-yellow-800">مساحة التخزين المحلية تقترب من الامتلاء</p>
              <p className="text-yellow-700 mt-1">
                مستخدم {formatBytes(quota.usageBytes)} من {formatBytes(quota.quotaBytes)} ({quota.usagePercent}%)
              </p>
              <div className="flex gap-2 mt-2">
                <button
                  type="button"
                  onClick={async () => {
                    await cleanOldCache(7);
                    setDismissed(true);
                  }}
                  className="text-xs bg-yellow-600 text-white px-3 py-1 rounded-lg hover:bg-yellow-700"
                >
                  امسح cache قديم
                </button>
                <button
                  type="button"
                  onClick={() => setDismissed(true)}
                  className="text-xs text-yellow-700 underline"
                >
                  لاحقاً
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {blocked && createPortal(
        <div
          className="fixed inset-0 z-[9999] bg-black/60 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="quota-title"
        >
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 text-center">
            <span className="text-5xl block mb-4">🚫</span>
            <h2 id="quota-title" className="text-xl font-bold text-gray-800 mb-2">
              مساحة التخزين ممتلئة
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              تم استخدام {quota.usagePercent}% من المساحة المحلية. لا يمكن حفظ بيانات جديدة.
            </p>
            <button
              type="button"
              onClick={async () => {
                await cleanOldCache(1);
                setBlocked(false);
              }}
              className="bg-red-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-red-700 w-full mb-2"
            >
              امسح cache اليوم
            </button>
            <button
              type="button"
              onClick={() => setBlocked(false)}
              className="text-gray-500 underline text-sm"
            >
              تجاهل (قد تفقد بيانات محلية)
            </button>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
