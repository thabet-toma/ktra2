import React, { useCallback, useEffect, useState } from "react";
import { Camera, Loader2, Pencil, Phone, X } from "lucide-react";

import {
  EMPLOYEE_STATUS_LABEL,
  PERFORMANCE_AXES,
  PERFORMANCE_AXIS_LABELS,
  getEmployeePerformance,
  getPlatformEmployee,
  setEmployeeProfileCard,
  uploadEmployeePhoto,
  type EmployeePerformance,
  type PlatformEmployeeRow,
} from "../../services/platformEmployeeProfileApi";
import { getEmployeeTargets, type EmployeeTargets } from "../../services/platformEmployeeTargetsApi";
import {
  getEmployeePilotPerformance,
  getEmployeeWallet,
  WALLET_LINE_STATUS_LABEL,
  type AcquisitionCommissionLineRow,
  type EmployeePilotPerformance,
  type EmployeeSalaryLineRow,
  type EmployeeWalletSummary,
  type WalletLineStatus,
} from "../../services/platformPilotApi";
import { getEmployeeActivity, type PlatformActivityLog } from "../../services/platformOpsApi";
import {
  createPlatformTask,
  listPlatformTaskAssignments,
  type PlatformTaskAssignment,
  type PlatformTaskPriority,
} from "../../services/platformTasksApi";
import {
  createPlatformEmployeeNote,
  listPlatformEmployeeNotes,
  type PlatformEmployeeNote,
  type PlatformEmployeeNoteVisibility,
} from "../../services/platformTasksApi";
import { PilotAxesTable } from "./PilotAxesTable";
import { useAuth } from "../../contexts/AuthContext";
import { usePlatformStaffCapabilitiesState } from "../../hooks/usePlatformStaffCapabilities";
import { useToast } from "../../contexts/ToastContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { CcAvatar } from "./ui/CcAvatar";
import { CcCard } from "./ui/CcCard";
import { CcEmpty } from "./ui/CcEmpty";
import { CcGauge } from "./ui/CcGauge";
import { CcPill } from "./ui/CcPill";
import { CcStatTile } from "./ui/CcStatTile";
import { CcTable, CcTd, CcTh, CcThead, CcTr } from "./ui/CcTable";
import { CcTabs } from "./ui/CcTabs";

type ProfileTab = "general" | "performance" | "tasks" | "wallet" | "notes" | "activity";

const TABS: { key: ProfileTab; label: string }[] = [
  { key: "general", label: "عام" },
  { key: "performance", label: "الأداء" },
  { key: "tasks", label: "المهامّ" },
  { key: "wallet", label: "المحفظة" },
  { key: "notes", label: "الملاحظات" },
  { key: "activity", label: "النشاط" },
];

type WalletLine = EmployeeSalaryLineRow | AcquisitionCommissionLineRow;
const isCommissionLine = (line: WalletLine): line is AcquisitionCommissionLineRow => "acquisition" in line;

/**
 * لونُ سطر المحفظة بحسب حالته — **ستُّ حالاتٍ لا اثنتان**. كان اللونُ
 * `pending ? أصفر : أخضر`، فيظهر السطرُ **المعكوس** (المُلغى) بأخضر المصروف:
 * مبلغٌ سُحب من الموظّف يُقرأ مالاً في يده.
 */
const WALLET_STATUS_CLASS: Record<WalletLineStatus, string> = {
  pending: "bg-amber-500/20 text-amber-300 border border-amber-500/30",
  eligible: "bg-amber-500/20 text-amber-300 border border-amber-500/30",
  approved: "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30",
  payable: "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30",
  paid: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30",
  reversed: "bg-rose-500/20 text-rose-300 border border-rose-500/30 line-through",
};

const now = new Date();

interface EmployeeProfileDrawerProps {
  employeeId: number;
  employeeName: string;
  onClose: () => void;
  /** يُستدعى بعد تعديل ناجحٍ للبطاقة — يتيح لمن يستضيف الدرج تحديثَ قوائمه هو. */
  onSaved?: () => void;
  /**
   * التبويبُ الذي يُفتَح عليه الدرج (212-O1).
   *
   * «أسند مهمّة لهذا الشخص» فعلٌ واحد؛ ولو فُتح الدرجُ على «عام» دائماً لصار
   * الفعلُ نقرتين وبحثاً عن التبويب — وهو بعينه ما شكا منه المالك في النموذج
   * المركزيّ ذي القائمة المنسدلة.
   */
  initialTab?: ProfileTab;
}

