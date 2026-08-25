/**
 * ProductCostPage — واجهة «تكلفة المنتجات».
 *
 * تختار منتجاً (افتراضياً من باراميتر ?product=ID عند الفتح من بطاقة الصنف أو
 * تنبيه فاتورة الشراء)، فتعرض كل فواتير الشراء التي تحتويه: تكلفة كل فاتورة على
 * حدة + متوسط سعر الوحدة لتلك الفاتورة. ثم تكلفة المنتج = متوسط أسعار وحدات
 * الفواتير **مرجّحاً بكمية كل فاتورة** — أي Σ(تكلفة الفواتير) ÷ Σ(كميات الشراء)،
 * المقام إجمالي المشترى لا الكمية الحالية المتبقية (فلا يتأثر بما بِيع).
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { inventoryApi, type ProductCostBreakdown, type ProductCostInvoiceRow } from "../../services/inventoryApi";
import { KitDenseTable, type DenseColumn } from "../kit/KitDenseTable";
import { DocRefCell } from "../shared/LedgerTable";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { BarChart3, RefreshCw, Search, Info } from "lucide-react";

interface ProductLite {
  id: number;
  sku: string;
  name_ar?: string | null;
  name_en?: string | null;
}

export const ProductCostPage: React.FC = () => {
  const location = useLocation();
  const initialProductId = useMemo(() => {
    const v = new URLSearchParams(location.search).get("product");
    return v ? Number(v) : null;
  }, [location.search]);

  const [products, setProducts] = useState<ProductLite[]>([]);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(initialProductId);

  const [data, setData] = useState<ProductCostBreakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // قائمة المنتجات (للاختيار/البحث).
  useEffect(() => {
    inventoryApi
      .getProducts()
      .then((d: unknown) => {
        const arr = Array.isArray(d) ? d : ((d as { results?: ProductLite[] })?.results ?? []);
        setProducts(arr as ProductLite[]);
      })
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : "تعذّر تحميل المنتجات"));
  }, []);

  const loadBreakdown = useCallback((id: number) => {
    setLoading(true);
    setErr(null);
    inventoryApi
      .getProductCostBreakdown(id)
      .then((d) => setData(d))
      .catch((e: unknown) => {
        setErr(e instanceof Error ? e.message : "تعذّر تحميل تكلفة المنتج");
        setData(null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedId != null) loadBreakdown(selectedId);
  }, [selectedId, loadBreakdown]);

  const matches = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return [] as ProductLite[];
    return products
      .filter(
        (p) =>
          p.sku.toLowerCase().includes(s) ||
          (p.name_ar || "").toLowerCase().includes(s) ||
          (p.name_en || "").toLowerCase().includes(s),
      )
      .slice(0, 15);
  }, [products, search]);

  const columns: DenseColumn<ProductCostInvoiceRow>[] = [
    {
      key: "invoice_number",
      header: "رقم الفاتورة",
      width: "150px",
      render: (r) => (
        <DocRefCell referenceType="PURCHASE_INVOICE" referenceId={r.invoice_id} label={r.invoice_number} />
      ),
    },
    { key: "date", header: "التاريخ", width: "110px", render: (r) => <>{r.date || "—"}</> },
    { key: "party", header: "المورد", render: (r) => <>{r.party || "—"}</> },
    {
      key: "quantity",
      header: "الكمية",
      width: "90px",
      align: "center",
      numeric: true,
      render: (r) => <>{formatQuantity(r.quantity)}</>,
    },
    {
      key: "invoice_cost",
      header: "تكلفة الفاتورة",
      width: "130px",
      align: "center",
      numeric: true,
      render: (r) => <>{formatMoney(r.invoice_cost)}</>,
    },
    {
      key: "unit_cost",
      header: "سعر الوحدة (متوسط الفاتورة)",
      width: "170px",
      align: "center",
      numeric: true,
      render: (r) => <b style={{ color: "var(--ktra-accent, #1857a4)" }}>{formatMoney(r.unit_cost)}</b>,
    },
  ];

  const footer =
    data && data.invoice_count > 0 ? (
      <span style={{ fontWeight: 700, color: "var(--ktra-ink)", display: "flex", gap: 18, flexWrap: "wrap" }}>
        <span>
          إجمالي الكمية المشتراة: <b>{formatQuantity(data.total_purchased_qty)}</b>
        </span>
        <span>
          تكلفة المنتج (متوسط مرجّح بالكمية):{" "}
          <span style={{ color: "var(--ktra-accent, #1857a4)" }}>{formatMoney(data.average_cost)}</span>
        </span>
      </span>
    ) : undefined;

  return (
    <div
      dir="rtl"
      style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <BarChart3 style={{ width: 16, height: 16, color: "var(--ktra-accent, #1857a4)" }} />
        <strong style={{ fontSize: "var(--ktra-fs-title, 14px)", color: "var(--ktra-ink)" }}>
          تكلفة المنتجات
        </strong>
        {data && (
          <span className="ktra-status-item">
            {data.sku} — {data.name} · <b>{data.invoice_count}</b> فاتورة · متوسط مرجّح{" "}
            <b>{formatMoney(data.average_cost)}</b>
          </span>
        )}
        <div style={{ flex: 1 }} />
        {selectedId != null && (
          <button
            className="ktra-toolbtn"
            onClick={() => loadBreakdown(selectedId)}
            disabled={loading}
            title="تحديث"
            style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 600 }}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            تحديث
          </button>
        )}
      </div>

      {/* Product picker */}
      <div
        style={{
          padding: "8px 10px",
          background: "var(--ktra-row-alt, #f5f5f5)",
          borderRadius: 4,
          border: "1px solid var(--ktra-border, #d0d0d0)",
        }}
      >
        <div className="ktra-field" style={{ position: "relative" }}>
          <label className="ktra-field-label" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Search style={{ width: 12, height: 12 }} /> اختر المنتج
          </label>
          <input
            className="ktra-input"
            placeholder="SKU / اسم المنتج…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {matches.length > 0 && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                insetInlineStart: 0,
                insetInlineEnd: 0,
                zIndex: 20,
                background: "var(--ktra-bg, #fff)",
                border: "1px solid var(--ktra-border, #d0d0d0)",
                borderRadius: 4,
                maxHeight: 280,
                overflowY: "auto",
                boxShadow: "0 4px 12px rgba(0,0,0,.12)",
              }}
            >
              {matches.map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setSelectedId(p.id);
                    setSearch("");
                  }}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "start",
                    padding: "6px 10px",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    fontSize: "var(--ktra-fs-sm)",
                    color: "var(--ktra-ink)",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--ktra-row-alt, #f0f0f0)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <b>{p.sku}</b> — {p.name_ar || p.name_en || "—"}
                </button>
              ))}
            </div>
          )}
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
          سعر وحدة كل فاتورة = تكلفة الفاتورة ÷ كميتها. تكلفة المنتج = متوسط هذه الأسعار مرجّحاً بكمية كل
          فاتورة (المقام إجمالي المشترى، لا الكمية الحالية).
        </span>
      </div>

      {selectedId == null && !loading && (
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
          <BarChart3 style={{ width: 40, height: 40, opacity: 0.3 }} />
          <p style={{ margin: 0 }}>ابحث واختر منتجاً لعرض تكلفته من فواتير الشراء</p>
        </div>
      )}

      {selectedId != null && (
        <KitDenseTable<ProductCostInvoiceRow>
          columns={columns}
          rows={data?.invoices ?? []}
          getRowKey={(r) => r.invoice_id}
          loading={loading}
          emptyHint="لا توجد فواتير شراء تحتوي هذا المنتج"
          footer={footer}
        />
      )}
    </div>
  );
};

export default ProductCostPage;
