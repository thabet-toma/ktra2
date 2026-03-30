import React from 'react';
import { Calculator, Wallet, CreditCard, Ship, TrendingDown, Percent, ChevronLeft, Info } from 'lucide-react';

interface NISFinancialSummaryProps {
    subtotal: number;
    discountAmount: number;
    taxAmount: number;
    taxRate: number;
    shippingCost: number;
    grandTotal: number;
    localPayments?: any;
    currency?: string;
}

export const NISFinancialSummary: React.FC<NISFinancialSummaryProps> = ({
    subtotal,
    discountAmount,
    taxAmount,
    taxRate,
    shippingCost,
    grandTotal,
    localPayments,
}) => {
    const symbol = '₪';

    const lp = localPayments || {};
    const hasLocalPayments = !lp.includedInPrice && (
        (lp.customsClearanceFees || 0) +
        (lp.customsDuties || 0) +
        (lp.portFees || 0) +
        (lp.internalShippingFees || 0) +
        (lp.palestinianTaxCustoms || 0)
    ) > 0;

    return (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <div className="p-5 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50 flex items-center justify-between">
                <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <Calculator className="w-5 h-5 text-emerald-500" />
                    الملخص المالي النهائي
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                    عملة الفاتورة: ILS
                </span>
            </div>

            <div className="p-6">
                <div className="space-y-4">
                    <div className="flex justify-between items-center">
                        <span className="text-gray-500 text-sm flex items-center gap-2">
                            <CreditCard className="w-4 h-4" /> إجمالي المنتجات
                        </span>
                        <span className="font-bold text-gray-900 dark:text-white text-lg">
                            {symbol}{subtotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                    </div>

                    {discountAmount > 0 && (
                        <div className="flex justify-between items-center text-rose-600 dark:text-rose-400">
                            <span className="text-sm flex items-center gap-2">
                                <TrendingDown className="w-4 h-4" /> خصومات تجارية
                            </span>
                            <span className="font-bold">
                                -{symbol}{discountAmount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </span>
                        </div>
                    )}

                    <div className="flex justify-between items-center">
                        <span className="text-gray-500 text-sm flex items-center gap-2">
                            <Percent className="w-4 h-4" /> ضريبة القيمة المضافة ({taxRate}%)
                        </span>
                        <span className="font-bold text-gray-900 dark:text-white">
                            {symbol}{taxAmount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                    </div>

                    <div className="flex justify-between items-center">
                        <span className="text-gray-500 text-sm flex items-center gap-2">
                            <Ship className="w-4 h-4" /> تكاليف الشحن (كلي)
                        </span>
                        <span className="font-bold text-gray-900 dark:text-white">
                            {symbol}{shippingCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                    </div>

                    {hasLocalPayments && (
                        <div className="pt-2 mt-2 border-t border-gray-100 dark:border-gray-800 space-y-1">
                            <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 block mb-1">تفاصيل المدفوعات المحلية (ILS):</span>
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px]">
                                {lp.customsClearanceFees > 0 && (
                                    <div className="flex justify-between italic"><span className="text-gray-500">المخلص:</span> <span className="font-bold">₪{lp.customsClearanceFees}</span></div>
                                )}
                                {lp.customsDuties > 0 && (
                                    <div className="flex justify-between italic"><span className="text-gray-500">الجمارك:</span> <span className="font-bold">₪{lp.customsDuties}</span></div>
                                )}
                                {lp.portFees > 0 && (
                                    <div className="flex justify-between italic"><span className="text-gray-500">الميناء:</span> <span className="font-bold">₪{lp.portFees}</span></div>
                                )}
                                {lp.internalShippingFees > 0 && (
                                    <div className="flex justify-between italic"><span className="text-gray-500">شحن داخلي:</span> <span className="font-bold">₪{lp.internalShippingFees}</span></div>
                                )}
                                {lp.palestinianTaxCustoms > 0 && (
                                    <div className="flex justify-between italic"><span className="text-gray-500">جمركة ضرائب:</span> <span className="font-bold">₪{lp.palestinianTaxCustoms}</span></div>
                                )}
                            </div>
                            <div className="flex justify-between mt-1 pt-1 border-t border-emerald-50 dark:border-emerald-900/50 text-[10px] text-emerald-700 dark:text-emerald-400 font-bold">
                                <span>إجمالي التكاليف المحلية:</span>
                                <span>₪{(
                                    (lp.customsClearanceFees || 0) +
                                    (lp.customsDuties || 0) +
                                    (lp.portFees || 0) +
                                    (lp.internalShippingFees || 0) +
                                    (lp.palestinianTaxCustoms || 0)
                                ).toLocaleString()}</span>
                            </div>
                        </div>
                    )}
                </div>

                <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800">
                    <div className="bg-emerald-600 p-4 rounded-xl shadow-lg shadow-emerald-500/20">
                        <div className="flex justify-between items-center">
                            <div>
                                <span className="text-emerald-100 text-xs block mb-1">المبلغ الإجمالي المطلوب</span>
                                <div className="flex items-baseline gap-1 text-white">
                                    <span className="text-3xl font-black">
                                        {grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                    </span>
                                    <span className="text-lg font-bold opacity-80">{symbol}</span>
                                </div>
                            </div>
                            <div className="p-3 bg-white/20 rounded-lg">
                                <Wallet className="w-8 h-8 text-white" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="p-4 bg-gray-50 dark:bg-gray-800/30 border-t border-gray-100 dark:border-gray-800">
                <p className="text-[10px] text-gray-500 text-center flex items-center justify-center gap-1">
                    <Info className="w-3 h-3" />
                    هذا المبلغ يمثل القيمة الفعلية لقيد المديونية بالشيقل في السجلات المالية.
                </p>
            </div>
        </div>
    );
};
