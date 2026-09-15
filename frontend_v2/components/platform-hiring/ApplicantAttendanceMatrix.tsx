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
import { applicantStatusBadgeClass, filterPlatformApplicants } from "../../utils/platformHiring";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";

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
  attended: <Check className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />,
  absent: <X className="h-4 w-4 text-rose-600 dark:text-rose-400" aria-hidden="true" />,
  invited: <Clock className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-hidden="true" />,
};

/**
 * يومُ الاجتماع **بتوقيت القارئ** لا بتوقيت UTC.
 *
 * `start` طابعُ وقتٍ كامل، و`formatDateValue` على نصٍّ تقتطع أوّلَ عشرة محارف —
 * فاجتماعُ الحاديةَ عشرةَ ليلاً يظهر في الشبكة بيومٍ وفي قائمة الاجتماعات (التي
 * تمرّ بـ`formatDateTimeValue`) بيومٍ آخر. تمريرُه `Date` يجعلهما يوماً واحداً.
 */
const meetingDay = (start: string): string => formatDateValue(new Date(start));

export const ApplicantAttendanceMatrix: React.FC<ApplicantAttendanceMatrixProps> = ({ onOpenMeeting, onOpenApplicant, refreshToken = 0 }) => {
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
      <button type="button" onClick={() => onOpenMeeting(cell.meeting)} title={`${meeting.title} — ${cell.status_display}${note}`} className="inline-flex min-h-9 min-w-9 items-center justify-center gap-1 rounded-md p-2 transition hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:bg-slate-800 dark:focus:ring-blue-400">
        {ATTENDANCE_ICON[cell.status]}
        {cell.note && <span className="h-1.5 w-1.5 rounded-full bg-slate-500 dark:bg-slate-400" aria-hidden="true" />}
        <span className="sr-only">{cell.status_display}{note}</span>
      </button>
    );
  };

  return (
    <div className="space-y-4 text-right" dir="rtl">
      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">من
              <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">إلى
              <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
            <button type="button" onClick={() => void applyTypedWindow()} disabled={loading} className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-600 dark:text-white dark:hover:bg-blue-700">
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              تحديث
            </button>
            <label className="relative text-xs font-semibold text-slate-700 dark:text-slate-300">بحث بالاسم
              <Search className="pointer-events-none absolute bottom-2.5 right-3 h-3.5 w-3.5 text-slate-400 dark:text-slate-500" aria-hidden="true" />
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="اكتب جزءاً من الاسم" className="mt-1 block w-full rounded-lg border border-slate-300 bg-white py-2 pr-9 pl-3 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
          </div>
          <button type="button" onClick={() => void exportMatrix()} disabled={exporting || loading || !matrix || windowIsUnapplied} title={windowIsUnapplied ? "اضغط «تحديث» أولاً كي يطابق الملفُّ المدى المكتوب" : "تصدير الشبكة المعروضة ملفَّ CSV"} className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            تصدير
          </button>
        </div>
        {matrix && <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">المدى المعروض: {formatDateValue(matrix.from)} — {formatDateValue(matrix.to)}{search.trim() && ` · المعروض ${formatNumber(visibleRows.length)} من ${formatNumber(matrix.rows.length)}`}</p>}
        {windowIsUnapplied && <p className="mt-2 text-xs font-semibold text-amber-600 dark:text-amber-400">المدى المكتوب لم يُطبَّق بعد — اضغط «تحديث».</p>}
        {exportError && <p className="mt-3 text-xs font-semibold text-rose-600 dark:text-rose-400">{exportError}</p>}
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white p-10 text-xs text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />جارٍ تحميل شبكة الحضور...</div>
      ) : loadError ? (
        <div className="space-y-3 rounded-xl border border-rose-200 bg-rose-50 p-8 text-center shadow-sm dark:border-rose-800 dark:bg-rose-950/40"><p className="text-xs font-semibold text-rose-700 dark:text-rose-300">تعذّر تحميل شبكة الحضور: {loadError}</p><button type="button" onClick={() => void applyTypedWindow()} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700 dark:bg-blue-600 dark:text-white dark:hover:bg-blue-700">إعادة المحاولة</button></div>
      ) : !matrix || matrix.meetings.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-xs text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">لا توجد اجتماعات في المدى المحدد.</div>
      ) : matrix.rows.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-xs text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">لا يوجد متقدّمون أو ضيوف في اجتماعات المدى المحدد.</div>
      ) : visibleRows.length === 0 ? (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900"><p className="text-xs text-slate-500 dark:text-slate-400">لا اسمَ يطابق «{search}» في هذا المدى.</p><button type="button" onClick={() => setSearch("")} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700 dark:bg-blue-600 dark:text-white dark:hover:bg-blue-700">مسح البحث</button></div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <table className="min-w-max w-full text-right text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300"><tr>
              <th className="sticky right-0 z-10 min-w-48 bg-slate-50 p-3 text-right font-semibold dark:bg-slate-800">الاسم</th>
              {matrix.meetings.map((meeting) => <th key={meeting.id} className="min-w-36 p-2 text-center font-semibold"><button type="button" onClick={() => onOpenMeeting(meeting.id)} title={`${meeting.title} — ${meeting.status_display}${meeting.location ? ` — ${meeting.location}` : ""}`} className="w-full rounded-md p-1.5 text-center transition hover:bg-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:bg-slate-700 dark:focus:ring-blue-400"><span className="block font-semibold">{meeting.title}</span><span className="mt-1 block text-[11px] font-normal text-slate-500 dark:text-slate-400">{meetingDay(meeting.start)}</span>{meeting.status !== "scheduled" && <span className="mt-1 block text-[11px] font-normal text-slate-400 dark:text-slate-500">{meeting.status_display}</span>}</button></th>)}
              <th className="p-3 text-center font-semibold">حاضر</th><th className="p-3 text-center font-semibold">غائب</th><th className="p-3 text-center font-semibold">مدعو</th><th className="p-3 text-center font-semibold">المجموع</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 text-slate-800 dark:divide-slate-800/80 dark:text-slate-200">
              {visibleRows.map((row) => <tr key={row.identity_key} className="group transition hover:bg-blue-50/40 dark:hover:bg-blue-950/20">
                <td className="sticky right-0 z-10 min-w-48 bg-white p-3 font-semibold transition group-hover:bg-blue-50/40 dark:bg-slate-900 dark:group-hover:bg-blue-950/20">
                  {row.applicant === null ? <span title="ضيف — لا ملفَّ متقدّمٍ له">{row.name}</span> : <button type="button" onClick={() => onOpenApplicant(row.applicant)} className="rounded-md text-right transition hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:text-blue-300 dark:focus:ring-blue-400">{row.name}</button>}
                  <span className={`mt-1 flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${row.applicant === null ? "border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400" : applicantStatusBadgeClass(row.applicant_status)}`}>{row.applicant === null ? "ضيف" : row.applicant_status_display}</span>
                </td>
                {matrix.meetings.map((meeting) => { const cell = row.cells[String(meeting.id)]; return <td key={meeting.id} className="p-2 text-center">{cell ? cellButton(meeting, cell) : <span className="text-base text-slate-300 dark:text-slate-600" title="لم يُدعَ"><span aria-hidden="true">—</span><span className="sr-only">لم يُدعَ</span></span>}</td>; })}
                <td className="p-3 text-center">{formatNumber(row.attended)}</td><td className="p-3 text-center">{formatNumber(row.absent)}</td><td className="p-3 text-center">{formatNumber(row.invited)}</td><td className="p-3 text-center font-semibold">{formatNumber(row.total)}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
