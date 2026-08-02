import React, { useState, useEffect, useRef } from 'react';
import { AppNotification, AppView } from '../../types';
import { notificationsService } from '../../services/notificationsService';
import { Bell, Check, ExternalLink, Inbox, X } from 'lucide-react';
import { isSafeInternalPath } from '../../utils/entityLinks';

interface NotificationCenterProps {
    currentUserId: string;
    onNavigate: (view: AppView, targetId?: string) => void;
}

export const NotificationCenter: React.FC<NotificationCenterProps> = ({ currentUserId, onNavigate }) => {
    const [notifications, setNotifications] = useState<AppNotification[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // Subscribe to notifications for this user (or "all_managers" as a broadcast)
        // For now, let's assume we subscribe to both
        const unsubscribe = notificationsService.subscribeToNotifications(currentUserId, (newNotifications) => {
            setNotifications(newNotifications);
        });

        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            unsubscribe();
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [currentUserId]);

    const unreadCount = notifications.filter(n => !n.isRead).length;

    const handleNotificationClick = async (notification: AppNotification) => {
        if (!notification.isRead) {
            await notificationsService.markAsRead(notification.id);
        }

        if (notification.targetPath && isSafeInternalPath(notification.targetPath)) {
            setIsOpen(false);
            window.location.assign(notification.targetPath);
            return;
        }

        if (notification.targetView) {
            // جسر تحديد العنصر داخل الوجهة (مثلاً تبويب «ملاحظات الزبون» + الملاحظة)
            // — يُقرأ ويُمسح في صفحة الوجهة بعد التنقل.
            try {
                if (notification.targetTab) {
                    sessionStorage.setItem('ktra_focus_partner_tab', notification.targetTab);
                    if (notification.targetSecondaryId) {
                        sessionStorage.setItem('ktra_focus_partner_note', notification.targetSecondaryId);
                    }
                }
            } catch { /* خاصية خاصة */ }
            onNavigate(notification.targetView, notification.targetId);
            setIsOpen(false);
        }
    };

    const markAllAsRead = async () => {
        const unreadIds = notifications.filter(n => !n.isRead).map(n => n.id);
        for (const id of unreadIds) {
            await notificationsService.markAsRead(id);
        }
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="relative p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)] rounded-full transition-all"
                title="الإشعارات"
                aria-label={`الإشعارات${unreadCount > 0 ? ` (${unreadCount} غير مقروءة)` : ""}`}
                aria-expanded={isOpen}
            >
                <Bell className="w-6 h-6" />
                {unreadCount > 0 && (
                    <span className="absolute top-0 right-0 w-5 h-5 bg-[var(--color-danger)] text-[var(--color-text-inverted)] text-[10px] font-bold flex items-center justify-center rounded-full border-2 border-[var(--color-surface)]">
                        {unreadCount > 9 ? '+9' : unreadCount}
                    </span>
                )}
            </button>

            {isOpen && (
                <div className="absolute left-0 mt-2 w-80 sm:w-96 bg-[var(--color-surface)] rounded-2xl shadow-2xl border border-[var(--color-border)] z-50 overflow-hidden animate-in fade-in slide-in-from-top-2">
                    <div className="p-4 border-b border-[var(--color-border)] flex justify-between items-center bg-[var(--color-surface-2)]">
                        <h3 className="font-bold dark:text-white flex items-center gap-2">
                            <Inbox className="w-5 h-5 text-[var(--color-primary)]" />
                            الإشعارات
                        </h3>
                        {unreadCount > 0 && (
                            <button
                                onClick={markAllAsRead}
                                className="text-xs text-[var(--color-primary)] hover:underline flex items-center gap-1"
                            >
                                <Check className="w-3 h-3" />
                                تحديد الكل كمقروء
                            </button>
                        )}
                    </div>

                    <div className="max-h-[400px] overflow-y-auto">
                        {notifications.length > 0 ? (
                            <div className="divide-y divide-[var(--color-border)]">
                                {notifications.map((n) => (
                                    <div
                                        key={n.id}
                                        onClick={() => handleNotificationClick(n)}
                                        className={`p-4 hover:bg-[var(--color-surface-2)] cursor-pointer transition-colors relative group ${!n.isRead ? 'bg-[color-mix(in_srgb,var(--color-primary)_7%,transparent)]' : ''}`}
                                    >
                                        {!n.isRead && (
                                            <div className="absolute right-2 top-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-[var(--color-primary)] rounded-full" />
                                        )}
                                        <div className="mr-3">
                                            <div className="flex justify-between items-start mb-1">
                                                <h4 className={`text-sm font-bold ${!n.isRead ? 'text-[var(--color-primary)]' : 'text-[var(--color-text)]'}`}>
                                                    {n.title}
                                                </h4>
                                                <span className="text-[10px] text-[var(--color-text-muted)]">
                                                    {new Date(n.createdAt).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                            </div>
                                            <p className="text-xs text-[var(--color-text-muted)] line-clamp-2 mb-2">
                                                {n.message}
                                            </p>
                                            {(n.targetView || n.targetPath) && (
                                                <div className="flex items-center gap-1 text-[10px] text-[var(--color-primary)] font-medium">
                                                    <ExternalLink className="w-3 h-3" />
                                                    عرض التفاصيل
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="p-12 text-center text-[var(--color-text-muted)]">
                                <Inbox className="w-12 h-12 mx-auto mb-3 opacity-20" />
                                <p className="text-sm">لا توجد إشعارات جديدة</p>
                            </div>
                        )}
                    </div>

                    <div className="p-3 border-t border-[var(--color-border)] bg-[var(--color-surface-2)] text-center">
                        <button
                            onClick={() => setIsOpen(false)}
                            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
                        >
                            إغلاق
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
