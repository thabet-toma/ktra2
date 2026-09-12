import React from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, Check, TrendingUp } from 'lucide-react';

import { useCompany } from '../contexts/CompanyContext';
import { usePublicPricing } from '../hooks/usePublicPricing.ts';
import { formatNumber } from '../utils/formatNumber.ts';
import { formatDateValue } from '../utils/formatDate.ts';
import { formatPlanLimitValue } from '../utils/planPricingDisplay.ts';

/**
 * 211-O — «خطّتي»: خطّة الشركة الحاليّة وحدودها وزرّ ترقية حقيقيّ إلى `/pricing`.
 *
 * **لا استهلاكَ معروضاً هنا**: نقطةُ استهلاك الحدود (`limit_rows`/`current_usage`
 * في `core/plans.py`) مكشوفةٌ للسوبر أدمن فقط (`core/platform_admin_api.py`)،
 * ولا نقطة مقابلة تقرأ استهلاك الشركة نفسِها لعضوٍ عاديّ فيها — فلا نخترع
 * نقطةً هنا؛ الحدودُ وحدَها معروضةٌ حتى تُضاف نقطةُ استهلاكٍ في تذكرةٍ لاحقة.
 */
export const MyPlanCard: React.FC = () => {
  const { currentCompany } = useCompany();
  const { data, loading, error } = usePublicPricing();

  if (!currentCompany) return null;

  const isTrial = currentCompany.SubscriptionPlan === 'Trial';
  const planRow = !isTrial ? data?.plans.find((p) => p.key === currentCompany.SubscriptionPlan) : undefined;
  const daysLeft = currentCompany.subscription_days_left;
  const endsAt = currentCompany.subscription_ends_at;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-slate-900/60">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-extrabold text-blue-600 dark:text-blue-400">خطّة الاشتراك</p>
          <h3 className="mt-1 text-xl font-black text-slate-950 dark:text-white">
            {isTrial ? 'الخطّة التجريبيّة' : planRow?.label ?? currentCompany.SubscriptionPlan}
          </h3>
        </div>

        {!isTrial && planRow && (
          <div className="flex items-end gap-1.5">
            <span className="text-2xl font-black text-slate-950 dark:text-white">{formatNumber(planRow.price)}</span>
            <span className="pb-0.5 text-sm font-bold text-slate-500 dark:text-slate-400">{planRow.currency_symbol} / شهرياً</span>
          </div>
        )}
      </div>

      {isTrial && (daysLeft !== null && daysLeft !== undefined) && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          <CalendarClock className="h-5 w-5 shrink-0" />
          <span>
            {daysLeft < 0
              ? `انتهت التجربة بتاريخ ${formatDateValue(endsAt)}.`
              : daysLeft === 0
                ? `اليوم آخر يوم في التجربة (${formatDateValue(endsAt)}).`
                : `يتبقّى ${formatNumber(daysLeft, { maxDecimals: 0 })} يوماً على انتهاء التجربة، بتاريخ ${formatDateValue(endsAt)}.`}
          </span>
        </div>
      )}

      {loading && <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">جاري تحميل حدود الخطّة...</p>}
      {!loading && error && <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-300">{error}</p>}

      {!loading && !error && planRow && (
        <ul className="mt-5 grid gap-2 sm:grid-cols-2">
          {planRow.limits.map((limit) => (
            <li key={limit.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <Check className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" strokeWidth={3} />
              <span>
                {limit.label}: <strong className="font-extrabold">{formatPlanLimitValue(limit.value)}</strong>
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* لا دفعَ ذاتيّاً في النظام — الزرّ يقود إلى صفحة الأسعار العامّة، لا إلى
          «ادفع الآن» بوعدٍ لا يقع. */}
      <Link
        to="/pricing"
        className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-extrabold text-white transition hover:bg-blue-700"
      >
        <TrendingUp className="h-4 w-4" />
        ترقية الخطّة
      </Link>
    </div>
  );
};

export default MyPlanCard;
