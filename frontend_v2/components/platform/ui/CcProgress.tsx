import React from "react";
import { formatNumber } from "../../../utils/formatNumber";
import { CcTone } from "../../../utils/ccTone";

export interface CcProgressProps {
  value: number;
  max: number;
  tone?: CcTone;
  label?: string;
  valueLabel?: string;
  className?: string;
}

const TONE_BAR_MAP = {
  neutral: "bg-cc-text-muted",
  accent: "bg-cc-accent-2",
  success: "bg-cc-success",
  warning: "bg-cc-warning",
  danger: "bg-cc-danger",
  violet: "bg-cc-violet",
} as const;

export const CcProgress: React.FC<CcProgressProps> = ({
  value,
  max,
  tone = "accent",
  label,
  valueLabel,
  className = "",
}) => {
  const safeMax = typeof max === "number" && max > 0 ? max : 100;
  const safeValue = typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
  const percentage = Math.min(100, (safeValue / safeMax) * 100);
  const barColor = TONE_BAR_MAP[tone] || TONE_BAR_MAP.accent;

  const displayValue = valueLabel || `${formatNumber(safeValue)} / ${formatNumber(safeMax)}`;

  return (
    <div
      role="progressbar"
      aria-valuenow={safeValue}
      aria-valuemin={0}
      aria-valuemax={safeMax}
      className={`w-full ${className}`}
    >
      {(label || valueLabel) && (
        <div className="flex items-center justify-between text-xs font-semibold text-cc-text-muted mb-1.5">
          {label && <span>{label}</span>}
          <span>{displayValue}</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-cc-bg-2 border border-cc-border">
        <div
          className={`h-full rounded-full ${barColor} transition-[width] duration-200 motion-reduce:transition-none`}
          style={{ width: `${percentage.toFixed(1)}%` }}
        />
      </div>
    </div>
  );
};

export default CcProgress;
