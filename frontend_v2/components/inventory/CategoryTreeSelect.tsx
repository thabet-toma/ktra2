/**
 * C1 — منتقي شجرة التصنيفات: وضعٌ واحد `single` (كرت المنتج، نافذة النقل)
 * ووضعٌ متعدّد `multi` (نطاق الجرد، نطاق رابط الموظف).
 *
 * **الخوارزمية في `utils/categoryTree.ts` وحدها** — الصفوف الظاهرة
 * (`visibleTreeRows`)، شجرة `restrictTo` (`restrictCategories`)، الحالة الثلاثية
 * لكل العُقد في مرورٍ واحد (`checkStates`)، التبديل (`toggleSubtree`)، والبحث
 * والمسار: دوالّ خالصة هناك ومختبرة بـ`node --test`. هنا الرسم وحدها: التحميل،
 * الطيّ، لوحة المفاتيح، ونموذج الإنشاء.
 *
 * **دلالة الاختيار في multi (قرار الخطة 3):** كل عقدة مؤشَّرة تعني منتجاتها
 * **المباشرة**؛ تأشير أب يؤشّر أحفاده بصرياً، وإلغاء ابنٍ يُبقي الأب مؤشَّراً
 * «جزئياً» وتبقى منتجاته المباشرة مشمولة.
 *
 * **`restrictTo` (نطاق رابط الجرد):** يُقصر التأشير على المسموح، وكلُّ مسموحٍ
 * يُربط بأقرب أبٍ مسموح — فتبديل الأب وإلغاؤه دورةٌ مغلقة داخل النطاق. والقيمة
 * لا تحمل معرّفاً خارج النطاق: ما جاء فيها من خارجه يُسقَط عند أوّل تبديل،
 * و«تحديد الكل/إلغاء الكل» يستبدلان القيمة.
 *
 * **لوحة المفاتيح:** ↑/↓ وHome/End بين الصفوف الظاهرة؛ السهمان الأفقيان
 * واعيان باتجاه العنصر نفسه (`getComputedStyle`): في RTL اليسار يفتح/يدخل
 * واليمين يطوي/يصعد، وفي LTR معكوسان؛ Space يؤشّر في multi (Enter لا يؤشّر
 * هناك)، وEnter أو Space يختار في single، وEnter/Space على سطر مسارٍ يفتحه أو
 * يطويه. Esc يغلق في single ويعيد التركيز إلى الحقل.
 */
import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, ChevronLeft, Plus, Search, X } from 'lucide-react';
import { inventoryApi } from '../../services/inventoryApi';
import { usePermissions } from '../../contexts/PermissionsContext';
import { formatNumber } from '../../utils/formatNumber';
import {
  ancestorIds,
  categoryKey,
  categoryPathLabel,
  checkStates,
  restrictCategories,
  restrictPathKeys,
  searchCategories,
  toggleSubtree,
  visibleTreeRows,
  type CategoryCheckState,
  type VisibleCategoryRow,
} from '../../utils/categoryTree';

export type CategoryTreeOption = {
  id: number;
  name: string;
  parent: number | null;
};

type CommonProps = {
  /** التصنيفات جاهزة من الشاشة الأم؛ غيابها يعني جلبها هنا بـ`getCategories`. */
  categories?: CategoryTreeOption[];
  className?: string;
};

export type CategoryTreeSelectSingleProps = CommonProps & {
  mode: 'single';
  value: number | null;
  onChange: (id: number | null, pathLabel: string) => void;
  /** يُظهر «إنشاء تصنيف» — مع `inventory.item.manage` فقط. */
  allowCreate?: boolean;
  disabled?: boolean;
  placeholder?: string;
};

export type CategoryTreeSelectMultiProps = CommonProps & {
  mode: 'multi';
  value: number[];
  onChange: (ids: number[]) => void;
  /** عدّاد المنتجات المباشرة لكل عقدة — يُظهر العدد ويُجمع في الملخّص. */
  productCounts?: Record<number, number>;
  /** يُعرض هؤلاء ومسار الوصول إليهم فقط (نطاق رابط الجرد). */
  restrictTo?: number[];
  disabled?: boolean;
};

export type CategoryTreeSelectProps =
  | CategoryTreeSelectSingleProps
  | CategoryTreeSelectMultiProps;

/** المسافة البادئة بدرجاتٍ ثابتة (تسع درجاتٍ ثم تُثبَّت) — Tailwind لا يبني صنفاً من متغيّر. */
const DEPTH_PAD = [
  'ps-0', 'ps-4', 'ps-8', 'ps-12', 'ps-16', 'ps-20', 'ps-24', 'ps-28', 'ps-32',
];

/**
 * قائمة التصنيفات: تُجلب هنا حين لا تُمرَّر، ويُدمج ما أُنشئ من هنا فوراً
 * حتى لو كانت القائمة تصل من الشاشة الأم.
 */
