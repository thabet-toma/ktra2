import React, { useState, useEffect } from "react";
import { Invoice, LocalPayments } from "@/types";
import {
    CreditCard,
    DollarSign,
    Calculator,
    Building,
    Shield,
    Anchor,
    Truck,
    Lock,
    Unlock
} from "lucide-react";

interface LocalPaymentsSectionProps {
    data: Partial<Invoice>;
    setData: React.Dispatch<React.SetStateAction<Partial<Invoice>>>;
}

export const LocalPaymentsSection: React.FC<LocalPaymentsSectionProps> = ({
    data,
    setData,
}) => {
    const localPayments = data.localPayments || {};
    const [calculationMethod, setCalculationMethod] = useState<'detailed' | 'lump_sum' | null>(
        localPayments.calculationMethod || null
    );
    const [includedInPrice, setIncludedInPrice] = useState<boolean>(
        localPayments.includedInPrice || false
    );

    // ✅ المدفوعات التفصيلية مع الأيقونات والملصقات
    const detailedPayments = [
        {
            key: 'customsClearanceFees',
            label: 'رسوم المخلص الجمركي',
            icon: <Building className="w-4 h-4" />,
            color: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800/30 text-blue-700 dark:text-blue-300',
            description: 'رسوم الوكيل الجمركي المسؤول عن تخليص البضاعة'
        },
        {
            key: 'customsDuties',
            label: 'رسوم الجمارك',
            icon: <Shield className="w-4 h-4" />,
            color: 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 border-[var(--color-border)] dark:border-[var(--color-border)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)]',
            description: 'الضرائب والرسوم الجمركية الرسمية'
        },
        {
            key: 'portFees',
            label: 'رسوم الميناء',
            icon: <Anchor className="w-4 h-4" />,
            color: 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/30 text-amber-700 dark:text-amber-300',
            description: 'رسوم التفريغ والشحن والخدمات المينائية'
        },
        {
            key: 'internalShippingFees',
            label: 'رسوم الشحن الداخلي',
            icon: <Truck className="w-4 h-4" />,
            color: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800/30 text-green-700 dark:text-green-300',
            description: 'نقل البضاعة داخل البلد'
        }
    ];

    // ✅ معالجة تغييرات الحقول
    const handleChange = (field: string, value: any) => {
        const updatedPayments = { ...localPayments, [field]: value };

        // إذا تم التفعيل "متضمن بالسعر"، نحذف جميع القيم
        if (field === 'includedInPrice' && value === true) {
            // نحتفظ فقط بالطريقة والخيار
            setData((prev) => ({
                ...prev,
                localPayments: {
                    calculationMethod: updatedPayments.calculationMethod,
                    includedInPrice: true
                }
            }));
        } else {
            setData((prev) => ({
                ...prev,
                localPayments: updatedPayments
            }));
        }
    };

    // ✅ تغيير طريقة الحساب
    const handleMethodChange = (method: 'detailed' | 'lump_sum') => {
        setCalculationMethod(method);

        if (includedInPrice) {
            // إذا كانت مشمولة، نحتفظ فقط بالطريقة
            setData((prev) => ({
                ...prev,
                localPayments: {
                    calculationMethod: method,
                    includedInPrice: true
                }
            }));
        } else {
            // إذا كانت غير مشمولة، نغير الطريقة ونهيء الحقول
            const newPayments: any = {
                calculationMethod: method,
                includedInPrice: false
            };

            // إذا تحولنا إلى مبلغ شامل، نحذف القيم التفصيلية
            if (method === 'lump_sum') {
                delete newPayments.customsClearanceFees;
                delete newPayments.customsDuties;
                delete newPayments.portFees;
                delete newPayments.internalShippingFees;
                newPayments.lumpSumAmount = 0;
            }
            // إذا تحولنا إلى تفصيلي، نحذف المبلغ الشامل
            else {
                delete newPayments.lumpSumAmount;
                newPayments.customsClearanceFees = 0;
                newPayments.customsDuties = 0;
                newPayments.portFees = 0;
                newPayments.internalShippingFees = 0;
            }

            setData((prev) => ({
                ...prev,
                localPayments: newPayments
            }));
        }
    };

    // ✅ تغيير خيار التضمين
    const handleIncludedToggle = (checked: boolean) => {
        setIncludedInPrice(checked);

        if (checked) {
            // تفعيل "متضمن بالسعر" → نحذف جميع القيم
            const cleanPayments: any = {
                calculationMethod: calculationMethod,
                includedInPrice: true
            };

            setData((prev) => ({
                ...prev,
                localPayments: cleanPayments
            }));
        } else {
            // إلغاء "متضمن بالسعر" → نهيء القيم حسب الطريقة
            const newPayments: any = {
                calculationMethod: calculationMethod,
                includedInPrice: false
            };

            if (calculationMethod === 'detailed') {
                newPayments.customsClearanceFees = 0;
                newPayments.customsDuties = 0;
                newPayments.portFees = 0;
                newPayments.internalShippingFees = 0;
            } else if (calculationMethod === 'lump_sum') {
                newPayments.lumpSumAmount = 0;
            }

            setData((prev) => ({
                ...prev,
                localPayments: newPayments
            }));
        }
    };

    // ✅ حساب الإجمالي
    const calculateTotalLocalPayments = () => {
        if (!localPayments || includedInPrice) return 0;

        if (localPayments.calculationMethod === 'lump_sum' && localPayments.lumpSumAmount) {
            return localPayments.lumpSumAmount;
        }

        if (localPayments.calculationMethod === 'detailed') {
            return (
                (localPayments.customsClearanceFees || 0) +
                (localPayments.customsDuties || 0) +
                (localPayments.portFees || 0) +
                (localPayments.internalShippingFees || 0)
            );
        }

        return 0;
    };

    const totalLocalPayments = calculateTotalLocalPayments();

    // ✅ تحديث الحالة عند تغيير البيانات
    useEffect(() => {
        if (data.localPayments?.includedInPrice !== includedInPrice) {
            setIncludedInPrice(data.localPayments?.includedInPrice || false);
        }
        if (data.localPayments?.calculationMethod !== calculationMethod) {
            setCalculationMethod(data.localPayments?.calculationMethod || null);
        }
    }, [data.localPayments]);

    return (
        <div className="space-y-6">
            {/* العنوان والوصف */}
            <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
                <div className="flex items-center gap-3 mb-2">
                    <CreditCard className="w-6 h-6 text-blue-500" />
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                        المدفوعات المحلية
                    </h3>
                    {includedInPrice && (
                        <span className="px-2 py-1 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full border border-green-200 dark:border-green-800">
                            مشمولة في سعر المورد
                        </span>
                    )}
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                    هذه الرسوم تضاف بعد وصول البضاعة إلى بلد الوجهة
                </p>
            </div>

            {/* بطاقة الحالة الرئيسية */}
            <div className={`p-4 rounded-xl border ${includedInPrice
                ? 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800/30'
                : 'bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800/30'
                }`}>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        {includedInPrice ? (
                            <Lock className="w-5 h-5 text-green-600 dark:text-green-400" />
                        ) : (
                            <Unlock className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        )}
                        <div>
                            <h4 className="font-medium text-gray-900 dark:text-white">
                                {includedInPrice ? 'الرسوم مشمولة في سعر المورد' : 'الرسوم غير مشمولة في السعر'}
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                {includedInPrice
                                    ? 'المورد يتحمل كافة الرسوم المحلية. لا حاجة لإدخال قيم.'
                                    : 'يجب إدخال قيم الرسوم المحلية يدوياً.'
                                }
                            </p>
                        </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            checked={includedInPrice}
                            onChange={(e) => handleIncludedToggle(e.target.checked)}
                            className="sr-only peer"
                        />
                        <div className="w-12 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-green-600"></div>
                    </label>
                </div>
            </div>

            {/* طرق الحساب - تظهر فقط إذا لم تكن مشمولة */}
            {!includedInPrice && (
                <>
                    <div className="mt-6">
                        <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                            اختر طريقة حساب الرسوم
                        </h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <button
                                type="button"
                                onClick={() => handleMethodChange('detailed')}
                                className={`p-4 rounded-xl border transition-all duration-200 flex flex-col items-center gap-3 ${calculationMethod === 'detailed'
                                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 shadow-sm'
                                    : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
                                    }`}
                            >
                                <Calculator className={`w-8 h-8 ${calculationMethod === 'detailed' ? 'text-blue-600' : 'text-gray-400'}`} />
                                <div className="text-center">
                                    <div className="font-medium text-gray-900 dark:text-white">
                                        تفصيلي
                                    </div>
                                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                        أدخل كل رسومة على حدة
                                    </div>
                                </div>
                            </button>

                            <button
                                type="button"
                                onClick={() => handleMethodChange('lump_sum')}
                                className={`p-4 rounded-xl border transition-all duration-200 flex flex-col items-center gap-3 ${calculationMethod === 'lump_sum'
                                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 shadow-sm'
                                    : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
                                    }`}
                            >
                                <DollarSign className={`w-8 h-8 ${calculationMethod === 'lump_sum' ? 'text-blue-600' : 'text-gray-400'}`} />
                                <div className="text-center">
                                    <div className="font-medium text-gray-900 dark:text-white">
                                        مبلغ شامل
                                    </div>
                                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                        أدخل مبلغاً إجمالياً للجميع
                                    </div>
                                </div>
                            </button>
                        </div>
                    </div>

                    {/* الحقول التفصيلية */}
                    {calculationMethod === 'detailed' && !includedInPrice && (
                        <div className="mt-6">
                            <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                                أدخل قيم الرسوم التفصيلية
                            </h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {detailedPayments.map((payment) => {
                                    const value =
                                        typeof localPayments[payment.key as keyof LocalPayments] === 'number'
                                            ? (localPayments[payment.key as keyof LocalPayments] as number)
                                            : '';

                                    return (
                                        <div
                                            key={payment.key}
                                            className={`p-4 rounded-xl border ${payment.color} transition-all duration-200 hover:shadow-sm`}
                                        >
                                            <div className="flex items-center gap-3 mb-2">
                                                {payment.icon}
                                                <span className="font-medium text-gray-900 dark:text-white">
                                                    {payment.label}
                                                </span>
                                            </div>

                                            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
                                                {payment.description}
                                            </p>

                                            <div className="relative">
                                                <input
                                                    type="number"
                                                    value={value}
                                                    onChange={(e) =>
                                                        handleChange(
                                                            payment.key,
                                                            e.target.value === '' ? 0 : Number(e.target.value)
                                                        )
                                                    }
                                                    placeholder="0.00"
                                                    className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                                    step="0.01"
                                                    min="0"
                                                />
                                                <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500">
                                                    $
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* المبلغ الشامل */}
                    {calculationMethod === 'lump_sum' && !includedInPrice && (
                        <div className="mt-6">
                            <div className="p-4 rounded-xl border bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800/30">
                                <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                                    المبلغ الشامل للرسوم المحلية
                                </h4>
                                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                                    أدخل المبلغ الإجمالي لجميع الرسوم المحلية معاً
                                </p>
                                <div className="relative">
                                    <input
                                        type="number"
                                        value={localPayments.lumpSumAmount || ''}
                                        onChange={(e) => handleChange('lumpSumAmount', parseFloat(e.target.value) || 0)}
                                        placeholder="0.00"
                                        className="w-full pl-12 pr-4 py-3 border-2 border-blue-300 dark:border-blue-700 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 text-lg font-medium focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                        step="0.01"
                                        min="0"
                                    />
                                    <div className="absolute left-3 top-1/2 transform -translate-y-1/2">
                                        <DollarSign className="w-6 h-6 text-blue-600" />
                                    </div>
                                </div>
                                <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                                    يشمل: المخلص الجمركي، الجمارك، الميناء، الشحن الداخلي
                                </div>
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* ملخص الإجمالي */}
            {(totalLocalPayments > 0 || includedInPrice) && (
                <div className="mt-6">
                    <div className="p-4 rounded-xl border bg-gradient-to-r from-blue-50 to-green-50 dark:from-blue-900/10 dark:to-green-900/10 border-blue-200 dark:border-blue-800/30">
                        <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-3">
                                <CreditCard className="w-5 h-5 text-blue-600" />
                                <h4 className="font-bold text-gray-900 dark:text-white">
                                    ملخص المدفوعات المحلية
                                </h4>
                            </div>
                            <div className="text-lg font-bold text-gray-900 dark:text-white">
                                {includedInPrice ? 'مشمولة في السعر' : `$${totalLocalPayments.toFixed(2)}`}
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
                            <div className="text-sm text-gray-600 dark:text-gray-400">
                                طريقة الحساب: <span className="font-medium">
                                    {calculationMethod === 'detailed' ? 'تفصيلي' :
                                        calculationMethod === 'lump_sum' ? 'مبلغ شامل' :
                                            'لم يتم تحديدها'}
                                </span>
                            </div>
                            <div className="text-sm text-gray-600 dark:text-gray-400">
                                حالة الدفع: <span className={`font-medium ${includedInPrice ? 'text-green-600' : 'text-blue-600'}`}>
                                    {includedInPrice ? 'مورد يدفع' : 'يتم حسابها'}
                                </span>
                            </div>
                        </div>

                        {/* تفاصيل الرسوم إذا كانت تفصيلية */}
                        {calculationMethod === 'detailed' && !includedInPrice && totalLocalPayments > 0 && (
                            <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                                <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    تفاصيل الرسوم:
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    {detailedPayments.map((payment) => {
                                        const value = localPayments[payment.key as keyof typeof localPayments] as number || 0;
                                        if (value <= 0) return null;

                                        return (
                                            <div key={payment.key} className="flex justify-between items-center text-sm">
                                                <span className="text-gray-600 dark:text-gray-400">{payment.label}:</span>
                                                <span className="font-medium">${value.toFixed(2)}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* رسالة توضيحية */}
            <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-800/30 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="text-sm text-gray-600 dark:text-gray-400">
                    <div className="font-medium mb-1">💡 ملاحظة مهمة:</div>
                    <ul className="list-disc list-inside space-y-1">
                        <li>اختر <span className="font-medium">"مشمولة في السعر"</span> إذا كان المورد يتحمل كافة الرسوم المحلية</li>
                        <li>اختر <span className="font-medium">"غير مشمولة"</span> ثم أدخل القيم يدوياً إذا كنت تتحمل الرسوم</li>
                        <li>القيم المدخلة ستؤثر على السعر الإجمالي للفاتورة</li>
                    </ul>
                </div>
            </div>
        </div>
    );
};