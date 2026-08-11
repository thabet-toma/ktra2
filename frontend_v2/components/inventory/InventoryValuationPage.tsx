/**
 * N5-T8 — InventoryValuationPage (N-F8، جديد)
 * قيمة البضاعة الموجودة بطرق متعددة.
 * مرجع: التحاليل المالية.txt:1-32
 */
import React, { useState, useMemo, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct, StockMovementDto } from "../../types/inventory";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { RefreshCw, BarChart2, Info } from "lucide-react";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { productProfilePath } from "../../utils/entityLinks";
import { openInNewTab } from "../../utils/openInNewTab";

type ValuationMethod =
  | "avg_cost"
  | "fifo"
  | "lifo"
  | "avg_purchase"
  | "avg_sale"
  | "selected_price";

type BonusCalc = "none" | "from_movements" | "from_card";

interface ValuationRow {
  id: number;
  sku: string;
  name: string;
  category: string;
  quantity: number;
  unitPrice: number;
  totalValue: number;
  currency: string;
}

const METHOD_LABELS: Record<ValuationMethod, string> = {
  avg_cost: "معدل التكلفة",
  fifo: "الوارد أولاً صادر أولاً (FIFO)",
  lifo: "الوارد أخيراً صادر أولاً (LIFO)",
  avg_purchase: "معدل سعر الشراء",
  avg_sale: "معدل سعر البيع",
  selected_price: "السعر المختار",
};

const BONUS_LABELS: Record<BonusCalc, string> = {
  none: "بدون احتساب",
  from_movements: "من الحركات",
  from_card: "من كارت الصنف",
};

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة عبر المُنسّق الموحّد.
const fmt = (n: number) => formatMoney(n, "0");

/**
 * يَحسب سعر الوحدة لصنف معيَّن حسب الطريقة المختارة.
 * - avg_cost: متوسط التكلفة الحالي (المخزون في كل حركة)
 * - fifo: تكلفة أقدم حركة IN لم تَستهلك بعد (تَقدير من الحركات)
 * - lifo: تكلفة أحدث حركة IN
 * - avg_purchase: المتوسط الحسابي لكل unit_cost في حركات IN
 * - avg_sale: المتوسط الحسابي لكل unit_cost في حركات OUT
 * - selected_price: avg_cost (placeholder حتى N8-T9 يَفتح price tiers)
 */
function computeUnitPrice(
  product: SqlProduct,
  method: ValuationMethod,
  movements: StockMovementDto[],
): number {
  const avgCost = Number(product.avg_cost) || 0;
  const productMoves = movements.filter((m) => m.product === product.id);
  const ins = productMoves.filter((m) => m.movement_type.includes("IN"));
  const outs = productMoves.filter((m) => m.movement_type.includes("OUT"));

  const avgOf = (arr: StockMovementDto[]): number => {
    const valid = arr.map((m) => Number(m.unit_cost)).filter((n) => n > 0);
    return valid.length ? valid.reduce((s, n) => s + n, 0) / valid.length : 0;
  };

  switch (method) {
    case "avg_cost":
      return avgCost;
    case "fifo":
      return Number(ins[0]?.unit_cost) || avgCost;
    case "lifo":
      return Number(ins[ins.length - 1]?.unit_cost) || avgCost;
    case "avg_purchase":
      return avgOf(ins) || avgCost;
    case "avg_sale":
      return avgOf(outs) || avgCost;
    case "selected_price":
      return avgCost;
    default:
      return avgCost;
  }
}

function applyBonusQty(
  product: SqlProduct,
  baseQty: number,
  bonus: BonusCalc,
  movements: StockMovementDto[],
): number {
  if (bonus === "none") return baseQty;
  if (bonus === "from_movements") {
    const productMoves = movements.filter((m) => m.product === product.id);
    return productMoves.reduce((s, m) => {
      const q = Number(m.quantity) || 0;
      return s + (m.movement_type.includes("IN") ? q : -q);
    }, 0);
  }
  return baseQty;
}

