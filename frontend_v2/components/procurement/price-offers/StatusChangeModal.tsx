import React, { useState } from 'react';
import { PriceOfferStatus } from '../../../types';
import { X, Save, AlertCircle, CheckCircle, Clock, MessageSquare } from 'lucide-react';

interface StatusChangeModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (status: PriceOfferStatus) => void; // تم إزالة notes
    currentStatus: PriceOfferStatus;
    newStatus: PriceOfferStatus;
    saving?: boolean;
}

export const StatusChangeModal: React.FC<StatusChangeModalProps> = ({
    isOpen,
    onClose,
    onConfirm,
    currentStatus,
    newStatus,
    saving = false
}) => {
    if (!isOpen) return null;

    const statusLabels: Record<PriceOfferStatus, string> = {
        initial: 'أولية',
        pending_info: 'بانتظار المعلومات',
        under_discussion: 'تحت المناقشة',
        approved_for_shipping: 'معتمدة للشراء',
        rejected: 'مرفوضة'
    };

    const getStatusIcon = (status: PriceOfferStatus) => {
        switch (status) {
            case 'initial': return <Clock className="w-5 h-5 text-gray-500" />;
            case 'pending_info': return <AlertCircle className="w-5 h-5 text-yellow-500" />;
            case 'under_discussion': return <MessageSquare className="w-5 h-5 text-blue-500" />;
            case 'approved_for_shipping': return <CheckCircle className="w-5 h-5 text-green-500" />;
            case 'rejected': return <X className="w-5 h-5 text-red-500" />;
            default: return <AlertCircle className="w-5 h-5 text-gray-500" />;
        }
    };

    const getStatusColor = (status: PriceOfferStatus) => {
        switch (status) {
            case 'initial': return 'text-gray-600 bg-gray-100 border-gray-300';
            case 'pending_info': return 'text-yellow-700 bg-yellow-50 border-yellow-200';
            case 'under_discussion': return 'text-blue-700 bg-blue-50 border-blue-200';
            case 'approved_for_shipping': return 'text-green-700 bg-green-50 border-green-200';
            case 'rejected': return 'text-red-700 bg-red-50 border-red-200';
            default: return 'text-gray-600 bg-gray-100 border-gray-300';
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md overflow-hidden border border-gray-200 dark:border-gray-700">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-900/50">
                    <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        <AlertCircle className="w-5 h-5 text-blue-500" />
                        تغيير حالة العرض
                    </h3>
                    <button
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-6 space-y-6">
                    {/* Status Transition Visualization */}
                    <div className="flex items-center justify-between">
                        <div className="text-center">
                            <div className={`flex items-center justify-center w-14 h-14 rounded-full ${getStatusColor(currentStatus)} border-2 mb-2`}>
                                {getStatusIcon(currentStatus)}
                            </div>
                            <div className="text-sm font-medium text-gray-900 dark:text-white">
                                {statusLabels[currentStatus]}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">الحالية</div>
                        </div>

                        <div className="flex-1 flex items-center justify-center">
                            <div className="w-16 h-1 bg-gray-300 dark:bg-gray-600"></div>
                            <div className="mx-4 p-2 bg-blue-100 dark:bg-blue-900/30 rounded-full">
                                <AlertCircle className="w-6 h-6 text-blue-500" />
                            </div>
                            <div className="w-16 h-1 bg-gray-300 dark:bg-gray-600"></div>
                        </div>

                        <div className="text-center">
                            <div className={`flex items-center justify-center w-14 h-14 rounded-full ${getStatusColor(newStatus)} border-2 mb-2`}>
                                {getStatusIcon(newStatus)}
                            </div>
                            <div className="text-sm font-bold text-blue-600 dark:text-blue-400">
                                {statusLabels[newStatus]}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">الجديدة</div>
                        </div>
                    </div>

                    {/* Informational Message */}
                    <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border border-blue-100 dark:border-blue-800">
                        <div className="flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                            <div>
                                <p className="text-sm text-gray-700 dark:text-gray-300">
                                    أنت على وشك تغيير حالة هذا العرض من <span className="font-bold">{statusLabels[currentStatus]}</span> إلى <span className="font-bold text-blue-600 dark:text-blue-400">{statusLabels[newStatus]}</span>.
                                </p>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                    سيتم تسجيل هذا التغيير في الملاحظات الداخلية تلقائياً.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex gap-3 justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        disabled={saving}
                    >
                        إلغاء
                    </button>
                    <button
                        onClick={() => onConfirm(newStatus)} // فقط تأكيد التغيير بدون notes
                        disabled={saving}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded-lg flex items-center gap-2 font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {saving ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                جاري التغيير...
                            </>
                        ) : (
                            <>
                                <CheckCircle className="w-4 h-4" />
                                تأكيد التغيير
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};