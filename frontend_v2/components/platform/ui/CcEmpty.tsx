import React from "react";

export interface CcEmptyProps {
  title: string;
  hint?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export const CcEmpty: React.FC<CcEmptyProps> = ({
  title,
  hint,
  icon,
  action,
  className = "",
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 sm:p-12 text-center rounded-[var(--radius-cc,1rem)] border border-dashed border-cc-border bg-cc-surface/30 ${className}`}
    >
      {icon && (
        <div className="mb-3 rounded-full bg-cc-surface-2 p-3 text-cc-text-muted border border-cc-border shrink-0">
          {icon}
        </div>
      )}
      <h3 className="text-sm sm:text-base font-bold text-cc-text mb-1">{title}</h3>
      {hint && <p className="text-xs text-cc-text-muted max-w-sm mb-4 leading-relaxed">{hint}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
};

export default CcEmpty;
