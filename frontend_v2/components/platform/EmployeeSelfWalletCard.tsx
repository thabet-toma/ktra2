import React, { useCallback, useEffect, useState } from "react";
import { Wallet } from "lucide-react";

import {
  getEmployeePilotPerformance,
  getEmployeeWallet,
  WALLET_LINE_STATUS_LABEL,
  type AcquisitionCommissionLineRow,
  type EmployeePilotPerformance,
  type EmployeeSalaryLineRow,
  type EmployeeWalletSummary,
  type WalletLineStatus,
} from "../../services/platformPilotApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { PilotAxesTable } from "./PilotAxesTable";
import {
  listMyPerformanceReviewRequests,
  openPerformanceReviewRequest,
  type PerformanceReviewRequestRow,
} from "../../services/platformEmployeeSpaceApi";
import { useToast } from "../../contexts/ToastContext";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لاستعراض هذه المحفظة.", "تعذّر تحميل البيانات.");

const now = new Date();

type WalletLine = EmployeeSalaryLineRow | AcquisitionCommissionLineRow;
const isCommissionLine = (line: WalletLine): line is AcquisitionCommissionLineRow => "acquisition" in line;

/**
 * ألوانُ حالات سطر المحفظة. **`reversed` ليس مؤكَّداً**: كان يقع في فرع «غير معلَّق»
 * فيُرسَم بأخضر المؤكَّد، فيقرأ الموظّفُ سطراً عُكس مالاً مستحقّاً له.
 */
const WALLET_STATUS_TONE: Partial<Record<WalletLineStatus, string>> = {
  pending: "bg-amber-100 text-amber-700",
  eligible: "bg-sky-100 text-sky-700",
  reversed: "bg-rose-100 text-rose-700 line-through",
};

/**
 * قراءةٌ ذاتيّةٌ للموظّف لمحفظته وتفصيل محاور تقييمه — **بلا أفعالٍ إداريّة**
 * (لا نقل حالة ولا عكس ولا تسوية؛ تلك لمدير العمليات في `EmployeeWalletPanel`).
 * القصص ٤١-٤٧: «كيف يُحسب تقييمي؟» والمحفظة الشهرية وحالاتها.
 */
