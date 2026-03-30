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
    <span className="font-semibold text-gray-700 dark:text-gray-300">
      {label}:
    </span>
    <span className="text-gray-600 dark:text-gray-200 text-left">{value}</span>
  </div>
);