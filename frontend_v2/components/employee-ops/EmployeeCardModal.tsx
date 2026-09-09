import React, { useEffect, useState } from "react";
import {
  Activity,
  FileText,
  Loader2,
  Send,
  User as UserIcon,
  X,
} from "lucide-react";
import {
  getEmployeeCard,
  listEmployeeNotes,
  createEmployeeNote,
  getEmployeeActivity,
  deactivateEmployee,
  reactivateEmployee,
  listEmployees,
  updateEmployee,
  type ActivityEventDto,
  type EmployeeCardDto,
  type EmployeeDto,
  type EmployeeNoteDto,
} from "../../services/employeeOpsApi";
import { formatDateTimeValue } from "../../utils/formatDate";
// القاموسُ العربيّ للنشاط موجودٌ في المستودع ويستعمله سجلُّ النشاط العام —
// طباعةُ `create`/`login` حرفيّاً كانت تُظهر مفرداتِ الكود للمستخدم.
import { actionMeta, entityLabel } from "../activity/activityMeta";
import { formatNumber } from "../../utils/formatNumber";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";

interface EmployeeCardModalProps {
  employeeId: number | null;
  isOpen: boolean;
  onClose: () => void;
  onEmployeeChanged?: () => void;
}

type CardTab = "details" | "notes" | "activity";

