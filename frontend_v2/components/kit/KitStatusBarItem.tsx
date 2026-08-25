/**
 * N0-T9 — KitStatusBarItem
 * Helper type-safe لعناصر شريط الحالة — يُختصر التكرار في 30+ صفحة.
 */
import React from 'react';

export type KitStatusBarItemProps = {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
};

export const KitStatusBarItem: React.FC<KitStatusBarItemProps> = ({ label, value, icon }) => (
  <span className="ktra-status-item">
    {icon && <span className="ktra-status-icon">{icon}</span>}
    <span className="ktra-status-label">{label}</span>
    <span className="ktra-status-value">{value}</span>
  </span>
);
