import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Fingerprint,
  Flame,
  History,
  Loader2,
  Medal,
  PlusCircle,
  Settings,
  Trophy,
  X,
} from "lucide-react";
import {
  checkInAttendance,
  getEmployeeOpsSettings,
  getLeaderboard,
  listEmployees,
  listPoints,
  recordManualPoints,
  updateEmployeeOpsSettings,
  type AttendanceCheckInResultDto,
  type EmployeeDto,
  type EmployeeOpsSettingsDto,
  type LeaderboardDto,
  type PointEntryDto,
} from "../../services/employeeOpsApi";
import { employeeOpsNavLabels } from "../../utils/employeeOps";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useToast } from "../../contexts/ToastContext";

/** حقولُ إعدادات الوحدة — مرآةُ `EmployeeOpsSettings` في الخادم بترتيبٍ يقرؤه المدير. */
const SETTINGS_FIELDS: Array<{
  key: keyof Pick<
    EmployeeOpsSettingsDto,
    | "points_full"
    | "points_partial"
    | "points_attendance"
    | "attendance_daily_cap"
    | "leaderboard_highlight_count"
    | "rejected_retention_months"
    | "invitation_expiry_days"
  >;
  label: string;
  hint: string;
  min: number;
}> = [
  { key: "points_full", label: "نقاط القبول الكامل", hint: "تُمنح عند اعتماد التسليم كاملاً.", min: 0 },
  { key: "points_partial", label: "نقاط القبول الجزئي", hint: "تُمنح عند الاعتماد الجزئي.", min: 0 },
  { key: "points_attendance", label: "نقاط الحضور", hint: "لكل ضغطة زرِّ حضور.", min: 0 },
  { key: "attendance_daily_cap", label: "سقف الحضور اليومي", hint: "أقصى عدد ضغطاتٍ تُحتسب في اليوم.", min: 0 },
  { key: "leaderboard_highlight_count", label: "عدد المُبرَزين في لوحة الشرف", hint: "كم اسماً يُميَّز في أعلى اللوحة.", min: 0 },
  { key: "rejected_retention_months", label: "الاحتفاظ ببيانات المرفوضين (شهر)", hint: "مدّةُ بقاء بيانات المتقدّمين المرفوضين.", min: 0 },
  { key: "invitation_expiry_days", label: "صلاحية رابط الدعوة (يوم)", hint: "لا يقلّ عن يومٍ واحد.", min: 1 },
];

