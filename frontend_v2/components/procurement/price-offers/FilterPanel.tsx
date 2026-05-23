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
        { value: 'all', label: 'جميع العروض', icon: List, color: 'aseel-text-soft dark:aseel-text-soft' },
        { value: 'initial', label: 'العروض الأولية', icon: Clock, color: 'aseel-text-soft dark:aseel-text-soft' },
        { value: 'pending_info', label: 'بانتظار المعلومات', icon: AlertCircle, color: 'aseel-text-soft dark:aseel-text-soft' },
        { value: 'under_discussion', label: 'تحت المناقشة', icon: MessageSquare, color: 'aseel-text-soft dark:aseel-text-soft' },
        { value: 'approved_for_shipping', label: 'معتمد للشراء', icon: CheckSquare, color: 'text-green-500 dark:text-green-400' },
    ];

    const getCount = (status: PriceOfferStatus | 'all') => {
        if (status === 'all') return offers.length;
        return offers.filter(offer => offer.status === status).length;
    };

    return (
        <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl border aseel-border-soft dark:aseel-border-soft p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Filter className="w-5 h-5 aseel-text-soft" />
                    <h3 className="font-bold aseel-text-ink dark:text-white">تصفية العروض</h3>
                </div>
                <div className="text-sm aseel-text-soft dark:aseel-text-soft">
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
                                ? 'aseel-bg-accent dark:aseel-bg-accent-bg text-white shadow-md'
                                : 'aseel-bg-panel dark:aseel-bg-panel aseel-text-ink dark:aseel-text-soft hover:aseel-bg-grid-head dark:hover:aseel-bg-panel'
                                }`}
                        >
                            <Icon className={`w-4 h-4 ${isActive ? 'text-white' : option.color}`} />
                            <span className="font-medium">{option.label}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${isActive
                                ? 'aseel-bg-field/20'
                                : 'aseel-bg-grid-head dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft'
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
