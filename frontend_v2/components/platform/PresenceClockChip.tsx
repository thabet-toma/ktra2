import React from "react";

import { formatNumber } from "../../utils/formatNumber";
import { presenceClockLabel, presenceToneOf, type PresenceTone } from "../../utils/presenceClock";

/**
 * رقاقةُ «مجموعُ وقته على المنصّة اليوم» — **شيءٌ واحدٌ لموضعَين** (212-N2).
 *
 * نصُّ طلب المالك «يبين بالطاولة فوق صورتو»، والطاولةُ عنده طاولةُ مساحة العمل
 * (`WorkspaceRoom`) حيث تجلس الوجوه؛ وكانت الرقاقةُ في بطاقة الموظّف وحدَها
 * (`EmployeeCard`) فلم يرها حيث نظر. ونسخةٌ ثانيةٌ منها كانت ستعني سلّمَ ألوانٍ
 * يفترق بين الموضعين عند أوّل تعديلٍ للعتبة — فصارت مكوّناً واحداً.
 *
 * والنبرةُ من `presenceToneOf` الخالصةِ المختبَرة؛ وما هنا هو الألوانُ وحدَها،
 * وموضعُها `.tsx` داخل `components/platform/` عن قصد: حارسُ الجلد الداكن يمسح
 * الـ`*.tsx` في هذا المجلّد، فخريطةُ أصنافٍ فاتحةٍ في ملفّ `.ts` كانت تفلت من
 * المسح وتظهر بيضاءَ وسطَ مركز قيادةٍ داكن.
 */
const TONE_CLASS: Record<PresenceTone, string> = {
  unknown: "bg-slate-100 text-slate-400",
  met: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-700",
  absent: "bg-rose-100 text-rose-700",
};

/** احتياطُ الحمولةِ القديمةِ وحدَه — العتبةُ الحقيقيّةُ تأتي من السياسةِ النشطة. */
export const PRESENCE_TARGET_FALLBACK_HOURS = 3;

interface PresenceClockChipProps {
  /** ثواني اليوم من دفتر الخادم — `undefined` حمولةٌ لا تحمل العدّاد. */
  seconds?: number;
  /** عتبةُ تخصّصِ الموظّف من السياسة النشطة. */
  targetHours?: number | null;
}

export const PresenceClockChip: React.FC<PresenceClockChipProps> = ({ seconds, targetHours }) => {
  const target = targetHours ?? PRESENCE_TARGET_FALLBACK_HOURS;
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold leading-none ${TONE_CLASS[presenceToneOf(seconds, target)]}`}
      title={`مجموع وقته على المنصة اليوم — المطلوب ${formatNumber(target)} ساعات`}
    >
      {presenceClockLabel(seconds)}
    </span>
  );
};

export default PresenceClockChip;
