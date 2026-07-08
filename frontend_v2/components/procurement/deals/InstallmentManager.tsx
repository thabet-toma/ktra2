import React, { useState, useEffect } from 'react';
import { DealInstallment } from '@/types';
import { findPaymentForInstallment } from '@/utils/dealPaymentMatch';
import { formatNumber } from '@/utils/formatNumber';
import { Plus, Trash2, Calculator, CheckCircle2, AlertCircle, Lock, DollarSign, Percent, Sparkles } from 'lucide-react';

/** من صفين فما فوق: الصفوف 1…ن−1 يحرّرها المستخدم، الأخير = باقي الإجمالي وباقي 100% */
export function balanceLastInstallment(
    rows: DealInstallment[],
    grandTotal: number
): DealInstallment[] {
    if (rows.length < 2) {
        return rows.map((r, i) => ({ ...r, installmentNumber: i + 1 }));
    }
    const out = rows.map((r) => ({ ...r }));
    const lastI = out.length - 1;
    let sumAmt = 0;
    let sumPct = 0;
    for (let i = 0; i < lastI; i++) {
        const pct = Number(out[i].percentage || 0);
        sumPct += pct;
        const amt = Number(((pct / 100) * grandTotal).toFixed(2));
        out[i] = { ...out[i], amount: amt };
        sumAmt += amt;
    }
    const lastPct = Math.max(0, Number((100 - sumPct).toFixed(2)));
    const lastAmt = Math.max(0, Number((grandTotal - sumAmt).toFixed(2)));
    out[lastI] = {
        ...out[lastI],
        percentage: lastPct,
        amount: lastAmt,
    };
    return out.map((r, i) => ({ ...r, installmentNumber: i + 1 }));
}

interface InstallmentManagerProps {
    installments: DealInstallment[];
    grandTotal: number;
    onUpdateInstallments: (installments: DealInstallment[]) => void;
    validationError: string;
    installmentPlanEnabled: boolean;
    onTogglePlan: (enabled: boolean) => void;
    deal?: any;
    readOnly?: boolean;
    /** شحن: جدول دفعات نشط تلقائياً عند وجود إجمالي — بدون مفتاح تفعيل */
    variant?: 'deal' | 'shipment';
}

