import React from 'react';
import { PriceOfferStatus } from '../../../types';
import { Clock, AlertCircle, MessageSquare, CheckSquare } from 'lucide-react';

export const StatusBadge: React.FC<{ status: PriceOfferStatus }> = ({ status }) => {
    const statusConfig = {
        initial: {
            label: "أولية",
            icon: Clock,
            bg: "aseel-bg-panel dark:aseel-bg-panel",
            text: "aseel-text-ink dark:aseel-text-soft",
            border: "aseel-border-soft dark:aseel-border-soft",
            iconColor: "aseel-text-soft dark:aseel-text-soft"
        },
        pending_info: {
            label: "بانتظار المعلومات",
            icon: AlertCircle,
            bg: "aseel-bg-panel dark:aseel-bg-panel/30",
            text: "aseel-text-ink dark:aseel-text-soft",
            border: "aseel-border-soft dark:aseel-border-soft",
            iconColor: "aseel-text-soft dark:aseel-text-soft"
        },
        under_discussion: {
            label: "تحت المناقشة",
            icon: MessageSquare,
            bg: "aseel-bg-accent-bg dark:aseel-bg-panel/30",
            text: "aseel-text-ink dark:aseel-text-soft",
            border: "aseel-border-accent dark:aseel-border-soft",
            iconColor: "aseel-text-soft dark:aseel-text-soft"
        },
        approved_for_shipping: {
            label: "معتمدة للشراء ",
            icon: CheckSquare,
            bg: "bg-green-100 dark:bg-green-900/30",
            text: "text-green-800 dark:text-green-300",
            border: "aseel-border-soft dark:border-green-800",
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
