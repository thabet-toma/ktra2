import React, { useState, useRef, useEffect } from "react";
import { format, isValid, parse, addMonths, subMonths, setMonth, setYear } from "date-fns";
import { ar } from "date-fns/locale";
import { Calendar as CalendarIcon, ChevronRight, ChevronLeft } from "lucide-react";

interface Props {
  value: string;
  onChange: (val: string) => void;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
}

export const AseelDatePicker: React.FC<Props> = ({
  value,
  onChange,
  disabled,
  className = "",
  placeholder = "YYYY-MM-DD",
}) => {
  const [open, setOpen] = useState(false);
  const [currentMonth, setCurrentMonth] = useState(() => {
    const d = value ? parse(value, "yyyy-MM-dd", new Date()) : new Date();
    return isValid(d) ? d : new Date();
  });
  
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (d: Date) => {
    onChange(format(d, "yyyy-MM-dd"));
    setOpen(false);
  };

  const handleClear = () => {
    onChange("");
    setOpen(false);
  };

  const handleToday = () => {
    const today = new Date();
    onChange(format(today, "yyyy-MM-dd"));
    setCurrentMonth(today);
    setOpen(false);
  };

  const daysInMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 0).getDate();
  const firstDay = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1).getDay();
  
  // RTL offset: Sunday is 0, but in RTL we might want Saturday or Sunday first. Let's use standard (Sunday=0).
  const blanks = Array.from({ length: firstDay }, (_, i) => i);
  const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);

  const months = Array.from({ length: 12 }, (_, i) => {
    const d = new Date();
    d.setMonth(i);
    return format(d, "MMMM", { locale: ar });
  });

  const years = Array.from({ length: 20 }, (_, i) => currentMonth.getFullYear() - 10 + i);

  return (
    <div className="relative inline-block w-full" ref={containerRef} dir="rtl">
      <div 
        className={`flex items-center bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 h-8 cursor-text ${disabled ? "opacity-60 cursor-not-allowed bg-[var(--color-surface-2)]" : ""} ${className}`}
        onClick={() => !disabled && setOpen(!open)}
      >
        <input
          type="text"
          readOnly
          value={value}
          placeholder={placeholder}
          className="flex-1 bg-transparent border-none outline-none text-sm w-full cursor-pointer text-[var(--color-text)]"
          disabled={disabled}
        />
        <CalendarIcon className="w-4 h-4 text-[var(--color-text-muted)] mr-1" />
      </div>

      {open && (
        <div className="absolute top-full right-0 mt-1 z-50 bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xl rounded-md p-3 w-64 text-sm font-sans">
          <div className="flex justify-between items-center mb-3">
            <button
              type="button"
              className="p-1 hover:bg-[var(--color-surface-3)] rounded"
              onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <div className="flex gap-1">
              <select
                className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded px-1 py-0.5"
                value={currentMonth.getMonth()}
                onChange={(e) => setCurrentMonth(setMonth(currentMonth, parseInt(e.target.value)))}
              >
                {months.map((m, i) => <option key={i} value={i}>{m}</option>)}
              </select>
              <select
                className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded px-1 py-0.5"
                value={currentMonth.getFullYear()}
                onChange={(e) => setCurrentMonth(setYear(currentMonth, parseInt(e.target.value)))}
              >
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <button
              type="button"
              className="p-1 hover:bg-[var(--color-surface-3)] rounded"
              onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center mb-2">
            {["أحد", "إثن", "ثلا", "أرب", "خمي", "جمع", "سبت"].map((d) => (
              <div key={d} className="text-xs font-semibold text-[var(--color-text-muted)]">{d}</div>
            ))}
            {blanks.map((b) => <div key={`blank-${b}`} />)}
            {days.map((d) => {
              const dateObj = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), d);
              const dateStr = format(dateObj, "yyyy-MM-dd");
              const isSelected = dateStr === value;
              const isToday = dateStr === format(new Date(), "yyyy-MM-dd");
              
              return (
                <button
                  key={d}
                  type="button"
                  onClick={() => handleSelect(dateObj)}
                  className={`w-7 h-7 rounded-full flex items-center justify-center transition-colors
                    ${isSelected ? "bg-blue-600 text-white" : "hover:bg-[var(--color-surface-3)] text-[var(--color-text)]"}
                    ${isToday && !isSelected ? "border border-blue-400" : ""}
                  `}
                >
                  {d}
                </button>
              );
            })}
          </div>

          <div className="flex justify-between border-t pt-2 mt-2">
            <button type="button" className="text-blue-600 hover:text-blue-800" onClick={handleToday}>اليوم</button>
            <button type="button" className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]" onClick={handleClear}>مسح</button>
            <button type="button" className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]" onClick={() => setOpen(false)}>إغلاق</button>
          </div>
        </div>
      )}
    </div>
  );
};
