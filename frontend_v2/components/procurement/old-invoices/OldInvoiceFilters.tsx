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
        <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm border aseel-border-soft dark:aseel-border-soft p-4">
            <div className="flex flex-col md:flex-row gap-4 items-end md:items-center">
                {/* Search */}
                <div className="flex-1 w-full relative">
                    <label className="text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1 block">بحث</label>
                    <div className="relative">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 aseel-text-soft w-4 h-4" />
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => onSearchChange(e.target.value)}
                            placeholder="رقم الفاتورة، المورد، أو المنتج..."
                            className="w-full pr-9 pl-4 py-2 rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                </div>

                {/* Supplier Filter */}
                <div className="w-full md:w-64">
                    <label className="text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1 block">المورد</label>
                    <select
                        value={selectedSupplierId}
                        onChange={(e) => onSupplierChange(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-blue-500"
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
                    <label className="text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1 block">المنتجات</label>
                    <div className="relative">
                        <button
                            onClick={() => {
                                setShowItemsDropdown(!showItemsDropdown);
                                setItemSearch('');
                            }}
                            className={`w-full px-3 py-2 rounded-lg border ${showItemsDropdown || selectedItemIds.length > 0
                                ? 'aseel-border-soft ring-1 ring-blue-500 aseel-bg-accent-bg dark:aseel-bg-panel/20'
                                : 'aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel'
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
                                <Package className="w-4 h-4 aseel-text-soft" />
                                <ChevronDown className={`w-3 h-3 transition-transform ${showItemsDropdown ? 'rotate-180' : ''}`} />
                            </div>
                        </button>

                        {showItemsDropdown && (
                            <div className="absolute top-full left-0 mt-1 z-50 w-full aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg shadow-lg max-h-96 overflow-hidden">
                                <div className="flex flex-col h-full">
                                    {/* Header with search and close */}
                                    <div className="sticky top-0 aseel-bg-field dark:aseel-bg-panel p-3 border-b aseel-border-soft dark:aseel-border-soft">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-sm font-medium aseel-text-ink dark:aseel-text-soft">اختر المنتجات</span>
                                            <div className="flex items-center gap-2">
                                                {selectedItemIds.length > 0 && (
                                                    <button
                                                        onClick={clearAllItemFilters}
                                                        className="text-xs aseel-text-soft hover:aseel-text-state px-2 py-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel/20 rounded"
                                                        title="إلغاء جميع المنتجات"
                                                    >
                                                        مسح الكل
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => setShowItemsDropdown(false)}
                                                    className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded"
                                                >
                                                    <X className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>

                                        {/* Search inside dropdown */}
                                        <div className="relative">
                                            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 aseel-text-soft" />
                                            <input
                                                type="text"
                                                placeholder="ابحث عن منتج بالاسم، المودل، أو الفئة..."
                                                value={itemSearch}
                                                onChange={(e) => setItemSearch(e.target.value)}
                                                className="w-full pr-10 pl-4 py-2 text-sm border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg focus:ring-1 focus:ring-blue-500 focus:aseel-border-soft"
                                                autoFocus
                                                onClick={(e) => e.stopPropagation()}
                                            />
                                        </div>

                                        <div className="flex items-center justify-between mt-2">
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">
                                                {selectedItemIds.length} منتج مختار
                                            </div>
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">
                                                {filteredItems.length} منتج
                                            </div>
                                        </div>
                                    </div>

                                    {/* Items list */}
                                    <div className="flex-1 overflow-y-auto max-h-64">
                                        {filteredItems.length === 0 ? (
                                            <div className="text-center py-8">
                                                <Package className="w-10 h-10 aseel-text-soft dark:aseel-text-soft mx-auto mb-2" />
                                                <p className="text-sm aseel-text-soft dark:aseel-text-soft">لا توجد منتجات تطابق البحث</p>
                                                <p className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">"{itemSearch}"</p>
                                            </div>
                                        ) : (
                                            <div className="p-2 space-y-1">
                                                {filteredItems.map(item => (
                                                    <label
                                                        key={item.id}
                                                        className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selectedItemIds.includes(item.id)
                                                            ? 'aseel-bg-accent-bg dark:aseel-bg-panel/30 border aseel-border-accent dark:aseel-border-soft'
                                                            : 'hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                                            }`}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedItemIds.includes(item.id)}
                                                            onChange={() => handleItemToggle(item.id)}
                                                            className="rounded aseel-text-accent focus:ring-blue-500"
                                                        />
                                                        <div className="flex-1 text-right min-w-0">
                                                            <div className="flex items-center justify-between">
                                                                <div className="flex-1">
                                                                    <div className="text-sm font-medium aseel-text-ink dark:aseel-text-soft truncate">
                                                                        {item.name}
                                                                    </div>
                                                                    <div className="flex items-center gap-2 mt-1">
                                                                        <span className="text-xs aseel-text-soft dark:aseel-text-soft">
                                                                            {item.categoryName}
                                                                        </span>
                                                                        {item.modelNumber && (
                                                                            <span className="text-xs aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft px-2 py-0.5 rounded">
                                                                                {item.modelNumber}
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                                {selectedItemIds.includes(item.id) && (
                                                                    <div className="w-5 h-5 flex items-center justify-center aseel-bg-accent-bg text-white rounded-full ml-2 flex-shrink-0">
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
                                        <div className="sticky bottom-0 aseel-bg-field dark:aseel-bg-panel p-3 border-t aseel-border-soft dark:aseel-border-soft">
                                            <div className="flex items-center justify-between">
                                                <span className="text-sm aseel-text-ink dark:aseel-text-soft">
                                                    {selectedItemIds.length} منتج مختار
                                                </span>
                                                <button
                                                    onClick={() => setShowItemsDropdown(false)}
                                                    className="px-3 py-1.5 aseel-bg-accent hover:aseel-bg-accent dark:aseel-bg-accent-bg dark:hover:aseel-bg-accent text-white text-sm rounded-lg transition-colors"
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
                                            className="inline-flex items-center gap-1 aseel-bg-accent-bg dark:aseel-bg-panel/30 aseel-text-accent dark:aseel-text-soft px-2 py-1 rounded-full text-xs"
                                        >
                                            {item.name}
                                            <button
                                                onClick={() => clearItemFilter(itemId)}
                                                className="p-0.5 hover:aseel-bg-grid-head dark:hover:aseel-bg-panel/50 rounded-full"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </span>
                                    ) : null;
                                })}
                                {selectedItemIds.length > 3 && (
                                    <span className="inline-flex items-center gap-1 aseel-bg-accent-bg dark:aseel-bg-panel/20 aseel-text-soft dark:aseel-text-soft px-2 py-1 rounded-full text-xs">
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
                        <label className="text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1 block">من تاريخ</label>
                        <input
                            type="date"
                            value={dateRange.start}
                            onChange={(e) => onDateRangeChange({ ...dateRange, start: e.target.value })}
                            className="w-full px-3 py-2 rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-blue-500"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1 block">إلى تاريخ</label>
                        <input
                            type="date"
                            value={dateRange.end}
                            onChange={(e) => onDateRangeChange({ ...dateRange, end: e.target.value })}
                            className="w-full px-3 py-2 rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-blue-500"
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
                        className="p-2 aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel/20 rounded-lg transition-colors"
                        title="مسح جميع الفلاتر"
                    >
                        <Filter className="w-4 h-4" />
                    </button>
                )}
            </div>
        </div>
    );
};