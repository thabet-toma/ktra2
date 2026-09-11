import React, { useCallback, useEffect, useState } from "react";
import { Check, Copy, Info, Share2, ShieldAlert, Star, UserCheck } from "lucide-react";

import {
  generateRatingLink,
  getEmployeeRatingsSummary,
  submitDailyRating,
  updateDailyRating,
  type AgentInfo,
  type DailyRatingRecord,
  type EmployeeRatingsSummary,
  type GenerateLinkResult,
  type TodayRating,
} from "../../services/myAgentApi";
import { useToast } from "../../contexts/ToastContext";
import { formatDateTimeValue, formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { canEditRating } from "../../utils/agentBooks";
import { DailyStarRating } from "./DailyStarRating";

/**
 * بطاقةُ وكيلٍ واحدٍ داخل تبويب «من يمسك دفاتري»: هويّتُه وصلاحيّتُه وتقييمُ يومه.
 *
 * **بطاقةٌ لكلّ وكيل**: فرادةُ الارتباط على (موظف، شركة) لا على الشركة، فقد يعمل
 * على دفاترك اثنان — والتقييمُ نفسُه مفتاحُه (شركة، موظف، يوم)، فلكلٍّ نجماتُه.
 */
interface AgentRatingCardProps {
  agent: AgentInfo;
  /** يومُ الخدمة بتوقيت الشركة — من الخادم، لا `new Date()` في جهاز الزائر. */
  serviceDate: string;
  canSuspend?: boolean;
  onSuspend?: () => void;
}

const toTodayRating = (row: DailyRatingRecord): TodayRating => ({
  id: row.id,
  service_date: row.service_date,
  stars: row.stars,
  note: row.note,
  edited_once: row.edited_once,
});

export const AgentRatingCard: React.FC<AgentRatingCardProps> = ({
  agent,
  serviceDate,
  canSuspend,
  onSuspend,
}) => {
  const [rating, setRating] = useState<TodayRating | null>(agent.today_rating);
  const [stars, setStars] = useState<number>(agent.today_rating?.stars ?? 0);
  const [note, setNote] = useState<string>(agent.today_rating?.note ?? "");
  const [busy, setBusy] = useState<boolean>(false);
  const [summary, setSummary] = useState<EmployeeRatingsSummary | null>(null);
  const [link, setLink] = useState<GenerateLinkResult | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const toast = useToast();
  const locked = Boolean(rating && !canEditRating(true, rating.edited_once));

  useEffect(() => {
    let alive = true;
    // رقمٌ مساعدٌ لا عمودُ الشاشة: فشلُه لا يجوز أن يُسقط البطاقة.
    void getEmployeeRatingsSummary(agent.id)
      .then((data) => { if (alive) setSummary(data); })
      .catch(() => { if (alive) setSummary(null); });
    return () => { alive = false; };
  }, [agent.id]);

  const handlePick = useCallback(async (star: number) => {
    if (locked) return;
    setBusy(true);
    try {
      if (!rating) {
        const created = await submitDailyRating({
          employee_id: agent.id,
          service_date: serviceDate,
          stars: star,
          note: note.trim(),
        });
        setRating(toTodayRating(created));
        setStars(created.stars);
        toast("تم تسجيل تقييمك بنجاح.", "success");
      } else {
        const updated = await updateDailyRating(rating.id, { stars: star });
        setRating(toTodayRating(updated));
        setStars(updated.stars);
        toast("تم تحديث التقييم بنجاح.", "success");
      }
    } catch (err: any) {
      toast(err?.message || "تعذر تسجيل التقييم.", "error");
    } finally {
      setBusy(false);
    }
  }, [agent.id, locked, note, rating, serviceDate, toast]);

  const handleSaveNote = useCallback(async () => {
    if (!rating || locked) return;
    setBusy(true);
    try {
      const updated = await updateDailyRating(rating.id, { note: note.trim() });
      setRating(toTodayRating(updated));
      setNote(updated.note || "");
      toast("تم حفظ الملاحظة بنجاح.", "success");
    } catch (err: any) {
      toast(err?.message || "تعذر حفظ الملاحظة.", "error");
    } finally {
      setBusy(false);
    }
  }, [locked, note, rating, toast]);

  const handleGenerateLink = useCallback(async () => {
    setBusy(true);
    try {
      const result = await generateRatingLink({
        employee_id: agent.id,
        service_date: serviceDate,
      });
      setLink(result);
      // النسخُ للحافظة يحتاج سياقاً آمناً وقد يرفضه المتصفّح، و**فشلُه ليس فشلَ
      // التوليد**: الرابطُ مولَّدٌ ومعروضٌ للنسخ اليدويّ أدناه.
      try {
        await navigator.clipboard.writeText(result.public_url);
        setCopied(true);
        setTimeout(() => setCopied(false), 3000);
        toast("تم توليد الرابط ونسخه للحافظة بنجاح.", "success");
      } catch {
        toast("تم توليد الرابط — انسخه من الصندوق أدناه.", "success");
      }
    } catch (err: any) {
      toast(err?.message || "تعذر توليد رابط التقييم.", "error");
    } finally {
      setBusy(false);
    }
  }, [agent.id, serviceDate, toast]);

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
          <UserCheck className="w-5 h-5 text-emerald-600" />
          {agent.name}
        </h3>
        {canSuspend && onSuspend && agent.engagement_status === "active" && (
          <button
            type="button"
            onClick={onSuspend}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/60 transition"
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            تعليق الوصول
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60">
          <span className="text-xs text-slate-500 dark:text-slate-400 block">صفته على شركتك</span>
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">{agent.role_title}</span>
        </div>
        <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60">
          <span className="text-xs text-slate-500 dark:text-slate-400 block">تخصصه</span>
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">{agent.specialty}</span>
        </div>
        <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60">
          <span className="text-xs text-slate-500 dark:text-slate-400 block">تاريخ الإسناد</span>
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {formatDateValue(agent.assigned_at)}
          </span>
        </div>
      </div>

      {/* قصّة ٥٠: تُقال الصلاحيّة صراحةً بلا تلطيف — والنصُّ نصُّ الخادم. */}
      {agent.authority_notice && (
        <div className="p-3.5 rounded-lg bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300 text-xs md:text-sm flex items-center gap-2">
          <Info className="w-4 h-4 flex-shrink-0" />
          <span>{agent.authority_notice}</span>
        </div>
      )}

      <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
              <Star className="w-4 h-4 text-amber-500 fill-amber-500" />
              تقييم عمل {formatDateValue(serviceDate)}
            </h4>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              التقييم بنقرة واحدة يُحفظ فوراً، ومتاح تعديله لمرة واحدة فقط.
            </p>
            {summary && (
              <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">
                {summary.status === "sufficient_data" && summary.average_stars != null
                  ? `متوسط تقييماتك لهذا الوكيل: ${formatNumber(summary.average_stars, { maxDecimals: 2 })} من ${formatNumber(5)} (${formatNumber(summary.sample_size)} تقييماً).`
                  : `سجّلتَ ${formatNumber(summary.sample_size)} تقييماً؛ يظهر المتوسط بعد ${formatNumber(summary.min_sample_size)}.`}
              </p>
            )}
          </div>

          {agent.worked_today && (
            <button
              type="button"
              onClick={() => void handleGenerateLink()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition disabled:opacity-50"
            >
              <Share2 className="w-3.5 h-3.5" />
              مشاركة رابط التقييم
            </button>
          )}
        </div>

        {/* قصّة ٦٠: «لا يُطلَب منّي تقييمُ يومٍ لم يعمل فيه أحد» — فلا نجماتٍ أصلاً،
            لا نجماتٍ تُنقَر ثمّ يردّ الخادمُ 400 في شريطٍ أحمر. */}
        {agent.worked_today ? (
          <DailyStarRating
            stars={stars}
            note={note}
            locked={locked}
            busy={busy}
            onPick={(star) => void handlePick(star)}
            onNoteChange={setNote}
            onSaveNote={() => void handleSaveNote()}
            label={rating ? "تقييمك المسجل:" : "انقر على النجوم لتسجيل تقييمك:"}
          />
        ) : (
          <p className="text-xs text-slate-500 dark:text-slate-400 py-2">
            لا عمل مسجَّلاً لهذا الوكيل على دفاترك في {formatDateValue(serviceDate)} — لا تقييم لهذا اليوم.
          </p>
        )}

        {link && (
          <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">رابط التقييم العام:</span>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(link.public_url).then(
                    () => {
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2500);
                    },
                    () => toast("تعذر النسخ — حدّد الرابط وانسخه يدوياً.", "error"),
                  );
                }}
                className="text-xs font-medium text-emerald-700 dark:text-emerald-300 hover:underline flex items-center gap-1"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied ? "تم النسخ" : "نسخ الرابط"}
              </button>
            </div>
            <div className="text-xs font-mono break-all select-all p-1.5 rounded bg-white dark:bg-slate-900 border border-emerald-200 dark:border-emerald-800 text-slate-700 dark:text-slate-300">
              {link.public_url}
            </div>
            <p className="text-[11px] text-emerald-700 dark:text-emerald-400">
              تنتهي صلاحية الرابط في: {formatDateTimeValue(link.expires_at)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
