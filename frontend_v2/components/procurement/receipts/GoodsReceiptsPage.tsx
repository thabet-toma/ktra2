/**
 * إرساليات الشراء — قائمة المستندات + محرّر (إنشاء/تعديل) + عرض وطباعة.
 *
 * المستند نوعان يحكمهما وجود «الفاتورة المرتبطة»:
 *  - مرتبط بفاتورة ⇒ اسمه من الإعدادات (افتراضياً «إرسالية شراء»)، وبنوده
 *    تُختار من بنود تلك الفاتورة حصراً بكمياتها المتبقية.
 *  - بلا فاتورة ⇒ «سند استلام» (بضاعة وصلت قبل فاتورتها): يُحدَّد المورد وأصنافه
 *    وأسعارها، ويُرحَّل مقابل وسيط «بضاعة مستلَمة لم تُفوتَر».
 * التسميتان وإتاحة السند المستقل والتعديل — كلها من إعدادات الشراء.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FileSearch, Loader2, Pencil, Printer, Save, Trash2, X } from "lucide-react";
import {
  createGoodsReceipt,
  deleteGoodsReceipt,
  getGoodsReceipt,
  getOutstandingReceiptLines,
  getReceivableLines,
  listGoodsReceipts,
  updateGoodsReceipt,
  type GoodsReceiptDto,
  type GoodsReceiptRow,
  type GoodsReceiptSaveLine,
  type ReceivableLineRow,
} from "../../../services/goodsReceiptsApi";
import { purchaseInvoiceApi } from "../../../services/purchaseInvoiceApi";
import { inventoryApi, listPickerProducts } from "../../../services/inventoryApi";
import { apiGetList } from "../../../services/restApi";
import { resolveTenantId } from "../../../utils/tenantContext";
import { openInNewTab } from "../../../utils/openInNewTab";
import { formatMoney, formatQuantity } from "../../../utils/formatNumber";
import { formatDateLocalized, todayIso } from "../../../utils/formatDate";
import { printReport } from "../../../utils/printReport";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { KitAutocomplete, KitDateInput } from "../../kit";
import {
  CommercialDocumentEditor,
  type CommercialLineColumn,
  type CommercialToolbarAction,
} from "../../shared/CommercialDocumentEditor";
import {
  CommercialDocumentsList,
  type CommercialListColumn,
} from "../../shared/CommercialDocumentsList";
import {
  InvoicePickerModal,
  type PickableInvoice,
} from "../../shared/InvoicePickerModal";

type WarehouseOpt = { id: number; name: string; is_default?: boolean };
type PartnerOpt = { id: number; name: string; partner_type?: string };
type ProductOpt = { id: number; sku?: string; name_ar?: string; name_en?: string };

type LineState = {
  /** بند الفاتورة المرتبطة — فارغ في السند المستقل. */
  item_id: number | "";
  /** الصنف — يُختار مباشرة في السند المستقل. */
  product_id: number | "";
  product_name: string;
  ordered: number;
  received: number;
  remaining: number;
  quantity: string;
  unit_price: string;
  warehouse_id: number | "";
};

const blankLine = (warehouseId: number | ""): LineState => ({
  item_id: "",
  product_id: "",
  product_name: "",
  ordered: 0,
  received: 0,
  remaining: 0,
  quantity: "",
  unit_price: "",
  warehouse_id: warehouseId,
});

const productLabel = (p: ProductOpt) => p.name_ar || p.name_en || p.sku || `#${p.id}`;

