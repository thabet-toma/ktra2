import React, { useState } from 'react';
import { ChevronDown, ChevronUp, LucideIcon, Info } from 'lucide-react';

interface CollapsibleSectionProps {
    title: string;
    icon?: LucideIcon;
    defaultOpen?: boolean;
    children: React.ReactNode;
    className?: string;
    description?: string;
    compact?: boolean;
    badge?: string;
    badgeColor?: 'blue' | 'green' | 'red' | 'yellow' | 'purple' | 'gray';
    onToggle?: (isOpen: boolean) => void;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
    title,
    icon: Icon,
    defaultOpen = true,
    children,
    className = "",
    description,
    compact = false,
    badge,
    badgeColor = 'blue',
    onToggle
}) => {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    const handleToggle = () => {
        const newState = !isOpen;
        setIsOpen(newState);
        onToggle?.(newState);
    };

    const badgeColors = {
        blue: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800/50',
        green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800/50',
        red: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-800/50',
        yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800/50',
        purple: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200 dark:border-purple-800/50',
        gray: 'bg-[var(--color-surface-3)] text-[var(--color-text)] border-[var(--color-border)]'
    };

    return (
        <div className={`${compact ? 'rounded-lg' : 'rounded-xl'} bg-[var(--color-surface)] shadow-sm border border-[var(--color-border)] overflow-hidden transition-all duration-200 ${className}`}>
            <button
                onClick={handleToggle}
                className={`w-full flex items-center justify-between ${compact ? 'p-3' : 'p-4'} ${isOpen
                    ? 'bg-gray-50/80 dark:bg-gray-800/80 border-b border-[var(--color-border)]'
                    : 'bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]'
                    } transition-colors`}
            >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    {Icon && (
                        <div className={`${compact ? 'p-1.5' : 'p-2'} rounded-lg flex-shrink-0 ${isOpen
                                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                                : 'bg-[var(--color-surface-3)] text-[var(--color-text-muted)]'
                            }`}>
                            <Icon className={compact ? "w-4 h-4" : "w-5 h-5"} />
                        </div>
                    )}

                    <div className={`flex-1 min-w-0 ${compact ? 'text-right pr-2' : 'text-right pr-3'}`}>
                        <div className="flex items-center justify-between gap-2">
                            <h3 className={`font-semibold truncate ${compact ? 'text-sm' : 'text-base'} text-[var(--color-text)]`}>
                                {title}
                            </h3>

                            {badge && (
                                <span className={`flex-shrink-0 px-2 py-0.5 rounded-full text-xs border ${badgeColors[badgeColor]}`}>
                                    {badge}
                                </span>
                            )}
                        </div>

                        {description && (
                            <p className={`truncate ${compact ? 'text-xs mt-0.5' : 'text-sm mt-1'} text-[var(--color-text-muted)] font-normal`}>
                                {description}
                            </p>
                        )}
                    </div>
                </div>

                <div className={`flex-shrink-0 ${compact ? 'p-1' : 'p-1.5'} rounded-full transition-colors ${isOpen ? 'bg-[var(--color-surface-3)]' : 'bg-[var(--color-surface-3)]'
                    }`}>
                    {isOpen ? (
                        <ChevronUp className={`${compact ? 'w-4 h-4' : 'w-5 h-5'} text-[var(--color-text-muted)]`} />
                    ) : (
                        <ChevronDown className={`${compact ? 'w-4 h-4' : 'w-5 h-5'} text-[var(--color-text-muted)]`} />
                    )}
                </div>
            </button>

            <div
                className={`transition-all duration-200 ease-in-out ${isOpen
                        ? compact
                            ? 'max-h-[2000px] opacity-100 py-3'
                            : 'max-h-[5000px] opacity-100 py-4'
                        : 'max-h-0 opacity-0'
                    } overflow-hidden`}
            >
                <div className={compact ? 'px-3' : 'px-4'}>
                    {children}
                </div>
            </div>
        </div>
    );
};