import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import {
  deleteTask,
  getTask,
  listMyTasks,
  listSubmissions,
  listTasks,
  type TaskDto,
  type TaskSubmissionDto,
} from "../../services/employeeOpsApi";
import {
  assignmentStatusLabel,
  employeeOpsNavLabels,
  submissionDecisionLabel,
  taskPriorityBadgeClass,
  taskPriorityLabel,
  taskStatusLabel,
} from "../../utils/employeeOps";
import { formatDateLocalized, formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { TaskFormModal } from "./TaskFormModal";
import { TaskSubmitModal } from "./TaskSubmitModal";
import { TaskReviewModal } from "./TaskReviewModal";

export const EmployeeOpsTasksScreen: React.FC = () => {
  const { can } = usePermissions();
  const canManage = can("employee_ops.manage");
  const navLabels = employeeOpsNavLabels(canManage);
  const toast = useToast();
  const confirm = useConfirm();

  const [tasks, setTasks] = useState<TaskDto[]>([]);
  const [loading, setLoading] = useState(true);

  // الفلاتر والبحث
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("");

  // نوافذ التفاعل
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [taskToEdit, setTaskToEdit] = useState<TaskDto | null>(null);
  const [activeTaskDetails, setActiveTaskDetails] = useState<TaskDto | null>(null);
  const [taskSubmissions, setTaskSubmissions] = useState<TaskSubmissionDto[]>([]);
  const [loadingSubmissions, setLoadingSubmissions] = useState(false);

  // مودال تسليم المهمة
  const [submitTaskTarget, setSubmitTaskTarget] = useState<TaskDto | null>(null);
  // مودال مراجعة التسليم للمدير
  const [reviewSubmissionTarget, setReviewSubmissionTarget] = useState<TaskSubmissionDto | null>(null);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = canManage ? await listTasks() : await listMyTasks();
      setTasks(data);
    } catch (err: any) {
      toast(err?.message || "فشل تحميل المهام", "error");
    } finally {
      setLoading(false);
    }
  }, [canManage, toast]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  // آخرُ مهمّةٍ طُلبت تفاصيلُها — ردُّ الأبطأِ لا يدهس شاشةَ الأحدث.
  const detailsRequestRef = useRef(0);

  // فتح تفاصيل المهمة وجلب تسليماتها
  const handleOpenTaskDetails = async (task: TaskDto) => {
    setActiveTaskDetails(task);
    const token = ++detailsRequestRef.current;
    setLoadingSubmissions(true);
    try {
      const freshTask = await getTask(task.id);
      if (token !== detailsRequestRef.current) return;
      setActiveTaskDetails(freshTask);

      // الفلترةُ في الخادم: كان يُنزل سجلَّ تسليمات الشركة كلَّه لفتحِ مهمّة.
      const subs = await listSubmissions({ task: task.id });
      if (token !== detailsRequestRef.current) return;
      setTaskSubmissions(subs);
    } catch (err: any) {
      if (token === detailsRequestRef.current) {
        toast(err?.message || "فشل تحميل تفاصيل المهمة والتسليمات", "error");
      }
    } finally {
      if (token === detailsRequestRef.current) setLoadingSubmissions(false);
    }
  };

  const handleDeleteTask = async (task: TaskDto) => {
    const ok = await confirm({
      title: "تأكيد حذف المهمة",
      message: `هل أنت متأكد من حذف المهمة "${task.title}"؟ لا يمكن حذف مهمة لها تسليمات مسبقة.`,
      confirmText: "حذف",
      danger: true,
    });
    if (!ok) return;

    try {
      await deleteTask(task.id);
      toast("تم حذف المهمة بنجاح", "success");
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
      if (activeTaskDetails?.id === task.id) {
        setActiveTaskDetails(null);
      }
    } catch (err: any) {
      toast(err?.message || "فشل حذف المهمة", "error");
    }
  };

  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      if (statusFilter && t.status !== statusFilter) return false;
      if (priorityFilter && t.priority !== priorityFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesTitle = t.title.toLowerCase().includes(q);
        const matchesDesc = (t.description || "").toLowerCase().includes(q);
        const matchesAssignee = t.assignments.some((a) =>
          a.employee_name.toLowerCase().includes(q),
        );
        if (!matchesTitle && !matchesDesc && !matchesAssignee) return false;
      }
      return true;
    });
  }, [tasks, statusFilter, priorityFilter, searchQuery]);

  return (
    <div className="space-y-4 p-4 md:p-6 max-w-7xl mx-auto">
      {/* شريط العنوان وزر المهمة الجديدة */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div>
          <h1 className="text-lg font-bold text-[var(--color-text)]">
            {navLabels.tasks}
          </h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
            {canManage
              ? "متابعة وإسناد جميع مهام الشركة ومراجعة تسليمات الموظفين"
              : "قائمة المهام المسندة إليك وتسليم إنجازك"}
          </p>
        </div>

        {canManage && (
          <button
            type="button"
            onClick={() => {
              setTaskToEdit(null);
              setIsCreateModalOpen(true);
            }}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white hover:opacity-90 shadow-sm"
          >
            <Plus className="h-4 w-4" /> مهمة جديدة
          </button>
        )}
      </div>

      {/* الفلاتر والبحث */}
      <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute right-3 top-2.5 h-4 w-4 text-[var(--color-text-muted)]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="بحث بالعنوان، الوصف، أو الموظف المسند..."
            className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] pr-9 pl-3 text-xs text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)] outline-none"
        >
          <option value="">كل الحالات</option>
          <option value="NEW">جديدة</option>
          <option value="IN_PROGRESS">قيد التنفيذ</option>
          <option value="WAITING_FOR_REVIEW">بانتظار المراجعة</option>
          <option value="COMPLETED">مكتملة</option>
          <option value="REJECTED">مرفوضة</option>
        </select>

        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)] outline-none"
        >
          <option value="">كل الأولويات</option>
          <option value="URGENT">حرجة</option>
          <option value="HIGH">عالية</option>
          <option value="MEDIUM">متوسطة</option>
          <option value="LOW">منخفضة</option>
        </select>
      </div>

      {/* جدول / قائمة المهام */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--color-primary)]" />
        </div>
      ) : filteredTasks.length === 0 ? (
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center text-xs text-[var(--color-text-muted)]">
          لا توجد مهام تطابق البحث والفلاتر المحددة.
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
                  <th className="py-2.5 px-3 font-semibold">عنوان المهمة</th>
                  <th className="py-2.5 px-3 font-semibold text-center">الأولوية</th>
                  <th className="py-2.5 px-3 font-semibold text-center">الحالة</th>
                  <th className="py-2.5 px-3 font-semibold">الموعد النهائي</th>
                  <th className="py-2.5 px-3 font-semibold">المسند إليهم</th>
                  <th className="py-2.5 px-3 font-semibold text-center">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {filteredTasks.map((t) => (
                  <tr key={t.id} className="hover:bg-[var(--color-surface-2)] transition-colors">
                    <td className="py-3 px-3 font-bold text-[var(--color-text)] max-w-xs truncate">
                      <button
                        type="button"
                        onClick={() => handleOpenTaskDetails(t)}
                        className="text-right hover:text-[var(--color-primary)] hover:underline"
                      >
                        {t.title}
                      </button>
                    </td>

                    <td className="py-3 px-3 text-center">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border ${taskPriorityBadgeClass(
                          t.priority,
                        )}`}
                      >
                        {taskPriorityLabel(t.priority)}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-[var(--color-surface-3)] text-[var(--color-text)]">
                        {taskStatusLabel(t.status)}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-[var(--color-text-muted)]">
                      {formatDateLocalized(t.due_date) || "—"}
                    </td>

                    <td className="py-3 px-3">
                      {t.assignments.length === 0 ? (
                        <span className="text-[var(--color-text-muted)]">بدون إسناد</span>
                      ) : (
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {t.assignments.map((a) => (
                            <span
                              key={a.id}
                              className="rounded bg-[var(--color-surface-3)] px-1.5 py-0.5 text-[10px] text-[var(--color-text)]"
                            >
                              {a.employee_name}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>

                    <td className="py-3 px-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleOpenTaskDetails(t)}
                          className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary)] hover:bg-[var(--color-surface-3)]"
                        >
                          عرض التفاصيل
                        </button>

                        {/* بإسنادي أنا: `canManage` ليست الشرط — مديرٌ مُسنَدةٌ إليه
                            مهمّةٌ يسلّمها، وموظفٌ سلّم بالفعل لا يُعرض له زرٌّ
                            يردّه الخادمُ بـ«لا تسليمَ ثانٍ ينتظر بجانب أوّل».
                            والمديرُ يقرأ عبر `listTasks` فيأتي `my_assignment`
                            فارغاً، فلا يظهر له الزرُّ على ما ليس إسناداً له. */}
                        {t.my_assignment &&
                          t.my_assignment.status !== "submitted" &&
                          t.my_assignment.status !== "completed" &&
                          t.status !== "COMPLETED" && (
                          <button
                            type="button"
                            onClick={() => setSubmitTaskTarget(t)}
                            className="rounded-md bg-[var(--color-primary)] px-2.5 py-1 text-[11px] font-bold text-white hover:opacity-90"
                          >
                            سلّم
                          </button>
                        )}

                        {canManage && (
                          <button
                            type="button"
                            onClick={() => {
                              setTaskToEdit(t);
                              setIsCreateModalOpen(true);
                            }}
                            title="تعديل المهمة"
                            className="text-[var(--color-text-muted)] hover:text-[var(--color-primary)] p-1"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                        )}

                        {canManage && (
                          <button
                            type="button"
                            onClick={() => handleDeleteTask(t)}
                            title="حذف المهمة"
                            className="text-red-500 hover:text-red-700 p-1"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* نافذة تفاصيل المهمة وإسناداتها وتسليماتها */}
      {activeTaskDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
              <div>
                <h2 className="text-base font-bold text-[var(--color-text)]">
                  {activeTaskDetails.title}
                </h2>
                <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] mt-1">
                  <span>الأولوية: {taskPriorityLabel(activeTaskDetails.priority)}</span>
                  <span>•</span>
                  <span>الحالة: {taskStatusLabel(activeTaskDetails.status)}</span>
                  {activeTaskDetails.due_date && (
                    <>
                      <span>•</span>
                      <span>الموعد: {formatDateLocalized(activeTaskDetails.due_date)}</span>
                    </>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTaskDetails(null)}
                className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-xs">
              {/* الوصف */}
              {activeTaskDetails.description && (
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
                  <span className="font-bold text-[var(--color-text)] block mb-1">وصف المهمة:</span>
                  <p className="text-[var(--color-text)] whitespace-pre-wrap leading-relaxed">
                    {activeTaskDetails.description}
                  </p>
                </div>
              )}

              {/* إسنادات المهمة */}
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
                <span className="font-bold text-[var(--color-text)] block mb-2">
                  الموظفون المسندة إليهم ({activeTaskDetails.assignments.length})
                </span>
                {activeTaskDetails.assignments.length === 0 ? (
                  <p className="text-[var(--color-text-muted)]">لم تسند هذه المهمة لأحد بعد.</p>
                ) : (
                  <div className="space-y-1.5">
                    {activeTaskDetails.assignments.map((a) => (
                      <div
                        key={a.id}
                        className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
                      >
                        <div>
                          <span className="font-bold text-[var(--color-text)]">{a.employee_name}</span>
                          <span className="text-[11px] text-[var(--color-text-muted)] mr-2">
                            حالة الإسناد: {assignmentStatusLabel(a.status)}
                          </span>
                        </div>
                        <span className="text-[11px] text-[var(--color-text-muted)]">
                          وقت العمل: {formatNumber(Math.round(a.total_work_seconds / 60))} دقيقة
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* تسليمات المهمة ومراجعتها */}
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-[var(--color-text)]">
                    التسليمات الواردة ({taskSubmissions.length})
                  </span>
                  {/* نفسُ محدِّد صفِّ القائمة: `canManage` ليست الشرط، والإسنادُ هو. */}
                  {activeTaskDetails.my_assignment &&
                    activeTaskDetails.my_assignment.status !== "submitted" &&
                    activeTaskDetails.my_assignment.status !== "completed" &&
                    activeTaskDetails.status !== "COMPLETED" && (
                    <button
                      type="button"
                      onClick={() => setSubmitTaskTarget(activeTaskDetails)}
                      className="rounded bg-[var(--color-primary)] px-2.5 py-1 text-xs font-bold text-white hover:opacity-90"
                    >
                      تسليم جديد
                    </button>
                  )}
                </div>

                {loadingSubmissions ? (
                  <div className="flex justify-center py-4">
                    <Loader2 className="h-4 w-4 animate-spin text-[var(--color-primary)]" />
                  </div>
                ) : taskSubmissions.length === 0 ? (
                  <p className="text-[var(--color-text-muted)] py-2">لا توجد تسليمات مسجلة على هذه المهمة بعد.</p>
                ) : (
                  <div className="space-y-2">
                    {taskSubmissions.map((sub) => (
                      <div
                        key={sub.id}
                        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 space-y-2"
                      >
                        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-1.5">
                          <span className="font-bold text-[var(--color-text)]">
                            {sub.employee_name}
                          </span>
                          <span className="text-[11px] text-[var(--color-text-muted)]">
                            {formatDateTimeValue(sub.created_at)}
                          </span>
                        </div>

                        {sub.body && (
                          <p className="text-[var(--color-text)] whitespace-pre-wrap">{sub.body}</p>
                        )}

                        {/* سببُ القرار يقرؤه صاحبُ التسليم لا المديرُ وحده —
                            «مرفوض» بلا سببٍ يترك الموظفَ يخمّن ما يصلحه. */}
                        {sub.reviewer_notes && (
                          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
                            <span className="text-[11px] font-bold text-[var(--color-text-muted)]">
                              ملاحظات المراجع:{" "}
                            </span>
                            <span className="text-[11px] text-[var(--color-text)] whitespace-pre-wrap">
                              {sub.reviewer_notes}
                            </span>
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-1 text-[11px]">
                          <div>
                            <span className="text-[var(--color-text-muted)]">القرار: </span>
                            <span className="font-bold text-[var(--color-text)]">
                              {/* بلا أرقامٍ مثبَّتة: قيمةُ النقطة إعدادٌ لكلّ شركة،
                                  وشاشةٌ تَعِد بعشرٍ بينما الدفتر يقيّد عشرين تكذب. */}
                              {submissionDecisionLabel(sub.decision)}
                            </span>
                          </div>

                          {canManage && (
                            <button
                              type="button"
                              onClick={() => setReviewSubmissionTarget(sub)}
                              className="rounded border border-[var(--color-primary)] px-2 py-1 text-[11px] font-bold text-[var(--color-primary)] hover:bg-[var(--color-primary)]/10"
                            >
                              {sub.decision === "pending" ? "مراجعة واعتماد" : "تعديل المراجعة"}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* مودال إنشاء المهمة */}
      {isCreateModalOpen && (
        <TaskFormModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          taskToEdit={taskToEdit}
          onSaved={() => void loadTasks()}
        />
      )}

      {/* مودال التسليم */}
      {submitTaskTarget && (
        <TaskSubmitModal
          task={submitTaskTarget}
          isOpen={Boolean(submitTaskTarget)}
          onClose={() => setSubmitTaskTarget(null)}
          onSubmitted={() => {
            void loadTasks();
            if (activeTaskDetails) void handleOpenTaskDetails(activeTaskDetails);
          }}
        />
      )}

      {/* مودال المراجعة */}
      {reviewSubmissionTarget && (
        <TaskReviewModal
          submission={reviewSubmissionTarget}
          isOpen={Boolean(reviewSubmissionTarget)}
          onClose={() => setReviewSubmissionTarget(null)}
          onReviewed={() => {
            void loadTasks();
            if (activeTaskDetails) void handleOpenTaskDetails(activeTaskDetails);
          }}
        />
      )}
    </div>
  );
};