const useCategoryList = (categories?: CategoryTreeOption[]) => {
  const [fetchedCategories, setFetchedCategories] = useState<CategoryTreeOption[]>([]);
  const [createdCategories, setCreatedCategories] = useState<CategoryTreeOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await inventoryApi.getCategories();
      setFetchedCategories(Array.isArray(data) ? (data as CategoryTreeOption[]) : []);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'تعذّر تحميل التصنيفات');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (categories === undefined) void load();
  }, [categories, load]);

  const allCategories = useMemo<CategoryTreeOption[]>(() => {
    const base = categories ?? fetchedCategories;
    if (!createdCategories.length) return base;
    const seen = new Set(base.map((c) => c.id));
    return [...base, ...createdCategories.filter((c) => !seen.has(c.id))];
  }, [categories, fetchedCategories, createdCategories]);

  const addCreated = useCallback((node: CategoryTreeOption) => {
    setCreatedCategories((prev) => [...prev, node]);
  }, []);

  return { allCategories, addCreated, loading, loadError, load };
};

type TreeRowsCommonProps = {
  rows: Array<VisibleCategoryRow<CategoryTreeOption>>;
  expandedKeys: ReadonlySet<string>;
  autoExpandAll: boolean;
  /** المفتاح الذي يأخذ `tabIndex` 0 عند التركيز الأوّل (المحدَّد في single). */
  initialFocusKey?: string | null;
  disabled?: boolean;
  onToggleExpand: (key: string) => void;
  ariaLabel: string;
};

/** الخصائص تتفرّع بحسب الوضع — لا خصائص صوريّة يمرّرها وضعٌ ولا يستعملها. */
type TreeRowsProps = TreeRowsCommonProps & (
  | {
    mode: 'single';
    selectedId: number | null;
    onPick: (category: CategoryTreeOption) => void;
    onEscape: () => void;
  }
  | {
    mode: 'multi';
    states: ReadonlyMap<string, CategoryCheckState>;
    onToggleCheck: (category: CategoryTreeOption) => void;
    /** عدّاد المنتجات المباشرة لكل عقدة — يُرسم ويُجمع في الملخّص. */
    productCounts?: Record<number, number>;
  }
);

/**
 * الشجرة المرسومة — عنصرُ `treeitem` واحد لكل صفّ بتبويبٍ متحرّك (roving
 * tabIndex). إن غاب المفتاح المركَّز من الصفوف الظاهرة (طُوي أبوه أو تغيّر
 * البحث) يأخذ الصفُّ الأول التبويبَ ويبدأ التنقّل منه.
 */
