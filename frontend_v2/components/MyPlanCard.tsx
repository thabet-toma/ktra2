import React from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, Infinity as InfinityIcon, Lock, TrendingUp } from 'lucide-react';

import { useCompany } from '../contexts/CompanyContext';
import { usePublicPricing } from '../hooks/usePublicPricing.ts';
import { useMyPlanUsage } from '../hooks/useMyPlanUsage.ts';
import { formatNumber } from '../utils/formatNumber.ts';
import { formatDateValue } from '../utils/formatDate.ts';
import { buildPlanUsageBar, formatPlanLimitValue } from '../utils/planPricingDisplay.ts';
import { barWidthClass } from '../utils/barWidth.ts';
import type { MyPlanLimitUsage } from '../services/pricingApi.ts';

/**
 * 211-O — «خطّتي»: خطّة الشركة الحاليّة، وحدودها **الفعّالة** مع استهلاكها،
 * وزرّ ترقية حقيقيّ إلى `/pricing`.
 *
 * **الحدودُ من `/api/my-plan/usage/` لا من حمولة الأسعار العامّة.** تلك تعرف
 * `PLAN_DEFAULTS` وحدَها ولا تعرف الشركةَ أصلاً، فشركةٌ رُفع لها حدٌّ
 * بـ`TenantLimit` كانت ترى رقمَ الخطّة لا رقمَها — ثمّ تُمنَع عند رقمٍ غيرِ
 * الذي قرأته، أو تُمنَح فوقه. والسعرُ وحدَه يبقى من الحمولة العامّة لأنّه سعرُ
 * الخطّة لا سعرُ الشركة.
 */

const TONE_BAR: Record<string, string> = {
  ok: 'bg-emerald-500',
  warning: 'bg-amber-500',
  over: 'bg-red-500',
};

const TONE_TEXT: Record<string, string> = {
  ok: 'text-slate-600 dark:text-slate-300',
  warning: 'text-amber-700 dark:text-amber-300',
  over: 'text-red-700 dark:text-red-300',
};

const UsageRow: React.FC<{ row: MyPlanLimitUsage }> = ({ row }) => {
  const bar = buildPlanUsageBar(row.usage, row.limit);
  const usageText = formatNumber(row.usage, { maxDecimals: 0, group: true });

  return (
    <li className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
          {row.label}
          <span className="ms-1 text-xs font-medium text-slate-500 dark:text-slate-400">{row.period_label}</span>
        </span>

        {bar.unbounded ? (
          <span className="flex items-center gap-1 text-xs font-bold text-slate-600 dark:text-slate-300">
            <InfinityIcon className="h-4 w-4" aria-hidden="true" />
            {usageText} {row.unit} · بلا حدّ
          </span>
        ) : bar.unavailable ? (
          <span className="flex items-center gap-1 text-xs font-bold text-slate-500 dark:text-slate-400">
            <Lock className="h-3.5 w-3.5" aria-hidden="true" />
            {formatPlanLimitValue(0)}
          </span>
        ) : (
          // الرقمُ الكاملُ لا النسبةُ وحدَها: «٩٠٪» لا تقول كم بقي، و«١٨٠ من ٢٠٠» تقول.
          <span className={`text-xs font-extrabold ${TONE_TEXT[bar.tone]}`}>
            {usageText} / {formatPlanLimitValue(row.limit)} {row.unit}
          </span>
        )}
      </div>

      {!bar.unbounded && !bar.unavailable && (
        <>
          <div
            className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/10"
            role="progressbar"
            aria-valuenow={Math.round(bar.rawPercent)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${row.label}: ${row.usage} من ${row.limit}`}
          >
            <div className={`h-full rounded-full ${TONE_BAR[bar.tone]} ${barWidthClass(bar.percent)}`} />
          </div>
          <p className={`mt-1 text-xs font-semibold ${TONE_TEXT[bar.tone]}`}>
            {bar.tone === 'over'
              ? 'بلغتَ الحدّ — الإنشاء الجديد سيُمنَع حتى ترقية الخطّة.'
              : `يتبقّى ${formatNumber(bar.remaining ?? 0, { maxDecimals: 0, group: true })} ${row.unit}`}
          </p>
        </>
      )}
    </li>
  );
};

export const MyPlanCard: React.FC = () => {
  const { currentCompany } = useCompany();
  const { data: pricing, loading: pricingLoading, error: pricingError } = usePublicPricing();
  const { data: usage, loading: usageLoading, error: usageError } = useMyPlanUsage(
    currentCompany?.TenantID ?? null,
  );

  if (!currentCompany) return null;

  const isTrial = currentCompany.SubscriptionPlan === 'Trial';
  const planRow = !isTrial ? pricing?.plans.find((p) => p.key === currentCompany.SubscriptionPlan) : undefined;
  const daysLeft = currentCompany.subscription_days_left;
  const endsAt = currentCompany.subscription_ends_at;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-slate-900/60">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-extrabold text-blue-600 dark:text-blue-400">خطّة الاشتراك</p>
          <h3 className="mt-1 text-xl font-black text-slate-950 dark:text-white">
            {isTrial ? 'الخطّة التجريبيّة' : planRow?.label ?? usage?.plan_label ?? currentCompany.SubscriptionPlan}
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

      {/* الاستهلاكُ أوّلاً — هو سببُ فتح هذا القسم. والتجريبيّةُ لها حدودٌ
          تُفرَض أيضاً (`PLAN_DEFAULTS["Trial"]`)، فالشريطُ يظهر لها كما لغيرها. */}
      {usageLoading && <p className="mt-5 text-sm text-slate-500 dark:text-slate-400">جاري تحميل استهلاك خطّتك...</p>}
      {!usageLoading && usageError && (
        <p role="alert" className="mt-5 text-sm text-red-700 dark:text-red-300">{usageError}</p>
      )}

      {!usageLoading && !usageError && usage && (
        <ul className="mt-5 grid gap-2 sm:grid-cols-2">
          {usage.limits.map((row) => <UsageRow key={row.key} row={row} />)}
        </ul>
      )}

      {/* سقوطٌ إلى حدود الخطّة المعلنة حين يتعذّر الاستهلاك: حدٌّ بلا استهلاكٍ
          أنفعُ من فراغ، وأصدقُ من صفرٍ يُقرأ «لم تستهلك شيئاً». */}
      {!usageLoading && usageError && !pricingLoading && !pricingError && planRow && (
        <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
          {planRow.limits.map((limit) => (
            <li key={limit.key} className="text-sm text-slate-700 dark:text-slate-300">
              {limit.label}: <strong className="font-extrabold">{formatPlanLimitValue(limit.value)}</strong>
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
