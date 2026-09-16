import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Clock, Download, Loader2, RefreshCw, Search, X } from "lucide-react";

import {
  exportApplicantAttendanceMatrix,
  getApplicantAttendanceMatrix,
  type ApplicantAttendanceCell,
  type ApplicantAttendanceColumn,
  type ApplicantAttendanceStatus,
  type ApplicantAttendanceWindow,
  type ApplicantAttendanceMatrix as ApplicantAttendanceMatrixData,
} from "../../services/platformHiringApi";
import { applicantStatusTone, filterPlatformApplicants } from "../../utils/platformHiring";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import { CcCard, CcEmpty, CcPill } from "../platform/ui";

interface ApplicantAttendanceMatrixProps {
  onOpenMeeting: (meetingId: number) => void;
  onOpenApplicant: (applicantId: number) => void;
  /**
  * عدّادٌ يزيده الأبُ ليطلب إعادةَ الجلب **على المدى المطبَّق نفسِه**.
  *
  * الشبكةُ تبقى مركَّبةً خلف تفصيل الاجتماع كي لا يضيع المدى الذي اختاره
  * المستخدم؛ ولأنّها تبقى، فتسجيلُ حضورٍ في التفصيل لا يصلها من تلقائه —
  * فالعودةُ تزيد العدّادَ وتأتي بالخلايا الجديدة.
  */
  refreshToken?: number;
}

/**
* أيقونةُ كلِّ حالةٍ — **خريطةٌ شاملةٌ على النوع لا سلسلةُ `if` بنصوصٍ حرّة**.
*
* كانت `if (status === "ATTENDED")` وقيمُ الخادم صغيرةٌ (`attended`)، فكانت
* المقارنتان كاذبتين دائماً و**كلُّ خليّةٍ في الشبكة ترسم ساعةَ «مدعوّ»** — أي
* أنّ الجدولَ الذي وُجد ليُقرأ نظرةً واحدةً كان يقول الشيءَ نفسَه عن الجميع.
* و`Record<ApplicantAttendanceStatus, …>` يجعل الحالةَ الناقصةَ أو الزائدةَ
* **خطأَ ترجمة**، فلا يتكرّر الصنفُ بصمت.
*/
const ATTENDANCE_ICON: Record<ApplicantAttendanceStatus, React.ReactNode> = {
  attended: <Check className="h-4 w-4 text-emerald-400" aria-hidden="true" />,
  absent: <X className="h-4 w-4 text-rose-400" aria-hidden="true" />,
  invited: <Clock className="h-4 w-4 text-amber-400" aria-hidden="true" />,
};

/**
* يومُ الاجتماع **بتوقيت القارئ** لا بتوقيت UTC.
*
* `start` طابعُ وقتٍ كامل، و`formatDateValue` على نصٍّ تقتطع أوّلَ عشرة محارف —
* فاجتماعُ الحاديةَ عشرةَ ليلاً يظهر في الشبكة بيومٍ وفي قائمة الاجتماعات (التي
* تمرّ بـ`formatDateTimeValue`) بيومٍ آخر. تمريرُه `Date` يجعلهما يوماً واحداً.
*/
const meetingDay = (start: string): string => formatDateValue(new Date(start));

