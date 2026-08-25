/**
 * N5-T8 — InventoryValuationPage (N-F8، جديد)
 * قيمة البضاعة الموجودة بطرق متعددة.
 * مرجع: التحاليل المالية.txt:1-32
 */
import React, { useState, useMemo, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";

/** P0-5: صف التقييم الخادمي — تجميعات لكل صنف بدل كل حركات المخزون. */
interface ValuationServerRow {
  id: number;
  sku: string;
  name_ar: string;
  name_en: string;
  category_name: string;
  quantity_on_hand: string;
  avg_cost: string;
  first_in_cost: string | null;
  last_in_cost: string | null;
  avg_in_cost: string | null;
  avg_out_cost: string | null;
  moves_qty_delta: string | null;
}
import { KitDenseTable, type DenseColumn } from "../kit/KitDenseTable";
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

function computeUnitPrice(row: ValuationServerRow, method: ValuationMethod): number {
  // P0-5: كانت تُحسب من كل الحركات في المتصفح — صارت قراءةً من تجميعات
  // الخادم بنفس الدلالة حرفياً (fallback إلى avg_cost حيث لا قيمة).
  const avgCost = Number(row.avg_cost) || 0;
  switch (method) {
    case "avg_cost":
      return avgCost;
    case "fifo":
      return Number(row.first_in_cost) || avgCost;
    case "lifo":
      return Number(row.last_in_cost) || avgCost;
    case "avg_purchase":
      return Number(row.avg_in_cost) || avgCost;
    case "avg_sale":
      return Number(row.avg_out_cost) || avgCost;
    case "selected_price":
      return avgCost;
    default:
      return avgCost;
  }
}

function applyBonusQty(row: ValuationServerRow, baseQty: number, bonus: BonusCalc): number {
  if (bonus === "from_movements") return Number(row.moves_qty_delta) || 0;
  return baseQty;
}

export const InventoryValuationPage: React.FC = () => {
  const [serverRows, setServerRows] = useState<ValuationServerRow[]>([]);
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
      // P0-5: نداء تجميعي واحد (~صف/صنف) بدل جلب كل الأصناف + كل الحركات.
      const res = await inventoryApi.getStockValuation(
        asOfDate ? { as_of: asOfDate } : undefined,
      );
      setServerRows(res.rows);
      setHasRun(true);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في التحميل");
    } finally {
      setLoading(false);
    }
  }, [asOfDate]);

  const categories = useMemo(() => {
    const set = new Set(serverRows.map((p) => p.category_name || "").filter(Boolean));
    return Array.from(set).sort();
  }, [serverRows]);

  const rows: ValuationRow[] = useMemo(() => {
    const s = search.toLowerCase();
    return serverRows
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
        const qty = applyBonusQty(p, baseQty, bonusCalc);
        const unitPrice = computeUnitPrice(p, method);
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
  }, [serverRows, method, bonusCalc, filterCategory, search]);

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
        <b style={{ color: "var(--ktra-accent, #1857a4)" }}>{fmt(r.totalValue)}</b>
      ),
    },
  ];

  const footer = hasRun ? (
    <span style={{ fontWeight: 700, color: "var(--ktra-ink)" }}>
      إجمالي قيمة البضاعة ({rows.length} صنف):{" "}
      <span style={{ color: "var(--ktra-accent, #1857a4)" }}>{fmt(grandTotal)}</span>
    </span>
  ) : undefined;

  return (
    <div
      dir="rtl"
      style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }}
    >
      {/* Header bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <BarChart2 style={{ width: 16, height: 16, color: "var(--ktra-accent, #1857a4)" }} />
        <strong style={{ fontSize: "var(--ktra-fs-title, 14px)", color: "var(--ktra-ink)" }}>
          قيمة البضاعة الموجودة
        </strong>
        {hasRun && (
          <span className="ktra-status-item">
            <b>{rows.length}</b> صنف — إجمالي: <b>{fmt(grandTotal)}</b>
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          className="ktra-toolbtn"
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
          background: "var(--ktra-row-alt, #f5f5f5)",
          borderRadius: 4,
          border: "1px solid var(--ktra-border, #d0d0d0)",
        }}
      >
        {/* Valuation method */}
        <div className="ktra-field">
          <label className="ktra-field-label">طريقة الاحتساب</label>
          <select
            className="ktra-input"
            value={method}
            onChange={(e) => setMethod(e.target.value as ValuationMethod)}
          >
            {(Object.entries(METHOD_LABELS) as [ValuationMethod, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* Bonus quantities */}
        <div className="ktra-field">
          <label className="ktra-field-label">الكميات الإضافية</label>
          <select
            className="ktra-input"
            value={bonusCalc}
            onChange={(e) => setBonusCalc(e.target.value as BonusCalc)}
          >
            {(Object.entries(BONUS_LABELS) as [BonusCalc, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* As-of date */}
        <div className="ktra-field">
          <label className="ktra-field-label">التاريخ حتى</label>
          <input
            type="date"
            className="ktra-input"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
          />
        </div>

        {/* Category filter */}
        <div className="ktra-field">
          <label className="ktra-field-label">التصنيف</label>
          <select
            className="ktra-input"
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
        <div className="ktra-field" style={{ gridColumn: "span 2" }}>
          <label className="ktra-field-label">بحث</label>
          <input
            className="ktra-input"
            placeholder="SKU / اسم الصنف…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {err && <div className="ktra-banner ktra-banner--err">{err}</div>}

      <div
        style={{
          display: "flex",
          gap: 6,
          alignItems: "center",
          fontSize: "var(--ktra-fs-sm)",
          color: "var(--ktra-ink-soft)",
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
            color: "var(--ktra-ink-soft)",
          }}
        >
          <BarChart2 style={{ width: 40, height: 40, opacity: 0.3 }} />
          <p style={{ margin: 0 }}>اختر طريقة الاحتساب والفلاتر ثم اضغط "احتساب"</p>
        </div>
      )}

      {(hasRun || loading) && (
        <KitDenseTable<ValuationRow>
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
