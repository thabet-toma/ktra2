/**
 * N5-T3 — ItemsManagement (L4) — AseelDenseTable للأصناف
 * يستخدم SQL products من inventoryApi (لا Firestore).
 */
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct } from "../../types/inventory";
import { type DenseColumn } from "../aseel/AseelDenseTable";
import { GroupedItemsTable, type TreeCategory } from "./GroupedItemsTable";
import { Plus, RefreshCw, Edit2, Package, Boxes, ListTree, Table2, Printer, Copy, ExternalLink, FolderTree } from "lucide-react";
import { ItemFormAseel } from "./ItemFormAseel";
import { useProductInsights, useGroupInsights } from "./ProductInsightTabs";
import { AseelTabs, type AseelTab } from "../aseel";
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

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة عبر المُنسّق الموحّد.
const fmt = (n: number | string) => formatMoney(n, "0");

type View = "list" | "form";
type StockStatus = "" | "out_of_stock" | "low_stock" | "in_stock";

// مفتاح عمود الجدول → حقل الترتيب الخادمي (OrderingFilter).
const ORDER_FIELD: Record<string, string> = {
  sku: "sku",
  name_ar: "name_ar",
  qty: "quantity_on_hand",
  avg_cost: "avg_cost",
  sale_price: "sale_price",
  min: "min_stock_level",
};

const STATUS_LABEL: Record<Exclude<StockStatus, "">, string> = {
  out_of_stock: "نفذ",
  low_stock: "منخفض",
  in_stock: "متوفر",
};

const exportItemStyle: React.CSSProperties = {
  display: "block", width: "100%", textAlign: "start", padding: "8px 12px",
  background: "none", border: "none", cursor: "pointer", color: "var(--aseel-ink)",
};

/**
 * البطاقة الجانبية للعرض الشجري — العرض الشجري كان يشغل شريط 240px ويترك بقية
 * عرض الشاشة بياضاً، والنقر على منتج (أو تصنيف) يقذف المستخدم إلى تبويب جديد.
 * صار الفراغ بطاقةَ ما هو محدَّد في الشجرة، على نمط شجرة الحسابات: شريط شجرة
 * + بطاقة السجل المحدَّد.
 *
 * إطارٌ واحد للحالتين (صنف مفرد · تصنيف مجمّع): الرأس هوية وأزرار، وتحته
 * تبويبات الكرت نفسها التي تعرضها الصفحة الكاملة — لا نسخة ثانية منها.
 */
const TreePaneFrame: React.FC<{
  icon: React.ReactNode;
  title: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  tabs: AseelTab[];
}> = ({ icon, title, badge, actions, tabs }) => (
  <div className="flex h-full min-h-0 flex-col">
    <div className="flex items-center gap-2 border-b border-[var(--aseel-border)] px-2 py-1.5">
      {icon}
      <b className="truncate text-[var(--aseel-ink)]" title={title}>{title}</b>
      {badge}
      <div className="flex-1" />
      {actions}
    </div>
    <div className="min-h-0 flex-1 overflow-auto">
      <AseelTabs tabs={tabs} />
    </div>
  </div>
);

/**
 * بطاقة الصنف المفرد. التركيب بمفتاح `key` عند المستدعي: كل اختيار يُعيد
 * التركيب، فنتائج طلبٍ سابق بطيء تسقط على مكوّن مفكوك بدل أن تكتب فوق
 * بيانات الصنف الجديد.
 */
