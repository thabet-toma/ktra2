import React from 'react';
import { Package, X, PlusCircle } from 'lucide-react';

interface ShipmentDealsTableProps {
    deals: any[];
    allDeals: any[];
    onRemoveDeal: (id: string) => void;
    onUpdateDeal: (id: string, field: string, value: any) => void;
    onOpenSelector: () => void;
    totalBase: number;
    totalExtra: number;
    grandTotal: number;
}

export const ShipmentDealsTable: React.FC<ShipmentDealsTableProps> = ({
    deals, allDeals, onRemoveDeal, onUpdateDeal, onOpenSelector, totalBase, totalExtra, grandTotal
}) => {
    return (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-bold dark:text-white flex items-center gap-2">
                    <Package className="w-5 h-5 text-purple-500" /> الصفقات وتوزيع التكلفة
                </h3>
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
                                <th className="px-2 py-3">المجموع للصفقة</th>
                                <th className="px-2 py-3 rounded-l-xl"></th>
                            </tr>
                        </thead>
                        <tbody className="text-sm">
                            {deals.map((dealInfo) => {
                                const fullDeal = allDeals.find(d => d.id === dealInfo.dealId);
                                const weight = fullDeal?.totalWeight || 0;
                                const dealTotalCost = (dealInfo.distributedCost || 0) + (dealInfo.extraCosts || 0);

                                return (
                                    <tr key={dealInfo.dealId} className="bg-gray-50/50 dark:bg-gray-900/50 hover:bg-white dark:hover:bg-gray-800 transition-colors shadow-sm">
                                        <td className="px-3 py-3 rounded-r-xl">
                                            <div className="font-bold dark:text-white">{dealInfo.originalOfferNumber}</div>
                                            <div className="text-xs text-gray-500">${dealInfo.totalAmount?.toLocaleString()}</div>
                                        </td>
                                        <td className="px-2 py-3 text-center font-mono text-xs dark:text-gray-300">
                                            <div>{weight.toLocaleString()} kg</div>
                                            <div className="text-gray-400">{dealInfo.totalVolume} cbm</div>
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
                                <td colSpan={2} className="px-4 py-4 font-bold text-gray-700 dark:text-gray-300 text-left">المجاميع:</td>
                                <td className="px-3 py-4 font-bold text-blue-600 dark:text-blue-400">${totalBase.toLocaleString()}</td>
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