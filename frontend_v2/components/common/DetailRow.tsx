// DetailRow.tsx
import React from "react";

interface DetailRowProps {
  label: string;
  value: React.ReactNode;
}

export const DetailRow: React.FC<DetailRowProps> = ({
  label,
  value,
}) => (
  <div className="flex justify-between py-2">
    <span className="font-semibold text-[var(--color-text)]">
      {label}:
    </span>
    <span className="text-[var(--color-text-muted)] text-left">{value}</span>
  </div>
);