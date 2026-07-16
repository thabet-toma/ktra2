import React, { useState } from 'react';
import { Deal, DealInstallment, DealPayment, User } from '@/types';
import { formatNumber } from '@/utils/formatNumber';
import {
    Lock, Unlock, DollarSign, CheckCircle2, Clock,
    ArrowRight, RefreshCw, Calendar, Download,
    Eye, ImageIcon, FileText, AlertCircle,
    X, Wallet, Banknote, BookOpen, Trash2,
} from 'lucide-react';
import { PaymentRegistration } from '@/components/forms/deal-parts/PaymentRegistration';
import { useToast } from '@/contexts/ToastContext';
import { useConfirm } from '@/contexts/ConfirmContext';
import {
    findPaymentForInstallmentId,
    pickBestDealPayment,
} from '@/utils/dealPaymentMatch';
import { isAwaitingSupplierConfirmation } from '@/utils/dealPaymentFlow';

function parseSqlJournalId(p: DealPayment | undefined): number | null {
    if (p == null) return null;
    const raw = p.journalId as number | string | undefined;
    if (raw === undefined || raw === null || raw === '') return null;
    const n = typeof raw === 'string' ? parseInt(String(raw).trim(), 10) : Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
}

interface PaymentProgressProps {
    installments: DealInstallment[];
    deal: Partial<Deal>;
    /** شحنة: عناوين «دفعات الشحنة» بدل صفقة الشراء */
    variant?: 'deal' | 'shipment';
    currentUser: User;
    onPaymentOperation: (
        operation:
            | "claim"
            | "swift"
            | "add"
            | "confirm"
            | "cancel"
            | "unpost"
            | "linkJournal",
        paymentType: string,
        data: any,
        paymentId?: string
    ) => void;
    onConfirmSupplier: (data: any) => void;
    /** فتح شاشة قيد اليومية (نفس مسار /accounting/journals/{id}) */
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
    /** إخفاء حذف الدفعة (مثلاً شحنة مسلّمة) */
    readOnly?: boolean;
}

