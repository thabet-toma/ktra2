import React from 'react';

export const AccountantPage: React.FC<{
  title: string;
  description: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, description, actions, children }) => (
  <section dir="rtl" className="mx-auto max-w-6xl space-y-6">
    <header className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center sm:justify-between dark:border-slate-700 dark:bg-slate-900">
      <div>
        <p className="mb-1 text-sm font-bold text-blue-600">بوابة المحاسب القانوني</p>
        <h1 className="text-2xl font-black text-slate-900 dark:text-white">{title}</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{description}</p>
      </div>
      {actions}
    </header>
    {children}
  </section>
);

export const AccountantSkeleton: React.FC<{ rows?: number }> = ({ rows = 4 }) => (
  <div aria-label="جاري التحميل" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
    {Array.from({ length: rows }, (_, index) => (
      <div key={index} className="h-12 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
    ))}
  </div>
);

export const AccountantError: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
  <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center text-red-800">
    <p>{message}</p>
    <button type="button" onClick={onRetry} className="mt-4 rounded-xl bg-red-700 px-5 py-2 font-bold text-white hover:bg-red-800">إعادة المحاولة</button>
  </div>
);

