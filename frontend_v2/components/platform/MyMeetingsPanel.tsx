import React, { useCallback, useEffect, useState } from "react";
import { CalendarClock, LogIn } from "lucide-react";

import {
  MEETING_ATTENDANCE_STATUS_LABEL,
  MEETING_STATUS_LABEL,
  checkInToMeeting,
  listPlatformMeetings,
  submitMeetingExcuse,
  type PlatformMeetingRow,
} from "../../services/platformMeetingsApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useToast } from "../../contexts/ToastContext";
import { CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton } from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذا الإجراء متاح لموظّفي عمليات المنصة فقط.", "تعذّر إتمام العملية.");

/**
 * نافذةُ الدخول: مطابقةٌ لـ`MEETING_CHECK_IN_EARLY_WINDOW_MINUTES` في
 * `platform_ops/services.py`.
 *
 * **وهي هنا تلميحٌ لا قفل.** الحسابُ يجري بساعة المتصفّح، وساعةُ جهازٍ مغلوطةٌ
 * بساعةٍ واحدةٍ تكفي لإطفاء الزرّ على موظّفٍ داخلَ النافذة فعلاً — فيُحرَم من
 * تسجيل حضورٍ **يرفع درجتَه ويُنزّلها** بلا مخرجٍ ولا رسالةٍ تشرح. فالزرُّ يبقى
 * قابلاً للنقر، والخادمُ — وساعتُه هي المرجع — يردّ `outside_check_in_window`
 * برسالةٍ عربيّةٍ صريحةٍ إن كان محقّاً. أسوأُ ما يقع: طلبٌ ضائع؛ وأسوأُ البديل:
 * موظّفٌ محبوسٌ خارجَ اجتماعه.
 *
 * (وهو نفسُ سببِ قراءةِ الاتّصال من حساب الخادم في `utils/roomPresence.ts`.)
 */
const CHECK_IN_EARLY_WINDOW_MINUTES = 15;

type CheckInAvailability = "too_early" | "open" | "too_late";

const checkInAvailability = (meeting: PlatformMeetingRow, now: Date): CheckInAvailability => {
  const start = new Date(meeting.start).getTime();
  const end = new Date(meeting.end).getTime();
  const windowStart = start - CHECK_IN_EARLY_WINDOW_MINUTES * 60_000;
  const nowMs = now.getTime();
  if (nowMs < windowStart) return "too_early";
  if (nowMs > end) return "too_late";
  return "open";
};

