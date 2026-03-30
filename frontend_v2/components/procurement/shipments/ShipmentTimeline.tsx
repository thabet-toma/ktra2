import React from 'react';
import { SHIPPING_TERMS, getShippingPath, getShippingTermIndex } from '../../../constants/shipping';
import { Check, ChevronRight } from 'lucide-react';

interface ShipmentTimelineProps {
    fromTerm: string;
    toTerm: string;
}

export const ShipmentTimeline: React.FC<ShipmentTimelineProps> = ({ fromTerm, toTerm }) => {
    const path = getShippingPath(fromTerm, toTerm);
    const fromIndex = getShippingTermIndex(fromTerm);
    const toIndex = getShippingTermIndex(toTerm);

    if (path.length === 0) return null;

    return (
        <div className="w-full py-8 overflow-x-auto">
            <div className="flex items-center min-w-max px-4">
                {path.map((item, index) => {
                    const isFirst = index === 0;
                    const isLast = index === path.length - 1;

                    return (
                        <React.Fragment key={item.code}>
                            {/* Step Circle & Label */}
                            <div className="flex flex-col items-center relative group">
                                <div
                                    className={`
                                        w-12 h-12 rounded-full flex items-center justify-center border-4 transition-all duration-500
                                        ${isFirst ? 'bg-blue-600 border-blue-200 dark:border-blue-900 text-white scale-110 shadow-lg shadow-blue-200 dark:shadow-blue-900/20' :
                                            isLast ? 'bg-emerald-500 border-emerald-100 dark:border-emerald-900 text-white scale-110 shadow-lg shadow-emerald-200 dark:shadow-emerald-900/20' :
                                                'bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700 text-gray-400 group-hover:border-blue-300 dark:group-hover:border-blue-800'}
                                    `}
                                >
                                    {isFirst ? <span className="text-xs font-bold">START</span> :
                                        isLast ? <Check className="w-6 h-6" /> :
                                            <span className="text-xs font-medium">{index + 1}</span>}
                                </div>

                                <div className="mt-3 text-center">
                                    <span className={`block text-sm font-bold tracking-wider ${isFirst || isLast ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
                                        {item.code}
                                    </span>
                                    <span className="block text-[10px] text-gray-400 dark:text-gray-500 max-w-[80px] leading-tight mt-1">
                                        {item.name}
                                    </span>
                                </div>

                                {/* Animated Tooltip-like background for active ends */}
                                {(isFirst || isLast) && (
                                    <div className={`absolute -top-2 w-1 h-1 rounded-full ${isFirst ? 'bg-blue-400' : 'bg-emerald-400'} animate-ping`} />
                                )}
                            </div>

                            {/* Connector Line */}
                            {!isLast && (
                                <div className="flex-1 min-w-[60px] flex items-center px-2 -mt-10">
                                    <div className="relative w-full h-1 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                        <div
                                            className="absolute top-0 left-0 h-full bg-gradient-to-r from-blue-500 to-emerald-500 transition-all duration-1000"
                                            style={{ width: '100%' }}
                                        />
                                    </div>
                                    <ChevronRight className="w-4 h-4 text-emerald-500 -ml-1" />
                                </div>
                            )}
                        </React.Fragment>
                    );
                })}
            </div>
        </div>
    );
};
