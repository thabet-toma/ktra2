import React from 'react';
import { Package, Tag, Hash, DollarSign, Info, Layers } from 'lucide-react';
import { InvoiceItem } from '@/types';

interface NISItemsTableProps {
    items: InvoiceItem[];
    conversionRate: number;
}

export const NISItemsTable: React.FC<NISItemsTableProps> = ({ items, conversionRate }) => {
    return (
        <div className="overflow-hidden rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm">
            <div className="overflow-x-auto">
                <table className="w-full text-right border-collapse">
                    <thead>
                        <tr className="bg-emerald-50/50 dark:bg-emerald-900/20 border-b border-emerald-100 dark:border-emerald-800/50">
                            <th className="px-6 py-4 text-sm font-bold text-gray-700 dark:text-gray-300">المنتج</th>
                            <th className="px-4 py-4 text-sm font-bold text-gray-700 dark:text-gray-300 text-center">الكمية</th>
                            <th className="px-4 py-4 text-sm font-bold text-gray-700 dark:text-gray-300">سعر الوحدة (₪)</th>
                            <th className="px-6 py-4 text-sm font-bold text-gray-700 dark:text-gray-300">الإجمالي (₪)</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {items.map((item, idx) => {
                            const usdUnitPrice = item.unitPrice / conversionRate;
                            const usdTotalPrice = item.totalPrice / conversionRate;

                            return (
                                <tr key={item.id || idx} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group">
                                    <td className="px-6 py-4">
                                        <div className="flex items-start gap-3">
                                            <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-gray-800 flex-shrink-0 overflow-hidden border border-gray-100 dark:border-gray-700 group-hover:border-emerald-200 transition-colors">
                                                {item.imageUrls?.[0] ? (
                                                    <img src={item.imageUrls[0]} alt={item.name} className="w-full h-full object-cover" />
                                                ) : (
                                                    <div className="w-full h-full flex items-center justify-center text-gray-400">
                                                        <Package className="w-5 h-5" />
                                                    </div>
                                                )}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-bold text-gray-900 dark:text-white truncate">
                                                    {item.name}
                                                </div>
                                                <div className="text-[10px] text-gray-500 flex items-center gap-1 mt-1">
                                                    <Tag className="w-3 h-3" />
                                                    {item.categoryName} {item.modelNumber && ` | ${item.modelNumber}`}
                                                </div>
                                                {item.specifications && (
                                                    <div className="text-[10px] text-gray-400 truncate mt-0.5">
                                                        {item.specifications}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 text-center">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                                            {item.quantity}
                                        </span>
                                    </td>
                                    <td className="px-4 py-4">
                                        <div className="flex flex-col">
                                            <span className="text-sm font-black text-gray-900 dark:text-white">
                                                ₪{item.unitPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </span>
                                            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-0.5">
                                                <DollarSign className="w-2.5 h-2.5" />
                                                ${usdUnitPrice.toFixed(2)}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex flex-col">
                                            <span className="text-sm font-black text-emerald-700 dark:text-emerald-400">
                                                ₪{item.totalPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </span>
                                            <span className="text-[10px] text-gray-400 font-medium flex items-center gap-0.5">
                                                <DollarSign className="w-2.5 h-2.5" />
                                                ${usdTotalPrice.toFixed(2)}
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {items.length === 0 && (
                <div className="p-12 text-center">
                    <Layers className="w-12 h-12 text-gray-200 dark:text-gray-700 mx-auto mb-3" />
                    <p className="text-gray-500 text-sm">لا توجد منتجات في هذه الفاتورة</p>
                </div>
            )}
        </div>
    );
};
