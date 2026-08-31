import React, { useState, useMemo, useEffect } from 'react';
import { Item, SupplierItemPrice } from '../../../types';
import { Package, X, Search, Hash, DollarSign, Plus } from 'lucide-react';
import { collection, query, where, orderBy, getDocs, limit, db } from "../../../services/sqlApiClient";
import { ItemQuickCreateModal } from '../../items/ItemQuickCreateModal';
import { mapPickerProductToItem } from '../../../utils/pickerProductToItem';

interface ItemSearchModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelectItem: (item: Item, lastPrice?: number) => void;
    items: Item[];
    supplierId?: string;
    /** T-SEARCH: يفتح الفهرس على نفس ما كتبه المستخدم في المنتقي المدمج. */
    initialSearch?: string;
    /** task18 DEF-B2: يُستدعى بعد إنشاء منتج جديد (Product) ليُضيفه الأب إلى قائمة
     *  المنتجات فوراً فيظهر في المنتقي/الإكمال التلقائي ويُعاد اختياره. */
    onItemCreated?: (item: Item) => void;
}

/** task18 DEF-B2: تحويل Product المُنشأ (من inventory) إلى شكل Item الذي يتوقعه
 *  سطر الفاتورة — كان السطر يُعبَّأ بـ name=undefined لأن Product يحمل name_ar.
 *  THA-19: نقطة التحويل الموحّدة — راجع utils/pickerProductToItem.ts للخيارات
 *  التي تحفظ سلوك هذه النافذة بالضبط (فرقها عن الشاشة الكاملة موثَّق هناك). */
export const productToItem = (p: any): Item =>
    mapPickerProductToItem(p, {
        fallbackName: (row) => `منتج ${(row as any).id ?? ""}`,
        categoryIdAcceptsZero: true,
        emptyModelNumberAsUndefined: true,
    });

