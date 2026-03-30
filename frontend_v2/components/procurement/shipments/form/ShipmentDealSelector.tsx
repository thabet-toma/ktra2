import React, { useState, useMemo } from "react";
import { Deal, Supplier } from "../../../../types"; // تأكد من المسار
import {
    Search, Filter, Calendar, X, CheckCircle2, Package, Truck,
    Factory, AlertCircle, DollarSign, CheckCircle
} from "lucide-react";

interface ShipmentDealSelectorProps {
    isOpen: boolean;
    onClose: () => void;
    allDeals: Deal[];
    existingDealIds: string[]; // الصفقات الموجودة بالفعل في الشحنة لاستثنائها
    allSuppliers: Supplier[];
    onAddDeals: (selectedDealIds: string[]) => void;
}

export const ShipmentDealSelector: React.FC<ShipmentDealSelectorProps> = ({
    isOpen, onClose, allDeals, existingDealIds, allSuppliers, onAddDeals
}) => {
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [searchTerm, setSearchTerm] = useState("");
    const [filterStatus, setFilterStatus] = useState("all");

    // تصفية الصفقات (نستثني المضافة مسبقاً)
    const filteredDeals = useMemo(() => {
        return allDeals.filter(deal => {
            if (existingDealIds.includes(deal.id)) return false; // إخفاء المضافة مسبقاً

            // فلتر البحث
            if (searchTerm) {
                const term = searchTerm.toLowerCase();
                const matches =
                    deal.dealNumber?.toLowerCase().includes(term) ||
                    deal.originalOfferNumber?.toLowerCase().includes(term) ||
                    deal.factoryName?.toLowerCase().includes(term);
                if (!matches) return false;
            }

            // فلتر الحالة (اختياري)
            if (filterStatus !== "all" && deal.status !== filterStatus) return false;

            return true;
        });
    }, [allDeals, existingDealIds, searchTerm, filterStatus]);

    const toggleSelection = (dealId: string) => {
        setSelectedIds(prev => {
            const newSet = new Set(prev);
            if (newSet.has(dealId)) newSet.delete(dealId);
            else newSet.add(dealId);
            return newSet;
        });
    };

    const handleConfirm = () => {
        onAddDeals(Array.from(selectedIds));
        setSelectedIds(new Set());
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col border border-gray-200 dark:border-gray-700">

                {/* Header */}
                <div className="p-5 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-gray-800/50 rounded-t-2xl">
                    <div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                            <Package className="w-6 h-6 text-blue-500" />
                            اختر الصفقات للشحن
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            تم تحديد {selectedIds.size} صفقة
                        </p>
                    </div>
                    <div className="flex gap-3">
                        <button onClick={onClose} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors">
                            <X className="w-5 h-5 text-gray-500" />
                        </button>
                    </div>
                </div>

                {/* Filters */}
                <div className="p-4 border-b border-gray-100 dark:border-gray-800 flex gap-3 bg-white dark:bg-gray-900">
                    <div className="relative flex-1">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                            type="text"
                            placeholder="بحث عن صفقة، مورد، رقم..."
                            className="w-full pl-4 pr-10 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                    {/* يمكنك إضافة المزيد من الفلاتر هنا */}
                </div>

                {/* List */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50/50 dark:bg-black/20 custom-scrollbar">
                    {filteredDeals.length === 0 ? (
                        <div className="text-center py-10 text-gray-400">
                            لا توجد صفقات متاحة للشحن تطابق بحثك.
                        </div>
                    ) : (
                        filteredDeals.map(deal => {
                            const isSelected = selectedIds.has(deal.id);
                            // استخراج الصور
                            const images = deal.items?.flatMap(i => i.imageUrls || []).slice(0, 3) || [];

                            return (
                                <div
                                    key={deal.id}
                                    onClick={() => toggleSelection(deal.id)}
                                    className={`group relative flex items-center gap-4 p-4 rounded-xl border transition-all cursor-pointer hover:shadow-md
                                        ${isSelected
                                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-500 ring-1 ring-blue-500'
                                            : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700'
                                        }`}
                                >
                                    {/* Checkbox */}
                                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors
                                        ${isSelected
                                            ? 'bg-blue-500 border-blue-500 text-white'
                                            : 'border-gray-300 dark:border-gray-600 text-transparent group-hover:border-blue-400'
                                        }`}>
                                        <CheckCircle2 className="w-4 h-4" />
                                    </div>

                                    {/* Images */}
                                    <div className="flex -space-x-3 rtl:space-x-reverse">
                                        {images.length > 0 ? images.map((img, i) => (
                                            <img key={i} src={img} className="w-12 h-12 rounded-lg border-2 border-white dark:border-gray-800 object-cover shadow-sm" />
                                        )) : (
                                            <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-gray-400">
                                                <Package className="w-5 h-5" />
                                            </div>
                                        )}
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="font-bold text-gray-900 dark:text-white text-base">
                                                {deal.originalOfferNumber || deal.dealNumber}
                                            </span>
                                            <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded-md text-gray-600 dark:text-gray-300">
                                                {new Date(deal.createdAt).toLocaleDateString('en-GB')}
                                            </span>
                                        </div>
                                        <div className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-2">
                                            <Factory className="w-3.5 h-3.5" />
                                            {deal.factoryName || "مورد غير محدد"}
                                            <span className="text-gray-300">|</span>
                                            <span>{deal.items?.length || 0} منتجات</span>
                                        </div>
                                    </div>

                                    {/* Stats */}
                                    <div className="flex items-center gap-6 text-sm">
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500">الوزن</div>
                                            <div className="font-bold dark:text-gray-200">{(deal.totalWeight || 0).toLocaleString()} kg</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500">الحجم</div>
                                            <div className="font-bold dark:text-gray-200">{(deal.totalVolume || 0).toLocaleString()} cbm</div>
                                        </div>
                                        <div className="text-center px-3 py-1 bg-gray-100 dark:bg-gray-900 rounded-lg">
                                            <div className="text-xs text-gray-500">الإجمالي</div>
                                            <div className="font-bold text-blue-600 dark:text-blue-400">${(deal.totalAmount || 0).toLocaleString()}</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>

                {/* Footer */}
                <div className="p-5 border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 rounded-b-2xl flex justify-between items-center">
                    <span className="text-sm text-gray-500">
                        {selectedIds.size > 0 ? `تم اختيار ${selectedIds.size} صفقة` : 'لم يتم اختيار أي صفقة'}
                    </span>
                    <div className="flex gap-3">
                        <button
                            onClick={onClose}
                            className="px-5 py-2.5 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl transition-colors font-medium"
                        >
                            إلغاء
                        </button>
                        <button
                            onClick={handleConfirm}
                            disabled={selectedIds.size === 0}
                            className="px-8 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl shadow-lg shadow-blue-500/20 transition-all font-bold disabled:opacity-50 disabled:shadow-none"
                        >
                            إضافة ({selectedIds.size})
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};