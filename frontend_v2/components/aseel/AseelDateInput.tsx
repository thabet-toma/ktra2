/**
 * N1-T5 — AseelDateInput
 * Wrapper حول <input type="date"> يُطبّق ميزات Aseel للحقول الزمنية:
 *
 *   - data-aseel-field="date" مُطبَّق تلقائياً
 *   - `*` يَزيد التاريخ يوماً واحداً
 *   - `-` يَنقص التاريخ يوماً واحداً
 *   - `+` يَزيد شهراً
 *   - Double-click على الحقل ⇒ يَفتح modal تقويم سنوي (12 شهر × أيام)
 *     مع تمييز اليوم الحالي.
 *
 * Reference: docs/aseel_reference/invoices.txt 38–43, الجديد:111.
 */
import React, { useCallback, useMemo, useState } from 'react';
import { Calendar } from 'lucide-react';
import { formatDateLocalized } from '../../utils/formatDate';

export interface AseelDateInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange'> {
  /** ISO date string (YYYY-MM-DD). */
  value: string;
  /** Called with the new ISO date string. */
  onChange: (value: string) => void;
  /** Disable the year-calendar modal trigger (the asterisk and minus key shortcuts still work). */
  disableCalendar?: boolean;
}

/** ── Date math helpers (UTC-safe, format-stable) ────────────────────── */

function parseIso(s: string | undefined): Date | null {
  if (!s) return null;
  // s = "YYYY-MM-DD"
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  const dt = new Date(y, mo, d);
  if (Number.isNaN(dt.getTime())) return null;
  return dt;
}

function toIso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function addDays(s: string, n: number): string {
  const d = parseIso(s) || new Date();
  d.setDate(d.getDate() + n);
  return toIso(d);
}

function addMonths(s: string, n: number): string {
  const d = parseIso(s) || new Date();
  d.setMonth(d.getMonth() + n);
  return toIso(d);
}

/** ── Year-calendar modal ────────────────────────────────────────────── */

const AR_MONTHS = [
  'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
  'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر',
];

const AR_WEEKDAYS_SHORT = ['أحد', 'إث', 'ثل', 'أر', 'خم', 'جم', 'سب'];

function daysInMonth(year: number, monthIdx: number): number {
  return new Date(year, monthIdx + 1, 0).getDate();
}

function firstWeekday(year: number, monthIdx: number): number {
  // 0 = Sunday
  return new Date(year, monthIdx, 1).getDay();
}

interface YearCalendarProps {
  year: number;
  selected: string;
  onPick: (iso: string) => void;
  onYearChange: (y: number) => void;
  onClose: () => void;
}