/**
 * ملفُّ الموظّف الـ360 (التذكرة 211-J): درجٌ يُفتح بمعرّف موظّف، رأسُه بطاقتُه
 * الشخصيّة (211-Q)، وتبويباتُه الأربعة تحمّل بياناتِها عند فتحها لا قبله — نداءٌ
 * واحدٌ لكلّ تبويبٍ لا خمسةٌ عند أوّل نقرة.
 *
 * **لا رقمَ يُشتقّ هنا**: كلُّ ما يُعرَض يأتي حرفيّاً من حمولة النقطة المقابلة؛
 * ما لا تُرجعه نقطةٌ لا يُعرَض ولا يُخترَع بديلٌ عنه.
 */
export const EmployeeProfileDrawer: React.FC<EmployeeProfileDrawerProps> = ({
  employeeId,
  employeeName,
  onClose,
  onSaved,
  initialTab = "general",
}) => {
  const toast = useToast();
  const { currentUser } = useAuth();
  const { capabilities } = usePlatformStaffCapabilitiesState(
    currentUser?.id ? String(currentUser.id) : undefined,
    !!currentUser?.isSuperAdmin,
  );
  const canManage = capabilities.is_platform_admin;

  const [employee, setEmployee] = useState<PlatformEmployeeRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<ProfileTab>(initialTab);

  const [editing, setEditing] = useState(false);
  const [jobTitle, setJobTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const loadEmployee = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const row = await getPlatformEmployee(employeeId);
      setEmployee(row);
      setJobTitle(row.job_title);
      setPhone(row.phone);
    } catch (cause) {
      setError(describePlatformOpsError(cause, "لا تصريح لك بعرض بطاقة هذا الموظّف.", "تعذّر تحميل بيانات الموظّف."));
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => { void loadEmployee(); }, [loadEmployee]);

  // تبويب «عام» — المستهدفان ومقاديرُهما المقترحة.
  const [targets, setTargets] = useState<EmployeeTargets | null>(null);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [targetsError, setTargetsError] = useState<string | null>(null);

  // تبويب «الأداء» — المحاور الخمسة الرسميّة ومحاور الـpilot الأربعة معاً.
  const [performance, setPerformance] = useState<EmployeePerformance | null>(null);
  const [pilotPerformance, setPilotPerformance] = useState<EmployeePilotPerformance | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(false);
  const [performanceError, setPerformanceError] = useState<string | null>(null);

  // حلقةُ التقييم في **رأس** اللوح (اللوحة 4 من صورة المالك) لا في تبويب — فتلزمها
  // الدرجةُ عند الفتح لا عند النقر على «الأداء». وبلا هذا الطلب كانت الحلقةُ تقول
  // «—» لموظّفٍ درجتُه معلومة، وهو كذبٌ بالرمز. والخطأُ يُبتلع هنا **عمداً**: الرأسُ
  // يبقى «—»، وتبويبُ «الأداء» يطلب من جديد ويعرض سببَ الفشل كاملاً لمن يفتحه.
  useEffect(() => {
    void getEmployeePerformance(employeeId)
      .then(setPerformance)
      .catch(() => {});
  }, [employeeId]);

  // تبويب «المحفظة».
  const [wallet, setWallet] = useState<EmployeeWalletSummary | null>(null);
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletYear, setWalletYear] = useState(now.getFullYear());
  const [walletMonth, setWalletMonth] = useState(now.getMonth() + 1);

  // تبويب «النشاط».
  // تبويب «الملاحظات» — ملاحظاتُ المدير على **هذا** الموظّف.
  //
  // كانت الملاحظاتُ تُكتَب وتُقرأ في تبويبٍ آخرَ تماماً («مهامّ الموظفين»)
  // باختيار الموظّفِ من قائمةٍ منسدلة، فمن فتح ملفَّ موظّفٍ ليقرأ ما عليه لم يجد
  // شيئاً — وهو بلاغُ المالك حرفيّاً: «ليش مش موجوده بملفو الشخصي». والمكانُ
  // الطبيعيُّ لما هو **على** الموظّف هو ملفُّه لا شاشةُ المهامّ.
  //
  // ويراها الموظّفُ نفسُه في `/staff/tasks` («ملاحظات المدير عليّ») مقصورةً على
  // `visibility=EMPLOYEE`؛ و`MANAGER_ONLY` لا تخرج من هنا — يضيّقها الخادمُ في
  // `PlatformEmployeeNoteViewSet.get_queryset` لا هذه الشاشة.
  const [notes, setNotes] = useState<PlatformEmployeeNote[] | null>(null);
  const [notesLoading, setNotesLoading] = useState(false);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [noteVisibility, setNoteVisibility] = useState<PlatformEmployeeNoteVisibility>("EMPLOYEE");
  const [noteSaving, setNoteSaving] = useState(false);

  // تبويب «المهامّ».
  /**
   * مهامُّ هذا الشخص (212-O2) — بمرشِّح `?employee=` لا بسحب إسنادات المنصّة
   * كلِّها ثمّ تصفيتِها في المتصفّح: الطاولةُ عشراتُ الأشخاص، وكلُّ فتحةِ درجٍ
   * كانت ستجرّ جدولَ الإسنادات بأكمله.
   */
  const [assignments, setAssignments] = useState<PlatformTaskAssignment[] | null>(null);
  const [assignmentsLoading, setAssignmentsLoading] = useState(false);
  const [assignmentsError, setAssignmentsError] = useState<string | null>(null);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [taskPriority, setTaskPriority] = useState<PlatformTaskPriority>("MEDIUM");
  const [taskDueDate, setTaskDueDate] = useState("");
  const [taskSaving, setTaskSaving] = useState(false);

  const [activity, setActivity] = useState<PlatformActivityLog[] | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityError, setActivityError] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== "general" || targets || targetsLoading) return;
    setTargetsLoading(true);
    setTargetsError(null);
    getEmployeeTargets(employeeId)
      .then(setTargets)
      .catch((cause) => setTargetsError(describePlatformOpsError(cause, "لا تصريح لك بعرض مستهدفات هذا الموظّف.", "تعذّر تحميل المستهدفات.")))
      .finally(() => setTargetsLoading(false));
  }, [tab, employeeId, targets, targetsLoading]);

  useEffect(() => {
    if (tab !== "performance" || (performance && pilotPerformance) || performanceLoading) return;
    setPerformanceLoading(true);
    setPerformanceError(null);
    Promise.all([getEmployeePerformance(employeeId), getEmployeePilotPerformance(employeeId)])
      .then(([perf, pilot]) => {
        setPerformance(perf);
        setPilotPerformance(pilot);
      })
      .catch((cause) => setPerformanceError(describePlatformOpsError(cause, "لا تصريح لك بعرض أداء هذا الموظّف.", "تعذّر تحميل الأداء.")))
      .finally(() => setPerformanceLoading(false));
  }, [tab, employeeId, performance, pilotPerformance, performanceLoading]);

  const loadWallet = useCallback(() => {
    setWalletLoading(true);
    setWalletError(null);
    getEmployeeWallet(employeeId, walletYear, walletMonth)
      .then(setWallet)
      .catch((cause) => setWalletError(describePlatformOpsError(cause, "لا تصريح لك بعرض محفظة هذا الموظّف.", "تعذّر تحميل المحفظة.")))
      .finally(() => setWalletLoading(false));
  }, [employeeId, walletYear, walletMonth]);

  useEffect(() => {
    if (tab !== "wallet" || wallet || walletLoading) return;
    loadWallet();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const loadAssignments = useCallback(async () => {
    setAssignmentsLoading(true);
    setAssignmentsError(null);
    try {
      setAssignments(await listPlatformTaskAssignments(employeeId));
    } catch (cause) {
      setAssignmentsError(describePlatformOpsError(
        cause, "لا تصريح لك بعرض مهامّ هذا الموظّف.", "تعذّر تحميل المهامّ.",
      ));
    } finally {
      setAssignmentsLoading(false);
    }
  }, [employeeId]);

  useEffect(() => {
    if (tab !== "tasks" || assignments || assignmentsLoading) return;
    void loadAssignments();
  }, [tab, assignments, assignmentsLoading, loadAssignments]);

  const assignTask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!taskTitle.trim()) return;
    setTaskSaving(true);
    try {
      // **إسنادٌ فرديٌّ لهذا الشخص بعينه**: `INDIVIDUAL` يلزمه موظّفٌ واحدٌ
      // بالضبط، فلا قائمةَ منسدلةً يُختار منها اسمُه — الدرجُ مفتوحٌ عليه.
      await createPlatformTask({
        title: taskTitle,
        description: taskDescription,
        priority: taskPriority,
        due_date: taskDueDate || null,
        audience: "INDIVIDUAL",
        employee_ids: [employeeId],
      });
      toast(`أُسندت المهمة إلى ${employeeName}.`, "success");
      setTaskTitle(""); setTaskDescription(""); setTaskPriority("MEDIUM"); setTaskDueDate("");
      setAssignments(null);
      await loadAssignments();
      onSaved?.();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "لا تصريح لك بإسناد المهامّ.", "تعذّر إسناد المهمة."), "error");
    } finally {
      setTaskSaving(false);
    }
  };

  const loadNotes = useCallback(async () => {
    setNotesLoading(true);
    setNotesError(null);
    try {
      setNotes(await listPlatformEmployeeNotes(employeeId));
    } catch (cause) {
      setNotesError(describePlatformOpsError(
        cause, "لا تصريح لك بعرض ملاحظات هذا الموظّف.", "تعذّر تحميل الملاحظات.",
      ));
    } finally {
      setNotesLoading(false);
    }
  }, [employeeId]);

  useEffect(() => {
    if (tab !== "notes" || notes || notesLoading) return;
    void loadNotes();
  }, [tab, notes, notesLoading, loadNotes]);

  const saveNote = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!noteBody.trim()) return;
    setNoteSaving(true);
    try {
      await createPlatformEmployeeNote(employeeId, noteBody.trim(), noteVisibility);
      toast("تمت إضافة الملاحظة.", "success");
      setNoteBody("");
      await loadNotes();
    } catch (cause) {
      toast(describePlatformOpsError(
        cause, "كتابةُ الملاحظات لمدير العمليات وحده.", "تعذّر حفظ الملاحظة.",
      ), "error");
    } finally {
      setNoteSaving(false);
    }
  };

  useEffect(() => {
    if (tab !== "activity" || activity || activityLoading) return;
    setActivityLoading(true);
    setActivityError(null);
    getEmployeeActivity(employeeId)
      .then(setActivity)
      .catch((cause) => setActivityError(describePlatformOpsError(cause, "لا تصريح لك بعرض نشاط هذا الموظّف.", "تعذّر تحميل سجلّ النشاط.")))
      .finally(() => setActivityLoading(false));
  }, [tab, employeeId, activity, activityLoading]);

  const saveProfileCard = async () => {
    if (!employee) return;
    const payload: { phone?: string; job_title?: string } = {};
    if (phone.trim() !== employee.phone) payload.phone = phone.trim();
    if (jobTitle.trim() !== employee.job_title) payload.job_title = jobTitle.trim();
    if (Object.keys(payload).length === 0) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await setEmployeeProfileCard(employeeId, payload);
      setEmployee(updated);
      toast("حُفظت بطاقة الموظّف.", "success");
      setEditing(false);
      onSaved?.();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "المسمّى الوظيفي لمدير العمليات وحده.", "تعذّر حفظ البطاقة."), "error");
    } finally {
      setSaving(false);
    }
  };

  const onPickPhoto = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const { photo_url } = await uploadEmployeePhoto(employeeId, file);
      setEmployee((prev) => (prev ? { ...prev, photo_url } : prev));
      toast("حُفظت الصورة.", "success");
      onSaved?.();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "لا تصريح لك برفع صورة هذا الموظّف.", "تعذّر رفع الصورة."), "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm" dir="rtl" role="dialog" aria-modal="true" aria-label="ملف الموظف">
      <div className="flex h-full w-full max-w-xl flex-col bg-cc-bg border-r border-cc-border shadow-2xl text-cc-text">
        <div className="flex items-center justify-between border-b border-cc-border px-5 py-3.5 bg-cc-surface">
          <h3 className="text-sm font-bold text-cc-text">ملفّ الموظّف</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="إغلاق"
            className="rounded-lg p-1.5 text-cc-text-muted transition hover:bg-cc-surface-2 hover:text-cc-text"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="py-14 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
          ) : error || !employee ? (
            <div className="m-5 flex items-center justify-between gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void loadEmployee()}
                className="rounded-lg bg-rose-500/20 px-3 py-1 text-[11px] font-bold text-rose-200 hover:bg-rose-500/30"
              >
                إعادة المحاولة
              </button>
            </div>
          ) : (
            <>
              {/* الرأس: الصورة أو الأحرف الأولى، الاسم، المسمّى الوظيفي، التخصّص، الحالة والهاتف. */}
              <div className="border-b border-cc-border p-5 bg-cc-surface">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="relative">
                      <CcAvatar
                        name={employeeName}
                        photoUrl={employee.photo_url}
                        size="lg"
                        presence={employee.status === "active" ? "online" : employee.status === "on_leave" ? "meeting" : "offline"}
                      />
                      {canManage && (
                        <label
                          className="absolute -bottom-1 -left-1 flex h-6 w-6 cursor-pointer items-center justify-center rounded-full bg-slate-800 text-white shadow ring-2 ring-cc-border hover:bg-slate-700 transition"
                          title="رفع صورة"
                        >
                          {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Camera className="h-3 w-3" />}
                          <input type="file" accept="image/*" className="sr-only" onChange={onPickPhoto} disabled={uploading} />
                        </label>
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h2 className="truncate text-base font-bold text-cc-text">{employeeName}</h2>
                        {canManage && !editing && (
                          <button
                            type="button"
                            onClick={() => setEditing(true)}
                            className="flex shrink-0 items-center gap-1 rounded-lg border border-cc-border bg-cc-surface-2 px-2 py-1 text-[11px] font-bold text-cc-text-muted transition hover:text-cc-text"
                          >
                            <Pencil className="h-3 w-3" /> تعديل
                          </button>
                        )}
                      </div>

                      {!editing ? (
                        <div className="mt-1 space-y-1">
                          {employee.job_title && (
                            <p className="text-xs font-semibold text-cc-text-muted">{employee.job_title}</p>
                          )}
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-cc-text-muted">
                            {employee.specialty && (
                              <span className="rounded-md bg-cc-surface-2 border border-cc-border px-2 py-0.5 font-medium text-cc-text">
                                {employee.specialty}
                              </span>
                            )}
                            <CcPill
                              tone={employee.status === "active" ? "success" : employee.status === "on_leave" ? "warning" : "neutral"}
                            >
                              {EMPLOYEE_STATUS_LABEL[employee.status]}
                            </CcPill>
                            {employee.phone && (
                              <span className="flex items-center gap-1">
                                <Phone className="h-3 w-3" /> {employee.phone}
                              </span>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 space-y-2">
                          <label className="block">
                            <span className="mb-1 block text-[11px] font-bold text-cc-text-muted">المسمّى الوظيفي</span>
                            <input
                              type="text"
                              value={jobTitle}
                              onChange={(event) => setJobTitle(event.target.value)}
                              className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
                            />
                          </label>
                          <label className="block">
                            <span className="mb-1 block text-[11px] font-bold text-cc-text-muted">الهاتف</span>
                            <input
                              type="text"
                              value={phone}
                              onChange={(event) => setPhone(event.target.value)}
                              className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
                            />
                          </label>
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setEditing(false);
                                setJobTitle(employee.job_title);
                                setPhone(employee.phone);
                              }}
                              className="rounded-lg bg-cc-surface-2 px-3 py-1 text-[11px] font-bold text-cc-text-muted hover:text-cc-text"
                            >
                              إلغاء
                            </button>
                            <button
                              type="button"
                              disabled={saving}
                              onClick={() => void saveProfileCard()}
                              className="rounded-lg bg-sky-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-sky-500 disabled:opacity-50"
                            >
                              حفظ
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* حلقة التقييم للأداء العام (Panel 4) */}
                  <div className="shrink-0 flex flex-col items-center justify-center p-2 rounded-xl border border-cc-border bg-cc-surface-2/40">
                    <CcGauge
                      value={performance?.composite_score ?? 0}
                      displayValue={performance?.composite_score != null ? `${formatNumber(Math.round(performance.composite_score))}%` : "—"}
                      size="md"
                      caption="الأداء العام"
                    />
                  </div>
                </div>
              </div>

              {/* التبويبات */}
              <div className="border-b border-cc-border bg-cc-surface px-5">
                <CcTabs
                  tabs={TABS}
                  active={tab}
                  onChange={(key) => setTab(key as ProfileTab)}
                />
              </div>

              <div className="p-5">
                {tab === "general" && (
                  <section className="space-y-4">
                    {targetsLoading ? (
                      <div className="py-8 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
                    ) : targetsError ? (
                      <p className="text-xs text-rose-400">{targetsError}</p>
                    ) : targets ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <CcCard className="border-cc-border bg-cc-surface">
                            <p className="text-[11px] text-cc-text-muted">طاقة الإسناد</p>
                            <p className="mt-1 text-lg font-bold text-cc-text">{formatNumber(targets.capacity_target)}</p>
                          </CcCard>
                          <CcCard className="border-cc-border bg-cc-surface">
                            <p className="text-[11px] text-cc-text-muted">مقام الإنجاز الشهري (وحدات)</p>
                            <p className="mt-1 text-lg font-bold text-cc-text">{formatNumber(targets.monthly_units_target)}</p>
                          </CcCard>
                        </div>
                        {targets.monthly_units_suggestion?.targets && (
                          <CcCard tone="accent" className="border-cc-border bg-cc-surface-2/60">
                            <p className="mb-2 text-[11px] font-bold text-cc-text">مقاديرُ مقترحة لمقام الإنجاز</p>
                            <div className="flex flex-wrap gap-4 text-xs text-cc-text-muted">
                              <span>الأدنى: <strong className="text-cc-text font-mono">{formatNumber(targets.monthly_units_suggestion.targets.low)}</strong></span>
                              <span>المتوسط: <strong className="text-cc-text font-mono">{formatNumber(targets.monthly_units_suggestion.targets.medium)}</strong></span>
                              <span>الأعلى: <strong className="text-cc-text font-mono">{formatNumber(targets.monthly_units_suggestion.targets.high)}</strong></span>
                            </div>
                          </CcCard>
                        )}
                      </div>
                    ) : (
                      <CcEmpty title="لا توجد مستهدفات مسجّلة." />
                    )}
                  </section>
                )}

                {tab === "performance" && (
                  <section className="space-y-5">
                    {performanceLoading ? (
                      <div className="py-8 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
                    ) : performanceError ? (
                      <p className="text-xs text-rose-400">{performanceError}</p>
                    ) : (
                      <>
                        {performance && (
                          <CcCard className="space-y-3 border-cc-border bg-cc-surface">
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-bold text-cc-text">المحاور الخمسة الرسميّة</h4>
                              {performance.composite_score !== null && (
                                <CcPill tone="success">
                                  النتيجة المركّبة: {formatNumber(performance.composite_score)}%
                                </CcPill>
                              )}
                            </div>
                            <p className="text-[11px] text-cc-text-muted">
                              {performance.status_message} · حجم العينة: {formatNumber(performance.sample_size)} (الحد الأدنى{" "}
                              {formatNumber(performance.min_sample_size)})
                            </p>
                            <CcTable>
                              <CcThead>
                                <CcTr>
                                  <CcTh align="right">المحور</CcTh>
                                  <CcTh align="right">منطبق</CcTh>
                                  <CcTh align="right">الوزن</CcTh>
                                  <CcTh align="right">النتيجة</CcTh>
                                  <CcTh align="right">المساهمة</CcTh>
                                </CcTr>
                              </CcThead>
                              <tbody>
                                {PERFORMANCE_AXES.map((axis) => {
                                  const detail = performance.axes[axis];
                                  if (!detail) return null;
                                  return (
                                    <CcTr key={axis}>
                                      <CcTd align="right" className="font-medium text-cc-text">{PERFORMANCE_AXIS_LABELS[axis]}</CcTd>
                                      <CcTd align="right">{detail.applicable ? "نعم" : "لا"}</CcTd>
                                      <CcTd align="right">{formatNumber(detail.weight_pct)}%</CcTd>
                                      <CcTd align="right">{formatNumber(detail.score_pct)}%</CcTd>
                                      <CcTd align="right">{formatNumber(detail.weighted_contribution)}</CcTd>
                                    </CcTr>
                                  );
                                })}
                              </tbody>
                            </CcTable>
                          </CcCard>
                        )}

                        {pilotPerformance && (
                          <CcCard className="space-y-3 border-cc-border bg-cc-surface">
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-bold text-cc-text">محاور الـpilot الأربعة</h4>
                              {pilotPerformance.composite_score !== null && (
                                <CcPill tone="accent">
                                  النتيجة المركّبة: {formatNumber(pilotPerformance.composite_score)}%
                                </CcPill>
                              )}
                            </div>
                            <p className="text-[11px] text-cc-text-muted">
                              {pilotPerformance.status_message} · حجم العينة: {formatNumber(pilotPerformance.sample_size)} (الحد
                              الأدنى {formatNumber(pilotPerformance.min_sample_size)})
                            </p>
                            <PilotAxesTable performance={pilotPerformance} />
                          </CcCard>
                        )}
                      </>
                    )}
                  </section>
                )}

                {tab === "tasks" && (
                  <section className="space-y-4">
                    {canManage && (
                      <form onSubmit={assignTask} className="rounded-xl border border-cc-border bg-cc-surface p-4 space-y-3">
                        <h3 className="text-xs font-bold text-cc-text">أسند مهمة إلى {employeeName}</h3>
                        <input
                          required
                          value={taskTitle}
                          onChange={(event) => setTaskTitle(event.target.value)}
                          className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
                          placeholder="عنوان المهمة"
                        />
                        <textarea
                          value={taskDescription}
                          onChange={(event) => setTaskDescription(event.target.value)}
                          className="min-h-16 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
                          placeholder="الوصف (اختياري)"
                        />
                        <div className="grid grid-cols-2 gap-2">
                          <label className="text-xs font-semibold text-cc-text-muted">
                            الأولوية
                            <select
                              value={taskPriority}
                              onChange={(event) => setTaskPriority(event.target.value as PlatformTaskPriority)}
                              className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
                            >
                              <option value="LOW" className="bg-slate-900 text-slate-100">منخفضة</option>
                              <option value="MEDIUM" className="bg-slate-900 text-slate-100">متوسطة</option>
                              <option value="HIGH" className="bg-slate-900 text-slate-100">عالية</option>
                              <option value="URGENT" className="bg-slate-900 text-slate-100">عاجلة</option>
                            </select>
                          </label>
                          <label className="text-xs font-semibold text-cc-text-muted">
                            الاستحقاق <span className="font-normal text-cc-text-muted/60">(اختياري)</span>
                            <input
                              type="date"
                              value={taskDueDate}
                              onChange={(event) => setTaskDueDate(event.target.value)}
                              className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
                            />
                          </label>
                        </div>
                        <button
                          type="submit"
                          disabled={taskSaving}
                          className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition"
                        >
                          {taskSaving ? "جاري الإسناد..." : "أسند المهمة"}
                        </button>
                      </form>
                    )}
                    {assignmentsLoading ? (
                      <div className="py-8 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
                    ) : assignmentsError ? (
                      <p className="text-xs text-rose-400">{assignmentsError}</p>
                    ) : assignments && assignments.length > 0 ? (
                      <div className="space-y-2">
                        {assignments.map((assignment) => (
                          <article key={assignment.id} className="rounded-xl border border-cc-border bg-cc-surface p-3.5">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-xs font-bold text-cc-text">{assignment.task_title}</span>
                              <CcPill
                                tone={assignment.status === 'COMPLETED' ? 'success' : assignment.status === 'RETURNED' ? 'warning' : 'accent'}
                              >
                                {assignment.status_display}
                              </CcPill>
                            </div>
                            <p className="mt-1.5 text-xs text-cc-text-muted">
                              أُسندت {formatDateTimeValue(assignment.offered_at)}
                              {assignment.accepted_at ? ` · قبلها ${formatDateTimeValue(assignment.accepted_at)}` : ""}
                              {assignment.submitted_at ? ` · سلّمها ${formatDateTimeValue(assignment.submitted_at)}` : ""}
                            </p>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <CcEmpty title="لا مهامَّ مُسندةً لهذا الموظّف بعد." />
                    )}
                  </section>
                )}

                {tab === "wallet" && (
                  <section className="space-y-4">
                    <div className="flex flex-wrap items-end gap-2 bg-cc-surface-2/40 p-3 rounded-xl border border-cc-border">
                      <label className="space-y-1 text-[11px]">
                        <span className="block text-cc-text-muted">السنة</span>
                        <input
                          type="number"
                          value={walletYear}
                          onChange={(event) => setWalletYear(Number(event.target.value))}
                          className="w-20 rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text"
                        />
                      </label>
                      <label className="space-y-1 text-[11px]">
                        <span className="block text-cc-text-muted">الشهر</span>
                        <input
                          type="number"
                          min={1}
                          max={12}
                          value={walletMonth}
                          onChange={(event) => setWalletMonth(Number(event.target.value))}
                          className="w-16 rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setWallet(null);
                          loadWallet();
                        }}
                        className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-[11px] font-bold text-cc-text hover:bg-cc-surface transition"
                      >
                        عرض
                      </button>
                    </div>

                    {walletLoading ? (
                      <div className="py-8 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
                    ) : walletError ? (
                      <p className="text-xs text-rose-400">{walletError}</p>
                    ) : wallet ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <CcCard tone="success" className="border-cc-border bg-cc-surface p-3.5">
                            <CcStatTile
                              label="مؤكَّد"
                              value={formatNumber(wallet.totals.confirmed)}
                              tone="success"
                            />
                          </CcCard>
                          <CcCard tone="warning" className="border-cc-border bg-cc-surface p-3.5">
                            <CcStatTile
                              label="معلَّق"
                              value={formatNumber(wallet.totals.pending)}
                              tone="warning"
                            />
                          </CcCard>
                        </div>
                        {(() => {
                          const lines: WalletLine[] = [...wallet.salary_lines, ...wallet.commission_lines];
                          return lines.length === 0 ? (
                            <CcEmpty title="لا سطور لهذا الشهر." />
                          ) : (
                            <CcTable>
                              <CcThead>
                                <CcTr>
                                  <CcTh align="right">النوع</CcTh>
                                  <CcTh align="right">المبلغ</CcTh>
                                  <CcTh align="right">الحالة</CcTh>
                                  <CcTh align="right">آخر تحديث</CcTh>
                                </CcTr>
                              </CcThead>
                              <tbody>
                                {lines.map((line) => (
                                  <CcTr key={`${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`}>
                                    <CcTd align="right" className="font-medium text-cc-text">
                                      {isCommissionLine(line) ? "عمولة اكتساب" : "راتب"}
                                    </CcTd>
                                    <CcTd align="right" className="font-semibold text-cc-text">
                                      {formatNumber(line.amount)}
                                    </CcTd>
                                    <CcTd align="right">
                                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${WALLET_STATUS_CLASS[line.status]}`}>
                                        {line.status_display || WALLET_LINE_STATUS_LABEL[line.status]}
                                      </span>
                                    </CcTd>
                                    <CcTd align="right" className="text-cc-text-muted font-mono text-xs">
                                      {formatDateTimeValue(line.updated_at) || "—"}
                                    </CcTd>
                                  </CcTr>
                                ))}
                              </tbody>
                            </CcTable>
                          );
                        })()}
                      </div>
                    ) : null}
                  </section>
                )}

                {tab === "notes" && (
                  <section className="space-y-4">
                    {canManage && (
                      <form onSubmit={saveNote} className="rounded-xl border border-cc-border bg-cc-surface p-4 space-y-3">
                        <h3 className="text-xs font-bold text-cc-text">أضف ملاحظة على هذا الموظّف</h3>
                        <textarea
                          required
                          value={noteBody}
                          onChange={(event) => setNoteBody(event.target.value)}
                          className="min-h-20 w-full rounded-lg border border-cc-border bg-cc-surface-2 p-2.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
                          placeholder="ما تريد تسجيلَه على الموظّف"
                        />
                        <fieldset>
                          <legend className="text-xs font-semibold text-cc-text-muted">الرؤية</legend>
                          <div className="mt-1 flex flex-wrap gap-4 text-xs text-cc-text">
                            <label className="inline-flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="radio"
                                name="profile-note-visibility"
                                checked={noteVisibility === "EMPLOYEE"}
                                onChange={() => setNoteVisibility("EMPLOYEE")}
                              />
                              <span>يراها الموظّف</span>
                            </label>
                            <label className="inline-flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="radio"
                                name="profile-note-visibility"
                                checked={noteVisibility === "MANAGER_ONLY"}
                                onChange={() => setNoteVisibility("MANAGER_ONLY")}
                              />
                              <span>للمدير فقط</span>
                            </label>
                          </div>
                        </fieldset>
                        <button
                          type="submit"
                          disabled={noteSaving}
                          className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition"
                        >
                          {noteSaving ? "جاري الحفظ..." : "أضف الملاحظة"}
                        </button>
                      </form>
                    )}
                    {notesLoading ? (
                      <div className="py-8 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
                    ) : notesError ? (
                      <p className="text-xs text-rose-400">{notesError}</p>
                    ) : notes && notes.length > 0 ? (
                      <div className="space-y-3">
                        {notes.map((note) => {
                          const isManagerOnly = note.visibility === "MANAGER_ONLY";
                          return (
                            <div
                              key={note.id}
                              className={`flex flex-col ${isManagerOnly ? "items-start" : "items-end"}`}
                            >
                              <article
                                className={`max-w-[85%] rounded-2xl p-3.5 shadow-sm ${
                                  isManagerOnly
                                    ? "rounded-tr-none bg-cc-surface-2 border border-cc-border text-cc-text"
                                    : "rounded-tl-none bg-emerald-950/40 border border-emerald-500/30 text-cc-text"
                                }`}
                              >
                                <div className="flex items-center gap-2 mb-1.5">
                                  <CcPill
                                    tone={isManagerOnly ? "danger" : "success"}
                                  >
                                    {note.visibility_display}
                                  </CcPill>
                                  <span className="text-xs font-bold text-cc-text">{note.author_name}</span>
                                </div>
                                <p className="whitespace-pre-wrap text-xs leading-relaxed text-cc-text/90">{note.body}</p>
                                <div className="mt-2 text-[10px] text-cc-text-muted font-mono">
                                  {formatDateTimeValue(note.created_at)}
                                </div>
                              </article>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <CcEmpty title="لا ملاحظاتٍ على هذا الموظّف بعد." />
                    )}
                  </section>
                )}

                {tab === "activity" && (
                  <section>
                    {activityLoading ? (
                      <div className="py-8 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
                    ) : activityError ? (
                      <p className="text-xs text-rose-400">{activityError}</p>
                    ) : activity && activity.length > 0 ? (
                      <CcTable>
                        <CcThead>
                          <CcTr>
                            <CcTh align="right">التوقيت</CcTh>
                            <CcTh align="right">الحدث</CcTh>
                            <CcTh align="right">الوصف</CcTh>
                            <CcTh align="right">الشركة</CcTh>
                          </CcTr>
                        </CcThead>
                        <tbody>
                          {activity.map((log) => (
                            <CcTr key={log.id}>
                              <CcTd align="right" className="whitespace-nowrap text-cc-text-muted font-mono text-xs">
                                {formatDateTimeValue(log.created_at)}
                              </CcTd>
                              <CcTd align="right" className="font-mono text-xs text-cc-text">
                                {log.action_display || log.action}
                              </CcTd>
                              <CcTd align="right" className="text-xs text-cc-text">
                                {log.description}
                              </CcTd>
                              <CcTd align="right" className="text-xs text-cc-text-muted">
                                {log.company_name || "—"}
                              </CcTd>
                            </CcTr>
                          ))}
                        </tbody>
                      </CcTable>
                    ) : (
                      <CcEmpty title="لا يوجد نشاطٌ مسجَّل حتى الآن." />
                    )}
                  </section>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default EmployeeProfileDrawer;
