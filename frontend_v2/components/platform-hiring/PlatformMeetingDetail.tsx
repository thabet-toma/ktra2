import React, { useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Loader2,
  MapPin,
  Pencil,
  Plus,
  Save,
  Trash2,
  UserPlus,
  Users,
  XCircle,
} from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import {
  addApplicantMeetingAttendee,
  listPlatformApplicants,
  recordApplicantMeetingAttendee,
  removeApplicantMeetingAttendee,
  updateApplicantMeeting,
  type ApplicantMeeting,
  type ApplicantMeetingAttendee,
  type PlatformJobApplicant,
} from "../../services/platformHiringApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcStatTile,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "../platform/ui";

interface PlatformMeetingDetailProps {
  meeting: ApplicantMeeting;
  onBack: () => void;
  onMeetingUpdated: (meeting: ApplicantMeeting) => void;
}

const ATTENDANCE_BUTTONS: Array<{
  value: ApplicantMeetingAttendee["status"];
  label: string;
  activeClass: string;
  idleClass: string;
}> = [
  {
    value: "invited",
    label: "مدعوّ",
    activeClass: "bg-amber-500/20 text-amber-300 border-amber-500/40 ring-1 ring-amber-400",
    idleClass: "bg-cc-surface-2 text-cc-text-muted border-cc-border hover:text-cc-text",
  },
  {
    value: "attended",
    label: "حضر",
    activeClass: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 ring-1 ring-emerald-400",
    idleClass: "bg-cc-surface-2 text-cc-text-muted border-cc-border hover:text-cc-text",
  },
  {
    value: "absent",
    label: "لم يحضر",
    activeClass: "bg-rose-500/20 text-rose-300 border-rose-500/40 ring-1 ring-rose-400",
    idleClass: "bg-cc-surface-2 text-cc-text-muted border-cc-border hover:text-cc-text",
  },
];

const MEETING_TONE_MAP: Record<string, "accent" | "success" | "danger" | "neutral"> = {
  scheduled: "accent",
  finished: "success",
  cancelled: "danger",
};

const isoToDateTimeLocal = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};

