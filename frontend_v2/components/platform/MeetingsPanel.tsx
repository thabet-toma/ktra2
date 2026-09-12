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

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذا الإجراء متاح لمدير العمليات وحده.", "تعذّر إتمام العملية.");

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
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input
          type="text"
          value={form.title}
          onChange={(event) => set("title", event.target.value)}
          placeholder="عنوان الاجتماع"
          className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
        />
        <input
          type="text"
          value={form.meeting_link}
          onChange={(event) => set("meeting_link", event.target.value)}
          placeholder="رابط الاجتماع"
          className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
        />
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          البداية
          <input
            type="datetime-local"
            value={form.start}
            onChange={(event) => set("start", event.target.value)}
            className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-500">
          النهاية
          <input
            type="datetime-local"
            value={form.end}
            onChange={(event) => set("end", event.target.value)}
            className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
          />
        </label>
        <textarea
          value={form.agenda}
          onChange={(event) => set("agenda", event.target.value)}
          placeholder="جدول الأعمال (اختياري)"
          rows={2}
          className="md:col-span-2 px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
        />
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={handleSubmit}
          className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "..." : submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg bg-slate-100 px-3.5 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-200"
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
      .catch((cause) => { if (!cancelled) toast(displayError(cause), "error"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [meeting.id, toast]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
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
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 space-y-3" dir="rtl">
      <h3 className="text-xs font-bold text-blue-900">دعوةُ موظّفين إلى «{meeting.title}»</h3>
      {loading ? (
        <p className="text-xs text-slate-500">جاري التحميل...</p>
      ) : !employees || employees.length === 0 ? (
        <p className="text-xs text-slate-500">لا موظّفو منصّةٍ نشطون.</p>
      ) : (
        <ul className="max-h-52 overflow-y-auto space-y-1 rounded-lg bg-white p-2 border border-blue-100">
          {employees.map((employee) => {
            const invited = alreadyInvited.has(employee.id);
            return (
              <li key={employee.id}>
                <label
                  className={`flex items-center gap-2 rounded px-1 py-1 text-xs ${
                    invited ? "text-slate-400" : "text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={invited || selected.has(employee.id)}
                    disabled={invited}
                    onChange={() => toggle(employee.id)}
                  />
                  <span>
                    {employee.username} {employee.specialty ? `— ${employee.specialty}` : ""}
                  </span>
                  {invited && <span className="text-[10px] font-bold text-blue-600">مدعوٌّ سلفاً</span>}
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
          className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "..." : `دعوة (${formatNumber(selected.size)})`}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg bg-white px-3.5 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 border border-slate-200"
        >
          إغلاق
        </button>
      </div>
    </div>
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

  useEffect(() => { void load(); }, [load]);

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
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3" dir="rtl">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-800">دفترُ حضور «{meeting.title}»</h3>
        <button type="button" onClick={onClose} className="text-[11px] text-slate-500 underline">
          إغلاق
        </button>
      </div>
      {loading ? (
        <p className="text-xs text-slate-400">جاري التحميل...</p>
      ) : !rows || rows.length === 0 ? (
        <p className="text-xs text-slate-400">لا مدعوّون بعد.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-bold text-slate-600">
            <span>مدعوّون {formatNumber(counts.total)}</span>
            <span className="text-emerald-700">حضر {formatNumber(counts.attended)}</span>
            <span className="text-rose-700">غاب بلا عذر {formatNumber(counts.absent)}</span>
            {counts.excusedPending > 0 && (
              <span className="text-amber-700">عذرٌ بانتظار البتّ {formatNumber(counts.excusedPending)}</span>
            )}
            {counts.excusedAccepted > 0 && (
              <span className="text-blue-700">عذرٌ مقبول {formatNumber(counts.excusedAccepted)}</span>
            )}
            {counts.excusedRejected > 0 && (
              <span className="text-rose-700">عذرٌ مرفوض {formatNumber(counts.excusedRejected)}</span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-2 text-right">الموظّف</th>
                  <th className="py-2 px-2 text-right">الحالة</th>
                  <th className="py-2 px-2 text-right">وقت الدخول</th>
                  <th className="py-2 px-2 text-right">سبب العذر</th>
                  <th className="py-2 px-2 text-right">البتّ</th>
                  <th className="py-2 px-2 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 align-top">
                    <td className="py-1.5 pr-2 font-medium text-slate-700">{row.employee_name}</td>
                    <td className="py-1.5 px-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          row.status === "attended"
                            ? "bg-emerald-100 text-emerald-700"
                            : row.status === "excused_pending"
                            ? "bg-amber-100 text-amber-700"
                            : row.status === "excused_accepted"
                            ? "bg-blue-100 text-blue-700"
                            : row.status === "excused_rejected"
                            ? "bg-rose-100 text-rose-700"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {row.status_display}
                      </span>
                    </td>
                    <td className="py-1.5 px-2">{row.checked_in_at ? formatDateTimeValue(row.checked_in_at) : "—"}</td>
                    <td className="py-1.5 px-2">{row.excuse_note || "—"}</td>
                    <td className="py-1.5 px-2 text-slate-500">
                      {row.excuse_decided_by_name
                        ? `${row.excuse_decided_by_name} — ${formatDateTimeValue(row.excuse_decided_at)}`
                        : "—"}
                    </td>
                    <td className="py-1.5 px-2 whitespace-nowrap">
                      {row.status === "excused_pending" && (
                        <div className="flex gap-1">
                          <button
                            type="button"
                            disabled={busyId === row.id}
                            onClick={() => void decide(row, true)}
                            className="rounded-lg bg-emerald-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                          >
                            قبول
                          </button>
                          <button
                            type="button"
                            disabled={busyId === row.id}
                            onClick={() => void decide(row, false)}
                            className="rounded-lg bg-rose-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                          >
                            رفض
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
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

  useEffect(() => { void load(); }, [load]);

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
    <section className="space-y-4" dir="rtl">
      <div className="flex items-center gap-2">
        <CalendarClock className="h-4 w-4 text-slate-500" />
        <h2 className="text-sm font-bold text-slate-800">الاجتماعات</h2>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-xs font-bold text-slate-700">اجتماعٌ جديد</h3>
        <MeetingForm key={formSeq} submitLabel="إنشاء الاجتماع" busy={creating} onSubmit={submitCreate} />
      </div>

      {error && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="rounded-lg bg-rose-100 px-3 py-1 text-[11px] font-bold hover:bg-rose-200">
            إعادة المحاولة
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
      ) : !meetings || meetings.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-xs text-slate-400">
          لا اجتماعات مجدولة بعد.
        </div>
      ) : (
        <ul className="space-y-3">
          {meetings.map((meeting) => (
            <li key={meeting.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-bold text-slate-800">{meeting.title}</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}
                  </p>
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                    <Users className="h-3 w-3" /> مدعوّون: {formatNumber(meeting.invited_count)}
                  </p>
                  {meeting.agenda && <p className="mt-1 text-[11px] text-slate-500">{meeting.agenda}</p>}
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-blue-600">
                    <Video className="h-3 w-3" /> {meeting.meeting_link}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                    meeting.status === "scheduled"
                      ? "bg-blue-100 text-blue-700"
                      : meeting.status === "cancelled"
                      ? "bg-rose-100 text-rose-700"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {MEETING_STATUS_LABEL[meeting.status]}
                </span>
              </div>

              {meeting.status === "scheduled" && (
                <>
                  {editingId === meeting.id ? (
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
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setEditingId(meeting.id)}
                        className="rounded-lg bg-slate-100 px-3 py-1.5 text-[11px] font-bold text-slate-700 hover:bg-slate-200"
                      >
                        تعديل
                      </button>
                      <button
                        type="button"
                        disabled={busyId === meeting.id}
                        onClick={() => void cancel(meeting)}
                        className="rounded-lg bg-rose-50 px-3 py-1.5 text-[11px] font-bold text-rose-700 hover:bg-rose-100 disabled:opacity-50"
                      >
                        إلغاء الاجتماع
                      </button>
                      <button
                        type="button"
                        onClick={() => setInviteMeeting(meeting)}
                        className="rounded-lg bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700 hover:bg-blue-100"
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
                className="text-[11px] font-bold text-slate-600 underline"
              >
                دفتر الحضور
              </button>

              {inviteMeeting?.id === meeting.id && (
                <InvitePicker meeting={meeting} onClose={() => setInviteMeeting(null)} onInvited={() => void load()} />
              )}

              {attendanceMeeting?.id === meeting.id && (
                <AttendanceBook meeting={meeting} onClose={() => setAttendanceMeeting(null)} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default MeetingsPanel;
