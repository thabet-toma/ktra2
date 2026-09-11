import React, { useEffect, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";

interface Props<T extends { id: number }> {
  value: number | null;
  valueLabel: string | null;
  onChange: (item: T | null) => void;
  search: (query: string) => Promise<T[]>;
  searchKey?: number | string;
  renderOption: (item: T) => React.ReactNode;
  selectedFallback: string;
  placeholder: string;
  emptyText: string;
  clearLabel: string;
  disabled?: boolean;
}

/**
 * هيكل منتقي البحث المشترك: حقل بحث مؤجَّل 250ms، قائمة نتائج، وشريحة للقيمة المختارة.
 * حصر النتائج يبقى خادمياً داخل `search` التي يمرّرها المستدعي — لا معامل شركة يُرسل من هنا.
 *
 * `search` تُقرأ من مرجع لا من قائمة اعتماديات الأثر: تمريرها دالّةً جديدة كل رسم (وهو
 * الشائع في المستدعي) كان سيعيد إطلاق البحث بلا نهاية. ما يُعيد البحث هو النص و`searchKey`
 * (معرّف السياسة أو الاشتراك مثلاً) وحدهما.
 */
export function SearchPicker<T extends { id: number }>({
  value,
  valueLabel,
  onChange,
  search,
  searchKey,
  renderOption,
  selectedFallback,
  placeholder,
  emptyText,
  clearLabel,
  disabled,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef(search);
  searchRef.current = search;

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) { setOptions([]); setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      searchRef.current(trimmed)
        .then((rows) => { if (!cancelled) setOptions(rows); })
        .catch(() => { if (!cancelled) setOptions([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, searchKey]);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-300 px-2 py-1.5 text-xs
        dark:border-slate-700">
        <span>{valueLabel ?? selectedFallback}</span>
        {!disabled && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-slate-400 hover:text-rose-600"
            aria-label={clearLabel}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="relative">
        <Search className="absolute right-2 top-2.5 h-3.5 w-3.5 text-slate-400" />
        <input
          className="w-full rounded-lg border border-slate-300 bg-white py-1.5 pl-2 pr-7 text-xs text-slate-900
            focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800
            dark:text-slate-100"
          value={query}
          disabled={disabled}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
        />
        {loading && <Loader2 className="absolute left-2 top-2.5 h-3.5 w-3.5 animate-spin text-slate-400" />}
      </div>
      {query.trim() && !loading && (
        <ul className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700">
          {options.length === 0 ? (
            <li className="p-2 text-[11px] text-slate-500">{emptyText}</li>
          ) : options.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => { onChange(item); setQuery(""); }}
                className="block w-full px-2 py-1.5 text-right text-xs hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                {renderOption(item)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
