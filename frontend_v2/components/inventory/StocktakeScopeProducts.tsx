/**
 * ST-2 — منتجات تصنيفٍ واحد داخل «جرد جديد»: تُفتح على طلب المستخدم (لا عند فتح
 * النافذة) **بلا أيّ تأشير مسبق**، فيختار منتجاً منتجاً أو التصنيف كاملاً.
 *
 * **الجلب ليس هنا:** `NewStocktakeModal` يحمل الكاش (مفتاحُه `(category,
 * include_inactive)` نفسه) وحارسَ التسابق، وهذا المكوّن يرسم حالةً وصلته
 * (`ScopeProductsLoad`): تحميلاً أو صفوفاً أو خطأً بزرّ «إعادة المحاولة».
 *
 * **ودلالة الأزرار على التصنيف لا على المعروض:** البحث يرشّح الصفوف الظاهرة
 * وحدها، و«تحديد الكل»/«مسح الكل» يُرقّيان الاختيار إلى التصنيف نفسه أو يُلغيانه
 * (`setCategoryProducts` في `utils/stocktake.ts`) — فعدّادُ «محدَّد X من Y» يبقى
 * عدّاد التصنيف ولو ضاق البحث.
 *
 * **مربّع «الكل» و«لا شيء» ليسا هنا:** التصنيف المشمول بكامله يُظهر كلّ صفوفه
 * مؤشَّرة (المحمَّل هو ما يعرفه المستدعي)، ومربّعُ التصنيف في الشجرة يبقى هو
 * المرجع البصري للحالة الكاملة/الجزئية.
 */
import React, { useMemo, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { formatNumber } from '../../utils/formatNumber';
import type { StocktakeScopeProduct } from '../../types/inventory';

/** حالة قائمة منتجات تصنيفٍ واحد — يملكها المستدعي (الكاش وحارس التسابق). */
export type ScopeProductsLoad =
  | { status: 'loading'; rows: StocktakeScopeProduct[] }
  | { status: 'ready'; rows: StocktakeScopeProduct[] }
  | { status: 'error'; rows: StocktakeScopeProduct[]; message: string };

type Props = {
  /** اسم التصنيف للعنوان — «بدون تصنيف» يُمرَّر نصّاً ليس `null`. */
  categoryName: string;
  load: ScopeProductsLoad;
  /** معرّفات المشمول صراحةً **أو** بكامل تصنيفه — مربّعُ كلّ صفٍّ يُقرأ منه. */
  selectedIds: ReadonlySet<number>;
  disabled?: boolean;
  onToggle: (product: StocktakeScopeProduct) => void;
  onSetAll: (mode: 'all' | 'none') => void;
  onRetry: () => void;
};

export const StocktakeScopeProducts: React.FC<Props> = ({
  categoryName, load, selectedIds, disabled, onToggle, onSetAll, onRetry,
}) => {
  const [query, setQuery] = useState('');
  const rows = load.rows;

  // بحثٌ محلي: الاسم أو الرمز — لا طلبَ خادمٍ لكل حرف (القائمة محمَّلة أصلاً).
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('ar');
    if (!needle) return rows;
    return rows.filter((product) => `${product.name} ${product.sku}`
      .toLocaleLowerCase('ar').includes(needle));
  }, [query, rows]);

  const searching = query.trim() !== '';

  return (
    <div
      data-testid="stocktake-scope-products"
      className="ms-4 mt-1 space-y-1.5 rounded border border-[var(--ktra-border-soft)] bg-[var(--ktra-surface)] p-2"
    >
      <div className="text-xs font-medium text-[var(--ktra-ink)]">منتجات {categoryName}</div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-40 flex-1">
          <Search className="pointer-events-none absolute end-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--ktra-ink-soft)]" />
          <input
            className="ktra-input w-full pe-7"
            placeholder="ابحث في منتجات هذا التصنيف"
            aria-label="ابحث في منتجات هذا التصنيف"
            value={query}
            disabled={disabled}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <button
          type="button"
          className="ktra-toolbtn"
          disabled={disabled || rows.length === 0}
          onClick={() => onSetAll('all')}
        >
          تحديد الكل
        </button>
        <button
          type="button"
          className="ktra-toolbtn"
          disabled={disabled || rows.length === 0}
          onClick={() => onSetAll('none')}
        >
          مسح الكل
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--ktra-ink-soft)]">
        <span>
          محدَّد {formatNumber(selectedIds.size)} من {formatNumber(rows.length)}
        </span>
        {searching && (
          <span>
            ظاهر {formatNumber(visible.length)} من {formatNumber(rows.length)}
          </span>
        )}
      </div>

      {load.status === 'error' && (
        <div className="ktra-banner ktra-banner--err flex items-center gap-2 text-sm">
          <span className="flex-1">{load.message}</span>
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={disabled}
            onClick={onRetry}
          >
            <RefreshCw className="h-4 w-4" />
            إعادة المحاولة
          </button>
        </div>
      )}

      {load.status !== 'error' && rows.length === 0 && (
        <div className="p-2 text-center text-xs text-[var(--ktra-ink-soft)]">
          {load.status === 'loading' ? 'جارٍ تحميل المنتجات…' : 'لا منتجات في هذا التصنيف'}
        </div>
      )}

      {load.status !== 'error' && rows.length > 0 && visible.length === 0 && (
        <div className="p-2 text-center text-xs text-[var(--ktra-ink-soft)]">
          لا تطابق في منتجات هذا التصنيف
        </div>
      )}

      {visible.length > 0 && (
        <div className="max-h-48 space-y-0.5 overflow-y-auto">
          {visible.map((product) => (
            <label
              key={product.id}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm text-[var(--ktra-ink)] hover:bg-[var(--ktra-hover)]"
            >
              <input
                type="checkbox"
                className="h-3.5 w-3.5 shrink-0 accent-[var(--ktra-accent)]"
                checked={selectedIds.has(product.id)}
                disabled={disabled}
                aria-label={`اختيار ${product.name}`}
                onChange={() => onToggle(product)}
              />
              <span className="truncate">{product.name}</span>
              {product.sku && (
                <span className="shrink-0 text-xs text-[var(--ktra-ink-soft)]">{product.sku}</span>
              )}
              {!product.is_active && (
                <span className="ms-auto shrink-0 rounded bg-[var(--ktra-hover)] px-1 text-[10px] text-[var(--ktra-ink-soft)]">
                  غير فعّال
                </span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
};

export default StocktakeScopeProducts;
