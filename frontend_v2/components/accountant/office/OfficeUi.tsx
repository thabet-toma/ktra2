import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * عناصر واجهة مكتب المحاسبة القانونية — هويّة بصرية **مستقلة تماماً** عن النظام
 * التجاري: لوحة داكنة، بطاقات هادئة، أرقام لاتينية مضبوطة. لا تستعمل متغيّرات
 * الثيم التجاري (`--color-*`) كي لا تشبهه.
 */
export const OfficeCard: React.FC<{
  title?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}> = ({ title, actions, children, className = '' }) => (
  <section className={`rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
    {(title || actions) && (
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
        {title && <h2 className="text-base font-black text-slate-900 dark:text-white">{title}</h2>}
        {actions}
      </header>
    )}
    <div className="p-5">{children}</div>
  </section>
);

export const OfficeStat: React.FC<{
  label: string;
  value: string;
  hint?: string;
  tone?: 'neutral' | 'positive' | 'negative' | 'accent';
}> = ({ label, value, hint, tone = 'neutral' }) => {
  const tones: Record<string, string> = {
    neutral: 'text-slate-900 dark:text-white',
    positive: 'text-emerald-700 dark:text-emerald-300',
    negative: 'text-red-700 dark:text-red-300',
    accent: 'text-indigo-700 dark:text-indigo-300',
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-sm font-bold text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-2 text-2xl font-black ${tones[tone]}`} style={{ direction: 'ltr' }}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
};

/** وسم صغير — نوع الزبون، حالة برنامج، منتج موعد. */
export const OfficeBadge: React.FC<{ tone: string; children: React.ReactNode }> = ({ tone, children }) => (
  <span className={`inline-block rounded-lg px-2 py-1 text-xs font-bold ${tone}`}>{children}</span>
);

const CONTROL_CLASS =
  'w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm dark:border-slate-700 dark:bg-slate-950';

/**
 * حقل نموذج المكتب: التسمية مربوطة بالعنصر عبر `useId` — كل حقل هنا يُنطق باسمه
 * لقارئ الشاشة بلا `aria-label` مكرّر على كل استدعاء.
 */
export const OfficeField: React.FC<{
  label: string;
  hint?: string;
  required?: boolean;
  className?: string;
  children: (id: string) => React.ReactNode;
}> = ({ label, hint, required, className = '', children }) => {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-xs font-bold text-slate-600 dark:text-slate-300">
        {label} {required && <span className="text-red-600">*</span>}
      </label>
      {children(id)}
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
};

export const OfficeInput: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input {...props} className={`${CONTROL_CLASS} ${props.className || ''}`} />
);

export const OfficeSelect: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = (props) => (
  <select {...props} className={`${CONTROL_CLASS} ${props.className || ''}`} />
);

export const OfficeTextarea: React.FC<React.TextareaHTMLAttributes<HTMLTextAreaElement>> = (props) => (
  <textarea {...props} className={`${CONTROL_CLASS} ${props.className || ''}`} />
);

/**
 * حوار المكتب — الخروج منه مضمون دائماً: Escape، أو النقر خارجه، أو زر الإغلاق.
 * أي نموذج هنا حالةٌ لها طريق عودة، لا شاشة يعلق فيها المحاسب.
 */
export const OfficeModal: React.FC<{
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}> = ({ title, onClose, children, footer, wide = false }) => {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    panel.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/60 p-4 sm:p-8"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        dir="rtl"
        className={`w-full rounded-2xl bg-white shadow-2xl outline-none dark:bg-slate-900 ${wide ? 'max-w-3xl' : 'max-w-xl'}`}
      >
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <h2 id={titleId} className="text-base font-black text-slate-900 dark:text-white">{title}</h2>
          <button type="button" onClick={onClose} aria-label="إغلاق" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-5">{children}</div>
        {footer && (
          <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-4 dark:border-slate-800">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
};

export const OfficeSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div aria-label="جاري التحميل" className="space-y-3">
    {Array.from({ length: rows }, (_, index) => (
      <div key={index} className="h-12 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
    ))}
  </div>
);

export const OfficeEmpty: React.FC<{ title: string; hint?: string }> = ({ title, hint }) => (
  <div className="rounded-2xl border border-dashed border-slate-300 p-10 text-center dark:border-slate-700">
    <p className="font-bold text-slate-700 dark:text-slate-200">{title}</p>
    {hint && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{hint}</p>}
  </div>
);

export const OfficeError: React.FC<{ message: string; onRetry?: () => void }> = ({ message, onRetry }) => (
  <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center text-red-800">
    <p className="font-bold">{message}</p>
    {onRetry && (
      <button type="button" onClick={onRetry} className="mt-4 rounded-xl bg-red-700 px-5 py-2 font-bold text-white hover:bg-red-800">
        إعادة المحاولة
      </button>
    )}
  </div>
);

/** جدول المكتب — رأس ثابت، أرقام LTR، وتمرير أفقي داخل حدوده لا في الصفحة. */
export const OfficeTable: React.FC<{
  columns: { key: string; header: string; numeric?: boolean }[];
  rows: Record<string, React.ReactNode>[];
  footer?: Record<string, React.ReactNode>;
  emptyHint?: string;
}> = ({ columns, rows, footer, emptyHint }) => {
  if (rows.length === 0) return <OfficeEmpty title="لا سجلات في هذه الفترة" hint={emptyHint} />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-right text-sm">
        <thead className="bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="whitespace-nowrap px-4 py-3 font-bold">{column.header}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((row, index) => (
            <tr key={String(row.__key ?? index)} className="hover:bg-slate-50 dark:hover:bg-slate-800/60">
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`whitespace-nowrap px-4 py-3 ${column.numeric ? 'font-mono' : ''}`}
                  style={column.numeric ? { direction: 'ltr', textAlign: 'left' } : undefined}
                >
                  {row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot className="bg-slate-50 font-black dark:bg-slate-800">
            <tr>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-4 py-3 ${column.numeric ? 'font-mono' : ''}`}
                  style={column.numeric ? { direction: 'ltr', textAlign: 'left' } : undefined}
                >
                  {footer[column.key] ?? ''}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
};
