/**
 * N1-T5 — AseelDateInput
 * wrapper حول <input type="date"> يُطبّق useAseelFieldShortcuts تلقائياً:
 *   - * ⇒ +1 يوم
 *   - - ⇒ −1 يوم
 *   - double-click على السنة → modal تقويم سنوي (placeholder)
 * Reference: docs/aseel_reference/new.txt:111.
 */
import React, { useCallback, useState } from 'react';
import { useAseelFieldShortcuts } from './useAseelFieldShortcuts';

export type AseelDateInputProps = {
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  className?: string;
  /** يضيف data-aseel-field="date" تلقائياً لتفعيل اختصارات +/- */
  enableShortcuts?: boolean;
};

export const AseelDateInput: React.FC<AseelDateInputProps> = ({
  value = '',
  onChange,
  disabled,
  className = '',
  enableShortcuts = true,
}) => {
  const [showYearPicker, setShowYearPicker] = useState(false);

  const adjustDate = useCallback(
    (days: number) => {
      if (!value) return;
      const d = new Date(value);
      d.setDate(d.getDate() + days);
      const next = d.toISOString().slice(0, 10);
      onChange?.(next);
    },
    [value, onChange]
  );

  useAseelFieldShortcuts(
    {
      'date-next': () => adjustDate(1),
      'date-prev': () => adjustDate(-1),
    },
    { enabled: enableShortcuts && !disabled }
  );

  return (
    <>
      <input
        type="date"
        className={`aseel-input ${className}`}
        value={value}
        disabled={disabled}
        data-aseel-field={enableShortcuts ? 'date' : undefined}
        onChange={(e) => onChange?.(e.target.value)}
        onDoubleClick={() => setShowYearPicker(true)}
      />
      {showYearPicker && (
        <div
          className="fixed inset-0 z-[9999] bg-black/40 flex items-center justify-center"
          onClick={() => setShowYearPicker(false)}
        >
          <div
            className="bg-white rounded-lg shadow-xl p-4 w-80"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 className="font-bold mb-3 text-center">اختر السنة</h4>
            <div className="grid grid-cols-3 gap-2 max-h-60 overflow-y-auto">
              {Array.from({ length: 20 }, (_, i) => {
                const year = new Date().getFullYear() - 10 + i;
                return (
                  <button
                    key={year}
                    className="px-3 py-1 text-sm border rounded hover:bg-amber-50"
                    onClick={() => {
                      const base = value ? new Date(value) : new Date();
                      base.setFullYear(year);
                      onChange?.(base.toISOString().slice(0, 10));
                      setShowYearPicker(false);
                    }}
                  >
                    {year}
                  </button>
                );
              })}
            </div>
            <button
              className="mt-3 w-full text-center text-sm text-gray-500 hover:text-gray-700"
              onClick={() => setShowYearPicker(false)}
            >
              إغلاق
            </button>
          </div>
        </div>
      )}
    </>
  );
};
