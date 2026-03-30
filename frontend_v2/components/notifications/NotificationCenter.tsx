import React, { useState, useEffect, useRef } from 'react';
import { AppNotification, AppView } from '../../types';
import { notificationsService } from '../../services/notificationsService';
import { Bell, Check, ExternalLink, Inbox, X } from 'lucide-react';

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

        if (notification.targetView) {
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
                className="relative p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-all"
            >
                <Bell className="w-6 h-6" />
                {unreadCount > 0 && (
                    <span className="absolute top-0 right-0 w-5 h-5 bg-red-500 text-white text-[10px] font-bold flex items-center justify-center rounded-full border-2 border-white dark:border-gray-800">
                        {unreadCount > 9 ? '+9' : unreadCount}
                    </span>
                )}
            </button>

            {isOpen && (
                <div className="absolute left-0 mt-2 w-80 sm:w-96 bg-white dark:bg-gray-800 rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-700 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2">
                    <div className="p-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center bg-gray-50/50 dark:bg-gray-900/50">
                        <h3 className="font-bold dark:text-white flex items-center gap-2">
                            <Inbox className="w-5 h-5 text-blue-500" />
                            الإشعارات
                        </h3>
                        {unreadCount > 0 && (
                            <button
                                onClick={markAllAsRead}
                                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                            >
                                <Check className="w-3 h-3" />
                                تحديد الكل كمقروء
                            </button>
                        )}
                    </div>

                    <div className="max-h-[400px] overflow-y-auto">
                        {notifications.length > 0 ? (
                            <div className="divide-y divide-gray-100 dark:divide-gray-700">
                                {notifications.map((n) => (
                                    <div
                                        key={n.id}
                                        onClick={() => handleNotificationClick(n)}
                                        className={`p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors relative group ${!n.isRead ? 'bg-blue-50/30 dark:bg-blue-900/10' : ''}`}
                                    >
                                        {!n.isRead && (
                                            <div className="absolute right-2 top-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-blue-500 rounded-full" />
                                        )}
                                        <div className="mr-3">
                                            <div className="flex justify-between items-start mb-1">
                                                <h4 className={`text-sm font-bold ${!n.isRead ? 'text-blue-900 dark:text-blue-100' : 'text-gray-900 dark:text-gray-100'}`}>
                                                    {n.title}
                                                </h4>
                                                <span className="text-[10px] text-gray-400">
                                                    {new Date(n.createdAt).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                            </div>
                                            <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mb-2">
                                                {n.message}
                                            </p>
                                            {n.targetView && (
                                                <div className="flex items-center gap-1 text-[10px] text-blue-600 dark:text-blue-400 font-medium">
                                                    <ExternalLink className="w-3 h-3" />
                                                    عرض التفاصيل
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="p-12 text-center text-gray-500 dark:text-gray-400">
                                <Inbox className="w-12 h-12 mx-auto mb-3 opacity-20" />
                                <p className="text-sm">لا توجد إشعارات جديدة</p>
                            </div>
                        )}
                    </div>

                    <div className="p-3 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/50 text-center">
                        <button
                            onClick={() => setIsOpen(false)}
                            className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 transition-colors"
                        >
                            إغلاق
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
