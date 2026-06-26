import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import type { StockMovementDto, SqlProduct } from "../../types/inventory";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { Plus, RefreshCw, X, Save, Loader2, Warehouse as WhIcon } from "lucide-react";
import { invoicePathForReference, productPath } from "../../utils/entityLinks";
import { openInNewTab } from "@/utils/openInNewTab";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";

const TYPES: Record<string, string> = {
  IN: "استلام", OUT: "صرف",
  ADJUST_IN: "تسوية +", ADJUST_OUT: "تسوية −",
  RETURN_IN: "مرتجع ←", RETURN_OUT: "مرتجع →",
};

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة عبر المُنسّق الموحّد.
const fmt = (n: string | number) => formatMoney(n, "0");

const fmtDate = (d: string) => {
  if (!d) return "—";
  const [y, m, day] = d.split("T")[0].split("-");
  return `${day}/${m}/${y}`;
};

type FormState = {
  product: string; movement_type: string; quantity: string;
  unit_cost: string; movement_date: string; notes: string;
};

const blankForm = (): FormState => ({
  product: "", movement_type: "ADJUST_IN", quantity: "",
  unit_cost: "", movement_date: new Date().toISOString().slice(0, 10), notes: "",
});

export const StockMovementsPage: React.FC = () => {
  const navigate = useNavigate();
  const [movements, setMovements] = useState<StockMovementDto[]>([]);
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(blankForm());

  // فلاتر
  const [filterProduct, setFilterProduct] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  // تقسيم المخزن: محلي (فاتورة شراء) / دولي (مسار الاستيراد)
  const [filterOrigin, setFilterOrigin] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {};
      if (filterProduct) params.product = filterProduct;
      if (filterType) params.movement_type = filterType;
      if (filterOrigin) params.origin = filterOrigin;
      if (filterDateFrom) params.date_from = filterDateFrom;
      if (filterDateTo) params.date_to = filterDateTo;
      const [mvs, prods] = await Promise.all([
        inventoryApi.getStockMovements(Object.keys(params).length ? params : undefined),
        inventoryApi.getProducts(),
      ]);
      setMovements(mvs as StockMovementDto[]);
      setProducts(prods as SqlProduct[]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, [filterProduct, filterType, filterOrigin, filterDateFrom, filterDateTo]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!form.product || !form.quantity) { setErr("اختر الصنف والكمية."); return; }
    setBusy(true); setErr(null);
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
      setForm(blankForm());
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const columns: DenseColumn<StockMovementDto>[] = [
    { key: "id", header: "#", width: "55px", align: "center",
      render: (m) => <>{m.id}</> },
    { key: "date", header: "التاريخ", width: "90px",
      render: (m) => <>{fmtDate(m.movement_date)}</> },
    { key: "sku", header: "SKU", width: "100px",
      render: (m) => <>{m.product_sku}</> },
    { key: "name", header: "الصنف",
      render: (m) => (
        // task16 A4: اسم الصنف رابط يفتح صفحة الأصناف
        m.product_name ? (
          <button
            type="button"
            className="text-blue-700 hover:underline text-right"
            onClick={() => openInNewTab(productPath())}
            title="فتح الأصناف"
          >
            {m.product_name}
          </button>
        ) : <>—</>
      ) },
    { key: "type", header: "النوع", width: "90px",
      render: (m) => {
        const label = m.movement_type_display || TYPES[m.movement_type] || m.movement_type;
        const isIn = m.movement_type.includes("IN") || m.movement_type === "IN";
        return <span style={{ color: isIn ? "var(--aseel-ok, #267346)" : "var(--aseel-danger, #c00)" }}>{label}</span>;
      }
    },
    { key: "qty", header: "الكمية", width: "80px", align: "center", numeric: true,
      render: (m) => <>{formatQuantity(m.quantity)}</> },
    { key: "cost", header: "سعر الوحدة", width: "100px", align: "center", numeric: true,
      render: (m) => <>{fmt(m.unit_cost)}</> },
    { key: "total", header: "الإجمالي", width: "110px", align: "center", numeric: true,
      render: (m) => <>{fmt(m.total_cost)}</> },
    { key: "ref", header: "المرجع", width: "90px",
      render: (m) => {
        // task16 A5: مرجع الفاتورة في حركات المخزن رابط يفتح الفاتورة
        const href = invoicePathForReference(m.reference_type, m.reference_id);
        const label = m.reference_type_display || m.reference_type;
        if (!href) return <>{label}</>;
        return (
          <button
            type="button"
            className="text-blue-700 hover:underline"
            onClick={() => openInNewTab(href)}
            title="فتح الفاتورة المرتبطة"
          >
            {label}{m.reference_id ? ` #${m.reference_id}` : ""}
          </button>
        );
      } },
    { key: "origin", header: "المصدر", width: "90px", align: "center",
      render: (m) => {
        if (m.origin === "international")
          return <span style={{ color: "#1d4ed8", fontWeight: 600 }}>دولي</span>;
        if (m.origin === "local")
          return <span style={{ color: "#166534", fontWeight: 600 }}>محلي</span>;
        return <>—</>;
      } },
    { key: "notes", header: "ملاحظات",
      render: (m) => <>{m.notes || "—"}</> },
  ];

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }} data-skin="aseel">
      {/* شريط الفلاتر */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          حركات المخازن
        </strong>
        <select className="aseel-input" style={{ width: 170 }}
          value={filterProduct} onChange={(e) => setFilterProduct(e.target.value)}>
          <option value="">كل الأصناف</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>{p.sku} — {p.name_ar || p.name_en || "—"}</option>
          ))}
        </select>
        <select className="aseel-input" style={{ width: 130 }}
          value={filterType} onChange={(e) => setFilterType(e.target.value)}>
          <option value="">كل الأنواع</option>
          {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="aseel-input" style={{ width: 120 }}
          value={filterOrigin} onChange={(e) => setFilterOrigin(e.target.value)} title="مصدر البضاعة">
          <option value="">كل المصادر</option>
          <option value="local">محلي (شراء)</option>
          <option value="international">دولي (استيراد)</option>
        </select>
        <input className="aseel-input" style={{ width: 120 }} type="date"
          value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} title="من تاريخ" />
        <input className="aseel-input" style={{ width: 120 }} type="date"
          value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} title="إلى تاريخ" />
        <button className="aseel-toolbtn" onClick={load} title="تطبيق الفلاتر">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <div style={{ flex: 1 }} />
        <button className="aseel-toolbtn" onClick={() => { setShowForm(true); setErr(null); }} title="إضافة حركة (Ctrl+Ins)">
          <Plus className="h-4 w-4" /> إضافة حركة
        </button>
      </div>

      {err && <div className="aseel-banner aseel-banner--err">{err}</div>}

      <AseelDenseTable<StockMovementDto>
        columns={columns}
        rows={movements}
        getRowKey={(m) => m.id}
        loading={loading}
        emptyHint="لا توجد حركات في النطاق المحدد"
      />

      {/* نموذج إضافة حركة يدوية */}
      {showForm && (
        <div className="aseel-picker-mask" data-skin="aseel" data-aseel-modal="1">
          <div className="aseel-picker" role="dialog" aria-modal="true" aria-label="إضافة حركة مخزن"
            style={{ width: "min(520px, 96vw)" }}>
            <div className="aseel-picker-head">
              <span>إضافة حركة مخزن يدوية</span>
              <button type="button" className="aseel-toolbtn" onClick={() => setShowForm(false)}><X /></button>
            </div>
            <div className="aseel-picker-body" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, padding: 10 }}>
              <label className="aseel-field" style={{ gridColumn: "1/-1" }}>
                <span className="aseel-field-label">الصنف</span>
                <select className="aseel-input" value={form.product}
                  onChange={(e) => setForm((f) => ({ ...f, product: e.target.value }))}>
                  <option value="">— اختر صنفاً —</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>{p.sku} — {p.name_ar || p.name_en}</option>
                  ))}
                </select>
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">نوع الحركة</span>
                <select className="aseel-input" value={form.movement_type}
                  onChange={(e) => setForm((f) => ({ ...f, movement_type: e.target.value }))}>
                  {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">التاريخ</span>
                <input className="aseel-input" type="date" value={form.movement_date}
                  onChange={(e) => setForm((f) => ({ ...f, movement_date: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">الكمية</span>
                <input className="aseel-input" type="number" min="0" step="0.001"
                  value={form.quantity}
                  onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">سعر الوحدة</span>
                <input className="aseel-input" type="number" min="0" step="0.01"
                  value={form.unit_cost}
                  onChange={(e) => setForm((f) => ({ ...f, unit_cost: e.target.value }))} />
              </label>
              <label className="aseel-field" style={{ gridColumn: "1/-1" }}>
                <span className="aseel-field-label">ملاحظات</span>
                <input className="aseel-input" value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
              </label>
            </div>
            <div className="aseel-picker-foot" style={{ gap: 8 }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setShowForm(false)}><X /> إلغاء</button>
              <button type="button" className="aseel-toolbtn" disabled={busy} onClick={handleCreate}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save />} حفظ
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
