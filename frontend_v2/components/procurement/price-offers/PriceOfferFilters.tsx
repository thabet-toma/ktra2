import React, { useState, useMemo } from 'react';
import { Search, Package, X, ChevronDown, Building, Tag, Calendar, SlidersHorizontal, Filter } from 'lucide-react';
import { Supplier, Item, PriceOfferStatus } from '../../../types';

interface PriceOfferFiltersProps {
    searchTerm: string;
    onSearchChange: (value: string) => void;
    selectedSupplierId: string;
    onSupplierChange: (id: string) => void;
    selectedItemIds: string[];
    onItemsChange: (ids: string[]) => void;
    selectedStatus: PriceOfferStatus | 'all';
    onStatusChange: (status: PriceOfferStatus | 'all') => void;
    dateRange: { start: string; end: string };
    onDateRangeChange: (range: { start: string; end: string }) => void;
    suppliers: Supplier[];
    items: Item[];
    offersCount: number;
    filteredCount: number;
}

const statusOptions: { value: PriceOfferStatus | 'all'; label: string }[] = [
    { value: 'all', label: 'كل الحالات' },
    { value: 'initial', label: 'مبدئي' },
    { value: 'pending_info', label: 'بانتظار معلومات' },
    { value: 'under_discussion', label: 'قيد المناقشة' },
    { value: 'approved_for_shipping', label: 'معتمد للشراء' },
    { value: 'rejected', label: 'مرفوض' },
];