export const PlatformMeetingDetail: React.FC<PlatformMeetingDetailProps> = ({
  meeting,
  onBack,
  onMeetingUpdated,
}: PlatformMeetingDetailProps) => {
  const confirm = useConfirm();
  const [applicants, setApplicants] = useState<PlatformJobApplicant[]>([]);
  const [loadingApplicants, setLoadingApplicants] = useState(true);
  const [selectedApplicant, setSelectedApplicant] = useState("");
  const [guestName, setGuestName] = useState("");
  const [savingAttendee, setSavingAttendee] = useState(false);
  const [busyAttendeeId, setBusyAttendeeId] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState("");
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [location, setLocation] = useState("");
  const [agenda, setAgenda] = useState("");
  const [savingMeeting, setSavingMeeting] = useState(false);

  // **`meeting.id` لا `meeting`**: كلُّ فعلٍ على حاضرٍ يُرجِع كائنَ اجتماعٍ جديداً،
  // فبالاعتماد على الكائن كانت هذه الحقنةُ تُعيد كتابةَ **كلّ** خانات الملاحظات من
  // الخادم — بما فيها ملاحظةٌ يكتبها المستخدمُ الآن في صفٍّ آخر ولم يحفظها بعد،
  // فيضيع نصُّه لأنّ زميله في الصفّ المجاور سُجّل حضورُه. والحقنةُ عند فتح
  // الاجتماع تكفي: هذه الشاشةُ هي الكاتبُ الوحيدُ لهذه الحقول، والصفُّ الجديد
  // يقرأ `?? ""`.
  useEffect(() => {
    setNotes(Object.fromEntries(meeting.attendees.map((attendee) => [attendee.id, attendee.note])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting.id]);

  useEffect(() => {
    let active = true;
    listPlatformApplicants()
      .then((items) => { if (active) setApplicants(items); })
      .catch((err: unknown) => { if (active) setActionError(humanizeThrown(err)); })
      .finally(() => { if (active) setLoadingApplicants(false); });
    return () => { active = false; };
  }, []);

  /**
  * **لا يُعرَض في المنتقي من رفضه الخادمُ سلفاً.** `add_meeting_attendee` تردّ
  * ٤٠٠ على من صار موظّفاً («هذه الاجتماعاتُ لمن لم يُوظَّف بعد»)، وقائمةُ
  * `job-applicants` تشمل الجميع — فكان المنتقي يعرض خياراً يفشل كلَّما اختير.
  * والسلطةُ تبقى في الخدمة: هذا تضييقُ عرضٍ لا نسخةٌ ثانيةٌ من القاعدة، وحارسٌ
  * ساكنٌ يربط هذا النصَّ بـ`JobApplicant.Status.HIRED` فلا يفترقان.
  */
  const selectableApplicants = applicants.filter((applicant) => applicant.status !== "hired");

  const totalAttendees = meeting.attendees.length;
  const attendedCount = meeting.attendees.filter((a) => a.status === "attended").length;
  const absentCount = meeting.attendees.filter((a) => a.status === "absent").length;
  const invitedCount = meeting.attendees.filter((a) => a.status === "invited").length;

  const applyMeeting = (updated: ApplicantMeeting) => {
    setActionError("");
    onMeetingUpdated(updated);
  };

  const openEditForm = () => {
    setTitle(meeting.title);
    setStart(isoToDateTimeLocal(meeting.start));
    setEnd(isoToDateTimeLocal(meeting.end));
    setLocation(meeting.location);
    setAgenda(meeting.agenda);
    setActionError("");
    setEditing(true);
  };

  const saveMeeting = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingMeeting(true);
    setActionError("");
    try {
      applyMeeting(await updateApplicantMeeting(meeting.id, {
        title: title.trim(),
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        location: location.trim(),
        agenda: agenda.trim(),
      }));
      setEditing(false);
    } catch (err: unknown) {
      setActionError(humanizeThrown(err));
    } finally {
      setSavingMeeting(false);
    }
  };

  const changeMeetingStatus = async (status: "finished" | "cancelled") => {
    const accepted = await confirm({
      title: status === "finished" ? "إنهاء الاجتماع" : "إلغاء الاجتماع",
      message: status === "finished"
        ? "هل تريد إعلان هذا الاجتماع منتهياً؟"
        : "هل تريد إلغاء هذا الاجتماع؟",
      confirmText: status === "finished" ? "إنهاء الاجتماع" : "إلغاء الاجتماع",
      danger: status === "cancelled",
    });
    if (!accepted) return;
    setSavingMeeting(true);
    setActionError("");
    try {
      applyMeeting(await updateApplicantMeeting(meeting.id, { status }));
    } catch (err: unknown) {
      setActionError(humanizeThrown(err));
    } finally {
      setSavingMeeting(false);
    }
  };

  const addApplicant = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingAttendee(true);
    setActionError("");
    try {
      applyMeeting(await addApplicantMeetingAttendee(meeting.id, { applicant: Number(selectedApplicant) }));
      setSelectedApplicant("");
    } catch (err: unknown) {
      setActionError(humanizeThrown(err));
    } finally {
      setSavingAttendee(false);
    }
  };

  const addGuest = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingAttendee(true);
    setActionError("");
    try {
      applyMeeting(await addApplicantMeetingAttendee(meeting.id, { guest_name: guestName.trim() }));
      setGuestName("");
    } catch (err: unknown) {
      setActionError(humanizeThrown(err));
    } finally {
      setSavingAttendee(false);
    }
  };

  const recordAttendee = async (attendee: ApplicantMeetingAttendee, input: { status?: ApplicantMeetingAttendee["status"]; note?: string }) => {
    setBusyAttendeeId(attendee.id);
    setActionError("");
    try {
      applyMeeting(await recordApplicantMeetingAttendee(meeting.id, { attendee: attendee.id, ...input }));
    } catch (err: unknown) {
      setActionError(humanizeThrown(err));
    } finally {
      setBusyAttendeeId(null);
    }
  };

  const removeAttendee = async (attendee: ApplicantMeetingAttendee) => {
    const accepted = await confirm({
      title: "إزالة الحاضر",
      message: `هل تريد إزالة «${attendee.name}» من هذا الاجتماع؟`,
      confirmText: "إزالة الحاضر",
      danger: true,
    });
    if (!accepted) return;
    setBusyAttendeeId(attendee.id);
    setActionError("");
    try {
      applyMeeting(await removeApplicantMeetingAttendee(meeting.id, attendee.id));
    } catch (err: unknown) {
      setActionError(humanizeThrown(err));
    } finally {
      setBusyAttendeeId(null);
    }
  };

  const statusTone = MEETING_TONE_MAP[meeting.status] || "neutral";

  return (
    <div className="space-y-5 text-right" dir="rtl">
      {/* 1. رأس تفاصيل الاجتماع بـ CcCard */}
      <CcCard className="p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <button
              type="button"
              onClick={onBack}
              className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-sky-400 hover:text-sky-300 transition"
            >
              <ArrowRight className="h-4 w-4" />
              العودة إلى الاجتماعات
            </button>
            <h2 className="text-xl font-bold text-cc-text">{meeting.title}</h2>
            <div className="mt-1 flex items-center gap-2 text-xs text-cc-text-muted flex-wrap">
              <span>{formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}</span>
              {meeting.location && (
                <>
                  <span>•</span>
                  <span className="inline-flex items-center gap-1 text-cc-text">
                    <MapPin className="h-3.5 w-3.5 text-sky-400" />
                    {meeting.location}
                  </span>
                </>
              )}
            </div>
            {meeting.agenda && (
              <p className="mt-3 text-xs leading-relaxed text-cc-text-muted max-w-2xl">
                {meeting.agenda}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <CcPill tone={statusTone}>
              {meeting.status_display}
            </CcPill>
            <button
              type="button"
              onClick={openEditForm}
              disabled={savingMeeting}
              className="inline-flex items-center gap-1 rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-semibold text-cc-text transition hover:bg-cc-surface disabled:opacity-50"
            >
              <Pencil className="h-3.5 w-3.5" />
              تعديل
            </button>
            {meeting.status !== "finished" && (
              <button
                type="button"
                onClick={() => void changeMeetingStatus("finished")}
                disabled={savingMeeting}
                className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-400 transition hover:bg-emerald-500/25 disabled:opacity-50"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                إنهاء الاجتماع
              </button>
            )}
            {meeting.status !== "cancelled" && (
              <button
                type="button"
                onClick={() => void changeMeetingStatus("cancelled")}
                disabled={savingMeeting}
                className="inline-flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/15 px-3 py-1.5 text-xs font-semibold text-rose-400 transition hover:bg-rose-500/25 disabled:opacity-50"
              >
                <XCircle className="h-3.5 w-3.5" />
                إلغاء الاجتماع
              </button>
            )}
          </div>
        </div>
      </CcCard>

      {/* 2. صف أرقام الحضور بـ CcStatTile */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <CcCard className="p-4">
          <CcStatTile
            label="إجمالي الحاضرين"
            value={totalAttendees}
            tone="neutral"
            icon={<Users className="w-4 h-4" />}
          />
        </CcCard>
        <CcCard className="p-4">
          <CcStatTile
            label="حضروا"
            value={attendedCount}
            tone="success"
          />
        </CcCard>
        <CcCard className="p-4">
          <CcStatTile
            label="لم يحضروا"
            value={absentCount}
            tone="danger"
          />
        </CcCard>
        <CcCard className="p-4">
          <CcStatTile
            label="مدعوون"
            value={invitedCount}
            tone="warning"
          />
        </CcCard>
      </div>

      {/* نموذج التعديل */}
      {editing && (
        <CcCard className="p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-cc-border">
            <h3 className="text-sm font-bold text-cc-text">تعديل بيانات الاجتماع</h3>
            <button
              type="button"
              onClick={() => setEditing(false)}
              disabled={savingMeeting}
              className="text-xs font-semibold text-cc-text-muted hover:text-cc-text"
            >
              إلغاء
            </button>
          </div>

          <form onSubmit={(event) => void saveMeeting(event)} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="text-xs font-semibold text-cc-text">
                العنوان <span className="text-rose-400">*</span>
                <input
                  required
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:ring-2 focus:ring-sky-500 outline-none"
                />
              </label>
              <label className="text-xs font-semibold text-cc-text">
                المكان أو الرابط
                <input
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:ring-2 focus:ring-sky-500 outline-none"
                />
              </label>
              <label className="text-xs font-semibold text-cc-text">
                البداية <span className="text-rose-400">*</span>
                <input
                  required
                  type="datetime-local"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:ring-2 focus:ring-sky-500 outline-none"
                />
              </label>
              <label className="text-xs font-semibold text-cc-text">
                النهاية <span className="text-rose-400">*</span>
                <input
                  required
                  type="datetime-local"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:ring-2 focus:ring-sky-500 outline-none"
                />
              </label>
            </div>

            <label className="block text-xs font-semibold text-cc-text">
              جدول الأعمال
              <textarea
                value={agenda}
                onChange={(event) => setAgenda(event.target.value)}
                rows={3}
                className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:ring-2 focus:ring-sky-500 outline-none"
              />
            </label>

            <div className="flex justify-end gap-2 border-t border-cc-border pt-4">
              <button
                type="button"
                onClick={() => setEditing(false)}
                disabled={savingMeeting}
                className="rounded-lg px-4 py-2 text-xs font-semibold text-cc-text-muted hover:text-cc-text hover:bg-cc-surface-2 transition"
              >
                إلغاء
              </button>
              <button
                type="submit"
                disabled={savingMeeting}
                className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-sky-500 disabled:opacity-50"
              >
                {savingMeeting && <Loader2 className="h-4 w-4 animate-spin" />}
                حفظ التعديلات
              </button>
            </div>
          </form>
        </CcCard>
      )}

      {actionError && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-300">
          {actionError}
        </div>
      )}

      {/* 3. إضافة حاضر جديد */}
      <CcCard className="p-5 space-y-3">
        <CcSectionTitle
          title="إضافة حاضر"
          subtitle="يمكنك إضافة مرشح من قائمة المتقدمين أو إدخال اسم ضيف من خارج الرابط"
        />

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 pt-2">
          <form onSubmit={(event) => void addApplicant(event)} className="flex gap-2">
            <select
              required
              value={selectedApplicant}
              onChange={(event) => setSelectedApplicant(event.target.value)}
              disabled={loadingApplicants || savingAttendee}
              className="min-w-0 flex-1 rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
            >
              <option value="">
                {loadingApplicants ? "جارٍ تحميل المتقدّمين..." : "اختر متقدّماً مسجلاً"}
              </option>
              {selectableApplicants.map((applicant) => (
                <option key={applicant.id} value={applicant.id}>
                  {applicant.name} — {applicant.status_display}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={savingAttendee || !selectedApplicant}
              className="inline-flex items-center gap-1 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50 transition"
            >
              <Plus className="h-3.5 w-3.5" />
              إضافة
            </button>
          </form>

          <form onSubmit={(event) => void addGuest(event)} className="flex gap-2">
            <input
              required
              value={guestName}
              onChange={(event) => setGuestName(event.target.value)}
              disabled={savingAttendee}
              placeholder="اسم ضيف من خارج المنصة..."
              className="min-w-0 flex-1 rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={savingAttendee || !guestName.trim()}
              className="inline-flex items-center gap-1 rounded-lg bg-cc-surface-2 border border-cc-border px-4 py-2 text-xs font-semibold text-cc-text hover:bg-cc-surface disabled:opacity-50 transition"
            >
              <Plus className="h-3.5 w-3.5" />
              إضافة ضيف
            </button>
          </form>
        </div>
      </CcCard>

      {/* 4. جدول الحاضرين بـ CcTable */}
      <div className="space-y-3">
        <CcSectionTitle
          title="قائمة الحاضرين"
          subtitle="تسجيل الحضور والملاحظة مستقلة لكل شخص"
          badge={totalAttendees}
        />

        <CcTable>
          <CcThead>
            <tr>
              <CcTh>الاسم</CcTh>
              <CcTh>حالة الحضور</CcTh>
              <CcTh className="w-[40%]">الملاحظة</CcTh>
              <CcTh className="text-center">إزالة</CcTh>
            </tr>
          </CcThead>
          <tbody>
            {meeting.attendees.length === 0 ? (
              <tr>
                <CcTd colSpan={4} className="p-8 text-center">
                  <CcEmpty
                    title="لا يوجد حاضرون مسجلون في هذا الاجتماع بعد"
                    hint="أضف متقدّماً أو اسماً حراً لبدء تسجيل الحضور وتوثيق المقابلات."
                  />
                </CcTd>
              </tr>
            ) : (
              meeting.attendees.map((attendee) => (
                <CcTr key={attendee.id}>
                  <CcTd className="align-top">
                    <div className="font-bold text-cc-text">{attendee.name}</div>
                    {attendee.applicant === null ? (
                      <span className="mt-1 inline-flex rounded-full border border-purple-500/30 bg-purple-500/15 px-2 py-0.5 text-[10px] font-semibold text-purple-300">
                        من خارج الرابط
                      </span>
                    ) : (
                      <div className="mt-0.5 text-[11px] text-cc-text-muted">
                        {attendee.job_title}
                      </div>
                    )}
                  </CcTd>
                  <CcTd className="align-top">
                    <div className="flex gap-1.5">
                      {ATTENDANCE_BUTTONS.map((opt) => {
                        const isCurrent = attendee.status === opt.value;
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            disabled={busyAttendeeId === attendee.id}
                            onClick={() => void recordAttendee(attendee, { status: opt.value })}
                            className={`rounded-lg border px-2.5 py-1 text-xs font-semibold transition disabled:opacity-50 ${
                              isCurrent ? opt.activeClass : opt.idleClass
                            }`}
                          >
                            {opt.label}
                          </button>
                        );
                      })}
                    </div>
                  </CcTd>
                  <CcTd className="align-top">
                    <div className="flex gap-2">
                      <input
                        value={notes[attendee.id] ?? ""}
                        onChange={(event) =>
                          setNotes((current) => ({ ...current, [attendee.id]: event.target.value }))
                        }
                        onBlur={() => {
                          const note = notes[attendee.id] ?? "";
                          if (note !== attendee.note) void recordAttendee(attendee, { note });
                        }}
                        disabled={busyAttendeeId === attendee.id}
                        placeholder="اكتب ملاحظة هذا الشخص..."
                        className="min-w-[200px] flex-1 rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
                      />
                      <button
                        type="button"
                        title="حفظ الملاحظة"
                        disabled={busyAttendeeId === attendee.id || (notes[attendee.id] ?? "") === attendee.note}
                        onClick={() => void recordAttendee(attendee, { note: notes[attendee.id] ?? "" })}
                        className="rounded-lg border border-sky-500/30 bg-sky-500/15 p-2 text-sky-400 hover:bg-sky-500/25 disabled:opacity-50 transition"
                      >
                        <Save className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </CcTd>
                  <CcTd className="text-center align-top">
                    <button
                      type="button"
                      title="إزالة الحاضر"
                      disabled={busyAttendeeId === attendee.id}
                      onClick={() => void removeAttendee(attendee)}
                      className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-400 hover:bg-rose-500/20 disabled:opacity-50 transition"
                    >
                      {busyAttendeeId === attendee.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </CcTd>
                </CcTr>
              ))
            )}
          </tbody>
        </CcTable>
      </div>
    </div>
  );
};
