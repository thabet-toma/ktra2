/**
 * task13 M5 — KitAutocomplete
 * منتقي مدمج بنمط دفترة: حقل نصي داخل خلية الجدول، الكتابة تفتح قائمة
 * منسدلة صغيرة تحت الحقل تفلتر فورياً وتقدّم أقرب تطابق أولاً، مع خيار
 * «+ إضافة كمنتج جديد» عند توفر onFreeText. يستبدل المودالات العريضة
 * (ItemSearchModal / SalesProductPickerModal) كمسار الإدخال الأساسي.
 *
 * القائمة تُرسم عبر portal على <body> (position:fixed) كي لا تُقص بمناطق
 * overflow في الجداول، وتُغلق عند النقر خارجها أو Esc أو تمرير الصفحة.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Info, Pencil, Search } from 'lucide-react';
import { usePriceVisibility } from '../../contexts/PriceVisibilityContext';
import { firstMatchRange, rankOptions } from '../../utils/autocompleteRank';

export interface KitPriceInfo {
  label: string;
  value: string;
  link?: string;
}

export interface KitAutocompleteOption {
  id: string | number;
  /** النص الأساسي (اسم المنتج) — هدف المطابقة الأول */
  label: string;
  /** سطر ثانوي اختياري (موديل / SKU / رصيد) — هدف مطابقة ثانٍ */
  sub?: string;
  /** أسعار متعددة قابلة للنقر (آخر شراء، أقل سعر، الخ) */
  prices?: KitPriceInfo[];
  /** task24: السعر المقترح معروض مباشرة في الخيار (نص منسّق) — بلا نقر. */
  price?: string;
  /** task24: تسمية مصدر السعر (آخر بيع/شراء، عرض سعر، افتراضي…). */
  priceLabel?: string;
  /** T-REORDER: شارة حالة قصيرة بجانب الاسم (نفذ/منخفض) — تُبنى من
   *  `utils/stockBadge` كي لا تُكتب القاعدة في كل شاشة. */
  badge?: { text: string; tone: 'danger' | 'warn'; title?: string };
  /** T-SEARCH: نصٌّ إضافي يُبحَث فيه ولا يُعرض — SKU والباركود والهاتف.
   *  يُمرَّر بحروف صغيرة مسبقاً، فالمطابقة تجري لكل ضغطة مفتاح. */
  keywords?: string;
}

export interface KitAutocompleteProps {
  /** النص المثبت حالياً في السطر (اسم المنتج المختار) */
  value: string;
  options: KitAutocompleteOption[];
  onPick: (id: string | number) => void;
  /** DEF-008: عند توفره تظهر أيقونة (i) لكل خيار → تفتح بطاقة المنتج دون اختياره. */
  onInfo?: (id: string | number) => void;
  /** T-ITEMS M3: عند توفره يظهر قلمٌ بجانب (i) → تحريرٌ سريع دون مغادرة المستند.
   *  المقعد هنا لا في كل محرّر: تمريرة واحدة تخدم كل شاشة تستعمل المنتقي. */
  onEdit?: (id: string | number) => void;
  /** عند توفره: خيار «+ إضافة …» يثبت النص المكتوب كمنتج حر/جديد */
  onFreeText?: (text: string) => void;
  /** نص خيار النص الحر — الافتراضي «إضافة … كمنتج جديد». يُمرَّر له النص المكتوب
   *  كي تصف كل شاشة ما سيحدث فعلاً (مورد مبدئي، بند نصّي…) لا «منتج» دائماً. */
  createLabel?: (text: string) => string;
  /** ISSUE #110: يُنادى مع **كل حرف** يكتبه المستخدم — لا عند المغادرة (blur/close).
   *  اختياري ومنفصل تماماً عن `onFreeText`: `close()` يُستدعى من نقرة خارج الحقل
   *  ومن تمرير الصفحة وتغيير حجم النافذة، فيمحو `query` بلا نداء `onFreeText`
   *  (وإغلاق التبويب لا يُطلق حدث مغادرة أصلاً). من يريد ألا يضيع النص المكتوب
   *  يستعمل هذه الخاصية ليحتفظ به في حالة الشاشة بنفسه — لا تُطلِق أي فعلٍ ثانٍ
   *  (كفتح نافذة إنشاء) تلقائياً، فذلك قرار الشاشة المستدعية وحدها. */
  onTextChange?: (text: string) => void;
  placeholder?: string;
  disabled?: boolean;
  maxResults?: number;
  /** T-SEARCH: عند تجاوز المطابقات السقف يظهر صفّ «+N أخرى» يستدعيها
   *  بالاستعلام الحالي — عادةً لفتح الفهرس الكامل مُصفّىً مسبقاً. */
  onShowMore?: (query: string) => void;
}

