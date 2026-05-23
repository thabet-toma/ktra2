import React, { useState, useMemo, useRef } from 'react';
import { Invoice, Supplier } from '../../../types';
import {
    Calendar, History, FileText, ChevronDown, Edit2,
    Search, Filter, X, Eye,
    ChevronUp, ChevronLeft, ChevronRight,
    DollarSign, Hash, Building, List,
    Package,
    ArrowRight,
    Trash2
} from 'lucide-react';

interface OldInvoiceListProps {
    invoices: Invoice[];
    suppliers: Supplier[];
    onViewDetails: (invoice: Invoice) => void;
    onEdit: (invoice: Invoice) => void;
    onConvertToMain?: (invoice: Invoice) => void; // إضافة هذا السطر
    onDelete?: (invoice: Invoice) => void; // إضافة هذا السطر
    allDbItems?: any[];
}

// تعريف نوع لفلترة الأعمدة
type ColumnFilterKeys = 'invoiceDate' | 'invoiceNumber' | 'factoryName' | 'grandTotal';
type ColumnFilters = Record<ColumnFilterKeys, string>;

export const OldInvoiceList: React.FC<OldInvoiceListProps> = ({
    invoices,
    suppliers,
    onViewDetails,
    onEdit,
    allDbItems,
    onConvertToMain,
    onDelete
}) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({
        key: 'invoiceDate',
        direction: 'desc'
    });

    // تحديد النوع للفلترة
    const [columnFilters, setColumnFilters] = useState<ColumnFilters>({
        invoiceDate: '',
        invoiceNumber: '',
        factoryName: '',
        grandTotal: ''
    });

    const [activeColumnFilter, setActiveColumnFilter] = useState<ColumnFilterKeys | null>(null);
    const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
    const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
    const tableRef = useRef<HTMLDivElement>(null);

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const itemsPerPage = 20;

    // Helper function to get top 3 products by quantity
    const getTopProductsByQuantity = (invoice: Invoice) => {
        if (!invoice.items || invoice.items.length === 0) return [];
        return [...invoice.items]
            .sort((a, b) => (b.quantity || 0) - (a.quantity || 0))
            .slice(0, 3);
    };

    // فلترة الفواتير بناءً على بحث عام وفلترة الأعمدة
    const filteredInvoices = useMemo(() => {
        return invoices.filter(invoice => {
            // فلترة حسب البحث العام
            if (searchTerm) {
                const term = searchTerm.toLowerCase();
                const matchesNumber = (invoice.invoiceNumber || '').toLowerCase().includes(term);
                const matchesFactory = (invoice.factoryName || '').toLowerCase().includes(term);
                const matchesDate = (invoice.invoiceDate || '').includes(term);

                if (!(matchesNumber || matchesFactory || matchesDate)) {
                    return false;
                }
            }

            // فلترة حسب الأعمدة
            for (const [column, filterValue] of Object.entries(columnFilters) as [ColumnFilterKeys, string][]) {
                if (!filterValue || filterValue.trim() === '') continue;

                const value = filterValue.toLowerCase();

                switch (column) {
                    case 'invoiceDate':
                        if (!(invoice.invoiceDate || '').toLowerCase().includes(value)) return false;
                        break;
                    case 'invoiceNumber':
                        if (!(invoice.invoiceNumber || '').toLowerCase().includes(value)) return false;
                        break;
                    case 'factoryName':
                        if (!(invoice.factoryName || '').toLowerCase().includes(value)) return false;
                        break;
                    case 'grandTotal':
                        const total = (invoice.grandTotal?.toString() || '0').toLowerCase();
                        if (!total.includes(value)) return false;
                        break;
                }
            }

            return true;
        });
    }, [invoices, searchTerm, columnFilters]);

    // ترتيب الفواتير
    const sortedInvoices = useMemo(() => {
        return [...filteredInvoices].sort((a, b) => {
            let aValue: any = '';
            let bValue: any = '';

            switch (sortConfig.key) {
                case 'invoiceDate':
                    aValue = a.invoiceDate || '';
                    bValue = b.invoiceDate || '';
                    break;
                case 'invoiceNumber':
                    aValue = a.invoiceNumber || '';
                    bValue = b.invoiceNumber || '';
                    break;
                case 'factoryName':
                    aValue = a.factoryName || '';
                    bValue = b.factoryName || '';
                    break;
                case 'itemsCount':
                    aValue = a.items?.length || 0;
                    bValue = b.items?.length || 0;
                    break;
                case 'grandTotal':
                    aValue = a.grandTotal || 0;
                    bValue = b.grandTotal || 0;
                    break;
            }

            if (aValue < bValue) {
                return sortConfig.direction === 'asc' ? -1 : 1;
            }
            if (aValue > bValue) {
                return sortConfig.direction === 'asc' ? 1 : -1;
            }
            return 0;
        });
    }, [filteredInvoices, sortConfig]);

    // Pagination logic
    const totalPages = Math.ceil(sortedInvoices.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const paginatedInvoices = sortedInvoices.slice(startIndex, endIndex);

    // Reset to page 1 when filters change
    React.useEffect(() => {
        setCurrentPage(1);
    }, [searchTerm, columnFilters, sortConfig]);

    const goToPage = (page: number) => {
        setCurrentPage(Math.max(1, Math.min(page, totalPages)));
    };

    const getPageNumbers = () => {
        const pages: (number | string)[] = [];
        const showPages = 5; // Number of page buttons to show

        if (totalPages <= showPages) {
            for (let i = 1; i <= totalPages; i++) {
                pages.push(i);
            }
        } else {
            if (currentPage <= 3) {
                for (let i = 1; i <= 4; i++) pages.push(i);
                pages.push('...');
                pages.push(totalPages);
            } else if (currentPage >= totalPages - 2) {
                pages.push(1);
                pages.push('...');
                for (let i = totalPages - 3; i <= totalPages; i++) pages.push(i);
            } else {
                pages.push(1);
                pages.push('...');
                for (let i = currentPage - 1; i <= currentPage + 1; i++) pages.push(i);
                pages.push('...');
                pages.push(totalPages);
            }
        }
        return pages;
    };

    const handleSort = (key: string) => {
        setSortConfig(current => ({
            key,
            direction: current.key === key && current.direction === 'desc' ? 'asc' : 'desc'
        }));
    };

    const handleColumnFilter = (column: ColumnFilterKeys, value: string) => {
        setColumnFilters(prev => ({
            ...prev,
            [column]: value
        }));
    };

    const clearColumnFilter = (column: ColumnFilterKeys) => {
        setColumnFilters(prev => ({
            ...prev,
            [column]: ''
        }));
        if (activeColumnFilter === column) {
            setActiveColumnFilter(null);
        }
    };

    const clearAllFilters = () => {
        setColumnFilters({
            invoiceDate: '',
            invoiceNumber: '',
            factoryName: '',
            grandTotal: ''
        });
        setSearchTerm('');
        setActiveColumnFilter(null);
    };

    const getSortIcon = (column: string) => {
        if (sortConfig.key !== column) {
            return <ChevronDown className="w-3 h-3 opacity-30" />;
        }
        return sortConfig.direction === 'asc'
            ? <ChevronUp className="w-3 h-3" />
            : <ChevronDown className="w-3 h-3" />;
    };

    // تحقق مما إذا كان هناك أي فلتر نشط
    const hasActiveFilters = useMemo(() => {
        return searchTerm !== '' ||
            Object.values(columnFilters).some((value: string) => value.trim() !== '');
    }, [searchTerm, columnFilters]);

    // التعامل مع النقر العادي على الصف
    const handleRowClick = (invoice: Invoice, e: React.MouseEvent) => {
        e.stopPropagation();

        // حساب موقع النقر بالنسبة للجدول
        const rowElement = e.currentTarget as HTMLElement;
        const tableRect = tableRef.current?.getBoundingClientRect();
        const rowRect = rowElement.getBoundingClientRect();

        if (tableRect) {
            // حساب الموضع بحيث تكون القائمة في منتصف الصف
            const top = rowRect.top - tableRect.top + (rowRect.height / 2);
            const left = rowRect.right - tableRect.left;

            setSelectedInvoice(invoice);
            setMenuPosition({
                top: Math.min(top, tableRect.height - 200), // لمنع الخروج من أسفل الجدول
                left: Math.max(left - 250, 10) // تحريك لليسار ليكون بجوار الصف
            });
        }
    };

    // إغلاق القائمة المنبثقة
    const closeContextMenu = () => {
        setSelectedInvoice(null);
        setMenuPosition(null);
    };

    // إغلاق القائمة عند النقر خارجها
    React.useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (selectedInvoice && !(e.target as HTMLElement).closest('.context-menu') &&
                !(e.target as HTMLElement).closest('tr')) {
                closeContextMenu();
            }
        };

        document.addEventListener('click', handleClickOutside);
        return () => document.removeEventListener('click', handleClickOutside);
    }, [selectedInvoice]);

    if (invoices.length === 0) {
        return (
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm border aseel-border-soft dark:aseel-border-soft p-12 text-center">
                <div className="flex flex-col items-center justify-center gap-4">
                    <div className="w-16 h-16 aseel-bg-panel dark:aseel-bg-panel rounded-full flex items-center justify-center">
                        <History className="w-8 h-8 aseel-text-soft" />
                    </div>
                    <div className="aseel-text-soft dark:aseel-text-soft">
                        <div className="font-medium text-lg">لا توجد فواتير مؤرشفة</div>
                        <div className="text-sm mt-1">جرب تغيير معايير البحث أو أضف فاتورة جديدة</div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* شريط البحث والتحكم */}
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm border aseel-border-soft dark:aseel-border-soft p-4">
                <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
                    <div className="flex items-center gap-4 w-full md:w-auto">
                        <div className="relative flex-1 md:flex-none md:w-64">
                            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 aseel-text-soft dark:aseel-text-soft" />
                            <input
                                type="text"
                                placeholder="ابحث برقم الفاتورة، المورد، أو التاريخ..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="w-full pr-9 pl-4 py-2.5 border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent transition-all text-sm"
                            />
                        </div>

                        {hasActiveFilters && (
                            <button
                                onClick={clearAllFilters}
                                className="px-3 py-2.5 text-sm aseel-text-soft dark:aseel-text-soft hover:aseel-text-ink dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg flex items-center gap-2 transition-colors"
                            >
                                <X className="w-4 h-4" />
                                مسح جميع الفلاتر
                            </button>
                        )}
                    </div>

                    <div className="flex items-center gap-2 text-sm aseel-text-soft dark:aseel-text-soft">
                        <Filter className="w-4 h-4" />
                        <span>تم العثور على</span>
                        <span className="font-bold aseel-text-accent dark:aseel-text-soft">
                            {filteredInvoices.length}
                        </span>
                        <span>من أصل</span>
                        <span className="font-bold">{invoices.length}</span>
                        <span>فاتورة</span>
                    </div>
                </div>
            </div>

            {/* الجدول مع الفلترة المدمجة */}
            <div
                ref={tableRef}
                className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm border aseel-border-soft dark:aseel-border-soft overflow-hidden relative"
            >
                <div className="overflow-x-auto">
                    <table className="w-full text-right">
                        <thead className="aseel-bg-panel dark:aseel-bg-panel/50 aseel-text-ink dark:aseel-text-soft text-sm sticky top-0 z-20">
                            <tr>
                                {/* عمود التاريخ */}
                                <th className="px-6 py-4 font-semibold border-b dark:aseel-border-soft">
                                    <div className="flex items-center justify-between gap-2">
                                        <button
                                            onClick={() => handleSort('invoiceDate')}
                                            className="flex items-center gap-2 hover:aseel-text-accent dark:hover:aseel-text-soft transition-colors"
                                        >
                                            <Calendar className="w-4 h-4" />
                                            تاريخ الفاتورة
                                            {getSortIcon('invoiceDate')}
                                        </button>
                                        <div className="relative">
                                            <button
                                                onClick={() => setActiveColumnFilter(activeColumnFilter === 'invoiceDate' ? null : 'invoiceDate')}
                                                className={`p-1 rounded ${activeColumnFilter === 'invoiceDate' || columnFilters.invoiceDate !== ''
                                                    ? 'aseel-text-accent dark:aseel-text-soft aseel-bg-accent-bg dark:aseel-bg-panel/20'
                                                    : 'aseel-text-soft hover:aseel-text-soft dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                                    }`}
                                            >
                                                <Filter className="w-3 h-3" />
                                            </button>
                                            {activeColumnFilter === 'invoiceDate' && (
                                                <div className="absolute left-0 top-full mt-1 z-50 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg shadow-xl p-3 min-w-[220px]">
                                                    <div className="flex flex-col gap-2">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-xs font-medium aseel-text-soft dark:aseel-text-soft">فلترة التاريخ</span>
                                                            <button
                                                                onClick={() => clearColumnFilter('invoiceDate')}
                                                                className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded"
                                                            >
                                                                <X className="w-3 h-3" />
                                                            </button>
                                                        </div>
                                                        <div className="relative">
                                                            <input
                                                                type="date"
                                                                value={columnFilters.invoiceDate}
                                                                onChange={(e) => handleColumnFilter('invoiceDate', e.target.value)}
                                                                className="w-full px-3 py-2 text-sm border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                                                autoFocus
                                                            />
                                                        </div>
                                                        <div className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">
                                                            اختر تاريخاً محدداً للفلترة
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </th>

                                {/* عمود رقم الفاتورة */}
                                <th className="px-6 py-4 font-semibold border-b dark:aseel-border-soft">
                                    <div className="flex items-center justify-between gap-2">
                                        <button
                                            onClick={() => handleSort('invoiceNumber')}
                                            className="flex items-center gap-2 hover:aseel-text-accent dark:hover:aseel-text-soft transition-colors"
                                        >
                                            <Hash className="w-4 h-4" />
                                            رقم الفاتورة
                                            {getSortIcon('invoiceNumber')}
                                        </button>
                                        <div className="relative">
                                            <button
                                                onClick={() => setActiveColumnFilter(activeColumnFilter === 'invoiceNumber' ? null : 'invoiceNumber')}
                                                className={`p-1 rounded ${activeColumnFilter === 'invoiceNumber' || columnFilters.invoiceNumber !== ''
                                                    ? 'aseel-text-accent dark:aseel-text-soft aseel-bg-accent-bg dark:aseel-bg-panel/20'
                                                    : 'aseel-text-soft hover:aseel-text-soft dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                                    }`}
                                            >
                                                <Filter className="w-3 h-3" />
                                            </button>
                                            {activeColumnFilter === 'invoiceNumber' && (
                                                <div className="absolute left-0 top-full mt-1 z-50 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg shadow-xl p-3 min-w-[220px]">
                                                    <div className="flex flex-col gap-2">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-xs font-medium aseel-text-soft dark:aseel-text-soft">فلترة الرقم</span>
                                                            <button
                                                                onClick={() => clearColumnFilter('invoiceNumber')}
                                                                className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded"
                                                            >
                                                                <X className="w-3 h-3" />
                                                            </button>
                                                        </div>
                                                        <div className="relative">
                                                            <input
                                                                type="text"
                                                                placeholder="أدخل رقم الفاتورة..."
                                                                value={columnFilters.invoiceNumber}
                                                                onChange={(e) => handleColumnFilter('invoiceNumber', e.target.value)}
                                                                className="w-full px-3 py-2 text-sm border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                                                autoFocus
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </th>

                                {/* عمود المورد */}
                                <th className="px-6 py-4 font-semibold border-b dark:aseel-border-soft">
                                    <div className="flex items-center justify-between gap-2">
                                        <button
                                            onClick={() => handleSort('factoryName')}
                                            className="flex items-center gap-2 hover:aseel-text-accent dark:hover:aseel-text-soft transition-colors"
                                        >
                                            <Building className="w-4 h-4" />
                                            المورد
                                            {getSortIcon('factoryName')}
                                        </button>
                                        <div className="relative">
                                            <button
                                                onClick={() => setActiveColumnFilter(activeColumnFilter === 'factoryName' ? null : 'factoryName')}
                                                className={`p-1 rounded ${activeColumnFilter === 'factoryName' || columnFilters.factoryName !== ''
                                                    ? 'aseel-text-accent dark:aseel-text-soft aseel-bg-accent-bg dark:aseel-bg-panel/20'
                                                    : 'aseel-text-soft hover:aseel-text-soft dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                                    }`}
                                            >
                                                <Filter className="w-3 h-3" />
                                            </button>
                                            {activeColumnFilter === 'factoryName' && (
                                                <div className="absolute left-0 top-full mt-1 z-50 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg shadow-xl p-3 min-w-[220px]">
                                                    <div className="flex flex-col gap-2">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-xs font-medium aseel-text-soft dark:aseel-text-soft">فلترة المورد</span>
                                                            <button
                                                                onClick={() => clearColumnFilter('factoryName')}
                                                                className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded"
                                                            >
                                                                <X className="w-3 h-3" />
                                                            </button>
                                                        </div>
                                                        <div className="relative">
                                                            <input
                                                                type="text"
                                                                placeholder="أدخل اسم المورد..."
                                                                value={columnFilters.factoryName}
                                                                onChange={(e) => handleColumnFilter('factoryName', e.target.value)}
                                                                className="w-full px-3 py-2 text-sm border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                                                autoFocus
                                                            />
                                                        </div>
                                                        <div className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">
                                                            اكتب أول حرف أو كلمة كاملة
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </th>

                                {/* عمود المنتجات الرئيسية */}
                                <th className="px-6 py-4 font-semibold border-b dark:aseel-border-soft">
                                    <div className="flex items-center gap-2">
                                        <Package className="w-4 h-4 text-[var(--color-primary)]" />
                                        المنتجات الرئيسية
                                    </div>
                                </th>

                                {/* عمود الإجمالي */}
                                <th className="px-6 py-4 font-semibold border-b dark:aseel-border-soft text-center">
                                    <div className="flex items-center justify-center gap-2">
                                        <button
                                            onClick={() => handleSort('grandTotal')}
                                            className="flex items-center gap-2 hover:aseel-text-accent dark:hover:aseel-text-soft transition-colors"
                                        >
                                            <DollarSign className="w-4 h-4" />
                                            الإجمالي
                                            {getSortIcon('grandTotal')}
                                        </button>
                                        <div className="relative">
                                            <button
                                                onClick={() => setActiveColumnFilter(activeColumnFilter === 'grandTotal' ? null : 'grandTotal')}
                                                className={`p-1 rounded ${activeColumnFilter === 'grandTotal' || columnFilters.grandTotal !== ''
                                                    ? 'aseel-text-accent dark:aseel-text-soft aseel-bg-accent-bg dark:aseel-bg-panel/20'
                                                    : 'aseel-text-soft hover:aseel-text-soft dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                                    }`}
                                            >
                                                <Filter className="w-3 h-3" />
                                            </button>
                                            {activeColumnFilter === 'grandTotal' && (
                                                <div className="absolute left-0 top-full mt-1 z-50 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg shadow-xl p-3 min-w-[220px]">
                                                    <div className="flex flex-col gap-2">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-xs font-medium aseel-text-soft dark:aseel-text-soft">فلترة المبلغ</span>
                                                            <button
                                                                onClick={() => clearColumnFilter('grandTotal')}
                                                                className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded"
                                                            >
                                                                <X className="w-3 h-3" />
                                                            </button>
                                                        </div>
                                                        <div className="relative">
                                                            <input
                                                                type="text"
                                                                placeholder="أدخل المبلغ..."
                                                                value={columnFilters.grandTotal}
                                                                onChange={(e) => handleColumnFilter('grandTotal', e.target.value)}
                                                                className="w-full px-3 py-2 text-sm border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                                                autoFocus
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {paginatedInvoices.map((inv) => (
                                <tr
                                    key={inv.id}
                                    onClick={(e) => handleRowClick(inv, e)}
                                    className="hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 transition-colors cursor-pointer group"
                                >
                                    <td className="px-6 py-4 font-medium aseel-text-ink dark:text-white">
                                        <div className="flex items-center gap-2">
                                            <Calendar className="w-4 h-4 aseel-text-soft" />
                                            {inv.invoiceDate}
                                        </div>
                                        <div className="text-xs aseel-text-soft mt-1">
                                            أرشفت: {new Date(inv.createdAt).toLocaleDateString('ar-EG')}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className="font-mono aseel-bg-panel dark:aseel-bg-panel px-2 py-1 rounded text-sm font-semibold aseel-text-ink dark:aseel-text-soft">
                                            {inv.invoiceNumber}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="font-medium aseel-text-ink dark:text-white truncate max-w-[200px]">
                                            {(() => {
                                                const supplier = suppliers.find(s => s.id === inv.supplierId);
                                                return supplier?.alias || supplier?.tradeName || inv.factoryName || '-';
                                            })()}
                                        </div>
                                    </td>
                                    {/* Top Products Column */}
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-1">
                                            {(() => {
                                                const topProducts = getTopProductsByQuantity(inv);
                                                if (topProducts.length === 0) {
                                                    return (
                                                        <div className="text-xs aseel-text-soft dark:aseel-text-soft">لا توجد منتجات</div>
                                                    );
                                                }
                                                return (
                                                    <div className="flex flex-col gap-1.5">
                                                        {topProducts.map((item, idx) => (
                                                            <div key={idx} className="flex items-center gap-2 aseel-bg-panel dark:aseel-bg-panel/50 p-1 rounded-md border aseel-border-soft dark:aseel-border-soft">
                                                                <div className="relative w-6 h-6 shrink-0 rounded overflow-hidden aseel-bg-grid-head dark:aseel-bg-panel">
                                                                    {item.imageUrls && item.imageUrls.length > 0 ? (
                                                                        <img src={item.imageUrls[0]} alt={item.name} className="w-full h-full object-cover" />
                                                                    ) : (
                                                                        <div className="flex items-center justify-center w-full h-full text-[8px] font-bold aseel-text-soft">
                                                                            {item.name.charAt(0)}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                <div className="flex flex-col min-w-0">
                                                                    <div className="flex items-center gap-2">
                                                                        <span className="text-xs font-medium aseel-text-ink dark:aseel-text-soft truncate max-w-[120px]" title={item.name}>
                                                                            {item.name}
                                                                        </span>
                                                                        <span className="text-[10px] aseel-bg-field dark:aseel-bg-panel px-1 rounded aseel-text-soft dark:aseel-text-soft border aseel-border-soft dark:aseel-border-soft shrink-0">
                                                                            x{item.quantity}
                                                                        </span>
                                                                    </div>
                                                                    <span className="text-[10px] aseel-text-accent dark:aseel-text-soft font-mono flex items-center gap-1">
                                                                        HS: {(() => {
                                                                            const dbItem = allDbItems?.find(d => d.id === item.itemId || d.id === item.id);
                                                                            return item.hsCodePrimary || dbItem?.hsCodePrimary || "—";
                                                                        })()}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        ))}
                                                        {inv.items.length > 3 && (
                                                            <span className="text-[10px] aseel-text-soft pr-1">
                                                                +{inv.items.length - 3} المزيد
                                                            </span>
                                                        )}
                                                    </div>
                                                );
                                            })()}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <span className="font-bold text-green-600 dark:text-green-400">
                                            {(inv.grandTotal || 0).toLocaleString()} $
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* القائمة المنبثقة عند النقر على الصف */}
                {selectedInvoice && menuPosition && (
                    <div
                        className="context-menu absolute z-50 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl shadow-2xl min-w-[240px] animate-in fade-in zoom-in duration-200"
                        style={{
                            top: `${menuPosition.top}px`,
                            left: `${menuPosition.left}px`,
                            transform: 'translateY(-50%)'
                        }}
                    >
                        <div className="p-4">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-2">
                                    <FileText className="w-5 h-5 aseel-text-soft" />
                                    <span className="font-bold aseel-text-ink dark:text-white">
                                        {selectedInvoice.invoiceNumber}
                                    </span>
                                </div>
                                <button
                                    onClick={closeContextMenu}
                                    className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            <div className="space-y-2">
                                <button
                                    onClick={() => {
                                        onViewDetails(selectedInvoice);
                                        closeContextMenu();
                                    }}
                                    className="w-full flex items-center gap-3 px-4 py-3 aseel-text-ink dark:aseel-text-soft hover:aseel-bg-accent-bg dark:hover:aseel-bg-panel/20 hover:aseel-text-accent dark:hover:aseel-text-soft rounded-lg transition-colors"
                                >
                                    <Eye className="w-4 h-4 aseel-text-soft" />
                                    <span className="font-medium">عرض الفاتورة</span>
                                    <span className="text-xs aseel-text-soft ml-auto">للقراءة فقط</span>
                                </button>

                                <button
                                    onClick={() => {
                                        onEdit(selectedInvoice);
                                        closeContextMenu();
                                    }}
                                    className="w-full flex items-center gap-3 px-4 py-3 aseel-text-ink dark:aseel-text-soft hover:bg-green-50 dark:hover:bg-green-900/20 hover:text-green-600 dark:hover:text-green-400 rounded-lg transition-colors"
                                >
                                    <Edit2 className="w-4 h-4 text-green-500" />
                                    <span className="font-medium">تعديل الفاتورة</span>
                                </button>

                                <button
                                    onClick={() => {
                                        if (onConvertToMain) onConvertToMain(selectedInvoice);
                                        closeContextMenu();
                                    }}
                                    className="w-full flex items-center gap-3 px-4 py-3 aseel-text-ink dark:aseel-text-soft hover:bg-[var(--color-primary-hover)] dark:hover:bg-[var(--color-primary-hover)]/20 hover:text-[var(--color-primary-hover)] dark:hover:text-[var(--color-primary-hover)] rounded-lg transition-colors"
                                >
                                    <ArrowRight className="w-4 h-4 text-[var(--color-primary)]" />
                                    <span className="font-medium">تحويل إلى فاتورة رئيسية</span>
                                </button>

                                <div className="mt-4 pt-4 border-t aseel-border-soft dark:aseel-border-soft">
                                    <button
                                        onClick={() => {
                                            if (onDelete) onDelete(selectedInvoice);
                                            closeContextMenu();
                                        }}
                                        className="w-full flex items-center gap-3 px-4 py-3 aseel-text-ink dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel/20 hover:aseel-text-state dark:hover:aseel-text-soft rounded-lg transition-colors"
                                    >
                                        <Trash2 className="w-4 h-4 aseel-text-soft" />
                                        <span className="font-medium">حذف نهائي</span>
                                    </button>
                                </div>

                                <div className="mt-4 pt-4 border-t aseel-border-soft dark:aseel-border-soft">
                                    <div className="text-xs aseel-text-soft dark:aseel-text-soft text-center">
                                        انقر خارج القائمة للإغلاق
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* معلومات وأدوات التصفح */}
                {sortedInvoices.length === 0 ? (
                    <div className="text-center py-12 border-t aseel-border-soft dark:aseel-border-soft">
                        <div className="flex flex-col items-center justify-center gap-4">
                            <div className="w-16 h-16 aseel-bg-panel dark:aseel-bg-panel rounded-full flex items-center justify-center">
                                <Search className="w-8 h-8 aseel-text-soft" />
                            </div>
                            <div className="aseel-text-soft dark:aseel-text-soft">
                                <div className="font-medium text-lg">لم يتم العثور على نتائج</div>
                                <div className="text-sm mt-1">جرب تعديل معايير البحث أو الفلترة</div>
                            </div>
                            <button
                                onClick={clearAllFilters}
                                className="px-4 py-2 aseel-bg-accent hover:aseel-bg-accent dark:aseel-bg-accent-bg dark:hover:aseel-bg-accent text-white rounded-lg flex items-center gap-2 transition-colors"
                            >
                                <X className="w-4 h-4" />
                                مسح جميع الفلاتر
                            </button>
                        </div>
                    </div>
                ) : (
                    <>
                        {/* تفاصيل الفلترة النشطة */}
                        {hasActiveFilters && (
                            <div className="px-6 py-3 border-t aseel-border-soft dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel/50">
                                <div className="flex flex-wrap items-center gap-2 text-sm">
                                    <span className="aseel-text-soft dark:aseel-text-soft">فلاتر نشطة:</span>

                                    {searchTerm && (
                                        <span className="inline-flex items-center gap-1 aseel-bg-accent-bg dark:aseel-bg-panel/30 aseel-text-accent dark:aseel-text-soft px-2 py-1 rounded-full text-xs">
                                            بحث: "{searchTerm}"
                                            <button
                                                onClick={() => setSearchTerm('')}
                                                className="p-0.5 hover:aseel-bg-grid-head dark:hover:aseel-bg-panel/50 rounded-full"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </span>
                                    )}

                                    {(Object.entries(columnFilters) as [ColumnFilterKeys, string][]).map(([column, value]) => (
                                        value.trim() !== '' && (
                                            <span key={column} className="inline-flex items-center gap-1 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 px-2 py-1 rounded-full text-xs">
                                                {column === 'invoiceDate' && 'تاريخ: '}
                                                {column === 'invoiceNumber' && 'رقم: '}
                                                {column === 'factoryName' && 'مورد: '}
                                                {column === 'grandTotal' && 'مبلغ: '}
                                                "{value}"
                                                <button
                                                    onClick={() => clearColumnFilter(column)}
                                                    className="p-0.5 hover:bg-green-200 dark:hover:bg-green-900/50 rounded-full"
                                                >
                                                    <X className="w-3 h-3" />
                                                </button>
                                            </span>
                                        )
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* التصفح */}
                        <div className="px-6 py-3 border-t aseel-border-soft dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel/50">
                            <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                                <div className="text-sm aseel-text-soft dark:aseel-text-soft">
                                    عرض <span className="font-bold aseel-text-accent dark:aseel-text-soft">{startIndex + 1}</span> إلى <span className="font-bold aseel-text-accent dark:aseel-text-soft">{Math.min(endIndex, sortedInvoices.length)}</span> من أصل <span className="font-bold">{sortedInvoices.length}</span> فاتورة
                                    {sortedInvoices.length !== invoices.length && (
                                        <span className="text-xs"> (مفلترة من {invoices.length})</span>
                                    )}
                                </div>

                                {totalPages > 1 && (
                                    <div className="flex items-center gap-2">
                                        {/* Previous button */}
                                        <button
                                            onClick={() => goToPage(currentPage - 1)}
                                            disabled={currentPage === 1}
                                            className="p-2 aseel-text-soft dark:aseel-text-soft hover:aseel-text-ink dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            <ChevronRight className="w-4 h-4" />
                                        </button>

                                        {/* Page numbers */}
                                        <div className="flex items-center gap-1">
                                            {getPageNumbers().map((page, idx) => (
                                                typeof page === 'number' ? (
                                                    <button
                                                        key={idx}
                                                        onClick={() => goToPage(page)}
                                                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${currentPage === page
                                                            ? 'aseel-bg-accent text-white'
                                                            : 'aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft aseel-text-ink dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                                            }`}
                                                    >
                                                        {page}
                                                    </button>
                                                ) : (
                                                    <span key={idx} className="px-2 aseel-text-soft">...</span>
                                                )
                                            ))}
                                        </div>

                                        {/* Next button */}
                                        <button
                                            onClick={() => goToPage(currentPage + 1)}
                                            disabled={currentPage === totalPages}
                                            className="p-2 aseel-text-soft dark:aseel-text-soft hover:aseel-text-ink dark:hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            <ChevronLeft className="w-4 h-4" />
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};