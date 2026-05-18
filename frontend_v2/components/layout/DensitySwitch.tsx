import React from 'react';
import { Rows3, Rows4 } from 'lucide-react';

interface DensitySwitchProps {
  value: 'comfortable' | 'compact';
  onChange: (v: 'comfortable' | 'compact') => void;
}

export const DensitySwitch: React.FC<DensitySwitchProps> = ({ value, onChange }) => {
  return (
    <div className="flex items-center rounded-md border border-[var(--color-border)] overflow-hidden">
      <button
        onClick={() => onChange('comfortable')}
        title="مظهر مريح"
        className={`p-1.5 transition-colors ${value === 'comfortable'
          ? 'bg-[var(--color-primary)] text-white'
          : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-muted)]'}`}
      >
        <Rows4 className="h-4 w-4" />
      </button>
      <button
        onClick={() => onChange('compact')}
        title="مظهر مضغوط"
        className={`p-1.5 transition-colors border-s border-[var(--color-border)] ${value === 'compact'
          ? 'bg-[var(--color-primary)] text-white'
          : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-muted)]'}`}
      >
        <Rows3 className="h-4 w-4" />
      </button>
    </div>
  );
};