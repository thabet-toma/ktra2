/**
 * D1-03: UI Primitives Layer — KTRA Design System
 * All components are token-driven + RTL.
 * Usage: import { Button, Input, DataGrid, Badge, ... } from '@/components/ui'
 */
import React, { forwardRef, useEffect, useRef, useState } from 'react';

// ── Token access helper ───────────────────────────────────────────
function t(varName: string, fallback: string = ''): string {
  if (typeof window === 'undefined') return fallback;
  return (
    getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim() || fallback
  );
}

// ── Button ────────────────────────────────────────────────────────
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, icon, children, disabled, className = '', ...rest }, ref) => {
    const base = 'inline-flex items-center justify-center gap-1 font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

    const variants: Record<ButtonVariant, string> = {
      primary: 'bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] focus-visible:ring-[var(--color-primary)]',
      secondary: 'bg-[var(--color-surface-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:bg-[var(--color-surface-3)] focus-visible:ring-[var(--color-border)]',
      ghost: 'text-[var(--color-text-muted)] hover:bg-[var(--color-muted)] hover:text-[var(--color-text)] focus-visible:ring-[var(--color-border)]',
      danger: 'bg-[var(--color-danger)] text-white hover:bg-[var(--color-danger-hover)] focus-visible:ring-[var(--color-danger)]',
    };

    const sizes: Record<ButtonSize, string> = {
      sm: 'h-7 px-2.5 text-[var(--font-size-xs)]',
      md: 'h-8 px-3 text-[var(--font-size-sm)]',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
        {...rest}
      >
        {loading ? <span className="spinner" /> : icon}
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';

// ── Input ────────────────────────────────────────────────────────
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, className = '', ...rest }, ref) => (
    <div className="flex flex-col gap-0.5">
      {label && (
        <label className="text-[var(--font-size-xs)] font-medium text-[var(--color-text-muted)]">
          {label}
        </label>
      )}
      <input
        ref={ref}
        className={`
          h-7 px-2 text-[var(--font-size-sm)] rounded-md bg-[var(--color-surface)] text-[var(--color-text)] border border-[var(--color-border)] transition-colors placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)] focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-[var(--color-danger)]' : ''}
          ${className}
        `}
        {...rest}
      />
      {error && <span className="text-[var(--font-size-xs)] text-[var(--color-danger)]">{error}</span>}
      {hint && !error && <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{hint}</span>}
    </div>
  )
);
Input.displayName = 'Input';

// ── Select ───────────────────────────────────────────────────────
interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string | number; label: string }[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className = '', ...rest }, ref) => (
    <div className="flex flex-col gap-0.5">
      {label && (
        <label className="text-[var(--font-size-xs)] font-medium text-[var(--color-text-muted)]">
          {label}
        </label>
      )}
      <select
        ref={ref}
        className={`
          h-7 px-2 text-[var(--font-size-sm)] rounded-md bg-[var(--color-surface)] text-[var(--color-text)] border border-[var(--color-border)] transition-colors focus:outline-none focus:border-[var(--color-primary)] focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-[var(--color-danger)]' : ''}
          ${className}
        `}
        {...rest}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error && <span className="text-[var(--font-size-xs)] text-[var(--color-danger)]">{error}</span>}
    </div>
  )
);
Select.displayName = 'Select';

// ── Badge / StatusBadge ──────────────────────────────────────────
type BadgeVariant = 'primary' | 'success' | 'danger' | 'warning' | 'muted' | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const badgeVariants: Record<BadgeVariant, string> = {
  primary: 'badge badge-primary',
  success: 'badge badge-success',
  danger: 'badge badge-danger',
  warning: 'badge badge-warning',
  muted: 'badge badge-muted',
  neutral: 'badge badge-neutral',
};

export const Badge: React.FC<BadgeProps> = ({ variant = 'neutral', children, className = '' }) => (
  <span className={`${badgeVariants[variant]} ${className}`}>{children}</span>
);

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, BadgeVariant> = {
    Open: 'primary', Shipped: 'warning', Cleared: 'success', Closed: 'muted',
    Cancelled: 'danger', Pending: 'warning', InTransit: 'primary',
    Delivered: 'success', draft: 'muted', sent: 'primary', accepted: 'success',
    converted: 'neutral', expired: 'warning', rejected: 'danger',
    posted: 'success', unpaid: 'danger', 'partially paid': 'warning',
    'fully paid': 'success',
  };
  const variant = map[status] ?? 'muted';
  const label = status.replace(/([A-Z])/g, ' $1').trim();
  return <Badge variant={variant}>{label}</Badge>;
}

// ── Spinner ─────────────────────────────────────────────────────
export const Spinner: React.FC<{ size?: 'sm' | 'md' }> = ({ size = 'md' }) => {
  const sizeClass = size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';
  return (
    <div className={`${sizeClass} spinner`} role="status" aria-label="loading" />
  );
};

