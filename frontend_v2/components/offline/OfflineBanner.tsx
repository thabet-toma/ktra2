import React, { useState, useEffect } from 'react';
import type { OnlineStatus } from '../../hooks/useOnlineStatus';
import db from '../../services/offline/db';

type Props = {
  status: OnlineStatus;
  onRetry: () => void;
};

function relativeTime(date: Date): string {
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60) return 'منذ لحظات';
  if (diff < 3600) return `منذ ${Math.floor(diff / 60)} دقيقة`;
  if (diff < 86400) return `منذ ${Math.floor(diff / 3600)} ساعة`;
  return `منذ ${Math.floor(diff / 86400)} يوم`;
}

export default function OfflineBanner({ status, onRetry }: Props) {
  const [hasOfflineData, setHasOfflineData] = useState(false);
  const [customMessage, setCustomMessage] = useState('');

  useEffect(() => {
    db.cache_meta.count().then((count) => {
      setHasOfflineData(count > 0);
    });

    const msg = localStorage.getItem('offline_notification_message');
    if (msg) {
      setCustomMessage(msg);
    }
  }, []);

  if (status.online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={`sticky top-0 z-40 w-full px-4 py-2 text-sm text-center font-medium
        ${hasOfflineData
          ? 'bg-yellow-100 text-yellow-800 border-b border-yellow-200'
          : 'bg-red-100 text-red-800 border-b border-red-200'
        }`}
    >
      <span>
        {customMessage ? (
          customMessage
        ) : (
          `🔴 بدون اتصال — تعرض آخر بيانات محفوظة ${
            status.lastOnline ? relativeTime(status.lastOnline) : ''
          }. الترحيل والمزامنة معطَّلة.`
        )}
      </span>
      <button
        onClick={onRetry}
        className="mr-3 underline hover:no-underline font-semibold"
      >
        أعِد المحاولة
      </button>
    </div>
  );
}
