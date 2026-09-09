import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  ListTodo,
  Loader2,
  Play,
  Square,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react";
import {
  getPointsSummary,
  listMyTasks,
  listTasks,
  listSubmissions,
  listEmployees,
  startTaskTimer,
  stopTaskTimer,
  type EmployeeCardDto,
  type PointsSummaryDto,
  type TaskDto,
  type TaskSubmissionDto,
} from "../../services/employeeOpsApi";
import {
  assignmentStatusLabel,
  dailyBucket,
  splitMyDailyTasks,
  taskPriorityBadgeClass,
  taskPriorityLabel,
  taskStatusLabel,
} from "../../utils/employeeOps";
import { formatDateLocalized, formatDateTimeValue, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useToast } from "../../contexts/ToastContext";
import { TaskSubmitModal } from "./TaskSubmitModal";
import { TaskReviewModal } from "./TaskReviewModal";
import { EmployeeCardModal } from "./EmployeeCardModal";

export const EmployeeOpsDailyScreen: React.FC = () => {
  const { can } = usePermissions();
  const canManage = can("employee_ops.manage");
  const toast = useToast();

  const [summary, setSummary] = useState<PointsSummaryDto | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);

  // مهام المستخدم الحالي لشاشة يومي
  const [myTasks, setMyTasks] = useState<TaskDto[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(true);

  // حالة طي قسم «بانتظار موافقة المدير»
  const [pendingApprovalCollapsed, setPendingApprovalCollapsed] = useState(true);

  // مودال التسليم
  const [submitTaskTarget, setSubmitTaskTarget] = useState<TaskDto | null>(null);

  // لوحة المدير
  const [pendingSubmissions, setPendingSubmissions] = useState<TaskSubmissionDto[]>([]);
  const [overdueTasks, setOverdueTasks] = useState<TaskDto[]>([]);
  const [teamCards, setTeamCards] = useState<EmployeeCardDto[]>([]);
  const [loadingManagerQueue, setLoadingManagerQueue] = useState(false);
  const [reviewSubmissionTarget, setReviewSubmissionTarget] = useState<TaskSubmissionDto | null>(null);
  const [selectedCardEmployeeId, setSelectedCardEmployeeId] = useState<number | null>(null);

  const [togglingTimerId, setTogglingTimerId] = useState<number | null>(null);

  const today = useMemo(() => todayIso(), []);

  // جلب ملخص النقاط والمهام
  const loadDailyData = useCallback(async () => {
    try {
      const sum = await getPointsSummary();
      setSummary(sum);
    } catch {
      // ملخص النقاط قد يعود بصفر إن لم يكن للمستخدم ملف موظف
    } finally {
      setLoadingSummary(false);
    }

    try {
      const tasks = await listMyTasks();
      setMyTasks(tasks);
    } catch (err: any) {
      toast(err?.message || "فشل جلب مهامي اليومية", "error");
    } finally {
      setLoadingTasks(false);
    }
  }, [toast]);

  // جلب طابور المدير إن كان يملك صلاحية manage
  const loadManagerQueue = useCallback(async () => {
    if (!canManage) return;
    setLoadingManagerQueue(true);
    try {
      const [pendingSubs, allTasks, emps] = await Promise.all([
        // المنتظِرةُ وحدها من الخادم — لا سجلُّ التسليمات كلُّه لِيُرمى أغلبُه.
        listSubmissions({ decision: "pending" }),
        listTasks(),
        listEmployees(),
      ]);

      // 1. التسليمات التي تنتظر المراجعة
      setPendingSubmissions(pendingSubs);

      // 2. المهام المتأخرة غير المكتملة
      setOverdueTasks(
        allTasks.filter(
          (t) =>
            t.status !== "COMPLETED" &&
            dailyBucket(t.due_date, today) === "overdue",
        ),
      );

      // 3. صفوفُ الفريق — العدّاداتُ تأتي مع القائمة نفسها.
      // كانت هنا نداءةُ كرتٍ لكلّ موظف: خمسون موظفاً = خمسون طلبَ HTTP على
      // شاشةِ الدخول. صارت طلباً واحداً باستعلاماتٍ فرعيّة في الخادم.
      setTeamCards(emps.filter((e) => e.is_active));
    } catch (err: any) {
      toast(err?.message || "فشل جلب طابور مراجعة المدير", "error");
    } finally {
      setLoadingManagerQueue(false);
    }
  }, [canManage, today, toast]);

  useEffect(() => {
    void loadDailyData();
    if (canManage) {
      void loadManagerQueue();
    }
  }, [loadDailyData, loadManagerQueue, canManage]);

  // تشغيل / إيقاف المؤقت
  const handleToggleTimer = async (task: TaskDto) => {
    const isWorking = task.my_assignment?.work_started_at != null;
    setTogglingTimerId(task.id);
    try {
      let updatedAssignment;
      if (isWorking) {
        updatedAssignment = await stopTaskTimer(task.id);
        toast("تم إيقاف مؤقت العمل بنجاح", "info");
      } else {
        updatedAssignment = await startTaskTimer(task.id);
        toast("تم بدء احتساب وقت العمل على المهمة", "success");
      }
      setMyTasks((prev) =>
        prev.map((t) =>
          t.id === task.id ? { ...t, my_assignment: updatedAssignment } : t,
        ),
      );
    } catch (err: any) {
      toast(err?.message || "تعذر تعديل حالة المؤقت", "error");
    } finally {
      setTogglingTimerId(null);
    }
  };

  // تقسيم المهام: المفتوحة النشطة vs المسلّمة بانتظار المدير.
  // المنطقُ في `utils/employeeOps` لأنّه وحده ما تحرسه بوّابةُ `node --test`.
  const { activeDailyTasks, pendingApprovalTasks } = useMemo(() => {
    const { active, pending } = splitMyDailyTasks(myTasks, today);
    return { activeDailyTasks: active, pendingApprovalTasks: pending };
  }, [myTasks, today]);

  return (
    <div className="space-y-4 p-4 md:p-6 max-w-7xl mx-auto">
      {/* رأسٌ مضغوطٌ في سطر: نقاطُ الشهر · الترتيب · المهامُّ المفتوحة */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <ListTodo className="h-5 w-5 text-[var(--color-primary)]" />
          <h1 className="text-sm md:text-base font-bold text-[var(--color-text)]">
            يومي — خطة إنجاز اليوم
          </h1>
        </div>

        <div className="flex items-center gap-4 text-xs font-semibold text-[var(--color-text-muted)]">
          <div className="flex items-center gap-1.5">
            <Award className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <span>نقاط الشهر:</span>
            <span className="font-bold text-emerald-700 dark:text-emerald-300">
              {loadingSummary ? "…" : formatNumber(summary?.points ?? 0)}
            </span>
          </div>

          <span className="text-[var(--color-border)]">•</span>

          <div className="flex items-center gap-1.5">
            <TrendingUp className="h-4 w-4 text-amber-500" />
            <span>الترتيب:</span>
            <span className="font-bold text-[var(--color-text)]">
              {loadingSummary
                ? "…"
                : summary?.rank
                ? `#${summary.rank}`
                : "خارج اللوحة"}
            </span>
          </div>

          <span className="text-[var(--color-border)]">•</span>

          <div className="flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-blue-500" />
            <span>المهام المفتوحة:</span>
            <span className="font-bold text-[var(--color-text)]">
              {loadingSummary
                ? "…"
                : formatNumber(summary?.open_tasks_count ?? activeDailyTasks.length)}
            </span>
          </div>
        </div>
      </div>

      {/* لوحة المدير (لحامل manage) — الطابور قبل الأرقام: ما ينتظر تدخلك ثم فريقك */}
      {canManage && (
        <div className="space-y-4 rounded-2xl border border-blue-200 bg-blue-50/30 dark:border-blue-900/40 dark:bg-blue-950/10 p-4 md:p-5">
          <div className="flex items-center justify-between border-b border-blue-200 dark:border-blue-900/50 pb-2">
            <div className="flex items-center gap-2">
              <UserCheck className="h-4 w-4 text-blue-700 dark:text-blue-400" />
              <h2 className="text-xs md:text-sm font-bold text-blue-900 dark:text-blue-200">
                لوحة المدير — ما ينتظر تدخّلك وفريقك
              </h2>
            </div>
            {loadingManagerQueue && (
              <span className="flex items-center gap-1 text-[11px] text-blue-700 dark:text-blue-400">
                <Loader2 className="h-3 w-3 animate-spin" /> جاري التحديث...
              </span>
            )}
          </div>

          {/* (١) ما ينتظر تدخّلك: تسليمات تنتظر المراجعة ثم المتأخرات — قائمة قابلة للفتح لا رقماً */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* طابور التسليمات */}
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-[var(--color-text)] flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  تسليمات تنتظر المراجعة ({pendingSubmissions.length})
                </span>
              </div>

              {pendingSubmissions.length === 0 ? (
                <p className="text-xs text-[var(--color-text-muted)] py-4 text-center">
                  رائع! لا توجد تسليمات معلقة تنتظر مراجعتك حالياً.
                </p>
              ) : (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {pendingSubmissions.map((sub) => (
                    <button
                      key={sub.id}
                      type="button"
                      onClick={() => setReviewSubmissionTarget(sub)}
                      className="w-full flex items-center justify-between p-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-3)] text-right transition-all text-xs"
                    >
                      <div className="truncate ml-2">
                        <span className="font-bold text-[var(--color-text)] block">
                          {sub.employee_name}
                        </span>
                        <span className="text-[11px] text-[var(--color-text-muted)] truncate block">
                          {sub.body || "تسليم بدون نص مرفق"}
                        </span>
                      </div>
                      <span className="rounded-md bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-2 py-1 text-[10px] font-bold flex-shrink-0">
                        مراجعة الآن
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* طابور المتأخرات */}
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-[var(--color-text)] flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-600" />
                  مهام متأخرة مفتوحة ({overdueTasks.length})
                </span>
              </div>

              {overdueTasks.length === 0 ? (
                <p className="text-xs text-[var(--color-text-muted)] py-4 text-center">
                  ممتاز! لا توجد مهام متأخرة على الفريق حالياً.
                </p>
              ) : (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {overdueTasks.map((t) => (
                    <div
                      key={t.id}
                      className="flex items-center justify-between p-2.5 rounded-lg border border-rose-200 bg-rose-50/50 dark:border-rose-900/50 dark:bg-rose-950/20 text-xs"
                    >
                      <div className="truncate ml-2">
                        <span className="font-bold text-rose-900 dark:text-rose-200 block truncate">
                          {t.title}
                        </span>
                        <span className="text-[11px] text-rose-700 dark:text-rose-400 block">
                          استحقت: {formatDateLocalized(t.due_date)} • المسندين:{" "}
                          {t.assignments.map((a) => a.employee_name).join("، ") || "بدون إسناد"}
                        </span>
                      </div>
                      <span className="rounded bg-rose-200 text-rose-900 dark:bg-rose-900 dark:text-rose-200 px-2 py-0.5 text-[10px] font-bold flex-shrink-0">
                        متأخرة
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* (٢) فريقُك: صفٌّ لكلّ موظف (مفتوحة · متأخّرة · نقاطُ الشهر) */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 overflow-hidden">
            <h3 className="text-xs font-bold text-[var(--color-text)] mb-2 flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5 text-blue-600" />
              متابعة أداء الفريق ({teamCards.length})
            </h3>

            {teamCards.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)] py-3 text-center">
                لا يوجد موظفون نشطون مسجلون.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-right text-xs">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                      <th className="py-2 px-3 font-semibold">الموظف</th>
                      <th className="py-2 px-3 font-semibold">المسمى</th>
                      <th className="py-2 px-3 font-semibold text-center">المهام المفتوحة</th>
                      <th className="py-2 px-3 font-semibold text-center">المتأخرة</th>
                      <th className="py-2 px-3 font-semibold text-center">نقاط الشهر</th>
                      <th className="py-2 px-3 font-semibold text-center">آخر نشاط</th>
                      <th className="py-2 px-3 font-semibold text-center">الإجراء</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {teamCards.map((c) => (
                      <tr key={c.id} className="hover:bg-[var(--color-surface-2)]">
                        <td className="py-2.5 px-3 font-bold text-[var(--color-text)]">
                          {c.name}
                        </td>
                        <td className="py-2.5 px-3 text-[var(--color-text-muted)]">
                          {c.job_title || "—"}
                        </td>
                        <td className="py-2.5 px-3 text-center font-semibold">
                          {formatNumber(c.open_tasks)}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span
                            className={`font-bold ${
                              c.overdue_tasks > 0 ? "text-rose-600" : "text-[var(--color-text-muted)]"
                            }`}
                          >
                            {formatNumber(c.overdue_tasks)}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-center font-bold text-emerald-600 dark:text-emerald-400">
                          {formatNumber(c.month_points)}
                        </td>
                        <td className="py-2.5 px-3 text-center text-[var(--color-text-muted)]">
                          {c.last_activity ? formatDateTimeValue(c.last_activity) : "—"}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <button
                            type="button"
                            onClick={() => setSelectedCardEmployeeId(c.id)}
                            className="text-[var(--color-primary)] hover:underline font-semibold text-[11px]"
                          >
                            عرض الكرت
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* قائمة مهام الموظف لليوم (تملأ الشاشة) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[var(--color-text)]">
            مهامي المجدولة ({activeDailyTasks.length})
          </h2>
          <span className="text-xs text-[var(--color-text-muted)]">
            مرتبة: المتأخرة أولاً ثم المستحقة اليوم ثم الباقي
          </span>
        </div>

        {loadingTasks ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-[var(--color-primary)]" />
          </div>
        ) : activeDailyTasks.length === 0 ? (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center">
            <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto mb-2 opacity-80" />
            <h3 className="text-sm font-bold text-[var(--color-text)]">
              لا توجد مهام نشطة بانتظارك اليوم!
            </h3>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              جميع مهامك منجزة أو مسلّمة بانتظار اعتماد المدير.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeDailyTasks.map((t) => {
              const bucket = dailyBucket(t.due_date, today);
              const isTimerRunning = t.my_assignment?.work_started_at != null;

              return (
                <div
                  key={t.id}
                  className={`rounded-xl border p-4 flex flex-col justify-between transition-all shadow-sm ${
                    bucket === "overdue"
                      ? "border-rose-300 bg-rose-50/40 dark:border-rose-900/60 dark:bg-rose-950/20"
                      : bucket === "today"
                      ? "border-amber-300 bg-amber-50/40 dark:border-amber-900/60 dark:bg-amber-950/20"
                      : "border-[var(--color-border)] bg-[var(--color-surface)]"
                  }`}
                >
                  <div className="space-y-2">
                    {/* شارات الحالة والأولوية والموعد */}
                    <div className="flex items-center justify-between gap-1 flex-wrap text-[11px]">
                      <span className={`px-2 py-0.5 rounded font-bold border ${taskPriorityBadgeClass(t.priority)}`}>
                        {taskPriorityLabel(t.priority)}
                      </span>

                      <div className="flex items-center gap-1.5">
                        {bucket === "overdue" && (
                          <span className="rounded bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300 px-2 py-0.5 font-bold">
                            متأخرة ({formatDateLocalized(t.due_date)})
                          </span>
                        )}
                        {bucket === "today" && (
                          <span className="rounded bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 px-2 py-0.5 font-bold">
                            اليوم
                          </span>
                        )}
                        {bucket === "later" && (
                          <span className="text-[var(--color-text-muted)]">
                            موعدها: {formatDateLocalized(t.due_date)}
                          </span>
                        )}
                        {bucket === "undated" && (
                          <span className="text-[var(--color-text-muted)]">بدون موعد</span>
                        )}
                      </div>
                    </div>

                    <h3 className="text-sm font-bold text-[var(--color-text)] line-clamp-2">
                      {t.title}
                    </h3>

                    {/* الحالة: «العنوان والموعد **والحالة** وزرُّ سلّم» — حالةُ
                        إسنادي أنا حين يكون لي إسناد، وإلا حالةُ المهمّة. */}
                    <span className="inline-block rounded bg-[var(--color-surface-3)] px-2 py-0.5 text-[10px] font-bold text-[var(--color-text-muted)]">
                      {t.my_assignment
                        ? assignmentStatusLabel(t.my_assignment.status)
                        : taskStatusLabel(t.status)}
                    </span>

                    {t.description && (
                      <p className="text-xs text-[var(--color-text-muted)] line-clamp-3 whitespace-pre-wrap">
                        {t.description}
                      </p>
                    )}
                  </div>

                  {/* شريط الإجراءات: المؤقت + زر سلّم */}
                  <div className="pt-3 mt-3 border-t border-[var(--color-border)] flex items-center justify-between gap-2">
                    {/* زر المؤقت */}
                    <button
                      type="button"
                      disabled={togglingTimerId === t.id}
                      onClick={() => handleToggleTimer(t)}
                      className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 rounded-lg border transition-all ${
                        isTimerRunning
                          ? "border-amber-400 bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
                          : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                      }`}
                    >
                      {togglingTimerId === t.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : isTimerRunning ? (
                        <Square className="h-3.5 w-3.5 fill-current" />
                      ) : (
                        <Play className="h-3.5 w-3.5 fill-current" />
                      )}
                      <span>{isTimerRunning ? "إيقاف المؤقت" : "بدء العمل"}</span>
                    </button>

                    {/* زر سلّم */}
                    <button
                      type="button"
                      onClick={() => setSubmitTaskTarget(t)}
                      className="rounded-lg bg-[var(--color-primary)] px-4 py-1.5 text-xs font-bold text-white hover:opacity-90 shadow-sm"
                    >
                      سلّم
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* قسمٌ مطويّ: «بانتظار موافقة المدير» */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
        <button
          type="button"
          onClick={() => setPendingApprovalCollapsed(!pendingApprovalCollapsed)}
          className="flex items-center justify-between w-full p-3.5 text-right font-bold text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-2)] transition-all"
        >
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-500" />
            <span>بانتظار موافقة المدير ({pendingApprovalTasks.length})</span>
          </div>
          {pendingApprovalCollapsed ? (
            <ChevronDown className="h-4 w-4 text-[var(--color-text-muted)]" />
          ) : (
            <ChevronUp className="h-4 w-4 text-[var(--color-text-muted)]" />
          )}
        </button>

        {!pendingApprovalCollapsed && (
          <div className="p-3 border-t border-[var(--color-border)] space-y-2 bg-[var(--color-surface-2)]">
            {pendingApprovalTasks.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)] text-center py-3">
                لا توجد تسليمات معلقة تنتظر موافقة المدير.
              </p>
            ) : (
              pendingApprovalTasks.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-xs"
                >
                  <div>
                    <span className="font-bold text-[var(--color-text)] block">{t.title}</span>
                    <span className="text-[11px] text-amber-600 dark:text-amber-400">
                      قيد مراجعة الإدارة • ستحصل على نقاطك فور الاعتماد
                    </span>
                  </div>
                  <span className="rounded px-2 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                    بانتظار المراجعة
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* مودال التسليم */}
      {submitTaskTarget && (
        <TaskSubmitModal
          task={submitTaskTarget}
          isOpen={Boolean(submitTaskTarget)}
          onClose={() => setSubmitTaskTarget(null)}
          onSubmitted={() => {
            void loadDailyData();
            if (canManage) void loadManagerQueue();
          }}
        />
      )}

      {/* مودال مراجعة المدير */}
      {reviewSubmissionTarget && (
        <TaskReviewModal
          submission={reviewSubmissionTarget}
          isOpen={Boolean(reviewSubmissionTarget)}
          onClose={() => setReviewSubmissionTarget(null)}
          onReviewed={() => {
            void loadDailyData();
            if (canManage) void loadManagerQueue();
          }}
        />
      )}

      {/* مودال كرت الموظف */}
      {selectedCardEmployeeId && (
        <EmployeeCardModal
          employeeId={selectedCardEmployeeId}
          isOpen={Boolean(selectedCardEmployeeId)}
          onClose={() => setSelectedCardEmployeeId(null)}
          onEmployeeChanged={() => {
            if (canManage) void loadManagerQueue();
          }}
        />
      )}
    </div>
  );
};
