import React, { useEffect, useMemo, useState, useCallback } from "react";
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
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import { inventoryApi } from "../../../services/inventoryApi";
import { Item } from "../../../types";
import { ItemQuickCreateModal } from "../../items/ItemQuickCreateModal";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { productToItem } from "../price-offers/ItemSearchModal";

/**
 * task18 DEF-B1/B3: شجرة منتجات احترافية مرساة بجانب الفاتورة (نمط الأصيل).
 * المصطلحات (DEF-002): «صنف/فئة» = العقدة الفرعية (branch) · «منتج» = العقدة
 * الورقية (leaf). المنتجات تُجمَّع تحت أصنافها.
 * - زر الماوس الأيمن على أي عقدة → قائمة: «إضافة صنف» (فرعي) · «إضافة منتج» · «تعديل».
 * - DEF-007: النقر المفرد على منتج يفتح بطاقته · النقر المزدوج يُدرجه في الفاتورة.
 * + بحث فوري.
 */
type Cat = { id: string; name: string; parent: number | null };

interface Props {
  items: Item[];
  /** DEF-007: إدراج المنتج في الفاتورة (نقر مزدوج). */
  onPickItem: (item: Item) => void;
  /** DEF-007: فتح بطاقة المنتج (نقر مفرد). */
  onShowCard?: (item: Item) => void;
  /** تجميع البراندات: فتح الكرت المجمّع لعقدة المقاس (مجموع كل البراندات). */
  onShowGroup?: (memberIds: string[], name: string) => void;
  onItemCreated?: (item: Item) => void;
  disabled?: boolean;
  manageMode?: boolean; // If true, hides product-specific UI and acts purely as a category manager.
}

// تجميع البراندات أصبح حقيقياً (Category).
const displayNameOf = (it: Item) => String((it as unknown as { display_name?: string }).display_name || it.name || "");

const UNCAT = "__uncat__";

const ctxItemStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 6, width: "100%",
  padding: "6px 9px", border: 0, background: "transparent", cursor: "pointer",
  fontSize: 13, color: "#333426", textAlign: "start", borderRadius: 5,
};

