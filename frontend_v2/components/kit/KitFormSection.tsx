/**
 * N1-T1 — KitFormSection
 * صندوق فرعي بإطار var(--ktra-border-soft)، عنوان رمادي var(--ktra-ink-soft)،
 * grid داخلي 2-3 أعمدة auto-fit. يَدعم nested (form section داخل form section).
 * Reference: docs/aseel_reference/invoices.txt 51–92.
 */
import React from 'react';

export type KitFormSectionProps = {
  title?: string;
  children: React.ReactNode;
  cols?: 2 | 3 | 4;
  className?: string;
};

export const KitFormSection: React.FC<KitFormSectionProps> = ({
  title,
  children,
  cols = 2,
  className = '',
}) => {
  const colClass = cols === 3 ? 'ktra-grid-3' : cols === 4 ? 'ktra-grid-4' : 'ktra-grid-2';

  return (
    <div className={`ktra-form-section ${colClass} ${className}`}>
      {title && (
        <div className="ktra-form-section-title">{title}</div>
      )}
      <div className="ktra-form-section-body">{children}</div>
    </div>
  );
};
