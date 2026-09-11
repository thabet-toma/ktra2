import React, { useCallback, useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, Info, RefreshCw, Search } from "lucide-react";

import { listBillingRecords, type SubscriptionBillingRecordRow } from "../../services/platformOpsApi";
import { filterBillingRecords, sumDecimalAmounts } from "../../utils/billingRecords";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
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
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-8 text-right" dir="rtl">
      {/* الترويسة الرئيسية */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
            إدارة خدمة المتابعة وفواتيرها
          </h1>
          <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mt-1">
            نظرة عامة على الاشتراكات وسياسة إعداداتها، وسجل تدقيق الفوترة الشهرية.
            التفعيل والتعليق والإلغاء يتمّان من بطاقة كل شركة.
          </p>
        </div>
      </div>

      <SubscriptionPolicyPanel />
      <SubscriptionsPanel />

      {/* سجل الفوترة */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">سجل الفوترة</h2>
        </div>

        {/* تنبيه تعليمي إلزامي حسب المواصفة §5 */}
        <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/70 dark:bg-blue-950/30 p-4 text-xs text-blue-900 dark:text-blue-200 flex items-start gap-3">
          <Info className="w-4 h-4 mt-0.5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">
              الفواتيرُ تُصدَر بأمر الإدارة الشهريّ <code className="font-mono bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded text-[11px]">bill_service_subscriptions</code>.
            </p>
            <p className="text-blue-700 dark:text-blue-300 text-[11px]">
              هذه الشاشة نافذة تدقيق وقراءة على ما فُوتر فعلاً في شركة المنصة ولا تُنشئ فواتير جديدة بصورة كسولة عند فتحها.
            </p>
          </div>
        </div>

        {/* شريط البحث والتحديث */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white dark:bg-slate-900 p-3 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <div className="relative flex-1 max-w-md">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute right-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="ابحث باسم الشركة أو رقم الفاتورة..."
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 pr-8 pl-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2 justify-end">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {formatNumber(filteredRecords.length)} من {formatNumber(records.length)} سجل
            </span>
            <button
              type="button"
              onClick={() => void loadRecords()}
              disabled={loading}
              className="p-1.5 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              title="تحديث السجلات"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-rose-50 dark:bg-rose-950/40 p-3 text-xs font-semibold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
              {error}
              <button type="button" onClick={() => void loadRecords()} className="mr-2 underline">
                إعادة المحاولة
              </button>
          </div>
        )}

        {/* جدول سجلات الفوترة */}
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="p-3">الشركة</th>
                <th className="p-3">الدورة</th>
                <th className="p-3">رقم الفاتورة</th>
                <th className="p-3">الرسم الشهري</th>
                <th className="p-3 text-center">المشمول / المستهلك</th>
                <th className="p-3">الزائد × سعره = التجاوز</th>
                <th className="p-3">الإجمالي</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-slate-800 dark:text-slate-200">
              {filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-slate-400 dark:text-slate-500">
                    {loading ? "جاري تحميل سجلات الفوترة..." : "لا توجد سجلات فوترة تطابق البحث."}
                  </td>
                </tr>
              ) : (
                filteredRecords.map((record) => {
                  const hasOverage = record.overage_units > 0;
                  return (
                    <tr key={record.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition">
                      <td className="p-3 font-semibold text-slate-900 dark:text-slate-100">
                        {record.company_name}
                      </td>
                      <td className="p-3 text-slate-600 dark:text-slate-400 whitespace-nowrap">
                        {formatDateValue(record.period_start)} — {formatDateValue(record.period_end)}
                      </td>
                      <td className="p-3 font-mono text-slate-700 dark:text-slate-300">
                        {record.invoice_number ? (
                          <span className="bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded font-bold">
                            {record.invoice_number}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="p-3 font-mono">
                        {formatNumber(record.monthly_fee)}
                      </td>
                      <td className="p-3 text-center font-mono">
                        <span className="font-semibold text-slate-900 dark:text-slate-100">
                          {formatNumber(record.consumed_quota)}
                        </span>{" "}
                        / <span className="text-slate-500">{formatNumber(record.included_quota)}</span>
                      </td>
                      <td className="p-3 font-mono text-[11px]">
                        {hasOverage ? (
                          <span className="text-amber-700 dark:text-amber-300 font-semibold">
                            {formatNumber(record.overage_units)} × {formatNumber(record.overage_unit_price)} = {formatNumber(record.overage_fee)}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="p-3 font-mono font-bold text-slate-900 dark:text-slate-100">
                        {formatNumber(record.total_amount)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
            {filteredRecords.length > 0 && (
              <tfoot className="bg-slate-50 dark:bg-slate-800/80 font-bold border-t-2 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100">
                <tr>
                  <td colSpan={3} className="p-3 text-right">
                    المجموع ({formatNumber(filteredRecords.length)} سجل)
                  </td>
                  <td className="p-3 font-mono text-emerald-700 dark:text-emerald-300">
                    {formatNumber(totals.monthlyFee)}
                  </td>
                  <td className="p-3 text-center font-mono">
                    {formatNumber(totals.consumed)} / {formatNumber(totals.included)}
                  </td>
                  <td className="p-3 font-mono text-amber-700 dark:text-amber-300">
                    {formatNumber(totals.overageFee)}
                  </td>
                  <td className="p-3 font-mono text-blue-700 dark:text-blue-300 font-extrabold">
                    {formatNumber(totals.grandTotal)}
                  </td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </section>
    </div>
  );
};
