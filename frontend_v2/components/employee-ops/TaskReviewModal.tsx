import React, { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, XCircle, X, Loader2, RotateCcw } from "lucide-react";
import {
  getEmployeeOpsSettings,
  reviewSubmission,
  unreviewSubmission,
  type EmployeeOpsSettingsDto,
  type TaskSubmissionDto,
} from "../../services/employeeOpsApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { submissionDecisionLabel } from "../../utils/employeeOps";
import { useToast } from "../../contexts/ToastContext";

interface TaskReviewModalProps {
  submission: TaskSubmissionDto;
  isOpen: boolean;
  onClose: () => void;
  onReviewed: (updated: TaskSubmissionDto) => void;
}

export const TaskReviewModal: React.FC<TaskReviewModalProps> = ({
  submission,
  isOpen,
  onClose,
  onReviewed,
}) => {
  const toast = useToast();
  const [reviewerNotes, setReviewerNotes] = useState(submission.reviewer_notes || "");
  const [unreviewReason, setUnreviewReason] = useState("");
  const [showUnreviewInput, setShowUnreviewInput] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // قيمةُ النقطة إعدادٌ لكلّ شركة: الزرُّ يَعِد بما سيُقيَّد فعلاً لا برقمٍ مثبَّت.
  const [settings, setSettings] = useState<EmployeeOpsSettingsDto | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    let alive = true;
    getEmployeeOpsSettings()
      .then((s) => {
        if (alive) setSettings(s);
      })
      .catch(() => {
        // تعذّرُ جلبِ الإعدادات يُسقط الرقمَ من التسمية ولا يُعطّل المراجعة.
      });
    return () => {
      alive = false;
    };
  }, [isOpen]);

  const pointsHint = (value: number | undefined) =>
    typeof value === "number" ? ` (${formatNumber(value)} نقطة)` : "";

  if (!isOpen) return null;

  const handleReview = async (decision: "approved_full" | "approved_partial" | "rejected") => {
    const notesTrimmed = reviewerNotes.trim();
    if (decision === "rejected" && !notesTrimmed) {
      toast("سبب الرفض مطلوب عند رفض التسليم", "error");
      return;
    }

    setSubmitting(true);
    try {
      const res = await reviewSubmission(submission.id, {
        decision,
        reviewer_notes: notesTrimmed,
      });
      toast(`تم تسجيل القرار: ${submissionDecisionLabel(decision)}`, "success");
      onReviewed(res);
      onClose();
    } catch (err: any) {
      toast(err?.message || "فشل تسجيل مراجعة التسليم", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnreview = async () => {
    const reasonTrimmed = unreviewReason.trim();
    if (!reasonTrimmed) {
      toast("سبب إلغاء المراجعة مطلوب", "error");
      return;
    }

    setSubmitting(true);
    try {
      const res = await unreviewSubmission(submission.id, {
        reason: reasonTrimmed,
      });
      toast("تم إلغاء المراجعة وإعادة التسليم إلى طابور الانتظار", "success");
      onReviewed(res);
      onClose();
    } catch (err: any) {
      toast(err?.message || "فشل إلغاء المراجعة", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
          <div>
            <h2 className="text-lg font-bold text-[var(--color-text)]">مراجعة تسليم المهمة</h2>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              الموظف: {submission.employee_name} • تاريخ التسليم: {formatDateTimeValue(submission.created_at)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {/* نص التسليم */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
            <h3 className="text-xs font-bold text-[var(--color-text)] mb-2">بيان التسليم</h3>
            <p className="text-sm text-[var(--color-text)] whitespace-pre-wrap leading-relaxed">
              {submission.body || "لا يوجد نص مرفق بالتسليم."}
            </p>
          </div>

          {/* بنود المنتجات إن وجدت */}
          {submission.items && submission.items.length > 0 && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
              <h3 className="text-xs font-bold text-[var(--color-text)] mb-2">
                بنود المنتجات المرفقة ({submission.items.length})
              </h3>
              <div className="space-y-2">
                {submission.items.map((item, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-xs space-y-1"
                  >
                    {item.product_link && (
                      <div className="flex items-center gap-1">
                        <span className="text-[var(--color-text-muted)]">الرابط:</span>
                        <a
                          href={item.product_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[var(--color-primary)] hover:underline truncate"
                        >
                          {item.product_link}
                        </a>
                      </div>
                    )}
                    {item.product_price !== null && item.product_price !== undefined && (
                      <div>
                        <span className="text-[var(--color-text-muted)]">السعر:</span>{" "}
                        <span className="font-semibold text-[var(--color-text)]">
                          {formatNumber(item.product_price)}
                        </span>
                      </div>
                    )}
                    {item.notes && (
                      <div className="text-[var(--color-text)]">
                        <span className="text-[var(--color-text-muted)]">ملاحظات:</span> {item.notes}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* المرفقات إن وجدت */}
          {submission.attachments && submission.attachments.length > 0 && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
              <h3 className="text-xs font-bold text-[var(--color-text)] mb-2">
                المرفقات ({submission.attachments.length})
              </h3>
              <div className="flex flex-wrap gap-2">
                {submission.attachments.map((att, idx) => (
                  <a
                    key={idx}
                    href={att.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs text-[var(--color-primary)] hover:underline truncate max-w-xs"
                  >
                    {att.name || `مرفق #${idx + 1}`}
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* حالة المراجعة السابقة إن وجدت */}
          {submission.decision !== "pending" && (
            <div className="rounded-xl border border-blue-200 bg-blue-50/50 dark:border-blue-900/50 dark:bg-blue-950/20 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-blue-900 dark:text-blue-300">
                  تمت المراجعة: {submissionDecisionLabel(submission.decision)}
                </span>
                <span className="text-xs text-blue-700 dark:text-blue-400">
                  بواسطة: {submission.reviewer_name || "المدير"} • {formatDateTimeValue(submission.reviewed_at)}
                </span>
              </div>
              {submission.reviewer_notes && (
                <p className="text-xs text-blue-800 dark:text-blue-300 whitespace-pre-wrap">
                  ملاحظات المراجع: {submission.reviewer_notes}
                </p>
              )}

              {/* إلغاءُ المراجعة بقيدٍ مضادّ — للمقبول وحده: الرفضُ لا يُنشئ قيدَ
                  نقاطٍ أصلاً، فـ`unreview_submission` يردّ 400 «لا يوجد قيد نقاط
                  أصلي نشط لإلغائه». زرٌّ مصيرُه الفشلُ دائماً ليس زرّاً. */}
              {(submission.decision === "approved_full" ||
                submission.decision === "approved_partial") && (
              <div className="pt-2 border-t border-blue-200 dark:border-blue-900">
                {!showUnreviewInput ? (
                  <button
                    type="button"
                    onClick={() => setShowUnreviewInput(true)}
                    className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 font-semibold"
                  >
                    <RotateCcw className="h-3.5 w-3.5" /> إلغاء هذه المراجعة وإعادتها للانتظار
                  </button>
                ) : (
                  <div className="space-y-2 mt-2">
                    <label className="block text-xs font-semibold text-red-700 dark:text-red-400">
                      سبب إلغاء المراجعة (إلزامي):
                    </label>
                    <input
                      type="text"
                      value={unreviewReason}
                      onChange={(e) => setUnreviewReason(e.target.value)}
                      placeholder="اكتب سبب إلغاء القرار السابق..."
                      className="h-9 w-full rounded-lg border border-red-300 bg-white dark:bg-slate-900 px-3 text-xs text-[var(--color-text)] outline-none"
                    />
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={submitting}
                        onClick={handleUnreview}
                        className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700"
                      >
                        تأكيد إلغاء المراجعة
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowUnreviewInput(false)}
                        className="text-xs text-[var(--color-text-muted)] hover:underline"
                      >
                        تراجع
                      </button>
                    </div>
                  </div>
                )}
              </div>
              )}
            </div>
          )}

          {/* نموذج المراجعة للمدير إن كان معلقاً */}
          {submission.decision === "pending" && (
            <div className="space-y-3 pt-2">
              <div>
                <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                  ملاحظات المراجع (إلزامية عند الرفض، اختيارية عند القبول)
                </label>
                <textarea
                  rows={3}
                  value={reviewerNotes}
                  onChange={(e) => setReviewerNotes(e.target.value)}
                  placeholder="اكتب ملاحظاتك على التسليم (سبب الرفض إلزامي عند اتخاذ قرار الرفض)..."
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                />
              </div>

              {/* أزرار القرار الثلاثة */}
              <div className="flex flex-wrap items-center gap-2.5 pt-2">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleReview("approved_full")}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  قبول كامل{pointsHint(settings?.points_full)}
                </button>

                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleReview("approved_partial")}
                  className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  <AlertCircle className="h-4 w-4" />
                  قبول جزئي{pointsHint(settings?.points_partial)}
                </button>

                <button
                  type="button"
                  disabled={submitting || !reviewerNotes.trim()}
                  onClick={() => handleReview("rejected")}
                  title={!reviewerNotes.trim() ? "سبب الرفض مطلوب لتفعيل زر الرفض" : "رفض التسليم"}
                  className="flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-40"
                >
                  <XCircle className="h-4 w-4" />
                  رفض التسليم
                </button>
              </div>
              {!reviewerNotes.trim() && (
                <p className="text-[11px] text-rose-500">
                  * لتفعيل خيار «رفض التسليم»، يجب كتابة سبب الرفض في الملاحظات أعلاه أولاً.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
