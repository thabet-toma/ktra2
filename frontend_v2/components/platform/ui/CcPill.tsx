import React from "react";
import { CcTone, ccPillClasses } from "../../../utils/ccTone";

export interface CcPillProps {
  tone: CcTone;
  dot?: boolean;
  children: React.ReactNode;
  className?: string;
}

const DOT_COLOR_MAP = {
  neutral: "bg-slate-400",
  accent: "bg-sky-400",
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  danger: "bg-rose-400",
  violet: "bg-purple-400",
} as const;

export const CcPill: React.FC<CcPillProps> = ({
  tone,
  dot = false,
  children,
  className = "",
}) => {
  const baseClasses = ccPillClasses(tone);
  const dotColor = DOT_COLOR_MAP[tone] || DOT_COLOR_MAP.neutral;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold transition-colors duration-150 ${baseClasses} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dotColor}`} />}
      <span>{children}</span>
    </span>
  );
};

export default CcPill;
