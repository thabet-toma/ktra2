import React, { useState, useMemo } from 'react';
import { Search, Filter, Calendar, Package, X, ChevronDown } from 'lucide-react';
import { Supplier, Item } from '@/types';

interface OldInvoiceFiltersProps {
    searchTerm: string;
    onSearchChange: (value: string) => void;
    selectedSupplierId: string;
    onSupplierChange: (id: string) => void;
    selectedItemIds: string[];
    onItemsChange: (ids: string[]) => void;
    dateRange: { start: string; end: string };
    onDateRangeChange: (range: { start: string; end: string }) => void;
    suppliers: Supplier[];
    items: Item[];
}

export const OldInvoiceFilters: React.FC<OldInvoiceFiltersProps> = ({
    searchTerm,
    onSearchChange,
    selectedSupplierId,
    onSupplierChange,
    selectedItemIds,
    onItemsChange,
    dateRange,
    onDateRangeChange,
    suppliers,
    items
}) => {
    const [showItemsDropdown, setShowItemsDropdown] = React.useState(false);
    const [itemSearch, setItemSearch] = React.useState('');

    // فلترة العناصر بناءً على البحث
    const filteredItems = useMemo(() => {
        if (!itemSearch.trim()) return items;

        const searchLower = itemSearch.toLowerCase();
        return items.filter(item =>
            item.name.toLowerCase().includes(searchLower) ||
            (item.modelNumber && item.modelNumber.toLowerCase().includes(searchLower)) ||
            item.categoryName.toLowerCase().includes(searchLower)
        );
    }, [items, itemSearch]);

    const handleItemToggle = (itemId: string) => {
        const newSelected = selectedItemIds.includes(itemId)
            ? selectedItemIds.filter(id => id !== itemId)
            : [...selectedItemIds, itemId];
        onItemsChange(newSelected);
    };

    const clearItemFilter = (itemId: string) => {
        onItemsChange(selectedItemIds.filter(id => id !== itemId));
    };

    const clearAllItemFilters = () => {
        onItemsChange([]);
        setItemSearch('');
        setShowItemsDropdown(false);
    };

    const hasActiveFilters = searchTerm || selectedSupplierId || selectedItemIds.length > 0 || dateRange.start || dateRange.end;

    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex flex-col md:flex-row gap-4 items-end md:items-center">
                {/* Search */}
                <div className="flex-1 w-full relative">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 block">بحث</label>
                    <div className="relative">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => onSearchChange(e.target.value)}
                            placeholder="رقم الفاتورة، المورد، أو المنتج..."
                            className="w-full pr-9 pl-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                </div>

                {/* Supplier Filter */}
                <div className="w-full md:w-64">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 block">المورد</label>
                    <select
                        value={selectedSupplierId}
                        onChange={(e) => onSupplierChange(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500"
                    >
                        <option value="">جميع الموردين</option>
                        {suppliers.map(sup => (
                            <option key={sup.id} value={sup.id}>
                                {sup.alias || sup.tradeName}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Items Filter */}
                <div className="w-full md:w-64 relative">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 block">المنتجات</label>
                    <div className="relative">
                        <button
                            onClick={() => {
                                setShowItemsDropdown(!showItemsDropdown);
                                setItemSearch('');
                            }}
                            className={`w-full px-3 py-2 rounded-lg border ${showItemsDropdown || selectedItemIds.length > 0
                                ? 'border-blue-500 ring-1 ring-blue-500 bg-blue-50 dark:bg-blue-900/20'
                                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900'
                                } text-sm text-right flex items-center justify-between transition-all`}
                        >
                            <span className="truncate">
                                {selectedItemIds.length === 0
                                    ? 'جميع المنتجات'
                                    : selectedItemIds.length === 1
                                        ? 'منتج واحد'
                                        : `${selectedItemIds.length} منتجات`}
                            </span>
                            <div className="flex items-center gap-1">
                                <Package className="w-4 h-4 text-gray-400" />
                                <ChevronDown className={`w-3 h-3 transition-transform ${showItemsDropdown ? 'rotate-180' : ''}`} />
                            </div>
                        </button>

                        {showItemsDropdown && (
                            <div className="absolute top-full left-0 mt-1 z-50 w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-96 overflow-hidden">
                                <div className="flex flex-col h-full">
                                    {/* Header with search and close */}
                                    <div className="sticky top-0 bg-white dark:bg-gray-800 p-3 border-b border-gray-200 dark:border-gray-700">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">اختر المنتجات</span>
                                            <div className="flex items-center gap-2">
                                                {selectedItemIds.length > 0 && (
                                                    <button
                                                        onClick={clearAllItemFilters}
                                                        className="text-xs text-red-500 hover:text-red-600 px-2 py-1 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                                        title="إلغاء جميع المنتجات"
                                                    >
                                                        مسح الكل
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => setShowItemsDropdown(false)}
                                                    className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                                                >
                                                    <X className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>

                                        {/* Search inside dropdown */}
                                        <div className="relative">
                                            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                                            <input
                                                type="text"
                                                placeholder="ابحث عن منتج بالاسم، المودل، أو الفئة..."
                                                value={itemSearch}
                                                onChange={(e) => setItemSearch(e.target.value)}
                                                className="w-full pr-10 pl-4 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 rounded-lg focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                                autoFocus
                                                onClick={(e) => e.stopPropagation()}
                                            />
                                        </div>

                                        <div className="flex items-center justify-between mt-2">
                                            <div className="text-xs text-gray-500 dark:text-gray-400">
                                                {selectedItemIds.length} منتج مختار
                                            </div>
                                            <div className="text-xs text-gray-500 dark:text-gray-400">
                                                {filteredItems.length} منتج
                                            </div>
                                        </div>
                                    </div>

                                    {/* Items list */}
                                    <div className="flex-1 overflow-y-auto max-h-64">
                                        {filteredItems.length === 0 ? (
                                            <div className="text-center py-8">
                                                <Package className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                                                <p className="text-sm text-gray-500 dark:text-gray-400">لا توجد منتجات تطابق البحث</p>
                                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">"{itemSearch}"</p>
                                            </div>
                                        ) : (
                                            <div className="p-2 space-y-1">
                                                {filteredItems.map(item => (
                                                    <label
                                                        key={item.id}
                                                        className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selectedItemIds.includes(item.id)
                                                            ? 'bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800'
                                                            : 'hover:bg-gray-100 dark:hover:bg-gray-700'
                                                            }`}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedItemIds.includes(item.id)}
                                                            onChange={() => handleItemToggle(item.id)}
                                                            className="rounded text-blue-600 focus:ring-blue-500"
                                                        />
                                                        <div className="flex-1 text-right min-w-0">
                                                            <div className="flex items-center justify-between">
                                                                <div className="flex-1">
                                                                    <div className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                                                        {item.name}
                                                                    </div>
                                                                    <div className="flex items-center gap-2 mt-1">
                                                                        <span className="text-xs text-gray-500 dark:text-gray-400">
                                                                            {item.categoryName}
                                                                        </span>
                                                                        {item.modelNumber && (
                                                                            <span className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded">
                                                                                {item.modelNumber}
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                                {selectedItemIds.includes(item.id) && (
                                                                    <div className="w-5 h-5 flex items-center justify-center bg-blue-500 text-white rounded-full ml-2 flex-shrink-0">
                                                                        <span className="text-xs">✓</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </label>
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    {/* Footer with actions */}
                                    {selectedItemIds.length > 0 && (
                                        <div className="sticky bottom-0 bg-white dark:bg-gray-800 p-3 border-t border-gray-200 dark:border-gray-700">
                                            <div className="flex items-center justify-between">
                                                <span className="text-sm text-gray-700 dark:text-gray-300">
                                                    {selectedItemIds.length} منتج مختار
                                                </span>
                                                <button
                                                    onClick={() => setShowItemsDropdown(false)}
                                                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white text-sm rounded-lg transition-colors"
                                                >
                                                    تم الاختيار
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* عرض المنتجات المختارة */}
                        {selectedItemIds.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                                {selectedItemIds.slice(0, 3).map(itemId => {
                                    const item = items.find(i => i.id === itemId);
                                    return item ? (
                                        <span
                                            key={itemId}
                                            className="inline-flex items-center gap-1 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded-full text-xs"
                                        >
                                            {item.name}
                                            <button
                                                onClick={() => clearItemFilter(itemId)}
                                                className="p-0.5 hover:bg-blue-200 dark:hover:bg-blue-900/50 rounded-full"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </span>
                                    ) : null;
                                })}
                                {selectedItemIds.length > 3 && (
                                    <span className="inline-flex items-center gap-1 bg-blue-50 dark:bg-blue-900/20 text-blue-500 dark:text-blue-400 px-2 py-1 rounded-full text-xs">
                                        +{selectedItemIds.length - 3} أكثر
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Date Range */}
                <div className="flex gap-2 w-full md:w-auto">
                    <div>
                        <label className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 block">من تاريخ</label>
                        <input
                            type="date"
                            value={dateRange.start}
                            onChange={(e) => onDateRangeChange({ ...dateRange, start: e.target.value })}
                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 block">إلى تاريخ</label>
                        <input
                            type="date"
                            value={dateRange.end}
                            onChange={(e) => onDateRangeChange({ ...dateRange, end: e.target.value })}
                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                </div>

                {/* Clear All Filters */}
                {hasActiveFilters && (
                    <button
                        onClick={() => {
                            onSearchChange('');
                            onSupplierChange('');
                            onItemsChange([]);
                            onDateRangeChange({ start: '', end: '' });
                        }}
                        className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title="مسح جميع الفلاتر"
                    >
                        <Filter className="w-4 h-4" />
                    </button>
                )}
            </div>
        </div>
    );
};