export const ApplicantAttendanceMatrix: React.FC<ApplicantAttendanceMatrixProps> = ({
  onOpenMeeting,
  onOpenApplicant,
  refreshToken = 0,
}: ApplicantAttendanceMatrixProps) => {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [search, setSearch] = useState("");
  const [matrix, setMatrix] = useState<ApplicantAttendanceMatrixData | null>(null);
  const [appliedWindow, setAppliedWindow] = useState({ from: "", to: "" });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  /** آخرُ مدىً نجح جلبُه — مرجعٌ لا حالة، كي لا تدخل إعادةُ الجلب في تبعيّاتها. */
  const appliedRef = useRef<ApplicantAttendanceWindow>({});

  const loadMatrix = useCallback(async (range: ApplicantAttendanceWindow = {}) => {
    setLoading(true);
    setLoadError("");
    try {
      setMatrix(await getApplicantAttendanceMatrix(range));
      appliedRef.current = range;
      setAppliedWindow({ from: range.from || "", to: range.to || "" });
    } catch (err: unknown) {
      setMatrix(null);
      setLoadError(humanizeThrown(err));
    } finally {
      setLoading(false);
    }
  }, []);

  /** المدى المكتوبُ في الحقلين — موضعٌ واحدٌ يستعمله زرُّ التحديث وإعادةُ المحاولة. */
  const applyTypedWindow = useCallback(
    () => loadMatrix({ from: from || undefined, to: to || undefined }),
    [from, loadMatrix, to],
  );

  // التحميلُ الأوّل على المدى الافتراضيّ، ثمّ كلُّ عودةٍ من تفصيل اجتماعٍ على
  // المدى المطبَّق نفسِه — أثرٌ واحدٌ لا أثران، و`loadMatrix` ثابتةُ الهويّة.
  useEffect(() => {
    void loadMatrix(appliedRef.current);
  }, [loadMatrix, refreshToken]);

  const exportMatrix = async () => {
    if (!matrix) return;
    setExporting(true);
    setExportError("");
    try {
      const file = await exportApplicantAttendanceMatrix({
        from: appliedWindow.from || undefined,
        to: appliedWindow.to || undefined,
      });
      const url = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = url;
      link.download = `حضور-المتقدمين-${matrix.from}-${matrix.to}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setExportError(`تعذّر تصدير شبكة الحضور: ${humanizeThrown(err)}`);
    } finally {
      setExporting(false);
    }
  };

  // البحثُ محلّيٌّ فوق الحمولة المعروضة — بالدالّة المشتركة نفسِها التي يستعملها
  // تبويبُ المتقدّمين، فلا قاعدةَ بحثٍ ثانيةٌ تفترق عنها.
  const visibleRows = useMemo(
    () => filterPlatformApplicants(matrix?.rows ?? [], search),
    [matrix, search],
  );

  const windowIsUnapplied = from !== appliedWindow.from || to !== appliedWindow.to;

  const cellButton = (meeting: ApplicantAttendanceColumn, cell: ApplicantAttendanceCell) => {
    const note = cell.note ? ` — ${cell.note}` : "";
    return (
      <button
        type="button"
        onClick={() => onOpenMeeting(cell.meeting)}
        title={`${meeting.title} — ${cell.status_display}${note}`}
        className="inline-flex min-h-9 min-w-9 items-center justify-center gap-1 rounded-lg p-2 transition hover:bg-cc-surface-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
      >
        {ATTENDANCE_ICON[cell.status]}
        {cell.note && <span className="h-1.5 w-1.5 rounded-full bg-sky-400" aria-hidden="true" />}
        <span className="sr-only">{cell.status_display}{note}</span>
      </button>
    );
  };

  return (
    <div className="space-y-4 text-right" dir="rtl">
      {/* بطاقة التحكم والفلاتر بـ CcCard */}
      <CcCard className="p-4 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end flex-wrap">
            <label className="text-xs font-semibold text-cc-text">
              من
              <input
                type="date"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
                className="mt-1 block w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </label>
            <label className="text-xs font-semibold text-cc-text">
              إلى
              <input
                type="date"
                value={to}
                onChange={(event) => setTo(event.target.value)}
                className="mt-1 block w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </label>
            <button
              type="button"
              onClick={() => void applyTypedWindow()}
              disabled={loading}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-sky-500 disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>تحديث</span>
            </button>
            <label className="relative text-xs font-semibold text-cc-text min-w-[200px]">
              بحث بالاسم
              <Search className="pointer-events-none absolute bottom-2.5 right-3 h-3.5 w-3.5 text-cc-text-muted" aria-hidden="true" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="اكتب جزءاً من الاسم..."
                className="mt-1 block w-full rounded-lg border border-cc-border bg-cc-surface-2 py-2 pr-9 pl-3 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </label>
          </div>

          <button
            type="button"
            onClick={() => void exportMatrix()}
            disabled={exporting || loading || !matrix || windowIsUnapplied}
            title={windowIsUnapplied ? "اضغط «تحديث» أولاً كي يطابق الملفُّ المدى المكتوب" : "تصدير الشبكة المعروضة ملفَّ CSV"}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-cc-border bg-cc-surface-2 px-4 py-2 text-xs font-semibold text-cc-text shadow-sm transition hover:bg-cc-surface disabled:opacity-50"
          >
            {exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            <span>تصدير CSV</span>
          </button>
        </div>

        {matrix && (
          <p className="text-xs text-cc-text-muted pt-1">
            المدى المعروض: <strong className="text-cc-text">{formatDateValue(matrix.from)} — {formatDateValue(matrix.to)}</strong>
            {search.trim() && ` · المعروض ${formatNumber(visibleRows.length)} من ${formatNumber(matrix.rows.length)}`}
          </p>
        )}
        {windowIsUnapplied && (
          <p className="text-xs font-semibold text-amber-400">
            المدى المكتوب لم يُطبَّق بعد — اضغط «تحديث».
          </p>
        )}
        {exportError && (
          <p className="text-xs font-semibold text-rose-400">{exportError}</p>
        )}
      </CcCard>

      {/* مفتاح ألوان مقروء */}
      <div className="flex flex-wrap items-center gap-4 py-2 px-3.5 rounded-xl bg-cc-surface border border-cc-border text-xs">
        <span className="text-cc-text-muted font-bold text-[11px]">مفتاح حالات الحضور:</span>
        <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-400">
          <Check className="h-4 w-4" />
          <span>حضر</span>
        </span>
        <span className="inline-flex items-center gap-1.5 font-semibold text-rose-400">
          <X className="h-4 w-4" />
          <span>لم يحضر</span>
        </span>
        <span className="inline-flex items-center gap-1.5 font-semibold text-amber-400">
          <Clock className="h-4 w-4" />
          <span>مدعوّ</span>
        </span>
        <span className="inline-flex items-center gap-1.5 text-cc-text-muted font-semibold">
          <span className="font-mono text-sm leading-none">—</span>
          <span>لم يُدعَ</span>
        </span>
        <span className="inline-flex items-center gap-1.5 text-sky-400 font-semibold">
          <span className="h-2 w-2 rounded-full bg-sky-400" />
          <span>توجد ملاحظة</span>
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 rounded-xl border border-cc-border bg-cc-surface p-10 text-xs text-cc-text-muted shadow-cc-card">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>جارٍ تحميل شبكة الحضور...</span>
        </div>
      ) : loadError ? (
        <div className="space-y-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-8 text-center shadow-cc-card">
          <p className="text-xs font-semibold text-rose-300">تعذّر تحميل شبكة الحضور: {loadError}</p>
          <button
            type="button"
            onClick={() => void applyTypedWindow()}
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-500"
          >
            إعادة المحاولة
          </button>
        </div>
      ) : !matrix || matrix.meetings.length === 0 ? (
        <CcEmpty title="لا توجد اجتماعات في المدى المحدد" hint="حدد مدى تواريخ أوسع لعرض سجلات الحضور." />
      ) : matrix.rows.length === 0 ? (
        <CcEmpty title="لا يوجد متقدّمون أو ضيوف في اجتماعات المدى المحدد" />
      ) : visibleRows.length === 0 ? (
        <div className="space-y-3 rounded-xl border border-cc-border bg-cc-surface p-10 text-center shadow-cc-card">
          <p className="text-xs text-cc-text-muted">لا اسمَ يطابق «{search}» في هذا المدى.</p>
          <button
            type="button"
            onClick={() => setSearch("")}
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-500"
          >
            مسح البحث
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-cc,1rem)] border border-cc-border bg-cc-surface shadow-cc-card">
          <table className="min-w-max w-full text-right text-xs border-collapse">
            <thead className="border-b border-cc-border bg-cc-surface-2 text-cc-text-muted font-semibold">
              <tr>
                <th className="sticky right-0 z-10 min-w-48 bg-cc-surface-2 p-3 text-right font-semibold border-l border-cc-border">
                  الاسم
                </th>
                {matrix.meetings.map((meeting) => (
                  <th key={meeting.id} className="min-w-36 p-2 text-center font-semibold">
                    <button
                      type="button"
                      onClick={() => onOpenMeeting(meeting.id)}
                      title={`${meeting.title} — ${meeting.status_display}${meeting.location ? ` — ${meeting.location}` : ""}`}
                      className="w-full rounded-lg p-1.5 text-center transition hover:bg-cc-surface focus:outline-none focus:ring-2 focus:ring-sky-500"
                    >
                      <span className="block font-bold text-cc-text">{meeting.title}</span>
                      <span className="mt-0.5 block text-[11px] font-normal text-cc-text-muted">
                        {meetingDay(meeting.start)}
                      </span>
                      {meeting.status !== "scheduled" && (
                        <span className="mt-0.5 block text-[10px] font-semibold text-sky-400">
                          {meeting.status_display}
                        </span>
                      )}
                    </button>
                  </th>
                ))}
                <th className="p-3 text-center font-semibold">حاضر</th>
                <th className="p-3 text-center font-semibold">غائب</th>
                <th className="p-3 text-center font-semibold">مدعو</th>
                <th className="p-3 text-center font-semibold">المجموع</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cc-border text-cc-text">
              {visibleRows.map((row) => {
                const tone = row.applicant === null ? "neutral" : applicantStatusTone(row.applicant_status);

                return (
                  <tr key={row.identity_key} className="group transition hover:bg-cc-surface-2">
                    <td className="sticky right-0 z-10 min-w-48 bg-cc-surface p-3 font-semibold transition group-hover:bg-cc-surface-2 border-l border-cc-border">
                      {row.applicant === null ? (
                        <span className="text-cc-text" title="ضيف — لا ملفَّ متقدّمٍ له">{row.name}</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onOpenApplicant(row.applicant)}
                          className="rounded text-right font-bold text-cc-text transition hover:text-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-500"
                        >
                          {row.name}
                        </button>
                      )}
                      <div className="mt-1">
                        <CcPill tone={tone} className="text-[10px]">
                          {row.applicant === null ? "ضيف" : row.applicant_status_display}
                        </CcPill>
                      </div>
                    </td>
                    {matrix.meetings.map((meeting) => {
                      const cell = row.cells[String(meeting.id)];
                      return (
                        <td key={meeting.id} className="p-2 text-center align-middle">
                          {cell ? (
                            cellButton(meeting, cell)
                          ) : (
                            <span className="text-base text-cc-text-muted/40 font-mono" title="لم يُدعَ">
                              <span aria-hidden="true">—</span>
                              <span className="sr-only">لم يُدعَ</span>
                            </span>
                          )}
                        </td>
                      );
                    })}
                    <td className="p-3 text-center font-bold text-emerald-400">
                      {formatNumber(row.attended)}
                    </td>
                    <td className="p-3 text-center font-bold text-rose-400">
                      {formatNumber(row.absent)}
                    </td>
                    <td className="p-3 text-center font-bold text-amber-400">
                      {formatNumber(row.invited)}
                    </td>
                    <td className="p-3 text-center font-black text-cc-text">
                      {formatNumber(row.total)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
