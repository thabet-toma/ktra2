import React from 'react';
import { Package, X, PlusCircle } from 'lucide-react';
import { effectiveDealTitleForDisplay } from '../../../../utils/dealTitleDisplay';
import { getDealGrandTotalUsd } from '../../../../utils/dealGrandTotalUsd';
import type { Deal } from '../../../../types';

interface ShipmentDealsTableProps {
    deals: any[];
    allDeals: any[];
    onRemoveDeal: (id: string) => void;
    onUpdateDeal: (id: string, field: string, value: any) => void;
    onOpenSelector: () => void;
    totalExtra: number;
    grandTotal: number;
}

export const ShipmentDealsTable: React.FC<ShipmentDealsTableProps> = ({
    deals, allDeals, onRemoveDeal, onUpdateDeal, onOpenSelector, totalExtra, grandTotal
}) => {
    const sumDistributed = (deals || []).reduce(
        (s, d) => s + (Number((d as { distributedCost?: number }).distributedCost) || 0),
        0
    );
    return (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h3 className="text-lg font-bold dark:text-white flex items-center gap-2">
                        <Package className="w-5 h-5 text-purple-500" /> الصفقات وتوزيع التكلفة
                    </h3>
                    <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1 max-w-3xl leading-relaxed">
                        عمود «حصة الشحن + إضافي» يعرض فقط نصيب الصفقة من تكلفة الشحن الدولي للشحنة (بالدولار)، وليس
                        إجمالي سعر البضاعة. سعر الصفقة المعروض في قائمة الصفقات يطابق «إجمالي الصفقة» أدناه عند توفر
                        بيانات الصفقة كاملة.
                    </p>
                </div>
                <button
                    onClick={onOpenSelector}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-bold shadow-md shadow-blue-500/20 transition-all"
                >
                    <PlusCircle className="w-4 h-4" />
                    إضافة صفقات
                </button>
            </div>

            {deals && deals.length > 0 ? (
                <div className="overflow-x-auto">
                    <table className="w-full text-right border-separate border-spacing-y-2">
                        <thead className="bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs uppercase">
                            <tr>
                                <th className="px-3 py-3 rounded-r-xl">الصفقة</th>
                                <th className="px-2 py-3 text-center">الوزن/الحجم</th>
                                <th className="px-3 py-3 text-blue-600">التكلفة الموزعة</th>
                                <th className="px-2 py-3 w-32">تكاليف إضافية</th>
                                <th className="px-2 py-3 w-40">ملاحظات</th>
                                <th className="px-2 py-3">حصة الشحن + إضافي</th>
                                <th className="px-2 py-3 rounded-l-xl"></th>
                            </tr>
                        </thead>
                        <tbody className="text-sm">
                            {deals.map((dealInfo) => {
                                const fullDeal = allDeals.find((d) => String(d.id) === String(dealInfo.dealId)) as
                                    | Deal
                                    | undefined;
                                const notesRow = (
                                    fullDeal?.internalNotes ||
                                    dealInfo.notes ||
                                    ''
                                ).trim();
                                const title = effectiveDealTitleForDisplay({
                                    description:
                                        fullDeal?.dealDescription || dealInfo.dealDescriptionRaw,
                                    notes: notesRow || undefined,
                                    original_offer_number:
                                        fullDeal?.originalOfferNumber || dealInfo.originalOfferNumber,
                                    ref_number: fullDeal?.dealNumber || dealInfo.dealNumber,
                                });
                                const subLine = fullDeal?.dealNumber || dealInfo.dealNumber || '';
                                const contractTotal = Number(
                                    fullDeal?.totalAmount ?? dealInfo.totalAmount ?? 0
                                );
                                const computedGrand = fullDeal ? getDealGrandTotalUsd(fullDeal) : contractTotal;
                                const showBothTotals =
                                    fullDeal &&
                                    contractTotal > 0 &&
                                    Math.abs(computedGrand - contractTotal) >= 0.5;
                                const weightKg =
                                    fullDeal?.totalWeightKg ??
                                    fullDeal?.totalWeight ??
                                    dealInfo.totalWeightKg ??
                                    0;
                                const volume = Number(
                                    (fullDeal != null ? fullDeal.totalVolume : null) ??
                                        dealInfo.totalVolume ??
                                        0
                                );
                                const dealTotalCost = (dealInfo.distributedCost || 0) + (dealInfo.extraCosts || 0);

                                return (
                                    <tr key={dealInfo.dealId} className="bg-gray-50/50 dark:bg-gray-900/50 hover:bg-white dark:hover:bg-gray-800 transition-colors shadow-sm">
                                        <td className="px-3 py-3 rounded-r-xl">
                                            <div className="font-bold dark:text-white">{title}</div>
                                            {subLine && subLine !== title ? (
                                                <div className="text-xs text-gray-500 font-mono">{subLine}</div>
                                            ) : null}
                                            <div className="text-xs text-gray-600 dark:text-gray-300 space-y-0.5">
                                                <div>
                                                    <span className="text-gray-500 dark:text-gray-400">
                                                        إجمالي الصفقة:{" "}
                                                    </span>
                                                    <span className="font-semibold tabular-nums">
                                                        ${computedGrand.toLocaleString(undefined, {
                                                            maximumFractionDigits: 0,
                                                        })}
                                                    </span>
                                                </div>
                                                {showBothTotals ? (
                                                    <div className="text-[10px] text-gray-400 dark:text-gray-500">
                                                        حقل الإجمالي المسجّل: $
                                                        {contractTotal.toLocaleString(undefined, {
                                                            maximumFractionDigits: 0,
                                                        })}
                                                    </div>
                                                ) : null}
                                            </div>
                                        </td>
                                        <td className="px-2 py-3 text-center font-mono text-xs dark:text-gray-300">
                                            <div>{Number(weightKg).toLocaleString()} kg</div>
                                            <div className="text-gray-400">{Number(volume).toLocaleString()} cbm</div>
                                        </td>
                                        <td className="px-3 py-3 font-bold text-blue-600 dark:text-blue-400">
                                            ${dealInfo.distributedCost.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                                        </td>
                                        <td className="px-2 py-3">
                                            <input
                                                type="number" min="0"
                                                className="w-full p-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg dark:bg-gray-800 focus:ring-2 outline-none"
                                                value={dealInfo.extraCosts || ''}
                                                onChange={(e) => onUpdateDeal(dealInfo.dealId, 'extraCosts', parseFloat(e.target.value) || 0)}
                                            />
                                        </td>
                                        <td className="px-2 py-3">
                                            <input
                                                type="text"
                                                className="w-full p-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg dark:bg-gray-800 outline-none"
                                                value={dealInfo.notes || ''}
                                                onChange={(e) => onUpdateDeal(dealInfo.dealId, 'notes', e.target.value)}
                                            />
                                        </td>
                                        <td className="px-2 py-3 font-bold dark:text-white">
                                            ${dealTotalCost.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                                        </td>
                                        <td className="px-2 py-3 rounded-l-xl text-left">
                                            <button onClick={() => onRemoveDeal(dealInfo.dealId)} className="text-red-400 hover:text-red-600 p-1">
                                                <X className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                            <tr className="bg-gray-100 dark:bg-gray-800 border-t-2 border-gray-200 dark:border-gray-700">
                                <td colSpan={2} className="px-4 py-4 font-bold text-gray-700 dark:text-gray-300 text-left">
                                    مجموع توزيع الشحن (+ إضافي):
                                </td>
                                <td className="px-3 py-4 font-bold text-blue-600 dark:text-blue-400">
                                    ${sumDistributed.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                </td>
                                <td className="px-2 py-4 font-bold text-red-600 dark:text-red-400">+ ${totalExtra.toLocaleString()}</td>
                                <td></td>
                                <td className="px-2 py-4 font-black text-lg dark:text-white">= ${grandTotal.toLocaleString()}</td>
                                <td></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="text-center py-12 bg-gray-50 dark:bg-gray-900/50 rounded-2xl border-2 border-dashed border-gray-200 dark:border-gray-700">
                    <p className="text-gray-500 dark:text-gray-400">أضف صفقات لحساب التكلفة</p>
                </div>
            )}
        </div>
    );
};