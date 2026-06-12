/**
 * N4-T8 — PurchaseReturnEditor (N-F3، جديد) «مرجع الشراء»
 * Ref: task5.md:741-742 + الفواتير.txt:1-8
 *
 * مرآة N4-T7 لكن لـ Purchase (شراء بدل بيع):
 *   - invoice_kind='purchase_return' + original_invoice (purchase) FK
 *   - post: عَكس قيد فاتورة الشراء الأصلية + إنقاص المخزون + إنقاص الدفع للمورد
 *   - (Dr AP / Cr Purchase Return Cost)
 *
 * يَعتمد على N8-T11 backend.
 */
import React, { useEffect, useState, useCallback } from "react";
import { apiGetList, apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  AseelDocumentShell,
  AseelGrid,
  useAseelKeymap,
  type AseelGridColumn,
  type AseelToolbarAction,
  type AseelTab,
} from "../aseel";
import { Plus, Save, X, RefreshCw, AlertTriangle, Trash2 } from "lucide-react";

type Partner = { id: number; name: string };
type Product = { id: number; name: string; unit_price?: string };
type PurchaseInvoice = {
  id: number;
  invoice_number: string;
  supplier?: number;
  supplier_name?: string;
  invoice_date?: string;
  status?: string;
};

interface ReturnLine {
  _idx: number;
  product_id: string;
  product_name: string;
  quantity: string;
  unit_price: string;
  total: string;
}

interface Props {
  onBack?: () => void;
}

