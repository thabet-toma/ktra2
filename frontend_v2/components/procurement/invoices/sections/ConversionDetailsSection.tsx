import React from 'react';
import { Calculator, TrendingUp, DollarSign, Globe, ArrowRightLeft, Info, HelpCircle } from 'lucide-react';

interface ConversionMetadata {
    dealEffectiveRate: number;
    shipmentEffectiveRate: number;
    internalShippingUsd: number;
    globalShippingUsd: number;
    extraCostsUsd: number;
    totalUsd: number;
    remainingBalanceRate: number;
}

interface ConversionDetailsSectionProps {
    metadata?: ConversionMetadata;
}

export const ConversionDetailsSection: React.FC<ConversionDetailsSectionProps> = ({ metadata }) => {
    if (!metadata) return null;

    const {
        dealEffectiveRate,
        shipmentEffectiveRate,
        internalShippingUsd,
        globalShippingUsd,
        extraCostsUsd,
        totalUsd,
        remainingBalanceRate,
    } = metadata;

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-blue-100 dark:border-blue-900/30 overflow-hidden shadow-sm">
            <div className="bg-gradient-to-r from-blue-600 to-indigo-700 p-4">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-white/20 rounded-lg">
                        <ArrowRightLeft className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-white">تفاصيل عملية التحويل (USD ➔ ILS)</h3>
                        <p className="text-blue-100 text-xs">شرح كيف تم حساب القيم من الدولار إلى الشيقل</p>
                    </div>
                </div>
            </div>

            <div className="p-6 space-y-8">
                {/* أسعار الصرف الأساسية */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="p-4 rounded-xl bg-blue-50/50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-800/30">
                        <div className="flex items-center gap-2 mb-3">
                            <TrendingUp className="w-4 h-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900 dark:text-blue-100">سعر صرف البنود (المرجح)</span>
                        </div>
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-black text-blue-700 dark:text-blue-400">{dealEffectiveRate.toFixed(4)}</span>
                            <span className="text-xs text-blue-500 font-medium">₪ للدولار الواحد</span>
                        </div>
                        <p className="mt-2 text-[10px] text-gray-500 flex items-center gap-1">
                            <Info className="w-3 h-3" />
                            يشمل المبالغ المدفوعة والمتبقية (بسعر {remainingBalanceRate})
                        </p>
                    </div>

                    <div className="p-4 rounded-xl bg-indigo-50/50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-800/30">
                        <div className="flex items-center gap-2 mb-3">
                            <Globe className="w-4 h-4 text-indigo-600" />
                            <span className="text-sm font-bold text-indigo-900 dark:text-indigo-100">سعر صرف الشحن الدولي</span>
                        </div>
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-black text-indigo-700 dark:text-indigo-400">{shipmentEffectiveRate.toFixed(4)}</span>
                            <span className="text-xs text-indigo-500 font-medium">₪ للدولار الواحد</span>
                        </div>
                        <p className="mt-2 text-[10px] text-gray-500 flex items-center gap-1">
                            <Info className="w-3 h-3" />
                            يستخدم لحساب تكاليف الشحن الدولي والمصاريف الإضافية
                        </p>
                    </div>
                </div>

                {/* تفاصيل الشحن */}
                <div className="space-y-4">
                    <h4 className="flex items-center gap-2 text-sm font-bold text-gray-700 dark:text-gray-300">
                        <Calculator className="w-4 h-4 text-gray-400" />
                        تحليل تكاليف الشحن (Shipping Breakdown)
                    </h4>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="p-3 bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-lg">
                            <span className="text-[10px] text-gray-500 block mb-1">شحن داخلي (بالصين)</span>
                            <div className="flex justify-between items-center text-sm font-bold">
                                <span className="text-gray-400">${internalShippingUsd}</span>
                                <span className="text-blue-600">₪{(internalShippingUsd * dealEffectiveRate).toLocaleString()}</span>
                            </div>
                        </div>

                        <div className="p-3 bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-lg">
                            <span className="text-[10px] text-gray-500 block mb-1">شحن دولي (موزع)</span>
                            <div className="flex justify-between items-center text-sm font-bold">
                                <span className="text-gray-400">${globalShippingUsd}</span>
                                <span className="text-indigo-600">₪{(globalShippingUsd * shipmentEffectiveRate).toLocaleString()}</span>
                            </div>
                        </div>

                        <div className="p-3 bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-lg">
                            <span className="text-[10px] text-gray-500 block mb-1">مصاريف شحنة إضافية</span>
                            <div className="flex justify-between items-center text-sm font-bold">
                                <span className="text-gray-400">${extraCostsUsd}</span>
                                <span className="text-indigo-600">₪{(extraCostsUsd * shipmentEffectiveRate).toLocaleString()}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* تنويه */}
                <div className="p-3 bg-amber-50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-900/30 rounded-lg flex gap-3">
                    <HelpCircle className="w-5 h-5 text-amber-500 shrink-0" />
                    <p className="text-[11px] text-amber-700 dark:text-amber-300 leading-relaxed">
                        تم حساب هذه الفاتورة بناءً على صفقات سابقة بالدولار. جميع الأسعار الظاهرة في الجداول الداخلية (سعر الوحدة، الإجمالي)
                        هي قيم محولة إلى الشيقل لضمان دقة قيود المديونية ومصروفات العمل.
                    </p>
                </div>
            </div>
        </div>
    );
};