const YearCalendar: React.FC<YearCalendarProps> = ({
  year,
  selected,
  onPick,
  onYearChange,
  onClose,
}) => {
  const today = toIso(new Date());

  return (
    <div
      role="dialog"
      aria-label="تقويم سنوي"
      className="aseel-date-cal__backdrop"
      onClick={onClose}
    >
      <div
        className="aseel-date-cal"
        onClick={(e) => e.stopPropagation()}
        dir="rtl"
      >
        <div className="aseel-date-cal__header">
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => onYearChange(year - 1)}
            title="سنة سابقة"
          >
            ‹
          </button>
          <input
            type="number"
            className="aseel-input aseel-date-cal__year"
            value={year}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (Number.isFinite(n) && n >= 1900 && n <= 9999) onYearChange(n);
            }}
          />
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => onYearChange(year + 1)}
            title="سنة تالية"
          >
            ›
          </button>
          <button
            type="button"
            className="aseel-toolbtn aseel-toolbtn--danger"
            onClick={onClose}
            title="إغلاق (Esc)"
            style={{ marginInlineStart: 'auto' }}
          >
            ✕
          </button>
        </div>
        <div className="aseel-date-cal__grid">
          {AR_MONTHS.map((monthName, mIdx) => {
            const total = daysInMonth(year, mIdx);
            const offset = firstWeekday(year, mIdx);
            const cells: Array<number | null> = [];
            for (let i = 0; i < offset; i++) cells.push(null);
            for (let d = 1; d <= total; d++) cells.push(d);

            return (
              <div key={mIdx} className="aseel-date-cal__month">
                <div className="aseel-date-cal__month-title">{monthName}</div>
                <div className="aseel-date-cal__weekdays">
                  {AR_WEEKDAYS_SHORT.map((w) => (
                    <span key={w}>{w}</span>
                  ))}
                </div>
                <div className="aseel-date-cal__days">
                  {cells.map((d, i) => {
                    if (d === null) return <span key={i} />;
                    const iso = toIso(new Date(year, mIdx, d));
                    const isSelected = iso === selected;
                    const isToday = iso === today;
                    return (
                      <button
                        type="button"
                        key={i}
                        className={[
                          'aseel-date-cal__day',
                          isSelected ? 'aseel-date-cal__day--sel' : '',
                          isToday ? 'aseel-date-cal__day--today' : '',
                        ].filter(Boolean).join(' ')}
                        onClick={() => {
                          onPick(iso);
                          onClose();
                        }}
                      >
                        {d}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/** ── Main component ─────────────────────────────────────────────────── */

export const AseelDateInput: React.FC<AseelDateInputProps> = ({
  value,
  onChange,
  disableCalendar = false,
  onKeyDown,
  onDoubleClick,
  className,
  ...rest
}) => {
  const [calOpen, setCalOpen] = useState(false);
  const [calYear, setCalYear] = useState<number>(() => {
    const d = parseIso(value);
    return d ? d.getFullYear() : new Date().getFullYear();
  });

  /** Sync displayed year with value when modal opens. */
  const openCalendar = useCallback(() => {
    const d = parseIso(value);
    setCalYear(d ? d.getFullYear() : new Date().getFullYear());
    setCalOpen(true);
  }, [value]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      onKeyDown?.(e);
      if (e.defaultPrevented) return;
      const current = value || toIso(new Date());
      if (e.key === '*') {
        e.preventDefault();
        onChange(addDays(current, +1));
      } else if (e.key === '-') {
        e.preventDefault();
        onChange(addDays(current, -1));
      } else if (e.key === '+') {
        e.preventDefault();
        onChange(addMonths(current, +1));
      } else if (e.key === 'Escape' && calOpen) {
        e.preventDefault();
        setCalOpen(false);
      }
    },
    [calOpen, onChange, onKeyDown, value],
  );

  const handleDoubleClick = useCallback(
    (e: React.MouseEvent<HTMLInputElement>) => {
      onDoubleClick?.(e);
      if (e.defaultPrevented) return;
      if (disableCalendar) return;
      openCalendar();
    },
    [disableCalendar, onDoubleClick, openCalendar],
  );

  const inputClass = useMemo(
    () => ['aseel-input', className].filter(Boolean).join(' '),
    [className],
  );

  const disabled = Boolean((rest as { disabled?: boolean }).disabled);
  const openIfAllowed = () => { if (!disabled && !disableCalendar) openCalendar(); };

  // G10: العرض محلي (dd/MM/yyyy) بحقل قراءة — يفتح التقويم السنوي العربي بالنقر/النقر
  // المزدوج/زر التقويم بدل <input type=date> الذي كان يعرض mm/dd/yyyy حسب لغة المتصفّح.
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', width: '100%' }}>
      <input
        {...rest}
        readOnly
        type="text"
        data-aseel-field="date"
        className={inputClass}
        style={{ width: '100%', cursor: disabled ? undefined : 'pointer' }}
        value={formatDateLocalized(value)}
        placeholder="يوم/شهر/سنة"
        onKeyDown={handleKeyDown}
        onClick={openIfAllowed}
        onDoubleClick={handleDoubleClick}
        title="انقر لاختيار التاريخ · *: يوم لاحق · -: يوم سابق · +: شهر"
      />
      {!disableCalendar && (
        <button
          type="button"
          onClick={openIfAllowed}
          disabled={disabled}
          aria-label="فتح التقويم"
          title="اختر التاريخ"
          tabIndex={-1}
          style={{
            position: 'absolute', insetInlineStart: 6, background: 'none', border: 'none',
            padding: 0, cursor: disabled ? 'default' : 'pointer', color: 'var(--aseel-ink-soft, #888)',
            display: 'inline-flex',
          }}
        >
          <Calendar className="w-3.5 h-3.5" />
        </button>
      )}
      {calOpen && (
        <YearCalendar
          year={calYear}
          selected={value || ''}
          onYearChange={setCalYear}
          onPick={onChange}
          onClose={() => setCalOpen(false)}
        />
      )}
    </span>
  );
};
