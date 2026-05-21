/**
 * N0-T9 — AseelStatusBarItem
 * Helper type-safe لعناصر شريط الحالة — يُختصر التكرار في 30+ صفحة.
 */
import React from 'react';

export type AseelStatusBarItemProps = {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
};

export const AseelStatusBarItem: React.FC<AseelStatusBarItemProps> = ({ label, value, icon }) => (
  <span className="aseel-status-item">
    {icon && <span className="aseel-status-icon">{icon}</span>}
    <span className="aseel-status-label">{label}</span>
    <span className="aseel-status-value">{value}</span>
  </span>
);
