
import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
    title: string;
    value: string | number;
    icon: LucideIcon;
    trend?: {
        value: number;
        isPositive: boolean;
    };
    color: 'blue' | 'green' | 'purple' | 'orange' | 'red' | 'indigo';
    description?: string;
}

const colorStyles = {
    blue: { bg: 'bg-blue-50 dark:bg-blue-900/20', text: 'text-blue-600 dark:text-blue-400', border: 'border-blue-100 dark:border-blue-800' },
    green: { bg: 'bg-green-50 dark:bg-green-900/20', text: 'text-green-600 dark:text-green-400', border: 'border-green-100 dark:border-green-800' },
    purple: { bg: 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20', text: 'text-[var(--color-primary)] dark:text-[var(--color-primary)]', border: 'border-[var(--color-border)] dark:border-[var(--color-border)]' },
    orange: { bg: 'bg-orange-50 dark:bg-orange-900/20', text: 'text-orange-600 dark:text-orange-400', border: 'border-orange-100 dark:border-orange-800' },
    red: { bg: 'bg-red-50 dark:bg-red-900/20', text: 'text-red-600 dark:text-red-400', border: 'border-red-100 dark:border-red-800' },
    indigo: { bg: 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20', text: 'text-[var(--color-primary)] dark:text-[var(--color-primary)]', border: 'border-[var(--color-border)] dark:border-[var(--color-border)]' },
};

export const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, trend, color, description }) => {
    const styles = colorStyles[color];

    return (
        <div className={`relative overflow-hidden rounded-2xl bg-[var(--color-surface)] p-6 shadow-sm hover:shadow-md transition-all duration-300 border ${styles.border}`}>
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm font-medium text-[var(--color-text-muted)] mb-1">{title}</p>
                    <div className="flex items-baseline gap-2">
                        <h3 className="text-2xl font-bold text-[var(--color-text)]">{value}</h3>
                        {trend && (
                            <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${trend.isPositive ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}>
                                {trend.isPositive ? '+' : ''}{trend.value}%
                            </span>
                        )}
                    </div>
                    {description && <p className="text-xs text-[var(--color-text-muted)] mt-2">{description}</p>}
                </div>
                <div className={`p-3 rounded-xl ${styles.bg}`}>
                    <Icon className={`w-6 h-6 ${styles.text}`} />
                </div>
            </div>

            {/* Decorative gradient overlay */}
            <div className={`absolute -right-6 -bottom-6 w-24 h-24 rounded-full opacity-5 ${styles.bg.replace('bg-', 'bg-gradient-to-br from-')}`} />
        </div>
    );
};
