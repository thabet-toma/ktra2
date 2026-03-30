import React from 'react';
import { PriceOfferStatus } from '../../../types';
import { Clock, AlertCircle, MessageSquare, CheckSquare } from 'lucide-react';

export const StatusBadge: React.FC<{ status: PriceOfferStatus }> = ({ status }) => {
    const statusConfig = {
        initial: {
            label: "أولية",
            icon: Clock,
            bg: "bg-gray-100 dark:bg-gray-700",
            text: "text-gray-800 dark:text-gray-300",
            border: "border-gray-200 dark:border-gray-600",
            iconColor: "text-gray-500 dark:text-gray-400"
        },
        pending_info: {
            label: "بانتظار المعلومات",
            icon: AlertCircle,
            bg: "bg-yellow-100 dark:bg-yellow-900/30",
            text: "text-yellow-800 dark:text-yellow-300",
            border: "border-yellow-200 dark:border-yellow-800",
            iconColor: "text-yellow-500 dark:text-yellow-400"
        },
        under_discussion: {
            label: "تحت المناقشة",
            icon: MessageSquare,
            bg: "bg-blue-100 dark:bg-blue-900/30",
            text: "text-blue-800 dark:text-blue-300",
            border: "border-blue-200 dark:border-blue-800",
            iconColor: "text-blue-500 dark:text-blue-400"
        },
        approved_for_shipping: {
            label: "معتمدة للشراء ",
            icon: CheckSquare,
            bg: "bg-green-100 dark:bg-green-900/30",
            text: "text-green-800 dark:text-green-300",
            border: "border-green-200 dark:border-green-800",
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
