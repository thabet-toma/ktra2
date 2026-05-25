/**
 * N5-T3 — ItemsManagement (L4) — AseelDenseTable للأصناف
 * يستخدم SQL products من inventoryApi (لا Firestore).
 */
import React, { useEffect, useState, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct } from "../../types/inventory";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { Plus, RefreshCw, Edit2 } from "lucide-react";
import { ItemFormAseel } from "./ItemFormAseel";
import { StalenessBadge } from "../offline";
import db from "../../services/offline/db";

const fmt = (n: number | string) =>
  Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

type View = "list" | "form";

export const ItemsManagement: React.FC<{ user?: unknown }> = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>("list");
  const [editId, setEditId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  // Phase 2 wiring: track when the list was last refreshed from the server,
  // and whether the current render is being served from the offline cache.
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [fromCache, setFromCache] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const rows = (await inventoryApi.getProducts()) as SqlProduct[];
      setProducts(rows);
      const now = new Date().toISOString();
      setLastSync(now);
      setFromCache(false);
      // Mirror into Dexie so the offline fallback below has fresh data.
      try {
        for (const p of rows) {
          await db.products.put({
            id: p.id,
            tenant_id: (p as { tenant?: number }).tenant ?? 0,
            sku: p.sku,
            name_ar: p.name_ar || "",
            data: JSON.stringify(p),
            updated_at: now,
          });
        }
        await db.cache_meta.put({ key: "products:list", updated_at: now });
      } catch { /* IndexedDB unavailable in private mode — non-fatal */ }
    } catch (e: unknown) {
      // Network failed — try to serve the last cached snapshot so the screen
      // stays usable offline. Surface the staleness via the badge.
      try {
        const cached = await db.products.toArray();
        if (cached.length > 0) {
          setProducts(cached.map((c) => JSON.parse(c.data) as SqlProduct));
          const meta = await db.cache_meta.get("products:list");
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
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = products.filter((p) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      p.sku.toLowerCase().includes(s) ||
      (p.name_ar || "").toLowerCase().includes(s) ||
      (p.name_en || "").toLowerCase().includes(s)
    );
  });

  const columns: DenseColumn<SqlProduct>[] = [
    { key: "sku", header: "رقم الصنف", width: "110px", render: (p) => <b>{p.sku}</b> },
    { key: "name_ar", header: "اسم الصنف", render: (p) => <>{p.name_ar || p.name_en || "—"}</> },
    { key: "cat", header: "التصنيف", width: "140px", render: (p) => <>{p.category_name || "—"}</> },
    { key: "qty", header: "الكمية", width: "80px", align: "center", numeric: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = qty <= 0;
        return <span style={low ? { color: "var(--aseel-danger, #c00)", fontWeight: 600 } : {}}>{fmt(qty)}</span>;
      }
    },
    { key: "avg_cost", header: "متوسط التكلفة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(p.avg_cost)}</> },
    { key: "min", header: "الحد الأدنى", width: "90px", align: "center",
      render: (p) => <>{p.min_stock_level ?? "—"}</> },
    { key: "status", header: "الحالة", width: "80px", align: "center",
      render: (p) => {
        if (p.stock_status === "out_of_stock") return <span style={{ color: "var(--aseel-danger,#c00)" }}>نفذ</span>;
        if (p.stock_status === "low_stock") return <span style={{ color: "var(--aseel-warn,#b8800a)" }}>منخفض</span>;
        return <span style={{ color: "var(--aseel-ok,#267346)" }}>متوفر</span>;
      }
    },
    { key: "edit", header: "", width: "40px", align: "center",
      render: (p) => (
        <button className="aseel-iconbtn" title="تعديل"
          onClick={(e) => { e.stopPropagation(); setEditId(p.id); setView("form"); }}>
          <Edit2 className="h-3 w-3" />
        </button>
      )
    },
  ];

  if (view === "form") {
    return (
      <ItemFormAseel
        productId={editId}
        products={products}
        onSaved={() => { load(); setView("list"); setEditId(null); }}
        onCancel={() => { setView("list"); setEditId(null); }}
      />
    );
  }

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }} data-skin="aseel">
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          إدارة الأصناف
        </strong>
        <span className="aseel-status-item">الإجمالي: <b>{products.length}</b></span>
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
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <button className="aseel-toolbtn" onClick={load} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button className="aseel-toolbtn" onClick={() => { setEditId(null); setView("form"); }} title="إضافة صنف (Ctrl+Ins)">
          <Plus className="h-4 w-4" /> إضافة
        </button>
      </div>

      {err && <div className="aseel-banner aseel-banner--err">{err}</div>}

      <AseelDenseTable<SqlProduct>
        columns={columns}
        rows={filtered}
        getRowKey={(p) => p.id}
        loading={loading}
        emptyHint="لا توجد أصناف"
        onRowDoubleClick={(p) => { setEditId(p.id); setView("form"); }}
      />
    </div>
  );
};
