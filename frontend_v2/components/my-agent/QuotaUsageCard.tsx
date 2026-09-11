import React, { useCallback, useEffect, useState } from "react";
import { Gauge, Info, RefreshCw } from "lucide-react";

import {
  getMyQuotaUsage,
  type QuotaUsage,
  type QuotaUsageResponse,
} from "../../services/myAgentApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  quotaBarPercent,
  quotaHeadline,
  quotaOverageNotice,
  quotaTone,
  quotaToneMeta,
} from "../../utils/quotaUsage";

/**
 * بطاقةُ استهلاك الباقة — القصّة ٦٢: «أريد أن أرى استهلاكي من الباقة واقترابي من
 * الحدّ، حتى لا تفاجئني الفاتورة» (#207 م٨).
 *
 * الأرقامُ من `/api/my-agent/quota/` الذي يحسبها **بدالّة الفوترة نفسِها**
 * (`calculate_subscription_billing`)، فما يراه صاحبُ الشركة هنا هو ما سيُفوتَر لا
 * تقديرٌ موازٍ. وفشلُ تحميلها لا يُسقط الصفحة: بطاقةٌ مساعدةٌ لا عمودُ الشاشة.
 */
export const QuotaUsageCard: React.FC = () => {
  const [usage, setUsage] = useState<QuotaUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      setUsage(await getMyQuotaUsage());
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toneMeta = usage && usage.has_subscription ? quotaToneMeta(quotaTone(usage.usage_percent)) : null;

  return (
    <section
      aria-labelledby="quota-usage-title"
      className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm space-y-4"
    >
      <div className="flex items-center justify-between gap-3">
        <h2
          id="quota-usage-title"
          className="text-base font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2"
        >
          <Gauge className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          استهلاك الباقة
        </h2>
        {toneMeta && <span className={`text-xs font-bold ${toneMeta.textClass}`}>{toneMeta.label}</span>}
      </div>

      {loading ? (
        <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin" />
          جاري حساب الاستهلاك...
        </p>
      ) : failed ? (
        <div className="flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-400">
          <span>تعذّر تحميل استهلاك الباقة.</span>
          <button
            type="button"
            onClick={() => void load()}
            className="font-semibold text-blue-700 dark:text-blue-300 hover:underline"
          >
            إعادة المحاولة
          </button>
        </div>
      ) : !usage || !usage.has_subscription ? (
        <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
          <Info className="w-4 h-4 flex-shrink-0" />
          لا اشتراكَ خدمة متابعةٍ مفعَّلٌ لشركتك — فلا باقةَ ولا فاتورةَ خدمة.
        </p>
      ) : (
        <QuotaDetails usage={usage} />
      )}
    </section>
  );
};

const QuotaDetails: React.FC<{ usage: QuotaUsage }> = ({ usage }) => {
  const meta = quotaToneMeta(quotaTone(usage.usage_percent));
  const overage = quotaOverageNotice(usage.overage_units, usage.overage_fee);
  const percentText =
    usage.usage_percent == null ? "—" : `${formatNumber(usage.usage_percent, { maxDecimals: 0 })}%`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tabular-nums">
          {quotaHeadline(usage.consumed_quota, usage.included_quota)}
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          باقة {usage.plan} · {usage.status_display}
          {usage.period_start && usage.period_end && (
            <>
              {" "}· الدورة {formatDateValue(usage.period_start)} — {formatDateValue(usage.period_end)}
            </>
          )}
        </p>
      </div>

      <progress
        value={quotaBarPercent(usage.usage_percent)}
        max={100}
        aria-label={`نسبة استهلاك الباقة ${percentText}`}
        className={`block h-2.5 w-full appearance-none overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800 [&::-webkit-progress-bar]:bg-slate-200 dark:[&::-webkit-progress-bar]:bg-slate-800 ${meta.barClass}`}
      />

      <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <QuotaStat label="المتبقّي من الباقة" value={`${formatNumber(usage.remaining_quota)} عملية`} />
        <QuotaStat label="نسبة الاستهلاك" value={percentText} />
        <QuotaStat label="الرسم الشهري" value={formatNumber(usage.monthly_fee)} />
        <QuotaStat label="سعر العملية الزائدة" value={formatNumber(usage.overage_unit_price)} />
      </dl>

      {overage && (
        <p
          role="status"
          className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-xs text-rose-800 dark:text-rose-300"
        >
          {overage}
        </p>
      )}

      <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2.5">
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">
          الإجمالي المتوقّع لهذه الدورة
        </span>
        <span className="text-base font-extrabold text-slate-900 dark:text-slate-100 tabular-nums">
          {formatNumber(usage.projected_total)}
        </span>
      </div>

      <p className="text-[11px] text-slate-400 dark:text-slate-500">
        تُحتسب العمليّةُ عند قبول طلبٍ أو مستندٍ أرسلتَه، لا عند إدخال الوكيل — فحجمُ الفاتورة بيدك.
      </p>
    </div>
  );
};

const QuotaStat: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 p-3">
    <dt className="text-[11px] text-slate-500 dark:text-slate-400">{label}</dt>
    <dd className="mt-0.5 text-sm font-bold text-slate-900 dark:text-slate-100 tabular-nums">{value}</dd>
  </div>
);
