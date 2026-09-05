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
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { apiGetList, apiPostObject } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { formatTimeValue } from "../../utils/formatDate";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  KitDocumentShell,
  KitGrid,
  useKitKeymap,
  type KitGridColumn,
  type KitToolbarAction,
  type KitTab,
} from "../kit";
import { Plus, Save, X, RefreshCw, AlertTriangle, Trash2, Info, Undo2 } from "lucide-react";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "../../utils/documentDraft";

type Product = {
  id: number;
  name?: string;
  name_ar?: string;
  name_en?: string;
  sku?: string;
  display_name?: string;
  unit_price?: string;
};

/** اسم المنتج للعرض — المنتجات تُعاد بحقول name_ar/display_name/sku لا name. */
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

// W6: صف في منتقي بنود المرجع — المفوتر/المرتجع/المتبقّي + كمية الإرجاع المختارة.
interface PickerRow {
  product: number;
  name: string;
  unit_price: string;
  invoiced_qty: string;
  returned_qty: string;
  remaining_qty: string;
  selected: boolean;
  return_qty: string;
}

interface Props {
  onBack?: () => void;
}

/** ISSUE #121: حمولة المسودّة المحلية — خفيفة تكفي وحدها لإعادة بناء الشاشة
 *  (issue #118)، لا صلة بحمولة الحفظ الخادمية التي يبنيها `submit`. */
interface PurchaseReturnDraftPayload {
  originalInvoiceId: number | "";
  returnDate: string;
  supplierId: number | "";
  supplierName: string;
  reason: string;
  lines: ReturnLine[];
}

