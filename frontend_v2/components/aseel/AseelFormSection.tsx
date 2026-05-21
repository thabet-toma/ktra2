/**
 * N1-T1 — AseelFormSection
 * صندوق فرعي بإطار var(--aseel-border-soft)، عنوان رمادي var(--aseel-ink-soft)،
 * grid داخلي 2-3 أعمدة auto-fit. يَدعم nested (form section داخل form section).
 * Reference: docs/aseel_reference/invoices.txt 51–92.
 */
import React from 'react';

export type AseelFormSectionProps = {
  title?: string;
  children: React.ReactNode;
  cols?: 2 | 3 | 4;
  className?: string;
};

export const AseelFormSection: React.FC<AseelFormSectionProps> = ({
  title,
  children,
  cols = 2,
  className = '',
}) => {
  const colClass = cols === 3 ? 'aseel-grid-3' : cols === 4 ? 'aseel-grid-4' : 'aseel-grid-2';

  return (
    <div className={`aseel-form-section ${colClass} ${className}`}>
      {title && (
        <div className="aseel-form-section-title">{title}</div>
      )}
      <div className="aseel-form-section-body">{children}</div>
    </div>
  );
};
