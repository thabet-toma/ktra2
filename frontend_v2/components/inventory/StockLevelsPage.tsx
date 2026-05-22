import React, { useEffect, useState, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct, StockSummaryResponse } from "../../types/inventory";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { RefreshCw } from "lucide-react";

const fmt = (n: number | string) =>
  Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const StockLevelsPage: React.FC = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // فلاتر
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"" | "low" | "out" | "over">("");
  const [filterCategory, setFilterCategory] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [prods, sum] = await Promise.all([
        inventoryApi.getProducts(),
        inventoryApi.getStockSummary(),
      ]);
      setProducts(prods as SqlProduct[]);
      setSummary(sum as StockSummaryResponse);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const categories = Array.from(
    new Set(products.map((p) => p.category_name || "").filter(Boolean))
  ).sort();

  const filtered = products.filter((p) => {
    if (search) {
      const s = search.toLowerCase();
      if (
        !p.sku.toLowerCase().includes(s) &&
        !(p.name_ar || "").toLowerCase().includes(s) &&
        !(p.name_en || "").toLowerCase().includes(s)
      ) return false;
    }
    if (filterCategory && p.category_name !== filterCategory) return false;
    const qty = Number(p.quantity_on_hand);
    const min = Number(p.min_stock_level ?? 0);
    if (filterStatus === "out") return qty <= 0;
    if (filterStatus === "low") return qty > 0 && min > 0 && qty <= min;
    if (filterStatus === "over") return min > 0 && qty > min * 3;
    return true;
  });

  const statusCell = (p: SqlProduct) => {
    if (p.stock_status === "out_of_stock")
      return <span style={{ color: "var(--aseel-danger, #c00)" }}>نفذ</span>;
    if (p.stock_status === "low_stock")
      return <span style={{ color: "var(--aseel-warn, #b8800a)" }}>منخفض</span>;
    return <span style={{ color: "var(--aseel-ok, #267346)" }}>متوفر</span>;
  };

  const columns: DenseColumn<SqlProduct>[] = [
    { key: "sku", header: "SKU", width: "110px" },
    { key: "name", header: "الصنف", render: (p) => <>{p.name_ar || p.name_en || "—"}</> },
    { key: "cat", header: "التصنيف", width: "130px", render: (p) => <>{p.category_name || "—"}</> },
    { key: "qty", header: "المتاح", width: "90px", align: "center", numeric: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = qty <= (p.min_stock_level || 0);
        return <span style={low ? { color: "var(--aseel-danger, #c00)", fontWeight: 600 } : {}}>{fmt(qty)}</span>;
      }
    },
    { key: "min", header: "الحد الأدنى", width: "90px", align: "center", numeric: true,
      render: (p) => <>{p.min_stock_level ?? "—"}</> },
    { key: "status", header: "الحالة", width: "80px", align: "center", render: statusCell },
    { key: "avgcost", header: "متوسط التكلفة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(Number(p.avg_cost))}</> },
    { key: "val", header: "القيمة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(Number(p.quantity_on_hand) * Number(p.avg_cost))}</> },
  ];

  // footer: مجاميع
  const totalVal = filtered.reduce(
    (s, p) => s + Number(p.quantity_on_hand) * Number(p.avg_cost), 0
  );

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }} data-skin="aseel">
      {/* شريط العنوان والفلاتر */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          أرصدة المخزون
        </strong>
        {summary && (
          <span className="aseel-status-item">
            إجمالي الأصناف: <b>{summary.total_products_in_stock ?? products.length}</b>
          </span>
        )}
        {summary && (
          <span className="aseel-status-item">
            قيمة المخزون: <b>{fmt(Number(summary.total_inventory_value ?? 0))}</b>
          </span>
        )}
        <div style={{ flex: 1 }} />
        <input
          className="aseel-input"
          style={{ width: 180 }}
          placeholder="بحث SKU / الاسم…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="aseel-input"
          style={{ width: 140 }}
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
        >
          <option value="">كل التصنيفات</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          className="aseel-input"
          style={{ width: 140 }}
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as "" | "low" | "out" | "over")}
        >
          <option value="">كل الحالات</option>
          <option value="low">منخفض</option>
          <option value="out">نفذ</option>
          <option value="over">فوق الحد الأقصى</option>
        </select>
        <button className="aseel-toolbtn" onClick={load} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {err && (
        <div className="aseel-banner aseel-banner--err">{err}</div>
      )}

      <AseelDenseTable<SqlProduct>
        columns={columns}
        rows={filtered}
        getRowKey={(p) => p.id}
        loading={loading}
        emptyHint="لا توجد أصناف"
        footer={
          <span style={{ fontWeight: 700, color: "var(--aseel-ink)" }}>
            إجمالي القيمة ({filtered.length} صنف):{" "}
            <span style={{ color: "var(--aseel-accent, #1857a4)" }}>{fmt(totalVal)}</span>
          </span>
        }
      />
    </div>
  );
};
