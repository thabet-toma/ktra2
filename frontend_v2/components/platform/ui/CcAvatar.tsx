import React from "react";
import { ccInitials } from "../../../utils/ccInitials";

export interface CcAvatarProps {
  name: string;
  photoUrl?: string | null;
  size?: "sm" | "md" | "lg";
  presence?: "online" | "meeting" | "offline" | null;
  className?: string;
}

const SIZE_MAP = {
  sm: { box: "h-8 w-8 text-xs", dot: "h-2 w-2 bottom-0 left-0" },
  md: { box: "h-11 w-11 text-sm", dot: "h-3 w-3 bottom-0 left-0" },
  lg: { box: "h-16 w-16 text-lg", dot: "h-3.5 w-3.5 bottom-0.5 left-0.5" },
} as const;

/** ثلاثةُ ألوانِ الحضور هي ألوانُ `--pf-online/meeting/offline` نفسُها عبر
 *  رموزِ `cc`، فمعنى اللون في هذه الرقاقة هو معناه في غرفة العمل وفي كلّ
 *  بطاقةِ موظّف — لونٌ رابعٌ هنا كان يكسر المعجمَ البصريّ. */
const PRESENCE_MAP = {
  online: "bg-cc-success ring-2 ring-cc-bg",
  meeting: "bg-cc-warning ring-2 ring-cc-bg",
  offline: "bg-cc-danger ring-2 ring-cc-bg",
} as const;

/** نصُّ التلميح بالعربيّة — كان يعرض `online` حرفيّاً في واجهةٍ عربيّة. */
const PRESENCE_TITLE = {
  online: "متّصل الآن",
  meeting: "في اجتماع",
  offline: "غير متّصل",
} as const;

export const CcAvatar: React.FC<CcAvatarProps> = ({
  name,
  photoUrl,
  size = "md",
  presence = null,
  className = "",
}) => {
  const { box, dot } = SIZE_MAP[size] || SIZE_MAP.md;
  const presenceClass = presence ? PRESENCE_MAP[presence] : null;

  return (
    <div className={`relative inline-block shrink-0 ${box} ${className}`}>
      {photoUrl ? (
        <img
          src={photoUrl}
          alt={name}
          className="h-full w-full rounded-full object-cover ring-1 ring-white/10"
        />
      ) : (
        <div className="h-full w-full rounded-full bg-cc-surface-2 border border-cc-border flex items-center justify-center font-bold text-cc-text select-none">
          {ccInitials(name, "")}
        </div>
      )}
      {presenceClass && (
        <span
          className={`absolute rounded-full pointer-events-none ${dot} ${presenceClass}`}
          title={presence ? PRESENCE_TITLE[presence] : undefined}
        />
      )}
    </div>
  );
};

export default CcAvatar;
