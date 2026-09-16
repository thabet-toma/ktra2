import React, { useCallback, useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, Info, RefreshCw, Search } from "lucide-react";

import { listBillingRecords, type SubscriptionBillingRecordRow } from "../../services/platformOpsApi";
import { filterBillingRecords, sumDecimalAmounts } from "../../utils/billingRecords";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import {
  CcCard,
  CcEmpty,
  CcSectionTitle,
  CcStatTile,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "./ui";
import { SubscriptionPolicyPanel } from "./SubscriptionPolicyPanel";
import { SubscriptionsPanel } from "./SubscriptionsPanel";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لعرض سجلات فوترة الخدمة.", "تعذّر تحميل سجلات الفوترة.");

export const BillingRecordsScreen: React.FC = () => {
  const [records, setRecords] = useState<SubscriptionBillingRecordRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listBillingRecords();
      setRecords(data);
    } catch (err: unknown) {
      setError(displayError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  const filteredRecords = useMemo(() => {
    return filterBillingRecords(records, searchQuery);
  }, [records, searchQuery]);

  // حساب المجاميع بدقة بالسنتات عبر دالة sumDecimalAmounts الخالصة
  const totals = useMemo(() => {
    const totalMonthlyFee = sumDecimalAmounts(filteredRecords.map((r) => r.monthly_fee));
    const totalOverageFee = sumDecimalAmounts(filteredRecords.map((r) => r.overage_fee));
    const grandTotal = sumDecimalAmounts(filteredRecords.map((r) => r.total_amount));

    let totalIncluded = 0;
    let totalConsumed = 0;
    for (const r of filteredRecords) {
      totalIncluded += r.included_quota || 0;
      totalConsumed += r.consumed_quota || 0;
    }

    return {
      monthlyFee: totalMonthlyFee,
      overageFee: totalOverageFee,
      grandTotal,
      included: totalIncluded,
      consumed: totalConsumed,
    };
  }, [filteredRecords]);

  return (
    <div
      className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 text-right"
      dir="rtl"
    >
      <div className="max-w-7xl mx-auto space-y-6">
        {/* الترويسة الرئيسية */}
        <header className="flex flex-wrap items-center justify-between gap-4 pb-6 border-b border-cc-border">
          <div className="flex flex-col">
            <div className="flex items-center gap-2.5">
              <h1 className="text-xl sm:text-2xl font-black text-cc-text tracking-tight flex items-center gap-2">
                <FileSpreadsheet className="w-6 h-6 text-emerald-400" />
                إدارة خدمة المتابعة وفواتيرها
              </h1>
            </div>
            <p className="text-xs text-cc-text-muted mt-1">
              نظرة عامة على الاشتراكات وسياسة إعداداتها، وسجل تدقيق الفوترة الشهرية.
              التفعيل والتعليق والإلغاء يتمّان من بطاقة كل شركة.
            </p>
          </div>
        </header>

        <SubscriptionPolicyPanel />
        <SubscriptionsPanel />

        {/* سجل الفوترة */}
        <section className="space-y-4">
          <CcSectionTitle
            title="سجل الفوترة"
            badge={filteredRecords.length}
          />

          {/* تنبيه تعليمي إلزامي حسب المواصفة §5 */}
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-4 text-xs text-sky-200 flex items-start gap-3">
            <Info className="w-4 h-4 mt-0.5 text-sky-400 shrink-0" />
            <div className="space-y-1">
              <p className="font-semibold">
                الفواتيرُ تُصدَر بأمر الإدارة الشهريّ <code className="font-mono bg-sky-950/60 border border-sky-500/30 px-1.5 py-0.5 rounded text-[11px] text-sky-300">bill_service_subscriptions</code>.
              </p>
              <p className="text-sky-300/80 text-[11px]">
                هذه الشاشة نافذة تدقيق وقراءة على ما فُوتر فعلاً في شركة المنصة ولا تُنشئ فواتير جديدة بصورة كسولة عند فتحها.
              </p>
            </div>
          </div>

          {/* مجاميع totals الخمسة المحسوبة أصلاً */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <CcCard className="p-4">
              <CcStatTile
                label="الإجمالي"
                value={formatNumber(totals.grandTotal)}
                tone="accent"
                icon={<FileSpreadsheet className="w-4 h-4 text-sky-400" />}
              />
            </CcCard>
            <CcCard className="p-4">
              <CcStatTile
                label="الرسم الشهري"
                value={formatNumber(totals.monthlyFee)}
                tone="neutral"
                icon={<FileSpreadsheet className="w-4 h-4 text-cc-text-muted" />}
              />
            </CcCard>
            <CcCard className="p-4">
              <CcStatTile
                label="التجاوز"
                value={formatNumber(totals.overageFee)}
                tone={Number(totals.overageFee) > 0 ? "warning" : "neutral"}
                icon={<FileSpreadsheet className="w-4 h-4 text-amber-400" />}
              />
            </CcCard>
            <CcCard className="p-4">
              <CcStatTile
                label="المستهلك"
                value={totals.consumed}
                tone="neutral"
              />
            </CcCard>
            <CcCard className="p-4 sm:col-span-2 lg:col-span-1">
              <CcStatTile
                label="المشمول"
                value={totals.included}
                tone="neutral"
              />
            </CcCard>
          </div>

          {/* شريط البحث والتحديث */}
          <CcCard className="p-3">
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="w-3.5 h-3.5 text-cc-text-muted absolute right-3 top-2.5" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="ابحث باسم الشركة أو رقم الفاتورة..."
                  className="w-full rounded-lg border border-cc-border bg-cc-surface-2 pr-8 pl-3 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div className="flex items-center gap-2 justify-end">
                <span className="text-xs text-cc-text-muted">
                  {formatNumber(filteredRecords.length)} من {formatNumber(records.length)} سجل
                </span>
                <button
                  type="button"
                  onClick={() => void loadRecords()}
                  disabled={loading}
                  className="p-1.5 text-cc-text-muted hover:text-cc-text bg-cc-surface-2 hover:bg-cc-surface border border-cc-border rounded-lg transition"
                  title="تحديث السجلات"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                </button>
              </div>
            </div>
          </CcCard>

          {error && (
            <div className="rounded-xl bg-rose-500/10 p-3 text-xs font-semibold text-rose-300 border border-rose-500/30 flex items-center justify-between">
              <span>{error}</span>
              <button type="button" onClick={() => void loadRecords()} className="mr-2 underline text-rose-200 hover:text-rose-100">
                إعادة المحاولة
              </button>
            </div>
          )}

          {/* جدول سجلات الفوترة */}
          <CcTable>
            <CcThead>
              <tr>
                <CcTh>الشركة</CcTh>
                <CcTh>الدورة</CcTh>
                <CcTh>رقم الفاتورة</CcTh>
                <CcTh>الرسم الشهري</CcTh>
                <CcTh className="text-center">المشمول / المستهلك</CcTh>
                <CcTh>الزائد × سعره = التجاوز</CcTh>
                <CcTh>الإجمالي</CcTh>
              </tr>
            </CcThead>
            <tbody>
              {filteredRecords.length === 0 ? (
                <tr>
                  <CcTd colSpan={7} className="p-8 text-center">
                    <CcEmpty
                      title={loading ? "جاري تحميل سجلات الفوترة..." : "لا توجد سجلات فوترة تطابق البحث."}
                    />
                  </CcTd>
                </tr>
              ) : (
                filteredRecords.map((record) => {
                  const hasOverage = record.overage_units > 0;
                  return (
                    <CcTr key={record.id}>
                      <CcTd className="font-semibold text-cc-text">
                        {record.company_name}
                      </CcTd>
                      <CcTd className="text-cc-text-muted whitespace-nowrap">
                        {formatDateValue(record.period_start)} — {formatDateValue(record.period_end)}
                      </CcTd>
                      <CcTd className="font-mono text-cc-text">
                        {record.invoice_number ? (
                          <span className="bg-cc-surface-2 border border-cc-border px-2 py-0.5 rounded font-bold">
                            {record.invoice_number}
                          </span>
                        ) : (
                          <span className="text-cc-text-muted">—</span>
                        )}
                      </CcTd>
                      <CcTd className="font-mono">
                        {formatNumber(record.monthly_fee)}
                      </CcTd>
                      <CcTd className="text-center font-mono">
                        <span className="font-semibold text-cc-text">
                          {formatNumber(record.consumed_quota)}
                        </span>{" "}
                        / <span className="text-cc-text-muted">{formatNumber(record.included_quota)}</span>
                      </CcTd>
                      <CcTd className="font-mono text-[11px]">
                        {hasOverage ? (
                          <span className="text-amber-400 font-semibold">
                            {formatNumber(record.overage_units)} × {formatNumber(record.overage_unit_price)} = {formatNumber(record.overage_fee)}
                          </span>
                        ) : (
                          <span className="text-cc-text-muted">—</span>
                        )}
                      </CcTd>
                      <CcTd className="font-mono font-bold text-cc-text">
                        {formatNumber(record.total_amount)}
                      </CcTd>
                    </CcTr>
                  );
                })
              )}
            </tbody>
            {filteredRecords.length > 0 && (
              <tfoot className="border-t-2 border-cc-border bg-cc-surface-2 font-bold text-cc-text">
                <tr>
                  <td colSpan={3} className="p-3 text-right">
                    المجموع ({formatNumber(filteredRecords.length)} سجل)
                  </td>
                  <td className="p-3 font-mono text-emerald-400">
                    {formatNumber(totals.monthlyFee)}
                  </td>
                  <td className="p-3 text-center font-mono">
                    {formatNumber(totals.consumed)} / {formatNumber(totals.included)}
                  </td>
                  <td className="p-3 font-mono text-amber-400">
                    {formatNumber(totals.overageFee)}
                  </td>
                  <td className="p-3 font-mono text-sky-400 font-extrabold">
                    {formatNumber(totals.grandTotal)}
                  </td>
                </tr>
              </tfoot>
            )}
          </CcTable>
        </section>
      </div>
    </div>
  );
};
