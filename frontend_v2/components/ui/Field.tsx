/**
 * D1-03: Field — label + input/select/textarea + error wrapper
 */
import React, { forwardRef } from 'react';

interface FieldProps {
  label?: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactElement;
}

export const Field = forwardRef<HTMLDivElement, FieldProps>(
  ({ label, error, hint, required, children }, ref) => (
    <div ref={ref} className="flex flex-col gap-0.5">
      {label && (
        <label className="text-[var(--font-size-xs)] font-medium text-[var(--color-text-muted)]">
          {label}
          {required && <span className="text-[var(--color-danger)] ms-0.5">*</span>}
        </label>
      )}
      {React.cloneElement(children, { error } as Record<string, unknown>)}
      {error && <span className="text-[var(--font-size-xs)] text-[var(--color-danger)]">{error}</span>}
      {hint && !error && <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{hint}</span>}
    </div>
  )
);
Field.displayName = 'Field';