export const InventoryValuationPage: React.FC = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [movements, setMovements] = useState<StockMovementDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hasRun, setHasRun] = useState(false);

  const [method, setMethod] = useState<ValuationMethod>("avg_cost");
  const [bonusCalc, setBonusCalc] = useState<BonusCalc>("none");
  const [asOfDate, setAsOfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [filterCategory, setFilterCategory] = useState("");
  const [search, setSearch] = useState("");

  const run = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [all, moves] = await Promise.all([
        inventoryApi.getProducts(),
        inventoryApi.getStockMovements(
          asOfDate ? { date_to: asOfDate } : undefined,
        ),
      ]);
      setProducts(all as SqlProduct[]);
      setMovements(moves as StockMovementDto[]);
      setHasRun(true);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في التحميل");
    } finally {
      setLoading(false);
    }
  }, [asOfDate]);

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category_name || "").filter(Boolean));
    return Array.from(set).sort();
  }, [products]);

  const rows: ValuationRow[] = useMemo(() => {
    const s = search.toLowerCase();
    return products
      .filter((p) => {
        if (filterCategory && p.category_name !== filterCategory) return false;
        if (s) {
          return (
            p.sku.toLowerCase().includes(s) ||
            (p.name_ar || "").toLowerCase().includes(s) ||
            (p.name_en || "").toLowerCase().includes(s)
          );
        }
        return true;
      })
      .map((p) => {
        const baseQty = Number(p.quantity_on_hand) || 0;
        const qty = applyBonusQty(p, baseQty, bonusCalc, movements);
        const unitPrice = computeUnitPrice(p, method, movements);
        return {
          id: p.id,
          sku: p.sku,
          name: p.name_ar || p.name_en || "—",
          category: p.category_name || "—",
          quantity: qty,
          unitPrice,
          totalValue: qty * unitPrice,
          currency: "ILS",
        };
      })
      .filter((r) => r.quantity > 0);
  }, [products, movements, method, bonusCalc, filterCategory, search]);

  const grandTotal = useMemo(() => rows.reduce((s, r) => s + r.totalValue, 0), [rows]);

  const columns: DenseColumn<ValuationRow>[] = [
    { key: "sku", header: "رقم الصنف", width: "110px", render: (r) => <b>{r.sku}</b> },
    { key: "name", header: "اسم الصنف", render: (r) => (
        // اسم الصنف قابل للنقر — يفتح حركة مخزون الصنف.
        <button
          type="button"
          className="text-blue-700 hover:underline text-right"
          onClick={(e) => { e.stopPropagation(); openInNewTab(productProfilePath(r.id)); }}
          title="فتح حركة مخزون الصنف"
        >
          {r.name}
        </button>
      ) },
    { key: "category", header: "التصنيف", width: "140px", render: (r) => <>{r.category}</> },
    {
      key: "quantity",
      header: "الكمية",
      width: "90px",
      align: "center",
      numeric: true,
      render: (r) => <>{formatQuantity(r.quantity)}</>,
    },
    {
      key: "unitPrice",
      header: "سعر الوحدة",
      width: "110px",
      align: "center",
      numeric: true,
      render: (r) => <>{fmt(r.unitPrice)}</>,
    },
    {
      key: "totalValue",
      header: "القيمة الإجمالية",
      width: "130px",
      align: "center",
      numeric: true,
      render: (r) => (
        <b style={{ color: "var(--aseel-accent, #1857a4)" }}>{fmt(r.totalValue)}</b>
      ),
    },
  ];

  const footer = hasRun ? (
    <span style={{ fontWeight: 700, color: "var(--aseel-ink)" }}>
      إجمالي قيمة البضاعة ({rows.length} صنف):{" "}
      <span style={{ color: "var(--aseel-accent, #1857a4)" }}>{fmt(grandTotal)}</span>
    </span>
  ) : undefined;

  return (
    <div
      dir="rtl"
      style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }}
    >
      {/* Header bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <BarChart2 style={{ width: 16, height: 16, color: "var(--aseel-accent, #1857a4)" }} />
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          قيمة البضاعة الموجودة
        </strong>
        {hasRun && (
          <span className="aseel-status-item">
            <b>{rows.length}</b> صنف — إجمالي: <b>{fmt(grandTotal)}</b>
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          className="aseel-toolbtn"
          onClick={run}
          disabled={loading}
          title="احتساب قيمة البضاعة"
          style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 600 }}
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          احتساب
        </button>
      </div>

      {/* Filters panel */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          gap: 8,
          padding: "8px 10px",
          background: "var(--aseel-row-alt, #f5f5f5)",
          borderRadius: 4,
          border: "1px solid var(--aseel-border, #d0d0d0)",
        }}
      >
        {/* Valuation method */}
        <div className="aseel-field">
          <label className="aseel-field-label">طريقة الاحتساب</label>
          <select
            className="aseel-input"
            value={method}
            onChange={(e) => setMethod(e.target.value as ValuationMethod)}
          >
            {(Object.entries(METHOD_LABELS) as [ValuationMethod, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* Bonus quantities */}
        <div className="aseel-field">
          <label className="aseel-field-label">الكميات الإضافية</label>
          <select
            className="aseel-input"
            value={bonusCalc}
            onChange={(e) => setBonusCalc(e.target.value as BonusCalc)}
          >
            {(Object.entries(BONUS_LABELS) as [BonusCalc, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* As-of date */}
        <div className="aseel-field">
          <label className="aseel-field-label">التاريخ حتى</label>
          <input
            type="date"
            className="aseel-input"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
          />
        </div>

        {/* Category filter */}
        <div className="aseel-field">
          <label className="aseel-field-label">التصنيف</label>
          <select
            className="aseel-input"
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
          >
            <option value="">كل التصنيفات</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* Search */}
        <div className="aseel-field" style={{ gridColumn: "span 2" }}>
          <label className="aseel-field-label">بحث</label>
          <input
            className="aseel-input"
            placeholder="SKU / اسم الصنف…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {err && <div className="aseel-banner aseel-banner--err">{err}</div>}

      <div
        style={{
          display: "flex",
          gap: 6,
          alignItems: "center",
          fontSize: "var(--aseel-fs-sm)",
          color: "var(--aseel-ink-soft)",
          padding: "2px 4px",
        }}
      >
        <Info style={{ width: 12, height: 12 }} />
        <span>
          فلاتر «المخزن / الفرع» و«السعر المختار» تَتوفَّر بعد N8 (multi-warehouse + price tiers).
        </span>
      </div>

      {!hasRun && !loading && (
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 12,
            color: "var(--aseel-ink-soft)",
          }}
        >
          <BarChart2 style={{ width: 40, height: 40, opacity: 0.3 }} />
          <p style={{ margin: 0 }}>اختر طريقة الاحتساب والفلاتر ثم اضغط "احتساب"</p>
        </div>
      )}

      {(hasRun || loading) && (
        <AseelDenseTable<ValuationRow>
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          loading={loading}
          emptyHint="لا توجد بضائع بالمخزن"
          footer={footer}
        />
      )}
    </div>
  );
};
