import React, { useState, useEffect } from 'react';
import { DealInstallment } from '@/types';
import { Plus, Trash2, Calculator, CheckCircle2, AlertCircle, Lock, DollarSign, Percent } from 'lucide-react';

interface InstallmentManagerProps {
    installments: DealInstallment[];
    grandTotal: number;
    onUpdateInstallments: (installments: DealInstallment[]) => void;
    validationError: string;
    installmentPlanEnabled: boolean;
    onTogglePlan: (enabled: boolean) => void;
    deal?: any;
    readOnly?: boolean;
}

export const InstallmentManager: React.FC<InstallmentManagerProps> = ({
    installments: propInstallments,
    grandTotal,
    onUpdateInstallments,
    installmentPlanEnabled,
    onTogglePlan,
    deal = {},
    readOnly = false
}) => {
    const [numInstallments, setNumInstallments] = useState(propInstallments.length || 1);

    const getEffectiveInstallments = (): DealInstallment[] => {
        if (deal?.installments && deal.installments.length > 0) return deal.installments;
        return propInstallments;
    };

    const effectiveInstallments = getEffectiveInstallments();

    const checkIfPaymentsStarted = (): boolean => {
        const hasConfirmedPayments = deal?.payments?.some((p: any) => p.confirmedBySupplier || p.bankSwiftImage);
        const hasPaidInstallments = effectiveInstallments.some(inst => inst.status === 'paid');
        return hasConfirmedPayments || hasPaidInstallments;
    };

    const isLocked = checkIfPaymentsStarted() || readOnly;

    // تهيئة أولية
    useEffect(() => {
        if (installmentPlanEnabled && effectiveInstallments.length === 0) {
            const defaultInstallment: DealInstallment = {
                id: crypto.randomUUID(),
                installmentNumber: 1,
                percentage: 100,
                amount: Number(grandTotal.toFixed(2)),
                status: 'unpaid',
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString()
            };
            onUpdateInstallments([defaultInstallment]);
        } else if (!installmentPlanEnabled && effectiveInstallments.length > 0) {
            onUpdateInstallments([]);
        }
    }, [installmentPlanEnabled, grandTotal, effectiveInstallments]);

    // توليد دفعات جديدة
    const generateInstallments = (count: number) => {
        if (!installmentPlanEnabled || isLocked) return;
        const newInstallments: DealInstallment[] = [];
        const percentagePerInstallment = 100 / count;

        for (let i = 1; i <= count; i++) {
            newInstallments.push({
                id: crypto.randomUUID(),
                installmentNumber: i,
                percentage: Number(percentagePerInstallment.toFixed(2)),
                amount: Number(((percentagePerInstallment / 100) * grandTotal).toFixed(2)),
                status: 'unpaid',
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString()
            });
        }
        setNumInstallments(count);
        onUpdateInstallments(newInstallments);
    };

    // ✅ تحديث بناءً على النسبة (يعدل المبلغ)
    const updatePercentage = (index: number, newPercentage: number) => {
        if (!installmentPlanEnabled || isLocked) return;
        const updated = [...effectiveInstallments];
        updated[index] = {
            ...updated[index],
            percentage: newPercentage,
            amount: Number(((newPercentage / 100) * grandTotal).toFixed(2))
        };
        onUpdateInstallments(updated);
    };

    // ✅ تحديث بناءً على المبلغ (يعدل النسبة)
    const updateAmount = (index: number, newAmount: number) => {
        if (!installmentPlanEnabled || isLocked) return;
        const updated = [...effectiveInstallments];
        const newPercentage = grandTotal > 0 ? (newAmount / grandTotal) * 100 : 0;

        updated[index] = {
            ...updated[index],
            amount: newAmount,
            percentage: Number(newPercentage.toFixed(2))
        };
        onUpdateInstallments(updated);
    };

    const addNewInstallment = () => {
        if (!installmentPlanEnabled || isLocked) return;
        const remainingPct = Math.max(0, 100 - effectiveInstallments.reduce((sum, i) => sum + i.percentage, 0));
        const newInst: DealInstallment = {
            id: crypto.randomUUID(),
            installmentNumber: effectiveInstallments.length + 1,
            percentage: Number(remainingPct.toFixed(2)),
            amount: Number(((remainingPct / 100) * grandTotal).toFixed(2)),
            status: 'unpaid',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };
        onUpdateInstallments([...effectiveInstallments, newInst]);
    };

    const deleteInstallment = (index: number) => {
        if (!installmentPlanEnabled || effectiveInstallments.length <= 1 || isLocked) return;
        const updated = effectiveInstallments.filter((_, i) => i !== index)
            .map((inst, idx) => ({ ...inst, installmentNumber: idx + 1 }));
        setNumInstallments(updated.length);
        onUpdateInstallments(updated);
    };

    const totalPercentage = effectiveInstallments.reduce((sum, inst) => sum + inst.percentage, 0);
    const totalAmount = effectiveInstallments.reduce((sum, inst) => sum + inst.amount, 0);
    const isValid = Math.abs(totalPercentage - 100) < 0.1 || Math.abs(totalAmount - grandTotal) < 1;

    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">

            {/* --- Header (Compact) --- */}
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-100 dark:border-gray-700">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${isLocked ? 'bg-orange-50 text-orange-600' : 'bg-blue-50 text-blue-600'} dark:bg-opacity-10`}>
                        {isLocked ? <Lock className="w-5 h-5" /> : <Calculator className="w-5 h-5" />}
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="font-bold text-gray-900 dark:text-gray-100 text-base">جدول الدفعات</h3>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${installmentPlanEnabled ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-500'}`}>
                                {installmentPlanEnabled ? 'مفعل' : 'معطل'}
                            </span>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
                            <span>الإجمالي:</span>
                            <span className="font-bold text-gray-900 dark:text-gray-200">${grandTotal.toLocaleString()}</span>
                            {isLocked && <span className="text-orange-500 font-medium px-1">• مقفل</span>}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {!isLocked && installmentPlanEnabled && (
                        <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
                            {[1, 2, 3, 4].map(num => (
                                <button
                                    key={num}
                                    onClick={() => generateInstallments(num)}
                                    className={`w-7 h-7 text-xs font-bold rounded-md transition-all ${numInstallments === num ? 'bg-white dark:bg-gray-600 text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
                                >
                                    {num}
                                </button>
                            ))}
                            <button onClick={addNewInstallment} className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-white dark:hover:bg-gray-600 text-green-600">
                                <Plus className="w-3 h-3" />
                            </button>
                        </div>
                    )}

                    <button
                        onClick={() => !isLocked && onTogglePlan(!installmentPlanEnabled)}
                        disabled={isLocked && installmentPlanEnabled}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${installmentPlanEnabled ? (isLocked ? 'bg-orange-400' : 'bg-blue-600') : 'bg-gray-300'}`}
                    >
                        <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${installmentPlanEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                    </button>
                </div>
            </div>

            {/* --- Body --- */}
            {!installmentPlanEnabled ? (
                <div className="text-center py-6 text-gray-400 text-sm">
                    نظام الدفعات غير مفعل لهذه الصفقة
                </div>
            ) : (
                <div className="space-y-2">
                    {/* Table Header */}
                    <div className="grid grid-cols-12 gap-2 text-[11px] font-bold text-gray-400 dark:text-gray-500 px-2">
                        <div className="col-span-1 text-center">#</div>
                        <div className="col-span-3">النسبة %</div>
                        <div className="col-span-4">المبلغ ($)</div>
                        <div className="col-span-3">الحالة</div>
                        <div className="col-span-1 text-center"></div>
                    </div>

                    {/* Rows */}
                    {effectiveInstallments.map((inst, index) => {
                        const payment = deal?.payments?.find((p: any) => p.installmentId === inst.id);
                        const isPaid = inst.status === 'paid' || !!payment?.confirmedBySupplier;
                        const hasSwift = !!payment?.bankSwiftImage;

                        return (
                            <div key={inst.id}
                                className={`group grid grid-cols-12 gap-2 items-center p-1.5 rounded-lg border transition-all
                                ${isPaid
                                        ? 'bg-green-50/50 border-green-200 dark:bg-green-900/10 dark:border-green-800/50'
                                        : hasSwift
                                            ? 'bg-blue-50/50 border-blue-200 dark:bg-blue-900/10 dark:border-blue-800/50'
                                            : 'bg-white border-gray-200 hover:border-blue-300 dark:bg-gray-800 dark:border-gray-700'
                                    }`}
                            >
                                {/* # */}
                                <div className="col-span-1 flex justify-center">
                                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold 
                                        ${isPaid ? 'bg-green-100 text-green-700' : hasSwift ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
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
                                            disabled={isLocked}
                                            className="w-full pl-6 pr-1 py-1 text-xs font-semibold text-center rounded border border-gray-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-white disabled:bg-gray-50 disabled:text-gray-500 transition-colors"
                                        />
                                        <Percent className="w-3 h-3 text-gray-400 absolute left-1.5 pointer-events-none" />
                                    </div>
                                </div>

                                {/* Amount Input (Editable now) */}
                                <div className="col-span-4">
                                    <div className="relative flex items-center">
                                        <input
                                            type="number" min="0" step="0.01"
                                            value={inst.amount}
                                            onChange={(e) => updateAmount(index, parseFloat(e.target.value) || 0)}
                                            disabled={isLocked}
                                            className={`w-full pl-5 pr-1 py-1 text-xs font-bold text-center rounded border focus:ring-1 transition-colors
                                                ${isPaid ? 'text-green-700 border-green-200 bg-white dark:bg-gray-900 dark:text-green-400 dark:border-green-900'
                                                    : 'text-gray-900 border-gray-200 focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-900 dark:border-gray-600 dark:text-white disabled:bg-gray-50 disabled:text-gray-500'}`}
                                        />
                                        <DollarSign className={`w-3 h-3 absolute left-1.5 pointer-events-none ${isPaid ? 'text-green-500' : 'text-gray-400'}`} />
                                    </div>
                                </div>

                                {/* Status Text */}
                                <div className="col-span-3">
                                    <div className="flex flex-col text-[10px] leading-tight">
                                        {isPaid ? (
                                            <span className="text-green-600 font-bold flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> تم الدفع</span>
                                        ) : hasSwift ? (
                                            <span className="text-blue-600 font-medium">سليب مرفق</span>
                                        ) : (
                                            <span className="text-gray-400 dark:text-gray-500">بانتظار الدفع</span>
                                        )}
                                        {payment?.usdToIls && <span className="text-gray-400 text-[9px]">1$ = {payment.usdToIls}₪</span>}
                                    </div>
                                </div>

                                {/* Delete Action */}
                                <div className="col-span-1 flex justify-center">
                                    {!isLocked && effectiveInstallments.length > 1 && (
                                        <button onClick={() => deleteInstallment(index)} className="text-gray-300 hover:text-red-500 transition-colors">
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                    )}
                                </div>
                            </div>
                        );
                    })}

                    {/* Footer Summary */}
                    <div className={`mt-2 flex items-center justify-between px-3 py-2 rounded-lg text-xs border ${isValid ? 'bg-green-50/50 border-green-100 text-green-700 dark:bg-green-900/10 dark:border-green-900 dark:text-green-400' : 'bg-red-50 border-red-100 text-red-600 dark:bg-red-900/10 dark:border-red-900 dark:text-red-400'}`}>
                        <div className="flex items-center gap-2">
                            {isValid ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                            <span className="font-medium">{isValid ? 'التوزيع صحيح' : 'يرجى مراجعة النسب'}</span>
                        </div>
                        <span className="font-mono font-bold">{totalPercentage.toFixed(1)}%</span>
                    </div>
                </div>
            )}
        </div>
    );
};