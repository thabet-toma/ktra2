import React, { useState } from 'react';
import { Deal, DealInstallment, User } from '@/types';
import {
    Lock, Unlock, DollarSign, CheckCircle2, Clock,
    ArrowRight, RefreshCw, Calendar, Download,
    Eye, ImageIcon, FileText, AlertCircle,
    X, Wallet, Banknote
} from 'lucide-react';
import { PaymentRegistration } from '@/components/forms/deal-parts/PaymentRegistration';

interface PaymentProgressProps {
    installments: DealInstallment[];
    deal: Partial<Deal>;
    currentUser: User;
    onPaymentOperation: (
        operation: "claim" | "swift" | "add" | "confirm" | "cancel",
        paymentType: string,
        data: any,
        paymentId?: string
    ) => void;
    onConfirmSupplier: (data: any) => void;
}

export const PaymentProgress: React.FC<PaymentProgressProps> = ({
    installments,
    deal,
    currentUser,
    onPaymentOperation,
    onConfirmSupplier
}) => {
    const [selectedInstallment, setSelectedInstallment] = useState<DealInstallment | null>(null);
    const [showPaymentModal, setShowPaymentModal] = useState(false);
    const [showDetailsModal, setShowDetailsModal] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    const openImageInPopup = (imageUrl: string) => {
        window.open(imageUrl, '_blank', 'width=800,height=600');
    };

    const downloadImage = (imageUrl: string, filename: string) => {
        const link = document.createElement('a');
        link.href = imageUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const getPaymentForInstallment = (installmentId: string) => {
        return deal.payments?.find(p => p.installmentId === installmentId);
    };

    const isInstallmentUnlocked = (installmentNumber: number): boolean => {
        if (installmentNumber === 1) return true;
        const previousInstallment = installments.find(i => i.installmentNumber === installmentNumber - 1);
        if (previousInstallment) {
            const previousPayment = getPaymentForInstallment(previousInstallment.id);
            return !!previousPayment?.bankSwiftImage || previousInstallment.status === 'paid';
        }
        return false;
    };

    const totalPaid = installments.reduce((sum, inst) => {
        const payment = getPaymentForInstallment(inst.id);
        if (inst.status === 'paid' || payment?.bankSwiftImage) return sum + inst.amount;
        return sum;
    }, 0);

    const grandTotal = deal.totalAmount || 0;
    const progressPercentage = grandTotal > 0 ? (totalPaid / grandTotal) * 100 : 0;

    const handleStartPayment = (installment: DealInstallment) => {
        const unlocked = isInstallmentUnlocked(installment.installmentNumber);
        const payment = getPaymentForInstallment(installment.id);
        const isFullyFinished = !!payment?.confirmedBySupplier;

        if (!unlocked) {
            alert("هذه الدفعة مقفلة، يجب إكمال الدفعة السابقة أولاً");
            return;
        }

        if (isFullyFinished) {
            setSelectedInstallment(installment);
            setShowDetailsModal(true);
            return;
        }

        setSelectedInstallment(installment);
        setShowPaymentModal(true);
    };

    const handleSaveClaim = (data: any) => {
        onPaymentOperation("claim", `دفعة_${data.installmentNumber}`, {
            ...data,
            installmentId: selectedInstallment?.id,
            installmentNumber: selectedInstallment?.installmentNumber
        });
        setShowPaymentModal(false);
        setRefreshKey(prev => prev + 1);
    };

    const handleSavePayment = (data: any) => {
        const payment = getPaymentForInstallment(selectedInstallment?.id || '');
        if (payment?.id) {
            onPaymentOperation("swift", `دفعة_${selectedInstallment?.installmentNumber}`, data, payment.id);
        }
        setShowPaymentModal(false);
        setRefreshKey(prev => prev + 1);
    };

    const handleConfirmSupplier = (data: any) => {
        const payment = getPaymentForInstallment(selectedInstallment?.id || '');
        if (payment?.id) {
            onConfirmSupplier({ ...data, paymentId: payment.id });
        }
        setShowPaymentModal(false);
        setRefreshKey(prev => prev + 1);
    };

    const handleRefresh = () => setRefreshKey(prev => prev + 1);

    const getInstallmentStatusText = (installment: DealInstallment) => {
        const payment = getPaymentForInstallment(installment.id);
        if (payment?.confirmedBySupplier) return 'مكتملة';
        if (installment.status === 'paid' || payment?.bankSwiftImage) return 'بانتظار التأكيد';
        if (payment?.alibabaClaimImage) return 'تم رفع المطالبة';
        return 'غير مدفوعة';
    };

    // --- Compact Details Modal ---
    const renderDetailsModal = () => {
        if (!selectedInstallment || !showDetailsModal) return null;
        const payment = getPaymentForInstallment(selectedInstallment.id);

        const formatDate = (dateString?: string) => {
            if (!dateString) return '-';
            return new Date(dateString).toLocaleDateString('en-GB', {
                year: 'numeric', month: 'numeric', day: 'numeric'
            });
        };

        return (
            <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-2 z-50">
                {/* استخدمنا max-w-5xl لعرض أكبر واستغلال العرض بدلاً من الطول */}
                <div className="bg-white dark:bg-[#0f172a] rounded-xl shadow-2xl w-full max-w-6xl overflow-hidden border border-gray-200 dark:border-gray-700 flex flex-col max-h-[95vh]">

                    {/* Header: Compact & Includes Exchange Rate */}
                    <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between bg-gray-50 dark:bg-[#1e293b]">
                        <div className="flex items-center gap-4">
                            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg text-blue-600 dark:text-blue-400">
                                <FileText className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 className="font-bold text-gray-900 dark:text-white text-lg leading-tight">
                                    تفاصيل الدفعة {selectedInstallment.installmentNumber}
                                </h3>
                                <div className="text-xs text-gray-500 flex gap-2">
                                    <span>بواسطة: {currentUser.name}</span>
                                    {payment?.paymentConfirmationDate && (
                                        <span className="text-green-600 dark:text-green-400 flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3" /> تم التأكيد
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Exchange Rate moved to Header */}
                        {payment && (
                            <div className="flex items-center gap-4 bg-white dark:bg-black/20 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700">
                                <span className="text-xs text-gray-500 dark:text-gray-400">سعر التحويل:</span>
                                <span className="font-mono font-bold text-blue-600 dark:text-blue-400 text-sm dir-ltr">
                                    1 USD = {payment.usdToIls || '-'} ILS
                                </span>
                            </div>
                        )}

                        <button
                            onClick={() => { setShowDetailsModal(false); setSelectedInstallment(null); }}
                            className="p-1.5 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 rounded-lg text-gray-400 transition-colors"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Content: Grid Layout to reduce height */}
                    <div className="p-4 overflow-y-auto custom-scrollbar bg-white dark:bg-[#0f172a]">
                        {payment ? (
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-full">

                                {/* Right Column: Financials & Info (30% width on large screens) */}
                                <div className="lg:col-span-4 flex flex-col gap-3">

                                    {/* Financial Card */}
                                    <div className="bg-gradient-to-br from-gray-50 to-white dark:from-[#1e293b] dark:to-[#1e293b] rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
                                        <h4 className="text-gray-900 dark:text-gray-200 font-bold text-sm mb-3 flex items-center gap-2">
                                            <Wallet className="w-4 h-4 text-emerald-500" />
                                            البيانات المالية
                                        </h4>
                                        <div className="space-y-2">
                                            <div className="flex justify-between items-center p-2 bg-white dark:bg-black/20 rounded-lg border border-gray-100 dark:border-gray-800">
                                                <span className="text-xs text-gray-500 dark:text-gray-400">مبلغ الدفعة</span>
                                                <span className="font-bold text-gray-900 dark:text-white">${payment.amount?.toLocaleString()}</span>
                                            </div>
                                            <div className="flex justify-between items-center p-2 bg-white dark:bg-black/20 rounded-lg border border-gray-100 dark:border-gray-800">
                                                <span className="text-xs text-gray-500 dark:text-gray-400">تكلفة الحوالة</span>
                                                <span className="font-bold text-amber-600 dark:text-amber-500">${payment.transferCost?.toLocaleString() || '0'}</span>
                                            </div>
                                            <div className="flex justify-between items-center p-2 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-100 dark:border-emerald-800">
                                                <span className="text-xs text-emerald-700 dark:text-emerald-400 font-bold">الإجمالي الكلي</span>
                                                <span className="font-bold text-emerald-700 dark:text-emerald-400 text-lg">
                                                    ${((payment.amount || 0) + (payment.transferCost || 0)).toLocaleString()}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Dates Card */}
                                    <div className="bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm flex-1">
                                        <h4 className="text-gray-900 dark:text-gray-200 font-bold text-sm mb-3 flex items-center gap-2">
                                            <Calendar className="w-4 h-4 text-blue-500" />
                                            التواريخ
                                        </h4>
                                        <div className="space-y-3 text-sm">
                                            <div className="flex justify-between border-b border-gray-100 dark:border-gray-700 pb-2 last:border-0 last:pb-0">
                                                <span className="text-gray-500 dark:text-gray-400 text-xs">تاريخ التحويل</span>
                                                <span className="font-mono font-medium text-gray-800 dark:text-gray-200">{formatDate(payment.paymentDate)}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-gray-100 dark:border-gray-700 pb-2 last:border-0 last:pb-0">
                                                <span className="text-gray-500 dark:text-gray-400 text-xs">تاريخ التأكيد</span>
                                                <span className="font-mono font-medium text-gray-800 dark:text-gray-200">{formatDate(payment.paymentConfirmationDate)}</span>
                                            </div>
                                        </div>

                                        {/* Compact Notes */}
                                        <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700">
                                            <span className="text-xs text-gray-400 block mb-1">الملاحظات:</span>
                                            <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-3 leading-relaxed">
                                                {payment.notes || payment.supplierNotes || "لا توجد ملاحظات."}
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Left Column: Documents (70% width) */}
                                <div className="lg:col-span-8 flex flex-col h-full">
                                    <h4 className="text-gray-900 dark:text-gray-200 font-bold text-sm mb-3 flex items-center gap-2">
                                        <ImageIcon className="w-4 h-4 text-purple-500" />
                                        المستندات المرفقة
                                    </h4>

                                    <div className="grid grid-cols-2 gap-3 h-full min-h-[250px]">
                                        {/* Claim Image */}
                                        <div className="relative group border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-gray-50 dark:bg-black/20 flex flex-col">
                                            <div className="absolute top-2 right-2 left-2 z-10 flex justify-between items-start opacity-0 group-hover:opacity-100 transition-opacity">
                                                <span className="bg-amber-100/90 text-amber-700 text-[10px] px-2 py-0.5 rounded backdrop-blur-sm font-bold shadow-sm">المطالبة (Claim)</span>
                                                <div className="flex gap-1">
                                                    <button onClick={() => downloadImage(payment.alibabaClaimImage || '', 'claim.jpg')} className="p-1.5 bg-white/90 text-gray-700 rounded hover:text-blue-600 shadow-sm"><Download className="w-3 h-3" /></button>
                                                    <button onClick={() => openImageInPopup(payment.alibabaClaimImage || '')} className="p-1.5 bg-white/90 text-gray-700 rounded hover:text-blue-600 shadow-sm"><Eye className="w-3 h-3" /></button>
                                                </div>
                                            </div>
                                            {payment.alibabaClaimImage ? (
                                                <div className="flex-1 flex items-center justify-center p-2 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')]">
                                                    <img
                                                        src={payment.alibabaClaimImage}
                                                        className="max-w-full max-h-[220px] object-contain rounded drop-shadow-md transition-transform duration-300 group-hover:scale-105"
                                                        onClick={() => openImageInPopup(payment.alibabaClaimImage!)}
                                                    />
                                                </div>
                                            ) : (
                                                <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
                                                    <ImageIcon className="w-8 h-8 mb-2 opacity-20" />
                                                    <span className="text-xs">لا توجد صورة</span>
                                                </div>
                                            )}
                                        </div>

                                        {/* Swift Image */}
                                        <div className="relative group border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-gray-50 dark:bg-black/20 flex flex-col">
                                            <div className="absolute top-2 right-2 left-2 z-10 flex justify-between items-start opacity-0 group-hover:opacity-100 transition-opacity">
                                                <span className="bg-blue-100/90 text-blue-700 text-[10px] px-2 py-0.5 rounded backdrop-blur-sm font-bold shadow-sm">السليب (Swift)</span>
                                                <div className="flex gap-1">
                                                    <button onClick={() => downloadImage(payment.bankSwiftImage || '', 'swift.jpg')} className="p-1.5 bg-white/90 text-gray-700 rounded hover:text-blue-600 shadow-sm"><Download className="w-3 h-3" /></button>
                                                    <button onClick={() => openImageInPopup(payment.bankSwiftImage || '')} className="p-1.5 bg-white/90 text-gray-700 rounded hover:text-blue-600 shadow-sm"><Eye className="w-3 h-3" /></button>
                                                </div>
                                            </div>
                                            {payment.bankSwiftImage ? (
                                                <div className="flex-1 flex items-center justify-center p-2 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')]">
                                                    <img
                                                        src={payment.bankSwiftImage}
                                                        className="max-w-full max-h-[220px] object-contain rounded drop-shadow-md transition-transform duration-300 group-hover:scale-105"
                                                        onClick={() => openImageInPopup(payment.bankSwiftImage!)}
                                                    />
                                                </div>
                                            ) : (
                                                <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
                                                    <ImageIcon className="w-8 h-8 mb-2 opacity-20" />
                                                    <span className="text-xs">لا توجد صورة</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-48 text-gray-400">
                                <AlertCircle className="w-10 h-10 mb-2 opacity-50" />
                                <p className="text-sm">لا توجد بيانات</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm" key={refreshKey}>
            {/* Header Area */}
            <div className="mb-6 border-b border-gray-100 dark:border-gray-700 pb-5">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-blue-600 rounded-xl text-white shadow-lg shadow-blue-500/20">
                            <Banknote className="w-6 h-6" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h3 className="font-bold text-gray-900 dark:text-white text-lg">
                                    دفعات الشحنة
                                </h3>
                                <button
                                    onClick={handleRefresh}
                                    className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full text-gray-400 transition-colors"
                                >
                                    <RefreshCw className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                                <span>المدفوع:</span>
                                <span className="text-blue-600 dark:text-blue-400 font-bold">${totalPaid.toLocaleString()}</span>
                                <span className="text-gray-300">|</span>
                                <span>المتبقي:</span>
                                <span className="text-red-500 font-bold">${(grandTotal - totalPaid).toLocaleString()}</span>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        <div className="text-right">
                            <span className="text-xs text-gray-500 dark:text-gray-400 block">نسبة الإنجاز</span>
                            <span className="text-lg font-bold text-gray-900 dark:text-white">{progressPercentage.toFixed(1)}%</span>
                        </div>
                        <div className="w-16 h-16 relative flex items-center justify-center">
                            <svg className="w-full h-full transform -rotate-90">
                                <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-gray-100 dark:text-gray-700" />
                                <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="4" fill="transparent" strokeDasharray={175.9} strokeDashoffset={175.9 - (progressPercentage / 100) * 175.9} className="text-blue-500 transition-all duration-1000 ease-out" />
                            </svg>
                        </div>
                    </div>
                </div>
            </div>

            {/* Installments List */}
            <div className="space-y-3">
                {installments.map((installment) => {
                    const unlocked = isInstallmentUnlocked(installment.installmentNumber);
                    const payment = getPaymentForInstallment(installment.id);
                    const hasSwift = !!payment?.bankSwiftImage || installment.status === 'paid';
                    const isFullyFinished = !!payment?.confirmedBySupplier;
                    const hasAnyData = hasSwift || !!payment?.alibabaClaimImage || isFullyFinished;

                    return (
                        <div
                            key={installment.id}
                            className={`
                                group relative p-4 rounded-xl border transition-all duration-200 
                                ${isFullyFinished
                                    ? 'bg-green-50/40 dark:bg-green-900/10 border-green-200 dark:border-green-800/30'
                                    : hasSwift
                                        ? 'bg-blue-50/40 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800/30'
                                        : unlocked
                                            ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-300'
                                            : 'bg-gray-50 dark:bg-gray-900 border-gray-100 dark:border-gray-800 opacity-60'
                                }
                            `}
                        >
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                <div className="flex items-center gap-4">
                                    <div className={`
                                        w-10 h-10 rounded-full flex items-center justify-center border shadow-sm
                                        ${isFullyFinished ? 'bg-green-100 border-green-200 text-green-600 dark:bg-green-900/30 dark:border-green-800 dark:text-green-400' :
                                            hasSwift ? 'bg-blue-100 border-blue-200 text-blue-600 dark:bg-blue-900/30 dark:border-blue-800 dark:text-blue-400' :
                                                unlocked ? 'bg-white border-gray-200 text-gray-500 dark:bg-gray-800 dark:border-gray-600' :
                                                    'bg-gray-100 border-gray-200 text-gray-400 dark:bg-gray-800 dark:border-gray-700'}
                                    `}>
                                        {isFullyFinished ? <CheckCircle2 className="w-5 h-5" /> :
                                            hasSwift ? <DollarSign className="w-5 h-5" /> :
                                                unlocked ? <span className="font-bold text-sm">{installment.installmentNumber}</span> :
                                                    <Lock className="w-4 h-4" />}
                                    </div>

                                    <div>
                                        <div className="flex items-center gap-2">
                                            <h4 className="font-bold text-gray-900 dark:text-white text-base">
                                                الدفعة {installment.installmentNumber}
                                            </h4>
                                            <span className="text-xs text-gray-500 dark:text-gray-400 font-normal bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">
                                                {installment.percentage}%
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-3 mt-1 text-sm">
                                            <span className="font-bold text-gray-800 dark:text-gray-200">${installment.amount.toLocaleString()}</span>
                                            <span className="text-gray-300 dark:text-gray-600">|</span>
                                            <span className={`text-xs ${isFullyFinished ? 'text-green-600' : hasSwift ? 'text-blue-600' : 'text-gray-500'}`}>
                                                {getInstallmentStatusText(installment)}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 pl-2">
                                    {hasAnyData && (
                                        <button
                                            onClick={() => { setSelectedInstallment(installment); setShowDetailsModal(true); }}
                                            className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                                        >
                                            <Eye className="w-5 h-5" />
                                        </button>
                                    )}

                                    <button
                                        onClick={() => handleStartPayment(installment)}
                                        disabled={!unlocked || isFullyFinished}
                                        className={`
                                            px-4 py-2 rounded-lg text-sm font-bold transition-all flex items-center gap-2
                                            ${isFullyFinished
                                                ? 'bg-transparent text-green-600 cursor-default'
                                                : hasSwift
                                                    ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm shadow-blue-500/30'
                                                    : unlocked
                                                        ? 'bg-gray-900 text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200'
                                                        : 'bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-gray-800 dark:text-gray-600'}
                                        `}
                                    >
                                        {isFullyFinished ? 'تمت بنجاح' : hasSwift ? 'تأكيد المورد' : 'إجراء الدفع'}
                                        {!isFullyFinished && unlocked && <ArrowRight className="w-3.5 h-3.5" />}
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Payment Forms Modal (No changes to logic, just wrapper) */}
            {showPaymentModal && selectedInstallment && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border border-gray-200 dark:border-gray-700">
                        <div className="p-6">
                            <div className="flex justify-between items-center mb-6">
                                <h3 className="font-bold text-xl text-gray-900 dark:text-white">تسجيل الدفعة {selectedInstallment.installmentNumber}</h3>
                                <button onClick={() => setShowPaymentModal(false)} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full text-gray-500">✕</button>
                            </div>
                            <PaymentRegistration
                                title={`الدفعة ${selectedInstallment.installmentNumber}`}
                                paymentType={`دفعة_${selectedInstallment.installmentNumber}`}
                                paymentData={getPaymentForInstallment(selectedInstallment.id)}
                                currentUser={currentUser}
                                dealId={deal.id}
                                dealStatus={deal.status}
                                deal={deal}
                                installmentId={selectedInstallment.id}
                                installmentAmount={selectedInstallment.amount}
                                onSaveClaim={handleSaveClaim}
                                onSavePayment={handleSavePayment}
                                onConfirmSupplier={handleConfirmSupplier}
                            />
                        </div>
                    </div>
                </div>
            )}

            {renderDetailsModal()}
        </div>
    );
};