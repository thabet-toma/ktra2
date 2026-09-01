/**
 * N5-T3 — ItemsManagement (L4) — KitDenseTable للمنتجات
 * يستخدم SQL products من inventoryApi (لا Firestore).
 */
import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct } from "../../types/inventory";
import { type DenseColumn } from "../kit/KitDenseTable";
import { GroupedItemsTable, type TreeCategory } from "./GroupedItemsTable";
import { MergeProductsModal } from "./MergeProductsModal";
import {
  Plus, RefreshCw, Edit2, Package, Boxes, ListTree, Table2, Printer, Copy, ExternalLink,
  FolderTree, Merge, Undo2, X,
} from "lucide-react";
import { ItemForm } from "./ItemForm";
import { useProductInsights, useGroupInsights } from "./ProductInsightTabs";
import { KitTabs, type KitTab } from "../kit";
import { CategoriesManagement } from "./CategoriesManagement";
import { InvoiceCategoryTree } from "../procurement/invoices/InvoiceCategoryTree";
import type { Item } from "../../types";
import { StalenessBadge } from "../offline";
import db from "../../services/offline/db";
import { openInNewTab } from "@/utils/openInNewTab";
import { productGroupPath, productProfilePath } from "../../utils/entityLinks";
import { clientLogger } from "../../services/logger";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { resolveTenantId } from "../../utils/tenantContext";
import { tenantScopedOfflineKey } from "../../utils/offlineTenantScope";
import { useKeepOnce, useSimpleUi } from "../../hooks/useSimpleUi";
import {
  simpleFieldsFromProduct, dirtySimplePayload, validateSimpleFields,
} from "../../utils/itemSimpleFields";
import { humanizeThrown } from "../../utils/drfError";
import { groupProductsByFamily, buildFamilyRow } from "../../utils/familyGrouping";
import { eventBus } from "../../utils/eventBus";
import type { MergeCandidate } from "../../utils/productMerge";
import type { MergeProductsResult } from "../../services/inventoryApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة عبر المُنسّق الموحّد.
const fmt = (n: number | string) => formatMoney(n, "0");

type View = "list" | "form";
type StockStatus = "" | "out_of_stock" | "low_stock" | "overstock" | "in_stock";

// مفتاح عمود الجدول → حقل الترتيب الخادمي (OrderingFilter).
const ORDER_FIELD: Record<string, string> = {
  sku: "sku",
  name_ar: "name_ar",
  qty: "quantity_on_hand",
  avg_cost: "avg_cost",
  sale_price: "sale_price",
  min: "min_stock_level",
  max: "max_stock_level",
};

const STATUS_LABEL: Record<Exclude<StockStatus, "">, string> = {
  out_of_stock: "نفذ",
  low_stock: "منخفض",
  // T-REORDER: حالةٌ رابعة يحسمها الخادم — فوق الحدّ الأقصى المضبوط على المنتج.
  overstock: "فائض",
  in_stock: "متوفر",
};

const exportItemStyle: React.CSSProperties = {
  display: "block", width: "100%", textAlign: "start", padding: "8px 12px",
  background: "none", border: "none", cursor: "pointer", color: "var(--ktra-ink)",
};

/**
 * البطاقة الجانبية للعرض الشجري — العرض الشجري كان يشغل شريط 240px ويترك بقية
 * عرض الشاشة بياضاً، والنقر على منتج (أو تصنيف) يقذف المستخدم إلى تبويب جديد.
 * صار الفراغ بطاقةَ ما هو محدَّد في الشجرة، على نمط شجرة الحسابات: شريط شجرة
 * + بطاقة السجل المحدَّد.
 *
 * إطارٌ واحد للحالتين (منتج مفرد · تصنيف مجمّع): الرأس هوية وأزرار، وتحته
 * تبويبات الكرت نفسها التي تعرضها الصفحة الكاملة — لا نسخة ثانية منها.
 */
const TreePaneFrame: React.FC<{
  icon: React.ReactNode;
  title: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  tabs: KitTab[];
}> = ({ icon, title, badge, actions, tabs }) => (
  <div className="flex h-full min-h-0 flex-col">
    <div className="flex items-center gap-2 border-b border-[var(--ktra-border)] px-2 py-1.5">
      {icon}
      <b className="truncate text-[var(--ktra-ink)]" title={title}>{title}</b>
      {badge}
      <div className="flex-1" />
      {actions}
    </div>
    <div className="min-h-0 flex-1 overflow-auto">
      <KitTabs tabs={tabs} />
    </div>
  </div>
);

/**
 * بطاقة المنتج المفرد. التركيب بمفتاح `key` عند المستدعي: كل اختيار يُعيد
 * التركيب، فنتائج طلبٍ سابق بطيء تسقط على مكوّن مفكوك بدل أن تكتب فوق
 * بيانات المنتج الجديد.
 */
const ProductTreePane: React.FC<{
  productId: number;
  productName: string;
  onEdit: () => void;
}> = ({ productId, productName, onEdit }) => {
  const { profile, tabs } = useProductInsights(productId);
  const title = profile?.name || productName || `منتج #${productId}`;
  return (
    <TreePaneFrame
      icon={<Package className="h-4 w-4 shrink-0 text-[var(--ktra-ink-soft)]" />}
      title={title}
      badge={profile?.sku ? <span className="ktra-status-item" dir="ltr">{profile.sku}</span> : null}
      tabs={tabs}
      actions={
        <>
          <button type="button" className="ktra-toolbtn" onClick={onEdit} title="تعديل هذا المنتج">
            <Edit2 className="h-4 w-4" /> تعديل
          </button>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => openInNewTab(productProfilePath(productId))}
            title="فتح الكرت الكامل في تبويب مستقل"
          >
            <ExternalLink className="h-4 w-4" /> الكرت الكامل
          </button>
        </>
      }
    />
  );
};

/** بطاقة التصنيف: الكرت المجمّع لكل المنتجات تحته (وأحفاده).
 *  مع `categoryId` يشتقّ الخادمُ الأعضاء بنفسه، فلا يسافر تعدادُ 1500 معرّف في
 *  الطلب (كان يبلغ ~7.5KB في سطر الطلب فيردّه nginx بـ414). */
