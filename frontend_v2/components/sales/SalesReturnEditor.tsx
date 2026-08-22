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
  createSalesInvoice,
  getSalesInvoice,
  type SalesInvoiceRow,
} from "../../services/salesApi";
import { apiGetList } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
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
      // T-RETPARTY: سقطت قائمة العملاء (500 صفّاً) من الإقلاع — العميل مشتقٌّ
      // من الفاتورة الأصلية، فلا قائمةَ يُختار منها.
      const [invs, prods] = await Promise.allSettled([
        apiGetList<SalesInvoiceRow>("sales/invoices/lookup/?limit=500&status=posted", { tenantId }),
        listPickerProducts<Product>(tenantId),
      ]);
      if (invs.status === "fulfilled") {
        // Only posted invoices are eligible for return
        setOriginalInvoices(invs.value.filter((i) => i.status === "posted"));
      }
      if (prods.status === "fulfilled") setProducts(prods.value);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /** الفاتورة الأصلية المختارة — مصدر العميل ومصدر عرضه معاً. */
  const selectedOriginal = originalInvoices.find((i) => i.id === originalInvoiceId);

  // Auto-populate partner when original invoice is selected
  useEffect(() => {
    // T-RETPARTY: وإفراغُه مع إفراغ الأصل — عميلٌ عالقٌ من اختيارٍ ملغى كان
    // يبقى في الحمولة بلا حقلٍ يعرضه.
    setPartnerId(selectedOriginal ? selectedOriginal.customer : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Copy lines from original invoice (البنود المباعة فعلاً)
  const copyFromOriginal = async () => {
    if (originalInvoiceId === "") {
      setErr("اختر الفاتورة الأصلية أولاً");
      return;
    }
    setErr(null);
    setMsg(null);
    try {
      const inv = await getSalesInvoice(Number(originalInvoiceId));
      const copied: ReturnLine[] = (inv.lines || []).map((l, idx) => ({
        _idx: idx,
        product_id: String(l.product),
        product_name: l.product_name || "",
        quantity: formatQuantity(l.quantity, "0"),
        unit_price: formatQuantity(l.unit_price, "0"),
        total: (Number(l.quantity) * Number(l.unit_price)).toFixed(2),
      }));
      copied.push({ _idx: copied.length, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" });
      setLines(copied.length > 1 ? copied : lines);
      setMsg("تم نسخ بنود الفاتورة الأصلية — عدّل الكميات المرتجعة.");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر جلب بنود الفاتورة الأصلية.");
    }
  };

  // تعبئة تلقائية لبنود الفاتورة الأصلية فور اختيارها (ما دامت البنود فارغة).
  useEffect(() => {
    const isEmpty = lines.length === 1 && !lines[0].product_id;
    if (originalInvoiceId !== "" && isEmpty) void copyFromOriginal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originalInvoiceId]);

  const submit = async () => {
    if (!originalInvoiceId || !partnerId) {
      setErr("اختر الفاتورة الأصلية — العميل يتبعها.");
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
    try {
      // مرجع البيع = فاتورة بيع من نوع sale_return مربوطة بأصلها. الترحيل يعكس
      // القيد (دائن ذمم / مدين إيراد) ويُعيد الكمية للمخزون (RETURN_IN).
      const created = await createSalesInvoice({
        invoice_kind: "sale_return",
        original_invoice: Number(originalInvoiceId),
        customer: partnerId,
        invoice_date: returnDate,
        invoice_type: "credit",
        stock_on_post: true,
        notes: reason || "",
        lines: payloadLines,
      });
      const num = created?.invoice_number ? ` رقم ${created.invoice_number}` : "";
      setMsg(
        `✓ تم حفظ مرجع البيع${num} كمسودة. افتحه من «فواتير المبيعات» واضغط «ترحيل» ` +
        "لإعادة الكمية للمخزون وتخفيض ذمم العميل."
      );
      setLines([{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]);
      setOriginalInvoiceId("");
      setReason("");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ/ترحيل مرجع البيع.");
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
            product_name: productLabel(p),
            unit_price: formatQuantity(row.unit_price || p?.unit_price || "0", "0"),
          });
        }}
      >
        <option value="">— اختر —</option>
        {products.map((p) => (
          <option key={p.id} value={p.id}>{productLabel(p)}</option>
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
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
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
            {/* T-RETPARTY: العميل **مشتقٌّ** من الفاتورة الأصلية لا مُختار.
                كان قائمةً حرّة تُعبَّأ تلقائياً ثم تُترَك مفتوحة، فيمكن ربط
                مرجع فاتورة زيدٍ بذمم عمرو — نقصُ دينِ من لم يُرجِع شيئاً.
                الحارس الحقيقي في الخادم (`SalesInvoiceSerializer.validate`)،
                وهذا وجهه: لا يُعرض إلا الجواب الواحد الصحيح. */}
            <label className="aseel-field" style={{ minWidth: "180px" }}>
              <span className="aseel-field-label">العميل</span>
              <input
                className="aseel-input"
                readOnly
                data-testid="return-customer"
                title="يتبع الفاتورة الأصلية — لا يُختار"
                value={selectedOriginal?.customer_name || (partnerId !== "" ? `#${partnerId}` : "")}
                placeholder="— يتبع الفاتورة الأصلية —"
              />
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