const MAX_DEFAULT = 8;

/**
 * غلافٌ رقيق فوق `utils/autocompleteRank` — القاعدة هناك كي تُختبر وحدها،
 * وهنا يبقى الرسم وحده.
 */
function rank(options: KitAutocompleteOption[], q: string, max: number) {
  return rankOptions(options, q, max);
}

/** يظلّل أول تطابق في النصّ — بلا HTML خام. */
function highlight(text: string, q: string): React.ReactNode {
  const at = firstMatchRange(text, q);
  if (!at) return text;
  return (
    <>
      {text.slice(0, at.start)}
      <mark className="rounded bg-amber-200 px-0.5 text-inherit">
        {text.slice(at.start, at.end)}
      </mark>
      {text.slice(at.end)}
    </>
  );
}

export const KitAutocomplete: React.FC<KitAutocompleteProps> = ({
  value,
  options,
  onPick,
  onInfo,
  onEdit,
  onFreeText,
  createLabel,
  placeholder = 'اكتب للبحث…',
  disabled,
  maxResults = MAX_DEFAULT,
  onShowMore,
  onTextChange,
}) => {
  const { visible: showPrices } = usePriceVisibility(); // خصوصية: إخفاء الأسعار أمام الزبون
  const [query, setQuery] = useState<string | null>(null); // null = غير مفتوح، يعرض value
  const [sel, setSel] = useState(0);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  const open = query !== null;
  const ranked = useMemo(
    () => (open
      ? rank(options, query ?? '', maxResults)
      : { matches: [] as KitAutocompleteOption[], total: 0 }),
    [open, options, query, maxResults],
  );
  const matches = ranked.matches;
  const hiddenCount = Math.max(ranked.total - matches.length, 0);
  const canShowMore = !!onShowMore && hiddenCount > 0;
  const canCreate = !!onFreeText && (query ?? '').trim().length > 0;
  const rowCount = matches.length + (canShowMore ? 1 : 0) + (canCreate ? 1 : 0);

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
    } else if (canShowMore && idx === matches.length) {
      // لا نُغلق بالنتيجة: الفهرس الكامل يفتح على الاستعلام نفسه.
      onShowMore!((query ?? '').trim());
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
        className="ktra-input"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        disabled={disabled}
        placeholder={placeholder}
        value={open ? (query ?? '') : value}
        onFocus={openList}
        onClick={openList}
        onChange={(e) => {
          setQuery(e.target.value);
          setSel(0);
          reposition();
          onTextChange?.(e.target.value);
        }}
        onKeyDown={onKeyDown}
      />
      {open && pos && createPortal(
        <div
          ref={popRef}
          className="ktra-autocomplete-pop"
          role="listbox"
          dir="rtl"
          style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width }}
        >
          {matches.map((opt, i) => (
            <div
              key={opt.id}
              className={`ktra-autocomplete-row${i === sel ? ' ktra-autocomplete-row--sel' : ''}`}
              role="option"
              aria-selected={i === sel}
              onMouseEnter={() => setSel(i)}
            >
              <button
                type="button"
                className="ktra-autocomplete-main"
                onMouseDown={(e) => { e.preventDefault(); commit(i); }}
              >
                <span className="ktra-autocomplete-label">
                  {highlight(opt.label, query ?? '')}
                </span>
                {opt.badge && (
                  <span
                    title={opt.badge.title}
                    className={`shrink-0 rounded px-1 py-px text-[10px] font-semibold border ${
                      opt.badge.tone === 'danger'
                        ? 'bg-[var(--ktra-danger-bg)] border-[var(--ktra-danger-bd)] text-[var(--ktra-danger)]'
                        : 'bg-[var(--ktra-warn-bg)] border-[var(--ktra-warn-bd)] text-[var(--ktra-warn-fg)]'
                    }`}
                  >{opt.badge.text}</span>
                )}
                {opt.sub && (
                  <span className="ktra-autocomplete-sub">
                    {highlight(opt.sub, query ?? '')}
                  </span>
                )}
                {!showPrices ? null : opt.prices && opt.prices.length > 0 ? (
                  <div className="flex gap-2 items-center ml-auto">
                    {opt.prices.map((p, idx) => {
                      const content = (
                        <span className="ktra-autocomplete-price !ml-0" title={p.label}>
                          {p.value}
                          {p.label && <em className="ktra-autocomplete-price-src">{p.label}</em>}
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
                  <span className="ktra-autocomplete-price" title={opt.priceLabel}>
                    {opt.price}
                    {opt.priceLabel && (
                      <em className="ktra-autocomplete-price-src">{opt.priceLabel}</em>
                    )}
                  </span>
                ) : opt.priceLabel ? (
                  <span className="ktra-autocomplete-price ktra-autocomplete-price--none">
                    {opt.priceLabel}
                  </span>
                ) : null}
              </button>
              {onInfo && (
                <button
                  type="button"
                  className="ktra-autocomplete-info"
                  title="بطاقة المنتج"
                  aria-label="بطاقة المنتج"
                  onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); onInfo(opt.id); close(); }}
                >
                  <Info className="h-3.5 w-3.5" />
                </button>
              )}
              {onEdit && (
                <button
                  type="button"
                  className="ktra-autocomplete-info"
                  title="تعديل سريع للمنتج"
                  aria-label="تعديل سريع للمنتج"
                  onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); onEdit(opt.id); close(); }}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
          {matches.length === 0 && !canCreate && (
            <div className="ktra-autocomplete-empty">لا تطابق</div>
          )}
          {canShowMore && (
            <button
              type="button"
              role="option"
              data-testid="autocomplete-show-more"
              aria-selected={sel === matches.length}
              className={`ktra-autocomplete-row ktra-autocomplete-row--create${sel === matches.length ? ' ktra-autocomplete-row--sel' : ''}`}
              onMouseEnter={() => setSel(matches.length)}
              onMouseDown={(e) => { e.preventDefault(); commit(matches.length); }}
            >
              <Search className="h-3 w-3" />
              <span>{`عرض ${hiddenCount} نتيجة أخرى في الفهرس الكامل…`}</span>
            </button>
          )}
          {canCreate && (
            <button
              type="button"
              role="option"
              aria-selected={sel === matches.length + (canShowMore ? 1 : 0)}
              className={`ktra-autocomplete-row ktra-autocomplete-row--create${sel === matches.length + (canShowMore ? 1 : 0) ? ' ktra-autocomplete-row--sel' : ''}`}
              onMouseEnter={() => setSel(matches.length + (canShowMore ? 1 : 0))}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(matches.length + (canShowMore ? 1 : 0));
              }}
            >
              <Plus className="h-3 w-3" />
              <span>
                {createLabel
                  ? createLabel((query ?? '').trim())
                  : `إضافة «${(query ?? '').trim()}» كمنتج جديد`}
              </span>
            </button>
          )}
        </div>,
        document.body,
      )}
    </>
  );
};