export const GoodsReceiptsPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const location = useLocation();

  const [rows, setRows] = useState<GoodsReceiptRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);

  const [mode, setMode] = useState<"list" | "form" | "view">("list");
  const [viewDoc, setViewDoc] = useState<GoodsReceiptDto | null>(null);

  // إعدادات الشراء تحكم التسميات وإتاحة السند المستقل والتعديل.
  const [labels, setLabels] = useState({ linked: "إرسالية شراء", standalone: "سند استلام" });
  const [allowStandalone, setAllowStandalone] = useState(true);
  const [allowEdit, setAllowEdit] = useState(true);

  // ── حالة المحرّر ──
  const [editingId, setEditingId] = useState<number | null>(null);
  const [invoiceOptions, setInvoiceOptions] = useState<PickableInvoice[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [warehouses, setWarehouses] = useState<WarehouseOpt[]>([]);
  const [partners, setPartners] = useState<PartnerOpt[]>([]);
  const [products, setProducts] = useState<ProductOpt[]>([]);
  const [formInvoice, setFormInvoice] = useState<number | "">("");
  const [formInvoiceLabel, setFormInvoiceLabel] = useState("");
  const [formPartner, setFormPartner] = useState<number | "">("");
  const [formSupplierRef, setFormSupplierRef] = useState("");
  const [formDate, setFormDate] = useState(() => todayIso());
  const [formNotes, setFormNotes] = useState("");
  const [formLines, setFormLines] = useState<LineState[]>([]);
  const [invoiceLines, setInvoiceLines] = useState<ReceivableLineRow[]>([]);
  const [invoiceMeta, setInvoiceMeta] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const isStandalone = formInvoice === "";
  const docLabel = isStandalone ? labels.standalone : labels.linked;

  const defaultWarehouse = useMemo<number | "">(
    () => warehouses.find((w) => w.is_default)?.id ?? warehouses[0]?.id ?? "",
    [warehouses]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setRows(await listGoodsReceipts(search ? { search } : undefined));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل تحميل الإرساليات");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void (async () => {
      try {
        const s = await purchaseInvoiceApi.getSettings();
        setLabels({
          linked: s.receipt_doc_label || "إرسالية شراء",
          standalone: s.standalone_receipt_label || "سند استلام",
        });
        setAllowStandalone(s.allow_standalone_receipt !== false);
        setAllowEdit(s.allow_edit_receipt !== false);
      } catch {
        /* التسميات الافتراضية تكفي إن تعذّر جلب الإعدادات */
      }
    })();
  }, []);

  /** مراجع المحرّر: فواتير قابلة للاستلام + مستودعات + موردون + أصناف. */
  const loadRefs = useCallback(async () => {
    try {
      const tenantId = resolveTenantId();
      const [invs, whs, parts, prods] = await Promise.all([
        // P0-5: كان page_size بلا page لا يقيّد شيئاً (الترقيم اختياري) —
        // مع الترقيم الإلزامي صار فعلاً «أحدث 200».
        purchaseInvoiceApi.list({ page: "1", page_size: "200" }),
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<WarehouseOpt[]>,
        apiGetList<PartnerOpt>("partners/lookup/", {
          tenantId,
          query: { limit: 500 },
        }),
        listPickerProducts<ProductOpt>(tenantId),
      ]);
      setInvoiceOptions(
        (invs || [])
          // المستوردة تُستلَم من تخليص الشحنة، والمرجع لا يُستلَم أصلاً.
          .filter(
            (i) =>
              i.invoice_type !== "international" &&
              !i.is_return &&
              i.receipt_status !== "received"
          )
          .map((i) => ({
            id: i.id,
            number: i.invoice_number,
            date: i.invoice_date,
            partnerName: i.partner_name,
            total: i.payable_total ?? i.grand_total,
            statusLabel: i.receipt_status_display || (i.is_posted ? "مرحَّلة" : "مسودة"),
          }))
      );
      setWarehouses(whs || []);
      // الخادم لا يفلتر بالنوع — نُبقي الطرف المطلوب فقط.
      setPartners((parts || []).filter((p) => p.partner_type === "Supplier"));
      setProducts(prods || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل تحميل بيانات المحرّر");
    }
  }, []);

  /** تحميل بنود الفاتورة المرتبطة — مصدر خيارات منتقي البنود. */
  const pickInvoice = useCallback(
    async (invoiceId: number | "", keepLines = false) => {
      setFormInvoice(invoiceId);
      if (!keepLines) setFormLines([]);
      setInvoiceLines([]);
      setInvoiceMeta("");
      if (!invoiceId) {
        setFormInvoiceLabel("");
        return;
      }
      try {
        const data = await getReceivableLines(Number(invoiceId));
        setInvoiceLines(data.lines || []);
        setFormInvoiceLabel(data.invoice_number || "");
        setInvoiceMeta(
          `${data.partner_name || ""}${
            data.receipt_status_display ? ` · ${data.receipt_status_display}` : ""
          }`
        );
        setErr(
          data.is_local
            ? null
            : "فاتورة مستوردة — بضاعتها تُستلَم من تخليص الشحنة لا من إرسالية."
        );
      } catch (e) {
        setErr(e instanceof Error ? e.message : "تعذر تحميل بنود الفاتورة");
      }
    },
    []
  );

  const openNew = useCallback(
    async (invoiceId?: number) => {
      setMode("form");
      setViewDoc(null);
      setEditingId(null);
      setFormDate(todayIso());
      setFormNotes("");
      setFormSupplierRef("");
      setFormPartner("");
      setFormLines([]);
      setFormInvoice("");
      setFormInvoiceLabel("");
      await loadRefs();
      if (invoiceId) await pickInvoice(invoiceId);
    },
    [loadRefs, pickInvoice]
  );

  const openEdit = useCallback(
    async (doc: GoodsReceiptDto) => {
      setMode("form");
      setViewDoc(null);
      setEditingId(doc.id);
      setFormDate(doc.receipt_date || todayIso());
      setFormNotes(doc.notes || "");
      setFormSupplierRef(doc.supplier_ref || "");
      setFormPartner(doc.partner ?? "");
      await loadRefs();
      if (doc.invoice) {
        await pickInvoice(doc.invoice, true);
      } else {
        setFormInvoice("");
        setFormInvoiceLabel("");
      }
      setFormLines(
        (doc.lines || []).map((l) => ({
          item_id: l.item ?? "",
          product_id: l.product,
          product_name: l.product_name || l.item_name || "",
          ordered: Number(l.ordered_quantity) || 0,
          // المستلَم قبل هذه الإرسالية = التراكمي ناقص كميتها.
          received: Math.max(
            0,
            (Number(l.received_total) || 0) - (Number(l.quantity) || 0)
          ),
          remaining:
            (Number(l.remaining_quantity) || 0) + (Number(l.quantity) || 0),
          quantity: String(Number(l.quantity) || 0),
          unit_price: String(Number(l.unit_price) || 0),
          warehouse_id: l.warehouse ?? "",
        }))
      );
    },
    [loadRefs, pickInvoice]
  );

  // «إرسالية جديدة» من داخل فاتورة الشراء: /purchase-receipts/new?invoice=12
  useEffect(() => {
    if (!location.pathname.endsWith("/new")) return;
    const invoiceId = Number(new URLSearchParams(location.search).get("invoice") || 0);
    void openNew(invoiceId > 0 ? invoiceId : undefined);
    // المسار استُهلك — أعده للقائمة كي لا يُعاد فتح المحرّر عند أي تحديث.
    navigate("/purchase-receipts", { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search]);

  const openView = useCallback(
    async (id: number) => {
      try {
        setViewDoc(await getGoodsReceipt(id));
        setMode("view");
      } catch (e) {
        toast(e instanceof Error ? e.message : "تعذر فتح الإرسالية", "error");
      }
    },
    [toast]
  );

  const closeForm = () => {
    setMode("list");
    setViewDoc(null);
    setEditingId(null);
    void load();
  };

  const removeDoc = useCallback(
    async (doc: GoodsReceiptRow | GoodsReceiptDto) => {
      const ok = await confirm({
        title: "إلغاء الإرسالية",
        message:
          `سيُعكَس أثر ${doc.receipt_number}: تُحذف حركات مخزونها وقيدها وتعود ` +
          "الكميات غير مستلمة. متابعة؟",
      });
      if (!ok) return;
      try {
        await deleteGoodsReceipt(doc.id);
        toast("تم إلغاء الإرسالية وعكس أثرها.", "success");
        closeForm();
      } catch (e) {
        toast(e instanceof Error ? e.message : "تعذر إلغاء الإرسالية", "error");
      }
    },
    [confirm, toast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ── بنود المحرّر ──
  const usedItems = useMemo(
    () => new Set(formLines.map((l) => l.item_id).filter(Boolean) as number[]),
    [formLines]
  );

  const options = useMemo(() => {
    if (isStandalone) {
      const used = new Set(formLines.map((l) => l.product_id).filter(Boolean) as number[]);
      return products
        .filter((p) => !used.has(p.id))
        .map((p) => ({ id: p.id, label: productLabel(p), sub: p.sku || "" }));
    }
    return invoiceLines
      .filter((l) => Number(l.remaining_quantity) > 0 && !usedItems.has(l.item_id))
      .map((l) => ({
        id: l.item_id,
        label: l.product_name || l.name,
        sub: `المتبقي ${formatQuantity(l.remaining_quantity)} من ${formatQuantity(
          l.quantity
        )}`,
      }));
  }, [isStandalone, products, formLines, invoiceLines, usedItems]);

  const addLine = () => setFormLines((ls) => [...ls, blankLine(defaultWarehouse)]);

  const updateLine = (idx: number, patch: Partial<LineState>) =>
    setFormLines((ls) => ls.map((l, i) => (i === idx ? { ...l, ...patch } : l)));

  const pickRowItem = (idx: number, pickedId: number) => {
    if (isStandalone) {
      const p = products.find((x) => x.id === pickedId);
      if (!p) return;
      updateLine(idx, {
        item_id: "",
        product_id: p.id,
        product_name: productLabel(p),
        ordered: 0,
        received: 0,
        remaining: 0,
        quantity: "1",
      });
      return;
    }
    const src = invoiceLines.find((l) => l.item_id === pickedId);
    if (!src) return;
    const remaining = Number(src.remaining_quantity) || 0;
    updateLine(idx, {
      item_id: pickedId,
      product_id: src.product,
      product_name: src.product_name || src.name,
      ordered: Number(src.quantity) || 0,
      received: Number(src.received_quantity) || 0,
      remaining,
      quantity: String(remaining),
      unit_price: String(Number(src.unit_price) || 0),
    });
  };

  const lineColumns: CommercialLineColumn<LineState>[] = [
    {
      key: "product_name",
      header: "الصنف",
      width: isStandalone ? "30%" : "28%",
      render: (line, idx) => (
        <KitAutocomplete
          value={line.product_name}
          options={options}
          onPick={(id) => pickRowItem(idx, Number(id))}
          placeholder={
            isStandalone ? "ابحث عن صنف…" : "اختر من بنود الفاتورة…"
          }
        />
      ),
    },
    ...(isStandalone
      ? []
      : ([
          { key: "ordered", header: "المفوتر", width: "9%", type: "number", readOnly: true },
          { key: "received", header: "المستلَم", width: "9%", type: "number", readOnly: true },
          { key: "remaining", header: "الباقي", width: "9%", type: "number", readOnly: true },
        ] as CommercialLineColumn<LineState>[])),
    { key: "quantity", header: "الكمية المستلمة", width: "13%", type: "number" },
    {
      key: "unit_price",
      header: "سعر الوحدة",
      width: "13%",
      type: "number",
      readOnly: !isStandalone,
    },
    {
      key: "warehouse_id",
      header: "المستودع",
      width: "18%",
      render: (line, idx) => (
        <select
          className="ktra-input"
          value={line.warehouse_id === "" ? "" : String(line.warehouse_id)}
          onChange={(e) =>
            updateLine(idx, {
              warehouse_id: e.target.value ? Number(e.target.value) : "",
            })
          }
        >
          <option value="">—</option>
          {warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      ),
    },
    {
      key: "remove",
      header: "",
      width: "4%",
      render: (_line, idx) => (
        <button
          type="button"
          className="ktra-toolbtn ktra-toolbtn--danger"
          title="حذف السطر"
          onClick={() => setFormLines((ls) => ls.filter((_, i) => i !== idx))}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      ),
    },
  ];

  const getLineCell = (line: LineState, key: string) => {
    switch (key) {
      case "product_name":
        return line.product_name;
      case "ordered":
        return formatQuantity(line.ordered);
      case "received":
        return formatQuantity(line.received);
      case "remaining":
        return formatQuantity(line.remaining);
      case "quantity":
        return line.quantity;
      case "unit_price":
        return line.unit_price;
      default:
        return "";
    }
  };

  const save = async () => {
    if (isStandalone && !allowStandalone) {
      toast("سند الاستلام المستقل معطّل من إعدادات الشراء.", "error");
      return;
    }
    if (isStandalone && !formPartner) {
      toast("حدّد المورد لسند الاستلام.", "error");
      return;
    }
    const payload: GoodsReceiptSaveLine[] = formLines
      .filter(
        (l) =>
          (isStandalone ? l.product_id : l.item_id) &&
          Number(l.quantity) > 0 &&
          l.warehouse_id
      )
      .map((l) =>
        isStandalone
          ? {
              product_id: Number(l.product_id),
              quantity: Number(l.quantity),
              unit_price: Number(l.unit_price) || 0,
              warehouse_id: Number(l.warehouse_id),
            }
          : {
              item_id: Number(l.item_id),
              quantity: Number(l.quantity),
              warehouse_id: Number(l.warehouse_id),
            }
      );
    if (!payload.length) {
      toast("أضف بنداً واحداً على الأقل بكمية ومستودع.", "error");
      return;
    }
    if (!isStandalone) {
      const over = formLines.find((l) => l.item_id && Number(l.quantity) > l.remaining);
      if (over) {
        toast(`«${over.product_name}»: الكمية تتجاوز المتبقي (${over.remaining}).`, "error");
        return;
      }
    }
    setSaving(true);
    try {
      const body = {
        invoice: isStandalone ? null : Number(formInvoice),
        partner: formPartner ? Number(formPartner) : null,
        supplier_ref: formSupplierRef,
        receipt_date: formDate || undefined,
        notes: formNotes,
        lines: payload,
      };
      const saved = editingId
        ? await updateGoodsReceipt(editingId, body)
        : await createGoodsReceipt(body);
      toast(
        editingId
          ? `تم تعديل ${saved.receipt_number} وتحديث المخزون.`
          : `تم إنشاء ${saved.receipt_number} واستلام البضاعة.`,
        "success"
      );
      closeForm();
    } catch (e) {
      toast(e instanceof Error ? e.message : "فشل حفظ الإرسالية", "error");
    } finally {
      setSaving(false);
    }
  };

  /** طباعة/PDF لمستند واحد — مع عمود الباقي. */
  const printDoc = (doc: GoodsReceiptDto) => {
    const ok = printReport({
      title: doc.doc_label || docLabel,
      subtitle: doc.receipt_number,
      meta: [
        { label: "التاريخ", value: formatDateLocalized(doc.receipt_date) || "—" },
        { label: "المورد", value: doc.partner_name || "—" },
        { label: "الفاتورة المرتبطة", value: doc.invoice_number || "—" },
        { label: "مرجع المورد", value: doc.supplier_ref || "—" },
        ...(doc.notes ? [{ label: "ملاحظات", value: doc.notes }] : []),
      ],
      columns: [
        { header: "الصنف", value: (l: GoodsReceiptDto["lines"][number]) => l.product_name || l.item_name },
        { header: "المفوتر", value: (l) => formatQuantity(l.ordered_quantity), numeric: true },
        { header: "المستلَم في هذا المستند", value: (l) => formatQuantity(l.quantity), numeric: true },
        { header: "الباقي", value: (l) => formatQuantity(l.remaining_quantity), numeric: true },
        { header: "المستودع", value: (l) => l.warehouse_name || "—" },
      ],
      rows: doc.lines,
      footer: "توقيع المستلم: ______________________",
    });
    if (!ok) toast("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة", "error");
  };

  /** طباعة/PDF لكل البواقي غير المستلمة عبر الفواتير. */
  const printOutstanding = async () => {
    setExporting(true);
    try {
      const outstanding = await getOutstandingReceiptLines();
      const ok = printReport({
        title: "البواقي غير المستلمة",
        subtitle: "بنود فواتير شراء مرحّلة لم تُستلَم بضاعتها بعد",
        columns: [
          { header: "الفاتورة", value: (r) => r.invoice_number },
          { header: "التاريخ", value: (r) => formatDateLocalized(r.invoice_date) || "—" },
          { header: "المورد", value: (r) => r.partner_name },
          { header: "الصنف", value: (r) => r.product_name },
          { header: "المفوتر", value: (r) => formatQuantity(r.quantity), numeric: true },
          { header: "المستلَم", value: (r) => formatQuantity(r.received_quantity), numeric: true },
          { header: "الباقي", value: (r) => formatQuantity(r.remaining_quantity), numeric: true },
        ],
        rows: outstanding,
        emptyHint: "لا توجد بواقٍ — كل الفواتير المرحّلة مستلمة بالكامل.",
      });
      if (!ok) toast("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة", "error");
    } catch (e) {
      toast(e instanceof Error ? e.message : "تعذّر تحضير التقرير", "error");
    } finally {
      setExporting(false);
    }
  };

  // ── القائمة ──
  const columns: CommercialListColumn<GoodsReceiptRow>[] = [
    {
      key: "receipt_number",
      header: "رقم المستند",
      width: "120px",
      render: (r) => (
        <button
          type="button"
          className="font-mono text-xs text-[var(--ktra-accent)] hover:underline"
          onClick={(e) => {
            e.stopPropagation();
            void openView(r.id);
          }}
        >
          {r.receipt_number}
        </button>
      ),
    },
    {
      key: "doc_label",
      header: "النوع",
      width: "110px",
      align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "1px 6px",
            borderRadius: "4px",
            color: r.is_standalone ? "#b04a00" : "var(--ktra-accent, #2563eb)",
            background: r.is_standalone ? "rgba(176,74,0,0.12)" : "rgba(37,99,235,0.10)",
          }}
        >
          {r.doc_label}
        </span>
      ),
    },
    {
      key: "receipt_date",
      header: "التاريخ",
      width: "100px",
      align: "center",
      render: (r) => (
        <span className="text-xs">{formatDateLocalized(r.receipt_date) || "—"}</span>
      ),
    },
    {
      key: "invoice_number",
      header: "الفاتورة المرتبطة",
      width: "140px",
      render: (r) =>
        r.invoice ? (
          <button
            type="button"
            className="font-mono text-xs text-[var(--ktra-accent)] hover:underline"
            title="فتح الفاتورة في تبويب جديد"
            onClick={(e) => {
              e.stopPropagation();
              openInNewTab(`/purchase-invoices/${r.invoice}`);
            }}
          >
            {r.invoice_number}
          </button>
        ) : (
          <span className="text-xs ktra-text-soft">— بلا فاتورة —</span>
        ),
    },
    { key: "partner_name", header: "المورد" },
    {
      key: "supplier_ref",
      header: "مرجع المورد",
      width: "110px",
      render: (r) => <span className="text-xs">{r.supplier_ref || "—"}</span>,
    },
    {
      key: "total_quantity",
      header: "المستلَم",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => (
        <span className="ktra-num font-mono text-xs">{formatQuantity(r.total_quantity)}</span>
      ),
    },
    {
      key: "total_remaining",
      header: "الباقي",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => {
        const remaining = Number(r.total_remaining) || 0;
        return (
          <span
            className="ktra-num font-mono text-xs font-semibold"
            style={{
              color: remaining > 0 ? "var(--ktra-warn, #b06800)" : "var(--ktra-ok, #2d7d46)",
            }}
            title="الباقي غير المستلم من الفاتورة المرتبطة"
          >
            {formatQuantity(remaining)}
          </span>
        );
      },
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "120px",
      align: "center",
      render: (r) => (
        <div style={{ display: "flex", gap: "3px", justifyContent: "center" }}>
          <button
            type="button"
            className="ktra-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            title="عرض وطباعة"
            onClick={(e) => {
              e.stopPropagation();
              void openView(r.id);
            }}
          >
            <FileSearch className="w-3 h-3" />
          </button>
          {allowEdit && (
            <>
              <button
                type="button"
                className="ktra-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                title="تعديل"
                onClick={async (e) => {
                  e.stopPropagation();
                  try {
                    await openEdit(await getGoodsReceipt(r.id));
                  } catch (err2) {
                    toast(err2 instanceof Error ? err2.message : "تعذر الفتح", "error");
                  }
                }}
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                type="button"
                className="ktra-toolbtn ktra-toolbtn--danger"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                title="إلغاء الإرسالية"
                onClick={(e) => {
                  e.stopPropagation();
                  void removeDoc(r);
                }}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  if (mode === "view" && viewDoc) {
    return (
      <div dir="rtl" style={{ padding: "12px" }}>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="font-bold text-[var(--ktra-ink)]">
            {viewDoc.doc_label} {viewDoc.receipt_number}
          </h2>
          <div className="flex gap-2">
            <button
              type="button"
              className="ktra-toolbtn"
              onClick={() => printDoc(viewDoc)}
              title="طباعة / حفظ PDF"
            >
              <Printer className="h-4 w-4" /> طباعة / PDF
            </button>
            {allowEdit && (
              <>
                <button
                  type="button"
                  className="ktra-toolbtn"
                  onClick={() => void openEdit(viewDoc)}
                >
                  <Pencil className="h-4 w-4" /> تعديل
                </button>
                <button
                  type="button"
                  className="ktra-toolbtn ktra-toolbtn--danger"
                  onClick={() => void removeDoc(viewDoc)}
                >
                  <Trash2 className="h-4 w-4" /> إلغاء
                </button>
              </>
            )}
            <button type="button" className="ktra-toolbtn" onClick={closeForm}>
              <X className="h-4 w-4" /> إغلاق
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-4 text-sm mb-3 text-[var(--ktra-ink-soft)]">
          <span>التاريخ: {formatDateLocalized(viewDoc.receipt_date)}</span>
          <span>الفاتورة المرتبطة: {viewDoc.invoice_number || "— بلا فاتورة —"}</span>
          <span>المورد: {viewDoc.partner_name || "—"}</span>
          {viewDoc.supplier_ref && <span>مرجع المورد: {viewDoc.supplier_ref}</span>}
          <span>{viewDoc.auto_created ? "أُنشئت مع الترحيل" : "مستند يدوي"}</span>
          {viewDoc.notes && <span>ملاحظات: {viewDoc.notes}</span>}
        </div>
        <table className="ktra-grid">
          <thead>
            <tr>
              <th>الصنف</th>
              <th>المفوتر</th>
              <th>المستلَم في هذا المستند</th>
              <th>المستلَم تراكمياً</th>
              <th>الباقي</th>
              <th>المستودع</th>
            </tr>
          </thead>
          <tbody>
            {viewDoc.lines.map((l) => (
              <tr key={l.id}>
                <td>{l.product_name || l.item_name}</td>
                <td className="ktra-num">{formatQuantity(l.ordered_quantity)}</td>
                <td className="ktra-num">{formatQuantity(l.quantity)}</td>
                <td className="ktra-num">{formatQuantity(l.received_total)}</td>
                <td
                  className="ktra-num"
                  style={{
                    color:
                      Number(l.remaining_quantity) > 0
                        ? "var(--ktra-warn, #b06800)"
                        : "var(--ktra-ok, #2d7d46)",
                    fontWeight: 600,
                  }}
                >
                  {formatQuantity(l.remaining_quantity)}
                </td>
                <td>{l.warehouse_name || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (mode === "form") {
    const actions: CommercialToolbarAction[] = [
      {
        key: "save",
        label: saving ? "جارٍ الحفظ…" : editingId ? "حفظ التعديل" : "حفظ واستلام",
        icon: saving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        ),
        onClick: save,
        disabled: saving,
      },
      ...(editingId && allowEdit
        ? [
            {
              key: "delete",
              label: "إلغاء المستند",
              icon: <Trash2 className="h-4 w-4" />,
              onClick: () => {
                const row = rows.find((r) => r.id === editingId);
                if (row) void removeDoc(row);
              },
              danger: true,
              separatorBefore: true,
            } as CommercialToolbarAction,
          ]
        : []),
      {
        key: "cancel",
        label: "رجوع",
        icon: <X className="h-4 w-4" />,
        onClick: closeForm,
        separatorBefore: true,
      },
    ];

    return (
      <>
        <CommercialDocumentEditor<LineState>
          title={editingId ? `تعديل ${docLabel}` : `${docLabel} جديد`}
          state={invoiceMeta}
          actions={actions}
          headerFields={[
            {
              key: "invoice",
              label: "الفاتورة المرتبطة",
              control: (
                <div className="flex gap-1">
                  <input
                    className="ktra-input flex-1"
                    readOnly
                    value={formInvoiceLabel || "— بلا فاتورة (سند مستقل) —"}
                    placeholder="اختر فاتورة…"
                    onClick={() => setPickerOpen(true)}
                  />
                  <button
                    type="button"
                    className="ktra-toolbtn"
                    title="اختيار من قائمة فواتير الشراء"
                    onClick={() => setPickerOpen(true)}
                  >
                    <FileSearch className="h-4 w-4" />
                  </button>
                  {!isStandalone && (
                    <button
                      type="button"
                      className="ktra-toolbtn"
                      title="إزالة الربط (سند مستقل)"
                      onClick={() => void pickInvoice("")}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ),
            },
            {
              key: "partner",
              label: isStandalone ? "المورد (إلزامي)" : "المورد",
              control: (
                <select
                  className="ktra-input"
                  disabled={!isStandalone}
                  value={formPartner === "" ? "" : String(formPartner)}
                  onChange={(e) =>
                    setFormPartner(e.target.value ? Number(e.target.value) : "")
                  }
                >
                  <option value="">
                    {isStandalone ? "— اختر مورداً —" : "من الفاتورة المرتبطة"}
                  </option>
                  {partners.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              ),
            },
            {
              key: "supplier_ref",
              label: "رقم/مرجع المورد",
              control: (
                <input
                  className="ktra-input"
                  value={formSupplierRef}
                  onChange={(e) => setFormSupplierRef(e.target.value)}
                  placeholder="بوليصة، إشعار تسليم…"
                />
              ),
            },
            {
              key: "date",
              label: "التاريخ",
              control: <KitDateInput value={formDate} onChange={setFormDate} />,
            },
            {
              key: "notes",
              label: "ملاحظات",
              control: (
                <input
                  className="ktra-input"
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  placeholder="اسم المستلم / رقم المركبة…"
                />
              ),
            },
          ]}
          lines={formLines}
          lineColumns={lineColumns}
          getLineCell={getLineCell}
          getLineKey={(_l, i) => i}
          onLineChange={(idx, key, value) => {
            if (key === "quantity") updateLine(idx, { quantity: value });
            if (key === "unit_price" && isStandalone) {
              updateLine(idx, { unit_price: value });
            }
          }}
          onAddLine={addLine}
          addLineLabel={isStandalone ? "إضافة صنف" : "إضافة بند من الفاتورة"}
          emptyHint={
            isStandalone
              ? "لا توجد بنود — اضغط «إضافة صنف»"
              : "لا توجد بنود — اضغط «إضافة بند من الفاتورة»"
          }
          banner={
            err ? (
              <div className="ktra-banner ktra-banner--err" role="alert">
                {err}
              </div>
            ) : undefined
          }
          status={
            <>
              <span className="ktra-status-item">
                البنود <b>{formLines.length}</b>
              </span>
              {isStandalone && (
                <span className="ktra-status-item">
                  القيمة{" "}
                  <b className="ktra-num">
                    {formatMoney(
                      formLines.reduce(
                        (s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0),
                        0
                      )
                    )}
                  </b>
                </span>
              )}
            </>
          }
        />
        {pickerOpen && (
          <InvoicePickerModal
            title="اختيار فاتورة الشراء المرتبطة"
            rows={invoiceOptions}
            partnerHeader="المورد"
            emptyHint="لا توجد فواتير شراء قابلة للاستلام."
            onPick={(inv) => {
              setPickerOpen(false);
              void pickInvoice(inv.id);
            }}
            onClose={() => setPickerOpen(false)}
          />
        )}
      </>
    );
  }

  return (
    <CommercialDocumentsList<GoodsReceiptRow>
      title="إرساليات الشراء"
      rows={rows}
      columns={columns}
      getRowKey={(r) => r.id}
      loading={loading}
      error={err}
      emptyHint="لا توجد إرساليات — اضغط «إرسالية جديدة»"
      countLabel={`العدد ${rows.length}`}
      searchValue={search}
      searchPlaceholder="بحث برقم المستند / الفاتورة / المورد…"
      onSearchChange={setSearch}
      onNew={() => void openNew()}
      onReload={() => void load()}
      newLabel="إرسالية جديدة"
      onRowDoubleClick={(r) => void openView(r.id)}
      extraActions={[
        {
          key: "outstanding",
          label: exporting ? "جارٍ التحضير…" : "طباعة البواقي غير المستلمة",
          icon: exporting ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Printer />
          ),
          onClick: () => void printOutstanding(),
          separatorBefore: true,
        },
      ]}
    />
  );
};

export default GoodsReceiptsPage;
