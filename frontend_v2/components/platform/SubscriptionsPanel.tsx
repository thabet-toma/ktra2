import React, { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";

import {
  listServiceSubscriptions,
  type ServiceSubscriptionRow,
  type ServiceSubscriptionStatus,
} from "../../services/platformOpsApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  SUBSCRIPTION_STATUS_LABEL,
  describePlatformOpsError,
  formatTrialRemainingLabel,
} from "../../utils/platformSubscriptionManagement";

const STATUS_FILTERS = Object.keys(SUBSCRIPTION_STATUS_LABEL) as ServiceSubscriptionStatus[];

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لعرض اشتراكات الخدمة.", "تعذّر تحميل الاشتراكات.");

/**
 * نظرة عامة للقراءة على كل اشتراكات الخدمة — التعديل والانتقالات تتم من
 * بطاقة الشركة نفسها (`ServiceSubscriptionSection`) لا من هنا.
 */
export const SubscriptionsPanel: React.FC = () => {
  const [rows, setRows] = useState<ServiceSubscriptionRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<ServiceSubscriptionStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (status: ServiceSubscriptionStatus | "") => {
    setLoading(true);
    setError(null);
    try {
      setRows(await listServiceSubscriptions(status ? { status } : {}));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(statusFilter); }, [load, statusFilter]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">اشتراكات الخدمة</h2>
        <div className="flex items-center gap-2">
          <select
            className="ktra-input h-9"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ServiceSubscriptionStatus | "")}
            aria-label="تصفية حسب الحالة"
          >
            <option value="">كل الحالات</option>
            {STATUS_FILTERS.map((value) => (
              <option key={value} value={value}>{SUBSCRIPTION_STATUS_LABEL[value]}</option>
            ))}
          </select>
          <button type="button" onClick={() => void load(statusFilter)} className="ktra-iconbtn" title="تحديث" aria-label="تحديث">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700
          dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
          {error}
          <button type="button" onClick={() => void load(statusFilter)} className="mr-2 underline">إعادة المحاولة</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <table className="w-full text-right text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 font-semibold dark:border-slate-800 dark:bg-slate-800/60">
              <tr>
                <th className="p-3">الشركة</th>
                <th className="p-3">الحالة</th>
                <th className="p-3">الباقة</th>
                <th className="p-3">الحصة</th>
                <th className="p-3">عميل الفوترة</th>
                <th className="p-3">تنبيه</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {rows.length === 0 ? (
                <tr><td colSpan={6} className="p-8 text-center text-slate-400">لا اشتراكات مطابقة.</td></tr>
              ) : rows.map((row) => (
                <tr key={row.id}>
                  <td className="p-3 font-semibold">{row.company_name}</td>
                  <td className="p-3">{row.status_display}</td>
                  <td className="p-3">{row.plan}</td>
                  <td className="p-3">{formatNumber(row.consumed_quota)} / {formatNumber(row.included_quota)}</td>
                  <td className="p-3">{row.billing_customer_name ?? "—"}</td>
                  <td className="p-3 text-amber-700 dark:text-amber-300">
                    {row.status === "trial" && formatTrialRemainingLabel(row.trial_ends_at)}
                    {row.status === "trial" && row.scheduled_cancellation_date && " · "}
                    {row.scheduled_cancellation_date && `آخر يوم خدمة ${formatDateValue(row.scheduled_cancellation_date)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
