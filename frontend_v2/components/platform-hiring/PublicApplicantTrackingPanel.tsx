import React, { useState } from "react";
import { CalendarDays, Loader2, MapPin, RefreshCw, Send } from "lucide-react";

import {
  replyToPublicCareersTracking,
  type ApplicantUpdate,
  type PublicApplicantTrackingPayload,
} from "../../services/platformHiringApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { ApplicantUpdateThread } from "./ApplicantUpdateThread";

interface PublicApplicantTrackingPanelProps {
  tracking: PublicApplicantTrackingPayload;
  onRefresh: () => void;
  refreshing: boolean;
  error: string;
  onTrackingChanged: (tracking: PublicApplicantTrackingPayload) => void;
  onSessionExpired: () => void;
}

const isHttpUrl = (value: string) => /^https?:\/\//i.test(value.trim());

export const PublicApplicantTrackingPanel: React.FC<PublicApplicantTrackingPanelProps> = ({
  tracking,
  onRefresh,
  refreshing,
  error,
  onTrackingChanged,
  onSessionExpired,
}) => {
  const [reply, setReply] = useState("");
  const [replyError, setReplyError] = useState("");
  const [replying, setReplying] = useState(false);

  const sendReply = async (event: React.FormEvent) => {
    event.preventDefault();
    setReplyError("");
    setReplying(true);
    try {
      const result = await replyToPublicCareersTracking(tracking.session, reply);
      if (result.status === 401) {
        onSessionExpired();
        return;
      }
      if (result.status === 403) {
        onTrackingChanged({ ...tracking, applicant: { ...tracking.applicant, can_reply: false } });
        setReplyError((result.data && "detail" in result.data && result.data.detail) || "هذا الطلب مغلق للردود حالياً.");
        return;
      }
      if (result.status !== 201 || !result.data || !("id" in result.data)) {
        setReplyError((result.data && "body" in result.data && result.data.body) || (result.data && "detail" in result.data && result.data.detail) || "تعذّر إرسال الرسالة.");
        return;
      }
      onTrackingChanged({ ...tracking, updates: [...tracking.updates, result.data as ApplicantUpdate] });
      setReply("");
    } catch {
      setReplyError("تعذّر الاتصال بالخادم. حاول مرةً أخرى.");
    } finally {
      setReplying(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="border-b border-slate-200 pb-4 dark:border-slate-800">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">{tracking.job.title}</h1>
          <button type="button" onClick={onRefresh} disabled={refreshing} className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-slate-300 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} /> تحديث
          </button>
        </div>
        <p className="mt-3 text-base font-bold text-blue-700 dark:text-blue-300">{tracking.applicant.status_display}</p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">رقم التتبّع: <span dir="ltr" className="font-mono font-semibold text-slate-700 dark:text-slate-300">{tracking.applicant.reference_code}</span></p>
        {error && <p role="alert" className="mt-3 text-xs font-semibold text-red-600 dark:text-red-400">{error}</p>}
      </header>

      {tracking.meetings.length > 0 && (
        <section aria-labelledby="tracking-meetings" className="space-y-3">
          <h2 id="tracking-meetings" className="text-sm font-bold text-slate-900 dark:text-slate-100">اجتماعاتك</h2>
          {tracking.meetings.map((meeting) => (
            <article key={meeting.id} className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{meeting.title}</h3>
              <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400"><CalendarDays className="h-4 w-4 text-blue-600 dark:text-blue-400" /> {formatDateTimeValue(meeting.start)}{meeting.end ? ` — ${formatDateTimeValue(meeting.end)}` : ""}</p>
              {meeting.location && (isHttpUrl(meeting.location) ? (
                <a href={meeting.location} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-10 items-center rounded-lg bg-blue-600 px-3 text-xs font-bold text-white hover:bg-blue-700">انضمّ للاجتماع</a>
              ) : (
                <p className="mt-2 flex items-start gap-1.5 text-xs text-slate-600 dark:text-slate-400"><MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" /> {meeting.location}</p>
              ))}
            </article>
          ))}
        </section>
      )}

      <details className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
        <summary className="cursor-pointer text-sm font-bold text-slate-900 dark:text-slate-100">عن الوظيفة</summary>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-700 dark:text-slate-300">{tracking.job.description}</p>
        {tracking.job.requirements && (
          <div className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-950/50">
            <h3 className="mb-1 text-xs font-bold text-slate-700 dark:text-slate-300">المتطلبات</h3>
            <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-600 dark:text-slate-400">{tracking.job.requirements}</p>
          </div>
        )}
      </details>

      <section aria-labelledby="tracking-updates" className="space-y-3">
        <h2 id="tracking-updates" className="text-sm font-bold text-slate-900 dark:text-slate-100">التحديثات والرسائل</h2>
        <div role="status" aria-live="polite"><ApplicantUpdateThread updates={tracking.updates} /></div>
      </section>

      {tracking.applicant.can_reply ? (
        <form onSubmit={sendReply} className="border-t border-slate-200 pt-4 dark:border-slate-800">
          <label htmlFor="tracking-reply" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">اكتب ردّك</label>
          <textarea id="tracking-reply" rows={4} maxLength={4000} value={reply} onChange={(event) => setReply(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
          {replyError && <p role="alert" className="mt-2 text-xs font-semibold text-red-600 dark:text-red-400">{replyError}</p>}
          <button type="submit" disabled={replying || !reply.trim()} className="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-60">
            {replying && <Loader2 className="h-4 w-4 animate-spin" />} <Send className="h-4 w-4" /> إرسال الرد
          </button>
        </form>
      ) : (
        <p className="border-t border-slate-200 pt-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">هذا الطلب مغلق للردود حالياً.</p>
      )}
    </div>
  );
};
