import React, { useCallback, useEffect, useState } from "react";
import {
  CalendarDays,
  Clock,
  Loader2,
  MapPin,
  Plus,
  RefreshCw,
  Users,
} from "lucide-react";

import {
  createApplicantMeeting,
  getApplicantMeeting,
  listApplicantMeetings,
  type ApplicantMeeting,
} from "../../services/platformHiringApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "../platform/ui";
import { ApplicantAttendanceMatrix } from "./ApplicantAttendanceMatrix";
import { PlatformMeetingDetail } from "./PlatformMeetingDetail";

interface PlatformMeetingsTabProps {
  onOpenApplicant: (id: number) => void;
}

const MEETING_TONE_MAP: Record<string, "accent" | "success" | "danger" | "neutral"> = {
  scheduled: "accent",
  finished: "success",
  cancelled: "danger",
};

const getMeetingRelativeTime = (startStr: string): string => {
  const diffMs = new Date(startStr).getTime() - Date.now();
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (Math.abs(diffDays) >= 1) {
    return diffDays > 0 ? `بعد ${formatNumber(diffDays)} يوم` : `منذ ${formatNumber(Math.abs(diffDays))} يوم`;
  }
  if (Math.abs(diffHours) >= 1) {
    return diffHours > 0 ? `بعد ${formatNumber(diffHours)} ساعة` : `منذ ${formatNumber(Math.abs(diffHours))} ساعة`;
  }
  return "اليوم";
};

