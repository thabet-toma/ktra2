import React, { useCallback, useEffect, useState } from "react";
import { Check, X } from "lucide-react";

import {
  listPerformanceReviewRequestsForManager,
  recapturePerformanceAfterAcceptedReview,
  resolvePerformanceReviewRequest,
  type PerformanceReviewRequestRow,
  type PerformanceReviewStatus,
} from "../../services/platformEmployeeSpaceApi";
import { PILOT_AXIS_LABELS, type PilotAxisKey } from "../../services/platformPilotApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { type CcTone } from "../../utils/ccTone";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import {
  CcAvatar,
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcSkeleton,
} from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "الردّ على الاعتراضات لمدير العمليات وحده.", "تعذّر تحميل الاعتراضات.");

const axisLabel = (axis: string): string =>
  axis ? (PILOT_AXIS_LABELS[axis as PilotAxisKey] ?? axis) : "النتيجة المركّبة";

const REVIEW_STATUS_TONE: Record<PerformanceReviewStatus, CcTone> = {
  open: "warning",
  accepted: "success",
  rejected: "danger",
};

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
    <section className="space-y-6" dir="rtl">
      <CcSectionTitle
        title="اعتراضات الأداء"
        subtitle="ردُّ مدير العمليات على اعتراضات الموظّفين على نتائجهم الشهرية"
        badge={requests && requests.length > 0 ? requests.length : undefined}
      />

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400 font-semibold" role="alert">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="ktra-btn text-[11px] py-1 px-2.5"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          <CcSkeleton variant="card" count={3} />
        </div>
      ) : !requests || requests.length === 0 ? (
        <CcEmpty title="لا اعتراضات مسجَّلة." />
      ) : (
        <div className="space-y-4">
          {requests.map((row) => (
            <CcCard key={row.id} className="p-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  <CcAvatar name={row.employee_name} size="md" />
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-cc-text">
                      {row.employee_name} — {formatNumber(row.period_month)}/{formatNumber(row.period_year)} — {axisLabel(row.axis)}
                    </h3>
                    <p className="mt-1 text-xs text-cc-text-muted leading-relaxed">{row.reason}</p>
                  </div>
                </div>
                <CcPill
                  tone={REVIEW_STATUS_TONE[row.status] || "neutral"}
                  dot
                >
                  {row.status_display}
                </CcPill>
              </div>

              {row.status !== "open" ? (
                <div className="mt-2 space-y-2 border-t border-cc-border pt-3">
                  <p className="text-xs text-cc-text-muted">
                    ردّ {row.resolved_by_name || "—"} في {formatDateTimeValue(row.resolved_at) || "—"}: {row.resolution_note}
                  </p>
                  {row.status === "accepted" && (
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => void submitRecapture(row)}
                      className="ktra-btn text-xs font-bold disabled:opacity-50"
                    >
                      إعادةُ احتساب الشهر بعد التصحيح
                    </button>
                  )}
                </div>
              ) : resolvingId === row.id ? (
                <div className="mt-3 space-y-3 border-t border-cc-border pt-3">
                  <textarea
                    value={notes[row.id] ?? ""}
                    onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))}
                    placeholder="ردٌّ مكتوبٌ إلزاميّ — قبولاً كان أم رفضاً"
                    rows={2}
                    className="ktra-input w-full p-2.5 text-xs min-h-[60px]"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => void submitResolution(row, true)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50 transition"
                    >
                      <Check className="h-3.5 w-3.5" /> قبول الاعتراض
                    </button>
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => void submitResolution(row, false)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50 transition"
                    >
                      <X className="h-3.5 w-3.5" /> رفض الاعتراض
                    </button>
                    <button
                      type="button"
                      onClick={() => setResolvingId(null)}
                      className="ktra-btn text-xs"
                    >
                      إلغاء
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mt-2 border-t border-cc-border pt-2">
                  <button
                    type="button"
                    onClick={() => setResolvingId(row.id)}
                    className="ktra-btn text-xs"
                  >
                    الردّ على الاعتراض
                  </button>
                </div>
              )}
            </CcCard>
          ))}
        </div>
      )}
    </section>
  );
};

export default PerformanceReviewRequestsPanel;
