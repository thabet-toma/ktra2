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

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setProducts((await inventoryApi.getProducts()) as SqlProduct[]);
    } catch (e: unknown) {
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
