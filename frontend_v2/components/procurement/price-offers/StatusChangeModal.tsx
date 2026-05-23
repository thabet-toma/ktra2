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
            case 'initial': return <Clock className="w-5 h-5 aseel-text-soft" />;
            case 'pending_info': return <AlertCircle className="w-5 h-5 aseel-text-soft" />;
            case 'under_discussion': return <MessageSquare className="w-5 h-5 aseel-text-soft" />;
            case 'approved_for_shipping': return <CheckCircle className="w-5 h-5 text-green-500" />;
            case 'rejected': return <X className="w-5 h-5 aseel-text-soft" />;
            default: return <AlertCircle className="w-5 h-5 aseel-text-soft" />;
        }
    };

    const getStatusColor = (status: PriceOfferStatus) => {
        switch (status) {
            case 'initial': return 'aseel-text-soft aseel-bg-panel aseel-border-soft';
            case 'pending_info': return 'aseel-text-ink aseel-bg-panel aseel-border-soft';
            case 'under_discussion': return 'aseel-text-accent aseel-bg-accent-bg aseel-border-accent';
            case 'approved_for_shipping': return 'text-green-700 bg-green-50 aseel-border-soft';
            case 'rejected': return 'aseel-text-state aseel-bg-panel aseel-border-soft';
            default: return 'aseel-text-soft aseel-bg-panel aseel-border-soft';
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-2xl w-full max-w-md overflow-hidden border aseel-border-soft dark:aseel-border-soft">
                <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center aseel-bg-panel dark:aseel-bg-panel/50">
                    <h3 className="font-bold aseel-text-ink dark:text-white flex items-center gap-2">
                        <AlertCircle className="w-5 h-5 aseel-text-soft" />
                        تغيير حالة العرض
                    </h3>
                    <button
                        onClick={onClose}
                        className="aseel-text-soft hover:aseel-text-ink dark:aseel-text-soft dark:hover:aseel-text-soft transition-colors"
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
                            <div className="text-sm font-medium aseel-text-ink dark:text-white">
                                {statusLabels[currentStatus]}
                            </div>
                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">الحالية</div>
                        </div>

                        <div className="flex-1 flex items-center justify-center">
                            <div className="w-16 h-1 aseel-bg-grid-head dark:aseel-bg-panel"></div>
                            <div className="mx-4 p-2 aseel-bg-accent-bg dark:aseel-bg-panel/30 rounded-full">
                                <AlertCircle className="w-6 h-6 aseel-text-soft" />
                            </div>
                            <div className="w-16 h-1 aseel-bg-grid-head dark:aseel-bg-panel"></div>
                        </div>

                        <div className="text-center">
                            <div className={`flex items-center justify-center w-14 h-14 rounded-full ${getStatusColor(newStatus)} border-2 mb-2`}>
                                {getStatusIcon(newStatus)}
                            </div>
                            <div className="text-sm font-bold aseel-text-accent dark:aseel-text-soft">
                                {statusLabels[newStatus]}
                            </div>
                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">الجديدة</div>
                        </div>
                    </div>

                    {/* Informational Message */}
                    <div className="aseel-bg-accent-bg dark:aseel-bg-panel/20 p-4 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                        <div className="flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 aseel-text-soft mt-0.5 flex-shrink-0" />
                            <div>
                                <p className="text-sm aseel-text-ink dark:aseel-text-soft">
                                    أنت على وشك تغيير حالة هذا العرض من <span className="font-bold">{statusLabels[currentStatus]}</span> إلى <span className="font-bold aseel-text-accent dark:aseel-text-soft">{statusLabels[newStatus]}</span>.
                                </p>
                                <p className="text-sm aseel-text-soft dark:aseel-text-soft mt-1">
                                    سيتم تسجيل هذا التغيير في الملاحظات الداخلية تلقائياً.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-4 border-t aseel-border-soft dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel/50 flex gap-3 justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 aseel-text-ink dark:aseel-text-soft hover:aseel-bg-grid-head dark:hover:aseel-bg-panel rounded-lg transition-colors"
                        disabled={saving}
                    >
                        إلغاء
                    </button>
                    <button
                        onClick={() => onConfirm(newStatus)} // فقط تأكيد التغيير بدون notes
                        disabled={saving}
                        className="px-4 py-2 aseel-bg-accent hover:aseel-bg-accent dark:aseel-bg-accent-bg dark:hover:aseel-bg-accent text-white rounded-lg flex items-center gap-2 font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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