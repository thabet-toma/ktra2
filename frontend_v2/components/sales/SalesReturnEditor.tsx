/**
 * N4-T7 — SalesReturnEditor (N-F2، جديد) «مرجع البيع»
 * Ref: task5.md:732-739 + الفواتير.txt:1-8
 *
 * نفس SalesInvoiceEditor بنياً مع invoice_kind='sale_return' +
 *   original_invoice FK + (اختياري) نَسخ البنود من الأصلية.
 * post: يَعكس قيد الفاتورة الأصلية + يُعيد للمخزون + يُرجع للمدفوع.
 *
 * يَعتمد على N8-T11 backend (invoice_kind + original_invoice + reverse_post logic).
 * حالياً: UI كاملة + إشارة لاعتماد backend.
 */
import React, { useEffect, useState, useCallback } from "react";
import {
  listSalesInvoices,
  type SalesInvoiceRow,
} from "../../services/salesApi";
import { apiGetList, apiPostObject } from "../../services/restApi";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  AseelDocumentShell,
  AseelDenseTable,
  AseelGrid,
  useAseelKeymap,
  type AseelGridColumn,
  type AseelToolbarAction,
  type AseelTab,
  type DenseColumn,
} from "../aseel";
import { Plus, Save, X, RefreshCw, AlertTriangle, Search, Trash2 } from "lucide-react";

type Partner = { id: number; name: string };
type Product = { id: number; name: string; unit_price?: string };

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

