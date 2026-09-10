import React, { useEffect, useRef, useState } from "react";
import { formatDateTimeValue } from "../../utils/formatDate.ts";
import {
  getPlatformNotifications,
  getUnreadNotificationsCount,
  markAllNotificationsRead,
  markNotificationRead,
  PlatformNotification,
} from "../../services/platformOpsApi";

export const PlatformNotificationBell: React.FC = () => {
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [notifications, setNotifications] = useState<PlatformNotification[]>([]);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = async () => {
    try {
      const res = await getUnreadNotificationsCount();
      setUnreadCount(res.unread_count ?? 0);
    } catch {
      // إخفاق هادئ لا يعطل الواجهة
    }
  };

  const fetchNotificationsList = async () => {
    try {
      setLoading(true);
      const res = await getPlatformNotifications(false);
      const items = Array.isArray(res) ? res : res.results || [];
      setNotifications(items);
    } catch {
      // إخفاق هادئ
    } finally {
      setLoading(false);
    }
  };

  // اقتراع كل 60 ثانية ما دام التبويب ظاهراً حصراً (م٦)
  useEffect(() => {
    fetchUnreadCount();

    let intervalId: any = null;

    const startPolling = () => {
      if (!intervalId) {
        intervalId = setInterval(() => {
          if (document.visibilityState === "visible") {
            fetchUnreadCount();
          }
        }, 60000); // 60s
      }
    };

    const stopPolling = () => {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        fetchUnreadCount();
        startPolling();
      } else {
        stopPolling();
      }
    };

    if (document.visibilityState === "visible") {
      startPolling();
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  // إغلاق القائمة عند النقر خارجها
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const handleToggle = () => {
    const nextState = !isOpen;
    setIsOpen(nextState);
    if (nextState) {
      fetchNotificationsList();
    }
  };

  const handleMarkRead = async (id: number) => {
    try {
      await markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // إخفاق
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
    } catch {
      // إخفاق
    }
  };

  return (
    <div className="relative inline-block text-right" ref={dropdownRef} dir="rtl">
      <button
        type="button"
        onClick={handleToggle}
        className="relative p-2 text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-100 rounded-full border border-slate-200 transition focus:outline-none focus:ring-2 focus:ring-blue-500"
        title="إشعارات المنصة"
      >
        <span className="sr-only">فتح الإشعارات</span>
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>

        {unreadCount > 0 && (
          <span className="absolute -top-1 -left-1 flex items-center justify-center min-w-[20px] h-5 px-1 text-xs font-bold text-white bg-rose-600 rounded-full border-2 border-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-2 w-80 sm:w-96 bg-white rounded-xl shadow-xl border border-slate-200 z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-800">إشعارات المنصة</h3>
              {unreadCount > 0 && (
                <span className="px-2 py-0.5 text-xs font-medium text-blue-700 bg-blue-100 rounded-full">
                  {unreadCount} غير مقروء
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="text-xs text-blue-600 hover:text-blue-800 font-medium transition"
              >
                تعليم الكل كمقروء
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">
            {loading ? (
              <div className="py-8 text-center text-sm text-slate-400">جاري تحميل الإشعارات...</div>
            ) : notifications.length === 0 ? (
              <div className="py-8 text-center text-sm text-slate-400">لا توجد إشعارات حالياً</div>
            ) : (
              notifications.map((item) => (
                <div
                  key={item.id}
                  className={`p-3.5 transition flex items-start justify-between gap-3 ${
                    item.is_read ? "bg-white hover:bg-slate-50" : "bg-blue-50/40 hover:bg-blue-50/70"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`inline-block px-2 py-0.5 text-[11px] font-semibold rounded border ${
                          item.notification_type === "sla_breach"
                            ? "bg-rose-100 text-rose-800 border-rose-200"
                            : item.notification_type === "low_score"
                            ? "bg-purple-100 text-purple-800 border-purple-200"
                            : "bg-amber-100 text-amber-800 border-amber-200"
                        }`}
                      >
                        {item.notification_type_display || item.notification_type}
                      </span>
                      {item.company_name && (
                        <span className="text-xs text-slate-500 truncate max-w-[120px]">
                          {item.company_name}
                        </span>
                      )}
                    </div>
                    <h4 className="text-sm font-semibold text-slate-800 truncate">{item.title}</h4>
                    {item.message && (
                      <p className="text-xs text-slate-600 mt-0.5 line-clamp-2 leading-relaxed">
                        {item.message}
                      </p>
                    )}
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      {formatDateTimeValue(item.created_at)}
                    </span>
                  </div>

                  {!item.is_read && (
                    <button
                      type="button"
                      onClick={() => handleMarkRead(item.id)}
                      className="text-xs text-slate-400 hover:text-blue-600 p-1 rounded transition flex-shrink-0"
                      title="تعليم كمقروء"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                      </svg>
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
