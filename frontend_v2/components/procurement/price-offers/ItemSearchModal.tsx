import React, { useState, useMemo, useEffect } from 'react';
import { Item, SupplierItemPrice } from '../../../types';
import { Package, X, Search, Hash, DollarSign } from 'lucide-react';
import { collection, query, where, orderBy, getDocs, limit, db } from "../../../services/sqlApiClient";

interface ItemSearchModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelectItem: (item: Item, lastPrice?: number) => void;
    items: Item[];
    supplierId?: string;
}

export const ItemSearchModal: React.FC<ItemSearchModalProps> = ({ isOpen, onClose, onSelectItem, items = [], supplierId }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [itemPrices, setItemPrices] = useState<Record<string, number>>({});
    const [loadingPrices, setLoadingPrices] = useState(false);

    // Filter items based on search
    const filteredItems = useMemo(() => {
        if (!items) return [];
        if (!searchQuery.trim()) return items;
        const lowerQuery = searchQuery.toLowerCase();
        return items.filter(item =>
            item.name.toLowerCase().includes(lowerQuery) ||
            item.modelNumber?.toLowerCase().includes(lowerQuery) ||
            item.categoryName.toLowerCase().includes(lowerQuery)
        );
    }, [items, searchQuery]);

    // Fetch last prices for filtered items from this supplier
    useEffect(() => {
        const fetchPrices = async () => {
            if (!supplierId || !isOpen) return;

            setLoadingPrices(true);
            const prices: Record<string, number> = {};

            const targetItems = filteredItems.slice(0, 20);

            try {
                await Promise.all(
                    targetItems.map(async (item) => {
                        const q = query(
                            collection(db, "supplier_prices"),
                            where("supplierId", "==", supplierId),
                            where("itemId", "==", item.id),
                            orderBy("date", "desc"),
                            limit(1)
                        );
                        const snapshot = await getDocs(q);
                        if (!snapshot.empty) {
                            const data = snapshot.docs[0].data() as SupplierItemPrice;
                            prices[item.id] = data.price;
                        }
                    })
                );
                setItemPrices(prices);
            } catch (error) {
                console.error("Error fetching item prices:", error);
            } finally {
                setLoadingPrices(false);
            }
        };

        const debounceTimer = setTimeout(() => {
            fetchPrices();
        }, 500);

        return () => clearTimeout(debounceTimer);
    }, [filteredItems, supplierId, isOpen]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col border border-gray-200 dark:border-gray-700">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-900/50">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                            <Package className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white">إضافة صنف</h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400">اختر منتجاً من القائمة لإضافته </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
                    <div className="relative">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 dark:text-gray-500" />
                        <input
                            type="text"
                            placeholder="ابحث باسم المنتج، رقم الموديل، أو الفئة..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pr-10 pl-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent transition-all"
                            autoFocus
                        />
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-4">
                    {loadingPrices && (
                        <div className="text-center py-4">
                            <div className="inline-flex items-center gap-2 text-blue-600 dark:text-blue-400">
                                <div className="w-4 h-4 border-2 border-blue-600 dark:border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                                <span className="text-sm">جاري تحميل آخر الأسعار...</span>
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {filteredItems.slice(0, 50).map(item => (
                            <button
                                key={item.id}
                                onClick={() => onSelectItem(item, itemPrices[item.id])}
                                className="group text-right bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 hover:border-blue-500 dark:hover:border-blue-400 hover:shadow-lg transition-all duration-200 flex gap-4 w-full hover:bg-gray-50 dark:hover:bg-gray-700/50"
                            >
                                <div className="w-16 h-16 flex-shrink-0 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center overflow-hidden ring-1 ring-gray-200 dark:ring-gray-600 group-hover:ring-blue-300 dark:group-hover:ring-blue-500">
                                    {item.imageUrls?.[0] ? (
                                        <img
                                            src={item.imageUrls[0]}
                                            alt={item.name}
                                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                                        />
                                    ) : (
                                        <Package className="w-8 h-8 text-gray-400 dark:text-gray-500" />
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h4 className="font-bold text-gray-900 dark:text-white truncate group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                                        {item.name}
                                    </h4>
                                    <div className="flex flex-wrap gap-2 mt-2">
                                        <span className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-gray-600 dark:text-gray-300">
                                            {item.categoryName}
                                        </span>
                                        {item.modelNumber && (
                                            <span className="text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded flex items-center gap-1">
                                                <Hash className="w-3 h-3" /> {item.modelNumber}
                                            </span>
                                        )}
                                    </div>
                                    {itemPrices[item.id] !== undefined && (
                                        <div className="mt-3 flex items-center gap-1 text-sm">
                                            <DollarSign className="w-3 h-3 text-green-500" />
                                            <span className="font-bold text-green-600 dark:text-green-400">
                                                آخر سعر: {itemPrices[item.id].toLocaleString()} $
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </button>
                        ))}
                    </div>

                    {filteredItems.length === 0 && (
                        <div className="text-center py-12">
                            <Package className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                            <p className="text-gray-500 dark:text-gray-400">لم يتم العثور على منتجات تطابق بحثك</p>
                            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">حاول استخدام مصطلحات بحث مختلفة</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