export const SalesReturnEditor: React.FC<Props> = ({ onBack }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [originalInvoices, setOriginalInvoices] = useState<SalesInvoiceRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // Form state
  const [originalInvoiceId, setOriginalInvoiceId] = useState<number | "">("");
  const [returnDate, setReturnDate] = useState(today);
  const [partnerId, setPartnerId] = useState<number | "">("");
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState<ReturnLine[]>([
    { _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" },
  ]);
  const [showPicker, setShowPicker] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [invs, parts, prods] = await Promise.allSettled([
        listSalesInvoices(),
        apiGetList<Partner>("partners/", { tenantId }),
        apiGetList<Product>("inventory/products/", { tenantId }),
      ]);
      if (invs.status === "fulfilled") {
        // Only posted invoices are eligible for return
        setOriginalInvoices(invs.value.filter((i) => i.status === "posted"));
      }
      if (parts.status === "fulfilled") setPartners(parts.value);
      if (prods.status === "fulfilled") setProducts(prods.value);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Auto-populate partner when original invoice is selected
  useEffect(() => {
    if (originalInvoiceId !== "") {
      const inv = originalInvoices.find((i) => i.id === originalInvoiceId);
      if (inv) setPartnerId(inv.customer);
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

  // Copy lines from original invoice
  const copyFromOriginal = async () => {
    if (originalInvoiceId === "") {
      setErr("اختر الفاتورة الأصلية أولاً");
      return;
    }
    setErr(null);
    // Note: backend would expose getSalesInvoice(id) returning lines.
    // For now, this is a placeholder. The form starts empty until N8-T11.
    setMsg("نسخ البنود من الفاتورة الأصلية يَتطلب backend N8-T11. أَدخل البنود يدوياً.");
  };

  const submit = async () => {
    if (!originalInvoiceId || !partnerId || lines.length === 0) {
      setErr("الفاتورة الأصلية + العميل + بند واحد على الأقل");
      return;
    }
    setSaving(true);
    setErr(null);
    setMsg(null);
    const tenantId = resolveTenantId();
    try {
      // N8-T11 backend endpoint (assumed)
      const payload = {
        invoice_kind: "sale_return",
        original_invoice: originalInvoiceId,
        return_date: returnDate,
        customer: partnerId,
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
      await apiPostObject("sales/returns/", payload, { tenantId });
      setMsg("✓ تم إنشاء مرجع البيع — في انتظار الترحيل (يَنتظر backend N8-T11)");
      setLines([{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]);
    } catch (e: unknown) {
      setErr(
        e instanceof Error
          ? `${e.message} (يَتطلب N8-T11 backend: invoice_kind + reverse-post)`
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
      case "total": return formatMoney(row.total);
      default: return "";
    }
  };

  const renderProductCell = (row: ReturnLine) => {
    const prod = products.find((p) => String(p.id) === row.product_id);
    return (
      <select
        className="aseel-input"
        value={row.product_id}
        onChange={(e) => {
          const p = products.find((x) => String(x.id) === e.target.value);
          updateLine(row._idx, {
            product_id: e.target.value,
            product_name: p?.name || "",
            unit_price: formatQuantity(row.unit_price || p?.unit_price || "0", "0"),
          });
        }}
      >
        <option value="">— اختر —</option>
        {products.map((p) => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>
    );
  };

  const renderDelCell = (row: ReturnLine) =>
    lines.length > 1 ? (
      <button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => removeLine(row._idx)} title="حذف">
        <Trash2 className="w-3 h-3" />
      </button>
    ) : null;

  gridColumns[1].render = renderProductCell;
  gridColumns[5].render = renderDelCell;

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    if (key === "quantity") updateLine(rowIndex, { quantity: value });
    else if (key === "unit_price") updateLine(rowIndex, { unit_price: value });
  };

  const actions: AseelToolbarAction[] = [
    {
      key: "save",
      label: saving ? "..." : "حفظ مرجع البيع (F12)",
      icon: <Save />,
      onClick: () => void submit(),
      disabled: saving,
    },
    {
      key: "copy",
      label: "نسخ البنود من الأصلية",
      icon: <Plus />,
      onClick: () => void copyFromOriginal(),
      separatorBefore: true,
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
            هذه الصفحة تَتَطلب backend N8-T11 (invoice_kind='sale_return' + reverse-post).
            UI كاملة وتَرسل payload صحيح، الحفظ يَنتظر backend.
          </div>

          <AseelGrid<ReturnLine>
            columns={gridColumns}
            rows={lines}
            getCell={getCell}
            getRowKey={(r) => r._idx}
            onChange={gridOnChange}
            onAddRow={() => setLines((prev) => [...prev, { _idx: prev.length, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }])}
            emptyHint="ابدأ إدخال بنود المرجوع"
          />

          <div className="aseel-total-row aseel-total-row--grand" style={{ marginTop: "8px", padding: "8px 12px" }}>
            <span>إجمالي المرجوع</span>
            <span className="aseel-num font-bold">{formatMoney(totalAmount)}</span>
          </div>

          <div style={{ marginTop: "12px" }}>
            <label className="aseel-field">
              <span className="aseel-field-label">سبب المرجوع</span>
              <textarea className="aseel-input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="عيب جودة / طلب العميل / ..." />
            </label>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="مرجع البيع (Sale Return)"
        state={originalInvoiceId ? `للفاتورة #${originalInvoiceId}` : "مرجع جديد"}
        actions={actions}
        header={
          <>
            <label className="aseel-field">
              <span className="aseel-field-label">تاريخ المرجوع</span>
              <input type="date" className="aseel-input" value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
            </label>
            <label className="aseel-field" style={{ minWidth: "180px" }}>
              <span className="aseel-field-label">الفاتورة الأصلية *</span>
              <select
                className="aseel-input"
                value={originalInvoiceId}
                onChange={(e) => setOriginalInvoiceId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">— اختر —</option>
                {originalInvoices.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.invoice_number} ({i.customer_name || `#${i.customer}`})
                  </option>
                ))}
              </select>
            </label>
            <label className="aseel-field" style={{ minWidth: "180px" }}>
              <span className="aseel-field-label">العميل</span>
              <select
                className="aseel-input"
                value={partnerId}
                onChange={(e) => setPartnerId(e.target.value ? Number(e.target.value) : "")}
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
            <span className="aseel-status-item">الإجمالي <b className="aseel-num">{formatMoney(totalAmount)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>
              مسودة — يَنتظر N8-T11
            </span>
          </>
        }
      />
    </div>
  );
};