export const PlatformMeetingsTab: React.FC<PlatformMeetingsTabProps> = ({
  onOpenApplicant,
}: PlatformMeetingsTabProps) => {
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
  const [view, setView] = useState<"list" | "matrix">("list");
  const [gridRefresh, setGridRefresh] = useState(0);

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

  return (
    <>
      {selectedMeeting && (
        <PlatformMeetingDetail
          meeting={selectedMeeting}
          onBack={() => {
            setSelectedMeeting(null);
            setGridRefresh((token) => token + 1);
            void loadMeetings();
          }}
          onMeetingUpdated={replaceMeeting}
        />
      )}

      <div className="space-y-4 text-right" dir="rtl" hidden={selectedMeeting !== null}>
        {/* شريط التحكم بالاجتماعات */}
        <div className="flex flex-col gap-3 rounded-xl border border-cc-border bg-cc-surface p-3.5 shadow-cc-card sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-bold text-cc-text">
              <CalendarDays className="h-4 w-4 text-sky-400" />
              اجتماعات المتقدّمين
            </h2>
            <p className="mt-0.5 text-xs text-cc-text-muted">
              سجّل الحضور وملاحظة مستقلة لكل شخص مع إدارة المواعيد.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg border border-cc-border bg-cc-surface-2 p-1">
              <button
                type="button"
                onClick={() => setView("list")}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
                  view === "list"
                    ? "bg-cc-surface text-sky-400 shadow-sm"
                    : "text-cc-text-muted hover:text-cc-text"
                }`}
              >
                قائمة
              </button>
              <button
                type="button"
                onClick={() => setView("matrix")}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
                  view === "matrix"
                    ? "bg-cc-surface text-sky-400 shadow-sm"
                    : "text-cc-text-muted hover:text-cc-text"
                }`}
              >
                شبكة الحضور
              </button>
            </div>

            {view === "list" && (
              <button
                type="button"
                onClick={() => void loadMeetings()}
                disabled={loading}
                className="rounded-lg p-2 text-cc-text-muted hover:text-cc-text bg-cc-surface-2 hover:bg-cc-surface border border-cc-border transition disabled:opacity-50"
                title="تحديث القائمة"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              </button>
            )}

            <button
              type="button"
              onClick={() => setShowCreateForm(true)}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-sky-500"
            >
              <Plus className="h-4 w-4" />
              <span>اجتماع جديد</span>
            </button>
          </div>
        </div>

        {/* نموذج إنشاء اجتماع جديد */}
        {showCreateForm && (
          <CcCard className="p-5 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-cc-border">
              <h3 className="text-sm font-bold text-cc-text">إنشاء اجتماع جديد</h3>
              <button
                type="button"
                onClick={closeCreateForm}
                className="text-xs font-semibold text-cc-text-muted hover:text-cc-text"
              >
                إلغاء
              </button>
            </div>

            {createError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-300">
                {createError}
              </div>
            )}

            <form onSubmit={(event) => void createMeeting(event)} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <label className="text-xs font-semibold text-cc-text">
                  العنوان <span className="text-rose-400">*</span>
                  <input
                    required
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="مثال: مقابلة وظيفية أولى"
                    className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </label>
                <label className="text-xs font-semibold text-cc-text">
                  المكان أو الرابط
                  <input
                    value={location}
                    onChange={(event) => setLocation(event.target.value)}
                    placeholder="غرفة الاجتماعات 1 / رابط Google Meet"
                    className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </label>
                <label className="text-xs font-semibold text-cc-text">
                  البداية <span className="text-rose-400">*</span>
                  <input
                    required
                    type="datetime-local"
                    value={start}
                    onChange={(event) => setStart(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </label>
                <label className="text-xs font-semibold text-cc-text">
                  النهاية <span className="text-rose-400">*</span>
                  <input
                    required
                    type="datetime-local"
                    value={end}
                    onChange={(event) => setEnd(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </label>
              </div>

              <label className="block text-xs font-semibold text-cc-text">
                جدول الأعمال
                <textarea
                  value={agenda}
                  onChange={(event) => setAgenda(event.target.value)}
                  rows={3}
                  placeholder="محاور المقابلة والنقاط المراد نقاشها..."
                  className="mt-1 w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </label>

              <div className="flex justify-end gap-2 border-t border-cc-border pt-4">
                <button
                  type="button"
                  onClick={closeCreateForm}
                  className="rounded-lg px-4 py-2 text-xs font-semibold text-cc-text-muted hover:text-cc-text hover:bg-cc-surface-2 transition"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-sky-500 disabled:opacity-50"
                >
                  {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                  <span>إنشاء الاجتماع</span>
                </button>
              </div>
            </form>
          </CcCard>
        )}

        {openingError && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-300">
            {openingError}
          </div>
        )}

        {view === "matrix" ? (
          <ApplicantAttendanceMatrix
            onOpenMeeting={(id) => void openMeeting(id)}
            onOpenApplicant={onOpenApplicant}
            refreshToken={gridRefresh}
          />
        ) : (
          /* جدول الاجتماعات بـ CcTable مع وقت نسبي ورقاقة حالة */
          <CcTable>
            <CcThead>
              <tr>
                <CcTh>عنوان الاجتماع</CcTh>
                <CcTh>التوقيت</CcTh>
                <CcTh>المكان</CcTh>
                <CcTh>الحالة</CcTh>
                <CcTh className="text-center">عدد الحاضرين</CcTh>
                <CcTh className="text-center">الإجراء</CcTh>
              </tr>
            </CcThead>
            <tbody>
              {loading ? (
                <tr>
                  <CcTd colSpan={6} className="p-8 text-center">
                    <div className="flex items-center justify-center gap-2 text-xs text-cc-text-muted">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>جارٍ تحميل الاجتماعات...</span>
                    </div>
                  </CcTd>
                </tr>
              ) : loadError ? (
                <tr>
                  <CcTd colSpan={6} className="p-8 text-center">
                    <div className="space-y-3">
                      <p className="text-xs font-semibold text-rose-400">{loadError}</p>
                      <button
                        type="button"
                        onClick={() => void loadMeetings()}
                        className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-500 transition"
                      >
                        إعادة المحاولة
                      </button>
                    </div>
                  </CcTd>
                </tr>
              ) : meetings.length === 0 ? (
                <tr>
                  <CcTd colSpan={6} className="p-8 text-center">
                    <CcEmpty
                      title="لا توجد اجتماعات متقدّمين بعد"
                      hint="يمكنك جدولة أول اجتماع للمرشحين للبدء في تتبع الحضور."
                    />
                  </CcTd>
                </tr>
              ) : (
                meetings.map((meeting) => {
                  const tone = MEETING_TONE_MAP[meeting.status] || "neutral";
                  const relTime = getMeetingRelativeTime(meeting.start);

                  return (
                    <CcTr key={meeting.id}>
                      <CcTd className="font-semibold">
                        <button
                          type="button"
                          onClick={() => void openMeeting(meeting.id)}
                          className="text-right text-cc-text hover:text-sky-400 transition font-bold"
                        >
                          {meeting.title}
                        </button>
                        {meeting.created_by_name && (
                          <div className="text-[11px] text-cc-text-muted font-normal mt-0.5">
                            المنسق: {meeting.created_by_name}
                          </div>
                        )}
                      </CcTd>
                      <CcTd>
                        <div className="text-cc-text font-medium">
                          {formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}
                        </div>
                        <div className="text-[11px] text-sky-400 flex items-center gap-1 mt-0.5">
                          <Clock className="w-3 h-3" />
                          <span>{relTime}</span>
                        </div>
                      </CcTd>
                      <CcTd className="text-cc-text-muted">
                        {meeting.location ? (
                          <span className="inline-flex items-center gap-1 text-xs text-cc-text">
                            <MapPin className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                            <span>{meeting.location}</span>
                          </span>
                        ) : (
                          <span>—</span>
                        )}
                      </CcTd>
                      <CcTd>
                        <CcPill tone={tone}>
                          {meeting.status_display}
                        </CcPill>
                      </CcTd>
                      <CcTd className="text-center font-bold text-cc-text">
                        <span className="inline-flex items-center gap-1">
                          <Users className="h-3.5 w-3.5 text-cc-text-muted" />
                          <span>{formatNumber(meeting.attendee_count)}</span>
                        </span>
                      </CcTd>
                      <CcTd className="text-center">
                        <button
                          type="button"
                          onClick={() => void openMeeting(meeting.id)}
                          disabled={openingId === meeting.id}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-sky-400 bg-sky-500/15 hover:bg-sky-500/25 rounded-lg border border-sky-500/30 transition disabled:opacity-50"
                        >
                          {openingId === meeting.id && <Loader2 className="w-3 h-3 animate-spin" />}
                          <span>عرض التفاصيل</span>
                        </button>
                      </CcTd>
                    </CcTr>
                  );
                })
              )}
            </tbody>
          </CcTable>
        )}
      </div>
    </>
  );
};
