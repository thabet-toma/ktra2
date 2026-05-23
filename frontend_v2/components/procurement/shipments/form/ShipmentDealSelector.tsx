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
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col border aseel-border-soft dark:aseel-border-soft">

                {/* Header */}
                <div className="p-5 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center aseel-bg-panel dark:aseel-bg-panel/50 rounded-t-2xl">
                    <div>
                        <h3 className="text-xl font-bold aseel-text-ink dark:text-white flex items-center gap-2">
                            <Package className="w-6 h-6 aseel-text-soft" />
                            اختر الصفقات للشحن
                        </h3>
                        <p className="text-sm aseel-text-soft dark:aseel-text-soft mt-1">
                            تم تحديد {selectedIds.size} صفقة
                        </p>
                    </div>
                    <div className="flex gap-3">
                        <button onClick={onClose} className="p-2 hover:aseel-bg-grid-head dark:hover:aseel-bg-panel rounded-full transition-colors">
                            <X className="w-5 h-5 aseel-text-soft" />
                        </button>
                    </div>
                </div>

                {/* Filters */}
                <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft flex gap-3 aseel-bg-field dark:aseel-bg-panel">
                    <div className="relative flex-1">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 aseel-text-soft" />
                        <input
                            type="text"
                            placeholder="بحث عن صفقة، مورد، رقم..."
                            className="w-full pl-4 pr-10 py-2.5 aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                    {/* يمكنك إضافة المزيد من الفلاتر هنا */}
                </div>

                {/* List */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3 aseel-bg-panel/50 dark:bg-black/20 custom-scrollbar">
                    {filteredDeals.length === 0 ? (
                        <div className="text-center py-10 aseel-text-soft">
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
                                            ? 'aseel-bg-accent-bg dark:aseel-bg-panel/20 aseel-border-soft dark:aseel-border-soft ring-1 ring-blue-500'
                                            : 'aseel-bg-field dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft hover:aseel-border-soft dark:hover:aseel-border-soft'
                                        }`}
                                >
                                    {/* Checkbox */}
                                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors
                                        ${isSelected
                                            ? 'aseel-bg-accent-bg aseel-border-soft text-white'
                                            : 'aseel-border-soft dark:aseel-border-soft text-transparent group-hover:aseel-border-soft'
                                        }`}>
                                        <CheckCircle2 className="w-4 h-4" />
                                    </div>

                                    {/* Images */}
                                    <div className="flex -space-x-3 rtl:space-x-reverse">
                                        {images.length > 0 ? images.map((img, i) => (
                                            <img key={i} src={img} className="w-12 h-12 rounded-lg border-2 border-white dark:aseel-border-soft object-cover shadow-sm" />
                                        )) : (
                                            <div className="w-12 h-12 rounded-lg aseel-bg-panel dark:aseel-bg-panel flex items-center justify-center aseel-text-soft">
                                                <Package className="w-5 h-5" />
                                            </div>
                                        )}
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="font-bold aseel-text-ink dark:text-white text-base">
                                                {deal.originalOfferNumber || deal.dealNumber}
                                            </span>
                                            <span className="text-xs px-2 py-0.5 aseel-bg-panel dark:aseel-bg-panel rounded-md aseel-text-soft dark:aseel-text-soft">
                                                {new Date(deal.createdAt).toLocaleDateString('en-GB')}
                                            </span>
                                        </div>
                                        <div className="text-sm aseel-text-soft dark:aseel-text-soft flex items-center gap-2">
                                            <Factory className="w-3.5 h-3.5" />
                                            {deal.factoryName || "مورد غير محدد"}
                                            <span className="aseel-text-soft">|</span>
                                            <span>{deal.items?.length || 0} منتجات</span>
                                        </div>
                                    </div>

                                    {/* Stats */}
                                    <div className="flex items-center gap-6 text-sm">
                                        <div className="text-center">
                                            <div className="text-xs aseel-text-soft">الوزن</div>
                                            <div className="font-bold dark:aseel-text-soft">{(deal.totalWeight || 0).toLocaleString()} kg</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs aseel-text-soft">الحجم</div>
                                            <div className="font-bold dark:aseel-text-soft">{(deal.totalVolume || 0).toLocaleString()} cbm</div>
                                        </div>
                                        <div className="text-center px-3 py-1 aseel-bg-panel dark:aseel-bg-panel rounded-lg">
                                            <div className="text-xs aseel-text-soft">الإجمالي</div>
                                            <div className="font-bold aseel-text-accent dark:aseel-text-soft">${(deal.totalAmount || 0).toLocaleString()}</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>

                {/* Footer */}
                <div className="p-5 border-t aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-b-2xl flex justify-between items-center">
                    <span className="text-sm aseel-text-soft">
                        {selectedIds.size > 0 ? `تم اختيار ${selectedIds.size} صفقة` : 'لم يتم اختيار أي صفقة'}
                    </span>
                    <div className="flex gap-3">
                        <button
                            onClick={onClose}
                            className="px-5 py-2.5 aseel-text-soft dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-xl transition-colors font-medium"
                        >
                            إلغاء
                        </button>
                        <button
                            onClick={handleConfirm}
                            disabled={selectedIds.size === 0}
                            className="px-8 py-2.5 aseel-bg-accent hover:aseel-bg-accent text-white rounded-xl shadow-lg shadow-blue-500/20 transition-all font-bold disabled:opacity-50 disabled:shadow-none"
                        >
                            إضافة ({selectedIds.size})
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};