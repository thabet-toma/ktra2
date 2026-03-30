// DealActivityPreview.tsx
import React, { useState, useEffect } from 'react';
import { DealActivity } from '@/types';
import { dealsService } from '@/services/dealsService';
import {
    History, X, User, Clock, CheckCircle, AlertCircle,
    DollarSign, Package, Edit, FileText, MessageSquare,
    Calendar, Eye, RefreshCw
} from 'lucide-react';

interface DealActivityPreviewProps {
    dealId: string;
    dealNumber?: string;
    isOpen: boolean;
    onClose: () => void;
}

export const DealActivityPreview: React.FC<DealActivityPreviewProps> = ({
    dealId,
    dealNumber,
    isOpen,
    onClose
}) => {
    const [activities, setActivities] = useState<DealActivity[]>([]);
    const [loading, setLoading] = useState(false);

    // تحميل النشاطات عند فتح المكون
    useEffect(() => {
        if (isOpen && dealId) {
            loadActivities();
        }
    }, [isOpen, dealId]);

    const loadActivities = async () => {
        try {
            setLoading(true);
            const loadedActivities = await dealsService.getDealActivities(dealId);
            setActivities(loadedActivities);
        } catch (error) {
            console.error('Error loading activities:', error);
        } finally {
            setLoading(false);
        }
    };

    // تحديد أيقونة النشاط حسب النوع
    const getActivityIcon = (type: string, action?: string) => {
        const actionLower = action?.toLowerCase() || '';

        switch (type) {
            case 'status_change':
                if (actionLower.includes('complete') || actionLower.includes('confirm'))
                    return <CheckCircle className="w-5 h-5" />;
                if (actionLower.includes('cancel') || actionLower.includes('reject'))
                    return <AlertCircle className="w-5 h-5" />;
                return <Clock className="w-5 h-5" />;

            case 'payment':
                return <DollarSign className="w-5 h-5" />;

            case 'item_update':
                return <Package className="w-5 h-5" />;

            case 'attachment':
                return <FileText className="w-5 h-5" />;

            case 'note':
                return <MessageSquare className="w-5 h-5" />;

            default:
                return <Clock className="w-5 h-5" />;
        }
    };

    // تحديد لون النشاط
    const getActivityColor = (type: string, action: string) => {
        const actionLower = action.toLowerCase();

        if (actionLower.includes('completed') || actionLower.includes('confirmed') || actionLower.includes('success')) {
            return {
                bg: 'bg-green-50 dark:bg-green-900/20',
                text: 'text-green-700 dark:text-green-300',
                border: 'border-green-200 dark:border-green-800',
                icon: 'text-green-600 dark:text-green-400'
            };
        }

        if (actionLower.includes('cancelled') || actionLower.includes('rejected') || actionLower.includes('failed')) {
            return {
                bg: 'bg-red-50 dark:bg-red-900/20',
                text: 'text-red-700 dark:text-red-300',
                border: 'border-red-200 dark:border-red-800',
                icon: 'text-red-600 dark:text-red-400'
            };
        }

        if (actionLower.includes('pending') || actionLower.includes('waiting')) {
            return {
                bg: 'bg-amber-50 dark:bg-amber-900/20',
                text: 'text-amber-700 dark:text-amber-300',
                border: 'border-amber-200 dark:border-amber-800',
                icon: 'text-amber-600 dark:text-amber-400'
            };
        }

        // ألوان حسب النوع
        switch (type) {
            case 'payment':
                return {
                    bg: 'bg-blue-50 dark:bg-blue-900/20',
                    text: 'text-blue-700 dark:text-blue-300',
                    border: 'border-blue-200 dark:border-blue-800',
                    icon: 'text-blue-600 dark:text-blue-400'
                };

            case 'item_update':
                return {
                    bg: 'bg-purple-50 dark:bg-purple-900/20',
                    text: 'text-purple-700 dark:text-purple-300',
                    border: 'border-purple-200 dark:border-purple-800',
                    icon: 'text-purple-600 dark:text-purple-400'
                };

            case 'attachment':
                return {
                    bg: 'bg-cyan-50 dark:bg-cyan-900/20',
                    text: 'text-cyan-700 dark:text-cyan-300',
                    border: 'border-cyan-200 dark:border-cyan-800',
                    icon: 'text-cyan-600 dark:text-cyan-400'
                };

            default:
                return {
                    bg: 'bg-gray-50 dark:bg-gray-800/30',
                    text: 'text-gray-700 dark:text-gray-300',
                    border: 'border-gray-200 dark:border-gray-700',
                    icon: 'text-gray-600 dark:text-gray-400'
                };
        }
    };

    // تنسيق التاريخ والوقت
    const formatDateTime = (timestamp: string) => {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffHours = Math.floor(diffMs / 3600000);

        if (diffHours < 24) {
            return date.toLocaleTimeString('ar-EG', {
                hour: '2-digit',
                minute: '2-digit'
            });
        } else {
            return date.toLocaleDateString('ar-EG', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    };

    // تنسيق التاريخ الكامل
    const formatFullDate = (timestamp: string) => {
        const date = new Date(timestamp);
        return date.toLocaleDateString('ar-EG', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-gray-900/90 dark:bg-black/95 flex items-start justify-center p-0 z-[9999] overflow-y-auto">
            <div className="bg-white dark:bg-gray-900 w-full min-h-screen">
                {/* Header - Fixed */}
                <div className="sticky top-0 z-50 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 shadow-sm">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
                                    <History className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                                </div>
                                <div>
                                    <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
                                        سجل النشاطات
                                        {dealNumber && (
                                            <span className="text-blue-600 dark:text-blue-400 ml-2">
                                                #{dealNumber}
                                            </span>
                                        )}
                                    </h1>
                                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                        {activities.length} نشاط مسجل
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                <button
                                    onClick={loadActivities}
                                    disabled={loading}
                                    className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                                    title="تحديث"
                                >
                                    <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                                </button>
                                <button
                                    onClick={onClose}
                                    className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                                    title="إغلاق"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-20">
                            <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                            <p className="mt-4 text-gray-600 dark:text-gray-400">جاري تحميل النشاطات...</p>
                        </div>
                    ) : activities.length === 0 ? (
                        <div className="text-center py-20">
                            <div className="w-24 h-24 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-6">
                                <History className="w-12 h-12 text-gray-400 dark:text-gray-500" />
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                                لا توجد نشاطات
                            </h3>
                            <p className="text-gray-600 dark:text-gray-400">
                                لم يتم تسجيل أي نشاطات على هذه الصفقة بعد
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Summary */}
                            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4 border border-blue-200 dark:border-blue-800">
                                <div className="flex flex-wrap items-center gap-4 text-sm">
                                    <div className="flex items-center gap-2">
                                        <Calendar className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        <span className="text-gray-700 dark:text-gray-300">
                                            أول نشاط: {activities.length > 0 ? formatFullDate(activities[activities.length - 1].timestamp) : '-'}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Eye className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        <span className="text-gray-700 dark:text-gray-300">
                                            آخر نشاط: {activities.length > 0 ? formatDateTime(activities[0].timestamp) : '-'}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Activities List */}
                            <div className="space-y-4">
                                {activities.map((activity, index) => {
                                    const colors = getActivityColor(activity.type, activity.action);
                                    const isFirst = index === 0;
                                    const isLast = index === activities.length - 1;

                                    return (
                                        <div
                                            key={activity.id}
                                            className={`p-4 rounded-xl border ${colors.bg} ${colors.border} transition-colors hover:shadow-md`}
                                        >
                                            <div className="flex items-start gap-4">
                                                {/* Icon */}
                                                <div className={`p-3 rounded-lg ${colors.bg}`}>
                                                    <div className={colors.icon}>
                                                        {getActivityIcon(activity.type, activity.action)}
                                                    </div>
                                                </div>

                                                {/* Content */}
                                                <div className="flex-1">
                                                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-3 mb-2">
                                                        <div className="flex-1">
                                                            <h3 className={`font-bold text-lg mb-1 ${colors.text}`}>
                                                                {activity.action}
                                                            </h3>
                                                            {activity.details && (
                                                                <p className="text-gray-700 dark:text-gray-300 text-sm">
                                                                    {activity.details}
                                                                </p>
                                                            )}
                                                        </div>

                                                        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                                                            <Clock className="w-4 h-4" />
                                                            <span>{formatDateTime(activity.timestamp)}</span>
                                                        </div>
                                                    </div>

                                                    {/* User Info */}
                                                    <div className="flex flex-wrap items-center gap-4 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                                                        <div className="flex items-center gap-2">
                                                            <User className="w-4 h-4 text-gray-500" />
                                                            <span className="font-medium text-gray-700 dark:text-gray-300">
                                                                {activity.userName}
                                                            </span>
                                                            <span className="text-sm text-gray-500 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
                                                                {activity.userRole}
                                                            </span>
                                                        </div>

                                                        {/* Activity Type */}
                                                        <div className={`px-3 py-1 rounded-full text-xs font-medium ${colors.text} ${colors.bg} border ${colors.border}`}>
                                                            {activity.type === 'status_change' && 'تغيير حالة'}
                                                            {activity.type === 'payment' && 'دفعة'}
                                                            {activity.type === 'item_update' && 'منتج'}
                                                            {activity.type === 'attachment' && 'مرفق'}
                                                            {activity.type === 'note' && 'ملاحظة'}
                                                            {!['status_change', 'payment', 'item_update', 'attachment', 'note'].includes(activity.type) && activity.type}
                                                        </div>
                                                    </div>

                                                    {/* Metadata */}
                                                    {activity.metadata && Object.keys(activity.metadata).length > 0 && (
                                                        <details className="mt-4">
                                                            <summary className="cursor-pointer text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1">
                                                                <Eye className="w-4 h-4" />
                                                                <span>عرض التفاصيل</span>
                                                            </summary>
                                                            <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700">
                                                                <div className="space-y-2">
                                                                    {Object.entries(activity.metadata).map(([key, value]) => (
                                                                        <div key={key} className="flex justify-between text-sm">
                                                                            <span className="text-gray-600 dark:text-gray-400">
                                                                                {key}:
                                                                            </span>
                                                                            <span className="font-medium text-gray-800 dark:text-gray-200">
                                                                                {typeof value === 'object'
                                                                                    ? JSON.stringify(value)
                                                                                    : String(value)
                                                                                }
                                                                            </span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        </details>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Stats */}
                            <div className="bg-gray-50 dark:bg-gray-800/30 rounded-xl p-4 border border-gray-200 dark:border-gray-700">
                                <h3 className="font-bold text-gray-900 dark:text-white mb-3">إحصائيات النشاطات</h3>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                    <div className="bg-white dark:bg-gray-800 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                                        <div className="text-sm text-gray-500 dark:text-gray-400">المجموع</div>
                                        <div className="text-xl font-bold text-gray-900 dark:text-white">{activities.length}</div>
                                    </div>
                                    <div className="bg-white dark:bg-gray-800 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                                        <div className="text-sm text-gray-500 dark:text-gray-400">تغييرات الحالة</div>
                                        <div className="text-xl font-bold text-blue-600 dark:text-blue-400">
                                            {activities.filter(a => a.type === 'status_change').length}
                                        </div>
                                    </div>
                                    <div className="bg-white dark:bg-gray-800 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                                        <div className="text-sm text-gray-500 dark:text-gray-400">المدفوعات</div>
                                        <div className="text-xl font-bold text-green-600 dark:text-green-400">
                                            {activities.filter(a => a.type === 'payment').length}
                                        </div>
                                    </div>
                                    <div className="bg-white dark:bg-gray-800 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                                        <div className="text-sm text-gray-500 dark:text-gray-400">آخر 7 أيام</div>
                                        <div className="text-xl font-bold text-purple-600 dark:text-purple-400">
                                            {activities.filter(a => {
                                                const activityDate = new Date(a.timestamp);
                                                const weekAgo = new Date();
                                                weekAgo.setDate(weekAgo.getDate() - 7);
                                                return activityDate > weekAgo;
                                            }).length}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 py-4">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                                يتم تحديث النشاطات تلقائياً عند حدوث تغييرات
                            </div>
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={loadActivities}
                                    disabled={loading}
                                    className="px-4 py-2 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
                                >
                                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                                    تحديث
                                </button>
                                <button
                                    onClick={onClose}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center gap-2"
                                >
                                    <X className="w-4 h-4" />
                                    إغلاق
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};