export const PaymentProgress: React.FC<PaymentProgressProps> = ({
    installments,
    deal,
    variant = 'deal',
    currentUser,
    onPaymentOperation,
    onConfirmSupplier,
    onOpenAccountingJournal,
    readOnly = false,
}) => {
    const toast = useToast();
    const confirmDialog = useConfirm();
    const [selectedInstallment, setSelectedInstallment] = useState<DealInstallment | null>(null);
    const [showPaymentModal, setShowPaymentModal] = useState(false);
    const [showDetailsModal, setShowDetailsModal] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    const openImageInPopup = (imageUrl: string) => {
        window.open(imageUrl, '_blank', 'width=800,height=600');
    };

    const downloadImage = async (imageUrl: string, filename: string) => {
        try {
            const res = await fetch(imageUrl);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch {
            window.open(imageUrl, '_blank', 'noopener,noreferrer');
        }
    };

    /** نفس منطق البطاقات العلوية في DealForm: مجموع مبالغ كل صفوف الدفع */
    const paidAmountFromPayments =
        deal.payments?.reduce((s, p) => s + Number(p.amount || 0), 0) || 0;

    const getPaymentForInstallment = (installmentId: string) => {
        const found = findPaymentForInstallmentId(deal, installmentId);
        if (found) return found;
        if (
            installments.length === 1 &&
            (deal.payments?.length || 0) > 0
        ) {
            return pickBestDealPayment(deal.payments!);
        }
        return undefined;
    };

    /** يتوافق مع البطاقات العلوية: أي دفعة مسجّلة بمبلغ تُحسب مدفوعة للقسط */
    const countsAsPaidForProgress = (
        inst: DealInstallment,
        payment: ReturnType<typeof getPaymentForInstallment>
    ): boolean => {
        if (inst.status === 'paid') return true;
        if (!payment) return false;
        if (Number(payment.amount || 0) > 0) return true;
        if (payment.confirmedBySupplier) return true;
        if (payment.bankSwiftImage && String(payment.bankSwiftImage).trim()) return true;
        if (payment.isPosted) return true;
        if (payment.cashBoxWithdrawalAt && String(payment.cashBoxWithdrawalAt).trim())
            return true;
        return false;
    };

    const isInstallmentUnlocked = (installmentNumber: number): boolean => {
        if (installmentNumber === 1) return true;
        const previousInstallment = installments.find(i => i.installmentNumber === installmentNumber - 1);
        if (previousInstallment) {
            const previousPayment = getPaymentForInstallment(previousInstallment.id);
            return countsAsPaidForProgress(previousInstallment, previousPayment);
        }
        return false;
    };

    const grandTotal = deal.totalAmount || 0;
    /** إجمالي المعروض = مجموع payments (مثل البطاقات الخضراء/الصفراء)، لا يعتمد على ربط القسط فقط */
    const totalPaid = paidAmountFromPayments;
    const supplierAdvance = Math.max(0, Number(deal.supplierAdvance) || totalPaid - grandTotal);
    const amountOutstanding = Math.max(0, Number(deal.amountOutstanding) || grandTotal - totalPaid);
    const progressPercentage =
        grandTotal > 0 ? (totalPaid / grandTotal) * 100 : 0;
    const progressRingPercent = Math.min(100, progressPercentage);

    const handleStartPayment = (installment: DealInstallment) => {
        const unlocked = isInstallmentUnlocked(installment.installmentNumber);
        const payment = getPaymentForInstallment(installment.id);
        const isFullyFinished = !!payment?.confirmedBySupplier;

        if (!unlocked) {
            toast("هذه الدفعة مقفلة، يجب إكمال الدفعة السابقة أولاً", "info");
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
        const inst = selectedInstallment;
        if (!inst) return;
        let payment = getPaymentForInstallment(inst.id);
        if (
            payment &&
            payment.installmentNumber != null &&
            Number(payment.installmentNumber) !== Number(inst.installmentNumber)
        ) {
            payment = undefined;
        }
        onPaymentOperation(
            "swift",
            `دفعة_${inst.installmentNumber}`,
            {
                ...data,
                installmentId: inst.id,
                installmentNumber: inst.installmentNumber,
            },
            payment?.id
        );
        setShowPaymentModal(false);
        setRefreshKey(prev => prev + 1);
    };

    const handleConfirmSupplier = (data: any) => {
        const inst = selectedInstallment;
        if (!inst) return;
        let payment = getPaymentForInstallment(inst.id);
        if (
            payment &&
            payment.installmentNumber != null &&
            Number(payment.installmentNumber) !== Number(inst.installmentNumber)
        ) {
            payment = undefined;
        }
        if (payment?.id) {
            onConfirmSupplier({ ...data, paymentId: payment.id });
        } else {
            toast("لم يُعثر على دفعة تطابق هذا القسط. حدّث الصفحة (F5) ثم جرّب من سطر الدفعة الصحيحة.", "error");
        }
        setShowPaymentModal(false);
        setRefreshKey(prev => prev + 1);
    };

    const handleRefresh = () => setRefreshKey(prev => prev + 1);

    const openJournalForPayment = (payment: DealPayment | undefined) => {
        const jid = parseSqlJournalId(payment);
        if (jid == null) {
            toast("لا يوجد قيد يومية مرتبط بهذه الدفعة — يظهر رقم القيد بعد الترحيل المحاسبي.", "info");
            return;
        }
        const dealRef =
            variant === 'deal' && deal.id
                ? {
                      dealId: String(deal.id),
                      dealNumber: (deal.dealNumber || '').trim(),
                      displayName: [
                          deal.dealNumber,
                          (deal.dealDescription || deal.originalOfferNumber || '').trim(),
                      ]
                          .filter(Boolean)
                          .join(' — '),
                  }
                : undefined;
        if (onOpenAccountingJournal) {
            onOpenAccountingJournal(jid, dealRef);
        } else {
            const path = `/accounting/journals/${jid}`;
            window.open(path, '_blank', 'noopener,noreferrer');
        }
    };

    const getInstallmentStatusText = (installment: DealInstallment) => {
        const payment = getPaymentForInstallment(installment.id);
        if (payment?.confirmedBySupplier) return 'مكتملة';
        if (countsAsPaidForProgress(installment, payment) && !payment?.confirmedBySupplier) {
            if (payment?.bankSwiftImage && String(payment.bankSwiftImage).trim())
                return 'بانتظار التأكيد';
            if (payment?.isPosted) return 'مدفوعة (مرحّل)';
            if (
                payment?.cashBoxWithdrawalAt &&
                String(payment.cashBoxWithdrawalAt).trim()
            )
                return 'مدفوعة (صندوق)';
            if (installment.status === 'paid') return 'بانتظار التأكيد';
            if (Number(payment?.amount || 0) > 0) return 'مدفوعة (مسجّلة)';
        }
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
                <div className="aseel-bg-field dark:bg-[var(--color-surface)] rounded-xl shadow-2xl w-full max-w-6xl overflow-hidden border aseel-border-soft dark:aseel-border-soft flex flex-col max-h-[95vh]">

                    {/* Header: Compact & Includes Exchange Rate */}
                    <div className="px-5 py-3 border-b aseel-border-soft dark:aseel-border-soft flex items-center justify-between aseel-bg-panel dark:bg-[var(--color-surface-2)]">
                        <div className="flex items-center gap-4">
                            <div className="p-2 aseel-bg-accent-bg dark:aseel-bg-panel/30 rounded-lg aseel-text-accent dark:aseel-text-soft">
                                <FileText className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 className="font-bold aseel-text-ink dark:text-white text-lg leading-tight">
                                    تفاصيل الدفعة {selectedInstallment.installmentNumber}
                                </h3>
                                <div className="text-xs aseel-text-soft flex gap-2">
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
                            <div className="flex items-center gap-4 aseel-bg-field dark:bg-black/20 px-3 py-1.5 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                <span className="text-xs aseel-text-soft dark:aseel-text-soft">سعر التحويل:</span>
                                <span className="font-mono font-bold aseel-text-accent dark:aseel-text-soft text-sm dir-ltr">
                                    1 USD = {payment.usdToIls || '-'} ILS
                                </span>
                            </div>
                        )}

                        <div className="flex items-center gap-2 shrink-0">
                            {payment && parseSqlJournalId(payment) != null && (
                                <button
                                    type="button"
                                    onClick={() => openJournalForPayment(payment)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border aseel-border-soft aseel-bg-field aseel-text-ink dark:aseel-border-soft dark:aseel-bg-panel dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel transition-colors"
                                >
                                    <BookOpen className="w-4 h-4" />
                                    فتح القيد
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={() => { setShowDetailsModal(false); setSelectedInstallment(null); }}
                                className="p-1.5 hover:aseel-bg-panel hover:aseel-text-soft dark:hover:aseel-bg-panel/20 rounded-lg aseel-text-soft transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                    </div>

                    {/* Content: Grid Layout to reduce height */}
                    <div className="p-4 overflow-y-auto custom-scrollbar aseel-bg-field dark:bg-[var(--color-surface)]">
                        {payment ? (
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-full">

                                {/* Right Column: Financials & Info (30% width on large screens) */}
                                <div className="lg:col-span-4 flex flex-col gap-3">

                                    {/* Financial Card */}
                                    <div className="bg-gradient-to-br aseel-bg-panel to-white dark:from-[var(--color-surface-2)] dark:to-[var(--color-surface-2)] rounded-xl border aseel-border-soft dark:aseel-border-soft p-4 shadow-sm">
                                        <h4 className="aseel-text-ink dark:aseel-text-soft font-bold text-sm mb-3 flex items-center gap-2">
                                            <Wallet className="w-4 h-4 aseel-text-soft" />
                                            البيانات المالية
                                        </h4>
                                        <div className="space-y-2">
                                            <div className="flex justify-between items-center p-2 aseel-bg-field dark:bg-black/20 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                                <span className="text-xs aseel-text-soft dark:aseel-text-soft">مبلغ الدفعة</span>
                                                <span className="font-bold aseel-text-ink dark:text-white">${payment.amount?.toLocaleString()}</span>
                                            </div>
                                            <div className="flex justify-between items-center p-2 aseel-bg-field dark:bg-black/20 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                                <span className="text-xs aseel-text-soft dark:aseel-text-soft">تكلفة الحوالة</span>
                                                <span className="font-bold aseel-text-ink dark:aseel-text-soft">${payment.transferCost?.toLocaleString() || '0'}</span>
                                            </div>
                                            <div className="flex justify-between items-center p-2 aseel-bg-panel dark:aseel-bg-panel/20 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                                <span className="text-xs aseel-text-ink dark:aseel-text-soft font-bold">الإجمالي الكلي</span>
                                                <span className="font-bold aseel-text-ink dark:aseel-text-soft text-lg">
                                                    ${((payment.amount || 0) + (payment.transferCost || 0)).toLocaleString()}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Dates Card */}
                                    <div className="aseel-bg-field dark:bg-[var(--color-surface-2)] rounded-xl border aseel-border-soft dark:aseel-border-soft p-4 shadow-sm flex-1">
                                        <h4 className="aseel-text-ink dark:aseel-text-soft font-bold text-sm mb-3 flex items-center gap-2">
                                            <Calendar className="w-4 h-4 aseel-text-soft" />
                                            التواريخ
                                        </h4>
                                        <div className="space-y-3 text-sm">
                                            <div className="flex justify-between border-b aseel-border-soft dark:aseel-border-soft pb-2 last:border-0 last:pb-0">
                                                <span className="aseel-text-soft dark:aseel-text-soft text-xs">تاريخ التحويل</span>
                                                <span className="font-mono font-medium aseel-text-ink dark:aseel-text-soft">{formatDate(payment.paymentDate)}</span>
                                            </div>
                                            <div className="flex justify-between border-b aseel-border-soft dark:aseel-border-soft pb-2 last:border-0 last:pb-0">
                                                <span className="aseel-text-soft dark:aseel-text-soft text-xs">تاريخ التأكيد</span>
                                                <span className="font-mono font-medium aseel-text-ink dark:aseel-text-soft">{formatDate(payment.paymentConfirmationDate)}</span>
                                            </div>
                                        </div>

                                        {/* Compact Notes */}
                                        <div className="mt-4 pt-3 border-t aseel-border-soft dark:aseel-border-soft">
                                            <span className="text-xs aseel-text-soft block mb-1">الملاحظات:</span>
                                            <p className="text-xs aseel-text-soft dark:aseel-text-soft line-clamp-3 leading-relaxed">
                                                {payment.notes || payment.supplierNotes || "لا توجد ملاحظات."}
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Left Column: Documents (70% width) */}
                                <div className="lg:col-span-8 flex flex-col h-full">
                                    <h4 className="aseel-text-ink dark:aseel-text-soft font-bold text-sm mb-3 flex items-center gap-2">
                                        <ImageIcon className="w-4 h-4 text-[var(--color-primary)]" />
                                        المستندات المرفقة
                                    </h4>

                                    <div className="grid grid-cols-2 gap-3 h-full min-h-[250px]">
                                        {/* Claim Image */}
                                        <div className="relative group border aseel-border-soft dark:aseel-border-soft rounded-xl overflow-hidden aseel-bg-panel dark:bg-black/20 flex flex-col">
                                            <div className="absolute top-2 right-2 left-2 z-10 flex justify-between items-start opacity-0 group-hover:opacity-100 transition-opacity">
                                                <span className="aseel-bg-grid-head/90 aseel-text-ink text-[10px] px-2 py-0.5 rounded backdrop-blur-sm font-bold shadow-sm dark:aseel-bg-panel/90 dark:aseel-text-soft">المطالبة (Claim)</span>
                                                <div className="flex gap-1">
                                                    <button onClick={() => downloadImage(payment.alibabaClaimImage || '', 'claim.jpg')} className="p-1.5 aseel-bg-field/90 aseel-text-ink rounded hover:aseel-text-accent shadow-sm"><Download className="w-3 h-3" /></button>
                                                    <button onClick={() => openImageInPopup(payment.alibabaClaimImage || '')} className="p-1.5 aseel-bg-field/90 aseel-text-ink rounded hover:aseel-text-accent shadow-sm"><Eye className="w-3 h-3" /></button>
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
                                                <div className="flex-1 flex flex-col items-center justify-center aseel-text-soft">
                                                    <ImageIcon className="w-8 h-8 mb-2 opacity-20" />
                                                    <span className="text-xs">لا توجد صورة</span>
                                                </div>
                                            )}
                                        </div>

                                        {/* Swift Image */}
                                        <div className="relative group border aseel-border-soft dark:aseel-border-soft rounded-xl overflow-hidden aseel-bg-panel dark:bg-black/20 flex flex-col">
                                            <div className="absolute top-2 right-2 left-2 z-10 flex justify-between items-start opacity-0 group-hover:opacity-100 transition-opacity">
                                                <span className="aseel-bg-accent-bg/90 aseel-text-accent text-[10px] px-2 py-0.5 rounded backdrop-blur-sm font-bold shadow-sm">السليب (Swift)</span>
                                                <div className="flex gap-1">
                                                    <button onClick={() => downloadImage(payment.bankSwiftImage || '', 'swift.jpg')} className="p-1.5 aseel-bg-field/90 aseel-text-ink rounded hover:aseel-text-accent shadow-sm"><Download className="w-3 h-3" /></button>
                                                    <button onClick={() => openImageInPopup(payment.bankSwiftImage || '')} className="p-1.5 aseel-bg-field/90 aseel-text-ink rounded hover:aseel-text-accent shadow-sm"><Eye className="w-3 h-3" /></button>
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
                                                <div className="flex-1 flex flex-col items-center justify-center aseel-text-soft">
                                                    <ImageIcon className="w-8 h-8 mb-2 opacity-20" />
                                                    <span className="text-xs">لا توجد صورة</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-48 aseel-text-soft">
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
        <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl border aseel-border-soft dark:aseel-border-soft p-5 shadow-sm" key={refreshKey}>
            {/* Header Area */}
            <div className="mb-6 border-b aseel-border-soft dark:aseel-border-soft pb-5">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <div className="p-3 aseel-bg-accent rounded-xl text-white shadow-lg shadow-blue-500/20">
                            <Banknote className="w-6 h-6" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h3 className="font-bold aseel-text-ink dark:text-white text-lg">
                                    {variant === 'shipment' ? 'دفعات الشحنة' : 'دفعات الصفقة'}
                                </h3>
                                <button
                                    onClick={handleRefresh}
                                    className="p-1.5 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-full aseel-text-soft transition-colors"
                                >
                                    <RefreshCw className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            <div className="flex items-center gap-2 text-sm aseel-text-soft dark:aseel-text-soft">
                                <span>المدفوع:</span>
                                <span className="aseel-text-accent dark:aseel-text-soft font-bold">${totalPaid.toLocaleString()}</span>
                                <span className="aseel-text-soft">|</span>
                                <span>{supplierAdvance > 0 ? "رصيد لصالحك عند المورد:" : "المتبقي:"}</span>
                                <span className="aseel-text-soft font-bold">
                                    ${supplierAdvance > 0 ? supplierAdvance.toLocaleString() : amountOutstanding.toLocaleString()}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        <div className="text-right">
                            <span className="text-xs aseel-text-soft dark:aseel-text-soft block">نسبة الإنجاز</span>
                            <span className="text-lg font-bold aseel-text-ink dark:text-white">{formatNumber(progressPercentage, { maxDecimals: 1 })}%</span>
                        </div>
                        <div className="w-16 h-16 relative flex items-center justify-center">
                            <svg className="w-full h-full transform -rotate-90">
                                <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="4" fill="transparent" className="aseel-text-soft dark:aseel-text-ink" />
                                <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="4" fill="transparent" strokeDasharray={175.9} strokeDashoffset={175.9 - (progressRingPercent / 100) * 175.9} className="aseel-text-soft transition-all duration-1000 ease-out" />
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
                    const hasPaidProgress = countsAsPaidForProgress(installment, payment);
                    const awaitingSupplier = isAwaitingSupplierConfirmation(payment);
                    const isFullyFinished = !!payment?.confirmedBySupplier;
                    const hasAnyData = hasPaidProgress || !!payment?.alibabaClaimImage || isFullyFinished;
                    const paymentSqlId =
                        payment && /^\d+$/.test(String(payment.id).trim())
                            ? String(payment.id).trim()
                            : "";
                    const canDeleteFromRecord =
                        !readOnly &&
                        paymentSqlId &&
                        payment &&
                        !payment.isPosted;

                    return (
                        <div
                            key={installment.id}
                            className={`
                                group relative p-4 rounded-xl border transition-all duration-200 
                                ${isFullyFinished
                                    ? 'bg-green-50/40 dark:bg-green-900/10 aseel-border-soft dark:border-green-800/30'
                                    : hasPaidProgress
                                        ? 'aseel-bg-accent-bg/40 dark:aseel-bg-panel/10 aseel-border-accent dark:aseel-border-soft/30'
                                        : unlocked
                                            ? 'aseel-bg-field dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft hover:aseel-border-soft'
                                            : 'aseel-bg-panel dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft opacity-60'
                                }
                            `}
                        >
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                <div className="flex items-center gap-4">
                                    <div className={`
                                        w-10 h-10 rounded-full flex items-center justify-center border shadow-sm
                                        ${isFullyFinished ? 'bg-green-100 aseel-border-soft text-green-600 dark:bg-green-900/30 dark:border-green-800 dark:text-green-400' :
                                            hasPaidProgress ? 'aseel-bg-accent-bg aseel-border-accent aseel-text-accent dark:aseel-bg-panel/30 dark:aseel-border-soft dark:aseel-text-soft' :
                                                unlocked ? 'aseel-bg-field aseel-border-soft aseel-text-soft dark:aseel-bg-panel dark:aseel-border-soft' :
                                                    'aseel-bg-panel aseel-border-soft aseel-text-soft dark:aseel-bg-panel dark:aseel-border-soft'}
                                    `}>
                                        {isFullyFinished ? <CheckCircle2 className="w-5 h-5" /> :
                                            hasPaidProgress ? <DollarSign className="w-5 h-5" /> :
                                                unlocked ? <span className="font-bold text-sm">{installment.installmentNumber}</span> :
                                                    <Lock className="w-4 h-4" />}
                                    </div>

                                    <div>
                                        <div className="flex items-center gap-2">
                                            <h4 className="font-bold aseel-text-ink dark:text-white text-base">
                                                الدفعة {installment.installmentNumber}
                                            </h4>
                                            <span className="text-xs aseel-text-soft dark:aseel-text-soft font-normal aseel-bg-panel dark:aseel-bg-panel px-2 py-0.5 rounded-full">
                                                {installment.percentage}%
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-3 mt-1 text-sm">
                                            <span className="font-bold aseel-text-ink dark:aseel-text-soft">${installment.amount.toLocaleString()}</span>
                                            <span className="aseel-text-soft dark:aseel-text-soft">|</span>
                                            <span className={`text-xs ${isFullyFinished ? 'text-green-600' : hasPaidProgress ? 'aseel-text-accent' : 'aseel-text-soft'}`}>
                                                {getInstallmentStatusText(installment)}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 pl-2 flex-wrap sm:flex-nowrap justify-end">
                                    {parseSqlJournalId(payment) != null && (
                                        <button
                                            type="button"
                                            title="فتح القيد في المحاسبة"
                                            onClick={() => openJournalForPayment(payment)}
                                            className="p-2 aseel-text-soft hover:text-[var(--color-primary-hover)] hover:bg-[var(--color-primary-hover)] dark:hover:bg-[var(--color-primary-hover)]/20 rounded-lg transition-colors"
                                        >
                                            <BookOpen className="w-5 h-5" />
                                        </button>
                                    )}
                                    {payment &&
                                        parseSqlJournalId(payment) == null &&
                                        !payment.isPosted &&
                                        /^\d+$/.test(String(payment.id).trim()) &&
                                        (hasPaidProgress ||
                                            isFullyFinished ||
                                            payment.confirmedBySupplier) && (
                                        <button
                                            type="button"
                                            title="إن أنشأت القيد يدوياً في المحاسبة ولم يظهر رابط الدفتر — أدخل رقم القيد"
                                            onClick={() => {
                                                const raw = window.prompt(
                                                    "رقم قيد اليومية المرحّل (Journal ID) من شاشة المحاسبة:",
                                                    ""
                                                );
                                                if (raw == null || String(raw).trim() === "") return;
                                                const n = parseInt(String(raw).trim(), 10);
                                                if (!Number.isFinite(n) || n <= 0) {
                                                    toast("رقم غير صالح.", "error");
                                                    return;
                                                }
                                                onPaymentOperation(
                                                    "linkJournal",
                                                    `دفعة_${installment.installmentNumber}`,
                                                    { journalId: n },
                                                    String(payment.id)
                                                );
                                                setRefreshKey((k) => k + 1);
                                            }}
                                            className="shrink-0 rounded-md border aseel-border-soft aseel-bg-field px-2 py-1.5 text-xs font-semibold aseel-text-ink hover:aseel-bg-panel dark:aseel-border-soft dark:aseel-bg-panel dark:aseel-text-soft dark:hover:aseel-bg-panel"
                                        >
                                            ربط قيد
                                        </button>
                                    )}
                                    {hasAnyData && (
                                        <button
                                            type="button"
                                            title="تفاصيل الدفعة والمستندات"
                                            onClick={() => { setSelectedInstallment(installment); setShowDetailsModal(true); }}
                                            className="p-2 aseel-text-soft hover:aseel-text-accent hover:aseel-bg-accent-bg dark:hover:aseel-bg-panel/20 rounded-lg transition-colors"
                                        >
                                            <Eye className="w-5 h-5" />
                                        </button>
                                    )}

                                    {canDeleteFromRecord && (
                                        <button
                                            type="button"
                                            title={
                                                variant === "shipment"
                                                    ? "حذف الدفعة من سجل الشحنة (غير مسموح إن وُجد قيد مرحّل)"
                                                    : "حذف الدفعة من السجل (غير مسموح إن وُجد قيد مرحّل)"
                                            }
                                            onClick={async () => {
                                                const ok = await confirmDialog({
                                                    title: "حذف الدفعة",
                                                    message: `حذف «الدفعة ${installment.installmentNumber}» بمبلغ $${formatNumber(
                                                        Number(payment?.amount || 0), { maxDecimals: 2 }
                                                    )} من السجل؟`,
                                                });
                                                if (!ok) return;
                                                onPaymentOperation(
                                                    "cancel",
                                                    `دفعة_${installment.installmentNumber}`,
                                                    {},
                                                    paymentSqlId
                                                );
                                                setRefreshKey((k) => k + 1);
                                            }}
                                            className="p-2 aseel-text-soft hover:aseel-text-state hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 rounded-lg transition-colors"
                                        >
                                            <Trash2 className="w-5 h-5" />
                                        </button>
                                    )}

                                    <button
                                        onClick={() => handleStartPayment(installment)}
                                        disabled={!unlocked || isFullyFinished}
                                        className={`
                                            px-4 py-2 rounded-lg text-sm font-bold transition-all flex items-center gap-2
                                            ${isFullyFinished
                                                ? 'bg-transparent text-green-600 cursor-default'
                                                : awaitingSupplier
                                                    ? 'aseel-bg-accent text-white hover:aseel-bg-accent shadow-sm shadow-blue-500/30'
                                                    : unlocked
                                                        ? 'aseel-bg-panel text-white hover:aseel-bg-panel dark:aseel-bg-field dark:text-black dark:hover:aseel-bg-grid-head'
                                                        : 'aseel-bg-panel aseel-text-soft cursor-not-allowed dark:aseel-bg-panel dark:aseel-text-soft'}
                                        `}
                                    >
                                        {isFullyFinished ? 'تمت بنجاح' : awaitingSupplier ? 'تأكيد المورد' : 'إجراء الدفع'}
                                        {!isFullyFinished && unlocked && <ArrowRight className="w-3.5 h-3.5" />}
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Payment Forms Modal (No changes to logic, just wrapper) */}
            {showPaymentModal && selectedInstallment && (() => {
                const modalPayment = getPaymentForInstallment(selectedInstallment.id);
                const confirmOnlyModal = isAwaitingSupplierConfirmation(modalPayment);
                return (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border aseel-border-soft dark:aseel-border-soft">
                        <div className="p-6">
                            <div className="flex justify-between items-center mb-6">
                                <h3 className="font-bold text-xl aseel-text-ink dark:text-white">
                                    {confirmOnlyModal
                                        ? `تأكيد المورد — الدفعة ${selectedInstallment.installmentNumber}`
                                        : `تسجيل الدفعة ${selectedInstallment.installmentNumber}`}
                                </h3>
                                <button onClick={() => setShowPaymentModal(false)} className="p-2 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-full aseel-text-soft">✕</button>
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
                );
            })()}

            {renderDetailsModal()}
        </div>
    );
};
