import React from 'react';

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