export const PriceOfferFilters: React.FC<PriceOfferFiltersProps> = ({
    searchTerm,
    onSearchChange,
    selectedSupplierId,
    onSupplierChange,
    selectedItemIds,
    onItemsChange,
    selectedStatus,
    onStatusChange,
    dateRange,
    onDateRangeChange,
    suppliers,
    items,
    offersCount,
    filteredCount,
}) => {
    const [showItemsDropdown, setShowItemsDropdown] = useState(false);
    const [itemSearch, setItemSearch] = useState('');

    const filteredItems = useMemo(() => {
        if (!itemSearch.trim()) return items;
        const searchLower = itemSearch.toLowerCase();
        return items.filter(item =>
            item.name.toLowerCase().includes(searchLower) ||
            (item.modelNumber && item.modelNumber.toLowerCase().includes(searchLower))
        );
    }, [items, itemSearch]);

    const handleItemToggle = (itemId: string) => {
        const newSelected = selectedItemIds.includes(itemId)
            ? selectedItemIds.filter(id => id !== itemId)
            : [...selectedItemIds, itemId];
        onItemsChange(newSelected);
    };

    const clearAllItemFilters = () => {
        onItemsChange([]);
        setItemSearch('');
        setShowItemsDropdown(false);
    };

    const hasActiveFilters = searchTerm || selectedSupplierId || selectedItemIds.length > 0 || selectedStatus !== 'all' || dateRange.start || dateRange.end;

    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">

            {/* Header Compact */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-gray-700 dark:text-gray-200">
                    <Filter className="w-4 h-4 text-blue-600" />
                    <span className="text-sm font-bold">فلترة البيانات</span>
                    <span className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded-full">
                        {filteredCount}
                    </span>
                </div>
                {hasActiveFilters && (
                    <button
                        onClick={() => {
                            onSearchChange('');
                            onSupplierChange('');
                            onItemsChange([]);
                            onStatusChange('all');
                            onDateRangeChange({ start: '', end: '' });
                        }}
                        className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1 transition-colors"
                    >
                        <X className="w-3 h-3" />
                        مسح الكل
                    </button>
                )}
            </div>

            {/* Compact Grid Layout 
                - Mobile: 1 Column
                - Tablet/Small Laptop (with Sidebar): 2 Columns
                - Large Screen: 4 Columns
                هذا التوزيع يضمن أن العناصر تنزل للأسطر التالية بدلاً من الخروج عن الشاشة
            */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">

                {/* 1. Search Input (Takes 2 cols on Large screens for better visibility) */}
                <div className="md:col-span-2 relative">
                    <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                    <input
                        type="text"
                        value={searchTerm}
                        onChange={(e) => onSearchChange(e.target.value)}
                        placeholder="بحث شامل (رقم العرض، اسم المورد...)"
                        className="w-full pr-9 pl-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-all"
                    />
                </div>

                {/* 2. Supplier Select */}
                <div className="relative">
                    <Building className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4 pointer-events-none" />
                    <select
                        value={selectedSupplierId}
                        onChange={(e) => onSupplierChange(e.target.value)}
                        className="w-full pr-9 pl-8 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 appearance-none truncate"
                    >
                        <option value="">كل الموردين</option>
                        {suppliers.map(sup => (
                            <option key={sup.id} value={sup.id}>
                                {sup.alias || sup.tradeName}
                            </option>
                        ))}
                    </select>
                    <ChevronDown className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-3 h-3 pointer-events-none" />
                </div>

                {/* 3. Status Select */}
                <div className="relative">
                    <Tag className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4 pointer-events-none" />
                    <select
                        value={selectedStatus}
                        onChange={(e) => onStatusChange(e.target.value as PriceOfferStatus | 'all')}
                        className="w-full pr-9 pl-8 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 appearance-none"
                    >
                        {statusOptions.map(option => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                    <ChevronDown className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-3 h-3 pointer-events-none" />
                </div>

                {/* 4. Products Multi-select Dropdown */}
                <div className="relative">
                    <button
                        onClick={() => {
                            setShowItemsDropdown(!showItemsDropdown);
                            setItemSearch('');
                        }}
                        className={`w-full px-3 py-2 rounded-lg border text-sm flex items-center justify-between transition-all ${showItemsDropdown || selectedItemIds.length > 0
                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                            : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900'
                            }`}
                    >
                        <div className="flex items-center gap-2 truncate">
                            <Package className="w-4 h-4 text-gray-400 shrink-0" />
                            <span className="truncate text-gray-700 dark:text-gray-300">
                                {selectedItemIds.length === 0
                                    ? 'المنتجات'
                                    : `${selectedItemIds.length} منتج`}
                            </span>
                        </div>
                        <ChevronDown className={`w-3 h-3 text-gray-400 transition-transform ${showItemsDropdown ? 'rotate-180' : ''}`} />
                    </button>

                    {showItemsDropdown && (
                        <div className="absolute top-full left-0 right-0 mt-1 z-50 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-60 flex flex-col w-full min-w-[200px]">
                            <div className="p-2 border-b dark:border-gray-700">
                                <input
                                    type="text"
                                    placeholder="بحث..."
                                    value={itemSearch}
                                    onChange={(e) => setItemSearch(e.target.value)}
                                    className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-700 dark:border-gray-600"
                                    onClick={(e) => e.stopPropagation()}
                                    autoFocus
                                />
                            </div>
                            <div className="flex-1 overflow-y-auto p-1">
                                {filteredItems.length === 0 ? (
                                    <div className="p-2 text-xs text-center text-gray-500">لا يوجد</div>
                                ) : (
                                    filteredItems.map(item => (
                                        <label key={item.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={selectedItemIds.includes(item.id)}
                                                onChange={() => handleItemToggle(item.id)}
                                                className="rounded text-blue-600 w-3.5 h-3.5"
                                            />
                                            <span className="text-xs truncate">{item.name}</span>
                                        </label>
                                    ))
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* 5. Date Range (Merged into one grid cell or split if needed) */}

                <div className="md:col-span-2 xl:col-span-1 flex gap-2">
                    <div className="relative flex">
                        <span>من تاريخ</span>

                        <input
                            type="date"
                            value={dateRange.start}
                            onChange={(e) => onDateRangeChange({ ...dateRange, start: e.target.value })}
                            className="w-full px-2 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-xs focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                    <div className="relative flex">
                        <span>حتى تاريخ</span>
                        <input
                            type="date"
                            value={dateRange.end}
                            onChange={(e) => onDateRangeChange({ ...dateRange, end: e.target.value })}
                            className="w-full px-2 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-xs focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                </div>

            </div>

            {/* Selected Items Tags (Minimalist) */}
            {selectedItemIds.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-gray-100 dark:border-gray-700">
                    {selectedItemIds.map(itemId => {
                        const item = items.find(i => i.id === itemId);
                        if (!item) return null;
                        return (
                            <span key={itemId} className="inline-flex items-center gap-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded text-[10px] border border-blue-100 dark:border-blue-800">
                                {item.name}
                                <button onClick={() => handleItemToggle(itemId)} className="hover:text-red-500">
                                    <X className="w-3 h-3" />
                                </button>
                            </span>
                        )
                    })}
                </div>
            )}
        </div>
    );
};