export const InstallmentManager: React.FC<InstallmentManagerProps> = ({
    installments: propInstallments,
    grandTotal,
    onUpdateInstallments,
    installmentPlanEnabled,
    onTogglePlan,
    deal = {} as any,
    readOnly = false,
    variant = 'deal',
}) => {
    const [numInstallments, setNumInstallments] = useState(propInstallments.length || 1);

    const getEffectiveInstallments = (): DealInstallment[] => {
        if (deal?.installments && deal.installments.length > 0) return deal.installments;
        return propInstallments;
    };

    const effectiveInstallments = getEffectiveInstallments();

    const isShipmentFinance = variant === 'shipment';
    const planActive = isShipmentFinance
        ? (installmentPlanEnabled || grandTotal > 0.005 || effectiveInstallments.length > 0)
        : installmentPlanEnabled;

    const checkIfPaymentsStarted = (): boolean => {
        const hasConfirmedPayments = deal?.payments?.some(
            (p: any) =>
                p.confirmedBySupplier ||
                p.bankSwiftImage ||
                Number(p?.amount || 0) > 0
        );
        const hasPaidInstallments = effectiveInstallments.some(inst => inst.status === 'paid');
        return hasConfirmedPayments || hasPaidInstallments;
    };

    const isLocked = checkIfPaymentsStarted() || readOnly;

    // تهيئة أولية — للشحنة: إنشاء دفعة 100% تلقائياً عند وجود إجمالي دون ضغط «تفعيل»
    useEffect(() => {
        const active = isShipmentFinance
            ? (installmentPlanEnabled || grandTotal > 0.005 || propInstallments.length > 0)
            : installmentPlanEnabled;

        if (!active) {
            if (!isShipmentFinance && propInstallments.length > 0) {
                onUpdateInstallments([]);
            }
            return;
        }
        if (propInstallments.length === 0 && grandTotal > 0.005) {
            const defaultInstallment: DealInstallment = {
                id: crypto.randomUUID(),
                installmentNumber: 1,
                percentage: 100,
                amount: Number(grandTotal.toFixed(2)),
                status: 'unpaid',
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
            };
            onUpdateInstallments([defaultInstallment]);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onUpdateInstallments من الأب؛ إدراجه يسبب حلقة
    }, [isShipmentFinance, installmentPlanEnabled, grandTotal, propInstallments.length]);

    // عند تغيّر إجمالي الصفقة/الشحنة مع عدة أقساط: إعادة حساب القسط الأخير مع الإبقاء على نسب الدفعات السابقة
    useEffect(() => {
        if (!planActive || isLocked || propInstallments.length < 2 || grandTotal < 0) return;
        const balanced = balanceLastInstallment(
            propInstallments.map((x) => ({ ...x })),
            grandTotal
        );
        const li = balanced.length - 1;
        const a = propInstallments[li];
        const b = balanced[li];
        const amtDiff = Math.abs(Number(a?.amount || 0) - Number(b?.amount || 0));
        const pctDiff = Math.abs(Number(a?.percentage || 0) - Number(b?.percentage || 0));
        if (amtDiff > 0.02 || pctDiff > 0.08) {
            onUpdateInstallments(balanced);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [grandTotal, propInstallments.length, planActive, isLocked]);

    // توليد دفعات جديدة — الأخير يُكمِّل تلقائياً عند العدد ≥ 2
    const generateInstallments = (count: number) => {
        if (!planActive || isLocked) return;
        setNumInstallments(count);
        if (count < 2) {
            onUpdateInstallments([
                {
                    id: crypto.randomUUID(),
                    installmentNumber: 1,
                    percentage: 100,
                    amount: Number(grandTotal.toFixed(2)),
                    status: 'unpaid',
                    createdAt: new Date().toISOString(),
                    updatedAt: new Date().toISOString(),
                },
            ]);
            return;
        }
        const equalPct = Number((100 / count).toFixed(2));
        const base: DealInstallment[] = [];
        for (let i = 0; i < count; i++) {
            base.push({
                id: crypto.randomUUID(),
                installmentNumber: i + 1,
                percentage: i < count - 1 ? equalPct : 0,
                amount: 0,
                status: 'unpaid',
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
            });
        }
        onUpdateInstallments(balanceLastInstallment(base, grandTotal));
    };

    const lastIndex = effectiveInstallments.length - 1;

    // تحديث النسبة — لا يُحرَّر آخر قسط يدوياً إن وُجد أكثر من قسط
    const updatePercentage = (index: number, newPercentage: number) => {
        if (!planActive || isLocked) return;
        if (effectiveInstallments.length >= 2 && index === lastIndex) return;

        const updated = [...effectiveInstallments];
        updated[index] = {
            ...updated[index],
            percentage: newPercentage,
            amount: Number(((newPercentage / 100) * grandTotal).toFixed(2)),
        };

        if (updated.length >= 2) {
            onUpdateInstallments(balanceLastInstallment(updated, grandTotal));
        } else {
            onUpdateInstallments(updated);
        }
    };

    const updateAmount = (index: number, newAmount: number) => {
        if (!planActive || isLocked) return;
        if (effectiveInstallments.length >= 2 && index === lastIndex) return;

        const updated = [...effectiveInstallments];
        const newPercentage = grandTotal > 0 ? (newAmount / grandTotal) * 100 : 0;

        updated[index] = {
            ...updated[index],
            amount: newAmount,
            percentage: Number(newPercentage.toFixed(2)),
        };

        if (updated.length >= 2) {
            onUpdateInstallments(balanceLastInstallment(updated, grandTotal));
        } else {
            onUpdateInstallments(updated);
        }
    };

    /** إدراج قسط قبل الأخير وتقسيم حصة القسط الأخير السابق */
    const addNewInstallment = () => {
        if (!planActive || isLocked) return;
        const rows = [...effectiveInstallments];
        if (rows.length < 1) return;

        if (rows.length === 1) {
            generateInstallments(2);
            return;
        }

        const prevManual = rows.slice(0, -1);
        const last = rows[rows.length - 1];
        const givePct = Number((Number(last.percentage || 0) / 2).toFixed(2));

        const newMid: DealInstallment = {
            id: crypto.randomUUID(),
            installmentNumber: prevManual.length + 1,
            percentage: givePct,
            amount: Number((((givePct || 0) / 100) * grandTotal).toFixed(2)),
            status: 'unpaid',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        };

        const newRows = [...prevManual, newMid, { ...last, installmentNumber: prevManual.length + 2 }];
        setNumInstallments(newRows.length);
        onUpdateInstallments(balanceLastInstallment(newRows, grandTotal));
    };

    const deleteInstallment = (index: number) => {
        if (!planActive || effectiveInstallments.length <= 1 || isLocked) return;
        let updated = effectiveInstallments
            .filter((_, i) => i !== index)
            .map((inst, idx) => ({ ...inst, installmentNumber: idx + 1 }));

        setNumInstallments(updated.length);

        if (updated.length === 1 && grandTotal > 0.005) {
            updated = [
                {
                    ...updated[0],
                    percentage: 100,
                    amount: Number(grandTotal.toFixed(2)),
                },
            ];
        } else if (updated.length >= 2) {
            updated = balanceLastInstallment(updated, grandTotal);
        }

        onUpdateInstallments(updated);
    };

    const totalPercentage = effectiveInstallments.reduce((sum, inst) => sum + inst.percentage, 0);
    const totalAmount = effectiveInstallments.reduce((sum, inst) => sum + inst.amount, 0);
    // يجب توافق النسب (100%) والمبالغ (= إجمالي الصفقة) معاً لضمان صحة خطة الأقساط
    const isValid = Math.abs(totalPercentage - 100) < 0.1 && (grandTotal === 0 || Math.abs(totalAmount - grandTotal) < 1);
    const installmentPlanHintInvalid = (() => {
        if (isValid) return "";
        if (totalPercentage > 100.05) {
            return "مجموع النسب أعلى من 100٪ — غالباً لأن المبالغ المسجّلة لنفس رقم القسط اندمجت في العرض (مثلاً دفعتين على «دفعة 1»)، أو بيانات مكررة في السيرفر. راجع سجل المدفوعات والمبالغ.";
        }
        if (totalPercentage < 99.9) {
            return "مجموع النسب أقل من 100٪ — عدّل النسب أو أضف دفعة، أو راجع الخطة.";
        }
        if (grandTotal > 0.005 && Math.abs(totalAmount - grandTotal) >= 1) {
            return "مجموع مبالغ الأقساط لا يطابق إجمالي الصفقة — راجع المبالغ أو إجمالي الصفقة.";
        }
        return "يرجى مراجعة النسب (مجموع الدفعات غير الأخيرة لا يتجاوز 100٪ مع إكمال الدفعة الأخيرة تلقائياً).";
    })();

    return (
        <div
            className={`rounded-2xl border shadow-sm overflow-hidden ${
                isShipmentFinance
                    ? 'bg-gradient-to-br aseel-bg-panel via-white to-[var(--color-primary)]/40 dark:aseel-bg-panel dark:via-gray-900 dark:to-[var(--color-primary)]/30 border-[var(--color-border)]/60 dark:border-[var(--color-border)]/50'
                    : 'aseel-bg-field dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft'
            }`}
        >
            {isShipmentFinance && (
                <div className="px-4 py-2.5 bg-[var(--color-primary)]/95 dark:bg-[var(--color-surface-2)]/90 text-white text-xs flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 shrink-0 opacity-90" />
                    <span>
                        خطة الدفع تُهيَّأ تلقائياً من إجمالي الشحنة — انتقل مباشرة إلى «دفعات الشحنة» أدناه لتسجيل السليب والصندوق.
                    </span>
                </div>
            )}
            <div className="p-4">
            {/* --- Header (Compact) --- */}
            <div className="flex items-center justify-between mb-4 pb-3 border-b aseel-border-soft dark:aseel-border-soft">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${isLocked ? 'aseel-bg-panel aseel-text-soft' : isShipmentFinance ? 'bg-[var(--color-surface-2)] text-[var(--color-primary)] dark:bg-[var(--color-surface-2)]/40 dark:text-[var(--color-primary)]' : 'aseel-bg-accent-bg aseel-text-accent'} dark:bg-opacity-10`}>
                        {isLocked ? <Lock className="w-5 h-5" /> : isShipmentFinance ? <Sparkles className="w-5 h-5" /> : <Calculator className="w-5 h-5" />}
                    </div>
                    <div>
                        <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-bold aseel-text-ink dark:aseel-text-soft text-base">
                                {isShipmentFinance ? 'خطة دفع وكيل الشحن' : 'جدول الدفعات'}
                            </h3>
                            <span
                                className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                                    planActive
                                        ? 'aseel-bg-panel aseel-text-ink dark:aseel-bg-panel/40 dark:aseel-text-soft'
                                        : 'aseel-bg-panel aseel-text-soft dark:aseel-bg-panel/50'
                                }`}
                            >
                                {isShipmentFinance
                                    ? planActive
                                        ? grandTotal > 0.005
                                            ? 'جاهز للدفع'
                                            : 'أدخل تكلفة الشحن'
                                        : '—'
                                    : planActive
                                      ? 'مفعل'
                                      : 'معطل'}
                            </span>
                        </div>
                        <p className="text-xs aseel-text-soft dark:aseel-text-soft flex items-center gap-1 mt-0.5">
                            <span>المبلغ المرجعي:</span>
                            <span className="font-bold aseel-text-ink dark:aseel-text-soft">${grandTotal.toLocaleString()}</span>
                            {isLocked && <span className="aseel-text-soft font-medium px-1">• مقفل</span>}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {!isLocked && planActive && (
                        <div className="flex aseel-bg-panel dark:aseel-bg-panel rounded-lg p-0.5">
                            {[1, 2, 3, 4].map(num => (
                                <button
                                    key={num}
                                    onClick={() => generateInstallments(num)}
                                    className={`w-7 h-7 text-xs font-bold rounded-md transition-all ${numInstallments === num ? 'aseel-bg-field dark:aseel-bg-panel aseel-text-accent shadow-sm' : 'aseel-text-soft hover:aseel-text-ink'}`}
                                >
                                    {num}
                                </button>
                            ))}
                            <button onClick={addNewInstallment} className="w-7 h-7 flex items-center justify-center rounded-md hover:aseel-bg-field dark:hover:aseel-bg-panel text-green-600">
                                <Plus className="w-3 h-3" />
                            </button>
                        </div>
                    )}

                    {!isShipmentFinance && (
                        <button
                            type="button"
                            title={installmentPlanEnabled ? 'إيقاف جدول الدفعات' : 'تفعيل جدول الدفعات'}
                            onClick={() => !isLocked && onTogglePlan(!installmentPlanEnabled)}
                            disabled={isLocked && installmentPlanEnabled}
                            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${installmentPlanEnabled ? (isLocked ? 'aseel-bg-panel' : 'aseel-bg-accent') : 'aseel-bg-grid-head'}`}
                        >
                            <span className={`inline-block h-3 w-3 transform rounded-full aseel-bg-field transition-transform ${installmentPlanEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                        </button>
                    )}
                </div>
            </div>

            {/* --- Body --- */}
            {!planActive ? (
                <div className="text-center py-8 px-4 aseel-text-soft text-sm rounded-xl aseel-bg-panel/80 dark:aseel-bg-panel/50 border border-dashed aseel-border-soft dark:aseel-border-soft">
                    {isShipmentFinance ? (
                        <>
                            <p className="font-medium aseel-text-ink dark:aseel-text-soft mb-1">لا يوجد إجمالي شحنة بعد</p>
                            <p className="text-xs aseel-text-soft dark:aseel-text-soft max-w-md mx-auto">
                                عيّن تكلفة الشحن (إجمالي أو بالوحدة) ثم يظهر جدول الدفعات تلقائياً.
                            </p>
                        </>
                    ) : (
                        'نظام الدفعات غير مفعل لهذه الصفقة — استخدم المفتاح أعلاه للتفعيل.'
                    )}
                </div>
            ) : (
                <div className="space-y-2">
                    {/* Table Header */}
                    <div className="grid grid-cols-12 gap-2 text-[11px] font-bold aseel-text-soft dark:aseel-text-soft px-2">
                        <div className="col-span-1 text-center">#</div>
                        <div className="col-span-3">النسبة %</div>
                        <div className="col-span-4">المبلغ ($)</div>
                        <div className="col-span-3">الحالة</div>
                        <div className="col-span-1 text-center"></div>
                    </div>

                    {/* Rows */}
                    {effectiveInstallments.map((inst, index) => {
                        const payment = findPaymentForInstallment(deal, inst);
                        const isPaid =
                            inst.status === 'paid' ||
                            !!payment?.confirmedBySupplier ||
                            Number(payment?.amount || 0) > 0;
                        const hasSwift = !!payment?.bankSwiftImage;
                        const isLastAuto =
                            effectiveInstallments.length >= 2 && index === effectiveInstallments.length - 1;
                        const rowLockedInputs = isLocked || isLastAuto;

                        return (
                            <div key={inst.id}
                                className={`group grid grid-cols-12 gap-2 items-center p-1.5 rounded-lg border transition-all
                                ${isPaid
                                        ? 'bg-green-50/50 aseel-border-soft dark:bg-green-900/10 dark:border-green-800/50'
                                        : hasSwift
                                            ? 'aseel-bg-accent-bg/50 aseel-border-accent dark:aseel-bg-panel/10 dark:aseel-border-soft/50'
                                            : 'aseel-bg-field aseel-border-soft hover:aseel-border-soft dark:aseel-bg-panel dark:aseel-border-soft'
                                    }`}
                            >
                                {/* # */}
                                <div className="col-span-1 flex justify-center">
                                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold 
                                        ${isPaid ? 'bg-green-100 text-green-700' : hasSwift ? 'aseel-bg-accent-bg aseel-text-accent' : 'aseel-bg-panel aseel-text-soft dark:aseel-bg-panel dark:aseel-text-soft'}`}>
                                        {inst.installmentNumber}
                                    </div>
                                </div>

                                {/* Percentage Input */}
                                <div className="col-span-3">
                                    <div className="relative flex items-center">
                                        <input
                                            type="number" min="0" max="100" step="0.1"
                                            value={inst.percentage}
                                            onChange={(e) => updatePercentage(index, parseFloat(e.target.value) || 0)}
                                            disabled={rowLockedInputs}
                                            title={isLastAuto ? 'يُحسب تلقائياً كباقي 100%' : undefined}
                                            className={`w-full pl-6 pr-1 py-1 text-xs font-semibold text-center rounded border focus:ring-1 transition-colors ${
                                                isLastAuto
                                                    ? 'border-dashed border-[var(--color-border)] bg-[var(--color-surface-2)]/50 text-[var(--color-primary)] dark:bg-[var(--color-surface-2)]/30 dark:border-[var(--color-border)] dark:text-[var(--color-primary)]'
                                                    : 'aseel-border-soft focus:aseel-border-soft focus:ring-blue-500 aseel-bg-field dark:aseel-bg-panel dark:aseel-border-soft dark:text-white'
                                            } disabled:aseel-bg-panel disabled:aseel-text-soft`}
                                        />
                                        <Percent className="w-3 h-3 aseel-text-soft absolute left-1.5 pointer-events-none" />
                                    </div>
                                </div>

                                {/* Amount Input (Editable now) */}
                                <div className="col-span-4">
                                    <div className="relative flex items-center">
                                        <input
                                            type="number" min="0" step="0.01"
                                            value={inst.amount}
                                            onChange={(e) => updateAmount(index, parseFloat(e.target.value) || 0)}
                                            disabled={rowLockedInputs}
                                            title={isLastAuto ? 'يُحسب تلقائياً كباقي الإجمالي' : undefined}
                                            className={`w-full pl-5 pr-1 py-1 text-xs font-bold text-center rounded border focus:ring-1 transition-colors
                                                ${isPaid ? 'text-green-700 aseel-border-soft aseel-bg-field dark:aseel-bg-panel dark:text-green-400 dark:border-green-900'
                                                    : isLastAuto
                                                      ? 'border-dashed border-[var(--color-border)] bg-[var(--color-surface-2)]/50 text-[var(--color-primary)] dark:bg-[var(--color-surface-2)]/30 dark:border-[var(--color-border)] dark:text-[var(--color-primary)]'
                                                    : 'aseel-text-ink aseel-border-soft focus:aseel-border-soft focus:ring-blue-500 aseel-bg-field dark:aseel-bg-panel dark:aseel-border-soft dark:text-white disabled:aseel-bg-panel disabled:aseel-text-soft'}`}
                                        />
                                        <DollarSign className={`w-3 h-3 absolute left-1.5 pointer-events-none ${isPaid ? 'text-green-500' : 'aseel-text-soft'}`} />
                                    </div>
                                </div>

                                {/* Status Text */}
                                <div className="col-span-3">
                                    <div className="flex flex-col text-[10px] leading-tight">
                                        {isPaid ? (
                                            <span className="text-green-600 font-bold flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> تم الدفع</span>
                                        ) : hasSwift ? (
                                            <span className="aseel-text-accent font-medium">سليب مرفق</span>
                                        ) : (
                                            <span className="aseel-text-soft dark:aseel-text-soft">بانتظار الدفع</span>
                                        )}
                                        {payment?.usdToIls && <span className="aseel-text-soft text-[9px]">1$ = {payment.usdToIls}₪</span>}
                                    </div>
                                </div>

                                {/* Delete Action */}
                                <div className="col-span-1 flex justify-center">
                                    {!isLocked && effectiveInstallments.length > 1 && (
                                        <button onClick={() => deleteInstallment(index)} className="aseel-text-soft hover:aseel-text-soft transition-colors">
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                    )}
                                </div>
                            </div>
                        );
                    })}

                    {/* Footer Summary */}
                    <div className={`mt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-3 py-2 rounded-lg text-xs border ${isValid ? 'bg-green-50/50 border-green-100 text-green-700 dark:bg-green-900/10 dark:border-green-900 dark:text-green-400' : 'aseel-bg-panel aseel-border-soft aseel-text-state dark:aseel-bg-panel/10 dark:aseel-border-soft dark:aseel-text-soft'}`}>
                        <div className="flex items-center gap-2">
                            {isValid ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 shrink-0" />}
                            <div>
                                <span className="font-medium">
                                    {isValid ? "التوزيع صحيح" : installmentPlanHintInvalid}
                                </span>
                                {effectiveInstallments.length >= 2 && (
                                    <p className="text-[10px] opacity-80 mt-0.5 font-normal">
                                        الدفعة الأخيرة تُكمَّل تلقائياً لتساوي 100% والإجمالي بالضبط.
                                    </p>
                                )}
                            </div>
                        </div>
                        <span className="font-mono font-bold sm:shrink-0">{formatNumber(totalPercentage, { maxDecimals: 1 })}%</span>
                    </div>
                </div>
            )}
            </div>
        </div>
    );
};