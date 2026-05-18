import React, { useEffect, useState, useCallback } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type {
  StockMovementDto,
  SqlProduct,
  StockSummaryResponse,
} from "../../types/inventory";
import {
  Package,
  Plus,
  ArrowDownToLine,
  ArrowUpFromLine,
  Loader2,
  AlertTriangle,
  Filter,
  RefreshCw,
  TrendingUp,
  Boxes,
} from "lucide-react";

const MOVEMENT_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  IN: { label: "استلام", color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300" },
  OUT: { label: "صرف", color: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
  ADJUST_IN: { label: "تسوية +", color: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  ADJUST_OUT: { label: "تسوية −", color: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
  RETURN_IN: { label: "مرتجع ←", color: "bg-[var(--color-surface-2)] text-[var(--color-primary)] dark:bg-[var(--color-surface-2)]/40 dark:text-[var(--color-primary)]" },
  RETURN_OUT: { label: "مرتجع →", color: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300" },
};

export const StockMovementsPage: React.FC = () => {
  const [movements, setMovements] = useState<StockMovementDto[]>([]);
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [filterProduct, setFilterProduct] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    product: "",
    movement_type: "ADJUST_IN",
    quantity: "",
    unit_cost: "",
    movement_date: new Date().toISOString().split("T")[0],
    notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {};
      if (filterProduct) params.product = filterProduct;
      if (filterType) params.movement_type = filterType;
      if (filterDateFrom) params.date_from = filterDateFrom;
      if (filterDateTo) params.date_to = filterDateTo;

      const [mvs, prods, sum] = await Promise.all([
        inventoryApi.getStockMovements(
          Object.keys(params).length ? params : undefined
        ),
        inventoryApi.getProducts(),
        inventoryApi.getStockSummary(),
      ]);
      setMovements(mvs as StockMovementDto[]);
      setProducts(prods as SqlProduct[]);
      setSummary(sum as StockSummaryResponse);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, [filterProduct, filterType, filterDateFrom, filterDateTo]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    if (!form.product || !form.quantity) return;
    setBusy(true);
    setErr(null);
    try {
      await inventoryApi.createStockMovement({
        product: Number(form.product),
        movement_type: form.movement_type,
        quantity: parseFloat(form.quantity),
        unit_cost: parseFloat(form.unit_cost) || 0,
        movement_date: form.movement_date,
        notes: form.notes,
        reference_type: "MANUAL",
      });
      setShowForm(false);
      setForm({
        product: "",
        movement_type: "ADJUST_IN",
        quantity: "",
        unit_cost: "",
        movement_date: new Date().toISOString().split("T")[0],
        notes: "",
      });
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const fmtDate = (d: string) => {
    const [y, m, day] = d.split("-");
    return `${day}/${m}/${y}`;
  };

  const fmt = (n: number | string) =>
    Number(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" dir="rtl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Package className="w-7 h-7 text-[var(--color-primary)] dark:text-[var(--color-primary)]" />
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          حركات المخزون
        </h1>
      </div>

      {err && (
        <div className="p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg border border-red-200 dark:border-red-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {err}
        </div>
      )}

      {/* Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-1">
              <Boxes className="w-4 h-4" />
              أصناف بمخزون
            </div>
            <p className="text-2xl font-bold text-slate-800 dark:text-slate-100">
              {summary.total_products_in_stock}
            </p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-1">
              <TrendingUp className="w-4 h-4" />
              قيمة المخزون الكلية
            </div>
            <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
              {fmt(summary.total_inventory_value)}
            </p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-1">
              <Package className="w-4 h-4" />
              إجمالي الحركات
            </div>
            <p className="text-2xl font-bold text-slate-800 dark:text-slate-100">
              {movements.length}
            </p>
          </div>
        </div>
      )}

      {/* Filters + Add */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              <Filter className="w-3 h-3 inline ml-1" />
              المنتج
            </label>
            <select
              value={filterProduct}
              onChange={(e) => setFilterProduct(e.target.value)}
              className="w-48 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm text-slate-800 dark:text-slate-100"
            >
              <option value="">الكل</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} — {p.name_ar || p.name_en}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              نوع الحركة
            </label>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="w-36 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm text-slate-800 dark:text-slate-100"
            >
              <option value="">الكل</option>
              <option value="IN">استلام</option>
              <option value="OUT">صرف</option>
              <option value="ADJUST_IN">تسوية +</option>
              <option value="ADJUST_OUT">تسوية −</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              من تاريخ
            </label>
            <input
              type="date"
              value={filterDateFrom}
              onChange={(e) => setFilterDateFrom(e.target.value)}
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm text-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              إلى تاريخ
            </label>
            <input
              type="date"
              value={filterDateTo}
              onChange={(e) => setFilterDateTo(e.target.value)}
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm text-slate-800 dark:text-slate-100"
            />
          </div>
          <button
            onClick={load}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-slate-700 text-white text-sm hover:bg-slate-600"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            تطبيق
          </button>
          <div className="flex-1" />
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            حركة يدوية
          </button>
        </div>
      </div>

      {/* Manual Movement Form */}
      {showForm && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-[var(--color-border)] dark:border-[var(--color-border)] p-5 space-y-4">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            تسجيل حركة مخزون يدوية
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1">المنتج *</label>
              <select
                value={form.product}
                onChange={(e) => setForm((f) => ({ ...f, product: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
              >
                <option value="">— اختر —</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sku} — {p.name_ar || p.name_en}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">نوع الحركة *</label>
              <select
                value={form.movement_type}
                onChange={(e) => setForm((f) => ({ ...f, movement_type: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
              >
                <option value="ADJUST_IN">تسوية إضافة (+)</option>
                <option value="ADJUST_OUT">تسوية نقص (−)</option>
                <option value="IN">استلام</option>
                <option value="OUT">صرف</option>
                <option value="RETURN_IN">مرتجع داخل</option>
                <option value="RETURN_OUT">مرتجع خارج</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">التاريخ *</label>
              <input
                type="date"
                value={form.movement_date}
                onChange={(e) => setForm((f) => ({ ...f, movement_date: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">الكمية *</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={form.quantity}
                onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">تكلفة الوحدة</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.unit_cost}
                onChange={(e) => setForm((f) => ({ ...f, unit_cost: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">ملاحظات</label>
              <input
                type="text"
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg"
            >
              إلغاء
            </button>
            <button
              onClick={handleCreate}
              disabled={busy || !form.product || !form.quantity}
              className="flex items-center gap-2 px-5 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg text-sm disabled:opacity-50"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              تسجيل
            </button>
          </div>
        </div>
      )}

      {/* Movements Table */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary)]" />
        </div>
      ) : movements.length === 0 ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          لا توجد حركات مخزون مسجلة
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-600">
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    #
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    التاريخ
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    النوع
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    المنتج
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    الكمية
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    تكلفة الوحدة
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    الإجمالي
                  </th>
                  <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    الرصيد بعد
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    المرجع
                  </th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                    ملاحظات
                  </th>
                </tr>
              </thead>
              <tbody>
                {movements.map((m) => {
                  const isIn = ["IN", "ADJUST_IN", "RETURN_IN"].includes(m.movement_type);
                  const typeInfo = MOVEMENT_TYPE_LABELS[m.movement_type] || {
                    label: m.movement_type_display,
                    color: "bg-slate-100 text-slate-600",
                  };
                  return (
                    <tr
                      key={m.id}
                      className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">
                        {m.id}
                      </td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300 whitespace-nowrap">
                        {fmtDate(m.movement_date)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${typeInfo.color}`}
                        >
                          {isIn ? (
                            <ArrowDownToLine className="w-3 h-3" />
                          ) : (
                            <ArrowUpFromLine className="w-3 h-3" />
                          )}
                          {typeInfo.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">
                        <div className="text-sm">{m.product_name}</div>
                        <div className="text-xs text-slate-400">{m.product_sku}</div>
                      </td>
                      <td
                        className={`px-4 py-3 text-center font-mono font-semibold ${
                          isIn
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-red-600 dark:text-red-400"
                        }`}
                      >
                        {isIn ? "+" : "−"}
                        {Number(m.quantity).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-center font-mono text-slate-600 dark:text-slate-300">
                        {fmt(m.unit_cost)}
                      </td>
                      <td className="px-4 py-3 text-center font-mono text-slate-600 dark:text-slate-300">
                        {fmt(m.total_cost)}
                      </td>
                      <td className="px-4 py-3 text-center font-mono font-semibold text-slate-800 dark:text-slate-100">
                        {Number(m.quantity_after).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                        {m.reference_type_display}
                        {m.reference_id ? ` #${m.reference_id}` : ""}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400 max-w-[200px] truncate">
                        {m.notes || "—"}
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
