import React from "react";

export interface CcSkeletonProps {
  variant?: "line" | "card" | "circle";
  count?: number;
  className?: string;
}

const VARIANT_MAP = {
  line: "h-4 w-full rounded-md",
  card: "h-32 w-full rounded-[var(--radius-cc,1rem)]",
  circle: "h-10 w-10 rounded-full shrink-0",
} as const;

export const CcSkeleton: React.FC<CcSkeletonProps> = ({
  variant = "line",
  count = 1,
  className = "",
}) => {
  const baseClasses = VARIANT_MAP[variant] || VARIANT_MAP.line;
  const items = Array.from({ length: Math.max(1, count) }, (_, i) => i);

  return (
    <>
      {items.map((key) => (
        <div
          key={key}
          className={`bg-cc-surface-2 border border-cc-border animate-pulse motion-reduce:animate-none ${baseClasses} ${className}`}
        />
      ))}
    </>
  );
};

export default CcSkeleton;
