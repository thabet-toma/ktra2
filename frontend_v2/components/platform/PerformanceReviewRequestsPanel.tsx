import React, { useCallback, useEffect, useState } from "react";
import { MessageSquareWarning } from "lucide-react";

import {
  listPerformanceReviewRequestsForManager,
  recapturePerformanceAfterAcceptedReview,
  resolvePerformanceReviewRequest,
  type PerformanceReviewRequestRow,
} from "../../services/platformEmployeeSpaceApi";
import { PILOT_AXIS_LABELS, type PilotAxisKey } from "../../services/platformPilotApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "الردّ على الاعتراضات لمدير العمليات وحده.", "تعذّر تحميل الاعتراضات.");

const axisLabel = (axis: string): string =>
  axis ? (PILOT_AXIS_LABELS[axis as PilotAxisKey] ?? axis) : "النتيجة المركّبة";

/**
 * ردُّ مدير العمليات على اعتراضات الموظّفين على نتائجهم الشهرية (القصة ٤٤).
 *
 * `/performance-review-requests/{pk}/resolve/` كانت بلا شاشة — الموظّفُ يفتح
 * اعتراضه من `EmployeeSelfWalletCard.tsx` ولا أحد يردّ عليه (210-F).
 */
export const PerformanceReviewRequestsPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [requests, setRequests] = useState<PerformanceReviewRequestRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRequests(await listPerformanceReviewRequestsForManager());
    } catch (cause) {
      setError(displayError(cause));
      setRequests(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submitRecapture = async (row: PerformanceReviewRequestRow) => {
    const ok = await confirm({
      title: "إعادةُ احتساب الشهر",
      message:
        `ستُعاد لقطةُ ${row.period_month}/${row.period_year} للموظّف ${row.employee_name} على البيانات الحاليّة. `
        + "صحِّحِ المصدرَ أوّلاً (الرابط أو حدثَ الاستخدام أو تصنيفَ الرفض) — وأسطرُ المحفظة لا تتغيّر هنا، "
        + "تصحيحُها بسطر تسويةٍ ظاهر.",
      confirmText: "أعِد الاحتساب",
    });
    if (!ok) return;
    setBusyId(row.id);
    try {
      const snapshot = await recapturePerformanceAfterAcceptedReview(row.id);
      toast(
        snapshot.composite_score === null
          ? "أُعيد الاحتساب — بيانات غير كافية لهذا الشهر."
          : `أُعيد الاحتساب — الدرجةُ الآن ${formatNumber(snapshot.composite_score)}.`,
        "success",
      );
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  const submitResolution = async (row: PerformanceReviewRequestRow, accepted: boolean) => {
    const note = (notes[row.id] ?? "").trim();
    if (!note) {
      toast("الردّ المكتوب إلزاميّ — اكتبه قبل القبول أو الرفض.", "error");
      return;
    }
    setBusyId(row.id);
    try {
      await resolvePerformanceReviewRequest(row.id, { accepted, resolution_note: note });
      toast(accepted ? "قُبل الاعتراض." : "رُفض الاعتراض.", "success");
      setResolvingId(null);
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-4" dir="rtl">
      <div className="flex items-center gap-2">
        <MessageSquareWarning className="h-4 w-4 text-amber-600" />
        <h2 className="text-sm font-bold text-slate-800">اعتراضات الأداء</h2>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="rounded-lg bg-rose-100 px-3 py-1 text-[11px] font-bold hover:bg-rose-200">
            إعادة المحاولة
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
      ) : !requests || requests.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-xs text-slate-400">
          لا اعتراضات مسجَّلة.
        </div>
      ) : (
        <ul className="space-y-3">
          {requests.map((row) => (
            <li key={row.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-bold text-slate-800">
                    {row.employee_name} — {formatNumber(row.period_month)}/{formatNumber(row.period_year)} — {axisLabel(row.axis)}
                  </p>
                  <p className="mt-1 text-xs text-slate-600">{row.reason}</p>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                    row.status === "open"
                      ? "bg-amber-100 text-amber-700"
                      : row.status === "accepted"
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-rose-100 text-rose-700"
                  }`}
                >
                  {row.status_display}
                </span>
              </div>

              {row.status !== "open" ? (
                <div className="mt-2 space-y-2">
                  <p className="text-[11px] text-slate-500">
                    ردّ {row.resolved_by_name || "—"} في {formatDateTimeValue(row.resolved_at) || "—"}: {row.resolution_note}
                  </p>
                  {row.status === "accepted" && (
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => void submitRecapture(row)}
                      className="rounded-lg bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                    >
                      إعادةُ احتساب الشهر بعد التصحيح
                    </button>
                  )}
                </div>
              ) : resolvingId === row.id ? (
                <div className="mt-3 space-y-2">
                  <textarea
                    value={notes[row.id] ?? ""}
                    onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))}
                    placeholder="ردٌّ مكتوبٌ إلزاميّ — قبولاً كان أم رفضاً"
                    rows={2}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => void submitResolution(row, true)}
                      className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      قبول الاعتراض
                    </button>
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => void submitResolution(row, false)}
                      className="rounded-lg bg-rose-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                    >
                      رفض الاعتراض
                    </button>
                    <button
                      type="button"
                      onClick={() => setResolvingId(null)}
                      className="rounded-lg bg-slate-100 px-3 py-1.5 text-[11px] font-bold text-slate-600 hover:bg-slate-200"
                    >
                      إلغاء
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setResolvingId(row.id)}
                  className="mt-3 rounded-lg bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700 hover:bg-blue-100"
                >
                  الردّ على الاعتراض
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default PerformanceReviewRequestsPanel;