export const EmployeeCardModal: React.FC<EmployeeCardModalProps> = ({
  employeeId,
  isOpen,
  onClose,
  onEmployeeChanged,
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [activeTab, setActiveTab] = useState<CardTab>("details");
  // تحريرُ البيانات: الموظفُ القادمُ من الرواتب يُنشأ بلا مديرٍ مباشر،
  // فبلا هذا البابِ لا سبيلَ لضبطِ مديرِه ولا لتصحيحِ هاتفٍ مكتوبٍ خطأً.
  const [isEditing, setIsEditing] = useState(false);
  const [editDraft, setEditDraft] = useState<{
    name: string;
    phone: string;
    job_title: string;
    manager: string;
  } | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [colleagues, setColleagues] = useState<EmployeeDto[]>([]);
  const [card, setCard] = useState<EmployeeCardDto | null>(null);
  const [loadingCard, setLoadingCard] = useState(false);

  const startEditing = () => {
    if (!card) return;
    setEditDraft({
      name: card.name || "",
      phone: card.phone || "",
      job_title: card.job_title || "",
      manager: card.manager ? String(card.manager) : "",
    });
    setIsEditing(true);
    listEmployees()
      .then((emps) => setColleagues(emps.filter((e) => e.is_active && e.id !== card.id)))
      .catch((err: any) => toast(err?.message || "فشل تحميل قائمة المدراء", "error"));
  };

  const handleSaveEdit = async () => {
    if (!card || !editDraft) return;
    if (!editDraft.name.trim()) {
      toast("اسم الموظف مطلوب", "error");
      return;
    }
    setSavingEdit(true);
    try {
      await updateEmployee(card.id, {
        name: editDraft.name.trim(),
        phone: editDraft.phone.trim(),
        job_title: editDraft.job_title.trim(),
        manager: editDraft.manager ? Number(editDraft.manager) : null,
      });
      const refreshed = await getEmployeeCard(card.id);
      setCard(refreshed);
      setIsEditing(false);
      toast("تم حفظ بيانات الموظف", "success");
      onEmployeeChanged?.();
    } catch (err: any) {
      toast(err?.message || "فشل حفظ بيانات الموظف", "error");
    } finally {
      setSavingEdit(false);
    }
  };

  // الملاحظات
  const [notes, setNotes] = useState<EmployeeNoteDto[]>([]);
  const [loadingNotes, setLoadingNotes] = useState(false);
  const [newNoteBody, setNewNoteBody] = useState("");
  const [submittingNote, setSubmittingNote] = useState(false);

  // النشاط
  const [activities, setActivities] = useState<ActivityEventDto[]>([]);
  const [loadingActivities, setLoadingActivities] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [togglingActive, setTogglingActive] = useState(false);

  useEffect(() => {
    if (!isOpen || !employeeId) return;

    setActiveTab("details");
    setLoadingCard(true);
    getEmployeeCard(employeeId)
      .then((data) => setCard(data))
      .catch((err) => toast(err?.message || "فشل تحميل بيانات كرت الموظف", "error"))
      .finally(() => setLoadingCard(false));
  }, [isOpen, employeeId]);

  // تحميل التبويبات عند الانتقال.
  // `alive` يمنع ردَّ مدىً قديمٍ من دهسِ نتيجةِ مدىً أحدث: تغييرُ التاريخين
  // بسرعةٍ يُطلق طلبين، وسبقُ الأبطأِ يترك الشاشةَ تعرض ما لم يُطلَب.
  useEffect(() => {
    if (!isOpen || !employeeId) return;
    let alive = true;

    if (activeTab === "notes") {
      setLoadingNotes(true);
      listEmployeeNotes(employeeId)
        .then((res) => {
          if (alive) setNotes(res);
        })
        .catch((err) => {
          if (alive) toast(err?.message || "فشل تحميل الملاحظات", "error");
        })
        .finally(() => {
          if (alive) setLoadingNotes(false);
        });
    } else if (activeTab === "activity") {
      setLoadingActivities(true);
      getEmployeeActivity(employeeId, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
        .then((res) => {
          if (alive) setActivities(res.results);
        })
        .catch((err) => {
          if (alive) toast(err?.message || "فشل تحميل سجل النشاط", "error");
        })
        .finally(() => {
          if (alive) setLoadingActivities(false);
        });
    }

    return () => {
      alive = false;
    };
  }, [isOpen, employeeId, activeTab, dateFrom, dateTo, toast]);

  if (!isOpen || !employeeId) return null;

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNoteBody.trim()) {
      toast("نص الملاحظة مطلوب", "error");
      return;
    }

    setSubmittingNote(true);
    try {
      const added = await createEmployeeNote(employeeId, newNoteBody.trim());
      setNotes((prev) => [added, ...prev]);
      setNewNoteBody("");
      toast("تمت إضافة الملاحظة بنجاح", "success");
    } catch (err: any) {
      toast(err?.message || "فشل إضافة الملاحظة", "error");
    } finally {
      setSubmittingNote(false);
    }
  };

  const handleToggleActive = async () => {
    if (!card) return;
    const willDeactivate = card.is_active;
    const ok = await confirm({
      title: willDeactivate ? "تأكيد تعطيل الموظف" : "تأكيد إعادة تفعيل الموظف",
      message: willDeactivate
        ? `هل أنت متأكد من رغبتك في تعطيل الموظف (${card.name})؟ لن يتمكن من تسجيل الدخول وسيبقى تاريخه وسجلاته محفوظة.`
        : `هل أنت متأكد من إعادة تفعيل سجل الموظف (${card.name})؟`,
      confirmText: willDeactivate ? "تعطيل" : "إعادة تفعيل",
      danger: willDeactivate,
    });
    if (!ok) return;

    setTogglingActive(true);
    try {
      if (willDeactivate) {
        await deactivateEmployee(card.id);
        toast("تم تعطيل الموظف بنجاح", "success");
      } else {
        await reactivateEmployee(card.id);
        toast("تمت إعادة تفعيل الموظف بنجاح", "success");
      }
      const updated = await getEmployeeCard(card.id);
      setCard(updated);
      onEmployeeChanged?.();
    } catch (err: any) {
      toast(err?.message || "فشل تغيير حالة الموظف", "error");
    } finally {
      setTogglingActive(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
              <UserIcon className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-[var(--color-text)]">
                {card?.name || "كرت الموظف"}
              </h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                {card?.job_title || "بدون مسمى"} {card?.code ? `• كود: ${card.code}` : ""}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Counters Header (طلب واحد يجمع 3 عدادات) */}
        {card && (
          <div className="grid grid-cols-3 gap-2 mb-4 p-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] text-center text-xs">
            <div>
              <span className="text-[var(--color-text-muted)] block text-[11px]">المهام المفتوحة</span>
              <span className="font-bold text-[var(--color-text)] text-sm">
                {formatNumber(card.open_tasks)}
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)] block text-[11px]">المهام المتأخرة</span>
              <span className={`font-bold text-sm ${card.overdue_tasks > 0 ? "text-rose-600" : "text-[var(--color-text)]"}`}>
                {formatNumber(card.overdue_tasks)}
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)] block text-[11px]">نقاط هذا الشهر</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400 text-sm">
                {formatNumber(card.month_points)}
              </span>
            </div>
          </div>
        )}

        {/* Tab Switcher */}
        <div className="flex border-b border-[var(--color-border)] mb-4 gap-1">
          <button
            type="button"
            onClick={() => setActiveTab("details")}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold border-b-2 transition-all ${
              activeTab === "details"
                ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            <UserIcon className="h-3.5 w-3.5" /> بياناته
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("notes")}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold border-b-2 transition-all ${
              activeTab === "notes"
                ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            <FileText className="h-3.5 w-3.5" /> ملاحظاتٌ عليه
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("activity")}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold border-b-2 transition-all ${
              activeTab === "activity"
                ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            <Activity className="h-3.5 w-3.5" /> نشاطُه في المنصة
          </button>
        </div>

        {/* Tab 1: Details */}
        {activeTab === "details" && (
          <div className="flex-1 overflow-y-auto space-y-4 text-xs">
            {loadingCard ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-[var(--color-primary)]" />
              </div>
            ) : card && isEditing && editDraft ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block font-semibold text-[var(--color-text)]">الاسم</label>
                    <input
                      type="text"
                      value={editDraft.name}
                      onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })}
                      className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block font-semibold text-[var(--color-text)]">رقم الهاتف</label>
                    <input
                      type="text"
                      value={editDraft.phone}
                      onChange={(e) => setEditDraft({ ...editDraft, phone: e.target.value })}
                      className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block font-semibold text-[var(--color-text)]">المسمى الوظيفي</label>
                    <input
                      type="text"
                      value={editDraft.job_title}
                      onChange={(e) => setEditDraft({ ...editDraft, job_title: e.target.value })}
                      className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block font-semibold text-[var(--color-text)]">المدير المباشر</label>
                    <select
                      value={editDraft.manager}
                      onChange={(e) => setEditDraft({ ...editDraft, manager: e.target.value })}
                      className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
                    >
                      <option value="">بدون مدير مباشر</option>
                      {colleagues.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] pt-3">
                  <button
                    type="button"
                    onClick={() => setIsEditing(false)}
                    className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 font-semibold text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                  >
                    إلغاء
                  </button>
                  <button
                    type="button"
                    disabled={savingEdit}
                    onClick={handleSaveEdit}
                    className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 py-1.5 font-bold text-white hover:opacity-90 disabled:opacity-60"
                  >
                    {savingEdit && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    حفظ البيانات
                  </button>
                </div>
              </div>
            ) : card ? (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)]">
                  <div>
                    <span className="text-[var(--color-text-muted)] block mb-0.5">رقم الهاتف</span>
                    <span className="font-semibold text-[var(--color-text)]">{card.phone || "—"}</span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)] block mb-0.5">المدير المباشر</span>
                    <span className="font-semibold text-[var(--color-text)]">{card.manager_name || "—"}</span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)] block mb-0.5">حساب المنصة</span>
                    <span className="font-semibold text-[var(--color-text)]">
                      {card.has_account ? (
                        <span className="text-emerald-600 font-bold">يملك حساب دخول</span>
                      ) : (
                        <span className="text-amber-600">
                          {card.invitation_status === "pending" ? "تمت دعوته بانتظار القبول" : "بدون حساب"}
                        </span>
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)] block mb-0.5">حالة السجل</span>
                    <span
                      className={`inline-block px-2 py-0.5 rounded font-bold text-[10px] ${
                        card.is_active ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                      }`}
                    >
                      {card.is_active ? "نشط" : "معطل"}
                    </span>
                  </div>
                </div>

                {/* أزرار الإجراءات السريعة */}
                <div className="pt-2 border-t border-[var(--color-border)] flex items-center justify-between">
                  <span className="text-xs text-[var(--color-text-muted)]">إدارة الموظف:</span>
                  <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={startEditing}
                    className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-bold text-[var(--color-primary)] hover:bg-[var(--color-surface-2)]"
                  >
                    تعديل البيانات
                  </button>
                  <button
                    type="button"
                    disabled={togglingActive}
                    onClick={handleToggleActive}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                      card.is_active
                        ? "border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:hover:bg-rose-950/30"
                        : "bg-emerald-600 text-white hover:bg-emerald-700"
                    }`}
                  >
                    {togglingActive ? "جاري المعالجة..." : card.is_active ? "تعطيل الموظف" : "إعادة تفعيل الموظف"}
                  </button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}

        {/* Tab 2: Notes (تُكتب ولا تُعدّل ولا تُحذف) */}
        {activeTab === "notes" && (
          <div className="flex-1 overflow-y-auto space-y-4 flex flex-col">
            {/* إضافة ملاحظة جديدة */}
            <form onSubmit={handleAddNote} className="space-y-2">
              <label className="block text-xs font-semibold text-[var(--color-text)]">
                كتابة ملاحظة جديدة عن الموظف (الملاحظة تُحفظ دليلاً ولا تُعدَّل ولا تُحذف)
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newNoteBody}
                  onChange={(e) => setNewNoteBody(e.target.value)}
                  placeholder="اكتب ملاحظة توثيقية حول أداء الموظف أو سلوكه..."
                  className="h-10 flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                />
                <button
                  type="submit"
                  disabled={submittingNote || !newNoteBody.trim()}
                  className="flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {submittingNote ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  حفظ
                </button>
              </div>
            </form>

            {/* قائمة الملاحظات */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {loadingNotes ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-[var(--color-primary)]" />
                </div>
              ) : notes.length === 0 ? (
                <p className="text-xs text-[var(--color-text-muted)] text-center py-8">
                  لا توجد ملاحظات مسجلة على هذا الموظف بعد.
                </p>
              ) : (
                notes.map((note) => (
                  <div
                    key={note.id}
                    className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 space-y-1 text-xs"
                  >
                    <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)] border-b border-[var(--color-border)] pb-1 mb-1">
                      <span className="font-semibold text-[var(--color-text)]">
                        {note.author_name || "كاتب مجهول"}
                      </span>
                      <span>{formatDateTimeValue(note.created_at)}</span>
                    </div>
                    <p className="text-[var(--color-text)] whitespace-pre-wrap leading-relaxed">
                      {note.body}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Activity Log */}
        {activeTab === "activity" && (
          <div className="flex-1 overflow-y-auto space-y-3 flex flex-col">
            {/* فلتر المدى الزمني */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[var(--color-text-muted)]">من:</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 text-xs text-[var(--color-text)]"
              />
              <span className="text-[var(--color-text-muted)]">إلى:</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 text-xs text-[var(--color-text)]"
              />
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {loadingActivities ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-[var(--color-primary)]" />
                </div>
              ) : !card?.has_account ? (
                <p className="text-xs text-[var(--color-text-muted)] text-center py-8">
                  هذا الموظف ليس لديه حساب دخول للمنصة بعد، لذا لا يوجد سجل نشاط مسجل.
                </p>
              ) : activities.length === 0 ? (
                <p className="text-xs text-[var(--color-text-muted)] text-center py-8">
                  لا يوجد نشاط مسجل للموظف في هذه الفترة.
                </p>
              ) : (
                activities.map((act) => (
                  <div
                    key={act.id}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-xs flex items-center justify-between"
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${actionMeta(act.action).badge}`}
                      >
                        {actionMeta(act.action).label}
                      </span>
                      <span className="text-[var(--color-text-muted)]">
                        {act.entity_label ||
                          act.description ||
                          entityLabel(act.entity_type)}
                      </span>
                    </div>
                    <span className="text-[10px] text-[var(--color-text-muted)] flex-shrink-0">
                      {formatDateTimeValue(act.timestamp)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
