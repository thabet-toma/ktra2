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
        <div className="aseel-bg-field dark:aseel-bg-panel p-6 rounded-2xl shadow-sm border aseel-border-soft dark:aseel-border-soft overflow-hidden">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h3 className="text-lg font-bold dark:text-white flex items-center gap-2">
                        <Package className="w-5 h-5 text-[var(--color-primary)]" /> الصفقات وتوزيع التكلفة
                    </h3>
                    <p className="text-[11px] aseel-text-soft dark:aseel-text-soft mt-1 max-w-3xl leading-relaxed">
                        عمود «حصة الشحن + إضافي» يعرض فقط نصيب الصفقة من تكلفة الشحن الدولي للشحنة (بالدولار)، وليس
                        إجمالي سعر البضاعة. سعر الصفقة المعروض في قائمة الصفقات يطابق «إجمالي الصفقة» أدناه عند توفر
                        بيانات الصفقة كاملة.
                    </p>
                </div>
                <button
                    onClick={onOpenSelector}
                    className="flex items-center gap-2 px-4 py-2 aseel-bg-accent hover:aseel-bg-accent text-white rounded-xl text-sm font-bold shadow-md shadow-blue-500/20 transition-all"
                >
                    <PlusCircle className="w-4 h-4" />
                    إضافة صفقات
                </button>
            </div>

            {deals && deals.length > 0 ? (
                <div className="overflow-x-auto">
                    <table className="w-full text-right border-separate border-spacing-y-2">
                        <thead className="aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft text-xs uppercase">
                            <tr>
                                <th className="px-3 py-3 rounded-r-xl">الصفقة</th>
                                <th className="px-2 py-3 text-center">الوزن/الحجم</th>
                                <th className="px-3 py-3 aseel-text-accent">التكلفة الموزعة</th>
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
                                    <tr key={dealInfo.dealId} className="aseel-bg-panel/50 dark:aseel-bg-panel/50 hover:aseel-bg-field dark:hover:aseel-bg-panel transition-colors shadow-sm">
                                        <td className="px-3 py-3 rounded-r-xl">
                                            <div className="font-bold dark:text-white">{title}</div>
                                            {subLine && subLine !== title ? (
                                                <div className="text-xs aseel-text-soft font-mono">{subLine}</div>
                                            ) : null}
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft space-y-0.5">
                                                <div>
                                                    <span className="aseel-text-soft dark:aseel-text-soft">
                                                        إجمالي الصفقة:{" "}
                                                    </span>
                                                    <span className="font-semibold tabular-nums">
                                                        ${computedGrand.toLocaleString(undefined, {
                                                            maximumFractionDigits: 0,
                                                        })}
                                                    </span>
                                                </div>
                                                {showBothTotals ? (
                                                    <div className="text-[10px] aseel-text-soft dark:aseel-text-soft">
                                                        حقل الإجمالي المسجّل: $
                                                        {contractTotal.toLocaleString(undefined, {
                                                            maximumFractionDigits: 0,
                                                        })}
                                                    </div>
                                                ) : null}
                                            </div>
                                        </td>
                                        <td className="px-2 py-3 text-center font-mono text-xs dark:aseel-text-soft">
                                            <div>{Number(weightKg).toLocaleString()} kg</div>
                                            <div className="aseel-text-soft">{Number(volume).toLocaleString()} cbm</div>
                                        </td>
                                        <td className="px-3 py-3 font-bold aseel-text-accent dark:aseel-text-soft">
                                            ${dealInfo.distributedCost.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                                        </td>
                                        <td className="px-2 py-3">
                                            <input
                                                type="number" min="0"
                                                className="w-full p-1.5 text-sm border aseel-border-soft dark:aseel-border-soft rounded-lg dark:aseel-bg-panel focus:ring-2 outline-none"
                                                value={dealInfo.extraCosts || ''}
                                                onChange={(e) => onUpdateDeal(dealInfo.dealId, 'extraCosts', parseFloat(e.target.value) || 0)}
                                            />
                                        </td>
                                        <td className="px-2 py-3">
                                            <input
                                                type="text"
                                                className="w-full p-1.5 text-xs border aseel-border-soft dark:aseel-border-soft rounded-lg dark:aseel-bg-panel outline-none"
                                                value={dealInfo.notes || ''}
                                                onChange={(e) => onUpdateDeal(dealInfo.dealId, 'notes', e.target.value)}
                                            />
                                        </td>
                                        <td className="px-2 py-3 font-bold dark:text-white">
                                            ${dealTotalCost.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                                        </td>
                                        <td className="px-2 py-3 rounded-l-xl text-left">
                                            <button onClick={() => onRemoveDeal(dealInfo.dealId)} className="aseel-text-soft hover:aseel-text-state p-1">
                                                <X className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                            <tr className="aseel-bg-panel dark:aseel-bg-panel border-t-2 aseel-border-soft dark:aseel-border-soft">
                                <td colSpan={2} className="px-4 py-4 font-bold aseel-text-ink dark:aseel-text-soft text-left">
                                    مجموع توزيع الشحن (+ إضافي):
                                </td>
                                <td className="px-3 py-4 font-bold aseel-text-accent dark:aseel-text-soft">
                                    ${sumDistributed.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                </td>
                                <td className="px-2 py-4 font-bold aseel-text-state dark:aseel-text-soft">+ ${totalExtra.toLocaleString()}</td>
                                <td></td>
                                <td className="px-2 py-4 font-black text-lg dark:text-white">= ${grandTotal.toLocaleString()}</td>
                                <td></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="text-center py-12 aseel-bg-panel dark:aseel-bg-panel/50 rounded-2xl border-2 border-dashed aseel-border-soft dark:aseel-border-soft">
                    <p className="aseel-text-soft dark:aseel-text-soft">أضف صفقات لحساب التكلفة</p>
                </div>
            )}
        </div>
    );
};