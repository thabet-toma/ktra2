import React from 'react';
import { PriceOfferStatus } from '../../../types';
import { Clock, AlertCircle, MessageSquare, CheckSquare } from 'lucide-react';

export const StatusBadge: React.FC<{ status: PriceOfferStatus }> = ({ status }) => {
    const statusConfig = {
        initial: {
            label: "أولية",
            icon: Clock,
            bg: "ktra-bg-panel dark:ktra-bg-panel",
            text: "ktra-text-ink dark:ktra-text-soft",
            border: "ktra-border-soft dark:ktra-border-soft",
            iconColor: "ktra-text-soft dark:ktra-text-soft"
        },
        pending_info: {
            label: "بانتظار المعلومات",
            icon: AlertCircle,
            bg: "ktra-bg-panel dark:ktra-bg-panel/30",
            text: "ktra-text-ink dark:ktra-text-soft",
            border: "ktra-border-soft dark:ktra-border-soft",
            iconColor: "ktra-text-soft dark:ktra-text-soft"
        },
        under_discussion: {
            label: "تحت المناقشة",
            icon: MessageSquare,
            bg: "ktra-bg-accent-bg dark:ktra-bg-panel/30",
            text: "ktra-text-ink dark:ktra-text-soft",
            border: "ktra-border-accent dark:ktra-border-soft",
            iconColor: "ktra-text-soft dark:ktra-text-soft"
        },
        approved_for_shipping: {
            label: "معتمدة للشراء ",
            icon: CheckSquare,
            bg: "bg-green-100 dark:bg-green-900/30",
            text: "text-green-800 dark:text-green-300",
            border: "ktra-border-soft dark:border-green-800",
            iconColor: "text-green-500 dark:text-green-400"
        }
    };

    const config = statusConfig[status];
    const Icon = config.icon;

    return (
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full ${config.bg} ${config.text} border ${config.border} text-sm font-medium`}>
            <Icon className={`w-3.5 h-3.5 ${config.iconColor}`} />
            <span>{config.label}</span>
        </div>
    );
};
