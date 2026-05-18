import React, { useState, useRef, useEffect } from 'react';
import { PriceOffer, Supplier, PriceOfferStatus } from '../../../types';
import { StatusBadge } from './StatusBadge';
import {
    FileText, Search, Plus, Calendar,
    Package, DollarSign, Edit2, Eye, CheckCircle, AlertCircle, Clock, MessageSquare,
    ChevronDown, X, Tag
} from 'lucide-react';


interface PriceOfferListProps {
    offers: PriceOffer[];
    suppliers: Supplier[];
    activeFilter: PriceOfferStatus | 'all';
    searchQuery: string;
    onFilterChange: (filter: PriceOfferStatus | 'all') => void;
    onSearchChange: (query: string) => void;
    onEdit: (offer: PriceOffer) => void;
    onDelete: (id: string) => void;
    onCreateNew: () => void;
    onClearFilter: () => void;
    onViewDetails: (offer: PriceOffer) => void;
    onChangeStatus: (offerId: string, newStatus: PriceOfferStatus) => void;
    allDbItems?: any[];
}

export const PriceOfferList: React.FC<PriceOfferListProps> = ({
    offers,
    suppliers,
    activeFilter,
    searchQuery,
    onFilterChange,
    onSearchChange,
    onEdit,
    onDelete,
    onCreateNew,
    onClearFilter,
    onViewDetails,
    onChangeStatus,
    allDbItems
}) => {
    const [dropdownOpen, setDropdownOpen] = useState<string | null>(null);
    const [statusDropdown, setStatusDropdown] = useState<string | null>(null);
    const [selectedOffer, setSelectedOffer] = useState<PriceOffer | null>(null);
    const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
    const tableRef = useRef<HTMLDivElement>(null);

    // Helper function to get top 3 products by quantity
    const getTopProductsByQuantity = (offer: PriceOffer) => {
        if (!offer.items || offer.items.length === 0) return [];
        return [...offer.items]
            .sort((a, b) => (b.quantity || 0) - (a.quantity || 0))
            .slice(0, 3);
    };

    // دالة لاختصار النص الطويل
    const truncateText = (text: string, maxLength: number = 100) => {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    };

    // Handle row click for context menu
    const handleRowClick = (offer: PriceOffer, e: React.MouseEvent) => {
        e.stopPropagation();
        setSelectedOffer(offer);
        setMenuPosition({
            top: e.clientY,
            left: e.clientX
        });
        setDropdownOpen(null);
        setStatusDropdown(null);
    };

    // Close context menu when clicking outside
    useEffect(() => {
        if (!menuPosition) return;

        const handleClickOutside = (e: MouseEvent) => {
            setMenuPosition(null);
            setSelectedOffer(null);
        };

        const timer = setTimeout(() => {
            document.addEventListener('click', handleClickOutside);
        }, 100);

        return () => {
            clearTimeout(timer);
            document.removeEventListener('click', handleClickOutside);
        };
    }, [menuPosition]);

    const filteredOffers = React.useMemo(() => {
        return offers.filter(offer => {
            if (activeFilter !== 'all' && offer.status !== activeFilter) return false;

            if (searchQuery.trim()) {
                const query = searchQuery.toLowerCase();
                const supplier = suppliers.find(s => s.id === offer.supplierId);

                // تحديث منطق البحث ليشمل الاسم المستعار والملاحظات الداخلية
                const supplierName = (supplier?.alias || supplier?.tradeName || '').toLowerCase();

                const matchesOfferNumber = offer.offerNumber?.toLowerCase().includes(query);
                const matchesSupplier = supplierName.includes(query);
                const matchesFactoryName = offer.factoryName?.toLowerCase().includes(query);
                const matchesItems = offer.items?.some(item =>
                    item.name?.toLowerCase().includes(query)
                );
                const matchesInternalNotes = (offer.internalNotes || '').toLowerCase().includes(query);

                return matchesOfferNumber || matchesSupplier || matchesFactoryName ||
                    matchesItems || matchesInternalNotes;
            }

            return true;
        })
            .sort((a, b) => {
                if (a.status === 'under_discussion' && b.status !== 'under_discussion') return -1;
                if (a.status !== 'under_discussion' && b.status === 'under_discussion') return 1;
                return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
            });
    }, [offers, activeFilter, searchQuery, suppliers]);

    const toggleStatusDropdown = (id: string) => {
        setStatusDropdown(statusDropdown === id ? null : id);
        setDropdownOpen(null);
    };

    const handleStatusChange = (offerId: string, newStatus: PriceOfferStatus) => {
        onChangeStatus(offerId, newStatus);
        setStatusDropdown(null);
    };

    const statusOptions = [
        { value: 'initial' as PriceOfferStatus, label: 'أولية', icon: Clock, color: 'text-gray-500' },
        { value: 'pending_info' as PriceOfferStatus, label: 'بانتظار المعلومات', icon: AlertCircle, color: 'text-yellow-500' },
        { value: 'under_discussion' as PriceOfferStatus, label: 'تحت المناقشة', icon: MessageSquare, color: 'text-blue-500' },
        { value: 'approved_for_shipping' as PriceOfferStatus, label: 'معتمد للشراء', icon: CheckCircle, color: 'text-green-500' },
        { value: 'rejected' as PriceOfferStatus, label: 'مرفوضة', icon: X, color: 'text-red-500' }
    ];

    // دالة مساعدة للحصول على اسم العرض (الاسم المستعار أو الأصلي)
    const getSupplierDisplayName = (supplierId: string, factoryName?: string) => {
        const supplier = suppliers.find(s => s.id === supplierId);
        if (supplier) {
            return supplier.alias || supplier.tradeName;
        }
        return factoryName || 'غير محدد';
    };

    const getSupplierContact = (supplierId: string) => {
        const supplier = suppliers.find(s => s.id === supplierId);
        return supplier?.salesRepName || supplier?.phone || '-';
    };

    return (
        <div className="space-y-6">
            {/* Search Bar */}
            {/* Search Bar */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
                    <div className="text-sm text-gray-500">
                        {/* Static Shipping Terms now used */}
                    </div>
                </div>
            </div>

            {/* Table View */}
            <div ref={tableRef} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-visible">
                <div className="overflow-x-auto overflow-y-visible min-h-[400px]">
                    <table className="w-full text-right">
                        <thead className="bg-gray-50 dark:bg-gray-900">
                            <tr>
                                <th className="py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2">
                                        <FileText className="w-4 h-4" />
                                        اسم الفاتورة
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2">
                                        <Package className="w-4 h-4" />
                                        المورد
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2">
                                        <Calendar className="w-4 h-4" />
                                        التاريخ
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2">
                                        <Package className="w-4 h-4 text-[var(--color-primary)]" />
                                        المنتجات الرئيسية
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2">
                                        <Tag className="w-4 h-4" />
                                        الحالة والملاحظات
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2">
                                        <DollarSign className="w-4 h-4" />
                                        الإجمالي
                                    </div>
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {filteredOffers.map((offer) => {
                                const formattedDate = new Date(offer.createdAt).toLocaleDateString('ar-EG', {
                                    year: 'numeric',
                                    month: 'short',
                                    day: 'numeric'
                                });

                                return (
                                    <tr
                                        key={offer.id}
                                        onClick={(e) => handleRowClick(offer, e)}
                                        className={`hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors cursor-pointer ${offer.status === 'under_discussion'
                                            ? 'bg-blue-50/50 dark:bg-blue-900/10 border-l-4 border-l-blue-500'
                                            : ''
                                            }`}
                                    >
                                        <td className="py-3 px-4">
                                            <div className="flex flex-col">
                                                <span className="font-mono font-bold text-gray-900 dark:text-white">
                                                    {offer.offerNumber}
                                                </span>
                                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                                    {offer.id?.slice(-8)}
                                                </span>
                                            </div>
                                        </td>

                                        {/* عمود المورد المحدث */}
                                        <td className="py-3 px-4">
                                            <div className="flex items-center gap-2">
                                                <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                                                    <Package className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="font-medium text-gray-900 dark:text-white truncate max-w-[150px]">
                                                        {/* هنا التغيير: عرض الاسم المستعار أو الأصلي */}
                                                        {getSupplierDisplayName(offer.supplierId, offer.factoryName)}
                                                    </span>
                                                    <span className="text-xs text-gray-500 dark:text-gray-400">
                                                        {getSupplierContact(offer.supplierId)}
                                                    </span>
                                                </div>
                                            </div>
                                        </td>

                                        <td className="py-3 px-4">
                                            <div className="flex flex-col">
                                                <span className="text-gray-900 dark:text-white">{formattedDate}</span>
                                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                                    {new Date(offer.createdAt).toLocaleTimeString('ar-EG', {
                                                        hour: '2-digit',
                                                        minute: '2-digit'
                                                    })}
                                                </span>
                                            </div>
                                        </td>

                                        <td className="py-3 px-4">
                                            <div className="flex items-center gap-1">
                                                {(() => {
                                                    const topProducts = getTopProductsByQuantity(offer);
                                                    if (topProducts.length === 0) {
                                                        return (
                                                            <div className="text-xs text-gray-400 dark:text-gray-500">لا توجد منتجات</div>
                                                        );
                                                    }
                                                    return (
                                                        <div className="flex flex-col gap-1.5">
                                                            {topProducts.map((item, idx) => (
                                                                <div key={idx} className="flex items-center gap-2 bg-gray-50 dark:bg-gray-900/50 p-1 rounded-md border border-gray-100 dark:border-gray-700/50">
                                                                    <div className="w-7 h-7 shrink-0 rounded overflow-hidden bg-gray-200 dark:bg-gray-700 border border-gray-200 dark:border-gray-600">
                                                                        {item.imageUrls && item.imageUrls.length > 0 ? (
                                                                            <img
                                                                                src={item.imageUrls[0]}
                                                                                alt={item.name}
                                                                                className="w-full h-full object-cover"
                                                                            />
                                                                        ) : (
                                                                            <div className="w-full h-full flex items-center justify-center text-gray-400">
                                                                                <Package className="w-3 h-3" />
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    <div className="flex flex-col min-w-0">
                                                                        <div className="flex items-center gap-2">
                                                                            <span className="text-xs font-medium text-gray-700 dark:text-gray-200 truncate max-w-[120px]" title={item.name}>
                                                                                {item.name}
                                                                            </span>
                                                                            <span className="text-[10px] bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-1 rounded border border-blue-100 dark:border-blue-800 shrink-0">
                                                                                x{item.quantity}
                                                                            </span>
                                                                        </div>
                                                                        <span className="text-[10px] text-gray-500 dark:text-gray-400 font-mono">
                                                                            HS: {(() => {
                                                                                const dbItem = allDbItems?.find(d => d.id === item.itemId || d.id === item.id);
                                                                                return item.hsCodePrimary || dbItem?.hsCodePrimary || "—";
                                                                            })()}
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                            {(offer.items?.length || 0) > 3 && (
                                                                <span className="text-[10px] text-gray-400 pr-1">
                                                                    +{(offer.items?.length || 0) - 3} المزيد
                                                                </span>
                                                            )}
                                                        </div>
                                                    );
                                                })()}
                                            </div>
                                        </td>

                                        {/* عمود الحالة والملاحظات الداخلية */}
                                        <td className="py-3 px-4" onClick={(e) => e.stopPropagation()}>
                                            <div className="relative">
                                                <button
                                                    onClick={() => toggleStatusDropdown(offer.id)}
                                                    className="flex items-center gap-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg p-1 transition-colors"
                                                >
                                                    <StatusBadge status={offer.status} />
                                                    <ChevronDown className={`w-3 h-3 transition-transform ${statusDropdown === offer.id ? 'rotate-180' : ''
                                                        }`} />
                                                </button>

                                                {statusDropdown === offer.id && (
                                                    <div className="absolute top-full right-0 mt-2 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl min-w-[220px] overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                                                        <div className="p-1">
                                                            {statusOptions.map((option) => (
                                                                <button
                                                                    key={option.value}
                                                                    onClick={() => handleStatusChange(offer.id, option.value)}
                                                                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg transition-colors ${offer.status === option.value
                                                                        ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                                                                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                                                                        }`}
                                                                >
                                                                    <div className={`p-1.5 rounded-md ${offer.status === option.value ? 'bg-blue-100 dark:bg-blue-900/40' : 'bg-gray-100 dark:bg-gray-800'}`}>
                                                                        <option.icon className={`w-4 h-4 ${option.color}`} />
                                                                    </div>
                                                                    <span className="font-medium flex-1 text-right">
                                                                        {option.label}
                                                                    </span>
                                                                    {offer.status === option.value && (
                                                                        <CheckCircle className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                                                    )}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* عرض الملاحظات الداخلية بدلاً من statusNotes */}
                                                {offer.internalNotes && (
                                                    <div className="mt-3 relative group">
                                                        <div className="absolute -right-1 top-0 bottom-0 w-1 bg-yellow-400 dark:bg-yellow-500 rounded-full"></div>
                                                        <div className="pr-3">
                                                            <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">
                                                                {truncateText(offer.internalNotes, 100)}
                                                            </p>
                                                            {offer.internalNotes.length > 100 && (
                                                                <div className="absolute z-10 invisible group-hover:visible bottom-full right-3 mb-2 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg p-3 max-w-xs shadow-xl">
                                                                    <div className="font-medium mb-1 flex items-center gap-2">
                                                                        <MessageSquare className="w-4 h-4" />
                                                                        ملاحظات داخلية
                                                                    </div>
                                                                    <p className="text-gray-300 whitespace-pre-line">
                                                                        {offer.internalNotes}
                                                                    </p>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </td>

                                        <td className="py-3 px-4">
                                            <div className="flex flex-col">
                                                <div className="font-bold text-green-600 dark:text-green-400 flex items-center gap-1">
                                                    <DollarSign className="w-4 h-4" />
                                                    {offer.grandTotal.toLocaleString()} $
                                                </div>
                                                <div className="text-xs text-gray-500 dark:text-gray-400">
                                                    ضريبة: {offer.taxAmount?.toFixed(2)} $
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>

                    {filteredOffers.length === 0 && (
                        <div className="text-center py-16">
                            <FileText className="w-20 h-20 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
                            <h3 className="text-lg font-medium text-gray-500 dark:text-gray-400 mb-2">
                                {searchQuery ? 'لم يتم العثور على عروض' : 'لا توجد عروض'}
                            </h3>
                            <p className="text-gray-400 dark:text-gray-500 mb-6">
                                {searchQuery
                                    ? 'لا توجد عروض تطابق بحثك'
                                    : activeFilter === 'all'
                                        ? 'لم يتم إنشاء أي عروض أسعار بعد'
                                        : `لا توجد عروض بحالة "${activeFilter}"`}
                            </p>
                            {(activeFilter !== 'all' || searchQuery) && (
                                <button
                                    onClick={onClearFilter}
                                    className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg inline-flex items-center gap-2 mr-2"
                                >
                                    <X className="w-4 h-4" />
                                    مسح الفلترة
                                </button>
                            )}
                            <button
                                onClick={onCreateNew}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded-lg inline-flex items-center gap-2"
                            >
                                <Plus className="w-4 h-4" />
                                إنشاء أول عرض
                            </button>
                        </div>
                    )}
                </div>

                {filteredOffers.length > 0 && (
                    <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                        <div className="flex items-center justify-between">
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                                عرض <span className="font-medium">{filteredOffers.length}</span> من <span className="font-medium">{offers.length}</span> عرض
                            </div>
                            <div className="flex gap-1">
                                <button className="px-3 py-1 rounded-lg bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed">
                                    السابق
                                </button>
                                <button className="px-3 py-1 rounded-lg bg-blue-600 text-white">1</button>
                                <button className="px-3 py-1 rounded-lg bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600">
                                    2
                                </button>
                                <button className="px-3 py-1 rounded-lg bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600">
                                    التالي
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {menuPosition && selectedOffer && (
                <div
                    className="fixed bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl min-w-[160px] overflow-hidden z-50"
                    style={{
                        top: `${menuPosition.top}px`,
                        left: `${menuPosition.left}px`
                    }}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="p-1">
                        <button
                            onClick={() => {
                                onViewDetails(selectedOffer);
                                setMenuPosition(null);
                                setSelectedOffer(null);
                            }}
                            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors text-right"
                        >
                            <Eye className="w-4 h-4 text-blue-500" />
                            عرض
                        </button>
                        <button
                            onClick={() => {
                                onEdit(selectedOffer);
                                setMenuPosition(null);
                                setSelectedOffer(null);
                            }}
                            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors text-right"
                        >
                            <Edit2 className="w-4 h-4 text-green-500" />
                            تعديل
                        </button>
                    </div>
                </div>
            )}


        </div>
    );
};