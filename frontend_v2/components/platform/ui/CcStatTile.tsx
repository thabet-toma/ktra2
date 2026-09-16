import React from "react";
import { formatNumber } from "../../../utils/formatNumber";
import { CcTone } from "../../../utils/ccTone";

export interface CcStatTileProps {
  label: string;
  value: number | string;
  unit?: string;
  hint?: string;
  icon?: React.ReactNode;
  tone?: CcTone;
  className?: string;
}

const TONE_VALUE_MAP = {
  neutral: "text-cc-text",
  accent: "text-sky-400",
  success: "text-emerald-400",
  warning: "text-amber-400",
  danger: "text-rose-400",
  violet: "text-purple-400",
} as const;

export const CcStatTile: React.FC<CcStatTileProps> = ({
  label,
  value,
  unit,
  hint,
  icon,
  tone = "neutral",
  className = "",
}) => {
  const formattedValue = typeof value === "number" ? formatNumber(value) : value;
  const valueColorClass = TONE_VALUE_MAP[tone] || TONE_VALUE_MAP.neutral;

  return (
    <div className={`flex flex-col ${className}`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-xs font-semibold text-cc-text-muted">{label}</span>
        {icon && <span className="text-cc-text-muted shrink-0">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-2xl sm:text-3xl font-black tracking-tight ${valueColorClass}`}>
          {formattedValue}
        </span>
        {unit && <span className="text-xs font-medium text-cc-text-muted">{unit}</span>}
      </div>
      {hint && <span className="text-[11px] text-cc-text-muted mt-1">{hint}</span>}
    </div>
  );
};

export default CcStatTile;
