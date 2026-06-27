import React, { useEffect, useState, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct, StockSummaryResponse } from "../../types/inventory";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { RefreshCw, Download, Printer } from "lucide-react";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { productProfilePath } from "../../utils/entityLinks";
import { openInNewTab } from "../../utils/openInNewTab";

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة (6.00 ⇒ 6، 6.50 ⇒ 6.5) عبر المُنسّق الموحّد.
const fmt = (n: number | string) => formatMoney(n, "0");

export const StockLevelsPage: React.FC = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // فلاتر
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"" | "low" | "out" | "over">("");
  const [filterCategory, setFilterCategory] = useState<string>("");
  // task16 E18: اختيار الأصناف للتصدير
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

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

  // task16 E18: تصدير رصيد المخزون إلى CSV — المختار، وإلا كل المعروض
  const STATUS_AR: Record<string, string> = {
    out_of_stock: "نفذ", low_stock: "منخفض", in_stock: "متوفر",
  };
  const toggleOne = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const allFilteredSelected = filtered.length > 0 && filtered.every((p) => selectedIds.has(p.id));
  const toggleAll = () =>
    setSelectedIds((prev) => {
      if (filtered.every((p) => prev.has(p.id))) {
        const next = new Set(prev);
        filtered.forEach((p) => next.delete(p.id));
        return next;
      }
      const next = new Set(prev);
      filtered.forEach((p) => next.add(p.id));
      return next;
    });

  const printPdf = () => {
    const rowsToExport = selectedIds.size > 0
      ? filtered.filter((p) => selectedIds.has(p.id))
      : filtered;
    if (rowsToExport.length === 0) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert('الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة');
      return;
    }

    const today = new Date().toISOString().slice(0, 10);
    
    let html = `
      <html dir="rtl" lang="ar">
        <head>
          <title>أرصدة المخزون - ${today}</title>
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
            @media print {
              body { padding: 0; }
              @page { margin: 1.5cm; }
            }
          </style>
        </head>
        <body>
          <h2>تقرير أرصدة المخزون</h2>
          <div class="subtitle">التاريخ: ${today}</div>
          <table>
            <thead>
              <tr>
                <th>البضاعة (الصنف)</th>
                <th>الكمية المتبقية</th>
                <th>متوسط التكلفة</th>
                <th>الحد الأدنى</th>
              </tr>
            </thead>
            <tbody>
    `;

    rowsToExport.forEach(p => {
      const name = p.name_ar || p.name_en || p.sku || '—';
      const qty = Number(p.quantity_on_hand);
      const avgCost = Number(p.avg_cost).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const minStock = p.min_stock_level ?? '—';
      const isLow = qty <= (p.min_stock_level || 0);
      
      html += `
        <tr>
          <td>${name} <br><span style="color:#6b7280; font-size:12px">${p.sku}</span></td>
          <td class="num ${isLow ? 'danger' : ''}" style="direction: ltr">${qty}</td>
          <td class="num" style="direction: ltr">${avgCost}</td>
          <td class="num" style="direction: ltr">${minStock}</td>
        </tr>
      `;
    });

    html += `
            </tbody>
          </table>
          <script>
            window.onload = () => {
              window.print();
            };
          </script>
        </body>
      </html>
    `;

    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
  };

  const statusCell = (p: SqlProduct) => {
    if (p.stock_status === "out_of_stock")
      return <span style={{ color: "var(--aseel-danger, #c00)" }}>نفذ</span>;
    if (p.stock_status === "low_stock")
      return <span style={{ color: "var(--aseel-warn, #b8800a)" }}>منخفض</span>;
    return <span style={{ color: "var(--aseel-ok, #267346)" }}>متوفر</span>;
  };

  const columns: DenseColumn<SqlProduct>[] = [
    {
      key: "sel",
      header: "✓",
      width: "36px",
      align: "center",
      render: (p) => (
        <input
          type="checkbox"
          checked={selectedIds.has(p.id)}
          onChange={() => toggleOne(p.id)}
          onClick={(e) => e.stopPropagation()}
        />
      ),
    },
    { key: "sku", header: "SKU", width: "110px" },
    { key: "name", header: "الصنف", render: (p) => (
        // اسم الصنف قابل للنقر — يفتح حركة مخزون الصنف.
        <button
          type="button"
          className="text-blue-700 hover:underline text-right"
          onClick={(e) => { e.stopPropagation(); openInNewTab(productProfilePath(p.id)); }}
          title="فتح حركة مخزون الصنف"
        >
          {p.name_ar || p.name_en || "—"}
        </button>
      ) },
    { key: "cat", header: "التصنيف", width: "130px", render: (p) => <>{p.category_name || "—"}</> },
    { key: "qty", header: "المتاح", width: "90px", align: "center", numeric: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = qty <= (p.min_stock_level || 0);
        return <span style={low ? { color: "var(--aseel-danger, #c00)", fontWeight: 600 } : {}}>{formatQuantity(qty)}</span>;
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
        <label className="aseel-status-item" style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }} title="تحديد/إلغاء كل المعروض">
          <input type="checkbox" checked={allFilteredSelected} onChange={toggleAll} />
          تحديد الكل
        </label>
        <button
          className="aseel-toolbtn"
          onClick={printPdf}
          disabled={filtered.length === 0}
          title={selectedIds.size > 0 ? `طباعة ${selectedIds.size} صنف مختار` : "طباعة كل المعروض"}
          style={{ display: "flex", alignItems: "center", gap: 4 }}
        >
          <Printer className="h-4 w-4" />
          طباعة / PDF{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
        </button>
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