const GroupTreePane: React.FC<{
  ids: number[];
  groupName: string;
  categoryId?: number;
}> = ({ ids, groupName, categoryId }) => {
  const { profile, tabs } = useGroupInsights(
    categoryId != null ? { category: categoryId } : { ids },
  );
  const title = groupName || profile?.name || "كرت مجمّع";
  const count = profile?.member_count ?? ids.length;
  return (
    <TreePaneFrame
      icon={<FolderTree className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />}
      title={`كرت مجمّع: ${title}`}
      badge={<span className="ktra-status-item">{count} منتج</span>}
      tabs={tabs}
      actions={
        <button
          type="button"
          className="ktra-toolbtn"
          disabled={!ids.length && categoryId == null}
          onClick={() => openInNewTab(productGroupPath({ name: title, categoryId, ids }))}
          title="فتح الكرت المجمّع في تبويب مستقل"
        >
          <ExternalLink className="h-4 w-4" /> الكرت الكامل
        </button>
      }
    />
  );
};

/** ما هو محدَّد في الشجرة: منتجٌ مفرد أو تصنيفٌ مجمّع. */
type TreePreview =
  | { kind: "product"; id: number; name: string }
  | { kind: "group"; ids: number[]; name: string; categoryId?: number };

export const ItemsManagement: React.FC<{ user?: unknown, initialTab?: "products" | "categories" }> = ({ initialTab = "products" }) => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"products" | "categories">(initialTab);
  
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  const [products, setProducts] = useState<SqlProduct[]>([]);
  /* T-PRODUCT M2: تحرير الاسم داخل الخلية — خليةٌ واحدة قيد التحرير في كل وقت.
     الحالة تسكن هنا لا في `GroupedItemsTable`: الإغلاق الذي يبني العمود يلتقطها
     مباشرةً، فلا يُمَسّ عقد `DenseColumn` ولا بقية جداول التطبيق. */
  const [nameEdit, setNameEdit] = useState<{
    id: number; draft: string; saving: boolean; error: string | null;
  } | null>(null);
  // حارس الطلب الطائر: Enter يحفظ ثم يُعطّل الحقل، وتعطيلُه يُطلق `blur` — فلولا
  // هذا الحارس لانطلق الحفظ مرتين على نفس التعديل.
  const nameSavingRef = useRef(false);
  const nameInputRef = useRef<HTMLInputElement | null>(null);
  const nameEditRef = useRef<typeof nameEdit>(null);
  useEffect(() => { nameEditRef.current = nameEdit; }, [nameEdit]);
  const { columns: maskColumns } = useSimpleUi();
  // شجرة التصنيفات (أي عمق) لعرض الجدول الشجري + الكرت المجمّع لكل تصنيف.
  const [treeCategories, setTreeCategories] = useState<TreeCategory[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>("list");
  // T-N3: عرض المنتجات كشجرة تصنيفات (مثل شجرة المنتجات في الفواتير) أو كجدول.
  // الافتراضي «جدول» (بطلب المالك) — يفتح على وضعية الجدول مباشرةً.
  const [displayMode, setDisplayMode] = useState<"tree" | "table">("table");
  const [editId, setEditId] = useState<number | null>(null);
  const [duplicateId, setDuplicateId] = useState<number | null>(null);
  // المعروض في بطاقة العرض الشجري (يمين: الشجرة · يسار: بطاقة ما اخترته).
  const [preview, setPreview] = useState<TreePreview | null>(null);
  const [search, setSearch] = useState("");
  const [total, setTotal] = useState(0);
  // المرحلة 5 / P0-12: ترقيم خادمي فعلي للعرض الجدولي.
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  // جدول المنتجات: فلتر حالة المخزون + ترتيب حسب العمود (خادمي) + قائمة التصدير.
  const [statusFilter, setStatusFilter] = useState<StockStatus>("");
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const pageSize = 50;

  // #24: تحديد الضمّ — خريطةٌ لا مجموعة معرّفات: تحفظ لقطة الصفّ لحظة تحديده
  // (الوحدة/التتبّع التسلسلي/الاسم) كي تبقى صالحة بعد تبديل الصفحة، حين يُستبدل
  // `products` بصفحةٍ لا تحمل صفوف الصفحة السابقة المُحدَّدة.
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelected, setMergeSelected] = useState<Map<number, SqlProduct>>(new Map());
  const [mergeModalOpen, setMergeModalOpen] = useState(false);
  const [lastMerge, setLastMerge] = useState<{
    mergeId: number; targetName: string; mergedCount: number;
  } | null>(null);
  const [undoingMerge, setUndoingMerge] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();

  const orderingParam = sortKey
    ? `${sortDir === "desc" ? "-" : ""}${ORDER_FIELD[sortKey] ?? sortKey}`
    : "";
  // Phase 2 wiring: track when the list was last refreshed from the server,
  // and whether the current render is being served from the offline cache.
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [fromCache, setFromCache] = useState(false);

  const load = useCallback(async (opts: {
    search?: string; status?: StockStatus; ordering?: string;
    page?: number; mode?: "tree" | "table";
  } = {}) => {
    const {
      search: currentSearch = "", status = "", ordering = "",
      page = 1, mode = "table",
    } = opts;
    const tenantId = resolveTenantId();
    const cacheMetaKey = tenantScopedOfflineKey(tenantId, "products:list");
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string | number> = {};
      if (currentSearch) params.search = currentSearch;
      if (status) params.stock_status = status;
      if (ordering) params.ordering = ordering;
      // المرحلة 5 / P0-12: العرض الجدولي (الافتراضي) يجلب **صفحة واحدة** —
      // كان يدور على كل الصفحات (page_size=200) فيُصدر 8 طلبات متسلسلة لـ1490
      // منتجاً، ويُعيد ذلك كاملاً بعد كل دورة بحث (debounce 250ms).
      // العرض الشجري يجمّع حسب التصنيف فيحتاج المجموعة كاملة بطبيعته — يبقى
      // على الجلب الكامل، وهو ليس الوضع الافتراضي.
      let allRows: SqlProduct[];
      if (mode === "tree") {
        allRows = await inventoryApi.getAllProducts(params) as SqlProduct[];
        setProducts(allRows);
        setTotal(allRows.length);
        setHasNext(false);
      } else {
        const paged = await inventoryApi.getProductsPaged({
          // الخادم يُكمل عائلات الصفحة بعد التقسيم — بلا هذا يُرسم صفّ منتجٍ
          // بمجموع البراندات الواصلة وحدها ويدّعي أنه مجموع المنتج
          // (`inventory/views.py` — `_complete_families`). الوضع الشجري يجلب
          // المجموعة كاملة أصلاً فلا يلزمه.
          ...params, page, page_size: pageSize, complete_families: 1,
        });
        allRows = paged.results as SqlProduct[];
        setProducts(allRows);
        setTotal(paged.count);
        setHasNext(paged.hasNext);
      }
      // شجرة التصنيفات (لعرض الجدول الشجري) — غير حظري.
      try {
        const cats = await inventoryApi.getCategories() as Array<{ id: number; name: string; parent: number | null }>;
        setTreeCategories(cats.map((c) => ({ id: c.id, name: c.name, parent: c.parent ?? null })));
      } catch { /* non-fatal */ }
      const now = new Date().toISOString();
      setLastSync(now);
      setFromCache(false);
      // Mirror into Dexie so the offline fallback below has fresh data.
      try {
        for (const p of allRows) {
          await db.products.put({
            id: p.id,
            tenant_id: tenantId,
            sku: p.sku,
            name_ar: p.name_ar || "",
            data: JSON.stringify(p),
            updated_at: now,
          });
        }
        await db.cache_meta.put({ key: cacheMetaKey, updated_at: now });
      } catch { /* IndexedDB unavailable in private mode — non-fatal */ }
    } catch (e: unknown) {
      // Network failed — try to serve the last cached snapshot so the screen
      // stays usable offline. Surface the staleness via the badge.
      try {
        const cached = await db.products.where("tenant_id").equals(tenantId).toArray();
        if (cached.length > 0) {
          setProducts(cached.map((c) => JSON.parse(c.data) as SqlProduct));
          // أوفلاين: المعروض هو لقطة الكاش كاملةً، فالإجمالي هو طولها — وإلا
          // بقي العدّاد على count الخادم من آخر اتصال ناجح فأشار لعدد غير معروض.
          setTotal(cached.length);
          setHasNext(false);
          const meta = await db.cache_meta.get(cacheMetaKey);
          setLastSync(meta?.updated_at ?? cached[0].updated_at);
          setFromCache(true);
          setErr(null);
          return;
        }
      } catch { /* fall through */ }
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, [pageSize]);

  // تغيّر البحث/الفلتر/الترتيب يعيدنا للصفحة الأولى — وإلا بقينا على صفحة 7
  // من نتيجة لم تعد موجودة. مفصول عن تأثير الجلب كي لا يجلب مرتين.
  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, orderingParam, displayMode]);

  // مصدر تحميل واحد: البحث (debounced) + فلتر الحالة + الترتيب + الصفحة.
  useEffect(() => {
    const t = setTimeout(() => {
      load({
        search, status: statusFilter, ordering: orderingParam,
        page, mode: displayMode,
      });
    }, 250);
    return () => clearTimeout(t);
  }, [load, search, statusFilter, orderingParam, page, displayMode]);

  // إعادة تحميل يدوي (زر التحديث / بعد الحفظ) يحافظ على الفلاتر والصفحة الحالية.
  const reload = useCallback(() => {
    load({
      search, status: statusFilter, ordering: orderingParam,
      page, mode: displayMode,
    });
  }, [load, search, statusFilter, orderingParam, page, displayMode]);

  // #24: تبديل تحديد صفٍّ واحد — يلتقط الصفّ من `products` الحالية عند الإضافة
  // (هي معروضة فعلاً وقت النقر)، ويكتفي بالمعرّف عند الإزالة.
  const toggleMergeSelected = useCallback((id: number) => {
    setMergeSelected((prev) => {
      const next = new Map(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        const row = products.find((p) => p.id === id);
        if (row) next.set(id, row);
      }
      return next;
    });
  }, [products]);

  const mergeSelectedIds = useMemo(
    () => new Set(mergeSelected.keys()), [mergeSelected],
  );

  const mergeCandidates: MergeCandidate[] = useMemo(
    () => [...mergeSelected.values()].map((p) => ({
      id: p.id,
      // الاسم المجرَّد لا `display_name`: تلك تُلحق البراند القديم بين قوسين،
      // وهذه النافذة تعرض البراند في عمودٍ مستقلٍّ قابلٍ للتعديل — عرضهما معاً
      // يُبقي نصّاً قديماً بجانب حقلٍ حيّ يعدّله المستخدم فعلاً.
      name: p.name_ar || p.name_en || p.sku || `#${p.id}`,
      brand: p.brand || "",
      uomId: p.uom_id ?? null,
      isSerialized: !!p.is_serialized,
    })),
    [mergeSelected],
  );

  const handleMerged = useCallback((result: MergeProductsResult & { targetName: string }) => {
    setLastMerge({
      mergeId: result.merge_id, targetName: result.targetName,
      mergedCount: result.merged_product_ids.length,
    });
    setMergeSelected(new Map());
    setMergeMode(false);
    reload();
  }, [reload]);

  const handleUndoMerge = useCallback(async () => {
    if (!lastMerge) return;
    const ok = await confirm({
      title: "التراجع عن الضمّ",
      message: `سيعود ${lastMerge.mergedCount} منتجاً إلى ما كانوا عليه قبل الضمّ تحت «${lastMerge.targetName}» — الاسم والانتساب كما كانا حرفياً، بلا أثرٍ آخر.`,
      confirmText: "تراجع",
      danger: false,
    });
    if (!ok) return;
    setUndoingMerge(true);
    try {
      await inventoryApi.undoProductMerge(lastMerge.mergeId);
      toast("تمّ التراجع عن الضمّ.", "success");
      setLastMerge(null);
      reload();
    } catch (e: unknown) {
      toast(humanizeThrown(e, "تعذّر التراجع عن الضمّ"), "error");
    } finally {
      setUndoingMerge(false);
    }
  }, [lastMerge, confirm, toast, reload]);

  const beginNameEdit = useCallback((row: SqlProduct) => {
    if (nameSavingRef.current) return;
    setNameEdit({ id: row.id, draft: String(row.name_ar ?? row.name_en ?? ""), saving: false, error: null });
  }, []);

  /**
   * حفظ الاسم من داخل الخلية — **بلا مسار حفظٍ ثانٍ**: نفس تحقّق
   * `validateSimpleFields` ونفس حمولة `dirtySimplePayload` التي يستعملها
   * التحرير السريع من المستند والكرت الكامل.
   *
   * نشرُ `before` قبل تعديل الاسم حمّالٌ للمعنى: صفّ القائمة نحيلٌ مقارنةً
   * بالكرت، فبناء `after` من الصفر يُرسل `category: null` و`sale_price: null`
   * كتاباتٍ زائفة لم يطلبها أحد.
   *
   * ومتشائم لا متفائل: الجدول مفروزٌ ومصفَّحٌ خادمياً، فإظهار الاسم الجديد قبل
   * ردّ الخادم يترك الصفّ في موضعٍ ما كان الخادم ليضعه فيه. ولا شيء يُعدَّل
   * محلياً قبل الردّ — فلا شيء يُتراجَع عنه عند الفشل.
   */
  const commitNameEdit = useCallback(async (row: SqlProduct) => {
    const state = nameEditRef.current;
    if (!state || state.id !== row.id || nameSavingRef.current) return;
    const draft = state.draft.trim();
    const before = simpleFieldsFromProduct(row as unknown as Record<string, unknown>);
    const after = { ...before, name_ar: draft };
    const invalid = validateSimpleFields(after);
    if (invalid) { setNameEdit({ ...state, saving: false, error: invalid }); nameInputRef.current?.focus(); return; }
    const payload = dirtySimplePayload(before, after);
    if (Object.keys(payload).length === 0) { setNameEdit(null); return; }

    nameSavingRef.current = true;
    setNameEdit({ ...state, saving: true, error: null });
    try {
      const updated = await inventoryApi.updateProduct(row.id, payload) as Record<string, unknown>;
      // `updateProduct` يُبطل كاش منتقي المنتجات بنفسه؛ الحدث يوقظ الشاشات
      // التي تحمل قائمتها الخاصة (فاتورة بيع مفتوحة في تبويب آخر).
      eventBus.publish("products", resolveTenantId());
      setNameEdit(null);
      if (sortKey === "name_ar") {
        // الفرز على الاسم: موضع الصفّ قرارٌ خادمي، فيُعاد الجلب بدل تخمينه.
        reload();
      } else {
        // ترقيعُ حقول الاسم وحدها — لا نشر الردّ كاملاً فوق الصفّ: صفّ القائمة
        // يحمل حقولاً محسوبة (الرصيد، المتاح، متوسط البيع) لا يعيدها ردّ التعديل.
        setProducts((rows) => rows.map((r) => (r.id === row.id ? {
          ...r,
          name_ar: (updated.name_ar ?? null) as string | null,
          name_en: (updated.name_en ?? r.name_en ?? null) as string | null,
          display_name: (updated.display_name ?? null) as string | null,
        } : r)));
      }
    } catch (e: unknown) {
      setNameEdit({ ...state, saving: false, error: humanizeThrown(e, "تعذّر حفظ الاسم") });
      // البقاء في التحرير مع المسوّدة: المستخدم يصحّح ويعيد المحاولة بلا إعادة كتابة.
      setTimeout(() => nameInputRef.current?.focus(), 0);
    } finally {
      nameSavingRef.current = false;
    }
  }, [sortKey, reload]);

  // تصدير PDF للطباعة بخيارات: الكل / ما نفذ / المنخفضة — يجلب كل الصفحات المطابقة
  // (لا الصفحة الحالية فقط) ثم يفتح نافذة طباعة بنفس نمط تقرير أرصدة المخزون (DRY).
  const exportProducts = useCallback(async (status: StockStatus) => {
    setExportMenuOpen(false);
    setExporting(true);
    try {
      const all: SqlProduct[] = [];
      let pg = 1;
      for (;;) {
        const params: Record<string, string | number> = {
          page: pg, page_size: 200, complete_families: 1,
        };
        if (status) params.stock_status = status;
        const data = await inventoryApi.getProducts(params);
        const rows = (Array.isArray(data) ? data : (data.results ?? [])) as SqlProduct[];
        all.push(...rows);
        const count = (Array.isArray(data) ? rows.length : (data.count ?? all.length)) as number;
        if (rows.length === 0 || all.length >= count) break;
        pg++;
      }
      if (all.length === 0) { setErr("لا توجد منتجات للتصدير بهذا الخيار."); return; }

      const printWindow = window.open("", "_blank");
      if (!printWindow) { setErr("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة"); return; }

      const today = new Date().toISOString().slice(0, 10);
      const subset = status ? `المنتجات: ${STATUS_LABEL[status]}` : "كل المنتجات";
      const esc = (v: unknown) => String(v ?? "—")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      // التقرير يطبع **منتجات** لا براندات — نفس ما تعرضه الشاشة، ومن نفس
      // دالّة التجميع (`utils/familyGrouping`) لا نسخةٍ ثانية منها. كان يطبع
      // صفوف البراندات خاماً، فيظهر المقاس الواحد مرّتين بكميةِ كلِّ براندٍ
      // على حدة بينما شارته حكمٌ على المنتج كلّه (#25) — رقمان لسؤالٍ واحد في
      // الصفّ ذاته. والخادم يُكمل عائلات كل صفحةٍ (`complete_families=1`) فلا
      // يُبنى صفُّ منتجٍ من بعض براندَاته.
      const printableRows = groupProductsByFamily(all).map(
        (g) => (g.familyId == null ? g.members[0] : buildFamilyRow(g.members)),
      );
      const rowsHtml = printableRows.map((p) => {
        const name = esc(p.name_ar || p.name_en || p.sku);
        const qty = Number(p.quantity_on_hand);
        const avgCost = formatMoney(p.avg_cost);
        const cls = p.stock_status === "out_of_stock" ? "danger" : p.stock_status === "low_stock" ? "warn" : "";
        return `
          <tr>
            <td class="num" style="direction: ltr">${esc(p.sku)}</td>
            <td>${name}</td>
            <td>${esc(p.category_name || "—")}</td>
            <td class="num ${cls}" style="direction: ltr">${qty}</td>
            <td class="num" style="direction: ltr">${avgCost}</td>
            <td class="num" style="direction: ltr">${p.min_stock_level ?? "—"}</td>
            <td class="${cls}">${STATUS_LABEL[p.stock_status]}</td>
          </tr>`;
      }).join("");

      const html = `
        <html dir="rtl" lang="ar">
          <head>
            <title>تقرير المنتجات - ${today}</title>
            <style>
              body { font-family: system-ui, -apple-system, sans-serif; padding: 20px; color: #111827; }
              h2 { text-align: center; color: #1857a4; margin-bottom: 5px; }
              .subtitle { text-align: center; color: #6b7280; margin-bottom: 20px; font-size: 14px; }
              table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
              th, td { border: 1px solid #e5e7eb; padding: 10px 12px; text-align: right; }
              th { background-color: #f9fafb; color: #374151; font-weight: 600; }
              tr:nth-child(even) { background-color: #fcfcfd; }
              .num { text-align: left; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
              .danger { color: #dc2626; font-weight: bold; }
              .warn { color: #b8800a; font-weight: bold; }
              @media print { body { padding: 0; } @page { margin: 1.5cm; } }
            </style>
          </head>
          <body>
            <h2>تقرير المنتجات</h2>
            <div class="subtitle">${subset} · العدد: ${printableRows.length} · التاريخ: ${today}</div>
            <table>
              <thead>
                <tr>
                  <th>رقم المنتج</th><th>اسم المنتج</th><th>التصنيف</th>
                  <th>الكمية</th><th>متوسط التكلفة</th><th>الحد الأدنى</th><th>الحالة</th>
                </tr>
              </thead>
              <tbody>${rowsHtml}</tbody>
            </table>
            <script>window.onload = () => { window.print(); };</script>
          </body>
        </html>`;

      printWindow.document.open();
      printWindow.document.write(html);
      printWindow.document.close();
      clientLogger.info("items.export_pdf", { status: status || "all", count: all.length });
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر التصدير");
    } finally {
      setExporting(false);
    }
  }, []);

  const allColumns: DenseColumn<SqlProduct>[] = [
    // W8: الأعمدة القيادية بالترتيب المطلوب — الكمية المشتراة (الوارد التراكمي)،
    // ثم الكمية المتبقية، ثم عمود الاسم (المثبَّت)، ثم متوسط المبيعات الشهري.
    { key: "purchased", header: "الكمية المشتراة", width: "100px", align: "center", numeric: true,
      // الوارد التراكمي (كل حركات IN) من StockMovement — منقّط خادمياً (لا N+1).
      render: (p) => <span title="الوارد التراكمي (كل حركات الإدخال IN)">{p.purchased_qty != null ? formatQuantity(p.purchased_qty) : "—"}</span> },
    { key: "qty", header: "الكمية المتبقية", width: "90px", align: "center", numeric: true, sortable: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = qty <= 0;
        return <span title="المخزون الحالي" style={low ? { color: "var(--ktra-danger, #c00)", fontWeight: 600 } : {}}>{formatQuantity(qty)}</span>;
      }
    },
    // T-RESERVE: المحجوز لطلبيات الزبائن المؤكَّدة السارية — البيع من «المتاح» لا
    // من الرصيد، فبقاؤه مخفياً كان يجعل الحجز غير مرئي في شاشة المنتجات.
    { key: "reserved", header: "محجوز", width: "80px", align: "center", numeric: true,
      render: (p) => {
        const reserved = Number(p.reserved_quantity || 0);
        if (!reserved) return <span className="text-[var(--ktra-ink-soft)]">—</span>;
        return (
          <span title="محجوز بطلبيات زبائن مؤكَّدة سارية"
            style={{ color: "var(--ktra-warn, #b06800)", fontWeight: 600 }}>
            {formatQuantity(reserved)}
          </span>
        );
      }
    },
    { key: "available", header: "المتاح", width: "80px", align: "center", numeric: true,
      render: (p) => (
        <span title="المتاح للبيع = الكمية المتبقية − المحجوز">
          {formatQuantity(p.available_quantity ?? p.quantity_on_hand)}
        </span>
      )
    },
    { key: "name_ar", header: "اسم المنتج", sortable: true, render: (p) => {
      /* T-PRODUCT M2: الاسم كان زرّاً أزرق مسطَّراً — يقول «رابط» فلا يتوقّع منه
         أحدٌ تحريراً، ولا كان ثمّة طريقٌ لتعديله دون مغادرة الجدول. الآن نصٌّ
         عاديّ يُحرَّر في مكانه (نقرتان أو F2)، والمغادرةُ إلى تبويبٍ مستقل
         أيقونةٌ صريحة بجانبه.
         والنقرة المفردة تُركِّز ولا تفتح شيئاً: لو ظلّت تنقُل لكان قولنا «ليس
         رابطاً» كذباً. المنافذ الثلاثة الأخرى للكرت الكامل (نقرتان على صفٍّ
         آخر · عمود القلم · «تعديل» في الشجرة) لم تُمَسّ. */
      const editing = nameEdit?.id === p.id;
      return (
      <span
        className="group inline-flex w-full min-w-0 items-center gap-1"
        /* مرساةُ قائمة السياق على الحاوي لا على الزرّ: الزرّ يُستبدل بحقلٍ أثناء
           التحرير، و`contextMenuTargets` يصعد بـ`closest` — فلولا النقل لماتت
           قائمة السياق أثناء التحرير وحده. */
        data-ctx-item-id={p.id}
        data-ctx-item-name={p.display_name || p.name_ar || p.name_en || ""}
      >
        {editing ? (
          <input
            ref={nameInputRef}
            autoFocus
            className="ktra-input min-w-0 flex-1"
            value={nameEdit.draft}
            disabled={nameEdit.saving}
            aria-label="تعديل اسم المنتج"
            aria-invalid={nameEdit.error ? true : undefined}
            title={nameEdit.error ?? undefined}
            onChange={(e) => setNameEdit((st) => (st ? { ...st, draft: e.target.value } : st))}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") { e.preventDefault(); void commitNameEdit(p); }
              else if (e.key === "Escape") { e.preventDefault(); setNameEdit(null); }
            }}
            /* Tab وفقدان التركيز يحفظان إن تغيّر شيء — عُرف الجداول. */
            onBlur={() => { void commitNameEdit(p); }}
          />
        ) : (
          <button
            type="button"
            className="min-w-0 flex-1 cursor-text truncate rounded px-1 text-start hover:bg-[var(--color-surface-3)]"
            title="نقرتان أو F2 لتعديل الاسم"
            onClick={(e) => e.stopPropagation()}
            /* بلا إيقاف الانتشار تفتح الإيماءةُ الواحدة المحرِّرَ الكامل أيضاً
               (نقرتا الصفّ)، فيُلغى تركيب الحقل أثناء الكتابة. */
            onDoubleClick={(e) => { e.stopPropagation(); beginNameEdit(p); }}
            onKeyDown={(e) => {
              if (e.key === "F2") { e.preventDefault(); e.stopPropagation(); beginNameEdit(p); }
            }}
          >
            {p.display_name || p.name_ar || p.name_en || "—"}
          </button>
        )}
        <button
          type="button"
          className="ktra-iconbtn opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
          title="فتح في تبويب مستقل"
          aria-label="فتح في تبويب مستقل"
          onClick={(e) => { e.stopPropagation(); openInNewTab(productProfilePath(p.id)); }}
        ><ExternalLink className="h-3 w-3" /></button>
      </span>
      );
    } },
    { key: "avg_monthly", header: "متوسط البيع الشهري", width: "120px", align: "center", numeric: true,
      // صافي (OUT − RETURN_IN) خلال 90 يوماً ÷ 3.
      render: (p) => <span title="متوسط المبيعات الشهري = صافي البيع (بعد المرتجعات) خلال آخر 90 يوماً ÷ 3">{p.avg_monthly_sales != null ? formatQuantity(p.avg_monthly_sales) : "—"}</span> },
    { key: "sku", header: "رقم المنتج", width: "110px", sortable: true, render: (p) => (
        <b title={p.sku} style={{ display: "inline-block", maxWidth: "90px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", verticalAlign: "bottom" }}>
          {p.sku}
        </b>
    ) },
    { key: "avg_cost", header: "متوسط التكلفة", width: "110px", align: "center", numeric: true, sortable: true,
      render: (p) => <>{fmt(p.avg_cost)}</> },
    // كرت المنتج: سعر البيع المحفوظ — يُقرأ بجانب التكلفة بلا فتح الكرت.
    { key: "sale_price", header: "سعر البيع", width: "100px", align: "center", numeric: true, sortable: true,
      render: (p) => (
        <span title="سعر البيع الافتراضي المحفوظ على المنتج">
          {p.sale_price != null && p.sale_price !== "" ? formatMoney(p.sale_price) : "—"}
        </span>
      ) },
    { key: "min", header: "الحد الأدنى", width: "90px", align: "center", sortable: true,
      render: (p) => <>{p.min_stock_level ?? "—"}</> },
    { key: "max", header: "الحد الأقصى", width: "90px", align: "center", sortable: true,
      render: (p) => <>{p.max_stock_level ?? "—"}</> },
    // T-REORDER: «الصنف» يجمع الموديلات المتبادلة — وفراغه يعني ألّا بديل يُقترح
    // في الفاتورة ولا قرار «مؤجَّل» في تقرير التجديد. يُعيَّن من كرت المنتج، أو
    // للمحدَّد دفعةً واحدة من شاشة «أرصدة المخزون».
    { key: "grp", header: "الصنف", width: "120px",
      render: (p) => p.variant_group
        ? <>{p.variant_group}</>
        : <span style={{ color: "var(--ktra-ink-soft)" }}
            title="بلا صنف — لن تظهر له بدائل في الفاتورة">—</span> },
    { key: "status", header: "الحالة", width: "80px", align: "center",
      render: (p) => {
        if (p.stock_status === "out_of_stock") return <span style={{ color: "var(--ktra-danger,#c00)" }}>نفذ</span>;
        if (p.stock_status === "low_stock") return <span style={{ color: "var(--ktra-warn,#b8800a)" }}>منخفض</span>;
        if (p.stock_status === "overstock") return <span style={{ color: "var(--ktra-warn,#b8800a)" }}>فائض</span>;
        return <span style={{ color: "var(--ktra-ok,#267346)" }}>متوفر</span>;
      }
    },
    { key: "edit", header: "", width: "70px", align: "center",
      render: (p) => (
        <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
          <button className="ktra-iconbtn" title="تعديل"
            onClick={(e) => { e.stopPropagation(); setEditId(p.id); setDuplicateId(null); setView("form"); }}>
            <Edit2 className="h-3.5 w-3.5" />
          </button>
          <button className="ktra-iconbtn text-indigo-600 hover:bg-indigo-50" title="إضافة براند آخر (تكرار)"
            onClick={(e) => { e.stopPropagation(); setDuplicateId(p.id); setEditId(null); setView("form"); }}>
            <Copy className="h-3.5 w-3.5" />
          </button>
        </div>
      )
    },
  ];

  /* T-SIMPL2: أعمدة التحليل (المشتراة · متوسط البيع الشهري) وإعداد الكتالوج
     (الحدّ الأقصى · الصنف) تُطوى في الوضع السهل. و«محجوز/المتاح» يعودان لحظة
     يوجد حجزٌ فعلاً — رصيدٌ لا يُباع منه لا يُخفى عن بائعه. */
  /* القائمة مرقَّمة، و`products` صفحةٌ واحدة: بلا تثبيت تظهر الأعمدة في صفحة
     وتختفي في التي تليها — جدولٌ يتراقص تحت يد المستخدم. */
  const anyReserved = useKeepOnce(products.some((p) => Number(p.reserved_quantity || 0) > 0));
  const columns = maskColumns(
    allColumns,
    "items-management",
    anyReserved ? ["reserved", "available"] : [],
  );

  if (view === "form") {
    return (
      <ItemForm
        productId={editId}
        duplicateId={duplicateId}
        products={products}
        onSaved={() => { reload(); setView("list"); setEditId(null); setDuplicateId(null); }}
        onCancel={() => { setView("list"); setEditId(null); setDuplicateId(null); }}
      />
    );
  }

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", padding: "8px 12px" }}>
      {/* Tabs Header */}
      <div style={{ display: "flex", gap: "16px", borderBottom: "1px solid var(--ktra-border)", marginBottom: "8px" }}>
        <button
          onClick={() => setActiveTab("products")}
          style={{
            padding: "8px 16px",
            borderBottom: activeTab === "products" ? "2px solid var(--ktra-primary)" : "2px solid transparent",
            color: activeTab === "products" ? "var(--ktra-primary)" : "var(--ktra-ink)",
            fontWeight: activeTab === "products" ? "bold" : "normal",
            background: "none",
            borderTop: "none", borderLeft: "none", borderRight: "none",
            display: "flex", alignItems: "center", gap: "6px", cursor: "pointer"
          }}
        >
          <Package className="h-4 w-4" /> المنتجات
        </button>
        <button
          onClick={() => setActiveTab("categories")}
          style={{
            padding: "8px 16px",
            borderBottom: activeTab === "categories" ? "2px solid var(--ktra-primary)" : "2px solid transparent",
            color: activeTab === "categories" ? "var(--ktra-primary)" : "var(--ktra-ink)",
            fontWeight: activeTab === "categories" ? "bold" : "normal",
            background: "none",
            borderTop: "none", borderLeft: "none", borderRight: "none",
            display: "flex", alignItems: "center", gap: "6px", cursor: "pointer"
          }}
        >
          <Boxes className="h-4 w-4" /> التصنيفات
        </button>
      </div>

      {activeTab === "categories" ? (
        <div style={{ flex: 1, overflow: "hidden" }}>
          <CategoriesManagement />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <strong style={{ fontSize: "var(--ktra-fs-title, 14px)", color: "var(--ktra-ink)" }}>
              إدارة المنتجات
            </strong>
            {/* P0-12: الإجمالي من الخادم (count) لا من طول الصفحة المعروضة. */}
            <span className="ktra-status-item">الإجمالي: <b>{total}</b></span>
        {/* Phase 2 wiring — freshness/cache indicator */}
        <StalenessBadge updatedAt={lastSync} />
        {fromCache && (
          <span
            role="status"
            aria-live="polite"
            className="text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800"
            title="تعذّر الاتصال — يتم عرض آخر نسخة محفوظة محلياً"
          >
            من الذاكرة المحلية
          </span>
        )}
        <div style={{ flex: 1 }} />
        <input className="ktra-input" style={{ width: 200 }}
          placeholder="بحث SKU / الاسم…"
          value={search} onChange={(e) => { setSearch(e.target.value); }} />
        {/* فلتر حالة المخزون: الكل / نفذ / منخفض / متوفر (خادمي) */}
        <select className="ktra-input" style={{ width: 130 }}
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value as StockStatus); }}
          title="فلترة حسب حالة المخزون">
          <option value="">كل الحالات</option>
          <option value="out_of_stock">نفذ</option>
          <option value="low_stock">كمية منخفضة</option>
          <option value="overstock">فائض</option>
          <option value="in_stock">متوفر</option>
        </select>
        {/* تصدير بخيارات: الكل / ما نفذ / المنخفضة */}
        <div style={{ position: "relative" }}>
          <button className="ktra-toolbtn" disabled={exporting}
            onClick={() => setExportMenuOpen((o) => !o)} title="تصدير PDF للطباعة">
            <Printer className="h-4 w-4" /> {exporting ? "جارٍ التحضير…" : "تصدير PDF"}
          </button>
          {exportMenuOpen && (
            <div role="menu"
              style={{
                position: "absolute", insetInlineStart: 0, top: "calc(100% + 4px)", zIndex: 10,
                background: "var(--ktra-surface, #fff)", border: "1px solid var(--ktra-border)",
                borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,.12)", minWidth: 170,
              }}>
              <button className="ktra-menu-item" style={exportItemStyle} onClick={() => exportProducts("")}>تصدير الكل</button>
              <button className="ktra-menu-item" style={exportItemStyle} onClick={() => exportProducts("out_of_stock")}>المنتجات التي نفذت</button>
              <button className="ktra-menu-item" style={exportItemStyle} onClick={() => exportProducts("low_stock")}>الكمية المنخفضة</button>
            </div>
          )}
        </div>
        {/* T-N3: مبدّل عرض الشجرة/الجدول */}
        <button
          className="ktra-toolbtn"
          onClick={() => setDisplayMode(displayMode === "tree" ? "table" : "tree")}
          title={displayMode === "tree" ? "عرض كجدول" : "عرض كشجرة تصنيفات"}
        >
          {displayMode === "tree" ? <Table2 className="h-4 w-4" /> : <ListTree className="h-4 w-4" />}
          {displayMode === "tree" ? " جدول" : " شجرة"}
        </button>
        {/* #24: الضمّ الجماعي — عدّة منتجاتٍ هي في الحقيقة براندات منتجٍ واحد
            تحت منتجٍ واحدٍ يختاره المستخدم. متاحٌ في عرض الجدول وحده (عمود
            التحديد على `GroupedItemsTable`، لا الشجرة الخام). */}
        {displayMode !== "tree" && (
          <>
            <button
              type="button"
              className="ktra-toolbtn"
              onClick={() => {
                setMergeMode((m) => {
                  if (m) setMergeSelected(new Map());
                  return !m;
                });
              }}
              title="تحديد منتجات لضمّها تحت منتج واحد"
            >
              <Merge className="h-4 w-4" /> {mergeMode ? "إنهاء التحديد" : "ضمّ منتجات"}
            </button>
            {mergeMode && (
              <button
                type="button"
                className="ktra-btn ktra-btn-primary"
                disabled={mergeSelected.size < 2}
                onClick={() => setMergeModalOpen(true)}
                title={mergeSelected.size < 2 ? "حدّد منتجين على الأقل" : undefined}
              >
                ضمّ المحدَّد ({mergeSelected.size})
              </button>
            )}
          </>
        )}
        <button className="ktra-toolbtn" onClick={() => reload()} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button className="ktra-toolbtn" onClick={() => { setEditId(null); setDuplicateId(null); setView("form"); }} title="إضافة منتج (Ctrl+Ins)">
          <Plus className="h-4 w-4" /> إضافة
        </button>
      </div>

      {err && <div className="ktra-banner ktra-banner--err">{err}</div>}

      {/* #24: التراجع يبقى في متناول اليد بعد الضمّ — لا وسيلة API فقط. يبقى
          ظاهراً حتى يُغلقه المستخدم صراحةً أو يتراجع، لا مؤقّتاً كالتوست. */}
      {lastMerge && (
        <div className="ktra-banner ktra-banner--ok">
          <span className="flex-1">
            تمّ ضمّ {lastMerge.mergedCount} منتجاً تحت «{lastMerge.targetName}».
          </span>
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={undoingMerge}
            onClick={() => void handleUndoMerge()}
          >
            <Undo2 className="h-4 w-4" /> {undoingMerge ? "جارٍ التراجع…" : "تراجع"}
          </button>
          <button
            type="button"
            className="ktra-iconbtn"
            onClick={() => setLastMerge(null)}
            aria-label="إغلاق"
            title="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {displayMode === "tree" ? (
        // T-N3: شجرة التصنيفات/المنتجات (نفس مكوّن شجرة المنتجات في الفواتير).
        // نقرة مفردة على منتج → بطاقته؛ نقرة مزدوجة/اختيار → تعديله.
        <div className="flex min-h-0 flex-1 gap-2 overflow-hidden">
          <InvoiceCategoryTree
            items={products.map((p) => ({
              ...(p as unknown as Item),
              id: String(p.id),
              // اسم الورقة = اسم العرض (الاسم + البراند) مع احتياطي.
              name: p.display_name || p.name_ar || p.name_en || p.sku || "",
              group_key: p.group_key,
              display_name: p.display_name,
              has_group: p.has_group,
              categoryId: (p as unknown as { category?: number | string }).category ?? "",
            })) as unknown as Item[]}
            onShowCard={(it) => setPreview({ kind: "product", id: Number(it.id), name: it.name || "" })}
            onShowGroup={(ids, name, categoryId) =>
              setPreview({
                kind: "group", ids: ids.map(Number), name,
                categoryId: categoryId == null ? undefined : Number(categoryId),
              })}
            onPickItem={(it) => { setEditId(Number(it.id)); setView("form"); }}
            onItemCreated={() => reload()}
          />
          {/* الفراغ الذي كان بجانب الشجرة: بطاقة ما هو محدَّد فيها. */}
          <div className="min-w-0 flex-1 overflow-hidden rounded border border-[var(--ktra-border)] bg-[var(--ktra-panel)]">
            {preview?.kind === "product" ? (
              <ProductTreePane
                key={`p${preview.id}`}
                productId={preview.id}
                productName={preview.name}
                onEdit={() => { setEditId(preview.id); setDuplicateId(null); setView("form"); }}
              />
            ) : preview?.kind === "group" ? (
              <GroupTreePane
                key={`g${preview.categoryId ?? preview.ids.join(",")}`}
                ids={preview.ids}
                groupName={preview.name}
                categoryId={preview.categoryId}
              />
            ) : (
              <div className="flex h-full items-center justify-center p-6 text-center text-[var(--ktra-ink-soft)]">
                اختر منتجاً من الشجرة لتظهر بطاقته هنا، أو تصنيفاً ليظهر كرته المجمّع — التسعير والمخزون والفواتير وحركة المنتج.
              </div>
            )}
          </div>
        </div>
      ) : (
        // تجميع البراندات: عقدة «مجموعة» قابلة للطيّ بالجدول + كرت مجمّع (DRY مع الشجرة).
        <GroupedItemsTable
          columns={columns}
          rows={products} // search is server-side now
          categories={treeCategories}
          getRowKey={(p) => p.id}
          loading={loading}
          emptyHint="لا توجد منتجات"
          onRowDoubleClick={(p) => { setEditId(p.id); setView("form"); }}
          onShowGroup={(ids, name, categoryId) =>
            openInNewTab(productGroupPath({ name, categoryId, ids }))}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={(key, dir) => { setSortKey(key); setSortDir(dir); }}
          selection={mergeMode ? { selectedIds: mergeSelectedIds, onToggle: toggleMergeSelected } : undefined}
          // البحث وحده يُسقط التجميع إلى صفوف براندات: هو مسار الضمّ (اكتب
          // المقاس ← تظهر النسخ المكرّرة صفّاً صفّاً ← أشّر واضمم)، ومربّع
          // التحديد لا يحمله إلا صفّ البراند. أمّا فلتر الحالة فخرج من هذا
          // بعد #28: صار حكماً على المنتج فيُعيد **كل** براندات المنتج
          // المطابق، فصفّ المنتج مكتملٌ ولا يدّعي مجموعاً ناقصاً.
          brandFilterActive={Boolean(search)}
        />
      )}

      <MergeProductsModal
        isOpen={mergeModalOpen}
        onClose={() => setMergeModalOpen(false)}
        candidates={mergeCandidates}
        onMerged={handleMerged}
      />

      {/* المرحلة 5 / P0-12: تنقّل الصفحات — للعرض الجدولي وحده (الشجري يجمّع
          المجموعة كاملةً فلا معنى لتصفّحه). يظهر فقط عند وجود أكثر من صفحة. */}
      {displayMode !== "tree" && (page > 1 || hasNext) && (
        <div
          style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            gap: 12, padding: "6px 0",
          }}
        >
          <button
            className="ktra-btn"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            السابق
          </button>
          <span className="ktra-status-item">
            صفحة <b>{page}</b> من <b>{Math.max(1, Math.ceil(total / pageSize))}</b>
          </span>
          <button
            className="ktra-btn"
            disabled={!hasNext || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            التالي
          </button>
        </div>
      )}
        </div>
      )}
    </div>
  );
};
