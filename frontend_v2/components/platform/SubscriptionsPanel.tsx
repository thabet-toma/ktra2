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
import { type CcTone } from "../../utils/ccTone";
import { CcEmpty, CcPill, CcSectionTitle, CcTable, CcTd, CcTh, CcThead, CcTr } from "./ui";

const STATUS_FILTERS = Object.keys(SUBSCRIPTION_STATUS_LABEL) as ServiceSubscriptionStatus[];

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لعرض اشتراكات الخدمة.", "تعذّر تحميل الاشتراكات.");

const subscriptionStatusTone = (status: ServiceSubscriptionStatus): CcTone => {
  switch (status) {
    case "active":
      return "success";
    case "trial":
      return "accent";
    case "suspended":
      return "warning";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
};

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
      <CcSectionTitle
        title="اشتراكات الخدمة"
        subtitle="نظرة عامة للقراءة على كل اشتراكات الخدمة — التعديل والانتقالات تتم من بطاقة الشركة نفسها."
        badge={rows.length}
        action={
          <div className="flex items-center gap-2">
            <select
              className="ktra-input h-9 text-xs"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as ServiceSubscriptionStatus | "")}
              aria-label="تصفية حسب الحالة"
            >
              <option value="">كل الحالات</option>
              {STATUS_FILTERS.map((value) => (
                <option key={value} value={value}>{SUBSCRIPTION_STATUS_LABEL[value]}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void load(statusFilter)}
              className="ktra-iconbtn"
              title="تحديث"
              aria-label="تحديث"
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        }
      />

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-300 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => void load(statusFilter)} className="mr-2 underline text-rose-200 hover:text-rose-100">إعادة المحاولة</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-cc-text-muted">
          <Loader2 className="h-5 w-5 animate-spin text-sky-400" />
          <span>جارٍ التحميل…</span>
        </div>
      ) : (
        <CcTable>
          <CcThead>
            <tr>
              <CcTh>الشركة</CcTh>
              <CcTh>الحالة</CcTh>
              <CcTh>الباقة</CcTh>
              <CcTh>الحصة</CcTh>
              <CcTh>عميل الفوترة</CcTh>
              <CcTh>تنبيه</CcTh>
            </tr>
          </CcThead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <CcTd colSpan={6} className="p-8 text-center">
                  <CcEmpty title="لا اشتراكات مطابقة." />
                </CcTd>
              </tr>
            ) : (
              rows.map((row) => (
                <CcTr key={row.id}>
                  <CcTd className="font-semibold text-cc-text">{row.company_name}</CcTd>
                  <CcTd>
                    <CcPill tone={subscriptionStatusTone(row.status)} dot>
                      {row.status_display}
                    </CcPill>
                  </CcTd>
                  <CcTd className="text-cc-text">{row.plan}</CcTd>
                  <CcTd className="font-mono text-cc-text">
                    {formatNumber(row.consumed_quota)} / {formatNumber(row.included_quota)}
                  </CcTd>
                  <CcTd className="text-cc-text-muted">{row.billing_customer_name ?? "—"}</CcTd>
                  <CcTd className="text-amber-400 text-xs">
                    {row.status === "trial" && formatTrialRemainingLabel(row.trial_ends_at)}
                    {row.status === "trial" && row.scheduled_cancellation_date && " · "}
                    {row.scheduled_cancellation_date && `آخر يوم خدمة ${formatDateValue(row.scheduled_cancellation_date)}`}
                  </CcTd>
                </CcTr>
              ))
            )}
          </tbody>
        </CcTable>
      )}
    </section>
  );
};
