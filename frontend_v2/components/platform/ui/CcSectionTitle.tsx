import React from "react";
import { formatNumber } from "../../../utils/formatNumber";

export interface CcSectionTitleProps {
  title: string;
  subtitle?: string;
  badge?: string | number;
  action?: React.ReactNode;
  className?: string;
}

export const CcSectionTitle: React.FC<CcSectionTitleProps> = ({
  title,
  subtitle,
  badge,
  action,
  className = "",
}) => {
  const formattedBadge =
    badge !== undefined
      ? typeof badge === "number"
        ? formatNumber(badge)
        : badge
      : null;

  return (
    <div className={`flex items-center justify-between gap-4 ${className}`}>
      <div className="flex items-center gap-3">
        {formattedBadge !== null && (
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 text-xs font-black text-white shadow-sm shrink-0">
            {formattedBadge}
          </span>
        )}
        <div>
          <h2 className="text-base sm:text-lg font-bold text-cc-text tracking-tight">{title}</h2>
          {subtitle && <p className="text-xs text-cc-text-muted mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
};

export default CcSectionTitle;
