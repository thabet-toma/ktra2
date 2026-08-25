import React, { useState, useRef, useEffect } from 'react';
import { PriceOffer, Supplier, PriceOfferStatus } from '../../../types';
import { formatMoney } from '../../../utils/formatNumber';
import { StatusBadge } from './StatusBadge';
import { formatDateValue, formatTimeValue } from "../../../utils/formatDate";
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
        { value: 'initial' as PriceOfferStatus, label: 'أولية', icon: Clock, color: 'ktra-text-soft' },
        { value: 'pending_info' as PriceOfferStatus, label: 'بانتظار المعلومات', icon: AlertCircle, color: 'ktra-text-soft' },
        { value: 'under_discussion' as PriceOfferStatus, label: 'تحت المناقشة', icon: MessageSquare, color: 'ktra-text-soft' },
        { value: 'approved_for_shipping' as PriceOfferStatus, label: 'معتمد للشراء', icon: CheckCircle, color: 'text-green-500' },
        { value: 'rejected' as PriceOfferStatus, label: 'مرفوضة', icon: X, color: 'ktra-text-soft' }
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
            <div className="ktra-bg-field dark:ktra-bg-panel rounded-xl border ktra-border-soft dark:ktra-border-soft p-4">
                <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
                    <div className="text-sm ktra-text-soft">
                        {/* Static Shipping Terms now used */}
                    </div>
                </div>
            </div>

            {/* Table View */}
            <div ref={tableRef} className="ktra-bg-field dark:ktra-bg-panel rounded-xl border ktra-border-soft dark:ktra-border-soft shadow-sm overflow-visible">
                <div className="overflow-x-auto overflow-y-visible min-h-[400px]">
                    <table className="w-full text-right">
                        <thead className="ktra-bg-panel dark:ktra-bg-panel">
                            <tr>
                                <th className="py-3 px-4 text-sm font-semibold ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
                                    <div className="flex items-center gap-2">
                                        <FileText className="w-4 h-4" />
                                        اسم الفاتورة
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
                                    <div className="flex items-center gap-2">
                                        <Package className="w-4 h-4" />
                                        المورد
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
                                    <div className="flex items-center gap-2">
                                        <Calendar className="w-4 h-4" />
                                        التاريخ
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
                                    <div className="flex items-center gap-2">
                                        <Package className="w-4 h-4 text-[var(--color-primary)]" />
                                        المنتجات الرئيسية
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
                                    <div className="flex items-center gap-2">
                                        <Tag className="w-4 h-4" />
                                        الحالة والملاحظات
                                    </div>
                                </th>
                                <th className="py-3 px-4 text-sm font-semibold ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
                                    <div className="flex items-center gap-2">
                                        <DollarSign className="w-4 h-4" />
                                        الإجمالي
                                    </div>
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--color-border)]">
                            {filteredOffers.map((offer) => {
                                const formattedDate = formatDateValue(offer.createdAt);

                                return (
                                    <tr
                                        key={offer.id}
                                        onClick={(e) => handleRowClick(offer, e)}
                                        className={`hover:ktra-bg-panel dark:hover:ktra-bg-panel/30 transition-colors cursor-pointer ${offer.status === 'under_discussion'
                                            ? 'ktra-bg-accent-bg/50 dark:ktra-bg-panel/10 border-l-4 border-l-blue-500'
                                            : ''
                                            }`}
                                    >
                                        <td className="py-3 px-4">
                                            <div className="flex flex-col">
                                                <span className="font-mono font-bold ktra-text-ink dark:text-white">
                                                    {offer.offerNumber}
                                                </span>
                                                <span className="text-xs ktra-text-soft dark:ktra-text-soft">
                                                    {offer.id?.slice(-8)}
                                                </span>
                                            </div>
                                        </td>

                                        {/* عمود المورد المحدث */}
                                        <td className="py-3 px-4">
                                            <div className="flex items-center gap-2">
                                                <div className="w-8 h-8 ktra-bg-accent-bg dark:ktra-bg-panel/30 rounded-lg flex items-center justify-center">
                                                    <Package className="w-4 h-4 ktra-text-accent dark:ktra-text-soft" />
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="font-medium ktra-text-ink dark:text-white truncate max-w-[150px]">
                                                        {/* هنا التغيير: عرض الاسم المستعار أو الأصلي */}
                                                        {getSupplierDisplayName(offer.supplierId, offer.factoryName)}
                                                    </span>
                                                    <span className="text-xs ktra-text-soft dark:ktra-text-soft">
                                                        {getSupplierContact(offer.supplierId)}
                                                    </span>
                                                </div>
                                            </div>
                                        </td>

                                        <td className="py-3 px-4">
                                            <div className="flex flex-col">
                                                <span className="ktra-text-ink dark:text-white">{formattedDate}</span>
                                                <span className="text-xs ktra-text-soft dark:ktra-text-soft">
                                                    {formatTimeValue(offer.createdAt)}
                                                </span>
                                            </div>
                                        </td>

                                        <td className="py-3 px-4">
                                            <div className="flex items-center gap-1">
                                                {(() => {
                                                    const topProducts = getTopProductsByQuantity(offer);
                                                    if (topProducts.length === 0) {
                                                        return (
                                                            <div className="text-xs ktra-text-soft dark:ktra-text-soft">لا توجد منتجات</div>
                                                        );
                                                    }
                                                    return (
                                                        <div className="flex flex-col gap-1.5">
                                                            {topProducts.map((item, idx) => (
                                                                <div key={idx} className="flex items-center gap-2 ktra-bg-panel dark:ktra-bg-panel/50 p-1 rounded-md border ktra-border-soft dark:ktra-border-soft/50">
                                                                    <div className="w-7 h-7 shrink-0 rounded overflow-hidden ktra-bg-grid-head dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft">
                                                                        {item.imageUrls && item.imageUrls.length > 0 ? (
                                                                            <img
                                                                                src={item.imageUrls[0]}
                                                                                alt={item.name}
                                                                                className="w-full h-full object-cover"
                                                                            />
                                                                        ) : (
                                                                            <div className="w-full h-full flex items-center justify-center ktra-text-soft">
                                                                                <Package className="w-3 h-3" />
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    <div className="flex flex-col min-w-0">
                                                                        <div className="flex items-center gap-2">
                                                                            <span className="text-xs font-medium ktra-text-ink dark:ktra-text-soft truncate max-w-[120px]" title={item.name}>
                                                                                {item.name}
                                                                            </span>
                                                                            <span className="text-[10px] ktra-bg-accent-bg dark:ktra-bg-panel/30 ktra-text-accent dark:ktra-text-soft px-1 rounded border ktra-border-soft dark:ktra-border-soft shrink-0">
                                                                                x{item.quantity}
                                                                            </span>
                                                                        </div>
                                                                        <span className="text-[10px] ktra-text-soft dark:ktra-text-soft font-mono">
                                                                            HS: {(() => {
                                                                                const dbItem = allDbItems?.find(d => d.id === item.itemId || d.id === item.id);
                                                                                return item.hsCodePrimary || dbItem?.hsCodePrimary || "—";
                                                                            })()}
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                            {(offer.items?.length || 0) > 3 && (
                                                                <span className="text-[10px] ktra-text-soft pr-1">
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
                                                    className="flex items-center gap-2 hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg p-1 transition-colors"
                                                >
                                                    <StatusBadge status={offer.status} />
                                                    <ChevronDown className={`w-3 h-3 transition-transform ${statusDropdown === offer.id ? 'rotate-180' : ''
                                                        }`} />
                                                </button>

                                                {statusDropdown === offer.id && (
                                                    <div className="absolute top-full right-0 mt-2 z-50 ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft rounded-xl shadow-xl min-w-[220px] overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                                                        <div className="p-1">
                                                            {statusOptions.map((option) => (
                                                                <button
                                                                    key={option.value}
                                                                    onClick={() => handleStatusChange(offer.id, option.value)}
                                                                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg transition-colors ${offer.status === option.value
                                                                        ? 'ktra-bg-accent-bg dark:ktra-bg-panel/20 ktra-text-accent dark:ktra-text-soft'
                                                                        : 'ktra-text-ink dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel'
                                                                        }`}
                                                                >
                                                                    <div className={`p-1.5 rounded-md ${offer.status === option.value ? 'ktra-bg-accent-bg dark:ktra-bg-panel/40' : 'ktra-bg-panel dark:ktra-bg-panel'}`}>
                                                                        <option.icon className={`w-4 h-4 ${option.color}`} />
                                                                    </div>
                                                                    <span className="font-medium flex-1 text-right">
                                                                        {option.label}
                                                                    </span>
                                                                    {offer.status === option.value && (
                                                                        <CheckCircle className="w-4 h-4 ktra-text-accent dark:ktra-text-soft" />
                                                                    )}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* عرض الملاحظات الداخلية بدلاً من statusNotes */}
                                                {offer.internalNotes && (
                                                    <div className="mt-3 relative group">
                                                        <div className="absolute -right-1 top-0 bottom-0 w-1 ktra-bg-panel dark:ktra-bg-panel rounded-full"></div>
                                                        <div className="pr-3">
                                                            <p className="text-xs ktra-text-soft dark:ktra-text-soft line-clamp-2">
                                                                {truncateText(offer.internalNotes, 100)}
                                                            </p>
                                                            {offer.internalNotes.length > 100 && (
                                                                <div className="absolute z-10 invisible group-hover:visible bottom-full right-3 mb-2 ktra-bg-panel dark:ktra-bg-panel text-white text-sm rounded-lg p-3 max-w-xs shadow-xl">
                                                                    <div className="font-medium mb-1 flex items-center gap-2">
                                                                        <MessageSquare className="w-4 h-4" />
                                                                        ملاحظات داخلية
                                                                    </div>
                                                                    <p className="ktra-text-soft whitespace-pre-line">
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
                                                <div className="text-xs ktra-text-soft dark:ktra-text-soft">
                                                    ضريبة: {formatMoney(offer.taxAmount ?? 0)} $
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
                            <FileText className="w-20 h-20 ktra-text-soft dark:ktra-text-soft mx-auto mb-4" />
                            <h3 className="text-lg font-medium ktra-text-soft dark:ktra-text-soft mb-2">
                                {searchQuery ? 'لم يتم العثور على عروض' : 'لا توجد عروض'}
                            </h3>
                            <p className="ktra-text-soft dark:ktra-text-soft mb-6">
                                {searchQuery
                                    ? 'لا توجد عروض تطابق بحثك'
                                    : activeFilter === 'all'
                                        ? 'لم يتم إنشاء أي عروض أسعار بعد'
                                        : `لا توجد عروض بحالة "${activeFilter}"`}
                            </p>
                            {(activeFilter !== 'all' || searchQuery) && (
                                <button
                                    onClick={onClearFilter}
                                    className="px-4 py-2 ktra-bg-grid-head dark:ktra-bg-panel ktra-text-ink dark:ktra-text-soft rounded-lg inline-flex items-center gap-2 mr-2"
                                >
                                    <X className="w-4 h-4" />
                                    مسح الفلترة
                                </button>
                            )}
                            <button
                                onClick={onCreateNew}
                                className="px-4 py-2 ktra-bg-accent hover:ktra-bg-accent dark:ktra-bg-accent-bg dark:hover:ktra-bg-accent text-white rounded-lg inline-flex items-center gap-2"
                            >
                                <Plus className="w-4 h-4" />
                                إنشاء أول عرض
                            </button>
                        </div>
                    )}
                </div>

                {filteredOffers.length > 0 && (
                    <div className="px-4 py-3 border-t ktra-border-soft dark:ktra-border-soft ktra-bg-panel dark:ktra-bg-panel/50">
                        <div className="flex items-center justify-between">
                            <div className="text-sm ktra-text-soft dark:ktra-text-soft">
                                عرض <span className="font-medium">{filteredOffers.length}</span> من <span className="font-medium">{offers.length}</span> عرض
                            </div>
                            <div className="flex gap-1">
                                <button className="px-3 py-1 rounded-lg ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft ktra-text-ink dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel disabled:opacity-50 disabled:cursor-not-allowed">
                                    السابق
                                </button>
                                <button className="px-3 py-1 rounded-lg ktra-bg-accent text-white">1</button>
                                <button className="px-3 py-1 rounded-lg ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft ktra-text-ink dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel">
                                    2
                                </button>
                                <button className="px-3 py-1 rounded-lg ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft ktra-text-ink dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel">
                                    التالي
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {menuPosition && selectedOffer && (
                <div
                    className="fixed ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft rounded-xl shadow-xl min-w-[160px] overflow-hidden z-50"
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
                            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium ktra-text-ink dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg transition-colors text-right"
                        >
                            <Eye className="w-4 h-4 ktra-text-soft" />
                            عرض
                        </button>
                        <button
                            onClick={() => {
                                onEdit(selectedOffer);
                                setMenuPosition(null);
                                setSelectedOffer(null);
                            }}
                            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium ktra-text-ink dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg transition-colors text-right"
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