/**
 * task13 M5 — AseelAutocomplete
 * منتقي مدمج بنمط دفترة: حقل نصي داخل خلية الجدول، الكتابة تفتح قائمة
 * منسدلة صغيرة تحت الحقل تفلتر فورياً وتقدّم أقرب تطابق أولاً، مع خيار
 * «+ إضافة كصنف جديد» عند توفر onFreeText. يستبدل المودالات العريضة
 * (ItemSearchModal / SalesProductPickerModal) كمسار الإدخال الأساسي.
 *
 * القائمة تُرسم عبر portal على <body> (position:fixed) كي لا تُقص بمناطق
 * overflow في الجداول، وتُغلق عند النقر خارجها أو Esc أو تمرير الصفحة.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Info } from 'lucide-react';
import { usePriceVisibility } from '../../contexts/PriceVisibilityContext';

export interface AseelPriceInfo {
  label: string;
  value: string;
  link?: string;
}

export interface AseelAutocompleteOption {
  id: string | number;
  /** النص الأساسي (اسم الصنف) — هدف المطابقة الأول */
  label: string;
  /** سطر ثانوي اختياري (موديل / SKU / رصيد) — هدف مطابقة ثانٍ */
  sub?: string;
  /** أسعار متعددة قابلة للنقر (آخر شراء، أقل سعر، الخ) */
  prices?: AseelPriceInfo[];
  /** task24: السعر المقترح معروض مباشرة في الخيار (نص منسّق) — بلا نقر. */
  price?: string;
  /** task24: تسمية مصدر السعر (آخر بيع/شراء، عرض سعر، افتراضي…). */
  priceLabel?: string;
}

export interface AseelAutocompleteProps {
  /** النص المثبت حالياً في السطر (اسم الصنف المختار) */
  value: string;
  options: AseelAutocompleteOption[];
  onPick: (id: string | number) => void;
  /** DEF-008: عند توفره تظهر أيقونة (i) لكل خيار → تفتح بطاقة الصنف دون اختياره. */
  onInfo?: (id: string | number) => void;
  /** عند توفره: خيار «+ إضافة …» يثبت النص المكتوب كصنف حر/جديد */
  onFreeText?: (text: string) => void;
  placeholder?: string;
  disabled?: boolean;
  maxResults?: number;
}

const MAX_DEFAULT = 8;

/** ترتيب أقرب تطابق: يبدأ بالنص < يحتويه في الاسم < يحتويه في السطر الثانوي */
function rank(options: AseelAutocompleteOption[], q: string, max: number) {
  const needle = q.trim().toLowerCase();
  if (!needle) return options.slice(0, max);
  const scored: { opt: AseelAutocompleteOption; score: number }[] = [];
  for (const opt of options) {
    const label = (opt.label || '').toLowerCase();
    const sub = (opt.sub || '').toLowerCase();
    let score: number;
    if (label.startsWith(needle)) score = 0;
    else if (label.includes(needle)) score = 1;
    else if (sub.includes(needle)) score = 2;
    else continue;
    scored.push({ opt, score });
  }
  scored.sort((a, b) => a.score - b.score || a.opt.label.length - b.opt.label.length);
  return scored.slice(0, max).map((s) => s.opt);
}