const ProductTreePane: React.FC<{
  productId: number;
  productName: string;
  onEdit: () => void;
}> = ({ productId, productName, onEdit }) => {
  const { profile, tabs } = useProductInsights(productId);
  const title = profile?.name || productName || `صنف #${productId}`;
  return (
    <TreePaneFrame
      icon={<Package className="h-4 w-4 shrink-0 text-[var(--aseel-ink-soft)]" />}
      title={title}
      badge={profile?.sku ? <span className="aseel-status-item" dir="ltr">{profile.sku}</span> : null}
      tabs={tabs}
      actions={
        <>
          <button type="button" className="aseel-toolbtn" onClick={onEdit} title="تعديل هذا الصنف">
            <Edit2 className="h-4 w-4" /> تعديل
          </button>
          <button
            type="button"
            className="aseel-toolbtn"
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

/** بطاقة التصنيف: الكرت المجمّع لكل الأصناف تحته (وأحفاده).
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
      badge={<span className="aseel-status-item">{count} صنف</span>}
      tabs={tabs}
      actions={
        <button
          type="button"
          className="aseel-toolbtn"
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

/** ما هو محدَّد في الشجرة: صنفٌ مفرد أو تصنيفٌ مجمّع. */
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
  // شجرة التصنيفات (أي عمق) لعرض الجدول الشجري + الكرت المجمّع لكل تصنيف.
  const [treeCategories, setTreeCategories] = useState<TreeCategory[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>("list");
  // T-N3: عرض الأصناف كشجرة تصنيفات (مثل شجرة المنتجات في الفواتير) أو كجدول.
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
  // جدول الأصناف: فلتر حالة المخزون + ترتيب حسب العمود (خادمي) + قائمة التصدير.
  const [statusFilter, setStatusFilter] = useState<StockStatus>("");
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const pageSize = 50;

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
      // صنفاً، ويُعيد ذلك كاملاً بعد كل دورة بحث (debounce 250ms).
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
          ...params, page, page_size: pageSize,
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

  // تصدير PDF للطباعة بخيارات: الكل / ما نفذ / المنخفضة — يجلب كل الصفحات المطابقة
  // (لا الصفحة الحالية فقط) ثم يفتح نافذة طباعة بنفس نمط تقرير أرصدة المخزون (DRY).
  const exportProducts = useCallback(async (status: StockStatus) => {
    setExportMenuOpen(false);
    setExporting(true);
    try {
      const all: SqlProduct[] = [];
      let pg = 1;
      for (;;) {
        const params: Record<string, string | number> = { page: pg, page_size: 200 };
        if (status) params.stock_status = status;
        const data = await inventoryApi.getProducts(params);
        const rows = (Array.isArray(data) ? data : (data.results ?? [])) as SqlProduct[];
        all.push(...rows);
        const count = (Array.isArray(data) ? rows.length : (data.count ?? all.length)) as number;
        if (rows.length === 0 || all.length >= count) break;
        pg++;
      }
      if (all.length === 0) { setErr("لا توجد أصناف للتصدير بهذا الخيار."); return; }

      const printWindow = window.open("", "_blank");
      if (!printWindow) { setErr("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة"); return; }

      const today = new Date().toISOString().slice(0, 10);
      const subset = status ? `الأصناف: ${STATUS_LABEL[status]}` : "كل الأصناف";
      const esc = (v: unknown) => String(v ?? "—")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const rowsHtml = all.map((p) => {
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
            <title>تقرير الأصناف - ${today}</title>
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
            <h2>تقرير الأصناف</h2>
            <div class="subtitle">${subset} · العدد: ${all.length} · التاريخ: ${today}</div>
            <table>
              <thead>
                <tr>
                  <th>رقم الصنف</th><th>اسم الصنف</th><th>التصنيف</th>
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

  const columns: DenseColumn<SqlProduct>[] = [
    // W8: الأعمدة القيادية بالترتيب المطلوب — الكمية المشتراة (الوارد التراكمي)،
    // ثم الكمية المتبقية، ثم عمود الاسم (المثبَّت)، ثم متوسط المبيعات الشهري.
    { key: "purchased", header: "الكمية المشتراة", width: "100px", align: "center", numeric: true,
      // الوارد التراكمي (كل حركات IN) من StockMovement — منقّط خادمياً (لا N+1).
      render: (p) => <span title="الوارد التراكمي (كل حركات الإدخال IN)">{p.purchased_qty != null ? formatQuantity(p.purchased_qty) : "—"}</span> },
    { key: "qty", header: "الكمية المتبقية", width: "90px", align: "center", numeric: true, sortable: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = qty <= 0;
        return <span title="المخزون الحالي" style={low ? { color: "var(--aseel-danger, #c00)", fontWeight: 600 } : {}}>{formatQuantity(qty)}</span>;
      }
    },
    // T-RESERVE: المحجوز لطلبيات الزبائن المؤكَّدة السارية — البيع من «المتاح» لا
    // من الرصيد، فبقاؤه مخفياً كان يجعل الحجز غير مرئي في شاشة الأصناف.
    { key: "reserved", header: "محجوز", width: "80px", align: "center", numeric: true,
      render: (p) => {
        const reserved = Number(p.reserved_quantity || 0);
        if (!reserved) return <span className="text-[var(--aseel-ink-soft)]">—</span>;
        return (
          <span title="محجوز بطلبيات زبائن مؤكَّدة سارية"
            style={{ color: "var(--aseel-warn, #b06800)", fontWeight: 600 }}>
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
    { key: "name_ar", header: "اسم الصنف", sortable: true, render: (p) => (
      // FEAT-3: اسم الصنف يفتح بطاقة الصنف (الفواتير المرتبطة + دفتر الحركة).
      <button
        type="button"
        className="text-[var(--aseel-accent,#2563eb)] underline hover:opacity-80"
        title="عرض بطاقة الصنف"
        data-ctx-item-id={p.id}
        data-ctx-item-name={p.display_name || p.name_ar || p.name_en || ""}
        onClick={(e) => { e.stopPropagation(); openInNewTab(productProfilePath(p.id)); }}
      >
        {p.display_name || p.name_ar || p.name_en || "—"}
      </button>
    ) },
    { key: "avg_monthly", header: "متوسط البيع الشهري", width: "120px", align: "center", numeric: true,
      // صافي (OUT − RETURN_IN) خلال 90 يوماً ÷ 3.
      render: (p) => <span title="متوسط المبيعات الشهري = صافي البيع (بعد المرتجعات) خلال آخر 90 يوماً ÷ 3">{p.avg_monthly_sales != null ? formatQuantity(p.avg_monthly_sales) : "—"}</span> },
    { key: "sku", header: "رقم الصنف", width: "110px", sortable: true, render: (p) => (
        <b title={p.sku} style={{ display: "inline-block", maxWidth: "90px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", verticalAlign: "bottom" }}>
          {p.sku}
        </b>
    ) },
    { key: "avg_cost", header: "متوسط التكلفة", width: "110px", align: "center", numeric: true, sortable: true,
      render: (p) => <>{fmt(p.avg_cost)}</> },
    // كرت الصنف: سعر البيع المحفوظ — يُقرأ بجانب التكلفة بلا فتح الكرت.
    { key: "sale_price", header: "سعر البيع", width: "100px", align: "center", numeric: true, sortable: true,
      render: (p) => (
        <span title="سعر البيع الافتراضي المحفوظ على الصنف">
          {p.sale_price != null && p.sale_price !== "" ? formatMoney(p.sale_price) : "—"}
        </span>
      ) },
    { key: "min", header: "الحد الأدنى", width: "90px", align: "center", sortable: true,
      render: (p) => <>{p.min_stock_level ?? "—"}</> },
    { key: "status", header: "الحالة", width: "80px", align: "center",
      render: (p) => {
        if (p.stock_status === "out_of_stock") return <span style={{ color: "var(--aseel-danger,#c00)" }}>نفذ</span>;
        if (p.stock_status === "low_stock") return <span style={{ color: "var(--aseel-warn,#b8800a)" }}>منخفض</span>;
        return <span style={{ color: "var(--aseel-ok,#267346)" }}>متوفر</span>;
      }
    },
    { key: "edit", header: "", width: "70px", align: "center",
      render: (p) => (
        <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
          <button className="aseel-iconbtn" title="تعديل"
            onClick={(e) => { e.stopPropagation(); setEditId(p.id); setDuplicateId(null); setView("form"); }}>
            <Edit2 className="h-3.5 w-3.5" />
          </button>
          <button className="aseel-iconbtn text-indigo-600 hover:bg-indigo-50" title="إضافة براند آخر (تكرار)"
            onClick={(e) => { e.stopPropagation(); setDuplicateId(p.id); setEditId(null); setView("form"); }}>
            <Copy className="h-3.5 w-3.5" />
          </button>
        </div>
      )
    },
  ];

  if (view === "form") {
    return (
      <ItemFormAseel
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
      <div style={{ display: "flex", gap: "16px", borderBottom: "1px solid var(--aseel-border)", marginBottom: "8px" }}>
        <button
          onClick={() => setActiveTab("products")}
          style={{
            padding: "8px 16px",
            borderBottom: activeTab === "products" ? "2px solid var(--aseel-primary)" : "2px solid transparent",
            color: activeTab === "products" ? "var(--aseel-primary)" : "var(--aseel-ink)",
            fontWeight: activeTab === "products" ? "bold" : "normal",
            background: "none",
            borderTop: "none", borderLeft: "none", borderRight: "none",
            display: "flex", alignItems: "center", gap: "6px", cursor: "pointer"
          }}
        >
          <Package className="h-4 w-4" /> الأصناف
        </button>
        <button
          onClick={() => setActiveTab("categories")}
          style={{
            padding: "8px 16px",
            borderBottom: activeTab === "categories" ? "2px solid var(--aseel-primary)" : "2px solid transparent",
            color: activeTab === "categories" ? "var(--aseel-primary)" : "var(--aseel-ink)",
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
            <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
              إدارة الأصناف
            </strong>
            {/* P0-12: الإجمالي من الخادم (count) لا من طول الصفحة المعروضة. */}
            <span className="aseel-status-item">الإجمالي: <b>{total}</b></span>
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
        <input className="aseel-input" style={{ width: 200 }}
          placeholder="بحث SKU / الاسم…"
          value={search} onChange={(e) => { setSearch(e.target.value); }} />
        {/* فلتر حالة المخزون: الكل / نفذ / منخفض / متوفر (خادمي) */}
        <select className="aseel-input" style={{ width: 130 }}
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value as StockStatus); }}
          title="فلترة حسب حالة المخزون">
          <option value="">كل الحالات</option>
          <option value="out_of_stock">نفذ</option>
          <option value="low_stock">كمية منخفضة</option>
          <option value="in_stock">متوفر</option>
        </select>
        {/* تصدير بخيارات: الكل / ما نفذ / المنخفضة */}
        <div style={{ position: "relative" }}>
          <button className="aseel-toolbtn" disabled={exporting}
            onClick={() => setExportMenuOpen((o) => !o)} title="تصدير PDF للطباعة">
            <Printer className="h-4 w-4" /> {exporting ? "جارٍ التحضير…" : "تصدير PDF"}
          </button>
          {exportMenuOpen && (
            <div role="menu"
              style={{
                position: "absolute", insetInlineStart: 0, top: "calc(100% + 4px)", zIndex: 10,
                background: "var(--aseel-surface, #fff)", border: "1px solid var(--aseel-border)",
                borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,.12)", minWidth: 170,
              }}>
              <button className="aseel-menu-item" style={exportItemStyle} onClick={() => exportProducts("")}>تصدير الكل</button>
              <button className="aseel-menu-item" style={exportItemStyle} onClick={() => exportProducts("out_of_stock")}>الأصناف التي نفذت</button>
              <button className="aseel-menu-item" style={exportItemStyle} onClick={() => exportProducts("low_stock")}>الكمية المنخفضة</button>
            </div>
          )}
        </div>
        {/* T-N3: مبدّل عرض الشجرة/الجدول */}
        <button
          className="aseel-toolbtn"
          onClick={() => setDisplayMode(displayMode === "tree" ? "table" : "tree")}
          title={displayMode === "tree" ? "عرض كجدول" : "عرض كشجرة تصنيفات"}
        >
          {displayMode === "tree" ? <Table2 className="h-4 w-4" /> : <ListTree className="h-4 w-4" />}
          {displayMode === "tree" ? " جدول" : " شجرة"}
        </button>
        <button className="aseel-toolbtn" onClick={() => reload()} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button className="aseel-toolbtn" onClick={() => { setEditId(null); setDuplicateId(null); setView("form"); }} title="إضافة صنف (Ctrl+Ins)">
          <Plus className="h-4 w-4" /> إضافة
        </button>
      </div>

      {err && <div className="aseel-banner aseel-banner--err">{err}</div>}

      {displayMode === "tree" ? (
        // T-N3: شجرة التصنيفات/الأصناف (نفس مكوّن شجرة المنتجات في الفواتير).
        // نقرة مفردة على صنف → بطاقته؛ نقرة مزدوجة/اختيار → تعديله.
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
          <div className="min-w-0 flex-1 overflow-hidden rounded border border-[var(--aseel-border)] bg-[var(--aseel-panel)]">
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
              <div className="flex h-full items-center justify-center p-6 text-center text-[var(--aseel-ink-soft)]">
                اختر منتجاً من الشجرة لتظهر بطاقته هنا، أو تصنيفاً ليظهر كرته المجمّع — التسعير والمخزون والفواتير وحركة الصنف.
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
          emptyHint="لا توجد أصناف"
          onRowDoubleClick={(p) => { setEditId(p.id); setView("form"); }}
          onShowGroup={(ids, name, categoryId) =>
            openInNewTab(productGroupPath({ name, categoryId, ids }))}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={(key, dir) => { setSortKey(key); setSortDir(dir); }}
        />
      )}

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
            className="aseel-btn"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            السابق
          </button>
          <span className="aseel-status-item">
            صفحة <b>{page}</b> من <b>{Math.max(1, Math.ceil(total / pageSize))}</b>
          </span>
          <button
            className="aseel-btn"
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
