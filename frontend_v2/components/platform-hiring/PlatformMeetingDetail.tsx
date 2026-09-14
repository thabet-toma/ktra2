import React, { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Loader2, Pencil, Plus, Save, Trash2, UserPlus, Users, XCircle } from "lucide-react";

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
import { humanizeThrown } from "../../utils/drfError";

interface PlatformMeetingDetailProps {
  meeting: ApplicantMeeting;
  onBack: () => void;
  onMeetingUpdated: (meeting: ApplicantMeeting) => void;
}

const STATUS_OPTIONS: Array<{ value: ApplicantMeetingAttendee["status"]; label: string; className: string }> = [
  { value: "invited", label: "مدعوّ", className: "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  { value: "attended", label: "حضر", className: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300" },
  { value: "absent", label: "لم يحضر", className: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300" },
];

const isoToDateTimeLocal = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};

export const PlatformMeetingDetail: React.FC<PlatformMeetingDetailProps> = ({ meeting, onBack, onMeetingUpdated }) => {
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

  return (
    <div className="space-y-4 text-right" dir="rtl">
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"><ArrowRight className="h-4 w-4" />العودة إلى الاجتماعات</button>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">{meeting.title}</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}{meeting.location ? ` · ${meeting.location}` : ""}</p>
          {meeting.agenda && <p className="mt-2 text-xs leading-6 text-slate-600 dark:text-slate-300">{meeting.agenda}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-fit rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300">{meeting.status_display}</span>
          <button type="button" onClick={openEditForm} disabled={savingMeeting} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"><Pencil className="h-3.5 w-3.5" />تعديل</button>
          {meeting.status !== "finished" && <button type="button" onClick={() => void changeMeetingStatus("finished")} disabled={savingMeeting} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-900/50"><CheckCircle2 className="h-3.5 w-3.5" />إنهاء الاجتماع</button>}
          {meeting.status !== "cancelled" && <button type="button" onClick={() => void changeMeetingStatus("cancelled")} disabled={savingMeeting} className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 disabled:opacity-50 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300 dark:hover:bg-rose-900/50"><XCircle className="h-3.5 w-3.5" />إلغاء الاجتماع</button>}
        </div>
      </div>

      {editing && (
        <form onSubmit={(event) => void saveMeeting(event)} className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">تعديل الاجتماع</h3>
            <button type="button" onClick={() => setEditing(false)} disabled={savingMeeting} className="text-xs font-semibold text-slate-500 hover:text-slate-700 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200">إلغاء</button>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">العنوان <span className="text-rose-500">*</span>
              <input required value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">المكان أو الرابط
              <input value={location} onChange={(event) => setLocation(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">البداية <span className="text-rose-500">*</span>
              <input required type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">النهاية <span className="text-rose-500">*</span>
              <input required type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>
          </div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">جدول الأعمال
            <textarea value={agenda} onChange={(event) => setAgenda(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
          </label>
          <div className="flex justify-end gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
            <button type="button" onClick={() => setEditing(false)} disabled={savingMeeting} className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800">إلغاء</button>
            <button type="submit" disabled={savingMeeting} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50">{savingMeeting && <Loader2 className="h-4 w-4 animate-spin" />}حفظ التعديلات</button>
          </div>
        </form>
      )}

      {actionError && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">{actionError}</div>}

      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2"><UserPlus className="h-4 w-4 text-blue-600 dark:text-blue-400" /><h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">إضافة حاضر</h3></div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <form onSubmit={(event) => void addApplicant(event)} className="flex gap-2">
            <select required value={selectedApplicant} onChange={(event) => setSelectedApplicant(event.target.value)} disabled={loadingApplicants || savingAttendee} className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100">
              <option value="">{loadingApplicants ? "جارٍ تحميل المتقدّمين..." : "اختر متقدّماً"}</option>
              {selectableApplicants.map((applicant) => <option key={applicant.id} value={applicant.id}>{applicant.name} — {applicant.status_display}</option>)}
            </select>
            <button type="submit" disabled={savingAttendee || !selectedApplicant} className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"><Plus className="h-3.5 w-3.5" />إضافة</button>
          </form>
          <form onSubmit={(event) => void addGuest(event)} className="flex gap-2">
            <input required value={guestName} onChange={(event) => setGuestName(event.target.value)} disabled={savingAttendee} placeholder="اسم من خارج الرابط" className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            <button type="submit" disabled={savingAttendee || !guestName.trim()} className="inline-flex items-center gap-1 rounded-lg bg-slate-700 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-slate-700 dark:hover:bg-slate-600"><Plus className="h-3.5 w-3.5" />إضافة</button>
          </form>
        </div>
      </section>

      <section className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 p-4 dark:border-slate-800"><h3 className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-slate-100"><Users className="h-4 w-4 text-blue-600 dark:text-blue-400" />الحاضرون</h3><span className="text-xs text-slate-500 dark:text-slate-400">حالة الحضور والملاحظة تحفظان لكل شخص</span></div>
        <table className="min-w-[820px] w-full text-right text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 font-semibold text-slate-700 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300"><tr><th className="p-3">الاسم</th><th className="p-3">الحضور</th><th className="w-[36%] p-3">الملاحظة</th><th className="p-3 text-center">إزالة</th></tr></thead>
          <tbody className="divide-y divide-slate-100 text-slate-800 dark:divide-slate-800/80 dark:text-slate-200">
            {meeting.attendees.length === 0 ? (
              <tr><td colSpan={4} className="p-10 text-center text-slate-500 dark:text-slate-400">أضف متقدّماً أو اسماً حراً لبدء تسجيل الحضور.</td></tr>
            ) : meeting.attendees.map((attendee) => (
              <tr key={attendee.id}>
                <td className="p-3 align-top"><div className="font-semibold text-slate-900 dark:text-slate-100">{attendee.name}</div>{attendee.applicant === null ? <span className="mt-1 inline-flex rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300">من خارج الرابط</span> : <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{attendee.job_title}</div>}</td>
                <td className="p-3 align-top"><div className="flex gap-1">{STATUS_OPTIONS.map((option) => <button key={option.value} type="button" disabled={busyAttendeeId === attendee.id} onClick={() => void recordAttendee(attendee, { status: option.value })} className={`rounded-md border px-2 py-1 text-[11px] font-semibold transition disabled:opacity-50 ${option.className} ${attendee.status === option.value ? "ring-2 ring-offset-1 ring-blue-500 dark:ring-offset-slate-900" : "opacity-60 hover:opacity-100"}`}>{option.label}</button>)}</div></td>
                <td className="p-3 align-top"><div className="flex gap-2"><input value={notes[attendee.id] ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [attendee.id]: event.target.value }))} onBlur={() => { const note = notes[attendee.id] ?? ""; if (note !== attendee.note) void recordAttendee(attendee, { note }); }} disabled={busyAttendeeId === attendee.id} placeholder="اكتب ملاحظة هذا الشخص..." className="min-w-[230px] flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" /><button type="button" title="حفظ الملاحظة" disabled={busyAttendeeId === attendee.id || (notes[attendee.id] ?? "") === attendee.note} onClick={() => void recordAttendee(attendee, { note: notes[attendee.id] ?? "" })} className="rounded-lg border border-blue-200 bg-blue-50 p-2 text-blue-700 hover:bg-blue-100 disabled:opacity-50 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300 dark:hover:bg-blue-900/50"><Save className="h-3.5 w-3.5" /></button></div></td>
                <td className="p-3 text-center align-top"><button type="button" title="إزالة الحاضر" disabled={busyAttendeeId === attendee.id} onClick={() => void removeAttendee(attendee)} className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-rose-700 hover:bg-rose-100 disabled:opacity-50 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300 dark:hover:bg-rose-900/50">{busyAttendeeId === attendee.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
};
