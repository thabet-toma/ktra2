import React, { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Send, X } from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  broadcastPlatformApplicantNotice,
  listPlatformApplicants,
  type PlatformJobApplicant,
  type PlatformJobPosting,
} from "../../services/platformHiringApi";
import { formatNumber } from "../../utils/formatNumber";
import { APPLICANT_STATUS_OPTIONS, firstApiErrorMessage } from "../../utils/platformHiring";

interface PlatformApplicantBroadcastDialogProps {
  job: PlatformJobPosting;
  initialStatus: string;
  onClose: () => void;
  onSent: () => void;
}

const STATUS_CHOICES = [
  { value: "", label: "كافة الحالات" },
  ...APPLICANT_STATUS_OPTIONS,
];

/** مرآةُ `APPLICANT_REPLY_CLOSED_STATUSES` في `platform_ops/services.py` — الخادمُ
 *  يستثنيها فعلاً، وهذه تجعل العددَ المعروضَ يطابق ما سيُرسَل لا يخالفه. */
const CLOSED_STATUSES = new Set(["hired", "rejected"]);

export const PlatformApplicantBroadcastDialog: React.FC<PlatformApplicantBroadcastDialogProps> = ({
  job,
  initialStatus,
  onClose,
  onSent,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [status, setStatus] = useState(initialStatus);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [body, setBody] = useState("");
  const [link, setLink] = useState("");
  const [phone, setPhone] = useState("");
  const [sending, setSending] = useState(false);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [audience, setAudience] = useState<PlatformJobApplicant[] | null>(null);
  const [audienceError, setAudienceError] = useState<string | null>(null);

  // **العددُ يُجلَب من الخادم لا من قائمة التبويب**: تلك مصفّاةٌ أصلاً بحالةِ
  // الشاشة (`status` يُمرَّر في `listPlatformApplicants`)، فاختيارُ حالةٍ أخرى
  // هنا كان يعدُّ داخل جمهورٍ لا يحويها — صفرٌ كاذبٌ يقفل الزرّ، أو أسوأُ منه:
  // «كافة الحالات» تُظهر عددَ حالةٍ واحدةٍ ثمّ يصل الإرسالُ إلى أضعافه.
  // والعددُ هو كلُّ ما يحرس فعلاً لا رجعةَ فيه على عشرات الناس، فلا يكون
  // «إرشاديّاً».
  useEffect(() => {
    let active = true;
    setAudience(null);
    setAudienceError(null);
    listPlatformApplicants({ job: job.id, status: status || undefined })
      .then((rows) => {
        if (active) setAudience(rows);
      })
      .catch((err: any) => {
        if (active) {
          setAudienceError(firstApiErrorMessage(err?.data || err, "تعذّر حساب عدد المستقبلين."));
        }
      });
    return () => {
      active = false;
    };
  }, [job.id, status]);

  // ‏`null` = لم يُعرَف بعد، ولا يُعرَض صفرٌ مكانَه: رقمٌ كاذبٌ أسوأُ من انتظار.
  const recipientCount = useMemo(
    () =>
      audience === null
        ? null
        : audience.filter((applicant) => includeClosed || !CLOSED_STATUSES.has(applicant.status))
            .length,
    [audience, includeClosed],
  );
  const statusLabel = STATUS_CHOICES.find((choice) => choice.value === status)?.label ?? status;

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !sending) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, sending]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const ok = await confirm({
      title: "إرسال رسالة جماعية",
      message: `هل أنت متأكد من إرسال الرسالة إلى ${formatNumber(recipientCount ?? 0)} متقدماً لوظيفة «${job.title}»؟`,
      confirmText: "تأكيد الإرسال",
      danger: true,
    });
    if (!ok) return;

    setSending(true);
    try {
      const result = await broadcastPlatformApplicantNotice({
        job: job.id,
        body: body.trim(),
        statuses: status ? [status] : [],
        include_closed: includeClosed,
        link: link.trim() || undefined,
        phone: phone.trim() || undefined,
      });
      toast(`تم إرسال الرسالة إلى ${formatNumber(result.sent)} متقدماً.`, "success");
      onSent();
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذّر إرسال الرسالة."), "error");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" dir="rtl">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="applicant-broadcast-title"
        aria-describedby="applicant-broadcast-recipients"
        className="w-full max-w-2xl rounded-xl border border-slate-200 bg-white p-5 text-right shadow-2xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4 dark:border-slate-800">
          <div>
            <h2 id="applicant-broadcast-title" ref={titleRef} tabIndex={-1} className="text-lg font-bold text-slate-900 outline-none dark:text-slate-100">
              رسالة جماعية
            </h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">تُنشأ رسالة مستقلة في صفحة كل متقدّم.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={sending}
            aria-label="إغلاق"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-slate-200 dark:focus:ring-blue-400"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 pt-4">
          <section id="applicant-broadcast-recipients" aria-label="المستقبلون" className="rounded-lg border border-blue-200 bg-blue-50 p-3 dark:border-blue-900/70 dark:bg-blue-950/30">
            <p className="text-xs font-bold text-blue-900 dark:text-blue-100">إلى مَن</p>
            <p className="mt-1 text-sm font-semibold text-blue-950 dark:text-blue-50" aria-live="polite">
              {job.title} — {statusLabel} —{" "}
              {recipientCount === null ? "جارٍ حسابُ العدد…" : `${formatNumber(recipientCount)} متقدماً`}
            </p>
            {audienceError && (
              <p className="mt-1 text-xs font-semibold text-rose-700 dark:text-rose-300">{audienceError}</p>
            )}
          </section>

          <div>
            <label htmlFor="applicant-broadcast-status" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
              حالة المتقدّمين
            </label>
            <select
              id="applicant-broadcast-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              disabled={sending}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-blue-400"
            >
              {STATUS_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={includeClosed}
                onChange={(event) => setIncludeClosed(event.target.checked)}
                disabled={sending}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:focus:ring-blue-400"
              />
              أشمل الطلبات المغلقة (مقبول/مرفوض)
            </label>
            {includeClosed && (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                تحذير: ستصل الرسالة أيضاً إلى المتقدّمين المقبولين والمرفوضين.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="applicant-broadcast-body" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
              نص الرسالة
            </label>
            <textarea
              id="applicant-broadcast-body"
              rows={5}
              maxLength={4000}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              disabled={sending}
              className="w-full rounded-lg border border-slate-300 bg-white p-2 text-xs text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>

          <details className="text-xs text-slate-600 dark:text-slate-400">
            <summary className="cursor-pointer font-semibold text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-blue-300 dark:focus:ring-blue-400">
              إضافة رابط أو رقم اتصال
            </summary>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="block">رابط (اختياري)</span>
                <input
                  type="url"
                  dir="ltr"
                  value={link}
                  onChange={(event) => setLink(event.target.value)}
                  disabled={sending}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-left text-xs text-slate-900 outline-none focus:ring-2 focus:ring-blue-500/20 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
              </label>
              <label className="space-y-1">
                <span className="block">رقم هاتف (اختياري)</span>
                <input
                  type="tel"
                  dir="ltr"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  disabled={sending}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-left text-xs text-slate-900 outline-none focus:ring-2 focus:ring-blue-500/20 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
              </label>
            </div>
          </details>

          <div className="flex justify-end gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={sending}
              className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:focus:ring-blue-400"
            >
              إلغاء
            </button>
            <button
              type="submit"
              disabled={sending || !recipientCount || !body.trim()}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-xs font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-blue-400 dark:focus:ring-offset-slate-900"
            >
              {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Send className="h-3.5 w-3.5" aria-hidden="true" />}
              أرسل إلى {recipientCount === null ? "…" : formatNumber(recipientCount)} متقدماً
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
