import React, { useState } from 'react';
import { PriceOffer } from '../../../types';
import { X, Search, FileText, Calendar, DollarSign, ArrowRight, Building, CheckCircle, Users, Package, TrendingUp, Info, Truck } from 'lucide-react';

interface PriceOfferSelectionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (offerId: string) => void;
    offers: PriceOffer[];
    compactMode?: boolean;
}

export const PriceOfferSelectionModal: React.FC<PriceOfferSelectionModalProps> = ({
    isOpen, onClose, onSelect, offers,
    compactMode = false
}) => {
    const [search, setSearch] = useState('');
    const [selectedOffer, setSelectedOffer] = useState<string | null>(null);

    if (!isOpen) return null;

    const filteredOffers = offers.filter(o =>
        o.offerNumber.toLowerCase().includes(search.toLowerCase()) ||
        o.factoryName?.toLowerCase().includes(search.toLowerCase()) ||
        o.supplierId?.toLowerCase().includes(search.toLowerCase())
    );

    const handleSelectOffer = (offerId: string) => {
        setSelectedOffer(offerId);
        onSelect(offerId);
        onClose();
    };

    const getOfferStats = (offer: PriceOffer) => {
        return {
            itemsCount: offer.items?.length || 0,
            totalValue: offer.grandTotal || 0,
            shippingIncluded: offer.shippingIncluded || false,
            hasAttachments: (offer.quote_pdfs?.length || 0) > 0 || (offer.quote_images?.length || 0) > 0
        };
    };

    const getStatusColor = (offer: PriceOffer) => {
        if (offer.status === 'approved_for_shipping') return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800/50';
        if (offer.status === 'under_discussion') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800/50';
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600';
    };

    const getStatusText = (status: string) => {
        const statusMap: Record<string, string> = {
            'approved_for_shipping': 'معتمد للشحن',
            'under_discussion': 'قيد المناقشة',
            'initial': 'أولي',
            'pending_info': 'بانتظار معلومات'
        };
        return statusMap[status] || status;
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-3 md:p-4">
            <div className={`${compactMode ? 'max-w-lg' : 'max-w-2xl'} bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full border border-gray-200 dark:border-gray-700 flex flex-col max-h-[90vh]`}>

                {/* Header */}
                <div className={`${compactMode ? 'p-4' : 'p-5'} border-b border-gray-100 dark:border-gray-700 flex justify-between items-center bg-gradient-to-r from-gray-50 to-white/50 dark:from-gray-800/50 dark:to-gray-900/50`}>
                    <div className="flex items-center gap-3">
                        <div className={`${compactMode ? 'p-2' : 'p-2.5'} bg-blue-100 dark:bg-blue-900/30 rounded-lg`}>
                            <FileText className={`${compactMode ? 'w-5 h-5' : 'w-6 h-6'} text-blue-600 dark:text-blue-400`} />
                        </div>
                        <div>
                            <h3 className={`${compactMode ? 'text-base' : 'text-lg'} font-bold text-gray-900 dark:text-white`}>
                                اختر عرض سعر للتحويل
                            </h3>
                            <p className={`${compactMode ? 'text-xs' : 'text-sm'} text-gray-500 dark:text-gray-400 mt-0.5`}>
                                {offers.length} عرض متاح • {filteredOffers.length} نتيجة بحث
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className={`${compactMode ? 'p-1.5' : 'p-2'} hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors`}
                        title="إغلاق"
                    >
                        <X className="w-4 h-4 text-gray-500" />
                    </button>
                </div>

                {/* Search */}
                <div className={`${compactMode ? 'p-3' : 'p-4'} border-b border-gray-100 dark:border-gray-700`}>
                    <div className="relative">
                        <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                        <input
                            type="text"
                            placeholder="ابحث برقم العرض، المورد، المنتج..."
                            className="w-full p-2.5 pr-9 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            autoFocus
                        />
                    </div>

                    {/* Quick Stats */}
                    {offers.length > 0 && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                            <div className="text-center p-1.5 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-100 dark:border-blue-800/30">
                                <p className="text-xs text-blue-600 dark:text-blue-400">إجمالي القيمة</p>
                                <p className="text-sm font-bold">${offers.reduce((sum, o) => sum + (o.grandTotal || 0), 0).toLocaleString()}</p>
                            </div>
                            <div className="text-center p-1.5 bg-green-50 dark:bg-green-900/20 rounded border border-green-100 dark:border-green-800/30">
                                <p className="text-xs text-green-600 dark:text-green-400">العروض</p>
                                <p className="text-sm font-bold">{offers.length}</p>
                            </div>
                            <div className="text-center p-1.5 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 rounded border border-[var(--color-border)] dark:border-[var(--color-border)]/30">
                                <p className="text-xs text-[var(--color-primary)] dark:text-[var(--color-primary)]">المنتجات</p>
                                <p className="text-sm font-bold">{offers.reduce((sum, o) => sum + (o.items?.length || 0), 0)}</p>
                            </div>
                            <div className="text-center p-1.5 bg-amber-50 dark:bg-amber-900/20 rounded border border-amber-100 dark:border-amber-800/30">
                                <p className="text-xs text-amber-600 dark:text-amber-400">متاح للشحن</p>
                                <p className="text-sm font-bold">{offers.filter(o => o.status === 'approved_for_shipping').length}</p>
                            </div>
                        </div>
                    )}
                </div>

                {/* List */}
                <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                    {filteredOffers.length > 0 ? (
                        filteredOffers.map(offer => {
                            const stats = getOfferStats(offer);
                            const isSelected = selectedOffer === offer.id;

                            return (
                                <div
                                    key={offer.id}
                                    onClick={() => handleSelectOffer(offer.id)}
                                    className={`p-3 bg-white dark:bg-gray-700/30 border rounded-lg cursor-pointer transition-all duration-150 ${isSelected
                                        ? 'border-blue-500 dark:border-blue-400 bg-blue-50/50 dark:bg-blue-900/20'
                                        : 'border-gray-200 dark:border-gray-600 hover:border-blue-300 dark:hover:border-blue-500'
                                        }`}
                                >
                                    <div className="flex justify-between items-start gap-3">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-bold text-gray-900 dark:text-white text-sm">
                                                        {offer.offerNumber}
                                                    </span>
                                                    <span className={`px-1.5 py-0.5 rounded text-xs border ${getStatusColor(offer)}`}>
                                                        {getStatusText(offer.status)}
                                                    </span>
                                                </div>

                                                <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
                                                    <Calendar className="w-3 h-3" />
                                                    {new Date(offer.createdAt).toLocaleDateString('ar-SA')}
                                                </div>
                                            </div>

                                            <div className="flex flex-col sm:flex-row sm:items-center gap-3 text-sm">
                                                <div className="flex items-center gap-1.5">
                                                    <Building className="w-3.5 h-3.5 text-gray-400" />
                                                    <span className="text-gray-700 dark:text-gray-300 truncate">
                                                        {offer.factoryName || 'بدون مورد'}
                                                    </span>
                                                </div>

                                                <div className="flex items-center gap-3">
                                                    <div className="flex items-center gap-1">
                                                        <Package className="w-3.5 h-3.5 text-gray-400" />
                                                        <span className="text-xs bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">
                                                            {stats.itemsCount} منتج
                                                        </span>
                                                    </div>

                                                    {stats.shippingIncluded && (
                                                        <div className="flex items-center gap-1">
                                                            <Truck className="w-3.5 h-3.5 text-green-400" />
                                                            <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-1.5 py-0.5 rounded">
                                                                شامل الشحن
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            {offer.internalNotes && (
                                                <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 flex items-start gap-1">
                                                    <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                                    <span className="truncate">{offer.internalNotes}</span>
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex flex-col items-end gap-2">
                                            <div className="text-right">
                                                <div className="text-xs text-gray-500 dark:text-gray-400">القيمة</div>
                                                <div className="font-bold text-gray-900 dark:text-white text-sm flex items-center gap-0.5">
                                                    <DollarSign className="w-3.5 h-3.5 text-green-500" />
                                                    {stats.totalValue.toLocaleString()}$
                                                </div>
                                            </div>

                                            <div className={`p-1.5 rounded-full ${isSelected
                                                ? 'bg-blue-600 text-white'
                                                : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                                                }`}>
                                                <ArrowRight className="w-4 h-4" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Quick Stats */}
                                    <div className="grid grid-cols-4 gap-1 mt-3 pt-2 border-t border-gray-100 dark:border-gray-700">
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500 dark:text-gray-400">المنتجات</div>
                                            <div className="text-sm font-medium">{stats.itemsCount}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500 dark:text-gray-400">القيمة</div>
                                            <div className="text-sm font-medium">${stats.totalValue.toLocaleString()}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500 dark:text-gray-400">الشحن</div>
                                            <div className="text-sm font-medium">{stats.shippingIncluded ? 'مشمل' : 'منفصل'}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs text-gray-500 dark:text-gray-400">المرفقات</div>
                                            <div className="text-sm font-medium">{stats.hasAttachments ? '✓' : '✗'}</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    ) : (
                        <div className="text-center py-10">
                            <div className="inline-flex p-3 bg-gray-100 dark:bg-gray-800 rounded-xl mb-3">
                                <FileText className="w-8 h-8 text-gray-400 dark:text-gray-600" />
                            </div>
                            <h4 className="font-medium text-gray-800 dark:text-gray-200 mb-1">
                                لا توجد عروض مطابقة
                            </h4>
                            <p className="text-sm text-gray-500 dark:text-gray-400">
                                {search ? 'لم يتم العثور على عروض تطابق البحث' : 'لا توجد عروض أسعار متاحة'}
                            </p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-3 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
                    <div className="flex justify-between items-center">
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            {filteredOffers.length === 0 ? (
                                <span>انقر خارج النافذة للإغلاق</span>
                            ) : (
                                <span>انقر على العرض لتحويله إلى صفقة</span>
                            )}
                        </div>
                        <button
                            onClick={onClose}
                            className="px-3 py-1.5 text-sm bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                        >
                            إغلاق
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};