const MeetingRow: React.FC<{ meeting: PlatformMeetingRow; now: Date; onChanged: () => void }> = ({
  meeting,
  now,
  onChanged,
}) => {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [excusing, setExcusing] = useState(false);
  const [note, setNote] = useState("");

  const status = meeting.my_attendance_status;
  const cancelled = meeting.status === "cancelled";
  const attended = status === "attended";
  const availability = checkInAvailability(meeting, now);

  const handleCheckIn = async () => {
    setBusy(true);
    try {
      const result = await checkInToMeeting(meeting.id);
      window.open(result.meeting_link, "_blank", "noopener,noreferrer");
      toast("سُجِّل حضورُك.", "success");
      onChanged();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusy(false);
    }
  };

  const handleExcuse = async () => {
    const trimmed = note.trim();
    if (!trimmed) {
      toast("سببُ الاعتذار إلزاميّ.", "error");
      return;
    }
    setBusy(true);
    try {
      await submitMeetingExcuse(meeting.id, trimmed);
      toast("سُجِّل اعتذارُك.", "success");
      setExcusing(false);
      setNote("");
      onChanged();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusy(false);
    }
  };

  const checkInHint = cancelled
    ? "هذا الاجتماعُ ملغى."
    : availability === "too_early"
    ? `يفتح تسجيلُ الدخول قبل الموعد بـ${CHECK_IN_EARLY_WINDOW_MINUTES} دقيقة — بحسب ساعة جهازك.`
    : availability === "too_late"
    ? "انتهى وقتُ هذا الاجتماع بحسب ساعة جهازك."
    : "";

  return (
    <li className="list-none">
      <CcCard className="p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-xs sm:text-sm font-bold text-cc-text">{meeting.title}</p>
            <p className="text-[11px] text-sky-400 font-medium">
              {formatDateTimeValue(meeting.start)} — {formatDateTimeValue(meeting.end)}
            </p>
            {meeting.agenda && <p className="text-[11px] text-cc-text-muted mt-1">{meeting.agenda}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <CcPill tone={cancelled ? "danger" : "accent"}>
              {MEETING_STATUS_LABEL[meeting.status]}
            </CcPill>
            {status && (
              <CcPill tone={attended ? "success" : "neutral"}>
                {MEETING_ATTENDANCE_STATUS_LABEL[status]}
              </CcPill>
            )}
          </div>
        </div>

        {!cancelled && !attended && (
          <div className="space-y-2 border-t border-cc-border pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void handleCheckIn()}
                className="flex items-center gap-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50 transition-colors"
              >
                <LogIn className="h-3.5 w-3.5" /> تسجيل الدخول
              </button>
              {!excusing && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setExcusing(true)}
                  className="rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 px-3 py-1.5 text-xs font-semibold disabled:opacity-50 transition-colors"
                >
                  اعتذار
                </button>
              )}
            </div>
            {checkInHint && <p className="text-[11px] text-cc-text-muted">{checkInHint}</p>}
            {excusing && (
              <div className="space-y-2">
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="سببُ عدم الحضور — إلزاميّ"
                  rows={2}
                  className="w-full rounded-lg bg-cc-bg border border-cc-border px-3 py-2 text-xs text-cc-text focus:outline-none focus:border-sky-500"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleExcuse()}
                    className="rounded-lg bg-amber-600 hover:bg-amber-500 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50 transition-colors"
                  >
                    إرسال الاعتذار
                  </button>
                  <button
                    type="button"
                    onClick={() => { setExcusing(false); setNote(""); }}
                    className="rounded-lg bg-cc-surface-2 hover:bg-cc-border border border-cc-border px-3 py-1.5 text-xs font-semibold text-cc-text transition-colors"
                  >
                    تراجع
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </CcCard>
    </li>
  );
};

/**
 * شاشةُ الموظّف لاجتماعاته — «يحطّ دخول» يودّيه الرابطَ من ردّ الخادم مباشرةً
 * (211-G). القائمةُ مضيَّقةٌ خادمياً على اجتماعات المستخدم الحاليّ — لا فلترةَ ثانية هنا.
 */
export const MyMeetingsPanel: React.FC = () => {
  const [meetings, setMeetings] = useState<PlatformMeetingRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

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

  // تحديثٌ دوريٌّ للوقت الحاليّ كي تُفتح أزرارُ الدخول تلقائياً عند بلوغ النافذة
  // بلا حاجةٍ لتحديث الصفحة يدوياً.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="space-y-4" dir="rtl">
      <div className="flex items-center gap-2">
        <CalendarClock className="h-5 w-5 text-sky-400" />
        <CcSectionTitle title="اجتماعاتي" />
      </div>

      {error && (
        <CcCard tone="danger" className="flex items-center justify-between gap-2 p-3 text-xs">
          <span className="text-rose-400 font-semibold">{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 px-3 py-1 text-[11px] font-bold transition-colors"
          >
            إعادة المحاولة
          </button>
        </CcCard>
      )}

      {loading ? (
        <CcSkeleton variant="card" count={3} />
      ) : !meetings || meetings.length === 0 ? (
        <CcEmpty title="لا اجتماعات مدعوٌّ إليها بعد." />
      ) : (
        <ul className="space-y-3">
          {meetings.map((meeting) => (
            <MeetingRow key={meeting.id} meeting={meeting} now={now} onChanged={() => void load()} />
          ))}
        </ul>
      )}
    </section>
  );
};

export default MyMeetingsPanel;
