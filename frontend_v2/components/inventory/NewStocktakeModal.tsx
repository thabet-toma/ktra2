/**
 * K2 — «جرد جديد» في خطوتين (خطة §5.1): الرأس أولاً، ثم «ماذا سنجرد؟».
 *
 * الخطوة الثانية تعرض شجرة التصنيفات كاملةً بعدّادات الخادم، ودلالة الاختيار
 * صريحة (قرار ٣): تأشير عقدة = منتجاتها المباشرة وحدها؛ الأب المؤشَّر يؤشّر
 * أحفاده بصرياً ويمكن إلغاء ابنٍ فيبقى الأب «جزئياً». و«بدون تصنيف» قرارٌ منفصل
 * لأن الشجرة لا تحتويه.
 *
 * كل الأرقام من `GET stocktakes/scope-counts/` لا من كتالوجٍ منزَّل، والملخّص
 * الوحيد المرسوم هو هذا السطر — مكوّن الشجرة يستقبل `summary` بديلاً بدل
 * ملخّصه الافتراضي كي لا يقرأ المستخدم رقمين مختلفين.
 *
 * **ST-2 — منتجاتٌ صريحة تحت كل تصنيف:** زرُّ «منتجات» في صفّ التصنيف (وفي صفّ
 * «بدون تصنيف») يفتح لوحةً **كسولاً**: تُطلب منتجاتُ ذلك التصنيف وحدها من
 * `stocktakes/scope-products/` أوّل مرّة، بكاشٍ مفتاحه `(category,
 * include_inactive)` وحارسِ تسابقٍ لكل مفتاح. اللوحة تُفتح **بلا أيّ تأشير**، ومنها
 * يُختار منتجٌ منتجاً أو يُرقّى الاختيار إلى التصنيف كامله. والحالة كلها —
 * `categories` + `products` + `uncategorized` — تُدار بدوالّ `utils/stocktake.ts`
 * وحدها (`toggleScopeProduct` · `setCategoryProducts` · `reconcileScopeProducts` ·
 * `pruneInactiveScopeProducts` · `partialCategoryIds`)، فيبقى المعروض والمرسَل
 * تعبيراً واحداً عن الاختيار نفسه.
 */
import React, {
  useCallback, useEffect, useId, useMemo, useReducer, useRef, useState,
} from 'react';
import { ChevronLeft, RefreshCw } from 'lucide-react';
import { CategoryTreeSelect, type CategoryTreeOption } from './CategoryTreeSelect';
import { StocktakeDialog } from './StocktakeDialog';
import {
  StocktakeScopeProducts, type ScopeProductsLoad,
} from './StocktakeScopeProducts';
import { inventoryApi } from '../../services/inventoryApi';
import { formatNumber } from '../../utils/formatNumber';
import { todayIso } from '../../utils/formatDate';
import {
  arabicCount,
  buildStocktakeCreateBody,
  canCreateFromScope,
  partialCategoryIds,
  pruneInactiveScopeProducts,
  reconcileScopeProducts,
  setCategoryProducts,
  summarizeScopeSelection,
  toggleScopeProduct,
  type ScopeProductPick,
  type StocktakeScopeMode,
} from '../../utils/stocktake';
import type {
  Stocktake, StocktakeScopeCounts, StocktakeScopeProduct, WarehouseOption,
} from '../../types/inventory';

type Props = {
  categories: CategoryTreeOption[];
  warehouses: WarehouseOption[];
  onClose: () => void;
  onCreated: (result: { stocktake: Stocktake; etag: string | null }) => void;
};

const MODES: { value: StocktakeScopeMode; label: string; hint: string }[] = [
  {
    value: 'all',
    label: 'كل المنتجات',
    hint: 'كل منتجٍ غير خدمي — النشطة فقط ما لم تختر غير الفعّالة.',
  },
  { value: 'categories', label: 'تصنيفات محدّدة', hint: 'تختار فروع الشجرة أو منتجاتٍ بعينها تحت كل تصنيف.' },
  { value: 'manual', label: 'يدوي (فارغ)', hint: 'جردٌ بلا بنود — تضيفها من الورقة واحداً واحداً.' },
];

