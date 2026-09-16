import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarClock, Users, Video } from "lucide-react";

import {
  MEETING_STATUS_LABEL,
  cancelPlatformMeeting,
  createPlatformMeeting,
  decideMeetingExcuse,
  inviteEmployeesToMeeting,
  listActivePlatformEmployeesForInvite,
  listMeetingAttendance,
  listPlatformMeetings,
  updatePlatformMeeting,
  type PlatformMeetingAttendanceRow,
  type PlatformMeetingRow,
} from "../../services/platformMeetingsApi";
import type { MyPlatformEmployeeProfile } from "../../services/platformEmployeeSpaceApi";
import { dateTimeLocalToIso, isoToDateTimeLocal } from "../../utils/dateTimeLocal";
import { tallyAttendance } from "../../utils/meetingAttendanceTally";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  CcAvatar,
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcTable,
  CcThead,
  CcTh,
  CcTr,
  CcTd,
} from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذا الإجراء متاح لمدير العمليات وحده.", "تعذّر إتمام العملية.");

const meetingStatusTone = (status: string): "neutral" | "accent" | "success" | "warning" | "danger" => {
  switch (status) {
    case "scheduled":
      return "accent";
    case "finished":
      return "success";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
};

const attendanceStatusTone = (status: string): "neutral" | "accent" | "success" | "warning" | "danger" => {
  switch (status) {
    case "attended":
      return "success";
    case "absent":
      return "danger";
    case "excused_pending":
      return "warning";
    case "excused_accepted":
      return "accent";
    case "excused_rejected":
      return "danger";
    default:
      return "neutral";
  }
};

interface MeetingFormState {
  title: string;
  agenda: string;
  start: string;
  end: string;
  meeting_link: string;
}

const EMPTY_FORM: MeetingFormState = { title: "", agenda: "", start: "", end: "", meeting_link: "" };

/** تحقّقٌ فوريٌّ في الواجهة — الخادمُ يرفض بـ`meeting_end_before_start` أيضاً، لكنّ رسالةً قبل الإرسال أفضل. */
const validateWindow = (form: MeetingFormState): string | null => {
  if (!form.title.trim()) return "عنوانُ الاجتماع مطلوب.";
  if (!form.start || !form.end) return "بدايةُ الاجتماع ونهايتُه مطلوبتان.";
  if (!form.meeting_link.trim()) return "رابطُ الاجتماع مطلوب.";
  const start = new Date(form.start).getTime();
  const end = new Date(form.end).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return "تاريخٌ غير صالح.";
  if (end <= start) return "نهايةُ الاجتماع يجب أن تكون بعد بدايته.";
  return null;
};

const MeetingForm: React.FC<{
  initial?: MeetingFormState;
  submitLabel: string;
  busy: boolean;
  onCancel?: () => void;
  onSubmit: (form: MeetingFormState) => void;
}> = ({ initial, submitLabel, busy, onCancel, onSubmit }) => {
  const [form, setForm] = useState<MeetingFormState>(initial ?? EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof MeetingFormState>(key: K, value: MeetingFormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = () => {
    const validation = validateWindow(form);
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    onSubmit(form);
  };

  return (
    <div className="space-y-2">
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input
          type="text"
          value={form.title}
          onChange={(event) => set("title", event.target.value)}
          placeholder="عنوان الاجتماع"
          className="rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
        <input
          type="text"
          value={form.meeting_link}
          onChange={(event) => set("meeting_link", event.target.value)}
          placeholder="رابط الاجتماع"
          className="rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
        <label className="flex flex-col gap-0.5 text-[11px] text-cc-text-muted">
          البداية
          <input
            type="datetime-local"
            value={form.start}
            onChange={(event) => set("start", event.target.value)}
            className="rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-cc-text-muted">
          النهاية
          <input
            type="datetime-local"
            value={form.end}
            onChange={(event) => set("end", event.target.value)}
            className="rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </label>
        <textarea
          value={form.agenda}
          onChange={(event) => set("agenda", event.target.value)}
          placeholder="جدول الأعمال (اختياري)"
          rows={2}
          className="md:col-span-2 rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={handleSubmit}
          className="rounded-lg bg-sky-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition"
        >
          {busy ? "..." : submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg bg-cc-surface-2 border border-cc-border px-3.5 py-1.5 text-xs font-bold text-cc-text-muted hover:text-cc-text transition"
          >
            إلغاء
          </button>
        )}
      </div>
    </div>
  );
};

const InvitePicker: React.FC<{
  meeting: PlatformMeetingRow;
  onClose: () => void;
  onInvited: () => void;
}> = ({ meeting, onClose, onInvited }) => {
  const toast = useToast();
  const [employees, setEmployees] = useState<MyPlatformEmployeeProfile[] | null>(null);
  const [alreadyInvited, setAlreadyInvited] = useState<ReadonlySet<number>>(new Set());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // المدعوّون سلفاً يُقرآن مع القائمة: الخدمةُ idempotent فإعادةُ الدعوة لا تضرّ،
  // لكنّ منتقياً لا يُظهر مَن دُعي يجعل المديرَ يختار على غير علم — فيدعو نصفَ
  // الفريق مرّتين ويظنّ أنّه أضاف، أو يترك أحداً ظنّاً أنّه مدعوّ. والمعلومةُ
  // موجودةٌ في دفتر الحضور نفسِه، فجلبُها هنا يوفّر فتحَ شاشةٍ ثانية للتأكّد.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([listActivePlatformEmployeesForInvite(), listMeetingAttendance(meeting.id)])
      .then(([rows, attendance]) => {
        if (cancelled) return;
        setEmployees(rows);
        setAlreadyInvited(new Set(attendance.map((row) => row.employee)));
      })
      .catch((cause) => {
        if (!cancelled) toast(displayError(cause), "error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [meeting.id, toast]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const submit = async () => {
    if (selected.size === 0) {
      toast("اختر موظّفاً واحداً على الأقلّ.", "error");
      return;
    }
    setBusy(true);
    try {
      await inviteEmployeesToMeeting(meeting.id, Array.from(selected));
      toast("أُرسلت الدعوات.", "success");
      onInvited();
      onClose();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <CcCard tone="accent" className="p-4 space-y-3" dir="rtl">
      <h3 className="text-xs font-bold text-sky-400">دعوةُ موظّفين إلى «{meeting.title}»</h3>
      {loading ? (
        <p className="text-xs text-cc-text-muted">جاري التحميل...</p>
      ) : !employees || employees.length === 0 ? (
        <p className="text-xs text-cc-text-muted">لا موظّفو منصّةٍ نشطون.</p>
      ) : (
        <ul className="max-h-52 overflow-y-auto space-y-1 rounded-xl bg-cc-surface p-2 border border-cc-border">
          {employees.map((employee) => {
            const invited = alreadyInvited.has(employee.id);
            return (
              <li key={employee.id}>
                <label
                  className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs transition ${
                    invited ? "text-cc-text-muted/60" : "text-cc-text hover:bg-cc-surface-2"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={invited || selected.has(employee.id)}
                    disabled={invited}
                    onChange={() => toggle(employee.id)}
                    className="rounded border-cc-border"
                  />
                  <span>
                    {employee.username} {employee.specialty ? `— ${employee.specialty}` : ""}
                  </span>
                  {invited && (
                    <CcPill tone="accent" className="mr-auto">
                      مدعوٌّ سلفاً
                    </CcPill>
                  )}
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy || loading}
          onClick={() => void submit()}
          className="rounded-lg bg-sky-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition"
        >
          {busy ? "..." : `دعوة (${formatNumber(selected.size)})`}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg bg-cc-surface-2 border border-cc-border px-3.5 py-1.5 text-xs font-bold text-cc-text-muted hover:text-cc-text transition"
        >
          إغلاق
        </button>
      </div>
    </CcCard>
  );
};

const AttendanceBook: React.FC<{ meeting: PlatformMeetingRow; onClose: () => void }> = ({ meeting, onClose }) => {
  const toast = useToast();
  const [rows, setRows] = useState<PlatformMeetingAttendanceRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listMeetingAttendance(meeting.id));
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setLoading(false);
    }
  }, [meeting.id, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  // العدُّ في دالّةٍ خالصةٍ يفحصها `npm test` — منطقٌ يسكن `useMemo` لا يراه شيء.
  const counts = useMemo(() => tallyAttendance(rows), [rows]);

  const decide = async (attendance: PlatformMeetingAttendanceRow, accepted: boolean) => {
    setBusyId(attendance.id);
    try {
      await decideMeetingExcuse(meeting.id, attendance.id, accepted);
      toast(accepted ? "قُبل العذر." : "رُفض العذر.", "success");
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <CcCard className="p-4 space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-cc-text">دفترُ حضور «{meeting.title}»</h3>
        <button type="button" onClick={onClose} className="text-xs text-sky-400 hover:underline">
          إغلاق
        </button>
      </div>
      {loading ? (
        <p className="text-xs text-cc-text-muted">جاري التحميل...</p>
      ) : !rows || rows.length === 0 ? (
        <CcEmpty title="لا مدعوّون بعد." />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
            <span className="rounded-lg bg-cc-surface-2 border border-cc-border px-2.5 py-1 text-cc-text">
              مدعوّون {formatNumber(counts.total)}
            </span>
            <span className="rounded-lg bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-1 text-emerald-400">
              حضر {formatNumber(counts.attended)}
            </span>
            <span className="rounded-lg bg-rose-500/15 border border-rose-500/30 px-2.5 py-1 text-rose-400">
              غاب بلا عذر {formatNumber(counts.absent)}
            </span>
            {counts.excusedPending > 0 && (
              <span className="rounded-lg bg-amber-500/15 border border-amber-500/30 px-2.5 py-1 text-amber-400">
                عذرٌ بانتظار البتّ {formatNumber(counts.excusedPending)}
              </span>
            )}
            {counts.excusedAccepted > 0 && (
              <span className="rounded-lg bg-sky-500/15 border border-sky-500/30 px-2.5 py-1 text-sky-400">
                عذرٌ مقبول {formatNumber(counts.excusedAccepted)}
              </span>
            )}
            {counts.excusedRejected > 0 && (
              <span className="rounded-lg bg-rose-500/15 border border-rose-500/30 px-2.5 py-1 text-rose-400">
                عذرٌ مرفوض {formatNumber(counts.excusedRejected)}
              </span>
            )}
          </div>
          <CcTable>
            <CcThead>
              <tr>
                <CcTh>الموظّف</CcTh>
                <CcTh>الحالة</CcTh>
                <CcTh>وقت الدخول</CcTh>
                <CcTh>سبب العذر</CcTh>
                <CcTh>البتّ</CcTh>
                <CcTh />
              </tr>
            </CcThead>
            <tbody>
              {rows.map((row) => (
                <CcTr key={row.id}>
                  <CcTd className="font-medium text-cc-text">
                    <div className="flex items-center gap-2">
                      <CcAvatar name={row.employee_name} size="sm" />
                      <span>{row.employee_name}</span>
                    </div>
                  </CcTd>
                  <CcTd>
                    <CcPill tone={attendanceStatusTone(row.status)}>
                      {row.status_display}
                    </CcPill>
                  </CcTd>
                  <CcTd className="text-cc-text-muted">
                    {row.checked_in_at ? formatDateTimeValue(row.checked_in_at) : "—"}
                  </CcTd>
                  <CcTd className="text-cc-text">{row.excuse_note || "—"}</CcTd>
                  <CcTd className="text-cc-text-muted">
                    {row.excuse_decided_by_name
                      ? `${row.excuse_decided_by_name} — ${formatDateTimeValue(row.excuse_decided_at)}`
                      : "—"}
                  </CcTd>
                  <CcTd className="whitespace-nowrap">
                    {row.status === "excused_pending" && (
                      <div className="flex gap-1">
                        <button
                          type="button"
                          disabled={busyId === row.id}
                          onClick={() => void decide(row, true)}
                          className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                        >
                          قبول
                        </button>
                        <button
                          type="button"
                          disabled={busyId === row.id}
                          onClick={() => void decide(row, false)}
                          className="rounded-lg bg-rose-600 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 transition"
                        >
                          رفض
                        </button>
                      </div>
                    )}
                  </CcTd>
                </CcTr>
              ))}
            </tbody>
          </CcTable>
        </>
      )}
    </CcCard>
  );
};

/**
 * شاشةُ مدير العمليات لاجتماعات المنصّة: إنشاءٌ وتعديلٌ وإلغاءٌ ودعوةٌ ودفترُ
 * حضورٍ يبتُّ في الأعذار المعلَّقة (211-G — الخادمُ جاهزٌ منذ 211-F).
 */
export const MeetingsPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [meetings, setMeetings] = useState<PlatformMeetingRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [inviteMeeting, setInviteMeeting] = useState<PlatformMeetingRow | null>(null);
  const [attendanceMeeting, setAttendanceMeeting] = useState<PlatformMeetingRow | null>(null);
  // مفتاحُ نموذج الإنشاء: يُبدَّل بعد كلّ إنشاءٍ ناجحٍ فيُعاد تركيبُ النموذج فارغاً.
  // نموذجٌ يبقى ممتلئاً بعد النجاح يدعو إلى نقرةٍ ثانيةٍ تُنشئ اجتماعاً مكرَّراً
  // بالعنوان والوقت نفسِهما — والخادمُ لا يمنعه، فالتكرارُ مشروعٌ في ذاته.
  const [formSeq, setFormSeq] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMeetings(await listPlatformMeetings());
    } catch (cause) {
      setError(displayError(cause));
      setMeetings(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submitCreate = async (form: MeetingFormState) => {
    setCreating(true);
    try {
      await createPlatformMeeting({
        title: form.title.trim(),
        agenda: form.agenda.trim(),
        start: dateTimeLocalToIso(form.start) ?? "",
        end: dateTimeLocalToIso(form.end) ?? "",
        meeting_link: form.meeting_link.trim(),
      });
      toast("أُنشئ الاجتماع.", "success");
      setFormSeq((seq) => seq + 1);
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setCreating(false);
    }
  };

  const submitEdit = async (meeting: PlatformMeetingRow, form: MeetingFormState) => {
    setBusyId(meeting.id);
    try {
      await updatePlatformMeeting(meeting.id, {
        title: form.title.trim(),
        agenda: form.agenda.trim(),
        start: dateTimeLocalToIso(form.start) ?? undefined,
        end: dateTimeLocalToIso(form.end) ?? undefined,
        meeting_link: form.meeting_link.trim(),
      });
      toast("عُدِّل الاجتماع.", "success");
      setEditingId(null);
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  const cancel = async (meeting: PlatformMeetingRow) => {
    const proceed = await confirm({
      title: "إلغاء الاجتماع",
      message: `سيُلغى اجتماع «${meeting.title}» ويُمنع الدخولُ إليه والاعتذار عنه بعد ذلك. متابعة؟`,
      confirmText: "إلغاء الاجتماع",
      danger: true,
    });
    if (!proceed) return;
    setBusyId(meeting.id);
    try {
      await cancelPlatformMeeting(meeting.id);
      toast("أُلغي الاجتماع.", "success");
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-6" dir="rtl">
      <CcSectionTitle
        title="الاجتماعات"
        badge={meetings ? meetings.length : undefined}
      />

      <CcCard className="p-4 sm:p-5">
        <h3 className="mb-3 text-xs font-bold text-cc-text">اجتماعٌ جديد</h3>
        <MeetingForm key={formSeq} submitLabel="إنشاء الاجتماع" busy={creating} onSubmit={submitCreate} />
      </CcCard>

      {error && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg bg-rose-500/20 px-3 py-1 text-[11px] font-bold text-rose-200 hover:bg-rose-500/30 transition"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {loading ? (
        <CcCard className="p-6">
          <div className="py-12 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
        </CcCard>
      ) : !meetings || meetings.length === 0 ? (
        <CcEmpty title="لا اجتماعات مجدولة بعد." />
      ) : (
        <ul className="space-y-3">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
            <CcCard className="p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  {meeting.created_by_name && (
                    <CcAvatar name={meeting.created_by_name} size="md" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-sm font-bold text-cc-text">{meeting.title}</h4>
                      {meeting.created_by_name && (
                        <span className="text-[11px] text-cc-text-muted">
                          بواسطة {meeting.created_by_name}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-cc-text-muted">
                      <CalendarClock className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                      <span>
                        {formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}
                      </span>
                    </p>
                    <div className="mt-1 flex items-center gap-3 text-xs text-cc-text-muted flex-wrap">
                      <span className="flex items-center gap-1">
                        <Users className="h-3.5 w-3.5 text-cc-text-muted shrink-0" />
                        <span>مدعوّون: {formatNumber(meeting.invited_count)}</span>
                      </span>
                      {meeting.meeting_link && (
                        <span className="flex items-center gap-1 text-sky-400">
                          <Video className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate max-w-xs">{meeting.meeting_link}</span>
                        </span>
                      )}
                    </div>
                    {meeting.agenda && (
                      <p className="mt-2 text-xs text-cc-text-muted bg-cc-surface-2/60 rounded-lg p-2 border border-cc-border">
                        {meeting.agenda}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <CcPill tone={meetingStatusTone(meeting.status)}>
                    {meeting.status_display || MEETING_STATUS_LABEL[meeting.status]}
                  </CcPill>
                </div>
              </div>

              {meeting.status === "scheduled" && (
                <>
                  {editingId === meeting.id ? (
                    <div className="mt-3 pt-3 border-t border-cc-border">
                      <MeetingForm
                        initial={{
                          title: meeting.title,
                          agenda: meeting.agenda,
                          start: isoToDateTimeLocal(meeting.start),
                          end: isoToDateTimeLocal(meeting.end),
                          meeting_link: meeting.meeting_link,
                        }}
                        submitLabel="حفظ التعديل"
                        busy={busyId === meeting.id}
                        onCancel={() => setEditingId(null)}
                        onSubmit={(form) => void submitEdit(meeting, form)}
                      />
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2 pt-2 border-t border-cc-border">
                      <button
                        type="button"
                        onClick={() => setEditingId(meeting.id)}
                        className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-[11px] font-bold text-cc-text hover:bg-cc-surface transition"
                      >
                        تعديل
                      </button>
                      <button
                        type="button"
                        disabled={busyId === meeting.id}
                        onClick={() => void cancel(meeting)}
                        className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-[11px] font-bold text-rose-300 hover:bg-rose-500/20 disabled:opacity-50 transition"
                      >
                        إلغاء الاجتماع
                      </button>
                      <button
                        type="button"
                        onClick={() => setInviteMeeting(meeting)}
                        className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-[11px] font-bold text-sky-300 hover:bg-sky-500/20 transition"
                      >
                        دعوة موظّفين
                      </button>
                    </div>
                  )}
                </>
              )}

              <button
                type="button"
                onClick={() => setAttendanceMeeting(meeting)}
                className="text-[11px] font-bold text-sky-400 hover:underline"
              >
                دفتر الحضور
              </button>

              {inviteMeeting?.id === meeting.id && (
                <InvitePicker meeting={meeting} onClose={() => setInviteMeeting(null)} onInvited={() => void load()} />
              )}

              {attendanceMeeting?.id === meeting.id && (
                <AttendanceBook meeting={meeting} onClose={() => setAttendanceMeeting(null)} />
              )}
            </CcCard>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default MeetingsPanel;
