import React, { useCallback, useEffect, useState } from "react";
import { CalendarDays, Loader2, MapPin, Plus, RefreshCw, Users } from "lucide-react";

import {
  createApplicantMeeting,
  getApplicantMeeting,
  listApplicantMeetings,
  type ApplicantMeeting,
} from "../../services/platformHiringApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import { PlatformMeetingDetail } from "./PlatformMeetingDetail";

export const PlatformMeetingsTab: React.FC = () => {
  const [meetings, setMeetings] = useState<ApplicantMeeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selectedMeeting, setSelectedMeeting] = useState<ApplicantMeeting | null>(null);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [openingError, setOpeningError] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [location, setLocation] = useState("");
  const [agenda, setAgenda] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const loadMeetings = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setMeetings(await listApplicantMeetings());
    } catch (err: unknown) {
      setMeetings([]);
      setLoadError(humanizeThrown(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMeetings();
  }, [loadMeetings]);

  const openMeeting = async (meetingId: number) => {
    setOpeningId(meetingId);
    setOpeningError("");
    try {
      setSelectedMeeting(await getApplicantMeeting(meetingId));
    } catch (err: unknown) {
      setOpeningError(humanizeThrown(err));
    } finally {
      setOpeningId(null);
    }
  };

  const closeCreateForm = () => {
    setShowCreateForm(false);
    setCreateError("");
  };

  const createMeeting = async (event: React.FormEvent) => {
    event.preventDefault();
    setCreating(true);
    setCreateError("");
    try {
      const meeting = await createApplicantMeeting({
        title: title.trim(),
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        location: location.trim() || undefined,
        agenda: agenda.trim() || undefined,
      });
      setMeetings((current) => [meeting, ...current]);
      setSelectedMeeting(meeting);
      closeCreateForm();
    } catch (err: unknown) {
      setCreateError(humanizeThrown(err));
    } finally {
      setCreating(false);
    }
  };

  const replaceMeeting = (updated: ApplicantMeeting) => {
    setSelectedMeeting(updated);
    setMeetings((current) => current.map((meeting) => (meeting.id === updated.id ? updated : meeting)));
  };

  if (selectedMeeting) {
    return (
      <PlatformMeetingDetail
        meeting={selectedMeeting}
        onBack={() => {
          setSelectedMeeting(null);
          void loadMeetings();
        }}
        onMeetingUpdated={replaceMeeting}
      />
    );
  }

  return (
    <div className="space-y-4 text-right" dir="rtl">
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white p-3 shadow-sm dark:bg-slate-900 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-slate-100">
            <CalendarDays className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            اجتماعات المتقدّمين
          </h2>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">سجّل الحضور وملاحظة مستقلة لكل شخص.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadMeetings()}
            disabled={loading}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            title="تحديث القائمة"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            type="button"
            onClick={() => setShowCreateForm(true)}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700"
          >
            <Plus className="h-4 w-4" />
            اجتماع جديد
          </button>
        </div>
      </div>

      {showCreateForm && (
        <form onSubmit={(event) => void createMeeting(event)} className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">اجتماع جديد</h3>
            <button type="button" onClick={closeCreateForm} className="text-xs font-semibold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200">إلغاء</button>
          </div>
          {createError && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">{createError}</div>}
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
            <button type="button" onClick={closeCreateForm} className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">إلغاء</button>
            <button type="submit" disabled={creating} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50">
              {creating && <Loader2 className="h-4 w-4 animate-spin" />}
              إنشاء الاجتماع
            </button>
          </div>
        </form>
      )}

      {openingError && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">{openingError}</div>}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-10 text-xs text-slate-500 dark:text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />جارٍ تحميل الاجتماعات...</div>
        ) : loadError ? (
          <div className="space-y-3 p-8 text-center"><p className="text-xs font-semibold text-rose-600 dark:text-rose-400">{loadError}</p><button type="button" onClick={() => void loadMeetings()} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700">إعادة المحاولة</button></div>
        ) : meetings.length === 0 ? (
          <div className="p-10 text-center text-xs text-slate-500 dark:text-slate-400">لا توجد اجتماعات متقدّمين بعد.</div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {meetings.map((meeting) => (
              <button key={meeting.id} type="button" onClick={() => void openMeeting(meeting.id)} disabled={openingId === meeting.id} className="grid w-full grid-cols-1 gap-3 p-4 text-right transition hover:bg-blue-50/50 disabled:opacity-50 dark:hover:bg-blue-950/20 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center">
                <div>
                  <div className="font-semibold text-slate-900 dark:text-slate-100">{meeting.title}</div>
                  <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}</div>
                  {meeting.location && <div className="mt-1 inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400"><MapPin className="h-3.5 w-3.5" />{meeting.location}</div>}
                </div>
                <span className="w-fit rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300">{meeting.status_display}</span>
                <span className="inline-flex items-center gap-1 text-xs text-slate-600 dark:text-slate-300"><Users className="h-3.5 w-3.5" />عدد الحاضرين: {formatNumber(meeting.attendee_count)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