// ── EmptyState ───────────────────────────────────────────────────
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ icon, title, description, action }) => (
  <div className="empty-state">
    {icon && <div className="empty-state-icon">{icon}</div>}
    <span className="text-[var(--font-size-sm)] font-medium">{title}</span>
    {description && <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{description}</span>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);

// ── Modal / Drawer ────────────────────────────────────────────────
interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

const modalSizes: Record<string, string> = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

export const Modal: React.FC<ModalProps> = ({ open, onClose, title, children, footer, size = 'md' }) => {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="ktra-overlay-mask z-50 flex items-center justify-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className={`bg-[var(--color-surface)] rounded-xl shadow-[var(--elev-5)] w-full ${modalSizes[size]} max-h-[90vh] flex flex-col`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
          <h2 id="modal-title" className="text-[var(--font-size-sm)] font-semibold">{title}</h2>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] text-lg leading-none">&times;</button>
        </div>
        <div className="overflow-y-auto flex-1 p-4">{children}</div>
        {footer && <div className="px-4 py-3 border-t border-[var(--color-border)] flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
};

// ── Drawer (side panel) ──────────────────────────────────────────
interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export const Drawer: React.FC<DrawerProps> = ({ open, onClose, title, children, footer }) => {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-y-0 end-0 z-60 flex" style={{ direction: 'ltr' }}>
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <div className="drawer-header" id="drawer-title">
          <span className="text-[var(--font-size-sm)] font-semibold">{title}</span>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] text-lg">&times;</button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="px-4 py-3 border-t border-[var(--color-border)] flex justify-end gap-2 sticky bottom-0 bg-[var(--color-surface-2)]">{footer}</div>}
      </div>
      <div className="flex-1 bg-black/50" onClick={onClose} />
    </div>
  );
};

// ── PageHeader ────────────────────────────────────────────────────
interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, description, actions }) => (
  <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
    <div className="flex flex-col">
      <h1 className="text-[var(--font-size-lg)] font-semibold text-[var(--color-text)]">{title}</h1>
      {description && <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{description}</span>}
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
);

// ── Toolbar (sticky search/filter bar) ──────────────────────────
interface ToolbarProps {
  search?: string;
  onSearch?: (v: string) => void;
  searchPlaceholder?: string;
  filters?: React.ReactNode;
  actions?: React.ReactNode;
}

export const Toolbar: React.FC<ToolbarProps> = ({
  search, onSearch, searchPlaceholder = 'بحث...',
  filters, actions,
}) => (
  <div className="sticky-toolbar flex flex-wrap items-center gap-2 px-4 py-2">
    {onSearch && (
      <div className="relative flex items-center">
        <input
          type="search"
          value={search ?? ''}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={searchPlaceholder}
          className="h-7 w-48 pl-7 pr-2 text-[var(--font-size-sm)] rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]"
        />
        <span className="absolute start-1.5 text-[var(--color-text-muted)]">🔍</span>
      </div>
    )}
    {filters && <div className="flex items-center gap-1">{filters}</div>}
    {actions && <div className="ms-auto flex items-center gap-1">{actions}</div>}
  </div>
);

// ── DataGrid (compact dense table) ───────────────────────────────
interface Column<T> {
  key: keyof T | string;
  header: string;
  sortable?: boolean;
  width?: string;
  render?: (row: T, idx: number) => React.ReactNode;
  align?: 'start' | 'center' | 'end';
}

interface DataGridProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField?: keyof T;
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T, idx: number) => string;
}

export function DataGrid<T>({
  columns, data, keyField = 'id' as keyof T,
  loading, emptyMessage = 'لا توجد بيانات',
  onRowClick, rowClassName,
}: DataGridProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const sorted = sortKey
    ? [...data].sort((a, b) => {
        const av = (a as Record<string, unknown>)[sortKey];
        const bv = (b as Record<string, unknown>)[sortKey];
        const cmp = String(av ?? '') < String(bv ?? '') ? -1 : 1;
        return sortDir === 'asc' ? cmp : -cmp;
      })
    : data;

  return (
    <div className="w-full overflow-x-auto">
      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                style={{ width: col.width, textAlign: col.align ?? 'start' }}
                className="cursor-pointer select-none"
                onClick={() => {
                  if (col.sortable) {
                    if (sortKey === col.key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
                    else { setSortKey(String(col.key)); setSortDir('asc'); }
                  }
                }}
              >
                {col.header}
                {col.sortable && sortKey === col.key && (sortDir === 'asc' ? ' ↑' : ' ↓')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={columns.length} className="text-center py-4"><Spinner /></td></tr>
          ) : sorted.length === 0 ? (
            <tr><td colSpan={columns.length} className="text-center py-6 text-[var(--color-text-muted)]">{emptyMessage}</td></tr>
          ) : sorted.map((row, idx) => {
            const key = String((row as Record<string, unknown>)[String(keyField)] ?? idx);
            const extra = rowClassName?.(row, idx) ?? '';
            return (
              <tr
                key={key}
                className={`${onRowClick ? 'cursor-pointer' : ''} ${extra}`}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td key={`${key}-${String(col.key)}`} style={{ textAlign: col.align ?? 'start' }}>
                    {col.render
                      ? col.render(row, idx)
                      : String((row as Record<string, unknown>)[String(col.key)] ?? '')}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Export all as named exports for tree-shaking ─────────────────
export { Field } from './Field';
// SAVE-1: خطأ الخادم بجانب حقله بدل سحقه في لافتة واحدة.
export { FieldError } from './FieldError';
// M5-T4: unified Aseel-skinned states. `EmptyState`/`Spinner` already exist in
// this barrel from D1-03 — to avoid name clashes, the Aseel variants are
// exposed via a namespace import: `import { AseelStates } from '@/components/ui'`.
// For new screens that want the cream theme, use these. Existing screens keep
// the legacy variants — no breakage.
export * as AseelStates from './EmptyState';