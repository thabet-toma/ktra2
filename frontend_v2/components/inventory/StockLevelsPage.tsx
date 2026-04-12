import React, { useEffect, useState, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { StockSummaryItem, StockSummaryResponse, SqlProduct } from "../../types/inventory";
import {
  BarChart3,
  Loader2,
  AlertTriangle,
  RefreshCw,
  Package,
  ArrowDown,
  Search,
} from "lucide-react";

export const StockLevelsPage: React.FC = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");

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
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = products.filter((p) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      p.sku.toLowerCase().includes(s) ||
      (p.name_ar || "").toLowerCase().includes(s) ||
      (p.name_en || "").toLowerCase().includes(s)
    );
  });

  const fmt = (n: number | string) =>
    Number(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const statusBadge = (s: SqlProduct["stock_status"], minLvl?: number | null) => {
    if (s === "out_of_stock")
      return (
        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
          نفذ
        </span>
      );
    if (s === "low_stock")
      return (
        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          منخفض
        </span>
      );
    return (
      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
        متوفر
      </span>
    );
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" dir="rtl">
      <div className="flex items-center gap-3">
        <BarChart3 className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          أرصدة المخزون
        </h1>
      </div>

      {err && (
        <div className="p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg border border-red-200 dark:border-red-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {err}
        </div>
      )}

      {/* KPIs */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
              إجمالي المنتجات
            </div>
            <p className="text-2xl font-bold text-slate-800 dark:text-slate-100">
              {products.length}
            </p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
              منتجات بمخزون
            </div>
            <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
              {summary.total_products_in_stock}
            </p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
              قيمة المخزون الكلية
            </div>
            <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
              {fmt(summary.total_inventory_value)} ₪
            </p>
          </div>
        </div>
      )}

      {/* Search + refresh */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4 flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="بحث بالاسم أو SKU..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pr-9 pl-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm text-slate-800 dark:text-slate-100"
          />
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1 px-3 py-2 rounded-lg bg-slate-700 text-white text-sm hover:bg-slate-600"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          تحديث
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          <Package className="w-12 h-12 mx-auto mb-3 opacity-40" />
          لا توجد منتجات
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-600">
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    SKU
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    المنتج
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    التصنيف
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    الكمية
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    الحد الأدنى
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    الحالة
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    متوسط التكلفة
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    القيمة
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => {
                  const qty = Number(p.quantity_on_hand);
                  const avg = Number(p.avg_cost);
                  const val = qty * avg;
                  return (
                    <tr
                      key={p.id}
                      className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">
                        {p.sku}
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">
                        {p.name_ar || p.name_en || "—"}
                      </td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300 text-xs">
                        {p.category_name || "—"}
                      </td>
                      <td
                        className={`px-4 py-3 text-center font-mono font-semibold ${
                          qty <= 0
                            ? "text-red-600"
                            : qty <= (p.min_stock_level || 0)
                            ? "text-amber-600"
                            : "text-slate-800 dark:text-slate-100"
                        }`}
                      >
                        {qty.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-center font-mono text-slate-500">
                        {p.min_stock_level ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {statusBadge(p.stock_status, p.min_stock_level)}
                      </td>
                      <td className="px-4 py-3 text-center font-mono text-slate-600 dark:text-slate-300">
                        {fmt(avg)}
                      </td>
                      <td className="px-4 py-3 text-center font-mono font-semibold text-indigo-600 dark:text-indigo-400">
                        {fmt(val)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
