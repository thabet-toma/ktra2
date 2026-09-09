import React, { useEffect, useState } from "react";
import { Loader2, X, Check } from "lucide-react";
import {
  createTask,
  updateTask,
  listEmployees,
  type CreateTaskDto,
  type EmployeeDto,
  type TaskDto,
} from "../../services/employeeOpsApi";
import { useToast } from "../../contexts/ToastContext";

interface TaskFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  taskToEdit?: TaskDto | null;
  onSaved: (task: TaskDto) => void;
}

export const TaskFormModal: React.FC<TaskFormModalProps> = ({
  isOpen,
  onClose,
  taskToEdit,
  onSaved,
}) => {
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<"LOW" | "MEDIUM" | "HIGH" | "URGENT">("MEDIUM");
  const [dueDate, setDueDate] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [assigneeIds, setAssigneeIds] = useState<number[]>([]);

  const [employees, setEmployees] = useState<EmployeeDto[]>([]);
  const [loadingEmployees, setLoadingEmployees] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    if (taskToEdit) {
      setTitle(taskToEdit.title);
      setDescription(taskToEdit.description || "");
      setPriority(taskToEdit.priority || "MEDIUM");
      setDueDate(taskToEdit.due_date ? taskToEdit.due_date.slice(0, 10) : "");
      setTargetPrice(taskToEdit.target_price ? String(taskToEdit.target_price) : "");
      setAssigneeIds(taskToEdit.assignments.map((a) => a.employee));
    } else {
      setTitle("");
      setDescription("");
      setPriority("MEDIUM");
      setDueDate("");
      setTargetPrice("");
      setAssigneeIds([]);
    }

    setLoadingEmployees(true);
    listEmployees()
      .then((emps) => {
        setEmployees(emps.filter((e) => e.is_active));
      })
      .catch((err) => {
        toast(err?.message || "فشل تحميل قائمة الموظفين", "error");
      })
      .finally(() => setLoadingEmployees(false));
  }, [isOpen, taskToEdit]);

  if (!isOpen) return null;

  const toggleAssignee = (empId: number) => {
    setAssigneeIds((prev) =>
      prev.includes(empId) ? prev.filter((id) => id !== empId) : [...prev, empId],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      toast("عنوان المهمة مطلوب", "error");
      return;
    }

    setSaving(true);
    try {
      const payload: CreateTaskDto = {
        title: title.trim(),
        description: description.trim(),
        priority,
        due_date: dueDate.trim() ? dueDate.trim() : null,
        target_price: targetPrice ? Number(targetPrice) : null,
        assignee_ids: assigneeIds,
      };

      let saved: TaskDto;
      if (taskToEdit) {
        saved = await updateTask(taskToEdit.id, payload);
        toast("تم تعديل المهمة بنجاح", "success");
      } else {
        saved = await createTask(payload);
        toast("تم إنشاء المهمة بنجاح", "success");
      }

      onSaved(saved);
      onClose();
    } catch (err: any) {
      toast(err?.message || "فشل حفظ المهمة", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="relative w-full max-w-xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
          <h2 className="text-lg font-bold text-[var(--color-text)]">
            {taskToEdit ? "تعديل المهمة" : "إنشاء مهمة جديدة"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto space-y-4 pr-1">
          <div>
            <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
              عنوان المهمة <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="مثال: فحص جرد مستودع الزيوت، تحضير طلبية..."
              className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-sm text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
              تفاصيل ووصف المهمة
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="شرح المطلوب بالتفصيل..."
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                الأولوية
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as any)}
                className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-sm text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
              >
                <option value="LOW">منخفضة</option>
                <option value="MEDIUM">متوسطة</option>
                <option value="HIGH">عالية</option>
                <option value="URGENT">حرجة</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                الموعد النهائي (تاريخ الاستحقاق)
              </label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-sm text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
              السعر المستهدف (اختياري)
            </label>
            <input
              type="number"
              step="0.01"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder="0.00"
              className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-sm text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            />
          </div>

          {/* إسناد الموظفين (متعدد) */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
            <label className="mb-2 block text-xs font-semibold text-[var(--color-text)]">
              إسناد المهمة للموظفين (يمكن اختيار أكثر من موظف)
            </label>

            {loadingEmployees ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] py-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> جاري تحميل الموظفين...
              </div>
            ) : employees.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)] py-1">لا يوجد موظفون نشطون مسجلون.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
                {employees.map((emp) => {
                  const selected = assigneeIds.includes(emp.id);
                  return (
                    <button
                      key={emp.id}
                      type="button"
                      onClick={() => toggleAssignee(emp.id)}
                      className={`flex items-center justify-between p-2 rounded-lg border text-right transition-all ${
                        selected
                          ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)] font-semibold"
                          : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] hover:bg-[var(--color-surface-3)]"
                      }`}
                    >
                      <div className="truncate">
                        <div className="text-xs">{emp.name}</div>
                        {emp.job_title && (
                          <div className="text-[10px] text-[var(--color-text-muted)] truncate">
                            {emp.job_title}
                          </div>
                        )}
                      </div>
                      {selected && <Check className="h-4 w-4 flex-shrink-0" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--color-border)]">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
            >
              إلغاء
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-5 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {taskToEdit ? "حفظ التعديلات" : "إنشاء المهمة"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
