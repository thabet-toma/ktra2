/**
 * T5 — عناصر «نشط / غير نشط» المشتركة: فلتر الحالة الثلاثي، وشارة «غير نشط»، وشريط
 * التنبيه على بطاقة السجل الموقوف. عامّة عمداً (لا نصّ خاصّ بالأطراف) فتعيد استعمالها
 * شاشاتُ الأصناف وغيرها بالتصدير نفسه.
 */
import React from "react";
import type { ActiveStatus } from "../../utils/activeStatus";

const STATUS_OPTIONS: ReadonlyArray<{ value: ActiveStatus; label: string }> = [
  { value: "active", label: "نشط" },
  { value: "inactive", label: "غير نشط" },
  { value: "all", label: "الكل" },
];

export interface ActiveStatusFilterProps {
  value: ActiveStatus;
  onChange: (value: ActiveStatus) => void;
  /** يُسبق به `data-testid` الخيارات: `<testId>-active|inactive|all`. */
  testId?: string;
  className?: string;
}

/** فلتر ثلاثي مقسَّم: نشط (الافتراضي) · غير نشط · الكل. */
export const ActiveStatusFilter: React.FC<ActiveStatusFilterProps> = ({
  value, onChange, testId = "active-status-filter", className = "",
}) => (
  <div
    role="group"
    aria-label="حالة السجل"
    data-testid={testId}
    className={`inline-flex overflow-hidden rounded-lg border border-[var(--color-border)] text-xs ${className}`}
  >
    {STATUS_OPTIONS.map((option) => {
      const on = option.value === value;
      return (
        <button
          key={option.value}
          type="button"
          aria-pressed={on}
          data-testid={`${testId}-${option.value}`}
          onClick={() => { if (!on) onChange(option.value); }}
          className={`px-3 py-1 font-semibold transition-colors ${
            on
              ? "bg-blue-600 text-white"
              : "bg-[var(--color-surface)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          }`}
        >
          {option.label}
        </button>
      );
    })}
  </div>
);

/** شارة رمادية «غير نشط» بجانب اسم السجل. */
export const InactiveBadge: React.FC<{ className?: string }> = ({ className = "" }) => (
  <span
    data-testid="inactive-badge"
    className={`rounded-full bg-gray-200 px-1.5 py-px text-[10px] font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200 ${className}`}
  >
    غير نشط
  </span>
);

export interface InactiveBannerProps {
  title: string;
  description?: string;
  /** يُظهر زر «تنشيط» حين يُمرَّر. */
  onActivate?: () => void;
  busy?: boolean;
}

/** شريط أعلى بطاقة السجل الموقوف، بزر «تنشيط». */
export const InactiveBanner: React.FC<InactiveBannerProps> = ({ title, description, onActivate, busy = false }) => (
  <div
    role="status"
    data-testid="inactive-banner"
    className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-amber-900 dark:border-amber-700/60 dark:bg-amber-900/20 dark:text-amber-100"
  >
    <div className="min-w-0 flex-1">
      <div className="text-sm font-bold">{title}</div>
      {description && <div className="mt-0.5 text-xs opacity-90">{description}</div>}
    </div>
    {onActivate && (
      <button
        type="button"
        data-testid="inactive-banner-activate"
        disabled={busy}
        onClick={onActivate}
        className="rounded-lg bg-amber-600 px-3 py-1 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-60"
      >
        {busy ? "جارٍ التنشيط…" : "تنشيط"}
      </button>
    )}
  </div>
);