const TreeRows: React.FC<TreeRowsProps> = (props) => {
  const {
    rows, expandedKeys, autoExpandAll, initialFocusKey, disabled, onToggleExpand, ariaLabel,
  } = props;
  const [focusKey, setFocusKey] = useState<string | null>(initialFocusKey ?? null);
  const rowRefs = useRef<Map<string, HTMLLIElement>>(new Map());
  const treeRef = useRef<HTMLUListElement>(null);

  const focusedIndex = rows.findIndex((row) => categoryKey(row.id) === focusKey);
  const activeKey = focusedIndex >= 0
    ? focusKey
    : (rows.length ? categoryKey(rows[0].id) : null);

  const focusRow = (key: string) => {
    setFocusKey(key);
    rowRefs.current.get(key)?.focus();
  };

  // عند الفتح على قيمةٍ محدَّدة: صفُّها يُرى بلا تمرير يدوي (التركيز يبقى في البحث).
  useEffect(() => {
    if (focusKey) rowRefs.current.get(focusKey)?.scrollIntoView({ block: 'nearest' });
    // مرّةً عند التركيب: تغيير `focusKey` بعدها يتبع تركيز الصفّ نفسه.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isExpandedKey = (key: string) => autoExpandAll || expandedKeys.has(key);

  const onKeyDown = (e: React.KeyboardEvent<HTMLUListElement>) => {
    if (disabled || !rows.length) return;
    const index = rows.findIndex((row) => categoryKey(row.id) === activeKey);
    const current = index >= 0 ? rows[index] : null;
    const currentKey = current ? categoryKey(current.id) : '';

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusRow(categoryKey(rows[Math.min(index + 1, rows.length - 1)].id));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      focusRow(categoryKey(rows[Math.max(index - 1, 0)].id));
    } else if (e.key === 'Home') {
      e.preventDefault();
      focusRow(categoryKey(rows[0].id));
    } else if (e.key === 'End') {
      e.preventDefault();
      focusRow(categoryKey(rows[rows.length - 1].id));
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      if (!current) return;
      // الاتجاه من العنصر نفسه: في RTL اليسار يتقدّم واليمين يرتدّ، وفي LTR معكوسان.
      const direction = treeRef.current
        ? getComputedStyle(treeRef.current).direction
        : 'rtl';
      const forward = direction === 'ltr' ? 'ArrowRight' : 'ArrowLeft';
      if (e.key === forward) {
        // يتقدّم: يفتح الفرع المغلق، أو يدخل أول ابن ظاهر.
        if (current.hasChildren && !isExpandedKey(currentKey)) {
          onToggleExpand(currentKey);
          return;
        }
        if (current.hasChildren) {
          const child = rows[index + 1];
          if (child && child.depth > current.depth) focusRow(categoryKey(child.id));
        }
        return;
      }
      // يرتدّ: يطوي الفرع المفتوح بالطيّ اليدوي، وأما فتحُ البحث فيصعد للأب مباشرةً.
      if (!autoExpandAll && current.hasChildren && isExpandedKey(currentKey)) {
        onToggleExpand(currentKey);
        return;
      }
      for (let i = index - 1; i >= 0; i -= 1) {
        if (rows[i].depth < current.depth) { focusRow(categoryKey(rows[i].id)); break; }
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (!current) return;
      if (!current.selectable) { onToggleExpand(currentKey); return; }
      if (props.mode === 'single') { props.onPick(current.category); return; }
      // multi: Enter لا يؤشّر — ضغطةٌ عابرة لا تُغيّر النطاق؛ Space وحده يؤشّر.
      if (e.key === ' ') props.onToggleCheck(current.category);
    } else if (e.key === 'Escape' && props.mode === 'single') {
      props.onEscape();
    }
  };

  return (
    <ul
      ref={treeRef}
      role="tree"
      aria-label={ariaLabel}
      aria-multiselectable={props.mode === 'multi' ? true : undefined}
      className="m-0 list-none p-0"
      onKeyDown={onKeyDown}
    >
      {rows.map((row) => {
        const key = categoryKey(row.id);
        const selected = props.mode === 'single' && props.selectedId === row.id;
        const state: CategoryCheckState | null =
          props.mode === 'multi' && row.selectable
            ? props.states.get(key) ?? 'off'
            : null;
        const expanded = row.hasChildren && isExpandedKey(key);
        const count = props.mode === 'multi' ? props.productCounts?.[row.id] : undefined;
        const tabIndex = activeKey === key ? 0 : -1;

        return (
          <li
            key={key}
            ref={(el) => {
              if (el) rowRefs.current.set(key, el);
              else rowRefs.current.delete(key);
            }}
            role="treeitem"
            aria-level={row.depth + 1}
            aria-expanded={row.hasChildren ? expanded : undefined}
            aria-selected={props.mode === 'single' ? selected : undefined}
            aria-checked={state == null
              ? undefined
              : (state === 'partial' ? 'mixed' : state === 'on')}
            aria-disabled={row.selectable ? undefined : true}
            tabIndex={tabIndex}
            onFocus={() => setFocusKey(key)}
            onClick={() => {
              if (disabled) return;
              if (!row.selectable) { onToggleExpand(key); return; }
              if (props.mode === 'multi') props.onToggleCheck(row.category);
              else props.onPick(row.category);
            }}
            className={[
              'flex items-center gap-1.5 rounded px-1.5 py-1 text-sm outline-none',
              'focus-visible:ring-2 focus-visible:ring-[var(--ktra-accent)]',
              DEPTH_PAD[Math.min(row.depth, DEPTH_PAD.length - 1)],
              selected ? 'bg-[var(--ktra-active)] font-medium' : 'hover:bg-[var(--ktra-hover)]',
              row.selectable ? 'text-[var(--ktra-ink)]' : 'text-[var(--ktra-ink-soft)]',
            ].join(' ')}
          >
            {row.hasChildren ? (
              <button
                type="button"
                tabIndex={-1}
                aria-label={expanded ? 'طيّ' : 'فتح'}
                className="shrink-0 rounded p-0.5 text-[var(--ktra-ink-soft)] hover:bg-[var(--ktra-active)]"
                onClick={(e) => { e.stopPropagation(); onToggleExpand(key); }}
              >
                {expanded
                  ? <ChevronDown className="h-3.5 w-3.5" />
                  : <ChevronLeft className="h-3.5 w-3.5" />}
              </button>
            ) : (
              <span className="w-[18px] shrink-0" />
            )}

            {props.mode === 'multi' && row.selectable && (
              <label
                className="flex shrink-0 items-center"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  tabIndex={-1}
                  className="h-3.5 w-3.5 accent-[var(--ktra-accent)]"
                  checked={state === 'on'}
                  ref={(el) => { if (el) el.indeterminate = state === 'partial'; }}
                  onChange={() => { if (!disabled) props.onToggleCheck(row.category); }}
                  aria-label={`تحديد ${row.category.name}`}
                />
              </label>
            )}

            <span className="truncate">{row.category.name}</span>

            {props.mode === 'single' && selected && (
              <Check className="ms-auto h-3.5 w-3.5 shrink-0 text-[var(--ktra-accent)]" />
            )}
            {props.mode === 'multi' && props.productCounts && (
              <span className="ms-auto shrink-0 text-xs text-[var(--ktra-ink-soft)]">
                {formatNumber(count ?? 0)}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
};

const CREATE_POSITIONS = [
  { value: 'under', label: 'تحت المحدَّد' },
  { value: 'sibling', label: 'بجانب المحدَّد' },
  { value: 'root', label: 'تصنيف رئيسي' },
] as const;

type CreatePosition = (typeof CREATE_POSITIONS)[number]['value'];

const SingleCategoryTreeSelect: React.FC<CategoryTreeSelectSingleProps> = (props) => {
  const { categories, className, disabled, value, onChange } = props;
  const { allCategories, addCreated, loading, loadError, load } = useCategoryList(categories);
  const { can } = usePermissions();
  const canManageCatalog = can('inventory.item.manage');
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<
    { top: number; left: number; width: number; maxHeight: number | null } | null
  >(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [createPosition, setCreatePosition] = useState<CreatePosition>('root');
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const comboRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  // اسمٌ فريد لمجموعة أزرار الموضع: منتقيان مركّبان معاً لا يتنازعان الاختيار.
  const createGroupName = useId();
  // ومعرّفٌ فريد للوحة: يربطه `aria-controls` بالحقل وهي مفتوحة وحدها.
  const panelId = useId();

  const selectedId = value;
  const selectedLabel = categoryPathLabel(allCategories, selectedId);
  const rows = useMemo(
    () => visibleTreeRows(allCategories, { expanded }),
    [allCategories, expanded],
  );
  const searchResults = useMemo(
    () => (query.trim() ? searchCategories(allCategories, query) : []),
    [allCategories, query],
  );

  /**
   * موضع اللوحة من مستطيل الحقل — النمط نفسه في `components/kit/KitAutocomplete.tsx`
   * (بوّابةٌ على `body` و`position:fixed`): المنسدلة تُقصّ داخل نافذةٍ فيها
   * `overflow-hidden` (مثل `ItemQuickCreateModal`)، وهذا يخرجها من القصّ.
   *
   * **والقلب للأعلى شرطُ وصولٍ لا تجميل**: البوّابة خارج كل تمرير، فحقلٌ قريبٌ
   * من أسفل الشاشة يفتح لوحةً أسفل حدّها — والنتيجة الثانية فيها لا يمكن
   * النقر عليها أصلاً (قِيس في كرت المنتج على ارتفاع 720px: خيارُ البحث الثاني
   * صار «outside of the viewport»). تُقاس اللوحة بعد رسمها وتُقلَب متى ضاق
   * ما تحتها وكان فوقها أوسع.
   *
   * **والقياسُ الأوّل يقع لحظةَ تركيب اللوحة** (`attachPanel`)، لا في نداء
   * الفتح: قبل التركيب لا عقدةَ فتُقرأ صفراً — وحين يُحكَم بلا قياسٍ تُسقَط
   * اللوحة في أعلى الشاشة منفصلةً عن الحقل. فما دام الارتفاع صفراً تُوضع تحت
   * الحقل بلا سقفٍ مؤقّتاً، ثم تُقاس عند التركيب فتُقلَب أو تُسقَّف.
   */
  const reposition = useCallback(() => {
    const r = comboRef.current?.getBoundingClientRect();
    if (!r) return;
    const width = Math.max(r.width, 280);
    // RTL: نحاذي حافة الحقل اليمنى ونمنع الخروج عن يسار الشاشة.
    const left = Math.max(4, Math.min(r.right - width, window.innerWidth - width - 4));
    // الارتفاع **الطبيعي** لا المرسوم: اللوحة المقصوصة يبقى `scrollHeight` فيها
    // أكبر من `offsetHeight`، وقياسُ المقصوص يجعل القرار يقيس نفسه فيتذبذب بين
    // «اقصص» و«لا تقصص» بلا نهاية.
    const panel = panelRef.current;
    const height = Math.max(panel?.offsetHeight ?? 0, panel?.scrollHeight ?? 0);
    const below = window.innerHeight - r.bottom - 4;
    const above = r.top - 4;
    // لم تُقس بعد: تحت الحقل بلا سقفٍ مؤقّتاً — القرار بعد التركيب (`attachPanel`).
    if (height === 0) {
      setPos({ top: r.bottom + 2, left, width, maxHeight: null });
      return;
    }
    // يكفي ما تحته ⇒ تحته، وإلّا وفوقه يكفي ⇒ فوقه (القلب).
    if (height <= below) {
      setPos({ top: r.bottom + 2, left, width, maxHeight: null });
      return;
    }
    if (height <= above) {
      setPos({ top: Math.max(4, r.top - height - 2), left, width, maxHeight: null });
      return;
    }
    // لا يكفي أيُّ الجانبين: الجانب الأوسع، بارتفاعٍ محدودٍ بما فيه — فتُمرَّر
    // اللوحة داخلياً ولا تغطّي الحقل أبداً.
    const maxHeight = Math.max(below, above);
    const top = below >= above
      ? r.bottom + 2
      : Math.max(4, r.top - maxHeight - 2);
    setPos({ top, left, width, maxHeight });
  }, []);

  /**
   * مرجعُ اللوحة: يُخزّن العقدة **ويقيس لحظةَ تركيبها** — وهو القياسُ الأوّل.
   * مرجعُه مستقرّ (`reposition` لا يتغيّر) فلا يُعاد تركيب اللوحة، و`reposition`
   * لا يُبدّل هويّة العقدة، فلا دورةَ قياسٍ↔تركيب.
   */
  const attachPanel = useCallback((node: HTMLDivElement | null) => {
    panelRef.current = node;
    if (node) reposition();
  }, [reposition]);

  // القياس يتبع ما يُطيل اللوحة أو يقصّرها من حالاتها (نتائجُ البحث، انتهاءُ
  // التحميل، خطأُ تحميلٍ ظهر أو زال)؛ والقياسُ الأوّل عند التركيب نفسه.
  useLayoutEffect(() => {
    if (!open) return;
    reposition();
  }, [open, reposition, query, createOpen, createError, loading, loadError, searchResults.length, rows.length]);

  /**
   * الإغلاق الوحيد: يُطفئ اللوحة ويمحو الاستعلام ونموذج الإنشاء (فإعادةُ
   * الفتح لا تُظهر مسودّةً قديمة). `refocus` لما ينتهي فيه التفاعل داخل
   * المنتقي (Esc، اختيارٌ، إنشاءٌ ناجح) — ولا يُعاد التركيز عند نقرةٍ خارجية أو
   * تمرير أو تحجيم: فيه سرقةُ تركيزِ ما نقر المستخدم، وسحبُ الصفحة إلى الحقل
   * حين يمرّرها.
   */
  const closePanel = useCallback(({ refocus }: { refocus: boolean }) => {
    setOpen(false);
    setQuery('');
    setPos(null);
    setCreateOpen(false);
    setNewName('');
    setCreateError(null);
    if (refocus) comboRef.current?.focus();
  }, []);

  const openPanel = useCallback(() => {
    setOpen(true);
    if (selectedId != null) {
      // يفتح مسار المحدَّد كي يُرى صفّه فوراً عند الفتح.
      setExpanded((prev) => {
        const next = new Set(prev);
        for (const id of ancestorIds(allCategories, selectedId)) {
          next.add(categoryKey(id));
        }
        return next;
      });
    }
    reposition();
  }, [allCategories, reposition, selectedId]);

  /** الاختيار الوحيد: القيمة ثم الإغلاق — تستعمله الشجرة ونتائج البحث معاً. */
  const choose = useCallback((id: number, pathLabel: string) => {
    onChange(id, pathLabel);
    closePanel({ refocus: true });
  }, [closePanel, onChange]);

  const pick = useCallback((category: CategoryTreeOption) => {
    choose(category.id, categoryPathLabel(allCategories, category.id));
  }, [allCategories, choose]);

  const toggleExpanded = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // موضعٌ معطَّل (بلا محدَّد) لا يُبقى مختاراً: «تحت المحدَّد» بلا محدَّد يصير «رئيسي».
  useEffect(() => {
    if (selectedId == null && createPosition !== 'root') setCreatePosition('root');
  }, [createPosition, selectedId]);

  // إغلاق بنقرةٍ خارج الحقل واللوحة (والبوّابة ليست داخل الغلاف)، وعند
  // تمرير الصفحة أو تحجيم النافذة تُبطل الإحداثيات المحسوبة — كما في KitAutocomplete.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (wrapRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      closePanel({ refocus: false });
    };
    const onScroll = (e: Event) => {
      if (panelRef.current?.contains(e.target as Node)) return;
      closePanel({ refocus: false });
    };
    // التحجيم يُبطل الإحداثيات المحسوبة مثل التمرير — وإعادةُ التركيز هنا
    // تسحب الصفحة إلى الحقل، فلا.
    const onResize = () => closePanel({ refocus: false });
    document.addEventListener('mousedown', onDown);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
    };
  }, [open, closePanel]);

  const openCreate = () => {
    setCreateOpen(true);
    setCreateError(null);
    setCreatePosition(selectedId == null ? 'root' : 'under');
  };

  const cancelCreate = () => {
    setCreateOpen(false);
    setNewName('');
    setCreateError(null);
  };

  const submitCreate = async () => {
    if (createBusy) return;
    const name = newName.trim();
    if (!name) { setCreateError('اسم التصنيف مطلوب.'); return; }
    // لا يُرسَل موضعٌ معطَّل أبداً: بلا محدَّد يصير الإنشاء رئيسياً.
    const position: CreatePosition = selectedId == null ? 'root' : createPosition;
    let parent: number | null = null;
    if (position === 'under') parent = selectedId;
    else if (position === 'sibling') {
      parent = allCategories.find((c) => c.id === selectedId)?.parent ?? null;
    }
    setCreateBusy(true);
    setCreateError(null);
    try {
      const node = (await inventoryApi.createCategory({ name, parent })) as CategoryTreeOption;
      addCreated(node);
      if (parent != null) {
        setExpanded((prev) => new Set(prev).add(categoryKey(parent)));
      }
      // تحديثٌ من الخادم حين جلبنا القائمة بنفسنا — والدمج أعلاه يحفظ الاختيار فوراً.
      if (categories === undefined) void load();
      onChange(node.id, categoryPathLabel([...allCategories, node], node.id));
      setNewName('');
      setCreateOpen(false);
      closePanel({ refocus: true });
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'تعذّر إنشاء التصنيف');
    } finally {
      setCreateBusy(false);
    }
  };

  /** الأسهم في حقل البحث تنقل التركيز إلى الشجرة حين لا استعلام. */
  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { e.preventDefault(); closePanel({ refocus: true }); return; }
    if (!query.trim()) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const items = panelRef.current?.querySelectorAll<HTMLElement>('[role="treeitem"]');
        if (!items?.length) return;
        e.preventDefault();
        (e.key === 'ArrowDown' ? items[0] : items[items.length - 1]).focus();
      }
      return;
    }
    if (!searchResults.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, searchResults.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const hit = searchResults[Math.min(activeIndex, searchResults.length - 1)];
      if (hit) choose(hit.id, hit.pathLabel);
    }
  };

  return (
    <div ref={wrapRef} className={`relative ${className ?? ''}`}>
      <div
        ref={comboRef}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="tree"
        aria-controls={open ? panelId : undefined}
        aria-label="التصنيف"
        tabIndex={disabled ? -1 : 0}
        onClick={() => {
          if (disabled) return;
          if (open) closePanel({ refocus: false });
          else openPanel();
        }}
        onKeyDown={(e) => {
          if (disabled) return;
          if (e.key === 'ArrowDown' || e.key === 'Enter') {
            e.preventDefault();
            if (!open) openPanel();
          } else if (e.key === 'Escape') {
            e.preventDefault();
            if (open) closePanel({ refocus: true });
          }
        }}
        className={`ktra-input flex cursor-pointer items-center justify-between gap-2 ${
          disabled ? 'cursor-not-allowed opacity-60' : ''
        }`}
      >
        <span className={`truncate ${
          selectedId == null ? 'text-[var(--ktra-ink-soft)]' : 'text-[var(--ktra-ink)]'
        }`}>
          {selectedId == null
            ? (props.placeholder ?? 'بدون تصنيف')
            : (selectedLabel || (loading ? 'جارٍ التحميل…' : '—'))}
        </span>
        <span className="flex shrink-0 items-center gap-1">
          {selectedId != null && !disabled && (
            <button
              type="button"
              aria-label="مسح التصنيف"
              className="rounded p-0.5 hover:bg-[var(--ktra-hover)]"
              onClick={(e) => {
                e.stopPropagation();
                onChange(null, '');
              }}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </span>
      </div>

      {open && pos && createPortal(
        <div
          ref={attachPanel}
          id={panelId}
          dir="rtl"
          // فوق النوافذ: المستوى نفسه الذي يحمله `.ktra-autocomplete-pop`
          // (`z-index: 10000`). بـ`z-50` كانت اللوحة تفتح **خلف** نافذة
          // `ItemQuickCreateModal` (`z-[70]`) — وهي الحالة التي بُنيت لها البوّابة.
          className="z-[10000] flex flex-col overflow-hidden rounded-md border border-[var(--ktra-border)] bg-[var(--ktra-surface)] shadow-lg"
          // الإحداثيات المحسوبة وحدها — ومعها سقفُ الارتفاع حين لا يكفي أيُّ
          // الجانبين؛ الاستثناء الوحيد لـ«Tailwind فقط»، والنمط نفسه في
          // `KitAutocomplete` (ومنها `position:fixed`).
          style={{
            position: 'fixed', top: pos.top, left: pos.left, width: pos.width,
            maxHeight: pos.maxHeight ?? undefined,
          }}
        >
          <div className="relative border-b border-[var(--ktra-border)] p-1.5">
            <Search className="pointer-events-none absolute end-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--ktra-ink-soft)]" />
            <input
              autoFocus
              className="ktra-input w-full pe-7"
              placeholder="ابحث بالاسم أو داخل المسار…"
              aria-label="بحث التصنيفات"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setActiveIndex(0); }}
              onKeyDown={onSearchKeyDown}
            />
          </div>

          <div className="min-h-0 max-h-64 flex-1 overflow-y-auto p-1">
            {loading && allCategories.length === 0 ? (
              <div className="p-3 text-center text-xs text-[var(--ktra-ink-soft)]">
                جارٍ تحميل التصنيفات…
              </div>
            ) : loadError ? (
              <div className="p-3 text-center text-xs text-[var(--ktra-danger)]">
                {loadError}
                <button
                  type="button"
                  className="ms-2 underline"
                  onClick={() => void load()}
                >
                  إعادة المحاولة
                </button>
              </div>
            ) : query.trim() ? (
              searchResults.length ? (
                <ul role="listbox" aria-label="نتائج البحث" className="m-0 list-none p-0">
                  {searchResults.map((hit, i) => (
                    <li
                      key={hit.id}
                      role="option"
                      aria-selected={i === activeIndex}
                      onMouseEnter={() => setActiveIndex(i)}
                      onClick={() => choose(hit.id, hit.pathLabel)}
                      className={`flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-sm ${
                        i === activeIndex
                          ? 'bg-[var(--ktra-active)] text-[var(--ktra-ink)]'
                          : 'text-[var(--ktra-ink)]'
                      }`}
                    >
                      <span className="truncate">{hit.pathLabel}</span>
                      {selectedId === hit.id && (
                        <Check className="ms-auto h-3.5 w-3.5 shrink-0 text-[var(--ktra-accent)]" />
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="p-3 text-center text-xs text-[var(--ktra-ink-soft)]">لا تطابق</div>
              )
            ) : (
              <TreeRows
                rows={rows}
                expandedKeys={expanded}
                autoExpandAll={false}
                initialFocusKey={selectedId == null ? null : categoryKey(selectedId)}
                mode="single"
                selectedId={selectedId}
                disabled={disabled}
                onToggleExpand={toggleExpanded}
                onPick={pick}
                onEscape={() => closePanel({ refocus: true })}
                ariaLabel="شجرة التصنيفات"
              />
            )}
          </div>

          {props.allowCreate && canManageCatalog && (
            <div className="border-t border-[var(--ktra-border)] p-1.5">
              {!createOpen ? (
                <button
                  type="button"
                  className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-xs text-[var(--ktra-accent)] hover:bg-[var(--ktra-hover)]"
                  onClick={openCreate}
                >
                  <Plus className="h-3.5 w-3.5" />
                  إنشاء تصنيف
                </button>
              ) : (
                <div className="space-y-1.5">
                  <input
                    autoFocus
                    className="ktra-input w-full"
                    placeholder="اسم التصنيف الجديد"
                    aria-label="اسم التصنيف الجديد"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { e.preventDefault(); void submitCreate(); }
                      else if (e.key === 'Escape') { e.preventDefault(); cancelCreate(); }
                    }}
                  />
                  <div className="flex flex-wrap gap-2 text-xs text-[var(--ktra-ink)]">
                    {CREATE_POSITIONS.map((option) => (
                      <label key={option.value} className="flex items-center gap-1">
                        <input
                          type="radio"
                          name={createGroupName}
                          className="accent-[var(--ktra-accent)]"
                          checked={createPosition === option.value}
                          disabled={option.value !== 'root' && selectedId == null}
                          onChange={() => setCreatePosition(option.value)}
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="ktra-toolbtn"
                      disabled={createBusy}
                      onClick={() => void submitCreate()}
                    >
                      إضافة
                    </button>
                    <button type="button" className="ktra-toolbtn" onClick={cancelCreate}>
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  {createError && (
                    <div className="text-xs text-[var(--ktra-danger)]">{createError}</div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
};

const MultiCategoryTreeSelect: React.FC<CategoryTreeSelectMultiProps> = (props) => {
  const { categories, className, disabled, value, onChange, productCounts, restrictTo } = props;
  const { allCategories, loading, loadError, load } = useCategoryList(categories);
  const [query, setQuery] = useState('');
  // نطاقٌ مقصور يبدأ مساراتِه مفتوحة **في أوّل رسم** — البذر الكسول هنا يمنع
  // وميضَ إطارٍ مطويّ قبل أن يلحق الأثر. والأثر يبقى لما بعده: التصنيفات قد
  // تصل بعد التركيب، ولهذا يحمل توقيعه `@${allCategories.length}`.
  const [expanded, setExpanded] = useState<Set<string>>(
    () => (restrictTo?.length ? restrictPathKeys(allCategories, restrictTo) : new Set<string>()),
  );
  const panelRef = useRef<HTMLDivElement>(null);

  // ما يلي الأوّل: نطاقٌ تغيّر محتواه أو تصنيفاتٌ وصلت متأخّرة تُعيد البذر،
  // والطيّ بعده للمستخدم. التوقيع نصٌّ من المعرّفات **مرتّبة**: هويّةُ
  // `restrictTo` تتغيّر كلّ رسمٍ فلا تُقارَن، والمقارنة بالمحتوى تمنع إعادة
  // الفتح بعد أن يطوي.
  const restrictSig = restrictTo?.length
    ? [...new Set(restrictTo.map(categoryKey))].sort().join(',')
    : '';
  const seededSigRef = useRef('');
  useEffect(() => {
    if (!restrictSig) return;
    // طول القائمة يميّز «وصلت التصنيفات» من «لم تصل بعد» فتُزَرَع المسارات عندها.
    const sig = `${restrictSig}@${allCategories.length}`;
    if (seededSigRef.current === sig) return;
    seededSigRef.current = sig;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const key of restrictPathKeys(allCategories, restrictTo ?? [])) next.add(key);
      return next;
    });
  }, [allCategories, restrictSig, restrictTo]);

  const checkedSet = useMemo(() => new Set<number>(value), [value]);
  /** شجرة الاختيار: في `restrictTo` تُقصّ ويُعاد ربط أبٍ كل عقدةٍ بأقرب أبٍ مسموح. */
  const selectionCategories = useMemo(
    () => (restrictTo ? restrictCategories(allCategories, restrictTo) : allCategories),
    [allCategories, restrictTo],
  );
  const rows = useMemo(
    () => visibleTreeRows(allCategories, { expanded, restrictTo, query }),
    [allCategories, expanded, query, restrictTo],
  );
  /** الحالة الثلاثية لكل العُقد مرّةً واحدة لكل رسم — لا `checkState` لكل صفّ. */
  const states = useMemo(
    () => checkStates(selectionCategories, checkedSet),
    [checkedSet, selectionCategories],
  );
  /** ما في القائمة وحدها: معرّفٌ حُذف منها لا يُحسب في الملخّص. */
  const checkedInList = useMemo(
    () => allCategories.filter((c) => checkedSet.has(c.id)),
    [allCategories, checkedSet],
  );
  const productTotal = useMemo(() => {
    if (!productCounts) return null;
    let total = 0;
    for (const category of checkedInList) total += productCounts[category.id] ?? 0;
    return total;
  }, [checkedInList, productCounts]);

  const toggleExpanded = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleCheck = (category: CategoryTreeOption) => {
    if (disabled) return;
    // القيمة لا تحمل معرّفاً خارج النطاق: ما جاء فيها من خارجه (نطاقٌ ضاق بعد
    // الحفظ) يُسقَط هنا عند أوّل تبديل — و«تحديد الكل/إلغاء الكل» يستبدلانها.
    const inScope = new Set(selectionCategories.map((c) => c.id));
    const scoped = new Set([...checkedSet].filter((id) => inScope.has(id)));
    onChange([...toggleSubtree(selectionCategories, scoped, category.id)]);
  };

  const selectAll = () => {
    if (disabled) return;
    onChange(selectionCategories.map((c) => c.id));
  };

  const clearAll = () => {
    if (disabled) return;
    onChange([]);
  };

  return (
    <div
      className={`rounded-md border border-[var(--ktra-border)] bg-[var(--ktra-surface)] ${
        className ?? ''
      }`}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--ktra-border)] px-2 py-1.5">
        <div className="relative min-w-40 flex-1">
          <Search className="pointer-events-none absolute end-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--ktra-ink-soft)]" />
          <input
            className="ktra-input w-full pe-7"
            placeholder="ابحث بالاسم أو داخل المسار…"
            aria-label="بحث التصنيفات"
            value={query}
            disabled={disabled}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') { e.preventDefault(); setQuery(''); }
              else if (e.key === 'ArrowDown') {
                const first = panelRef.current?.querySelector<HTMLElement>('[role="treeitem"]');
                if (first) { e.preventDefault(); first.focus(); }
              }
            }}
          />
        </div>
        <button type="button" className="ktra-toolbtn" disabled={disabled} onClick={selectAll}>
          تحديد الكل
        </button>
        <button type="button" className="ktra-toolbtn" disabled={disabled} onClick={clearAll}>
          إلغاء الكل
        </button>
      </div>

      <div ref={panelRef} className="max-h-72 overflow-y-auto p-1">
        {loading && allCategories.length === 0 ? (
          <div className="p-3 text-center text-xs text-[var(--ktra-ink-soft)]">
            جارٍ تحميل التصنيفات…
          </div>
        ) : loadError ? (
          <div className="p-3 text-center text-xs text-[var(--ktra-danger)]">
            {loadError}
            <button type="button" className="ms-2 underline" onClick={() => void load()}>
              إعادة المحاولة
            </button>
          </div>
        ) : rows.length === 0 ? (
          <div className="p-3 text-center text-xs text-[var(--ktra-ink-soft)]">
            {query.trim() ? 'لا تطابق' : 'لا تصنيفات'}
          </div>
        ) : (
          <TreeRows
            rows={rows}
            expandedKeys={expanded}
            autoExpandAll={Boolean(query.trim())}
            mode="multi"
            states={states}
            productCounts={productCounts}
            disabled={disabled}
            onToggleExpand={toggleExpanded}
            onToggleCheck={toggleCheck}
            ariaLabel="شجرة تصنيفات الجرد"
          />
        )}
      </div>

      <div className="border-t border-[var(--ktra-border)] px-2 py-1.5 text-xs text-[var(--ktra-ink-soft)]">
        التصنيفات المحدّدة: {formatNumber(checkedInList.length)}
        {productTotal != null && <> · المنتجات: {formatNumber(productTotal)}</>}
      </div>
    </div>
  );
};

/** المصدَّر الوحيد: يوزّع على الوضعين — لكلٍّ خطّافه وحالاته المستقلّة. */
export const CategoryTreeSelect: React.FC<CategoryTreeSelectProps> = (props) => (
  props.mode === 'single'
    ? <SingleCategoryTreeSelect {...props} />
    : <MultiCategoryTreeSelect {...props} />
);
