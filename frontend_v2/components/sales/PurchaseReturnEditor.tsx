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
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
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
type Product = {
  id: number;
  name?: string;
  name_ar?: string;
  name_en?: string;
  sku?: string;
  display_name?: string;
  unit_price?: string;
};

/** اسم الصنف للعرض — الأصناف تُعاد بحقول name_ar/display_name/sku لا name. */
const productLabel = (p?: Product): string =>
  (p &&
    (p.display_name || p.name_ar || p.name_en || p.name || p.sku)) ||
  (p ? `#${p.id}` : "");
type PurchaseInvoice = {
  id: number;
  invoice_number: string;
  partner?: number;
  partner_name?: string;
  invoice_date?: string;
  is_posted?: boolean;
  is_return?: boolean;
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
        apiGetList<PurchaseInvoice>("logistics/purchase-invoices/", { tenantId }),
        apiGetList<Partner>("partners/", { tenantId }),
        apiGetList<Product>("inventory/products/", { tenantId }),
      ]);
      if (invs.status === "fulfilled") {
        // مرحّلة فقط، وليست هي نفسها مرجعاً — صالحة كـ«فاتورة أصلية».
        setOriginalInvoices(invs.value.filter((i) => i.is_posted && !i.is_return));
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
      if (inv?.partner) setSupplierId(inv.partner);
    }
  }, [originalInvoiceId, originalInvoices]);

  // نسخ بنود فاتورة الشراء الأصلية (لتعديل الكميات المرتجعة).
  const copyFromOriginal = async () => {
    if (originalInvoiceId === "") {
      setErr("اختر الفاتورة الأصلية أولاً");
      return;
    }
    setErr(null);
    setMsg(null);
    try {
      const inv = await purchaseInvoiceApi.get(Number(originalInvoiceId));
      const copied: ReturnLine[] = (inv.items || [])
        .filter((it) => it.product)
        .map((it, idx) => ({
          _idx: idx,
          product_id: String(it.product),
          product_name: it.product_name || it.name || "",
          quantity: formatQuantity(String(it.quantity ?? "0"), "0"),
          unit_price: formatQuantity(String(it.unit_price ?? "0"), "0"),
          total: (Number(it.quantity) * Number(it.unit_price)).toFixed(2),
        }));
      copied.push({ _idx: copied.length, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" });
      setLines(copied.length > 1 ? copied : lines);
      setMsg("تم نسخ بنود الفاتورة الأصلية — عدّل الكميات المرتجعة.");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر جلب بنود الفاتورة الأصلية.");
    }
  };

  // تعبئة تلقائية لبنود الفاتورة الأصلية فور اختيارها (ما دامت البنود فارغة) —
  // سلوك احترافي: تظهر أصناف الفاتورة جاهزةً لتعديل الكميات المرتجعة.
  useEffect(() => {
    const isEmpty = lines.length === 1 && !lines[0].product_id;
    if (originalInvoiceId !== "" && isEmpty) void copyFromOriginal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originalInvoiceId]);

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
    if (!supplierId) {
      setErr("اختر المورد.");
      return;
    }
    const payloadLines = lines
      .filter((l) => l.product_id && Number(l.quantity) > 0)
      .map((l) => ({
        product: Number(l.product_id),
        quantity: l.quantity,
        unit_price: l.unit_price || "0",
      }));
    if (payloadLines.length === 0) {
      setErr("أضِف بنداً واحداً على الأقل بكمية موجبة.");
      return;
    }
    setSaving(true);
    setErr(null);
    setMsg(null);
    const tenantId = resolveTenantId();
    try {
      // مرجع الشراء: يُخرج الكمية من المخزن (RETURN_OUT) ويُرحّل قيداً عكسياً
      // (مدين ذمم المورد / دائن مخزون + ض.مدخلات) فيقلّ ما نَدين به للمورد.
      const payload = {
        original_invoice: originalInvoiceId || null,
        supplier: supplierId,
        return_date: returnDate,
        reason: reason || "",
        lines: payloadLines,
      };
      const ret = await apiPostObject<{ invoice_number?: string }>(
        "logistics/purchase-invoices/returns/", payload, { tenantId }
      );
      const num = ret?.invoice_number ? ` رقم ${ret.invoice_number}` : "";
      setMsg(
        `✓ تم حفظ مرجع الشراء${num} كمسودة. افتحه من «فواتير الشراء» واضغط «ترحيل» ` +
        "لإخراج الكمية وتخفيض ذمم المورد."
      );
      setLines([{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]);
      setOriginalInvoiceId("");
      setReason("");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ/ترحيل مرجع الشراء.");
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

  gridColumns[1].render = (row) => (
    <select
      className="aseel-input"
      value={row.product_id}
      onChange={(e) => {
        const p = products.find((x) => String(x.id) === e.target.value);
        updateLine(row._idx, {
          product_id: e.target.value,
          product_name: productLabel(p),
          unit_price: formatQuantity(row.unit_price || p?.unit_price || "0", "0"),
        });
      }}
    >
      <option value="">— اختر —</option>
      {products.map((p) => <option key={p.id} value={p.id}>{productLabel(p)}</option>)}
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
      label: saving ? "..." : "حفظ المرجع كمسودة (F12)",
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
            <span className="aseel-num font-bold">{formatMoney(totalAmount)}</span>
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
                    {i.invoice_number} ({i.partner_name || `#${i.partner ?? "?"}`})
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
            <span className="aseel-status-item">الإجمالي <b className="aseel-num">{formatMoney(totalAmount)}</b></span>
          </>
        }
      />
    </div>
  );
};
