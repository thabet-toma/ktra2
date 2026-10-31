import React from 'react';

/**
 * ISSUE #271 — عناصر عرضٍ صغيرة للموديول، محليّةٌ على الوضع الداكن.
 *
 * **لا استيراد من `components/accountant/office/`**: تلك طبقةُ المكتب القديمة
 * وستُحذف في #291. المشتركُ العامّ يُستعمل من `components/ui`، وما لا يوجد فيه
 * يُكتب هنا صغيراً — بنفس اصطلاح الشاشات العامة المجاورة (`components/employee-ops/`):
 * `bg-white dark:bg-slate-900` · `border-slate-200 dark:border-slate-700`
 * · `text-slate-900 dark:text-slate-100`.
 */

const CARD = 'rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900';

export const OfficeCard: React.FC<{
  title?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}> = ({ title, actions, children, className = '' }) => (
  <section className={`${CARD} p-4 md:p-5 ${className}`}>
    {(title || actions) && (
      <div className="mb-3 flex items-center justify-between gap-2">
        {title ? (
          <h2 className="text-[13.5px] font-bold text-slate-900 dark:text-slate-100">{title}</h2>
        ) : <span />}
        {actions}
      </div>
    )}
    {children}
  </section>
);

export const OfficeSkeleton: React.FC<{ rows?: number }> = ({ rows = 4 }) => (
  <div aria-label="جاري التحميل" className="space-y-3">
    {Array.from({ length: rows }, (_, index) => (
      <div
        key={index}
        className="h-12 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"
      />
    ))}
  </div>
);

export const OfficeError: React.FC<{ message: string; onRetry?: () => void }> = ({
  message,
  onRetry,
}) => (
  <div
    role="alert"
    className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-center text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200"
  >
    <p className="text-[12.5px] font-bold">{message}</p>
    {onRetry ? (
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-lg bg-rose-700 px-4 py-1.5 text-[12px] font-semibold text-white hover:bg-rose-800"
      >
        أعد المحاولة
      </button>
    ) : null}
  </div>
);

export const OfficeEmpty: React.FC<{ title: string; hint?: string }> = ({ title, hint }) => (
  <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
    <p className="text-[13px] font-bold text-slate-700 dark:text-slate-200">{title}</p>
    {hint ? (
      <p className="mt-1 text-[11.5px] text-slate-500 dark:text-slate-400">{hint}</p>
    ) : null}
  </div>
);

/** حقلُ إدخالٍ موحّد الشكل — الوضع الداكنُ فيه مقصودٌ صراحةً. */
export const officeInputClass =
  'h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px] text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100';

export const officePrimaryButtonClass =
  'rounded-lg bg-teal-700 px-3 py-2 text-[12px] font-semibold text-white hover:bg-teal-800 disabled:opacity-50';

export const officeSecondaryButtonClass =
  'rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12px] font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700';
