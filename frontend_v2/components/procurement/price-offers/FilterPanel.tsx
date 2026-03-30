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
        { value: 'all', label: 'جميع العروض', icon: List, color: 'text-gray-600 dark:text-gray-300' },
        { value: 'initial', label: 'العروض الأولية', icon: Clock, color: 'text-gray-500 dark:text-gray-400' },
        { value: 'pending_info', label: 'بانتظار المعلومات', icon: AlertCircle, color: 'text-yellow-500 dark:text-yellow-400' },
        { value: 'under_discussion', label: 'تحت المناقشة', icon: MessageSquare, color: 'text-blue-500 dark:text-blue-400' },
        { value: 'approved_for_shipping', label: 'معتمد للشراء', icon: CheckSquare, color: 'text-green-500 dark:text-green-400' },
    ];

    const getCount = (status: PriceOfferStatus | 'all') => {
        if (status === 'all') return offers.length;
        return offers.filter(offer => offer.status === status).length;
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Filter className="w-5 h-5 text-blue-500" />
                    <h3 className="font-bold text-gray-900 dark:text-white">تصفية العروض</h3>
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
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
                                ? 'bg-blue-600 dark:bg-blue-500 text-white shadow-md'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                }`}
                        >
                            <Icon className={`w-4 h-4 ${isActive ? 'text-white' : option.color}`} />
                            <span className="font-medium">{option.label}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${isActive
                                ? 'bg-white/20'
                                : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-400'
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
