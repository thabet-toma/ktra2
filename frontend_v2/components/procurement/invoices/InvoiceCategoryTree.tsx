import React, { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import {
  ChevronDown,
  ChevronLeft,
  FolderTree,
  Layers,
  Package,
  Plus,
  Search,
  Loader2,
  Check,
  X,
  FolderPlus,
  PackagePlus,
  Pencil,
  Trash2,
  Copy,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import { inventoryApi } from "../../../services/inventoryApi";
import { Item } from "../../../types";
import { ItemQuickCreateModal } from "../../items/ItemQuickCreateModal";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { productToItem } from "../price-offers/ItemSearchModal";
import { buildCategoryIndex, descendantIds as descendantCategoryIds } from "../../../utils/categoryTree";
import { usePermissions } from "../../../contexts/PermissionsContext";

/**
 * task18 DEF-B1/B3: شجرة منتجات مرساة بجانب الفاتورة (نمط الأصيل).
 *
 * **المصطلحات (T-PRODUCT)**: «تصنيف» = العقدة الفرعية (branch) · «منتج» =
 * العقدة الورقية (leaf). كانت هذه الشاشة وحدها تعكسهما — تسمّي التصنيفَ «صنفاً»
 * بينما بقية الموديول تسمّي المنتجَ بذلك. صارت على المصطلح الواحد: كلُّ ما
 * يُنشئ عقدةً هنا «تصنيف»، وكلُّ ما يُنشئ سجلّاً قابلاً للبيع «منتج».
 * - زر الماوس الأيمن: على تصنيف → «إضافة تصنيف فرعي» · «إضافة منتج هنا» · تعديل/حذف؛
 *   على منتج → «فتح الكرت» · «إضافة منتج في نفس التصنيف» · «نسخ الرمز»؛ على الفراغ →
 *   «إضافة تصنيف رئيسي» · «إضافة منتج هنا» (بلا تصنيف).
 * - النقر المفرد على منتج يفتح بطاقته، ومنها يُدرَج في الفاتورة بزرّ «موافق»
 *   (الإدراج بالنقر المزدوج أُلغي — كان التعليق يصفه بعد زواله).
 * + بحث فوري.
 */
type Cat = { id: string; name: string; parent: number | null };

interface Props {
  items: Item[];
  /** إدراج المنتج في الفاتورة (من زرّ «موافق» في بطاقته). */
  onPickItem: (item: Item) => void;
  /** فتح بطاقة المنتج (نقر مفرد). */
  onShowCard?: (item: Item) => void;
  /** تجميع البراندات: فتح الكرت المجمّع لعقدة المقاس (مجموع كل البراندات).
   *  `categoryId` يُمرَّر كي يشتقّ الخادمُ الأعضاء بنفسه — تعدادُ معرّفات تصنيفٍ
   *  كبير في الطلب كان يبلغ آلاف البايتات فيردّه nginx (414). */
  onShowGroup?: (memberIds: string[], name: string, categoryId?: string) => void;
  onItemCreated?: (item: Item) => void;
  disabled?: boolean;
  manageMode?: boolean; // If true, hides product-specific UI and acts purely as a category manager.
}

// تجميع البراندات أصبح حقيقياً (Category).
const displayNameOf = (it: Item) => String((it as unknown as { display_name?: string }).display_name || it.name || "");

// الرمز لا يحمله نوع `Item` (يُضاف إليه من `Product` عند بناء أوراق الشجرة)،
// فنقرأه بنفس أسلوب `display_name` أعلاه بدل توسيع النوع لسطرٍ واحد.
const skuOf = (it: Item) => String((it as unknown as { sku?: string }).sku || "");

const UNCAT = "__uncat__";

/** هدف قائمة زر الماوس الأيمن — كان `catId` وحده، فكبسةُ اليمين على منتج
 *  تُظهر قائمة الفراغ وتُنشئ منتجاً بلا تصنيف (خطأ D6). */
type MenuTarget =
  | { kind: "empty" }
  | { kind: "category"; id: string }
  | { kind: "item"; item: Item };

const ctxItemStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 6, width: "100%",
  padding: "6px 9px", border: 0, background: "transparent", cursor: "pointer",
  fontSize: 13, color: "#333426", textAlign: "start", borderRadius: 5,
};

export const InvoiceCategoryTree: React.FC<Props> = ({ items, onPickItem, onShowCard, onShowGroup, onItemCreated, disabled, manageMode }) => {
  // نقرة مفردة على المنتج → تفتح بطاقة المنتج (وفيها «موافق» للإضافة). لا إدراج
  // بالنقر المزدوج. (الإدراج المباشر يبقى فقط عند إنشاء منتج جديد من الشجرة.)
  const handleLeafClick = (it: Item) => {
    if (disabled) return;
    onShowCard?.(it);
  };
  const [cats, setCats] = useState<Cat[]>([]);
  const toast = useToast();
  const confirmDialog = useConfirm();
  // كتابةُ الشجرة (إنشاء/تعديل/حذف تصنيف) تشترط `inventory.item.manage` على
  // الخادم — تُخفى هنا كي لا يفتح المستخدم نموذجاً يردّه 403. إنشاء المنتج
  // وتعديله لا يُمسّان.
  const { can } = usePermissions();
  const canManageCatalog = can("inventory.item.manage");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loadingCats, setLoadingCats] = useState(false);
  const [newRootName, setNewRootName] = useState("");
  /* T-PRODUCT: كان تركيز هذا الحقل يمرّ بـ`querySelector` مبنيٍّ على **نصّه
     العربي الحرفي** — فأيّ إعادة صياغةٍ للنصّ تُميت «إضافة تصنيف رئيسي» بصمت
     (`?.focus()` على `null` لا يرمي). مرجعٌ مباشر يقتل الاقتران نهائياً. */
  const rootNameInputRef = useRef<HTMLInputElement | null>(null);
  const [subParent, setSubParent] = useState<string | null>(null);
  const [subName, setSubName] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [addItemCat, setAddItemCat] = useState<string | number | null>(null);
  const [showAddItem, setShowAddItem] = useState(false);
  // قائمة زر الماوس الأيمن
  const [menu, setMenu] = useState<{ x: number; y: number; target: MenuTarget } | null>(null);
  // طيّ اللوحة كاملة لتوفير المساحة الأفقية
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  const loadCats = useCallback(async () => {
    setLoadingCats(true);
    try {
      const data = await inventoryApi.getCategories();
      const mapped = (Array.isArray(data) ? data : []).map((c: any) => ({
        id: String(c.id),
        name: c.name || `منتج ${c.id}`,
        parent: c.parent ?? null,
      }));
      setCats(mapped);
      // مطويّة افتراضياً — لا فتح تلقائي.
    } catch {
      setCats([]);
    } finally {
      setLoadingCats(false);
    }
  }, []);

  useEffect(() => {
    void loadCats();
  }, [loadCats]);

  // إغلاق قائمة الماوس عند النقر بأي مكان أو التمرير.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  const itemsByCat = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const it of items) {
      if (!it || !it.id) continue;
      const key = it.categoryId ? String(it.categoryId) : UNCAT;
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(it);
    }
    return m;
  }, [items]);

  // T-ITEMS M2: الفهرسة من `utils/categoryTree` — كانت هذه النسخةَ الثانيةَ من
  // الخوارزمية نفسها. الوحدة تطبّع المفاتيح نصّياً، فيلتقي معرّفُ العقدة النصّي
  // هنا بمعرّف الأب الرقمي القادم من الخادم.
  const childrenOf = useMemo(() => buildCategoryIndex<Cat>(cats).childrenOf, [cats]);

  const q = query.trim().toLowerCase();
  const itemMatches = (it: Item) => !q || (it.name || "").toLowerCase().includes(q);

  const toggle = (id: string) => setExpanded((e) => ({ ...e, [id]: !(e[id] ?? false) }));

  const createCat = async (name: string, parent: string | null) => {
    const n = name.trim();
    if (!n) return;
    try {
      await inventoryApi.createCategory({ name: n, parent: parent ? Number(parent) : null });
      if (parent) setExpanded((e) => ({ ...e, [parent]: true }));
      await loadCats();
    } catch {
      /* اسم مكرر أو خطأ — تجاهل */
    }
  };

  const renameCat = async () => {
    if (!editId || !editName.trim()) return;
    try {
      await inventoryApi.updateCategory(Number(editId), { name: editName.trim() });
      setEditId(null);
      await loadCats();
    } catch {
      /* تجاهل */
    }
  };

  const deleteCat = async (id: string) => {
    if (!(await confirmDialog({ title: "حذف التصنيف", message: "هل أنت متأكد من حذف هذا التصنيف؟" }))) return;
    try {
      await inventoryApi.deleteCategory(Number(id));
      await loadCats();
    } catch {
      toast("لا يمكن حذف التصنيف. قد يكون مرتبطاً بمنتجات أو تصنيفات فرعية.", "error");
    }
  };

  const openAddItem = (catId: string | number | null) => {
    setAddItemCat(catId);
    setShowAddItem(true);
  };

  const openMenuAt = (e: React.MouseEvent, target: MenuTarget) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    // «إضافة منتج هنا» متاحةٌ للجميع في الوضع العادي، فلا تُحجب القائمة عمّن
    // لا يملك مفتاح الكتابة — تُحجب فقط في وضع إدارة التصنيفات، حيث لا يبقى فيها شيء.
    if (manageMode && !canManageCatalog) return;
    setMenu({ x: e.clientX, y: e.clientY, target });
  };

  const openMenu = (e: React.MouseEvent, catId: string | null) => {
    openMenuAt(e, catId ? { kind: "category", id: catId } : { kind: "empty" });
  };

  // كبسةٌ يمين على ورقة منتج: قائمته وحدها. بلا `stopPropagation` يفقّع الحدث
  // إلى `.ktra-tree-body` فتُستبدل قائمةُ المنتج بقائمة الفراغ.
  const openItemMenu = (e: React.MouseEvent, it: Item) => {
    openMenuAt(e, { kind: "item", item: it });
  };

  const copySku = async (sku: string) => {
    try {
      await navigator.clipboard.writeText(sku);
      toast("نُسخ الرمز", "success");
    } catch {
      toast("تعذّر النسخ", "error");
    }
  };

  /**
   * قائمة المنتج — قراءةٌ فقط في هذه التذكرة: فتح الكرت · إضافة منتج في نفس
   * التصنيف · نسخ الرمز. **لا** أفعال كتابة على التصنيفات هنا، و**لا** «إضافة
   * منتج هنا»: تلك كانت تُنشئ منتجاً بلا تصنيف لأنها تأخذ تصنيف الفراغ (D6).
   */
  const itemMenu = (it: Item) => {
    // مفتاح التصنيف نفسه الذي تُوضع تحته الورقة في `itemsByCat` — والمنتج بلا
    // تصنيف يبقى بلا تصنيف، ويُقال ذلك في نصّ البند لا يُخفى.
    const catKey = it.categoryId ? String(it.categoryId) : null;
    const sku = skuOf(it);
    return (
      <>
        {onShowCard && (
          <button type="button" className="ktra-ctxmenu-item" style={ctxItemStyle} onClick={() => { onShowCard(it); setMenu(null); }}>
            <Package className="w-3.5 h-3.5" /> فتح الكرت
          </button>
        )}
        <button type="button" className="ktra-ctxmenu-item" style={ctxItemStyle} onClick={() => { openAddItem(catKey); setMenu(null); }}>
          <PackagePlus className="w-3.5 h-3.5" /> {catKey ? "إضافة منتج في نفس التصنيف" : "إضافة منتج بدون تصنيف"}
        </button>
        {sku && (
          <button type="button" className="ktra-ctxmenu-item" style={ctxItemStyle} onClick={() => { void copySku(sku); setMenu(null); }}>
            <Copy className="w-3.5 h-3.5" /> نسخ الرمز
          </button>
        )}
      </>
    );
  };

  // ورقة منتج مفردة (نقرة → بطاقة المنتج). اسم العرض يحمل البراند.
  const leafButton = (it: Item) => (
    <button
      key={it.id}
      type="button"
      disabled={disabled}
      className="ktra-tree-leaf"
      onClick={() => handleLeafClick(it)}
      onContextMenu={(e) => openItemMenu(e, it)}
      title={`${displayNameOf(it)} — انقر لعرض بطاقة المنتج`}
    >
      <Package className="w-3 h-3 shrink-0" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{displayNameOf(it)}</span>
    </button>
  );

  // عرض المنتجات كأوراق تحت المنتج مباشرة
  const renderItems = (catId: string) => {
    const list = (itemsByCat.get(catId) || []).filter(itemMatches);
    if (!list.length) return null;
    return (
      <div className="mt-0.5" style={{ marginInlineStart: "12px" }}>
        {list.slice(0, 400).map((it) => leafButton(it))}
      </div>
    );
  };

  // النزول إلى الأحفاد يمرّ بالوحدة المشتركة: كان تعاوداً بلا حارس، فحلقةٌ في
  // البيانات تعني تعاوداً لا نهائياً وشاشةً بيضاء.
  const descendantCatIds = (catId: string): string[] =>
    descendantCategoryIds(cats, catId).map(String);

  const descendantHasMatch = (cat: Cat): boolean =>
    descendantCatIds(cat.id).some((id) => (itemsByCat.get(id) || []).some(itemMatches));

  // كل معرّفات المنتجات تحت تصنيف (وكل أحفاده) — للكرت المجمّع الشامل.
  const descendantItemIds = (catId: string): string[] =>
    descendantCatIds(catId).flatMap((id) => (itemsByCat.get(id) || []).map((m) => String(m.id)));

  const renderNode = (c: Cat, depth: number): React.ReactNode => {
    if (q && !descendantHasMatch(c)) return null;
    const kids = childrenOf.get(c.id) || [];
    const open = q ? true : (expanded[c.id] ?? false);
    const isEditing = editId === c.id;

    return (
      <div key={c.id} style={{ marginInlineStart: `${depth * 10}px` }}>
        <div className="ktra-tree-cat" onContextMenu={(e) => openMenu(e, c.id)}>
          <button type="button" className="ktra-tree-twisty" onClick={() => toggle(c.id)} title={open ? "طيّ" : "فتح"}>
            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
          </button>
          <FolderTree className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
          {isEditing ? (
            <span className="flex items-center gap-1 flex-1 min-w-0">
              <input
                className="ktra-input flex-1"
                autoFocus
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { void renameCat(); }
                  if (e.key === "Escape") setEditId(null);
                }}
              />
              <button type="button" className="ktra-tree-act" title="حفظ" onClick={() => { void renameCat(); }}><Check className="w-3.5 h-3.5" /></button>
              <button type="button" className="ktra-tree-act" title="إلغاء" onClick={() => setEditId(null)}><X className="w-3.5 h-3.5" /></button>
            </span>
          ) : (
            <>
              <button
                type="button"
                className="truncate flex-1 text-start"
                onClick={() => {
                  if (!onShowGroup) { toggle(c.id); return; }
                  // كبسةٌ واحدة تختار وتكشف: تعرض الكرت المجمّع، وتفتح الفرع إن
                  // كان مطويّاً (ولا تطويه بإعادة الكبس — الطيّ مهمّة السهم)،
                  // كما يفعل مستكشف الملفات. بلا ذلك تُعرض بطاقة تصنيفٍ لا
                  // يمكن رؤية منتجاته إلا بكبسةٍ ثانية على سهمٍ لم ينتبه له أحد.
                  onShowGroup(descendantItemIds(c.id), c.name, c.id);
                  if (!open) toggle(c.id);
                }}
                title={onShowGroup ? "كبسة ⇒ الكرت المجمّع لكل ما تحته + فتح الفرع — السهم للطيّ — كبسة يمين لخيارات" : "نقر للفتح/الطيّ — كبسة يمين لخيارات"}
              >
                {c.name}
              </button>
              <span className="ktra-tree-count">{descendantItemIds(c.id).length || ""}</span>
            </>
          )}
        </div>

        {subParent === c.id && !disabled && (
          <div className="flex items-center gap-1 my-1" style={{ marginInlineStart: "16px" }}>
            <input
              className="ktra-input flex-1"
              autoFocus
              placeholder="اسم التصنيف الفرعي"
              value={subName}
              onChange={(e) => setSubName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") { void createCat(subName, c.id); setSubParent(null); }
                if (e.key === "Escape") setSubParent(null);
              }}
            />
            <button type="button" className="ktra-tree-act" title="حفظ" onClick={() => { void createCat(subName, c.id); setSubParent(null); }}><Check className="w-3.5 h-3.5" /></button>
            <button type="button" className="ktra-tree-act" title="إلغاء" onClick={() => setSubParent(null)}><X className="w-3.5 h-3.5" /></button>
          </div>
        )}

        {open && (
          <div className="mt-0.5">
            {kids.map((k) => renderNode(k, depth + 1))}
            {renderItems(c.id)}
          </div>
        )}
      </div>
    );
  };

  const rootCats = childrenOf.get(null) || [];
  const uncategorizedItems = (itemsByCat.get(UNCAT) || []).filter(itemMatches);
  // تصنيفُ القائمة المفتوحة الآن (null لقائمة الفراغ أو قائمة المنتج).
  const menuCatId = menu?.target.kind === "category" ? menu.target.id : null;

  if (panelCollapsed && !manageMode) {
    // شريط مطويّ لا لوحة فارغة: `.ktra-tree-panel` تفرض `flex: 0 0 240px` من
    // خارج طبقات Tailwind، فـ`w-10` كانت تخسر أمامها ويبقى الطيّ 240px بيضاء
    // (قِيست: 240×320). `.ktra-tree-rail` هي شريط النظام نفسه — 32px بعنوان
    // عمودي — فيعود عرضُ اللوحة إلى الشاشة فعلاً عند الطيّ.
    return (
      <div
        className="ktra-tree-rail"
        role="button"
        tabIndex={0}
        onClick={() => setPanelCollapsed(false)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPanelCollapsed(false); } }}
        title="إظهار شجرة المنتجات"
      >
        <PanelRightOpen className="w-4 h-4" />
        <span className="ktra-tree-rail-label">شجرة المنتجات</span>
      </div>
    );
  }

  return (
    <div className={`ktra-tree-panel shrink-0 flex-1 flex flex-col ${manageMode ? "w-full border-none" : "w-[280px]"}`}>
      <div className="ktra-tree-toolbar">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-semibold" style={{ color: "var(--ktra-ink)" }}>{manageMode ? "شجرة التصنيفات" : "شجرة المنتجات"}</span>
          {!manageMode && (
            <button type="button" className="ktra-toolbtn" title="طيّ اللوحة" onClick={() => setPanelCollapsed(true)}>
              <PanelRightClose className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="relative">
          <input
            type="text"
            className="ktra-input w-full"
            style={{ paddingInlineStart: "26px" }}
            placeholder={manageMode ? "بحث عن تصنيف..." : "بحث عن منتج..."}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Search className="w-4 h-4 text-[var(--color-text-muted)] absolute" style={{ insetInlineStart: "6px", top: "6px" }} />
        </div>
        {!disabled && (
          <div className="flex gap-1 mt-1.5">
            {canManageCatalog && (
              <>
                <input
                  type="text"
                  className="ktra-input flex-1"
                  ref={rootNameInputRef}
                  placeholder="تصنيف رئيسي جديد..."
                  value={newRootName}
                  onChange={(e) => setNewRootName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { void createCat(newRootName, null); setNewRootName(""); } }}
                />
                <button type="button" className="ktra-toolbtn" title="إضافة تصنيف رئيسي" onClick={() => { void createCat(newRootName, null); setNewRootName(""); }}>
                  <FolderPlus className="w-4 h-4" />
                </button>
              </>
            )}
            {!manageMode && (
              <button type="button" className="ktra-toolbtn" title="إضافة منتج (بدون تصنيف)" onClick={() => openAddItem(null)}>
                <Plus className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* كبسة يمين على الفراغ → إضافة منتج رئيسي/منتج بدون منتج */}
      <div className="ktra-tree-body" onContextMenu={(e) => openMenu(e, null)}>
        {loadingCats ? (
          <div className="p-3 text-center text-sm text-[var(--color-text-muted)] flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> جاري التحميل...
          </div>
        ) : (
          <>
            {rootCats.map((c) => renderNode(c, 0))}
            {!manageMode && uncategorizedItems.length > 0 && (
              <div className="mt-1">
                <div className="ktra-tree-cat" onContextMenu={(e) => openMenu(e, null)}>
                  <FolderTree className="w-4 h-4 text-[var(--color-text-muted)] shrink-0" />
                  <span className="truncate flex-1">بدون تصنيف</span>
                  <span className="ktra-tree-count">{uncategorizedItems.length}</span>
                </div>
                <div className="mt-0.5">{renderItems(UNCAT)}</div>
              </div>
            )}
            {!rootCats.length && !uncategorizedItems.length && !query && (
              <div className="p-3 text-center text-sm text-[var(--color-text-muted)]">لا تصنيفات ولا منتجات — كبسة يمين أو الأزرار بالأعلى لإضافة.</div>
            )}
          </>
        )}
      </div>

      {menu && createPortal(
        // أنماط inline مضمونة — البوابة تُرسم على body خارج نطاق data-skin فلا يطبّق CSS.
        <div
          dir="rtl"
          style={{
            position: "fixed", left: menu.x, top: menu.y, zIndex: 9999,
            minWidth: 170, background: "#ffffff", border: "1px solid #b9c4cf",
            borderRadius: 6, boxShadow: "0 6px 20px rgba(0,0,0,.18)", padding: 3,
            fontFamily: "inherit", fontSize: 13, color: "#333426",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {menu.target.kind === "item" ? itemMenu(menu.target.item) : (
            <>
              {canManageCatalog && (
                <button type="button" className="ktra-ctxmenu-item" style={ctxItemStyle} onClick={() => { if (menuCatId) { setSubParent(menuCatId); setExpanded((e) => ({ ...e, [menuCatId]: true })); setSubName(""); } else { rootNameInputRef.current?.focus(); } setMenu(null); }}>
                  <FolderPlus className="w-3.5 h-3.5" /> {menuCatId ? "إضافة تصنيف فرعي" : "إضافة تصنيف رئيسي"}
                </button>
              )}
              {!manageMode && (
                <button type="button" className="ktra-ctxmenu-item" style={ctxItemStyle} onClick={() => { openAddItem(menuCatId); setMenu(null); }}>
                  <PackagePlus className="w-3.5 h-3.5" /> إضافة منتج هنا
                </button>
              )}
              {menuCatId && canManageCatalog && (
                <>
                  <button type="button" className="ktra-ctxmenu-item" style={ctxItemStyle} onClick={() => {
                    const c = cats.find((x) => x.id === menuCatId);
                    setEditId(menuCatId); setEditName(c?.name || ""); setMenu(null);
                  }}>
                    <Pencil className="w-3.5 h-3.5" /> تعديل اسم التصنيف
                  </button>
                  <button type="button" className="ktra-ctxmenu-item text-red-600 hover:bg-red-50" style={{...ctxItemStyle, color: "#dc2626"}} onClick={() => {
                    const id = menuCatId; setMenu(null); void deleteCat(id!);
                  }}>
                    <Trash2 className="w-3.5 h-3.5" /> حذف التصنيف
                  </button>
                </>
              )}
            </>
          )}
        </div>,
        document.body,
      )}

      {showAddItem && (
        <ItemQuickCreateModal
          isOpen
          categoryId={addItemCat}
          onClose={() => setShowAddItem(false)}
          onSaved={(p) => {
            const item = productToItem(p);
            onItemCreated?.(item);
            onPickItem(item);
            setShowAddItem(false);
            void loadCats();
          }}
        />
      )}
    </div>
  );
};
