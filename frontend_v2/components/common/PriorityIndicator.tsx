// PriorityIndicator.tsx
import React from "react";

interface PriorityIndicatorProps {
  priority: string;
}

export const PriorityIndicator: React.FC<PriorityIndicatorProps> = ({ priority }) => {
  const style =
    {
      low: "text-green-600 dark:text-green-400",
      medium: "text-yellow-600 dark:text-yellow-400",
      high: "text-orange-600 dark:text-orange-400",
      urgent: "text-red-600 dark:text-red-400",
    }[priority] || "text-[var(--color-text-muted)]";
  return <span className={`font-semibold ${style}`}>{priority}</span>;
};