export const EmployeeSelfWalletCard: React.FC<{ employeeId: number }> = ({ employeeId }) => {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [wallet, setWallet] = useState<EmployeeWalletSummary | null>(null);
  const [performance, setPerformance] = useState<EmployeePilotPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const [reviews, setReviews] = useState<PerformanceReviewRequestRow[]>([]);
  const [reviewReason, setReviewReason] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [walletData, perfData] = await Promise.all([
        getEmployeeWallet(employeeId, year, month),
        getEmployeePilotPerformance(employeeId, year, month),
      ]);
      setWallet(walletData);
      setPerformance(perfData);
      // اعتراضاتي — فشلُها لا يُسقط المحفظةَ ولا التقييم؛ قائمةٌ فارغةٌ أهونُ من شاشةٍ ساقطة.
      setReviews(await listMyPerformanceReviewRequests().catch(() => []));
    } catch (cause) {
      setError(displayError(cause));
      setWallet(null);
      setPerformance(null);
    } finally {
      setLoading(false);
    }
  }, [employeeId, year, month]);

  useEffect(() => { void load(); }, [load]);

  const lines: WalletLine[] = [...(wallet?.salary_lines ?? []), ...(wallet?.commission_lines ?? [])];

  const periodReviews = reviews.filter((r) => r.period_year === year && r.period_month === month);
  const openReview = periodReviews.find((r) => r.status === "open") ?? null;
  const resolvedReviews = periodReviews.filter((r) => r.status !== "open");

  const submitReview = async () => {
    setSubmittingReview(true);
    try {
      const created = await openPerformanceReviewRequest({
        period_year: year, period_month: month, reason: reviewReason.trim(),
      });
      setReviews((prev) => [created, ...prev]);
      setReviewReason("");
      toast("أُرسل طلبُ المراجعة.", "success");
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setSubmittingReview(false);
    }
  };

  return (
    <section className="space-y-4" dir="rtl">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-bold text-slate-800 ml-auto">محفظتي وتقييمي</h2>
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">السنة</span>
          <input
            type="number"
            className="w-24 px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">الشهر</span>
          <input
            type="number"
            min={1}
            max={12}
            className="w-20 px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
            value={month}
            onChange={(event) => setMonth(Number(event.target.value))}
          />
        </label>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="px-3 py-1 bg-rose-100 hover:bg-rose-200 rounded-lg font-bold text-[11px]">
            إعادة المحاولة
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
      ) : (
        <>
          {wallet && (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2">
                  <Wallet className="h-5 w-5 text-emerald-600" />
                  <div>
                    <p className="text-xs text-slate-500">مؤكَّد</p>
                    <p className="text-lg font-bold text-emerald-700">{formatNumber(wallet.totals.confirmed)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Wallet className="h-5 w-5 text-amber-600" />
                  <div>
                    <p className="text-xs text-slate-500">معلَّق (بانتظار تسجيل الدفع أو الاعتماد)</p>
                    <p className="text-lg font-bold text-amber-700">{formatNumber(wallet.totals.pending)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Wallet className="h-5 w-5 text-slate-500" />
                  <div>
                    <p className="text-xs text-slate-500">متوقَّع (لو تحقّق كلُّ شرطٍ ناقص)</p>
                    <p className="text-lg font-bold text-slate-700">{formatNumber(wallet.totals.expected)}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-xs font-bold text-slate-700 mb-2">سطور المحفظة</h3>
                {lines.length === 0 ? (
                  <p className="text-xs text-slate-500">لا سطور لهذا الشهر.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-500">
                          <th className="py-1.5 pr-2 text-right">النوع</th>
                          <th className="py-1.5 px-2 text-right">المبلغ</th>
                          <th className="py-1.5 px-2 text-right">الحالة</th>
                          <th className="py-1.5 px-2 text-right">السبب/المصدر</th>
                          <th className="py-1.5 px-2 text-right">آخر تحديث</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lines.map((line) => (
                          <tr key={`${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`} className="border-b border-slate-100">
                            <td className="py-1.5 pr-2">{isCommissionLine(line) ? "عمولة اكتساب" : "راتب"}</td>
                            <td className="py-1.5 px-2 font-semibold">{formatNumber(line.amount)}</td>
                            <td className="py-1.5 px-2">
                              <span className={`rounded-full px-2 py-0.5 ${WALLET_STATUS_TONE[line.status] ?? "bg-emerald-100 text-emerald-700"}`}>
                                {line.status_display || WALLET_LINE_STATUS_LABEL[line.status]}
                              </span>
                            </td>
                            <td className="py-1.5 px-2">
                              {line.status === "pending" && line.pending_reason ? line.pending_reason : (line.reason || "—")}
                              {isCommissionLine(line) && ` · ${line.company_name} · شهر ${formatNumber(line.commission_month_index)}`}
                            </td>
                            <td className="py-1.5 px-2">{formatDateTimeValue(line.updated_at) || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {performance && (
            <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800">كيف يُحسب تقييمي؟</h3>
              <p className="text-xs text-slate-500">
                {performance.status_message} · حجم العينة: {formatNumber(performance.sample_size)} (الحد الأدنى{" "}
                {formatNumber(performance.min_sample_size)})
              </p>
              {performance.composite_score !== null && (
                <p className="text-sm font-bold">النتيجة المركّبة: {formatNumber(performance.composite_score)}%</p>
              )}
              <PilotAxesTable performance={performance} />

              {/* القصة ٤٤: طلبُ مراجعةِ نتيجةٍ بسبب. **لا يرفع الدرجةَ**: يفتح مساراً
                  بشريّاً يصحّح فيه المديرُ بيانةً أو تصنيفاً عند المصدر ثمّ تُعاد اللقطة. */}
              <div className="mt-3 border-t border-slate-100 pt-3">
                <h4 className="mb-1.5 text-xs font-bold text-slate-700">أعترض على هذه النتيجة</h4>
                {openReview ? (
                  <p className="rounded-lg border border-sky-200 bg-sky-50 p-2 text-[11px] text-sky-800">
                    لديك اعتراضٌ مفتوحٌ على هذه الفترة بانتظار ردّ مدير العمليات: «{openReview.reason}»
                  </p>
                ) : (
                  <div className="flex flex-wrap items-start gap-2">
                    <input
                      type="text"
                      value={reviewReason}
                      onChange={(event) => setReviewReason(event.target.value)}
                      placeholder="سبب الاعتراض — خطأُ بياناتٍ أو تصنيف"
                      className="min-w-[240px] flex-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() => void submitReview()}
                      disabled={submittingReview || !reviewReason.trim()}
                      className="rounded-lg bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                    >
                      {submittingReview ? "..." : "أرسل الطلب"}
                    </button>
                  </div>
                )}
                {resolvedReviews.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {resolvedReviews.map((row) => (
                      <li key={row.id} className="rounded-lg bg-slate-50 p-2 text-[11px] text-slate-600">
                        <span className={`ml-1 rounded-full px-2 py-0.5 font-bold ${row.status === "accepted" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-700"}`}>
                          {row.status_display}
                        </span>
                        «{row.reason}» — {row.resolution_note || "بلا ردٍّ مكتوب"}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
};

export default EmployeeSelfWalletCard;
