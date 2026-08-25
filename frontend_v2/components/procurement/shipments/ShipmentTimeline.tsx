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
                                        ${isFirst ? 'ktra-bg-accent ktra-border-accent dark:ktra-border-soft text-white scale-110 shadow-lg shadow-blue-200 dark:shadow-blue-900/20' :
                                            isLast ? 'ktra-bg-panel ktra-border-soft dark:ktra-border-soft text-white scale-110 shadow-lg shadow-emerald-200 dark:shadow-emerald-900/20' :
                                                'ktra-bg-field dark:ktra-bg-panel ktra-border-soft dark:ktra-border-soft ktra-text-soft group-hover:ktra-border-soft dark:group-hover:ktra-border-soft'}
                                    `}
                                >
                                    {isFirst ? <span className="text-xs font-bold">START</span> :
                                        isLast ? <Check className="w-6 h-6" /> :
                                            <span className="text-xs font-medium">{index + 1}</span>}
                                </div>

                                <div className="mt-3 text-center">
                                    <span className={`block text-sm font-bold tracking-wider ${isFirst || isLast ? 'ktra-text-ink dark:text-white' : 'ktra-text-soft dark:ktra-text-soft'}`}>
                                        {item.code}
                                    </span>
                                    <span className="block text-[10px] ktra-text-soft dark:ktra-text-soft max-w-[80px] leading-tight mt-1">
                                        {item.name}
                                    </span>
                                </div>

                                {/* Animated Tooltip-like background for active ends */}
                                {(isFirst || isLast) && (
                                    <div className={`absolute -top-2 w-1 h-1 rounded-full ${isFirst ? 'ktra-bg-panel' : 'ktra-bg-panel'} animate-ping`} />
                                )}
                            </div>

                            {/* Connector Line */}
                            {!isLast && (
                                <div className="flex-1 min-w-[60px] flex items-center px-2 -mt-10">
                                    <div className="relative w-full h-1 ktra-bg-panel dark:ktra-bg-panel rounded-full overflow-hidden">
                                        <div
                                            className="absolute top-0 left-0 h-full bg-gradient-to-r ktra-bg-panel ktra-bg-panel transition-all duration-1000"
                                            style={{ width: '100%' }}
                                        />
                                    </div>
                                    <ChevronRight className="w-4 h-4 ktra-text-soft -ml-1" />
                                </div>
                            )}
                        </React.Fragment>
                    );
                })}
            </div>
        </div>
    );
};