export const EmployeeOpsPointsScreen: React.FC = () => {
  const { can } = usePermissions();
  const canManage = can("employee_ops.manage");
  const navLabels = employeeOpsNavLabels(canManage);
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<"leaderboard" | "history">("leaderboard");

  // الشهر الحالي YYYY-MM
  const currentMonthStr = useMemo(() => todayIso().slice(0, 7), []);

  const [selectedMonth, setSelectedMonth] = useState(currentMonthStr);

  // لوحة الشرف
  const [leaderboard, setLeaderboard] = useState<LeaderboardDto | null>(null);
  const [loadingLeaderboard, setLoadingLeaderboard] = useState(true);

  // سجل النقاط
  const [pointsHistory, setPointsHistory] = useState<PointEntryDto[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedEmployeeFilter, setSelectedEmployeeFilter] = useState<string>("");

  // قائمة الموظفين (للمدير)
  const [employees, setEmployees] = useState<EmployeeDto[]>([]);

  // زر الحضور
  const [checkingIn, setCheckingIn] = useState(false);
  const [lastCheckInResult, setLastCheckInResult] = useState<AttendanceCheckInResultDto | null>(null);

  // مودال النقاط اليدوية (للمدير)
  const [isManualModalOpen, setIsManualModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState<EmployeeOpsSettingsDto | null>(null);
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [manualEmployeeId, setManualEmployeeId] = useState<number | null>(null);
  const [manualPoints, setManualPoints] = useState<string>("");
  const [manualReason, setManualReason] = useState<string>("");
  const [submittingManual, setSubmittingManual] = useState(false);

  // تحميل لوحة الشرف
  const loadLeaderboard = useCallback(async () => {
    setLoadingLeaderboard(true);
    try {
      // شهرُ اللوحة هو الجاري دائماً: «لوحةُ الشرف شهريّةٌ بلا أزرار مدى» —
      // منتقي الشهر يخصّ سجلَّ النقاط وحده.
      const data = await getLeaderboard({ month: currentMonthStr });
      setLeaderboard(data);
    } catch (err: any) {
      toast(err?.message || "فشل تحميل لوحة الشرف", "error");
    } finally {
      setLoadingLeaderboard(false);
    }
  }, [currentMonthStr, toast]);

  // تحميل سجل النقاط
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const empId = selectedEmployeeFilter ? Number(selectedEmployeeFilter) : undefined;
      const data = await listPoints({ month: selectedMonth, employee: empId });
      setPointsHistory(data);
    } catch (err: any) {
      toast(err?.message || "فشل تحميل سجل النقاط", "error");
    } finally {
      setLoadingHistory(false);
    }
  }, [selectedMonth, selectedEmployeeFilter, toast]);

  useEffect(() => {
    void loadLeaderboard();
  }, [loadLeaderboard]);

  useEffect(() => {
    if (activeTab === "history") {
      void loadHistory();
    }
  }, [activeTab, loadHistory]);

  useEffect(() => {
    if (canManage) {
      listEmployees()
        .then((emps) => setEmployees(emps.filter((e) => e.is_active)))
        .catch(() => {});
    }
  }, [canManage]);

  // إعداداتُ الوحدة — تُجلب عند الفتح لا مع الشاشة: بابٌ نادرُ الاستعمال.
  useEffect(() => {
    if (!isSettingsModalOpen) return;
    let alive = true;
    setLoadingSettings(true);
    getEmployeeOpsSettings()
      .then((data) => {
        if (alive) setSettingsDraft(data);
      })
      .catch((err: any) => {
        if (alive) toast(err?.message || "فشل تحميل إعدادات الوحدة", "error");
      })
      .finally(() => {
        if (alive) setLoadingSettings(false);
      });
    return () => {
      alive = false;
    };
  }, [isSettingsModalOpen, toast]);

  const handleSaveSettings = async () => {
    if (!settingsDraft) return;
    setSavingSettings(true);
    try {
      const saved = await updateEmployeeOpsSettings({
        points_full: settingsDraft.points_full,
        points_partial: settingsDraft.points_partial,
        points_attendance: settingsDraft.points_attendance,
        attendance_daily_cap: settingsDraft.attendance_daily_cap,
        leaderboard_highlight_count: settingsDraft.leaderboard_highlight_count,
        rejected_retention_months: settingsDraft.rejected_retention_months,
        invitation_expiry_days: settingsDraft.invitation_expiry_days,
      });
      setSettingsDraft(saved);
      toast("تم حفظ إعدادات الوحدة", "success");
      setIsSettingsModalOpen(false);
      // قيمُ النقاط تُبرِز الأوائل في اللوحة، فتُعاد قراءتُها بعد الحفظ.
      void loadLeaderboard();
    } catch (err: any) {
      toast(err?.message || "فشل حفظ الإعدادات", "error");
    } finally {
      setSavingSettings(false);
    }
  };

  // زر الحضور اليومي
  const handleAttendanceCheckIn = async () => {
    setCheckingIn(true);
    try {
      const res = await checkInAttendance();
      setLastCheckInResult(res);

      if (res.points_awarded > 0) {
        toast(
          `تم تسجيل حضور النشاط بنجاح ومنحك ${res.points_awarded} نقطة (مجموع حضور اليوم: ${res.today_points}/${res.daily_cap})`,
          "success",
        );
      } else {
        toast(
          `بلغتَ سقف اليوم من نقاط الحضور (${res.daily_cap} نقاط). لم تُضَف نقاط جديدة.`,
          "info",
        );
      }

      void loadLeaderboard();
      if (activeTab === "history") void loadHistory();
    } catch (err: any) {
      toast(err?.message || "فشل تسجيل الحضور", "error");
    } finally {
      setCheckingIn(false);
    }
  };

  // منح/خصم نقاط يدوي
  const handleSaveManualPoints = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualEmployeeId) {
      toast("يرجى اختيار الموظف", "error");
      return;
    }
    const pts = Number(manualPoints);
    if (!Number.isFinite(pts) || pts === 0) {
      toast("يرجى إدخال عدد نقاط صالح (موجب للمنح أو سالب للخصم)", "error");
      return;
    }
    if (!manualReason.trim()) {
      toast("سبب منح أو خصم النقاط مطلوب", "error");
      return;
    }

    setSubmittingManual(true);
    try {
      await recordManualPoints({
        employee: manualEmployeeId,
        points: pts,
        reason: manualReason.trim(),
      });
      toast(`تم تسجيل ${pts > 0 ? "منح" : "خصم"} ${Math.abs(pts)} نقطة بنجاح`, "success");
      setIsManualModalOpen(false);
      setManualPoints("");
      setManualReason("");
      setManualEmployeeId(null);

      void loadLeaderboard();
      if (activeTab === "history") void loadHistory();
    } catch (err: any) {
      toast(err?.message || "فشل تسجيل النقاط اليدوية", "error");
    } finally {
      setSubmittingManual(false);
    }
  };

  const getSourceLabel = (source: string) => {
    switch (source) {
      case "task_full":
        return "إنجاز مهمة كامل";
      case "task_partial":
        return "إنجاز مهمة جزئي";
      case "attendance":
        return "حضور نشاط";
      case "manual":
        return "تعديل يدوي";
      case "reversal":
        return "إلغاء اعتماد";
      default:
        return source;
    }
  };

  return (
    <div className="space-y-4 p-4 md:p-6 max-w-7xl mx-auto">
      {/* الترويسة وزر الحضور والنقاط اليدوية */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div>
          <h1 className="text-lg font-bold text-[var(--color-text)]">
            {navLabels.points}
          </h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
            لوحة الشرف الشهرية وسجل النقاط اليومية والنشاط
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* زر تأكيد الحضور */}
          <button
            type="button"
            disabled={checkingIn}
            onClick={handleAttendanceCheckIn}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50 shadow-sm"
          >
            {checkingIn ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Fingerprint className="h-4 w-4" />
            )}
            <span>تسجيل حضور نشاط اليوم</span>
          </button>

          {/* زر النقاط اليدوية للمدير */}
          {canManage && (
            <button
              type="button"
              onClick={() => setIsManualModalOpen(true)}
              className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3.5 py-2 text-xs font-bold text-white hover:opacity-90 shadow-sm"
            >
              <PlusCircle className="h-4 w-4" /> منح / خصم يدوي
            </button>
          )}
        </div>
      </div>

      {/* بطاقة توضيحية لنتيجة الحضور وسقف اليوم */}
      {lastCheckInResult && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/20 p-3 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            <span>
              حضور نشاط اليوم:{" "}
              <strong className="font-bold text-emerald-900 dark:text-emerald-200">
                {lastCheckInResult.today_points} / {lastCheckInResult.daily_cap} نقطة
              </strong>
            </span>
          </div>
          {lastCheckInResult.capped ? (
            <span className="text-[11px] font-bold text-amber-700 dark:text-amber-300">
              بلغتَ سقف اليوم
            </span>
          ) : (
            <span className="text-[11px] text-emerald-700 dark:text-emerald-300">
              متاح كسب المزيد اليوم
            </span>
          )}
        </div>
      )}

      {/* شريط التبويبات + منتقي الشهر (شهري بلا أزرار مدى) */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)]">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("leaderboard")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold border-b-2 transition-all ${
              activeTab === "leaderboard"
                ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            <Trophy className="h-4 w-4 text-amber-500" />
            لوحة الشرف الشهرية
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("history")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold border-b-2 transition-all ${
              activeTab === "history"
                ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            <History className="h-4 w-4" />
            سجل النقاط
          </button>
        </div>

        {/* اختيار الشهر — لسجلّ النقاط وحده */}
        <div className="flex items-center gap-2 pb-2">
          {canManage && (
            <button
              type="button"
              onClick={() => setIsSettingsModalOpen(true)}
              className="flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-2.5 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
            >
              <Settings className="h-3.5 w-3.5" /> إعدادات الوحدة
            </button>
          )}
          {activeTab === "history" && (
          <>
          <span className="text-xs text-[var(--color-text-muted)] font-semibold">الشهر:</span>
          <input
            type="month"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            className="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-xs text-[var(--color-text)] outline-none"
          />
          </>
          )}
        </div>
      </div>

      {/* تبويب 1: لوحة الشرف (كاملة بلا أزرار مدى مع تمييز الأوائل بـ highlight_count) */}
      {activeTab === "leaderboard" && (
        <div className="space-y-4">
          {loadingLeaderboard ? (
            <div className="flex justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-[var(--color-primary)]" />
            </div>
          ) : !leaderboard || leaderboard.results.length === 0 ? (
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center text-xs text-[var(--color-text-muted)]">
              لا توجد نقاط مسجلة في هذا الشهر حتى الآن.
            </div>
          ) : (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-sm">
              <div className="p-3 bg-[var(--color-surface-2)] border-b border-[var(--color-border)] flex items-center justify-between text-xs">
                <span className="font-bold text-[var(--color-text)] flex items-center gap-1.5">
                  <Flame className="h-4 w-4 text-amber-500" />
                  تصنيف موظفي الشركة لشهر {leaderboard.month}
                </span>
                <span className="text-[var(--color-text-muted)]">
                  يتم إبراز أول {leaderboard.highlight_count} مراكز في قائمة المتفوقين
                </span>
              </div>

              <div className="divide-y divide-[var(--color-border)]">
                {leaderboard.results.map((entry, index) => {
                  const isHighlighted = entry.rank <= leaderboard.highlight_count;

                  return (
                    <div
                      key={entry.employee}
                      className={`flex items-center justify-between p-3.5 transition-colors ${
                        isHighlighted
                          ? "bg-amber-50/40 dark:bg-amber-950/20 font-semibold"
                          : "hover:bg-[var(--color-surface-2)]"
                      }`}
                    >
                      <div className="flex items-center gap-3.5">
                        {/* شارة الرتبة */}
                        <div
                          className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold flex-shrink-0 ${
                            entry.rank === 1
                              ? "bg-amber-400 text-amber-950 shadow"
                              : entry.rank === 2
                              ? "bg-slate-300 text-slate-900"
                              : entry.rank === 3
                              ? "bg-amber-600 text-white"
                              : isHighlighted
                              ? "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100"
                              : "bg-[var(--color-surface-3)] text-[var(--color-text-muted)]"
                          }`}
                        >
                          {entry.rank <= 3 ? <Medal className="h-4 w-4" /> : `#${entry.rank}`}
                        </div>

                        <div>
                          <span className="text-sm font-bold text-[var(--color-text)] block">
                            {entry.employee_name}
                          </span>
                          {isHighlighted && (
                            <span className="text-[10px] text-amber-700 dark:text-amber-400 block">
                              ضمن قائمة الشرف
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-left font-mono">
                        <span className="text-base font-bold text-emerald-600 dark:text-emerald-400">
                          {formatNumber(entry.points)}
                        </span>
                        <span className="text-[10px] text-[var(--color-text-muted)] mr-1">نقطة</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* تبويب 2: سجل النقاط */}
      {activeTab === "history" && (
        <div className="space-y-3">
          {/* فلتر الموظف للمدير */}
          {canManage && employees.length > 0 && (
            <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-2.5 text-xs">
              <span className="text-[var(--color-text-muted)] font-semibold">تصفية بالموظف:</span>
              <select
                value={selectedEmployeeFilter}
                onChange={(e) => setSelectedEmployeeFilter(e.target.value)}
                className="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)] outline-none"
              >
                <option value="">جميع الموظفين</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {loadingHistory ? (
            <div className="flex justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-[var(--color-primary)]" />
            </div>
          ) : pointsHistory.length === 0 ? (
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center text-xs text-[var(--color-text-muted)]">
              لا توجد قيود نقاط مسجلة خلال هذا الشهر.
            </div>
          ) : (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-right text-xs">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
                      <th className="py-2.5 px-3 font-semibold">تاريخ الاستحقاق</th>
                      <th className="py-2.5 px-3 font-semibold">الموظف</th>
                      <th className="py-2.5 px-3 font-semibold">المصدر</th>
                      <th className="py-2.5 px-3 font-semibold">السبب والبيان</th>
                      <th className="py-2.5 px-3 font-semibold text-center">النقاط</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {pointsHistory.map((p) => (
                      <tr key={p.id} className="hover:bg-[var(--color-surface-2)]">
                        <td className="py-2.5 px-3 text-[var(--color-text-muted)] font-mono">
                          {formatDateLocalized(p.awarded_on)}
                        </td>
                        <td className="py-2.5 px-3 font-bold text-[var(--color-text)]">
                          {p.employee_name}
                        </td>
                        <td className="py-2.5 px-3 text-[var(--color-text-muted)]">
                          {getSourceLabel(p.source)}
                        </td>
                        <td className="py-2.5 px-3 text-[var(--color-text)] max-w-sm truncate">
                          {p.reason || "—"}
                        </td>
                        <td className="py-2.5 px-3 text-center font-bold font-mono text-sm">
                          <span className={p.points >= 0 ? "text-emerald-600" : "text-rose-600"}>
                            {p.points > 0 ? `+${formatNumber(p.points)}` : formatNumber(p.points)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* مودال المنح أو الخصم اليدوي */}
      {isSettingsModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="relative w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
              <h2 className="text-base font-bold text-[var(--color-text)]">إعدادات وحدة متابعة الموظفين</h2>
              <button
                type="button"
                onClick={() => setIsSettingsModalOpen(false)}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {loadingSettings || !settingsDraft ? (
              <div className="flex items-center justify-center gap-2 py-10 text-xs text-[var(--color-text-muted)]">
                <Loader2 className="h-4 w-4 animate-spin" /> جاري تحميل الإعدادات...
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
                  هذه القيم تخصّ شركتكم وحدها. وتغييرُها يسري على ما يُقيَّد بعد الحفظ فقط —
                  النقاط المُقيَّدة سابقاً تحتفظ بقيمتها وقتَ منحها.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {SETTINGS_FIELDS.map((f) => (
                    <div key={f.key}>
                      <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                        {f.label}
                      </label>
                      <input
                        type="number"
                        min={f.min}
                        value={settingsDraft[f.key]}
                        onChange={(e) =>
                          setSettingsDraft({
                            ...settingsDraft,
                            [f.key]: Number(e.target.value),
                          })
                        }
                        className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
                      />
                      <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">{f.hint}</p>
                    </div>
                  ))}
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] pt-4">
                  <button
                    type="button"
                    onClick={() => setIsSettingsModalOpen(false)}
                    className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-semibold text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                  >
                    إلغاء
                  </button>
                  <button
                    type="button"
                    disabled={savingSettings}
                    onClick={handleSaveSettings}
                    className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-60"
                  >
                    {savingSettings && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    حفظ الإعدادات
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {isManualModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="relative w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl space-y-4">
            <h2 className="text-base font-bold text-[var(--color-text)] border-b border-[var(--color-border)] pb-2">
              منح أو خصم نقاط يدوي
            </h2>

            <form onSubmit={handleSaveManualPoints} className="space-y-3 text-xs">
              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">
                  الموظف <span className="text-red-500">*</span>
                </label>
                <select
                  required
                  value={manualEmployeeId ?? ""}
                  onChange={(e) => setManualEmployeeId(e.target.value ? Number(e.target.value) : null)}
                  className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                >
                  <option value="">اختر الموظف...</option>
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">
                  عدد النقاط (موجب للمنح، سالب للخصم) <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  required
                  value={manualPoints}
                  onChange={(e) => setManualPoints(e.target.value)}
                  placeholder="مثال: 10 أو -5"
                  className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)] font-mono"
                />
              </div>

              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">
                  سبب المنح أو الخصم (إلزامي) <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  value={manualReason}
                  onChange={(e) => setManualReason(e.target.value)}
                  placeholder="اكتب سبب منح أو خصم النقاط..."
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                />
              </div>

              <div className="pt-2 border-t border-[var(--color-border)] flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsManualModalOpen(false)}
                  className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={submittingManual}
                  className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-5 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {submittingManual && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  تأكيد وحفظ القيد
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
