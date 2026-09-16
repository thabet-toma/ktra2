import React from "react";
import { formatNumber } from "../../../utils/formatNumber";
import { CcTone, ccScoreTone } from "../../../utils/ccTone";

export interface CcGaugeProps {
  value: number; // 0..100
  size?: "sm" | "md" | "lg";
  tone?: CcTone;
  caption?: string;
  displayValue?: string;
  className?: string;
}

const SIZE_CONFIG = {
  sm: { diameter: 64, radius: 24, strokeWidth: 6, textClass: "text-xs font-bold" },
  md: { diameter: 88, radius: 34, strokeWidth: 7, textClass: "text-sm font-black" },
  lg: { diameter: 120, radius: 46, strokeWidth: 8, textClass: "text-xl font-black" },
} as const;

const TONE_STROKE_MAP = {
  neutral: "text-slate-400",
  accent: "text-sky-400",
  success: "text-emerald-400",
  warning: "text-amber-400",
  danger: "text-rose-400",
  violet: "text-purple-400",
} as const;

export const CcGauge: React.FC<CcGaugeProps> = ({
  value,
  size = "md",
  tone,
  caption,
  displayValue,
  className = "",
}) => {
  const clamped = Math.max(0, Math.min(100, typeof value === "number" && Number.isFinite(value) ? value : 0));
  const effectiveTone = tone || ccScoreTone(clamped);
  const strokeClass = TONE_STROKE_MAP[effectiveTone] || TONE_STROKE_MAP.neutral;

  const { diameter, radius, strokeWidth, textClass } = SIZE_CONFIG[size] || SIZE_CONFIG.md;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped / 100);
  const centerText = displayValue !== undefined ? displayValue : `${formatNumber(Math.round(clamped))}%`;
  const ariaLabel = caption ? `${caption}: ${centerText}` : centerText;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className={`inline-flex flex-col items-center justify-center text-center ${className}`}
    >
      <div className="relative inline-flex items-center justify-center">
        <svg
          width={diameter}
          height={diameter}
          viewBox={`0 0 ${diameter} ${diameter}`}
          className="-rotate-90 transform"
        >
          {/* خلفية مسار الحلقة خافتة */}
          <circle
            cx={diameter / 2}
            cy={diameter / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-white/10"
          />
          {/* قوس التقدم الملون */}
          <circle
            cx={diameter / 2}
            cy={diameter / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            className={`${strokeClass} transition-[stroke-dashoffset] duration-200 motion-reduce:transition-none`}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className={`${textClass} text-cc-text`}>{centerText}</span>
        </div>
      </div>
      {caption && <span className="text-xs font-semibold text-cc-text-muted mt-2">{caption}</span>}
    </div>
  );
};

export default CcGauge;