export const InvoiceCategoryTree: React.FC<Props> = ({ items, onPickItem, onShowCard, onShowGroup, onItemCreated, disabled, manageMode }) => {
  // نقرة مفردة على الصنف → تفتح بطاقة الصنف (وفيها «موافق» للإضافة). لا إدراج
  // بالنقر المزدوج. (الإدراج المباشر يبقى فقط عند إنشاء صنف جديد من الشجرة.)
  const handleLeafClick = (it: Item) => {
    if (disabled) return;
    onShowCard?.(it);
  };
  const [cats, setCats] = useState<Cat[]>([]);
  const toast = useToast();
  const confirmDialog = useConfirm();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loadingCats, setLoadingCats] = useState(false);
  const [newRootName, setNewRootName] = useState("");
  const [subParent, setSubParent] = useState<string | null>(null);
  const [subName, setSubName] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [addItemCat, setAddItemCat] = useState<string | number | null>(null);
  const [showAddItem, setShowAddItem] = useState(false);
  // قائمة زر الماوس الأيمن
  const [menu, setMenu] = useState<{ x: number; y: number; catId: string | null } | null>(null);
  // طيّ اللوحة كاملة لتوفير المساحة الأفقية
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  const loadCats = useCallback(async () => {
    setLoadingCats(true);
    try {
      const data = await inventoryApi.getCategories();
      const mapped = (Array.isArray(data) ? data : []).map((c: any) => ({
        id: String(c.id),
        name: c.name || `صنف ${c.id}`,
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

  const childrenOf = useMemo(() => {
    const m = new Map<string | null, Cat[]>();
    for (const c of cats) {
      const p = c.parent == null ? null : String(c.parent);
      if (!m.has(p)) m.set(p, []);
      m.get(p)!.push(c);
    }
    return m;
  }, [cats]);

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
    if (!(await confirmDialog({ title: "حذف الصنف", message: "هل أنت متأكد من حذف هذا الصنف؟" }))) return;
    try {
      await inventoryApi.deleteCategory(Number(id));
      await loadCats();
    } catch {
      toast("لا يمكن حذف الصنف. قد يكون مرتبطاً بمنتجات أو أصناف فرعية.", "error");
    }
  };

  const openAddItem = (catId: string | number | null) => {
    setAddItemCat(catId);
    setShowAddItem(true);
  };

  const openMenu = (e: React.MouseEvent, catId: string | null) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, catId });
  };

  // ورقة منتج مفردة (نقرة → بطاقة الصنف). اسم العرض يحمل البراند.
  const leafButton = (it: Item) => (
    <button
      key={it.id}
      type="button"
      disabled={disabled}
      className="aseel-tree-leaf"
      onClick={() => handleLeafClick(it)}
      title={`${displayNameOf(it)} — انقر لعرض بطاقة الصنف`}
    >
      <Package className="w-3 h-3 shrink-0" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{displayNameOf(it)}</span>
    </button>
  );

  // عرض المنتجات كأوراق تحت الصنف مباشرة
  const renderItems = (catId: string) => {
    const list = (itemsByCat.get(catId) || []).filter(itemMatches);
    if (!list.length) return null;
    return (
      <div className="mt-0.5" style={{ marginInlineStart: "12px" }}>
        {list.slice(0, 400).map((it) => leafButton(it))}
      </div>
    );
  };

  const descendantHasMatch = (cat: Cat): boolean => {
    if ((itemsByCat.get(cat.id) || []).some(itemMatches)) return true;
    return (childrenOf.get(cat.id) || []).some(descendantHasMatch);
  };

  // كل معرّفات المنتجات تحت تصنيف (وكل أحفاده) — للكرت المجمّع الشامل.
  const descendantItemIds = (catId: string): string[] => {
    const ids = (itemsByCat.get(catId) || []).map((m) => String(m.id));
    for (const ch of childrenOf.get(catId) || []) ids.push(...descendantItemIds(ch.id));
    return ids;
  };

  const renderNode = (c: Cat, depth: number): React.ReactNode => {
    if (q && !descendantHasMatch(c)) return null;
    const kids = childrenOf.get(c.id) || [];
    const open = q ? true : (expanded[c.id] ?? false);
    const isEditing = editId === c.id;

    return (
      <div key={c.id} style={{ marginInlineStart: `${depth * 10}px` }}>
        <div className="aseel-tree-cat" onContextMenu={(e) => openMenu(e, c.id)}>
          <button type="button" className="aseel-tree-twisty" onClick={() => toggle(c.id)} title={open ? "طيّ" : "فتح"}>
            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
          </button>
          <FolderTree className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
          {isEditing ? (
            <span className="flex items-center gap-1 flex-1 min-w-0">
              <input
                className="aseel-input flex-1"
                autoFocus
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { void renameCat(); }
                  if (e.key === "Escape") setEditId(null);
                }}
              />
              <button type="button" className="aseel-tree-act" title="حفظ" onClick={() => { void renameCat(); }}><Check className="w-3.5 h-3.5" /></button>
              <button type="button" className="aseel-tree-act" title="إلغاء" onClick={() => setEditId(null)}><X className="w-3.5 h-3.5" /></button>
            </span>
          ) : (
            <>
              <button
                type="button"
                className="truncate flex-1 text-start"
                onClick={() => (onShowGroup ? onShowGroup(descendantItemIds(c.id), c.name) : toggle(c.id))}
                title={onShowGroup ? "كبسة ⇒ الكرت المجمّع لكل ما تحته — السهم للفتح/الطيّ — كبسة يمين لخيارات" : "نقر للفتح/الطيّ — كبسة يمين لخيارات"}
              >
                {c.name}
              </button>
              <span className="aseel-tree-count">{descendantItemIds(c.id).length || ""}</span>
            </>
          )}
        </div>

        {subParent === c.id && !disabled && (
          <div className="flex items-center gap-1 my-1" style={{ marginInlineStart: "16px" }}>
            <input
              className="aseel-input flex-1"
              autoFocus
              placeholder="اسم الصنف الفرعي"
              value={subName}
              onChange={(e) => setSubName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") { void createCat(subName, c.id); setSubParent(null); }
                if (e.key === "Escape") setSubParent(null);
              }}
            />
            <button type="button" className="aseel-tree-act" title="حفظ" onClick={() => { void createCat(subName, c.id); setSubParent(null); }}><Check className="w-3.5 h-3.5" /></button>
            <button type="button" className="aseel-tree-act" title="إلغاء" onClick={() => setSubParent(null)}><X className="w-3.5 h-3.5" /></button>
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

  if (panelCollapsed && !manageMode) {
    return (
      <div className="aseel-tree-panel w-10 shrink-0 flex flex-col items-center py-2 cursor-pointer hover:bg-gray-50" onClick={() => setPanelCollapsed(false)} title="إظهار الشجرة">
        <PanelRightOpen className="w-5 h-5 text-gray-500" />
      </div>
    );
  }

  return (
    <div className={`aseel-tree-panel shrink-0 flex-1 flex flex-col ${manageMode ? "w-full border-none" : "w-[280px]"}`}>
      <div className="aseel-tree-toolbar">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-semibold" style={{ color: "var(--aseel-ink)" }}>{manageMode ? "شجرة التصنيفات" : "شجرة المنتجات"}</span>
          {!manageMode && (
            <button type="button" className="aseel-toolbtn" title="طيّ اللوحة" onClick={() => setPanelCollapsed(true)}>
              <PanelRightClose className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="relative">
          <input
            type="text"
            className="aseel-input w-full"
            style={{ paddingInlineStart: "26px" }}
            placeholder={manageMode ? "بحث عن تصنيف..." : "بحث عن منتج..."}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Search className="w-4 h-4 text-gray-400 absolute" style={{ insetInlineStart: "6px", top: "6px" }} />
        </div>
        {!disabled && (
          <div className="flex gap-1 mt-1.5">
            <input
              type="text"
              className="aseel-input flex-1"
              placeholder="صنف رئيسي جديد..."
              value={newRootName}
              onChange={(e) => setNewRootName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { void createCat(newRootName, null); setNewRootName(""); } }}
            />
            <button type="button" className="aseel-toolbtn" title="إضافة صنف رئيسي" onClick={() => { void createCat(newRootName, null); setNewRootName(""); }}>
              <FolderPlus className="w-4 h-4" />
            </button>
            {!manageMode && (
              <button type="button" className="aseel-toolbtn" title="إضافة منتج (بدون صنف)" onClick={() => openAddItem(null)}>
                <Plus className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* كبسة يمين على الفراغ → إضافة صنف رئيسي/منتج بدون صنف */}
      <div className="aseel-tree-body" onContextMenu={(e) => openMenu(e, null)}>
        {loadingCats ? (
          <div className="p-3 text-center text-sm text-gray-500 flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> جاري التحميل...
          </div>
        ) : (
          <>
            {rootCats.map((c) => renderNode(c, 0))}
            {!manageMode && uncategorizedItems.length > 0 && (
              <div className="mt-1">
                <div className="aseel-tree-cat">
                  <FolderTree className="w-4 h-4 text-gray-400 shrink-0" />
                  <span className="truncate flex-1">بدون صنف</span>
                  <span className="aseel-tree-count">{uncategorizedItems.length}</span>
                </div>
                <div className="mt-0.5">{renderItems(UNCAT)}</div>
              </div>
            )}
            {!rootCats.length && !uncategorizedItems.length && !query && (
              <div className="p-3 text-center text-sm text-gray-500">لا أصناف/منتجات — كبسة يمين أو الأزرار بالأعلى لإضافة.</div>
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
          <button type="button" className="aseel-ctxmenu-item" style={ctxItemStyle} onClick={() => { if (menu.catId) { setSubParent(menu.catId); setExpanded((e) => ({ ...e, [menu.catId!]: true })); setSubName(""); } else { const input = document.querySelector<HTMLInputElement>("input[placeholder='صنف رئيسي جديد...']"); input?.focus(); } setMenu(null); }}>
            <FolderPlus className="w-3.5 h-3.5" /> {menu.catId ? "إضافة صنف فرعي" : "إضافة صنف رئيسي"}
          </button>
          {!manageMode && (
            <button type="button" className="aseel-ctxmenu-item" style={ctxItemStyle} onClick={() => { openAddItem(menu.catId); setMenu(null); }}>
              <PackagePlus className="w-3.5 h-3.5" /> إضافة منتج هنا
            </button>
          )}
          {menu.catId && (
            <>
              <button type="button" className="aseel-ctxmenu-item" style={ctxItemStyle} onClick={() => {
                const c = cats.find((x) => x.id === menu.catId);
                setEditId(menu.catId); setEditName(c?.name || ""); setMenu(null);
              }}>
                <Pencil className="w-3.5 h-3.5" /> تعديل اسم الصنف
              </button>
              <button type="button" className="aseel-ctxmenu-item text-red-600 hover:bg-red-50" style={{...ctxItemStyle, color: "#dc2626"}} onClick={() => {
                const id = menu.catId; setMenu(null); void deleteCat(id!);
              }}>
                <Trash2 className="w-3.5 h-3.5" /> حذف الصنف
              </button>
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
