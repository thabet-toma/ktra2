import React, { useState } from "react";
import { CheckCircle2, Clock, Loader2, Search, ShieldAlert, Users } from "lucide-react";

import {
  closeCompensationMonth,
  previewCompensationMonthClose,
  type CompensationMonthClosePreview,
  type MonthlyCompensationCloseRow,
} from "../../services/platformPilotApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import {
  CcCard,
  CcPill,
  CcSectionTitle,
  CcStatTile,
} from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لإغلاق مستحقّات الشهر.", "تعذّر إتمام العملية.");

const now = new Date();

/** شاشة إغلاق مستحقّات الشهر: معاينةٌ بلا كتابة ثم إغلاقٌ idempotent — لا إعادة فتحٍ إلا بسطر تسوية (210-D، §٥، §٧). */
export const CompensationMonthClosePanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [preview, setPreview] = useState<CompensationMonthClosePreview | null>(null);
  const [closeResult, setCloseResult] = useState<MonthlyCompensationCloseRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runPreview = async () => {
    setLoading(true);
    setError(null);
    setCloseResult(null);
    try {
      setPreview(await previewCompensationMonthClose(year, month));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  };

  const runClose = async () => {
    if (!preview) return;
    if (preview.blockers.length > 0) {
      setError("لا يمكن الإغلاق: توجد تسليماتٌ بانتظار المراجعة ضمن هذا الشهر — راجعها أولاً.");
      return;
    }
    const confirmed = await confirm({
      title: `إغلاق مستحقّات ${formatNumber(month)}/${formatNumber(year)}`,
      message: preview.already_closed
        ? "هذا الشهر مُغلَقٌ سلفاً — لن يتكرّر أيّ سطر، والعرض للمراجعة فقط."
        : `سيُحتسب أداء ورواتب وعمولات ${formatNumber(preview.eligible_employees)} موظفاً نشطاً لهذا الشهر. هذا الإجراء idempotent ولا يُلغى إلا بسطر تسوية لاحق.`,
      confirmText: "إغلاق الشهر",
      danger: false,
    });
    if (!confirmed) return;
    setClosing(true);
    setError(null);
    try {
      const result = await closeCompensationMonth(year, month);
      setCloseResult(result);
      toast("تم إغلاق مستحقّات الشهر.", "success");
      await runPreview();
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setClosing(false);
    }
  };

  return (
    <section className="space-y-6">
      <CcSectionTitle title="إغلاق مستحقّات الشهر" />

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-400" role="alert">
          {error}
        </div>
      )}

      <CcCard className="p-5">
        <div className="flex flex-wrap items-end gap-4">
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">السنة</span>
            <input
              type="number" className="ktra-input h-9 w-28" value={year}
              onChange={(event) => setYear(Number(event.target.value))}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">الشهر</span>
            <input
              type="number" min={1} max={12} className="ktra-input h-9 w-24" value={month}
              onChange={(event) => setMonth(Number(event.target.value))}
            />
          </label>
          <button
            type="button"
            onClick={() => void runPreview()}
            disabled={loading}
            className="ktra-btn ktra-btn-primary"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} معاينة
          </button>
        </div>
      </CcCard>

      {preview && (
        <CcCard className="p-5 space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <CcCard className="p-4">
              <div className="flex flex-col justify-between h-full gap-2">
                <span className="text-xs font-semibold text-cc-text-muted">حالة الشهر</span>
                <div>
                  <CcPill tone={preview.already_closed ? "success" : "warning"} dot>
                    {preview.already_closed ? "مُغلَق سلفاً" : "لم يُغلَق بعد"}
                  </CcPill>
                </div>
              </div>
            </CcCard>
            <CcCard className="p-4">
              <CcStatTile
                label="موظفون نشطون"
                value={preview.eligible_employees}
                tone="accent"
                icon={<Users className="h-4 w-4" />}
              />
            </CcCard>
            <CcCard className="p-4">
              <CcStatTile
                label="مهلة المراجعة"
                value={preview.review_grace_period_hours}
                unit="ساعة"
                tone="neutral"
                icon={<Clock className="h-4 w-4" />}
              />
            </CcCard>
          </div>

          {preview.blockers.length > 0 ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-300">
              <p className="font-bold flex items-center gap-1.5">
                <ShieldAlert className="h-4 w-4 text-amber-400" />
                {formatNumber(preview.blockers.length)} تسليماً بانتظار المراجعة يمنع الإغلاق:
              </p>
              <p className="mt-1.5 text-cc-text-muted">أرقام التسليمات: {preview.blockers.map((id) => `#${id}`).join("، ")}</p>
            </div>
          ) : (
            <p className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
              <CheckCircle2 className="h-4 w-4" /> لا تسليماتٍ معلَّقةً تمنع الإغلاق.
            </p>
          )}

          {preview.close && (
            <div className="space-y-3 pt-4 border-t border-cc-border">
              <h3 className="text-xs font-bold text-cc-text">تفاصيل الإغلاق المسجَّل</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <CcCard className="p-4">
                  <CcStatTile label="سطور رواتب" value={preview.close.salary_lines_created} tone="accent" />
                </CcCard>
                <CcCard className="p-4">
                  <CcStatTile label="سطور عمولات" value={preview.close.commission_lines_created} tone="violet" />
                </CcCard>
                <CcCard className="p-4">
                  <CcStatTile
                    label="لقطات أداء"
                    value={preview.close.snapshots_captured}
                    tone="success"
                    hint={`أُغلق في ${formatDateTimeValue(preview.close.created_at)}`}
                  />
                </CcCard>
              </div>
            </div>
          )}

          {!preview.already_closed && (
            <div className="pt-2">
              <button
                type="button"
                onClick={() => void runClose()}
                disabled={closing || preview.blockers.length > 0}
                className="ktra-btn ktra-btn-primary"
              >
                {closing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} إغلاق الشهر
              </button>
            </div>
          )}
        </CcCard>
      )}

      {closeResult && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs font-semibold text-emerald-400">
          تم إغلاق {formatNumber(closeResult.period_month)}/{formatNumber(closeResult.period_year)}: {formatNumber(closeResult.salary_lines_created)} سطر راتب و{formatNumber(closeResult.commission_lines_created)} سطر عمولة.
        </div>
      )}
    </section>
  );
};

export default CompensationMonthClosePanel;
