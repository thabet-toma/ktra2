import React, { useMemo } from 'react';
import { PriceOffer, PriceOfferStatus, Supplier } from '../../../types';
import { FileText, DollarSign, User, BarChart3 } from 'lucide-react';

export const StatisticsPanel: React.FC<{ offers: PriceOffer[]; suppliers: Supplier[] }> = ({ offers, suppliers }) => {
    const stats = useMemo(() => {
        const totalOffers = offers.length;
        const totalValue = offers.reduce((sum, offer) => sum + offer.grandTotal, 0);

        const statusCounts = offers.reduce((acc, offer) => {
            acc[offer.status] = (acc[offer.status] || 0) + 1;
            return acc;
        }, {} as Record<PriceOfferStatus, number>);

        const supplierCount = new Set(offers.map(offer => offer.supplierId)).size;
        const averageValue = totalOffers > 0 ? totalValue / totalOffers : 0;

        return {
            totalOffers,
            totalValue,
            statusCounts,
            supplierCount,
            averageValue
        };
    }, [offers]);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div className="bg-gradient-to-r aseel-bg-panel aseel-bg-panel rounded-xl p-5 text-white">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm opacity-90">إجمالي العروض</p>
                        <p className="text-2xl font-bold mt-1">{stats.totalOffers}</p>
                    </div>
                    <FileText className="w-10 h-10 opacity-80" />
                </div>
            </div>

            <div className="bg-gradient-to-r from-green-500 to-green-600 rounded-xl p-5 text-white">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm opacity-90">القيمة الإجمالية</p>
                        <p className="text-2xl font-bold mt-1">${stats.totalValue.toLocaleString()}</p>
                    </div>
                    <DollarSign className="w-10 h-10 opacity-80" />
                </div>
            </div>

            <div className="bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary)] rounded-xl p-5 text-white">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm opacity-90">عدد الموردين</p>
                        <p className="text-2xl font-bold mt-1">{stats.supplierCount}</p>
                    </div>
                    <User className="w-10 h-10 opacity-80" />
                </div>
            </div>

            <div className="bg-gradient-to-r aseel-bg-panel aseel-bg-panel rounded-xl p-5 text-white">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm opacity-90">متوسط قيمة العرض</p>
                        <p className="text-2xl font-bold mt-1">${stats.averageValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                    </div>
                    <BarChart3 className="w-10 h-10 opacity-80" />
                </div>
            </div>
        </div>
    );
};