export const ItemSearchModal: React.FC<ItemSearchModalProps> = ({ isOpen, onClose, onSelectItem, items = [], supplierId, initialSearch = '', onItemCreated }) => {
    const [searchQuery, setSearchQuery] = useState(initialSearch);
    const [itemPrices, setItemPrices] = useState<Record<string, number>>({});
    const [loadingPrices, setLoadingPrices] = useState(false);
    const [showAddItem, setShowAddItem] = useState(false);

    // Filter items based on search
    const filteredItems = useMemo(() => {
        if (!items) return [];
        if (!searchQuery.trim()) return items;
        const lowerQuery = searchQuery.toLowerCase();
        return items.filter(item =>
            item.name.toLowerCase().includes(lowerQuery) ||
            item.modelNumber?.toLowerCase().includes(lowerQuery) ||
            // T-SUPSKU: البحث برقم المورّد — المستخدم يمسك فاتورة دانتير بيده
            // ويكتب رقمها، لا رقمنا الذي لا يعرفه.
            item.supplierCodes?.toLowerCase().includes(lowerQuery) ||
            item.categoryName.toLowerCase().includes(lowerQuery)
        );
    }, [items, searchQuery]);

    /* T-SEARCH: كل فتحةٍ تبدأ من الاستعلام المنقول — النافذة تبقى مركَّبة بين
       الفتحات، فالحالة الابتدائية وحدها لا تكفي لتحديثه. */
    useEffect(() => {
        if (isOpen) setSearchQuery(initialSearch);
    }, [isOpen, initialSearch]);

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
                // console suppressed
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
            <div className="ktra-bg-field dark:ktra-bg-panel rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col border ktra-border-soft dark:ktra-border-soft">
                <div className="p-6 border-b ktra-border-soft dark:ktra-border-soft flex justify-between items-center ktra-bg-panel dark:ktra-bg-panel/50">
                    <div className="flex items-center gap-3">
                        <div className="p-2 ktra-bg-accent-bg dark:ktra-bg-panel/30 rounded-lg">
                            <Package className="w-5 h-5 ktra-text-accent dark:ktra-text-soft" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold ktra-text-ink dark:text-white">إضافة منتج</h3>
                            <p className="text-sm ktra-text-soft dark:ktra-text-soft">اختر منتجاً من القائمة لإضافته </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 ktra-text-soft dark:ktra-text-soft hover:ktra-text-ink dark:hover:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-4 border-b ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel">
                    <div className="relative flex items-center gap-2">
                        <div className="relative flex-1">
                            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 ktra-text-soft dark:ktra-text-soft" />
                            <input
                                type="text"
                                placeholder="ابحث باسم المنتج، رقم الموديل، أو الفئة..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pr-10 pl-4 py-3 rounded-lg border ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel ktra-text-ink dark:text-white focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent transition-all"
                                autoFocus
                            />
                        </div>
                        <button
                            type="button"
                            onClick={() => setShowAddItem(true)}
                            className="flex items-center gap-1 px-4 py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
                        >
                            <Plus className="w-5 h-5" /> إضافة منتج
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-4">
                    {loadingPrices && (
                        <div className="text-center py-4">
                            <div className="inline-flex items-center gap-2 ktra-text-accent dark:ktra-text-soft">
                                <div className="w-4 h-4 border-2 ktra-border-accent dark:ktra-border-soft border-t-transparent rounded-full animate-spin"></div>
                                <span className="text-sm">جاري تحميل آخر الأسعار...</span>
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {filteredItems.slice(0, 50).map(item => (
                            <button
                                key={item.id}
                                onClick={() => onSelectItem(item, itemPrices[item.id])}
                                className="group text-right ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft rounded-xl p-4 hover:ktra-border-soft dark:hover:ktra-border-soft hover:shadow-lg transition-all duration-200 flex gap-4 w-full hover:ktra-bg-panel dark:hover:ktra-bg-panel/50"
                            >
                                <div className="w-16 h-16 flex-shrink-0 ktra-bg-panel dark:ktra-bg-panel rounded-lg flex items-center justify-center overflow-hidden ring-1 ring-gray-200 dark:ring-gray-600 group-hover:ring-blue-300 dark:group-hover:ring-blue-500">
                                    {item.imageUrls?.[0] ? (
                                        <img
                                            src={item.imageUrls[0]}
                                            alt={item.name}
                                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                                        />
                                    ) : (
                                        <Package className="w-8 h-8 ktra-text-soft dark:ktra-text-soft" />
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h4 className="font-bold ktra-text-ink dark:text-white truncate group-hover:ktra-text-accent dark:group-hover:ktra-text-soft transition-colors">
                                        {item.name}
                                    </h4>
                                    <div className="flex flex-wrap gap-2 mt-2">
                                        <span className="text-xs ktra-bg-panel dark:ktra-bg-panel px-2 py-1 rounded ktra-text-soft dark:ktra-text-soft">
                                            {item.categoryName}
                                        </span>
                                        {item.modelNumber && (
                                            <span className="text-xs ktra-bg-accent-bg dark:ktra-bg-panel/30 ktra-text-accent dark:ktra-text-soft px-2 py-1 rounded flex items-center gap-1">
                                                <Hash className="w-3 h-3" /> {item.modelNumber}
                                            </span>
                                        )}
                                        {/* T-SUPSKU: يُعرض رقم المورّد كي يرى المستخدم
                                            **لماذا** طابق المنتجُ ما كتبه. */}
                                        {item.supplierCodes && (
                                            <span
                                                className="text-xs ktra-bg-panel dark:ktra-bg-panel px-2 py-1 rounded ktra-text-soft"
                                                title="رقم المنتج عند المورّد"
                                            >
                                                מק"ט {item.supplierCodes}
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
                            <Package className="w-12 h-12 ktra-text-soft dark:ktra-text-soft mx-auto mb-3" />
                            <p className="ktra-text-soft dark:ktra-text-soft">لم يتم العثور على منتجات تطابق بحثك</p>
                            <p className="text-sm ktra-text-soft dark:ktra-text-soft mt-1">حاول استخدام مصطلحات بحث مختلفة</p>
                        </div>
                    )}
                </div>
            </div>

            {showAddItem && (
                <ItemQuickCreateModal
                    isOpen={showAddItem}
                    onClose={() => setShowAddItem(false)}
                    onSaved={(newProduct) => {
                        setShowAddItem(false);
                        // task18 DEF-B2: طبّع Product→Item فيظهر اسمه في السطر،
                        // وأبلغ الأب ليُضيفه لقائمة المنتجات (يظهر في المنتقي لاحقاً).
                        const item = productToItem(newProduct);
                        onItemCreated?.(item);
                        onSelectItem(item, undefined);
                        onClose();
                    }}
                />
            )}
        </div>
    );
};
