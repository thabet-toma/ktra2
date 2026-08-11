import React, { useState } from 'react';
import { DollarSign, Percent, Tag } from 'lucide-react';
import { formatMoney, formatNumber } from '@/utils/formatNumber';

interface FinancialProps {
    data: any;
    onUpdate: (field: string, value: any) => void;
    readOnly?: boolean;
}

export const FinancialSummarySection: React.FC<FinancialProps> = ({ data, onUpdate, readOnly }) => {
    // حساب المبالغ
    const subtotal = data.subtotal || 0;
    const discountAmount = data.discountAmount || 0;
    const taxRate = data.taxRate || 0;

    // حساب الضريبة
    const netAfterDiscount = Math.max(0, subtotal - discountAmount);
    const taxAmount = netAfterDiscount * (taxRate / 100);
    // حساب تكلفة الشحن
    const shippingCost = data.shippingIncluded ? 0 : (data.shippingCost || 0);

    // حساب الإجمالي هنا مباشرة
    const grandTotal = subtotal - discountAmount + taxAmount + shippingCost;

    // حساب المبالغ المدفوعة والمتبقية
    const payments = data.payments || [];
    const paidAmount = payments.reduce((sum: number, payment: any) =>
        payment.confirmedBySupplier ? sum + (payment.amount || 0) : sum, 0);
    const remainingAmount = grandTotal - paidAmount;

    // حالة للتحكم بمربع تعديل الضريبة والخصم
    const [editingTax, setEditingTax] = useState(false);
    const [editingDiscount, setEditingDiscount] = useState(false);
    const [discountInput, setDiscountInput] = useState(discountAmount.toString());

    // حساب نسبة الخصم
    const discountPercentage = subtotal > 0 ? (discountAmount / subtotal) * 100 : 0;

    // معالجة تحديث الخصم
    const handleDiscountUpdate = () => {
        const value = Math.min(subtotal, Math.max(0, parseFloat(discountInput) || 0));
        onUpdate('discountAmount', value);
        setEditingDiscount(false);
    };

    // معالجة تحديث الضريبة
    const handleTaxUpdate = (value: number) => {
        onUpdate('taxRate', value);
        setEditingTax(false);
    };

    return (
        <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-3 w-full max-w-sm"> {/* زيادة العرض */}
            {/* العنوان مع الإجمالي في سطر واحد */}
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-semibold text-[var(--color-text)] flex items-center gap-2 whitespace-nowrap">
                    <DollarSign className="w-5 h-5 text-blue-500 flex-shrink-0" />
                    <span>الملخص المالي</span>
                </h3>
                <div className="text-lg font-bold text-green-600 whitespace-nowrap">
                    ${formatMoney(grandTotal)}
                </div>
            </div>

            {/* القائمة المدمجة */}
            <div className="space-y-2 text-sm"> {/* زيادة حجم الخط */}
                {/* سعر المنتجات */}
                <div className="flex justify-between items-center py-1">
                    <span className="text-[var(--color-text)] whitespace-nowrap">سعر المنتجات</span>
                    <span className="font-medium">${formatMoney(subtotal)}</span>
                </div>

                {/* الخصم - مع إمكانية التعديل */}
                <div className="flex justify-between items-center py-1">
                    <div className="flex items-center gap-2 text-[var(--color-text)] whitespace-nowrap">
                        <Tag className="w-4 h-4 text-red-500" />
                        الخصم
                        {!readOnly && (
                            <button
                                onClick={() => {
                                    setEditingDiscount(!editingDiscount);
                                    setDiscountInput(discountAmount.toString());
                                }}
                                className="text-sm text-blue-500 hover:text-blue-700"
                                title="تعديل الخصم"
                            >
                                {editingDiscount ? '✔' : '✏️'}
                            </button>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        {editingDiscount && !readOnly ? (
                            <div className="flex items-center gap-2">
                                <input
                                    type="number"
                                    value={discountInput}
                                    onChange={(e) => setDiscountInput(e.target.value)}
                                    className="w-20 px-2 py-1 text-center border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white text-sm"
                                    min="0"
                                    max={subtotal}
                                    step="0.01"
                                    autoFocus
                                    onBlur={handleDiscountUpdate}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            handleDiscountUpdate();
                                        }
                                        if (e.key === 'Escape') {
                                            setEditingDiscount(false);
                                            setDiscountInput(discountAmount.toString());
                                        }
                                    }}
                                />
                                <span className="text-[var(--color-text-muted)] text-sm">$</span>
                            </div>
                        ) : discountAmount > 0 ? (
                            <div className="flex flex-col items-end">
                                <span className="font-medium text-red-600">
                                    -${formatMoney(discountAmount)}
                                </span>
                                {discountPercentage > 0 && (
                                    <span className="text-xs text-[var(--color-text-muted)]">
                                        ({formatNumber(discountPercentage, { maxDecimals: 1 })}%)
                                    </span>
                                )}
                            </div>
                        ) : (
                            <span className="text-[var(--color-text-muted)] text-sm">-</span>
                        )}
                    </div>
                </div>

                {/* الضريبة - مع إمكانية التعديل */}
                <div className="flex justify-between items-center py-1">
                    <div className="flex items-center gap-2 text-[var(--color-text)] whitespace-nowrap">
                        <Percent className="w-4 h-4 text-[var(--color-text-muted)]" />
                        الضريبة
                        {!readOnly && (
                            <button
                                onClick={() => setEditingTax(!editingTax)}
                                className="text-sm text-blue-500 hover:text-blue-700"
                                title="تعديل الضريبة"
                            >
                                {editingTax ? '✔' : '✏️'}
                            </button>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        {editingTax && !readOnly ? (
                            <div className="flex items-center gap-2">
                                <input
                                    type="number"
                                    value={taxRate}
                                    onChange={(e) => {
                                        const value = Math.min(100, Math.max(0, parseFloat(e.target.value) || 0));
                                        handleTaxUpdate(value);
                                    }}
                                    className="w-16 px-2 py-1 text-center border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white text-sm"
                                    min="0"
                                    max="100"
                                    step="0.1"
                                    autoFocus
                                    onBlur={() => setEditingTax(false)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            setEditingTax(false);
                                        }
                                        if (e.key === 'Escape') {
                                            setEditingTax(false);
                                        }
                                    }}
                                />
                                <span className="text-[var(--color-text-muted)] text-sm">%</span>
                            </div>
                        ) : taxAmount > 0 ? (
                            <div className="flex flex-col items-end">
                                <span className="font-medium">
                                    ${formatMoney(taxAmount)}
                                </span>
                                <span className="text-xs text-[var(--color-text-muted)]">
                                    ({formatNumber(taxRate, { maxDecimals: 4 })}%)
                                </span>
                            </div>
                        ) : (
                            <span className="font-medium">
                                {formatNumber(taxRate, { maxDecimals: 4 })}%
                            </span>
                        )}
                    </div>
                </div>

                {/* الشحن */}
                {(shippingCost > 0 || data.shippingIncluded) && (
                    <div className="flex justify-between items-center py-1">
                        <span className="text-[var(--color-text)] whitespace-nowrap">
                            الشحن {data.shippingIncluded && <span className="text-xs text-green-600">(متضمن)</span>}
                        </span>
                        <span className="font-medium">
                            {data.shippingIncluded ? "متضمن" : `$${formatMoney(shippingCost)}`}
                        </span>
                    </div>
                )}

                {/* خط فاصل */}
                <div className="border-t border-[var(--color-border)] my-2"></div>

                {/* الإجمالي */}
                <div className="flex justify-between items-center py-1">
                    <span className="font-bold text-[var(--color-text)] text-base whitespace-nowrap">الإجمالي</span>
                    <span className="text-lg font-bold text-green-600 whitespace-nowrap">
                        ${formatMoney(grandTotal)}
                    </span>
                </div>

                {/* خط فاصل */}
                <div className="border-t border-[var(--color-border)] my-2"></div>

                {/* المدفوع */}
                <div className="flex justify-between items-center py-1">
                    <span className="text-[var(--color-text)] whitespace-nowrap">المدفوع</span>
                    <span className="font-bold text-green-600 text-sm">${formatMoney(paidAmount)}</span>
                </div>

                {/* المتبقي */}
                <div className="flex justify-between items-center py-1">
                    <span className="text-[var(--color-text)] whitespace-nowrap">المتبقي</span>
                    <span className="font-bold text-orange-600 text-sm">
                        ${formatMoney(remainingAmount)}
                    </span>
                </div>
            </div>

            {/* شريط التقدم للمدفوعات */}
            {grandTotal > 0 && (
                <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
                    <div className="flex justify-between text-sm text-[var(--color-text-muted)] mb-1">
                        <span className="whitespace-nowrap">تقدم الدفع</span>
                        <span>{Math.round((paidAmount / grandTotal) * 100)}%</span>
                    </div>
                    <div className="h-2 bg-[var(--color-surface-3)] rounded-full overflow-hidden">
                        <div
                            className="h-full bg-green-500 transition-all duration-300"
                            style={{ width: `${(paidAmount / grandTotal) * 100}%` }}
                        />
                    </div>
                </div>
            )}

            {/* ملاحظات عن الخصم والضريبة */}
            {(discountAmount > 0 || taxRate > 0) && (
                <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
                    <div className="text-xs text-[var(--color-text-muted)] space-y-1">
                        {discountAmount > 0 && (
                            <div className="flex justify-between">
                                <span>قيمة الخصم:</span>
                                <span className="font-medium">${formatMoney(discountAmount)}</span>
                            </div>
                        )}
                        {taxRate > 0 && (
                            <div className="flex justify-between">
                                <span>نسبة الضريبة:</span>
                                <span className="font-medium">{formatNumber(taxRate, { maxDecimals: 4 })}%</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};