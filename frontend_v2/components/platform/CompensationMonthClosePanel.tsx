import React, { useState } from "react";
import { CheckCircle2, Loader2, Search } from "lucide-react";

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
    <section className="space-y-4">
      <h2 className="text-lg font-bold text-slate-900">إغلاق مستحقّات الشهر</h2>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700" role="alert">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">السنة</span>
          <input
            type="number" className="ktra-input h-9 w-24" value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">الشهر</span>
          <input
            type="number" min={1} max={12} className="ktra-input h-9 w-20" value={month}
            onChange={(event) => setMonth(Number(event.target.value))}
          />
        </label>
        <button type="button" onClick={() => void runPreview()} disabled={loading} className="ktra-btn ktra-btn-primary">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} معاينة
        </button>
      </div>

      {preview && (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <p><span className="text-slate-500">الحالة:</span> {preview.already_closed ? "مُغلَق سلفاً" : "لم يُغلَق بعد"}</p>
            <p><span className="text-slate-500">موظفون نشطون:</span> {formatNumber(preview.eligible_employees)}</p>
            <p><span className="text-slate-500">مهلة المراجعة:</span> {formatNumber(preview.review_grace_period_hours)} ساعة</p>
          </div>

          {preview.blockers.length > 0 ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
              <p className="font-bold">{formatNumber(preview.blockers.length)} تسليماً بانتظار المراجعة يمنع الإغلاق:</p>
              <p>أرقام التسليمات: {preview.blockers.map((id) => `#${id}`).join("، ")}</p>
            </div>
          ) : (
            <p className="flex items-center gap-1 text-xs font-semibold text-emerald-700">
              <CheckCircle2 className="h-3.5 w-3.5" /> لا تسليماتٍ معلَّقةً تمنع الإغلاق.
            </p>
          )}

          {preview.close && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
              <p>سطور رواتب: {formatNumber(preview.close.salary_lines_created)} · سطور عمولات: {formatNumber(preview.close.commission_lines_created)}</p>
              <p>لقطات أداء: {formatNumber(preview.close.snapshots_captured)} · أُغلق في {formatDateTimeValue(preview.close.created_at)}</p>
            </div>
          )}

          {!preview.already_closed && (
            <button
              type="button" onClick={() => void runClose()}
              disabled={closing || preview.blockers.length > 0}
              className="ktra-btn ktra-btn-primary"
            >
              {closing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} إغلاق الشهر
            </button>
          )}
        </div>
      )}

      {closeResult && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
          تم إغلاق {formatNumber(closeResult.period_month)}/{formatNumber(closeResult.period_year)}: {formatNumber(closeResult.salary_lines_created)} سطر راتب و{formatNumber(closeResult.commission_lines_created)} سطر عمولة.
        </div>
      )}
    </section>
  );
};

export default CompensationMonthClosePanel;
