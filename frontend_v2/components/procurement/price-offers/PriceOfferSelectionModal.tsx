import React, { useState } from 'react';
import { PriceOffer } from '../../../types';
import { X, Search, FileText, Calendar, DollarSign, ArrowRight, Building, CheckCircle, Users, Package, TrendingUp, Info, Truck } from 'lucide-react';
import { formatDateValue } from "../../../utils/formatDate";

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
        if (offer.status === 'approved_for_shipping') return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 aseel-border-soft dark:border-green-800/50';
        if (offer.status === 'under_discussion') return 'aseel-bg-accent-bg aseel-text-ink dark:aseel-bg-panel/30 dark:aseel-text-soft aseel-border-accent dark:aseel-border-soft/50';
        return 'aseel-bg-panel aseel-text-ink dark:aseel-bg-panel dark:aseel-text-soft aseel-border-soft dark:aseel-border-soft';
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
            <div className={`${compactMode ? 'max-w-lg' : 'max-w-2xl'} aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-xl w-full border aseel-border-soft dark:aseel-border-soft flex flex-col max-h-[90vh]`}>

                {/* Header */}
                <div className={`${compactMode ? 'p-4' : 'p-5'} border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center bg-gradient-to-r aseel-bg-panel to-white/50 dark:aseel-bg-panel/50 dark:aseel-bg-panel/50`}>
                    <div className="flex items-center gap-3">
                        <div className={`${compactMode ? 'p-2' : 'p-2.5'} aseel-bg-accent-bg dark:aseel-bg-panel/30 rounded-lg`}>
                            <FileText className={`${compactMode ? 'w-5 h-5' : 'w-6 h-6'} aseel-text-accent dark:aseel-text-soft`} />
                        </div>
                        <div>
                            <h3 className={`${compactMode ? 'text-base' : 'text-lg'} font-bold aseel-text-ink dark:text-white`}>
                                اختر عرض سعر للتحويل
                            </h3>
                            <p className={`${compactMode ? 'text-xs' : 'text-sm'} aseel-text-soft dark:aseel-text-soft mt-0.5`}>
                                {offers.length} عرض متاح • {filteredOffers.length} نتيجة بحث
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className={`${compactMode ? 'p-1.5' : 'p-2'} hover:aseel-bg-grid-head dark:hover:aseel-bg-panel rounded-lg transition-colors`}
                        title="إغلاق"
                    >
                        <X className="w-4 h-4 aseel-text-soft" />
                    </button>
                </div>

                {/* Search */}
                <div className={`${compactMode ? 'p-3' : 'p-4'} border-b aseel-border-soft dark:aseel-border-soft`}>
                    <div className="relative">
                        <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 aseel-text-soft w-4 h-4" />
                        <input
                            type="text"
                            placeholder="ابحث برقم العرض، المورد، المنتج..."
                            className="w-full p-2.5 pr-9 text-sm border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            autoFocus
                        />
                    </div>

                    {/* Quick Stats */}
                    {offers.length > 0 && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                            <div className="text-center p-1.5 aseel-bg-accent-bg dark:aseel-bg-panel/20 rounded border aseel-border-soft dark:aseel-border-soft/30">
                                <p className="text-xs aseel-text-accent dark:aseel-text-soft">إجمالي القيمة</p>
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
                            <div className="text-center p-1.5 aseel-bg-panel dark:aseel-bg-panel/20 rounded border aseel-border-soft dark:aseel-border-soft/30">
                                <p className="text-xs aseel-text-soft dark:aseel-text-soft">متاح للشحن</p>
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
                                    className={`p-3 aseel-bg-field dark:aseel-bg-panel/30 border rounded-lg cursor-pointer transition-all duration-150 ${isSelected
                                        ? 'aseel-border-soft dark:aseel-border-soft aseel-bg-accent-bg/50 dark:aseel-bg-panel/20'
                                        : 'aseel-border-soft dark:aseel-border-soft hover:aseel-border-soft dark:hover:aseel-border-soft'
                                        }`}
                                >
                                    <div className="flex justify-between items-start gap-3">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-bold aseel-text-ink dark:text-white text-sm">
                                                        {offer.offerNumber}
                                                    </span>
                                                    <span className={`px-1.5 py-0.5 rounded text-xs border ${getStatusColor(offer)}`}>
                                                        {getStatusText(offer.status)}
                                                    </span>
                                                </div>

                                                <div className="text-xs aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
                                                    <Calendar className="w-3 h-3" />
                                                    {formatDateValue(offer.createdAt)}
                                                </div>
                                            </div>

                                            <div className="flex flex-col sm:flex-row sm:items-center gap-3 text-sm">
                                                <div className="flex items-center gap-1.5">
                                                    <Building className="w-3.5 h-3.5 aseel-text-soft" />
                                                    <span className="aseel-text-ink dark:aseel-text-soft truncate">
                                                        {offer.factoryName || 'بدون مورد'}
                                                    </span>
                                                </div>

                                                <div className="flex items-center gap-3">
                                                    <div className="flex items-center gap-1">
                                                        <Package className="w-3.5 h-3.5 aseel-text-soft" />
                                                        <span className="text-xs aseel-bg-panel dark:aseel-bg-panel px-1.5 py-0.5 rounded">
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
                                                <div className="mt-2 text-xs aseel-text-soft dark:aseel-text-soft flex items-start gap-1">
                                                    <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                                    <span className="truncate">{offer.internalNotes}</span>
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex flex-col items-end gap-2">
                                            <div className="text-right">
                                                <div className="text-xs aseel-text-soft dark:aseel-text-soft">القيمة</div>
                                                <div className="font-bold aseel-text-ink dark:text-white text-sm flex items-center gap-0.5">
                                                    <DollarSign className="w-3.5 h-3.5 text-green-500" />
                                                    {stats.totalValue.toLocaleString()}$
                                                </div>
                                            </div>

                                            <div className={`p-1.5 rounded-full ${isSelected
                                                ? 'aseel-bg-accent text-white'
                                                : 'aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft'
                                                }`}>
                                                <ArrowRight className="w-4 h-4" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Quick Stats */}
                                    <div className="grid grid-cols-4 gap-1 mt-3 pt-2 border-t aseel-border-soft dark:aseel-border-soft">
                                        <div className="text-center">
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">المنتجات</div>
                                            <div className="text-sm font-medium">{stats.itemsCount}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">القيمة</div>
                                            <div className="text-sm font-medium">${stats.totalValue.toLocaleString()}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">الشحن</div>
                                            <div className="text-sm font-medium">{stats.shippingIncluded ? 'مشمل' : 'منفصل'}</div>
                                        </div>
                                        <div className="text-center">
                                            <div className="text-xs aseel-text-soft dark:aseel-text-soft">المرفقات</div>
                                            <div className="text-sm font-medium">{stats.hasAttachments ? '✓' : '✗'}</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    ) : (
                        <div className="text-center py-10">
                            <div className="inline-flex p-3 aseel-bg-panel dark:aseel-bg-panel rounded-xl mb-3">
                                <FileText className="w-8 h-8 aseel-text-soft dark:aseel-text-soft" />
                            </div>
                            <h4 className="font-medium aseel-text-ink dark:aseel-text-soft mb-1">
                                لا توجد عروض مطابقة
                            </h4>
                            <p className="text-sm aseel-text-soft dark:aseel-text-soft">
                                {search ? 'لم يتم العثور على عروض تطابق البحث' : 'لا توجد عروض أسعار متاحة'}
                            </p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-3 border-t aseel-border-soft dark:aseel-border-soft aseel-bg-panel/50 dark:aseel-bg-panel/50">
                    <div className="flex justify-between items-center">
                        <div className="text-xs aseel-text-soft dark:aseel-text-soft">
                            {filteredOffers.length === 0 ? (
                                <span>انقر خارج النافذة للإغلاق</span>
                            ) : (
                                <span>انقر على العرض لتحويله إلى صفقة</span>
                            )}
                        </div>
                        <button
                            onClick={onClose}
                            className="px-3 py-1.5 text-sm aseel-bg-grid-head dark:aseel-bg-panel aseel-text-ink dark:aseel-text-soft rounded-lg hover:aseel-bg-grid-head dark:hover:aseel-bg-panel transition-colors"
                        >
                            إغلاق
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};