export const PurchaseReturnEditor: React.FC<Props> = ({ onBack }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [originalInvoices, setOriginalInvoices] = useState<PurchaseInvoice[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [originalInvoiceId, setOriginalInvoiceId] = useState<number | "">("");
  const [returnDate, setReturnDate] = useState(today);
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState<ReturnLine[]>([
    { _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" },
  ]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [invs, parts, prods] = await Promise.allSettled([
        apiGetList<PurchaseInvoice>("purchase/invoices/", { tenantId }),
        apiGetList<Partner>("partners/", { tenantId }),
        apiGetList<Product>("inventory/products/", { tenantId }),
      ]);
      if (invs.status === "fulfilled") {
        setOriginalInvoices(invs.value.filter((i) => i.status === "posted"));
      }
      if (parts.status === "fulfilled") setPartners(parts.value.filter((p) => true));
      if (prods.status === "fulfilled") setProducts(prods.value);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (originalInvoiceId !== "") {
      const inv = originalInvoices.find((i) => i.id === originalInvoiceId);
      if (inv?.supplier) setSupplierId(inv.supplier);
    }
  }, [originalInvoiceId, originalInvoices]);

  const updateLine = (i: number, patch: Partial<ReturnLine>) => {
    setLines((prev) => {
      const next = [...prev];
      const row = { ...next[i], ...patch };
      const q = Number(row.quantity) || 0;
      const p = Number(row.unit_price) || 0;
      row.total = (q * p).toFixed(2);
      next[i] = row;
      if (i === next.length - 1 && (row.product_id || row.quantity)) {
        next.push({ _idx: next.length, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" });
      }
      return next;
    });
  };

  const removeLine = (i: number) => {
    setLines((prev) => {
      const next = prev.filter((_, idx) => idx !== i).map((l, idx) => ({ ...l, _idx: idx }));
      return next.length ? next : [{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }];
    });
  };

  const totalAmount = lines.reduce((s, l) => s + (Number(l.total) || 0), 0);

  const submit = async () => {
    if (!originalInvoiceId || !supplierId || lines.length === 0) {
      setErr("الفاتورة الأصلية + المورد + بند واحد على الأقل");
      return;
    }
    setSaving(true);
    setErr(null);
    setMsg(null);
    const tenantId = resolveTenantId();
    try {
      const payload = {
        invoice_kind: "purchase_return",
        original_invoice: originalInvoiceId,
        return_date: returnDate,
        supplier: supplierId,
        reason: reason || null,
        lines: lines
          .filter((l) => l.product_id && Number(l.quantity) > 0)
          .map((l) => ({
            product: Number(l.product_id),
            quantity: l.quantity,
            unit_price: l.unit_price,
            line_total: l.total,
          })),
      };
      await apiPostObject("purchase/returns/", payload, { tenantId });
      setMsg("✓ تم إنشاء مرجع الشراء — في انتظار الترحيل (يَنتظر N8-T11)");
      setLines([{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]);
    } catch (e: unknown) {
      setErr(
        e instanceof Error
          ? `${e.message} (يَتطلب N8-T11 backend)`
          : "فشل الحفظ — يَتطلب N8-T11 backend"
      );
    } finally {
      setSaving(false);
    }
  };

  useAseelKeymap({
    Escape: onBack || (() => undefined),
    F12: () => void submit(),
    F5: () => void load(),
  });

  const gridColumns: AseelGridColumn<ReturnLine>[] = [
    { key: "seq", header: "#", width: "40px", align: "center", readOnly: true },
    { key: "product", header: "الصنف", width: "30%" },
    { key: "quantity", header: "الكمية", width: "100px", align: "center", type: "number" },
    { key: "unit_price", header: "سعر الوحدة", width: "120px", align: "center", type: "number" },
    { key: "total", header: "الإجمالي", width: "120px", align: "center", readOnly: true },
    { key: "del", header: "", width: "40px", align: "center" },
  ];

  const getCell = (row: ReturnLine, key: string): string | number => {
    switch (key) {
      case "seq": return row._idx + 1;
      case "quantity": return row.quantity;
      case "unit_price": return row.unit_price;
      case "total": return row.total;
      default: return "";
    }
  };

  gridColumns[1].render = (row) => (
    <select
      className="aseel-input"
      value={row.product_id}
      onChange={(e) => {
        const p = products.find((x) => String(x.id) === e.target.value);
        updateLine(row._idx, {
          product_id: e.target.value,
          product_name: p?.name || "",
          unit_price: row.unit_price || p?.unit_price || "0",
        });
      }}
    >
      <option value="">— اختر —</option>
      {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );

  gridColumns[5].render = (row) =>
    lines.length > 1 ? (
      <button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => removeLine(row._idx)}>
        <Trash2 className="w-3 h-3" />
      </button>
    ) : null;

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    if (key === "quantity") updateLine(rowIndex, { quantity: value });
    else if (key === "unit_price") updateLine(rowIndex, { unit_price: value });
  };

  const actions: AseelToolbarAction[] = [
    {
      key: "save",
      label: saving ? "..." : "حفظ مرجع الشراء (F12)",
      icon: <Save />,
      onClick: () => void submit(),
      disabled: saving,
    },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    ...(onBack ? [{ key: "back", label: "خروج", icon: <X />, onClick: onBack, danger: true } as AseelToolbarAction] : []),
  ];

  const tabs: AseelTab[] = [
    {
      key: "main",
      label: "بيانات المرجع",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}><AlertTriangle className="w-3 h-3 inline" /> {err}</div>}
          {msg && <div className="aseel-banner" style={{ marginBottom: "8px", color: "var(--aseel-ok, #2d7d46)" }}>{msg}</div>}

          <div className="aseel-banner" style={{ marginBottom: "12px", background: "var(--aseel-surface-2, #f4ede0)", fontSize: "11px", padding: "8px 12px" }}>
            <AlertTriangle className="w-3 h-3 inline" style={{ marginInlineEnd: "4px", color: "var(--aseel-warn, #b06800)" }} />
            هذه الصفحة تَتَطلب backend N8-T11 (invoice_kind='purchase_return' + reverse-post للمورد).
          </div>

          <AseelGrid<ReturnLine>
            columns={gridColumns}
            rows={lines}
            getCell={getCell}
            getRowKey={(r) => r._idx}
            onChange={gridOnChange}
            onAddRow={() => setLines((prev) => [...prev, { _idx: prev.length, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }])}
            emptyHint="ابدأ إدخال البنود المرتجعة للمورد"
          />

          <div className="aseel-total-row aseel-total-row--grand" style={{ marginTop: "8px", padding: "8px 12px" }}>
            <span>إجمالي المرجوع للمورد</span>
            <span className="aseel-num font-bold">{totalAmount.toFixed(2)}</span>
          </div>

          <div style={{ marginTop: "12px" }}>
            <label className="aseel-field">
              <span className="aseel-field-label">سبب الإرجاع للمورد</span>
              <textarea className="aseel-input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="عيب جودة / كميات زائدة / ..." />
            </label>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="مرجع الشراء (Purchase Return)"
        state={originalInvoiceId ? `للفاتورة #${originalInvoiceId}` : "مرجع جديد"}
        actions={actions}
        header={
          <>
            <label className="aseel-field">
              <span className="aseel-field-label">تاريخ المرجوع</span>
              <input type="date" className="aseel-input" value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
            </label>
            <label className="aseel-field" style={{ minWidth: "200px" }}>
              <span className="aseel-field-label">فاتورة الشراء الأصلية *</span>
              <select
                className="aseel-input"
                value={originalInvoiceId}
                onChange={(e) => setOriginalInvoiceId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">— اختر —</option>
                {originalInvoices.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.invoice_number} ({i.supplier_name || `#${i.supplier ?? "?"}`})
                  </option>
                ))}
              </select>
            </label>
            <label className="aseel-field" style={{ minWidth: "180px" }}>
              <span className="aseel-field-label">المورد</span>
              <select
                className="aseel-input"
                value={supplierId}
                onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">— اختر —</option>
                {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
          </>
        }
        tabs={tabs}
        status={
          <>
            <span className="aseel-status-item">عدد البنود <b>{lines.filter((l) => l.product_id).length}</b></span>
            <span className="aseel-status-item">الإجمالي <b className="aseel-num">{totalAmount.toFixed(2)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>
              مسودة — يَنتظر N8-T11
            </span>
          </>
        }
      />
    </div>
  );
};