export const PurchaseReturnEditor: React.FC<Props> = ({ onBack }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [originalInvoices, setOriginalInvoices] = useState<PurchaseInvoice[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [originalInvoiceId, setOriginalInvoiceId] = useState<number | "">("");
  const [returnDate, setReturnDate] = useState(today);
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [supplierName, setSupplierName] = useState<string>("");
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState<ReturnLine[]>([
    { _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" },
  ]);

  // W6: منتقي بنود المرجع.
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerRows, setPickerRows] = useState<PickerRow[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);

  // ISSUE #121: علامة «لُمِس» — تُرفَع مزامنةً داخل كل معالج تعديل مستخدم (لا
  // مشتقّة داخل useEffect؛ راجع تعليق الخطّاف نفسه: حالةٌ مشتقّة تفوّت بالضبط
  // حالة «عُدِّل مرّةً ثم غادر» التي صُمِّمت الميزة لأجلها).
  const [touched, setTouched] = useState(false);
  const markTouched = () => setTouched(true);
  // شريط اليتامى (issue #119 §٧) — إخفاءٌ محليّ بلا مسّ المسودّات نفسها.
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [invs, prods] = await Promise.allSettled([
        // P0-5: أحدث 200 فاتورة (القائمة مُرقَّمة إلزامياً) — منتقي الأصل.
        apiGetList<PurchaseInvoice>("logistics/purchase-invoices/", { tenantId, query: { page: 1, page_size: 200, is_posted: "true" } }),
        listPickerProducts<Product>(tenantId),
      ]);
      if (invs.status === "fulfilled") {
        // مرحّلة فقط، وليست هي نفسها مرجعاً — صالحة كـ«فاتورة أصلية».
        setOriginalInvoices(invs.value.filter((i) => i.is_posted && !i.is_return));
      }
      if (prods.status === "fulfilled") setProducts(prods.value);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // W7b: المورد موروث من الفاتورة الأصلية (يجب أن يصيب نفس حساب ذمم المورد عند العكس)
  // — يُضبط تلقائياً ويُعرض للقراءة فقط، لا يُحرّره المستخدم.
  useEffect(() => {
    if (originalInvoiceId !== "") {
      const inv = originalInvoices.find((i) => i.id === originalInvoiceId);
      if (inv?.partner) setSupplierId(inv.partner);
      setSupplierName(inv?.partner_name || (inv?.partner ? `#${inv.partner}` : ""));
    } else {
      setSupplierId("");
      setSupplierName("");
    }
  }, [originalInvoiceId, originalInvoices]);

  // W6: فتح منتقي البنود — يجلب المفوتر/المرتجع/المتبقّي من الخادم.
  const openPicker = useCallback(async (invId: number) => {
    setPickerLoading(true);
    setErr(null);
    setMsg(null);
    try {
      const data = await purchaseInvoiceApi.getReturnableLines(invId);
      const rows: PickerRow[] = (data.lines || []).map((l) => ({
        product: l.product,
        name: l.name,
        unit_price: l.unit_price,
        invoiced_qty: l.invoiced_qty,
        returned_qty: l.returned_qty,
        remaining_qty: l.remaining_qty,
        // البنود التي لم يبقَ منها شيء تبدأ غير مختارة ومعطّلة.
        selected: Number(l.remaining_qty) > 0,
        return_qty: formatQuantity(l.remaining_qty, "0"),
      }));
      setPickerRows(rows);
      setPickerOpen(true);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر جلب بنود الفاتورة الأصلية.");
    } finally {
      setPickerLoading(false);
    }
  }, []);

  // فور اختيار الفاتورة الأصلية: افتح المنتقي (بدل نسخ كل الأسطر تلقائياً).
  useEffect(() => {
    if (originalInvoiceId !== "") void openPicker(Number(originalInvoiceId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originalInvoiceId]);

  const setPickerField = (i: number, patch: Partial<PickerRow>) => {
    setPickerRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  // تأكيد المنتقي: البنود المختارة فقط تدخل المرجع، بكميات مقيّدة بالمتبقّي.
  const confirmPicker = () => {
    const chosen = pickerRows.filter(
      (r) => r.selected && Number(r.return_qty) > 0 && Number(r.remaining_qty) > 0,
    );
    if (chosen.length === 0) {
      setErr("اختر بنداً واحداً على الأقل بكمية إرجاع موجبة.");
      return;
    }
    const clamped = chosen.map((r, idx) => {
      const q = Math.min(Number(r.return_qty) || 0, Number(r.remaining_qty) || 0);
      return {
        _idx: idx,
        product_id: String(r.product),
        product_name: r.name,
        quantity: formatQuantity(String(q), "0"),
        unit_price: formatQuantity(r.unit_price, "0"),
        total: (q * (Number(r.unit_price) || 0)).toFixed(2),
      } as ReturnLine;
    });
    setLines(clamped);
    setPickerOpen(false);
    markTouched();
    setMsg("تم اختيار البنود — راجع الكميات ثم احفظ المرتجع.");
  };

  const updateLine = (i: number, patch: Partial<ReturnLine>) => {
    markTouched();
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
    markTouched();
    setLines((prev) => {
      const next = prev.filter((_, idx) => idx !== i).map((l, idx) => ({ ...l, _idx: idx }));
      return next.length ? next : [{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }];
    });
  };

  const totalAmount = lines.reduce((s, l) => s + (Number(l.total) || 0), 0);

  /* ISSUE #121: مسودّة محلية (IndexedDB، issue #118) — هذه الشاشة تُنشئ
   * مرجعاً جديداً دائماً (لا تحرير مرجعٍ قائم)، فـ`docId`/`isPosted`/
   * `docUpdatedAt` ثوابت. الحمولة كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة؛
   * لا صلة بحمولة الحفظ الخادمية التي يبنيها `submit`. */
  const draftPayload = useMemo<PurchaseReturnDraftPayload>(
    () => ({ originalInvoiceId, returnDate, supplierId, supplierName, reason, lines }),
    [originalInvoiceId, returnDate, supplierId, supplierName, reason, lines],
  );

  const onRestoreDraft = useCallback((restored: PurchaseReturnDraftPayload) => {
    setOriginalInvoiceId(restored.originalInvoiceId);
    setReturnDate(restored.returnDate);
    setSupplierId(restored.supplierId);
    setSupplierName(restored.supplierName);
    setReason(restored.reason);
    setLines(restored.lines);
    // استعادةٌ من مسودّة تعني اختلافاً عن الشاشة الفارغة — تُسجَّل «ملموسة»
    // فوراً كي يبقى الحارس وسياسة الحفظ متّسقين مع ما يراه المستخدم فعلاً.
    setTouched(true);
  }, []);

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft<PurchaseReturnDraftPayload>({
    docType: "purchase_return",
    docId: null,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    isPosted: false,
    docUpdatedAt: null,
  });

  /* ISSUE #120: الحارسُ مقلوب — يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ فعلاً. */
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (draftSaveFailed) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [draftSaveFailed]);

  /** «تراجع» على شريط الاستعادة: يعيد الشاشة إلى حالتها الفارغة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    setOriginalInvoiceId("");
    setReturnDate(today);
    setSupplierId("");
    setSupplierName("");
    setReason("");
    setLines([{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]);
    setTouched(false);
    void discardDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [discardDraft]);

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
        `✓ تم حفظ مرتجع الشراء${num} كمسودة. افتحه من «فواتير الشراء» واضغط «ترحيل» ` +
        "لإخراج الكمية وتخفيض ذمم المورد."
      );
      setLines([{ _idx: 0, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]);
      setOriginalInvoiceId("");
      setReason("");
      setTouched(false);
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      void discardDraft();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ/ترحيل مرتجع الشراء.");
    } finally {
      setSaving(false);
    }
  };

  useKitKeymap({
    Escape: onBack || (() => undefined),
    F12: () => void submit(),
    F5: () => void load(),
  });

  const gridColumns: KitGridColumn<ReturnLine>[] = [
    { key: "seq", header: "#", width: "40px", align: "center", readOnly: true },
    { key: "product", header: "المنتج", width: "30%" },
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
      className="ktra-input"
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
      <button type="button" className="ktra-iconbtn ktra-iconbtn--danger" onClick={() => removeLine(row._idx)}>
        <Trash2 className="w-3 h-3" />
      </button>
    ) : null;

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    if (key === "quantity") updateLine(rowIndex, { quantity: value });
    else if (key === "unit_price") updateLine(rowIndex, { unit_price: value });
  };

  const actions: KitToolbarAction[] = [
    {
      key: "save",
      label: saving ? "..." : "حفظ المرتجع كمسودة (F12)",
      icon: <Save />,
      onClick: () => void submit(),
      disabled: saving,
    },
    {
      key: "pick",
      label: "اختيار البنود من الأصلية",
      icon: <Plus />,
      onClick: () => {
        if (originalInvoiceId === "") { setErr("اختر الفاتورة الأصلية أولاً"); return; }
        void openPicker(Number(originalInvoiceId));
      },
      separatorBefore: true,
    },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    ...(onBack ? [{ key: "back", label: "خروج", icon: <X />, onClick: onBack, danger: true } as KitToolbarAction] : []),
  ];

  /* ISSUE #120: الحفظ المحلي فشل فعلاً — لافتةٌ لاصقة تطلب حفظاً يدوياً بدل
   * الانتظار الصامت حتى تحاول المغادرة. */
  const draftSaveFailedBanner = draftSaveFailed ? (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="draft-save-failed-banner"
      className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>تعذّر حفظ نسخة محلية من هذا المستند — اضغط «حفظ» يدوياً كي لا يضيع عملك.</span>
    </div>
  ) : null;

  /* ISSUE #118: شريط الاستعادة التلقائية — بلا لافتة تسأل. المحتوى مُطبَّقٌ
   * على النموذج فعلاً (`onRestoreDraft`) قبل أن يصل هذا الشريط أصلاً. */
  const draftRestoreBanner = draftBanner ? (
    <div
      className="ktra-banner ktra-banner--warn"
      role="status"
      data-testid="draft-restored-banner"
    >
      <Info className="h-4 w-4 shrink-0" />
      <span>
        {draftBanner.eligibility === "restore" &&
          `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "stale" &&
          `تغيّر المستند بعد مسودتك (مسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "posted" &&
          `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) لهذا المستند المرحَّل — للاطّلاع فقط.`}
      </span>
      {draftBanner.eligibility === "restore" && (
        <button type="button" className="ktra-toolbtn" onClick={handleUndoDraft} data-testid="draft-restored-undo">
          <Undo2 className="h-4 w-4" />
          تراجع
        </button>
      )}
      {draftBanner.eligibility === "stale" && (
        <>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => onRestoreDraft(draftBanner.payload)}
            data-testid="draft-stale-preview"
          >
            استعرض مسودتي
          </button>
          <button type="button" className="ktra-toolbtn" onClick={() => void discardDraft()} data-testid="draft-stale-discard">
            تجاهلها
          </button>
        </>
      )}
    </div>
  ) : null;

  /* شريط اليتامى (issue #119 §٧): مسودّات مرجعٍ جديد أخرى تُركت في تبويبات أخرى. */
  const orphanDraftsBanner = orphanDrafts.length > 0 && !orphanBarDismissed ? (
    <div className="ktra-banner" role="status" data-testid="orphan-drafts-banner">
      <Info className="h-4 w-4 shrink-0" />
      <div className="flex flex-col gap-1">
        <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
        <ul className="list-disc pr-4 text-xs">
          {orphanDrafts.map((o) => (
            <li key={o.key}>{formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}</li>
          ))}
        </ul>
      </div>
      <button type="button" className="ktra-toolbtn" onClick={() => setOrphanBarDismissed(true)} data-testid="orphan-drafts-dismiss">
        <X className="h-4 w-4" />
        إخفاء
      </button>
    </div>
  ) : null;

  const tabs: KitTab[] = [
    {
      key: "main",
      label: "بيانات المرتجع",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}><AlertTriangle className="w-3 h-3 inline" /> {err}</div>}
          {msg && <div className="ktra-banner" style={{ marginBottom: "8px", color: "var(--ktra-ok, #2d7d46)" }}>{msg}</div>}

          <KitGrid<ReturnLine>
            columns={gridColumns}
            rows={lines}
            getCell={getCell}
            getRowKey={(r) => r._idx}
            onChange={gridOnChange}
            onAddRow={() => { setLines((prev) => [...prev, { _idx: prev.length, product_id: "", product_name: "", quantity: "1", unit_price: "", total: "0" }]); markTouched(); }}
            emptyHint="ابدأ إدخال البنود المرتجعة للمورد"
          />

          <div className="ktra-total-row ktra-total-row--grand" style={{ marginTop: "8px", padding: "8px 12px" }}>
            <span>إجمالي المرجوع للمورد</span>
            <span className="ktra-num font-bold">{formatMoney(totalAmount)}</span>
          </div>

          <div style={{ marginTop: "12px" }}>
            <label className="ktra-field">
              <span className="ktra-field-label">سبب الإرجاع للمورد</span>
              <textarea className="ktra-input" rows={3} value={reason} onChange={(e) => { setReason(e.target.value); markTouched(); }} placeholder="عيب جودة / كميات زائدة / ..." data-testid="return-reason" />
            </label>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <KitDocumentShell
        title="مرتجع الشراء (Purchase Return)"
        state={originalInvoiceId ? `للفاتورة #${originalInvoiceId}` : "مرتجع جديد"}
        actions={actions}
        header={
          <>
            <label className="ktra-field">
              <span className="ktra-field-label">تاريخ المرجوع</span>
              <input type="date" className="ktra-input" value={returnDate} onChange={(e) => { setReturnDate(e.target.value); markTouched(); }} />
            </label>
            <label className="ktra-field" style={{ minWidth: "200px" }}>
              <span className="ktra-field-label">فاتورة الشراء الأصلية *</span>
              <select
                className="ktra-input"
                value={originalInvoiceId}
                onChange={(e) => { setOriginalInvoiceId(e.target.value ? Number(e.target.value) : ""); markTouched(); }}
              >
                <option value="">— اختر —</option>
                {originalInvoices.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.invoice_number} ({i.partner_name || `#${i.partner ?? "?"}`})
                  </option>
                ))}
              </select>
            </label>
            <label className="ktra-field" style={{ minWidth: "180px" }}>
              <span className="ktra-field-label">المورد (موروث من الفاتورة)</span>
              <input
                className="ktra-input"
                value={supplierName || "— اختر الفاتورة الأصلية —"}
                readOnly
                title="المورد يُورَّث من الفاتورة الأصلية ولا يُعدَّل — قيد العكس يجب أن يصيب نفس حساب ذمم المورد."
              />
            </label>
          </>
        }
        tabs={tabs}
        status={
          <>
            <span className="ktra-status-item">عدد البنود <b>{lines.filter((l) => l.product_id).length}</b></span>
            <span className="ktra-status-item">الإجمالي <b className="ktra-num">{formatMoney(totalAmount)}</b></span>
            {/* issue #109 §٦: مؤشّر دائم كي لا يضغط المستخدم «حفظ» احتياطاً كل دقيقة — لا يوجد حفظٌ خادميّ فوريّ في هذه الشاشة أصلاً. */}
            {draftSavedAt && (
              <span className="ktra-status-item" data-testid="draft-saved-indicator">
                مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
              </span>
            )}
          </>
        }
      >
        {draftSaveFailedBanner}
        {draftRestoreBanner}
        {orphanDraftsBanner}
      </KitDocumentShell>

      {/* W6: منتقي بنود المرجع — اختَر البنود واضبط كمية الإرجاع (مقيّدة بالمتبقّي). */}
      {pickerOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setPickerOpen(false)}
        >
          <div
            dir="rtl"
            className="bg-[var(--color-surface)] rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col border border-[var(--color-border)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
              <h3 className="text-sm font-bold text-[var(--color-text)]">اختيار بنود الإرجاع</h3>
              <button type="button" className="ktra-iconbtn" onClick={() => setPickerOpen(false)} title="إغلاق">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-4 py-2 text-xs text-[var(--color-text-muted)]">
              اختر البنود التي تريد إرجاعها وحدّد الكمية — لا يمكن تجاوز «المتبقّي القابل للإرجاع».
            </div>
            <div className="flex-1 overflow-y-auto px-2">
              {pickerLoading ? (
                <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">جارٍ التحميل…</div>
              ) : pickerRows.length === 0 ? (
                <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">لا توجد بنود قابلة للإرجاع.</div>
              ) : (
                <table className="w-full text-right text-xs">
                  <thead className="text-[var(--color-text-muted)]">
                    <tr className="border-b border-[var(--color-border)]">
                      <th className="p-2 w-8"></th>
                      <th className="p-2">المنتج</th>
                      <th className="p-2 text-center">المفوتر</th>
                      <th className="p-2 text-center">المرتجع</th>
                      <th className="p-2 text-center">المتبقّي</th>
                      <th className="p-2 text-center w-24">كمية الإرجاع</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickerRows.map((r, i) => {
                      const remaining = Number(r.remaining_qty) || 0;
                      const exhausted = remaining <= 0;
                      return (
                        <tr key={r.product} className={`border-b border-[var(--color-border)] ${exhausted ? "opacity-50" : ""}`}>
                          <td className="p-2 text-center">
                            <input
                              type="checkbox"
                              checked={r.selected}
                              disabled={exhausted}
                              onChange={(e) => setPickerField(i, { selected: e.target.checked })}
                            />
                          </td>
                          <td className="p-2 font-medium text-[var(--color-text)]">{r.name}</td>
                          <td className="p-2 text-center">{formatQuantity(r.invoiced_qty)}</td>
                          <td className="p-2 text-center">{formatQuantity(r.returned_qty)}</td>
                          <td className="p-2 text-center font-bold">{formatQuantity(r.remaining_qty)}</td>
                          <td className="p-2 text-center">
                            <input
                              type="number"
                              className="ktra-input"
                              style={{ width: "80px", textAlign: "center" }}
                              min={0}
                              max={remaining}
                              value={r.return_qty}
                              disabled={exhausted || !r.selected}
                              onChange={(e) => {
                                const v = Math.max(0, Math.min(Number(e.target.value) || 0, remaining));
                                setPickerField(i, { return_qty: String(v) });
                              }}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-[var(--color-border)]">
              <button type="button" className="ktra-btn" onClick={() => setPickerOpen(false)}>إلغاء</button>
              <button type="button" className="ktra-btn ktra-btn-primary" onClick={confirmPicker}>
                إضافة البنود المختارة
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