export const AseelAutocomplete: React.FC<AseelAutocompleteProps> = ({
  value,
  options,
  onPick,
  onInfo,
  onFreeText,
  placeholder = 'اكتب للبحث…',
  disabled,
  maxResults = MAX_DEFAULT,
}) => {
  const { visible: showPrices } = usePriceVisibility(); // خصوصية: إخفاء الأسعار أمام الزبون
  const [query, setQuery] = useState<string | null>(null); // null = غير مفتوح، يعرض value
  const [sel, setSel] = useState(0);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  const open = query !== null;
  const matches = useMemo(
    () => (open ? rank(options, query ?? '', maxResults) : []),
    [open, options, query, maxResults],
  );
  const canCreate = !!onFreeText && (query ?? '').trim().length > 0;
  const rowCount = matches.length + (canCreate ? 1 : 0);

  const reposition = () => {
    const r = inputRef.current?.getBoundingClientRect();
    if (!r) return;
    const width = Math.max(r.width, 280);
    // RTL: نحاذي حافة الحقل اليمنى ونمنع الخروج عن يسار الشاشة
    const left = Math.max(4, Math.min(r.right - width, window.innerWidth - width - 4));
    setPos({ top: r.bottom + 2, left, width });
  };

  const openList = () => {
    if (disabled) return;
    setQuery(query ?? '');
    setSel(0);
    reposition();
  };

  const close = () => { setQuery(null); setPos(null); };

  const commit = (idx: number) => {
    if (idx < matches.length) {
      onPick(matches[idx].id);
    } else if (canCreate) {
      onFreeText!((query ?? '').trim());
    }
    close();
  };

  // إغلاق عند النقر خارج الحقل والقائمة، وعند تمرير/تحجيم الصفحة
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (inputRef.current?.contains(t) || popRef.current?.contains(t)) return;
      close();
    };
    const onScroll = (e: Event) => {
      if (popRef.current?.contains(e.target as Node)) return; // تمرير داخل القائمة نفسها
      close();
    };
    document.addEventListener('mousedown', onDown);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') { e.preventDefault(); openList(); }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, rowCount - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (rowCount > 0) commit(Math.min(sel, rowCount - 1)); }
    else if (e.key === 'Tab') { close(); }
  };

  return (
    <>
      <input
        ref={inputRef}
        className="aseel-input"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        disabled={disabled}
        placeholder={placeholder}
        value={open ? (query ?? '') : value}
        onFocus={openList}
        onClick={openList}
        onChange={(e) => { setQuery(e.target.value); setSel(0); reposition(); }}
        onKeyDown={onKeyDown}
      />
      {open && pos && createPortal(
        <div
          ref={popRef}
          className="aseel-autocomplete-pop"
          role="listbox"
          dir="rtl"
          style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width }}
        >
          {matches.map((opt, i) => (
            <div
              key={opt.id}
              className={`aseel-autocomplete-row${i === sel ? ' aseel-autocomplete-row--sel' : ''}`}
              role="option"
              aria-selected={i === sel}
              onMouseEnter={() => setSel(i)}
            >
              <button
                type="button"
                className="aseel-autocomplete-main"
                onMouseDown={(e) => { e.preventDefault(); commit(i); }}
              >
                <span className="aseel-autocomplete-label">{opt.label}</span>
                {opt.sub && <span className="aseel-autocomplete-sub">{opt.sub}</span>}
                {!showPrices ? null : opt.prices && opt.prices.length > 0 ? (
                  <div className="flex gap-2 items-center ml-auto">
                    {opt.prices.map((p, idx) => {
                      const content = (
                        <span className="aseel-autocomplete-price !ml-0" title={p.label}>
                          {p.value}
                          {p.label && <em className="aseel-autocomplete-price-src">{p.label}</em>}
                        </span>
                      );
                      return p.link ? (
                        <a 
                          key={idx} 
                          href={p.link} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          className="hover:opacity-80 transition-opacity"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {content}
                        </a>
                      ) : (
                        <React.Fragment key={idx}>{content}</React.Fragment>
                      );
                    })}
                  </div>
                ) : opt.price ? (
                  <span className="aseel-autocomplete-price" title={opt.priceLabel}>
                    {opt.price}
                    {opt.priceLabel && (
                      <em className="aseel-autocomplete-price-src">{opt.priceLabel}</em>
                    )}
                  </span>
                ) : opt.priceLabel ? (
                  <span className="aseel-autocomplete-price aseel-autocomplete-price--none">
                    {opt.priceLabel}
                  </span>
                ) : null}
              </button>
              {onInfo && (
                <button
                  type="button"
                  className="aseel-autocomplete-info"
                  title="بطاقة الصنف"
                  aria-label="بطاقة الصنف"
                  onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); onInfo(opt.id); close(); }}
                >
                  <Info className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
          {matches.length === 0 && !canCreate && (
            <div className="aseel-autocomplete-empty">لا تطابق</div>
          )}
          {canCreate && (
            <button
              type="button"
              role="option"
              aria-selected={sel === matches.length}
              className={`aseel-autocomplete-row aseel-autocomplete-row--create${sel === matches.length ? ' aseel-autocomplete-row--sel' : ''}`}
              onMouseEnter={() => setSel(matches.length)}
              onMouseDown={(e) => { e.preventDefault(); commit(matches.length); }}
            >
              <Plus className="h-3 w-3" />
              <span>إضافة «{(query ?? '').trim()}» كصنف جديد</span>
            </button>
          )}
        </div>,
        document.body,
      )}
    </>
  );
};
