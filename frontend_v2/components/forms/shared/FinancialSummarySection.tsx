import React, { useState } from 'react';
import { DollarSign, Percent, Tag } from 'lucide-react';

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
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 w-full max-w-sm"> {/* زيادة العرض */}
            {/* العنوان مع الإجمالي في سطر واحد */}
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2 whitespace-nowrap">
                    <DollarSign className="w-5 h-5 text-blue-500 flex-shrink-0" />
                    <span>الملخص المالي</span>
                </h3>
                <div className="text-lg font-bold text-green-600 whitespace-nowrap">
                    ${grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
            </div>

            {/* القائمة المدمجة */}
            <div className="space-y-2 text-sm"> {/* زيادة حجم الخط */}
                {/* سعر المنتجات */}
                <div className="flex justify-between items-center py-1">
                    <span className="text-gray-700 dark:text-gray-300 whitespace-nowrap">سعر المنتجات</span>
                    <span className="font-medium">${subtotal.toLocaleString()}</span>
                </div>

                {/* الخصم - مع إمكانية التعديل */}
                <div className="flex justify-between items-center py-1">
                    <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300 whitespace-nowrap">
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
                                <span className="text-gray-500 text-sm">$</span>
                            </div>
                        ) : discountAmount > 0 ? (
                            <div className="flex flex-col items-end">
                                <span className="font-medium text-red-600">
                                    -${discountAmount.toLocaleString()}
                                </span>
                                {discountPercentage > 0 && (
                                    <span className="text-xs text-gray-500">
                                        ({discountPercentage.toFixed(1)}%)
                                    </span>
                                )}
                            </div>
                        ) : (
                            <span className="text-gray-400 text-sm">-</span>
                        )}
                    </div>
                </div>

                {/* الضريبة - مع إمكانية التعديل */}
                <div className="flex justify-between items-center py-1">
                    <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300 whitespace-nowrap">
                        <Percent className="w-4 h-4 text-gray-500" />
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
                                <span className="text-gray-500 text-sm">%</span>
                            </div>
                        ) : taxAmount > 0 ? (
                            <div className="flex flex-col items-end">
                                <span className="font-medium">
                                    ${taxAmount.toFixed(2)}
                                </span>
                                <span className="text-xs text-gray-500">
                                    ({taxRate}%)
                                </span>
                            </div>
                        ) : (
                            <span className="font-medium">
                                {taxRate}%
                            </span>
                        )}
                    </div>
                </div>

                {/* الشحن */}
                {(shippingCost > 0 || data.shippingIncluded) && (
                    <div className="flex justify-between items-center py-1">
                        <span className="text-gray-700 dark:text-gray-300 whitespace-nowrap">
                            الشحن {data.shippingIncluded && <span className="text-xs text-green-600">(متضمن)</span>}
                        </span>
                        <span className="font-medium">
                            {data.shippingIncluded ? "متضمن" : `$${shippingCost.toLocaleString()}`}
                        </span>
                    </div>
                )}

                {/* خط فاصل */}
                <div className="border-t border-gray-200 dark:border-gray-700 my-2"></div>

                {/* الإجمالي */}
                <div className="flex justify-between items-center py-1">
                    <span className="font-bold text-gray-900 dark:text-white text-base whitespace-nowrap">الإجمالي</span>
                    <span className="text-lg font-bold text-green-600 whitespace-nowrap">
                        ${grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                </div>

                {/* خط فاصل */}
                <div className="border-t border-gray-200 dark:border-gray-700 my-2"></div>

                {/* المدفوع */}
                <div className="flex justify-between items-center py-1">
                    <span className="text-gray-700 dark:text-gray-300 whitespace-nowrap">المدفوع</span>
                    <span className="font-bold text-green-600 text-sm">${paidAmount.toLocaleString()}</span>
                </div>

                {/* المتبقي */}
                <div className="flex justify-between items-center py-1">
                    <span className="text-gray-700 dark:text-gray-300 whitespace-nowrap">المتبقي</span>
                    <span className="font-bold text-orange-600 text-sm">
                        ${remainingAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                </div>
            </div>

            {/* شريط التقدم للمدفوعات */}
            {grandTotal > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between text-sm text-gray-500 dark:text-gray-400 mb-1">
                        <span className="whitespace-nowrap">تقدم الدفع</span>
                        <span>{Math.round((paidAmount / grandTotal) * 100)}%</span>
                    </div>
                    <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-green-500 transition-all duration-300"
                            style={{ width: `${(paidAmount / grandTotal) * 100}%` }}
                        />
                    </div>
                </div>
            )}

            {/* ملاحظات عن الخصم والضريبة */}
            {(discountAmount > 0 || taxRate > 0) && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                        {discountAmount > 0 && (
                            <div className="flex justify-between">
                                <span>قيمة الخصم:</span>
                                <span className="font-medium">${discountAmount.toFixed(2)}</span>
                            </div>
                        )}
                        {taxRate > 0 && (
                            <div className="flex justify-between">
                                <span>نسبة الضريبة:</span>
                                <span className="font-medium">{taxRate}%</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};