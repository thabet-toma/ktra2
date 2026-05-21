import React from 'react';
import { FileX, Loader2 } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'لا توجد بيانات',
  description = 'لم يتم العثور على سجلات',
  icon,
  action,
}) => (
  <div className="flex flex-col items-center justify-center py-16 text-center" data-skin="aseel">
    <div className="text-[var(--color-text-muted)] mb-4">
      {icon || <FileX className="w-12 h-12 mx-auto" />}
    </div>
    <h3 className="text-lg font-semibold text-[var(--color-text)] mb-1">{title}</h3>
    {description && <p className="text-sm text-[var(--color-text-muted)] mb-4">{description}</p>}
    {action}
  </div>
);

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md', label = 'جاري التحميل...' }) => {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  return (
    <div className="flex items-center justify-center py-8" data-skin="aseel">
      <Loader2 className={`${sizeClasses[size]} animate-spin text-[var(--color-primary)]`} />
      {label && <span className="mr-2 text-sm text-[var(--color-text-muted)]">{label}</span>}
    </div>
  );
};

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  message = 'حدث خطأ أثناء تحميل البيانات',
  onRetry,
}) => (
  <div className="flex flex-col items-center justify-center py-16 text-center" data-skin="aseel">
    <div className="text-[var(--color-danger)] mb-4">
      <FileX className="w-12 h-12 mx-auto" />
    </div>
    <h3 className="text-lg font-semibold text-[var(--color-text)] mb-1">خطأ</h3>
    <p className="text-sm text-[var(--color-text-muted)] mb-4">{message}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm hover:opacity-90"
      >
        إعادة المحاولة
      </button>
    )}
  </div>
);
