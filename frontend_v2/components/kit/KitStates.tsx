import React from 'react';

export interface KitEmptyStateProps {
  hint?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}

export const KitEmptyState: React.FC<KitEmptyStateProps> = ({
  hint = 'لا توجد بيانات',
  icon,
  action,
}) => (
  <div className="flex flex-col items-center justify-center py-12 ktra-text-soft">
    {icon && <div className="mb-3 opacity-40">{icon}</div>}
    <p className="text-sm">{hint}</p>
    {action && <div className="mt-3">{action}</div>}
  </div>
);

export interface KitSpinnerProps {
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const KitSpinner: React.FC<KitSpinnerProps> = ({
  label = 'جاري التحميل…',
  size = 'md',
}) => {
  const sizeClass = size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-6 h-6' : 'w-4 h-4';
  return (
    <div className="flex items-center justify-center gap-2 ktra-text-soft py-8">
      <svg className={`animate-spin ${sizeClass}`} viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <span className="text-sm">{label}</span>
    </div>
  );
};

export interface KitErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export const KitErrorState: React.FC<KitErrorStateProps> = ({ message, onRetry }) => (
  <div className="flex flex-col items-center justify-center py-8" style={{ color: 'var(--ktra-state)' }}>
    <p className="text-sm">{message}</p>
    {onRetry && (
      <button onClick={onRetry} className="ktra-btn-primary px-4 py-1.5 mt-3 text-xs">
        إعادة المحاولة
      </button>
    )}
  </div>
);