/** مفتاحُ اللوحة: `none` لـ«بدون تصنيف»، والتصنيفُ معرّفه. */
const scopeProductPanelKey = (category: number | null): string =>
  (category === null ? 'none' : String(category));

/** مفتاحُ الكاش: التصنيفُ والعلم معاً — قراءتان مختلفتان لقائمتين مختلفتين. */
const scopeProductCacheKey = (category: number | null, inactive: boolean): string =>
  `${scopeProductPanelKey(category)}|${inactive ? 1 : 0}`;

/**
 * نصّ ما استُبعد عند إطفاء «غير الفعّالة» — القاعدة العربية في `arabicCount` نفسها
 * (الذيل ثابت، والعدد يصوغ ما يليه)، فلا نسخةَ ثانية من قاعدة العدد.
 */
const prunedNotice = (count: number): string => `استُبعد ${arabicCount(count, {
  one: 'منتجٌ واحد غير فعّال',
  two: 'منتجان غير فعّالين',
  few: 'منتجات غير فعّالة',
  many: 'منتجاً غير فعّال',
})} من الاختيار`;

export const NewStocktakeModal: React.FC<Props> = ({
  categories, warehouses, onClose, onCreated,
}) => {
  const titleId = useId();

  const [step, setStep] = useState<1 | 2>(1);
  const [date, setDate] = useState(todayIso());
  const [warehouse, setWarehouse] = useState<number | ''>('');
  const [notes, setNotes] = useState('');
  const [mode, setMode] = useState<StocktakeScopeMode>('categories');
  const [checkedIds, setCheckedIds] = useState<number[]>([]);
  /** ST-2: منتجاتٌ مشمولة صراحةً — بمعرّف المنتج، كما تطلب دوالّ `utils/stocktake.ts`. */
  const [products, setProducts] = useState<ReadonlyMap<number, ScopeProductPick>>(new Map());
  const [uncategorized, setUncategorized] = useState(false);
  /** ST-2: لوحات المنتجات المفتوحة (`none` = «بدون تصنيف») — الجلب كسولٌ عند الفتح. */
  const [openProducts, setOpenProducts] = useState<ReadonlySet<string>>(new Set());
  /** ST-2: ما استُبعد بإطفاء «غير الفعّالة» — يُعلَن ولا يُبتلع. */
  const [pruned, setPruned] = useState(0);
  /**
   * كاشُ منتجات التصنيفات: `ref` لأن قراءته تقع لحظةَ الفتح وفي `siblings` قبل
   * إعادة الرسم، و`bump` يُعيد الرسم بعد كل تغيير. ومفتاحُه `(category,
   * include_inactive)` فلا تُقرأ قائمةُ العلم برسم العلم الآخر.
   */
  const productsCacheRef = useRef(new Map<string, ScopeProductsLoad>());
  /** حارسُ التسابق لكل مفتاح — تبديلُ العلم بسرعة يُطلق طلبين لتصنيفٍ واحد. */
  const productsRequestRef = useRef(new Map<string, number>());
  const [, bumpProductsCache] = useReducer((value: number) => value + 1, 0);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [counts, setCounts] = useState<StocktakeScopeCounts | null>(null);
  const [countsLoading, setCountsLoading] = useState(true);
  const [countsError, setCountsError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // تسلسل طلبات العدّادات: تبديل «غير الفعّالة» بسرعة يُطلق طلبين، وردُّ
  // الأقدم قد يهبط بعد الأحدث — يحكم آخرُ طلبٍ أُطلق وحده.
  const countsRequestRef = useRef(0);

  const loadCounts = useCallback(async () => {
    const requestId = countsRequestRef.current + 1;
    countsRequestRef.current = requestId;
    setCountsLoading(true);
    setCountsError(null);
    try {
      const next = await inventoryApi.getStocktakeScopeCounts(includeInactive);
      if (countsRequestRef.current !== requestId) return;
      setCounts(next);
    } catch (reason) {
      if (countsRequestRef.current !== requestId) return;
      setCounts(null);
      setCountsError(reason instanceof Error ? reason.message : 'تعذّر حساب عدد المنتجات');
    } finally {
      if (countsRequestRef.current === requestId) setCountsLoading(false);
    }
  }, [includeInactive]);

  // تبديل «غير الفعّالة» يعيد القراءة من الخادم: العدّاد يجب أن يطابق البنود.
  useEffect(() => { void loadCounts(); }, [loadCounts]);

  /**
   * جلبُ منتجات تصنيفٍ واحد — كسولٌ (أوّلَ فتحٍ للوحة) ولا يُطلب مرّتين لنفس
   * المفتاح. والخطأُ لا يُخزَّن نهائياً: `force` (زرّ «إعادة المحاولة») يعيده.
   */
  const loadScopeProducts = useCallback(async (
    category: number | null, inactive: boolean, force = false,
  ) => {
    const cacheKey = scopeProductCacheKey(category, inactive);
    const cached = productsCacheRef.current.get(cacheKey);
    if (!force && cached && cached.status !== 'error') return;
    const requestId = (productsRequestRef.current.get(cacheKey) ?? 0) + 1;
    productsRequestRef.current.set(cacheKey, requestId);
    productsCacheRef.current.set(cacheKey, { status: 'loading', rows: cached?.rows ?? [] });
    bumpProductsCache();
    try {
      const rows = await inventoryApi.getStocktakeScopeProducts(
        category === null ? 'none' : category, inactive,
      );
      if (productsRequestRef.current.get(cacheKey) !== requestId) return;
      productsCacheRef.current.set(cacheKey, { status: 'ready', rows });
    } catch (reason) {
      if (productsRequestRef.current.get(cacheKey) !== requestId) return;
      productsCacheRef.current.set(cacheKey, {
        status: 'error',
        rows: cached?.rows ?? [],
        message: reason instanceof Error ? reason.message : 'تعذّر تحميل منتجات التصنيف',
      });
    }
    bumpProductsCache();
  }, []);

  const toggleProductsPanel = (category: number | null) => {
    const key = scopeProductPanelKey(category);
    const open = openProducts.has(key);
    setOpenProducts((prev) => {
      const next = new Set(prev);
      if (open) next.delete(key);
      else next.add(key);
      return next;
    });
    if (!open) void loadScopeProducts(category, includeInactive);
  };

  /** منتجاتُ التصنيف كما حُمِّلت — هي `siblings` في دوالّ ST-2A. */
  const picksOf = (
    category: number | null, rows: StocktakeScopeProduct[],
  ): ScopeProductPick[] => rows.map((row) => ({
    id: row.id, category, isActive: row.is_active,
  }));

  /** منتجٌ واحد: قد يرقّي الاختيار إلى تصنيفٍ كامل أو يُنزعه (دلالة ST-2A). */
  const toggleScopePick = (
    category: number | null, product: StocktakeScopeProduct, rows: StocktakeScopeProduct[],
  ) => {
    const next = toggleScopeProduct(
      { categories: checkedIds, products, uncategorized },
      { id: product.id, category, isActive: product.is_active },
      picksOf(category, rows),
    );
    setCheckedIds(next.categories);
    setProducts(next.products);
    setUncategorized(next.uncategorized);
  };

  /** «تحديد الكل/مسح الكل» **للتصنيف** لا للمعروض بعد البحث. */
  const setScopeCategory = (
    category: number | null, selection: 'all' | 'none', rows: StocktakeScopeProduct[],
  ) => {
    const next = setCategoryProducts(
      { categories: checkedIds, products, uncategorized },
      category,
      selection,
      picksOf(category, rows),
    );
    setCheckedIds(next.categories);
    setProducts(next.products);
    setUncategorized(next.uncategorized);
  };

  /** تأشيرُ تصنيفٍ يغطّي منتجاته الصريحة ⇒ تُسقَط (لا تُذكر مرّتين ولا تُرسَل). */
  const changeCategories = (next: number[]) => {
    setCheckedIds(next);
    setProducts(reconcileScopeProducts({
      categories: next, products, uncategorized,
    }).products);
  };

  /** «إلغاء الكل» في الشجرة: العلمُ والمنتجاتُ الصريحة لا يعرفها `onChange` وحده. */
  const clearScopeSelection = () => {
    setProducts(new Map());
    setUncategorized(false);
  };

  const changeUncategorized = (next: boolean) => {
    setUncategorized(next);
    setProducts(reconcileScopeProducts({
      categories: checkedIds, products, uncategorized: next,
    }).products);
  };

  const changeIncludeInactive = (next: boolean) => {
    setIncludeInactive(next);
    if (next) {
      setPruned(0);
    } else {
      // كلُّ ما حُمِّل بالعلم يقرّر: منتجٌ غيرُ فعّالٍ اختير صراحةً يخرج، ومنتجٌ غاب
      // عن تصنيفٍ أُعيدت قراءته خرج من الأهلية — والعددُ يُعلَن.
      const loaded: ScopeProductPick[] = [];
      for (const [key, entry] of productsCacheRef.current) {
        if (!key.endsWith('|1')) continue;
        const category = key === 'none|1' ? null : Number(key.split('|1')[0]);
        for (const row of entry.rows) {
          loaded.push({ id: row.id, category, isActive: row.is_active });
        }
      }
      const prunedState = pruneInactiveScopeProducts(
        { categories: checkedIds, products, uncategorized }, loaded,
      );
      setProducts(prunedState.state.products);
      setPruned(prunedState.removed);
    }
    // اللوحات المفتوحة تنتقل إلى مفتاح العلم الجديد: تُطلب إن لم تكن في كاشها،
    // وتُترك كما هي إن كانت (لا طلبَ ثانٍ ولا مسحَ لقائمةٍ محمَّلة).
    for (const key of openProducts) {
      void loadScopeProducts(key === 'none' ? null : Number(key), next);
    }
  };

  /** لوحةُ منتجات تصنيفٍ واحد بحالتها ومعرّفاتها المشمولة. */
  const scopeProductsPanel = (category: number | null, categoryName: string) => {
    const load = productsCacheRef.current.get(scopeProductCacheKey(category, includeInactive))
      ?? { status: 'loading' as const, rows: [] };
    const rows = load.rows;
    // المشمولُ بكامله لا يحمل منتجاتٍ صريحة (الترقية تنقّيها) — فتُقرأ كلُّ صفوفه
    // مؤشَّرةً، وإلّا قال العدّاد «محدَّد 0 من 3» عن تصنيفٍ مشمولٍ كلّه.
    const covered = category === null ? uncategorized : checkedIds.includes(category);
    const selectedIds = covered
      ? new Set(rows.map((row) => row.id))
      : new Set(
        [...products.values()]
          .filter((pick) => (pick.category ?? null) === category)
          .map((pick) => pick.id),
      );
    return (
      <StocktakeScopeProducts
        categoryName={categoryName}
        load={load}
        selectedIds={selectedIds}
        disabled={creating}
        onToggle={(product) => toggleScopePick(category, product, rows)}
        onSetAll={(selection) => setScopeCategory(category, selection, rows)}
        onRetry={() => void loadScopeProducts(category, includeInactive, true)}
      />
    );
  };

  const partialIds = useMemo(
    () => partialCategoryIds({ categories: checkedIds, products, uncategorized }),
    [checkedIds, products, uncategorized],
  );
  const summary = summarizeScopeSelection({
    mode, checkedIds, uncategorized, counts, products,
  });
  // اليدوي لا ينتظر عدّاداتٍ أصلاً: فشلُها لا يمنع جرداً فارغاً مشروعاً.
  const canCreate = step === 2
    && !creating
    && canCreateFromScope(mode, summary)
    && (mode === 'manual' || (!countsLoading && !countsError));

  const create = async () => {
    if (!canCreate) return;
    setCreating(true);
    setError(null);
    try {
      const result = await inventoryApi.createStocktake(buildStocktakeCreateBody({
        mode,
        stocktakeDate: date,
        warehouse: warehouse === '' ? null : Number(warehouse),
        notes,
        checkedIds,
        uncategorized,
        includeInactive,
        products,
      }));
      onCreated(result);
    } catch (reason) {
      // فشل الشبكة وفشل الخادم سواء: النافذة تبقى باختياراتها ورسالةٌ تشرح.
      // ورسالة 400 الخادمية تسمّي التصنيفات المرفوضة، فلا تُستبدل بنصٍّ عام.
      setError(reason instanceof Error ? reason.message : 'تعذّر إنشاء الجرد');
    } finally {
      setCreating(false);
    }
  };

  const summaryText = mode === 'manual'
    ? 'جرد يدوي — تُضاف البنود من الورقة'
    : countsError
      ? 'تعذّر حساب عدد المنتجات'
      : countsLoading && !counts
        ? 'جارٍ حساب المنتجات…'
        : `سيُجرد ${arabicCount(summary.products, {
          one: 'منتجٌ واحد', two: 'منتجان', few: 'منتجات', many: 'منتجاً', zero: '0 منتج',
        })} في ${arabicCount(summary.categories, {
          one: 'تصنيفٍ واحد', two: 'تصنيفين', few: 'تصنيفات', many: 'تصنيفاً', zero: '0 تصنيف',
        })}`;
  const emptyChoice = mode !== 'manual' && !countsLoading && !countsError
    && summary.products === 0;

  return (
    <StocktakeDialog
      title="جرد جديد"
      titleId={titleId}
      onClose={onClose}
      busy={creating}
      closeLabel="إغلاق نافذة الجرد الجديد"
      closeTitle="إغلاق"
      overlayClassName="z-[90]"
      panelClassName="flex max-h-[90vh] max-w-2xl flex-col"
      bodyClassName="min-h-0 flex-1 space-y-4 overflow-y-auto p-4"
      headerExtra={(
        <span className="shrink-0 text-xs text-[var(--ktra-ink-soft)]">
          الخطوة {formatNumber(step)} من {formatNumber(2)}
        </span>
      )}
      footer={step === 1 ? (
        <>
          <button type="button" className="ktra-btn" onClick={onClose} disabled={creating}>
            إلغاء
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            disabled={!date || creating}
            onClick={() => setStep(2)}
          >
            التالي
            <ChevronLeft className="h-4 w-4" />
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className="ktra-btn"
            onClick={() => setStep(1)}
            disabled={creating}
          >
            السابق
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            onClick={() => void create()}
            disabled={!canCreate}
            title={countsError ? countsError : undefined}
          >
            {creating ? 'جارٍ الإنشاء…' : 'إنشاء'}
          </button>
        </>
      )}
    >
      {error && (
        <div role="alert" className="ktra-banner ktra-banner--err text-sm">{error}</div>
      )}

      {step === 1 ? (
        <>
          <div className="flex flex-wrap gap-3">
            <label className="ktra-field">
              <span className="ktra-field-label">التاريخ</span>
              <input
                type="date"
                className="ktra-input"
                value={date}
                disabled={creating}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
            <label className="ktra-field">
              <span className="ktra-field-label">المستودع</span>
              <select
                className="ktra-input"
                value={warehouse}
                disabled={creating}
                onChange={(event) => setWarehouse(
                  event.target.value ? Number(event.target.value) : '',
                )}
              >
                <option value="">— كل المخزون —</option>
                {warehouses.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label className="ktra-field min-w-40 flex-1">
              <span className="ktra-field-label">ملاحظات</span>
              <input
                className="ktra-input"
                value={notes}
                disabled={creating}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
          </div>
          <p className="text-xs text-[var(--ktra-ink-soft)]">
            المستودع وسمٌ على حركات الجرد ولا يقيّد البنود؛ البنود تُقرأ بأرصدة الشركة.
          </p>
        </>
      ) : (
        <>
          <h3 className="text-sm font-bold text-[var(--ktra-ink)]">ماذا سنجرد؟</h3>
          <div className="space-y-1.5">
            {MODES.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-start gap-2 rounded border border-[var(--ktra-border-soft)] px-2 py-1.5 text-sm"
              >
                <input
                  type="radio"
                  name="stocktake-scope-mode"
                  className="mt-0.5 accent-[var(--ktra-accent)]"
                  checked={mode === option.value}
                  disabled={creating}
                  onChange={() => setMode(option.value)}
                />
                <span>
                  <span className="font-medium text-[var(--ktra-ink)]">{option.label}</span>
                  <span className="block text-xs text-[var(--ktra-ink-soft)]">{option.hint}</span>
                </span>
              </label>
            ))}
          </div>

          {mode !== 'manual' && countsError && (
            <div className="ktra-banner ktra-banner--err flex items-center gap-2 text-sm">
              <span className="flex-1">{countsError}</span>
              <button
                type="button"
                className="ktra-toolbtn"
                onClick={() => void loadCounts()}
                disabled={countsLoading}
              >
                <RefreshCw className={`h-4 w-4 ${countsLoading ? 'animate-spin' : ''}`} />
                إعادة المحاولة
              </button>
            </div>
          )}

          {mode === 'categories' && (
            <div className="space-y-2">
              {!countsError && (
                <CategoryTreeSelect
                  mode="multi"
                  categories={categories}
                  value={checkedIds}
                  onChange={changeCategories}
                  productCounts={counts?.categories ?? {}}
                  partialIds={partialIds}
                  disabled={creating}
                  onClearAll={clearScopeSelection}
                  renderRowAction={(category) => (
                    // الزوج `aria-expanded`/`aria-label` على الزرّ وحده: النقر
                    // لا يبلغ الصفّ (الغلاف يوقف الانتشار) فلا يتغيّر التأشير.
                    <button
                      type="button"
                      className="rounded px-1 py-0.5 text-xs text-[var(--ktra-accent)] hover:bg-[var(--ktra-active)]"
                      aria-label={`منتجات ${category.name}`}
                      aria-expanded={openProducts.has(scopeProductPanelKey(category.id))}
                      disabled={creating}
                      onClick={() => toggleProductsPanel(category.id)}
                    >
                      منتجات
                    </button>
                  )}
                  renderRowPanel={(category) => (
                    openProducts.has(scopeProductPanelKey(category.id))
                      ? scopeProductsPanel(category.id, category.name)
                      : null
                  )}
                  summary={(
                    <span data-testid="stocktake-scope-summary">{summaryText}</span>
                  )}
                />
              )}

              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-sm text-[var(--ktra-ink)]">
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 accent-[var(--ktra-accent)]"
                      checked={uncategorized}
                      disabled={creating || !counts}
                      onChange={(event) => changeUncategorized(event.target.checked)}
                    />
                    بدون تصنيف
                    {counts && (
                      <span className="text-xs text-[var(--ktra-ink-soft)]">
                        ({formatNumber(counts.uncategorized)})
                      </span>
                    )}
                  </label>
                  {/* الشجرة لا تحتوي «بدون تصنيف»، ولوحةُ منتجاتها هي اللوحة نفسها
                      بـ`category=none` — والخانة تبقى شمولَها بكامله. */}
                  <button
                    type="button"
                    className="rounded px-1 py-0.5 text-xs text-[var(--ktra-accent)] hover:bg-[var(--ktra-hover)]"
                    aria-label="منتجات بدون تصنيف"
                    aria-expanded={openProducts.has('none')}
                    disabled={creating}
                    onClick={() => toggleProductsPanel(null)}
                  >
                    منتجات
                  </button>
                </div>
                {openProducts.has('none') && scopeProductsPanel(null, 'بدون تصنيف')}
              </div>
            </div>
          )}

          {mode !== 'categories' && (
            <div
              data-testid="stocktake-scope-summary"
              className="rounded border border-[var(--ktra-border-soft)] px-2 py-1.5 text-sm text-[var(--ktra-ink)]"
            >
              {summaryText}
            </div>
          )}

          {mode !== 'manual' && (
            <>
              <label className="flex items-center gap-2 text-sm text-[var(--ktra-ink)]">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-[var(--ktra-accent)]"
                  checked={includeInactive}
                  disabled={creating}
                  onChange={(event) => changeIncludeInactive(event.target.checked)}
                />
                شمل المنتجات غير الفعّالة
              </label>
              <p className="text-xs text-[var(--ktra-ink-soft)]">
                الخدمات تُستبعد دائماً. المنتج غير الفعّال قد يكون له رصيدٌ باقٍ يُعدّ.
              </p>
              {mode === 'categories' && pruned > 0 && (
                <div role="status" className="ktra-banner ktra-banner--warn text-sm">
                  {prunedNotice(pruned)}
                </div>
              )}
            </>
          )}

          {emptyChoice && (
            <div role="alert" className="ktra-banner ktra-banner--warn text-sm">
              لا منتجات في هذا الاختيار
            </div>
          )}
        </>
      )}
    </StocktakeDialog>
  );
};

export default NewStocktakeModal;
