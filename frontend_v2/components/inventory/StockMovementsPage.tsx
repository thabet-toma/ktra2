import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import type { StockMovementDto, SqlProduct } from "../../types/inventory";
import { KitDenseTable, type DenseColumn } from "../kit/KitDenseTable";
import { KitDocumentShell, type KitToolbarAction } from "../kit/KitDocumentShell";
import { Plus, RefreshCw, X, Save, Loader2, Warehouse as WhIcon } from "lucide-react";
import { invoicePathForReference, productProfilePath } from "../../utils/entityLinks";
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

  // صيانة الأداء 2026-07: سجل الحركات جدول متنامٍ بلا حد — ترقيم دفعات 100
  // بدل جلبه كاملاً بكل تحميل. الفلاتر تبقى على الخادم.
  const PAGE_SIZE = 100;
  const [totalCount, setTotalCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageRef = useRef(1);

  const buildParams = useCallback((page: number): Record<string, string> => {
    const params: Record<string, string> = {
      page: String(page),
      page_size: String(PAGE_SIZE),
    };
    if (filterProduct) params.product = filterProduct;
    if (filterType) params.movement_type = filterType;
    if (filterOrigin) params.origin = filterOrigin;
    if (filterDateFrom) params.date_from = filterDateFrom;
    if (filterDateTo) params.date_to = filterDateTo;
    return params;
  }, [filterProduct, filterType, filterOrigin, filterDateFrom, filterDateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      pageRef.current = 1;
      const [mvs, prods] = await Promise.all([
        inventoryApi.getStockMovementsPaged(buildParams(1)),
        inventoryApi.getProducts(),
      ]);
      setMovements(mvs.results as StockMovementDto[]);
      setTotalCount(mvs.count);
      setHasNext(mvs.hasNext);
      setProducts(prods as SqlProduct[]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const next = pageRef.current + 1;
      const mvs = await inventoryApi.getStockMovementsPaged(buildParams(next));
      pageRef.current = next;
      setMovements((prev) => [...prev, ...(mvs.results as StockMovementDto[])]);
      setTotalCount(mvs.count);
      setHasNext(mvs.hasNext);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoadingMore(false);
    }
  }, [buildParams, loadingMore]);

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
        // task16 A4: اسم الصنف رابط يفتح بطاقة الصنف على «حركة المخزون» مباشرة
        m.product_name ? (
          <button
            type="button"
            className="text-blue-700 hover:underline text-right"
            onClick={() => openInNewTab(productProfilePath(m.product))}
            title="فتح حركة مخزون الصنف"
          >
            {m.product_name}
          </button>
        ) : <>—</>
      ) },
    { key: "type", header: "النوع", width: "90px",
      render: (m) => {
        const label = m.movement_type_display || TYPES[m.movement_type] || m.movement_type;
        const isIn = m.movement_type.includes("IN") || m.movement_type === "IN";
        return <span className={isIn ? "ktra-text-ok" : "ktra-text-danger"}>{label}</span>;
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
          return <span className="font-semibold text-[var(--color-primary)]">دولي</span>;
        if (m.origin === "local")
          return <span className="font-semibold text-[var(--color-success)]">محلي</span>;
        return <>—</>;
      } },
    { key: "notes", header: "ملاحظات",
      render: (m) => <>{m.notes || "—"}</> },
  ];

  /* T-WIN M7: كانت الشاشة `div` بأنماط inline خارج الغلاف الموحّد. صارت
     `KitDocumentShell` كبقية الشاشات — النصوص كما هي، والإطار وحده تغيّر. */
  const actions: KitToolbarAction[] = [
    {
      key: "apply",
      label: "تطبيق الفلاتر",
      icon: <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />,
      onClick: load,
    },
    {
      key: "add",
      label: "إضافة حركة",
      icon: <Plus className="h-4 w-4" />,
      onClick: () => { setShowForm(true); setErr(null); },
      separatorBefore: true,
    },
  ];

  return (
    <KitDocumentShell
      title="حركات المخازن"
      actions={actions}
      status={(
        <span className="ktra-status-item">
          المعروض: <b>{movements.length}</b> من <b>{totalCount}</b>
        </span>
      )}
      header={(
        <div className="flex flex-wrap items-center gap-1.5">
          <select className="ktra-input w-[170px]"
            value={filterProduct} onChange={(e) => setFilterProduct(e.target.value)}>
            <option value="">كل الأصناف</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.sku} — {p.name_ar || p.name_en || "—"}</option>
            ))}
          </select>
          <select className="ktra-input w-[130px]"
            value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="">كل الأنواع</option>
            {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="ktra-input w-[120px]"
            value={filterOrigin} onChange={(e) => setFilterOrigin(e.target.value)} title="مصدر البضاعة">
            <option value="">كل المصادر</option>
            <option value="local">محلي (شراء)</option>
            <option value="international">دولي (استيراد)</option>
          </select>
          <input className="ktra-input w-[120px]" type="date"
            value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} title="من تاريخ" />
          <input className="ktra-input w-[120px]" type="date"
            value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} title="إلى تاريخ" />
        </div>
      )}
    >
      {err && <div className="ktra-banner ktra-banner--err">{err}</div>}

      <KitDenseTable<StockMovementDto>
        columns={columns}
        rows={movements}
        getRowKey={(m) => m.id}
        loading={loading}
        emptyHint="لا توجد حركات في النطاق المحدد"
      />

      {hasNext && (
        <div className="flex justify-center p-2">
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={loadingMore}
            onClick={() => void loadMore()}
          >
            {loadingMore
              ? "جاري التحميل…"
              : `تحميل المزيد (${movements.length} من ${totalCount})`}
          </button>
        </div>
      )}

      {/* نموذج إضافة حركة يدوية */}
      {showForm && (
        <div className="ktra-picker-mask" data-ktra-modal="1">
          <div className="ktra-picker w-[min(520px,96vw)]" role="dialog" aria-modal="true" aria-label="إضافة حركة مخزن"
            >
            <div className="ktra-picker-head">
              <span>إضافة حركة مخزن يدوية</span>
              <button type="button" className="ktra-toolbtn" onClick={() => setShowForm(false)}><X /></button>
            </div>
            <div className="ktra-picker-body grid grid-cols-2 gap-2 p-2.5">
              <label className="ktra-field col-span-2">
                <span className="ktra-field-label">الصنف</span>
                <select className="ktra-input" value={form.product}
                  onChange={(e) => setForm((f) => ({ ...f, product: e.target.value }))}>
                  <option value="">— اختر صنفاً —</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>{p.sku} — {p.name_ar || p.name_en}</option>
                  ))}
                </select>
              </label>
              <label className="ktra-field">
                <span className="ktra-field-label">نوع الحركة</span>
                <select className="ktra-input" value={form.movement_type}
                  onChange={(e) => setForm((f) => ({ ...f, movement_type: e.target.value }))}>
                  {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="ktra-field">
                <span className="ktra-field-label">التاريخ</span>
                <input className="ktra-input" type="date" value={form.movement_date}
                  onChange={(e) => setForm((f) => ({ ...f, movement_date: e.target.value }))} />
              </label>
              <label className="ktra-field">
                <span className="ktra-field-label">الكمية</span>
                <input className="ktra-input" type="number" min="0" step="0.001"
                  value={form.quantity}
                  onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} />
              </label>
              <label className="ktra-field">
                <span className="ktra-field-label">سعر الوحدة</span>
                <input className="ktra-input" type="number" min="0" step="0.01"
                  value={form.unit_cost}
                  onChange={(e) => setForm((f) => ({ ...f, unit_cost: e.target.value }))} />
              </label>
              <label className="ktra-field col-span-2">
                <span className="ktra-field-label">ملاحظات</span>
                <input className="ktra-input" value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
              </label>
            </div>
            <div className="ktra-picker-foot gap-2">
              <button type="button" className="ktra-toolbtn" onClick={() => setShowForm(false)}><X /> إلغاء</button>
              <button type="button" className="ktra-toolbtn" disabled={busy} onClick={handleCreate}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save />} حفظ
              </button>
            </div>
          </div>
        </div>
      )}
    </KitDocumentShell>
  );
};
