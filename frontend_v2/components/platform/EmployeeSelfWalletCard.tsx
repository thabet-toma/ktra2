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
import { CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton, CcStatTile, CcTable, CcTd, CcTh, CcThead, CcTr } from "./ui";
import type { CcTone } from "../../utils/ccTone";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لاستعراض هذه المحفظة.", "تعذّر تحميل البيانات.");

const now = new Date();

type WalletLine = EmployeeSalaryLineRow | AcquisitionCommissionLineRow;
const isCommissionLine = (line: WalletLine): line is AcquisitionCommissionLineRow => "acquisition" in line;

/**
 * ألوانُ حالات سطر المحفظة. **`reversed` ليس مؤكَّداً**: كان يقع في فرع «غير معلَّق»
 * فيُرسَم بأخضر المؤكَّد، فيقرأ الموظّفُ سطراً عُكس مالاً مستحقّاً له.
 */
const WALLET_STATUS_TONES: Partial<Record<WalletLineStatus, CcTone>> = {
  pending: "warning",
  eligible: "accent",
  reversed: "danger",
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
      <CcCard className="p-4 flex flex-wrap items-end gap-3">
        <div className="ml-auto">
          <CcSectionTitle title="محفظتي وتقييمي" />
        </div>
        <label className="space-y-1 text-xs">
          <span className="text-cc-text-muted">السنة</span>
          <input
            type="number"
            className="w-24 px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-cc-text-muted">الشهر</span>
          <input
            type="number"
            min={1}
            max={12}
            className="w-20 px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
            value={month}
            onChange={(event) => setMonth(Number(event.target.value))}
          />
        </label>
      </CcCard>

      {error && (
        <CcCard tone="danger" className="p-3 text-xs flex items-center justify-between gap-2">
          <span className="text-rose-400 font-semibold">{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 rounded-lg font-bold text-[11px] transition-colors"
          >
            إعادة المحاولة
          </button>
        </CcCard>
      )}

      {loading ? (
        <CcSkeleton variant="card" count={3} />
      ) : (
        <>
          {wallet && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <CcCard className="p-4">
                  <CcStatTile
                    label="مؤكَّد"
                    value={formatNumber(wallet.totals.confirmed)}
                    icon={<Wallet className="h-5 w-5" />}
                    tone="success"
                  />
                </CcCard>
                <CcCard className="p-4">
                  <CcStatTile
                    label="معلَّق"
                    hint="بانتظار تسجيل الدفع أو الاعتماد"
                    value={formatNumber(wallet.totals.pending)}
                    icon={<Wallet className="h-5 w-5" />}
                    tone="warning"
                  />
                </CcCard>
                <CcCard className="p-4">
                  <CcStatTile
                    label="متوقَّع"
                    hint="لو تحقّق كلُّ شرطٍ ناقص"
                    value={formatNumber(wallet.totals.expected)}
                    icon={<Wallet className="h-5 w-5" />}
                    tone="neutral"
                  />
                </CcCard>
              </div>

              <CcCard className="p-4 space-y-3">
                <h3 className="text-xs font-bold text-cc-text">سطور المحفظة</h3>
                {lines.length === 0 ? (
                  <CcEmpty title="لا سطور لهذا الشهر." />
                ) : (
                  <CcTable>
                    <CcThead>
                      <CcTr>
                        <CcTh>النوع</CcTh>
                        <CcTh>المبلغ</CcTh>
                        <CcTh>الحالة</CcTh>
                        <CcTh>السبب/المصدر</CcTh>
                        <CcTh>آخر تحديث</CcTh>
                      </CcTr>
                    </CcThead>
                    <tbody>
                      {lines.map((line) => {
                        const tone: CcTone = WALLET_STATUS_TONES[line.status] || "success";
                        return (
                          <CcTr key={`${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`}>
                            <CcTd className="font-medium">{isCommissionLine(line) ? "عمولة اكتساب" : "راتب"}</CcTd>
                            <CcTd className="font-bold text-cc-text">{formatNumber(line.amount)}</CcTd>
                            <CcTd>
                              <CcPill tone={tone} className={line.status === "reversed" ? "line-through" : ""}>
                                {line.status_display || WALLET_LINE_STATUS_LABEL[line.status]}
                              </CcPill>
                            </CcTd>
                            <CcTd className="text-cc-text-muted text-xs">
                              {line.status === "pending" && line.pending_reason ? line.pending_reason : (line.reason || "—")}
                              {isCommissionLine(line) && ` · ${line.company_name} · شهر ${formatNumber(line.commission_month_index)}`}
                            </CcTd>
                            <CcTd className="text-cc-text-muted text-xs">{formatDateTimeValue(line.updated_at) || "—"}</CcTd>
                          </CcTr>
                        );
                      })}
                    </tbody>
                  </CcTable>
                )}
              </CcCard>
            </div>
          )}

          {performance && (
            <CcCard className="p-4 space-y-3">
              <h3 className="text-sm font-bold text-cc-text">كيف يُحسب تقييمي؟</h3>
              <p className="text-xs text-cc-text-muted">
                {performance.status_message} · حجم العينة: {formatNumber(performance.sample_size)} (الحد الأدنى{" "}
                {formatNumber(performance.min_sample_size)})
              </p>
              {performance.composite_score !== null && (
                <p className="text-sm font-bold text-sky-400">النتيجة المركّبة: {formatNumber(performance.composite_score)}%</p>
              )}
              <PilotAxesTable performance={performance} />

              {/* القصة ٤٤: طلبُ مراجعةِ نتيجةٍ بسبب. **لا يرفع الدرجةَ**: يفتح مساراً
                  بشريّاً يصحّح فيه المديرُ بيانةً أو تصنيفاً عند المصدر ثمّ تُعاد اللقطة. */}
              <div className="mt-3 border-t border-cc-border pt-3">
                <h4 className="mb-1.5 text-xs font-bold text-cc-text">أعترض على هذه النتيجة</h4>
                {openReview ? (
                  <p className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2.5 text-[11px] text-sky-300">
                    لديك اعتراضٌ مفتوحٌ على هذه الفترة بانتظار ردّ مدير العمليات: «{openReview.reason}»
                  </p>
                ) : (
                  <div className="flex flex-wrap items-start gap-2">
                    <input
                      type="text"
                      value={reviewReason}
                      onChange={(event) => setReviewReason(event.target.value)}
                      placeholder="سبب الاعتراض — خطأُ بياناتٍ أو تصنيف"
                      className="min-w-[240px] flex-1 rounded-lg bg-cc-bg border border-cc-border px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:border-sky-500"
                    />
                    <button
                      type="button"
                      onClick={() => void submitReview()}
                      disabled={submittingReview || !reviewReason.trim()}
                      className="rounded-lg bg-cc-surface-2 hover:bg-cc-border border border-cc-border px-3 py-1.5 text-xs font-semibold text-cc-text disabled:opacity-50 transition-colors"
                    >
                      {submittingReview ? "..." : "أرسل الطلب"}
                    </button>
                  </div>
                )}
                {resolvedReviews.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {resolvedReviews.map((row) => (
                      <li key={row.id} className="rounded-lg bg-cc-surface-2 p-2 text-[11px] text-cc-text-muted border border-cc-border">
                        <CcPill tone={row.status === "accepted" ? "success" : "neutral"} className="ml-1">
                          {row.status_display}
                        </CcPill>
                        «{row.reason}» — {row.resolution_note || "بلا ردٍّ مكتوب"}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </CcCard>
          )}
        </>
      )}
    </section>
  );
};

export default EmployeeSelfWalletCard;
