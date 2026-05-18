import React, { useState, useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';
import { AppView } from '../../types';

interface GlobalSearchProps {
  userRole: string;
  onNavigate: (view: AppView) => void;
}

const QUICK_LINKS: { label: string; view: AppView }[] = [
  { label: 'الصفقات', view: 'deals-management' },
  { label: 'الشحنات', view: 'shipments-management' },
  { label: 'التخليص', view: 'customs-clearance' },
  { label: 'فواتير الشراء', view: 'purchase-invoices' },
  { label: 'فواتير المبيعات', view: 'sales-invoices' },
  { label: 'الشيكات', view: 'accounting-cheques' },
];

export const GlobalSearch: React.FC<GlobalSearchProps> = ({ userRole, onNavigate }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="p-2 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
        aria-label="بحث سريع"
      >
        <Search className="h-4 w-4" />
      </button>

      {open && (
        <div className="absolute top-full end-0 mt-1 w-64 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="p-2 border-b border-[var(--color-border)]">
            <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">روابط سريعة</span>
          </div>
          {QUICK_LINKS.map(link => (
            <button
              key={link.view}
              onClick={() => { onNavigate(link.view); setOpen(false); }}
              className="w-full text-start px-3 py-2 text-[var(--font-size-sm)] text-[var(--color-text)] hover:bg-[var(--color-muted)] transition-colors"
            >
              {link.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};