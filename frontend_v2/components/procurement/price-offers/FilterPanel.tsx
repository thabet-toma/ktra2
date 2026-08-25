import React from 'react';
import { PriceOffer, PriceOfferStatus } from '../../../types';
import { List, Clock, AlertCircle, MessageSquare, CheckSquare, Filter } from 'lucide-react';

interface FilterPanelProps {
    activeFilter: PriceOfferStatus | 'all';
    onFilterChange: (filter: PriceOfferStatus | 'all') => void;
    offers: PriceOffer[];
}

export const FilterPanel: React.FC<FilterPanelProps> = ({ activeFilter, onFilterChange, offers }) => {
    const filterOptions: Array<{ value: PriceOfferStatus | 'all', label: string, icon: any, color: string }> = [
        { value: 'all', label: 'جميع العروض', icon: List, color: 'ktra-text-soft dark:ktra-text-soft' },
        { value: 'initial', label: 'العروض الأولية', icon: Clock, color: 'ktra-text-soft dark:ktra-text-soft' },
        { value: 'pending_info', label: 'بانتظار المعلومات', icon: AlertCircle, color: 'ktra-text-soft dark:ktra-text-soft' },
        { value: 'under_discussion', label: 'تحت المناقشة', icon: MessageSquare, color: 'ktra-text-soft dark:ktra-text-soft' },
        { value: 'approved_for_shipping', label: 'معتمد للشراء', icon: CheckSquare, color: 'text-green-500 dark:text-green-400' },
    ];

    const getCount = (status: PriceOfferStatus | 'all') => {
        if (status === 'all') return offers.length;
        return offers.filter(offer => offer.status === status).length;
    };

    return (
        <div className="ktra-bg-field dark:ktra-bg-panel rounded-xl border ktra-border-soft dark:ktra-border-soft p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Filter className="w-5 h-5 ktra-text-soft" />
                    <h3 className="font-bold ktra-text-ink dark:text-white">تصفية العروض</h3>
                </div>
                <div className="text-sm ktra-text-soft dark:ktra-text-soft">
                    {activeFilter === 'all' ? 'عرض جميع العروض' : `عرض ${filterOptions.find(f => f.value === activeFilter)?.label}`}
                </div>
            </div>

            <div className="flex flex-wrap gap-2">
                {filterOptions.map((option) => {
                    const count = getCount(option.value);
                    const isActive = activeFilter === option.value;
                    const Icon = option.icon;

                    return (
                        <button
                            key={option.value}
                            onClick={() => onFilterChange(option.value)}
                            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg transition-all duration-200 ${isActive
                                ? 'ktra-bg-accent dark:ktra-bg-accent-bg text-white shadow-md'
                                : 'ktra-bg-panel dark:ktra-bg-panel ktra-text-ink dark:ktra-text-soft hover:ktra-bg-grid-head dark:hover:ktra-bg-panel'
                                }`}
                        >
                            <Icon className={`w-4 h-4 ${isActive ? 'text-white' : option.color}`} />
                            <span className="font-medium">{option.label}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${isActive
                                ? 'ktra-bg-field/20'
                                : 'ktra-bg-grid-head dark:ktra-bg-panel ktra-text-soft dark:ktra-text-soft'
                                }`}>
                                {count}
                            </span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};
