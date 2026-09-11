import React from "react";
import { Star, AlertTriangle } from "lucide-react";

import { formatNumber } from "../../utils/formatNumber";
import { isStarFilled } from "../../utils/agentBooks";

/**
 * نجماتُ التقييم اليوميّ الخمس وحقلُ ملاحظتها — **مكوّنٌ واحدٌ للسطحين**.
 *
 * كان الصفُّ منسوخاً حرفياً في شاشة «من يمسك دفاتري» وفي الصفحة العامّة، ومعه
 * نصُّ القفل نفسُه. ونسختان لقاعدةٍ واحدةٍ تفترقان بلا شكوى: إصلاحٌ يصيب إحداهما
 * ويترك الأخرى، وهو لغمٌ مسجَّلٌ في هذا المستودع.
 *
 * وهو **عرضٌ خالص**: لا يعرف الشبكة، والقرارُ (متى يُقفَل، وماذا يُرسَل) عند من
 * يستدعيه — لأنّ السطحين يعرفان القفلَ بطريقين: الداخليُّ من `edited_once`
 * والعامُّ من `can_edit` الذي يحسبه الخادم.
 */

/** نصُّ استهلاك حقّ التعديل — واحدٌ للسطحين. */
export const RATING_LOCKED_MESSAGE = "عدّلتَ تقييمَ هذا اليوم مرّةً، ولا تعديلَ ثانياً.";

interface DailyStarRatingProps {
  stars: number;
  note: string;
  locked: boolean;
  busy: boolean;
  onPick: (star: number) => void;
  onNoteChange: (value: string) => void;
  onSaveNote: () => void;
  /** عنوانُ النجمات — يختلف بين «انقر لتسجيل تقييمك» و«تقييمك المسجل». */
  label: string;
  saveLabel?: string;
  size?: "sm" | "lg";
}

export const DailyStarRating: React.FC<DailyStarRatingProps> = ({
  stars,
  note,
  locked,
  busy,
  onPick,
  onNoteChange,
  onSaveNote,
  label,
  saveLabel = "حفظ الملاحظة",
  size = "sm",
}) => {
  const [hoverStars, setHoverStars] = React.useState<number>(0);
  const starSize = size === "lg" ? "w-8 h-8" : "w-6 h-6";

  return (
    <div className="space-y-3">
      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">
        {label}
      </label>

      <div className={`flex items-center gap-1 py-1 ${size === "lg" ? "justify-center gap-2" : ""}`}>
        {[1, 2, 3, 4, 5].map((star) => {
          const filled = isStarFilled(star, hoverStars || stars);
          return (
            <button
              key={star}
              type="button"
              aria-label={`تقييم ${formatNumber(star)} نجوم`}
              disabled={busy || locked}
              onClick={() => onPick(star)}
              onMouseEnter={() => !locked && setHoverStars(star)}
              onMouseLeave={() => !locked && setHoverStars(0)}
              className={`p-1.5 rounded-lg transition-transform focus:outline-none focus:ring-2 focus:ring-amber-500/40 ${
                locked ? "cursor-not-allowed opacity-75" : "hover:scale-110 active:scale-95 cursor-pointer"
              }`}
            >
              <Star
                className={`${starSize} ${
                  filled ? "text-amber-500 fill-amber-500" : "text-slate-300 dark:text-slate-600"
                }`}
              />
            </button>
          );
        })}
        {stars > 0 && (
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 mr-2">
            {formatNumber(stars)} من {formatNumber(5)}
          </span>
        )}
      </div>

      {locked && (
        <div className="p-2.5 rounded-md bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs flex items-center gap-1.5">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{RATING_LOCKED_MESSAGE}</span>
        </div>
      )}

      {/* قصّة ٥٧: الملاحظةُ **بعد** النقرة لا قبلها، حتى لا تكون النقرةُ مكلفة. */}
      {stars > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate-200 dark:border-slate-700">
          <label className="text-xs font-medium text-slate-700 dark:text-slate-300 block">
            ملاحظة إضافية (اختيارية):
          </label>
          <textarea
            value={note}
            onChange={(e) => onNoteChange(e.target.value)}
            disabled={locked || busy}
            rows={2}
            placeholder="اكتب ملاحظتك حول إنجاز الوكيل اليوم..."
            className="w-full text-xs p-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed"
          />
          {!locked && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onSaveNote}
                disabled={busy}
                className="px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition disabled:opacity-50"
              >
                {busy ? "جاري الحفظ..." : saveLabel}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
