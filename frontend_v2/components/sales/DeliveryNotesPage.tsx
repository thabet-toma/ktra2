/**
 * إرساليات البيع — قائمة المستندات + محرّر (إنشاء/تعديل) + عرض وطباعة.
 *
 * مرآة «إرساليات الشراء». المستند نوعان يحكمهما وجود «الفاتورة المرتبطة»:
 *  - مرتبط بفاتورة ⇒ اسمه من الإعدادات (افتراضياً «إرسالية بيع»)، وبنوده من
 *    بنود تلك الفاتورة حصراً بكمياتها المتبقية.
 *  - بلا فاتورة ⇒ «سند تسليم» (بضاعة خرجت قبل فوترتها): يُحدَّد العميل ومنتجاته،
 *    ويُرحَّل مقابل حساب «بضاعة مسلَّمة لم تُفوتَر».
 * التسميتان وإتاحة السند المستقل والتعديل — كلها من إعدادات المبيعات.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FileSearch, Loader2, Pencil, Printer, Save, Trash2, X } from "lucide-react";
import {
  createDeliveryNote,
  deleteDeliveryNote,
  getDeliveryLines,
  getDeliveryNote,
  getOutstandingDeliveryLines,
  getSalesSettings,
  listDeliveryNotes,
  type SalesInvoiceRow,
  updateDeliveryNote,
  type DeliveryLineRow,
  type DeliveryNoteDto,
  type DeliveryNoteRow,
  type DeliveryNoteSaveLine,
} from "../../services/salesApi";
import { apiGetList } from "../../services/restApi";
import { inventoryApi, listPickerProducts } from "../../services/inventoryApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { openInNewTab } from "../../utils/openInNewTab";
import { formatQuantity } from "../../utils/formatNumber";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import { printReport } from "../../utils/printReport";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { KitAutocomplete, KitDateInput } from "../kit";
import {
  CommercialDocumentEditor,
  type CommercialLineColumn,
  type CommercialToolbarAction,
} from "../shared/CommercialDocumentEditor";
import {
  CommercialDocumentsList,
  type CommercialListColumn,
} from "../shared/CommercialDocumentsList";
import {
  InvoicePickerModal,
  type PickableInvoice,
} from "../shared/InvoicePickerModal";

type WarehouseOpt = { id: number; name: string; is_default?: boolean };
type PartnerOpt = { id: number; name: string; partner_type?: string };
type ProductOpt = { id: number; sku?: string; name_ar?: string; name_en?: string };

type LineState = {
  /** سطر الفاتورة المرتبطة — فارغ في السند المستقل. */
  line_id: number | "";
  product_id: number | "";
  product_name: string;
  ordered: number;
  delivered: number;
  remaining: number;
  quantity: string;
  warehouse_id: number | "";
};

const blankLine = (warehouseId: number | ""): LineState => ({
  line_id: "",
  product_id: "",
  product_name: "",
  ordered: 0,
  delivered: 0,
  remaining: 0,
  quantity: "",
  warehouse_id: warehouseId,
});

const productLabel = (p: ProductOpt) => p.name_ar || p.name_en || p.sku || `#${p.id}`;

export const DeliveryNotesPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const location = useLocation();

  const [rows, setRows] = useState<DeliveryNoteRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);

  const [mode, setMode] = useState<"list" | "form" | "view">("list");
  const [viewDoc, setViewDoc] = useState<DeliveryNoteDto | null>(null);

  const [labels, setLabels] = useState({ linked: "إرسالية بيع", standalone: "سند تسليم" });
  const [allowStandalone, setAllowStandalone] = useState(true);
  const [allowEdit, setAllowEdit] = useState(true);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [invoiceOptions, setInvoiceOptions] = useState<PickableInvoice[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [warehouses, setWarehouses] = useState<WarehouseOpt[]>([]);
  const [partners, setPartners] = useState<PartnerOpt[]>([]);
  const [products, setProducts] = useState<ProductOpt[]>([]);
  const [formInvoice, setFormInvoice] = useState<number | "">("");
  const [formInvoiceLabel, setFormInvoiceLabel] = useState("");
  const [formPartner, setFormPartner] = useState<number | "">("");
  const [formCustomerRef, setFormCustomerRef] = useState("");
  const [formDate, setFormDate] = useState(() => todayIso());
  const [formNotes, setFormNotes] = useState("");
  const [formLines, setFormLines] = useState<LineState[]>([]);
  const [invoiceLines, setInvoiceLines] = useState<DeliveryLineRow[]>([]);
  const [invoiceMeta, setInvoiceMeta] = useState("");
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
      // P0-5: القائمة مُرقَّمة إلزامياً — أحدث 200 إرسالية (البحث خادمي يضيّق).
      setRows(await listDeliveryNotes({ ...(search ? { search } : {}), page: 1, page_size: 200 }));
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
        const s = await getSalesSettings();
        setLabels({
          linked: s.delivery_doc_label || "إرسالية بيع",
          standalone: s.standalone_delivery_label || "سند تسليم",
        });
        setAllowStandalone(s.allow_standalone_delivery !== false);
        setAllowEdit(s.allow_edit_delivery !== false);
      } catch {
        /* التسميات الافتراضية تكفي إن تعذّر جلب الإعدادات */
      }
    })();
  }, []);

  /**
   * مراجع المحرّر: فواتير البيع المرحّلة + عملاء + منتجات + مستودعات.
   *
   * تُعرض **كل** الفواتير المرحّلة (رقم/تاريخ/عميل/إجمالي) كما في منتقي فواتير
   * الشراء؛ وما لا يقبل إرسالية يُعرَض غير قابل للاختيار بسببه لا مخفياً —
   * فالإخفاء كان يترك القائمة فارغة لأي شركة على الإعداد الافتراضي (خصم المخزون
   * مع الترحيل) بلا تفسير.
   */
  const loadRefs = useCallback(async () => {
    try {
      const tenantId = resolveTenantId();
      const [invs, parts, prods, whs] = await Promise.all([
        // P0-5: منتقي الفواتير على نقطة lookup المحدودة (مصفوفة خام بسقف 500)
        // — قائمة الفواتير نفسها صارت مُرقَّمة إلزامياً.
        apiGetList<SalesInvoiceRow>("sales/invoices/lookup/?limit=500&status=posted", { tenantId }),
        apiGetList<PartnerOpt>("partners/lookup/", {
          tenantId,
          query: { limit: 500 },
        }),
        listPickerProducts<ProductOpt>(tenantId),
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<WarehouseOpt[]>,
      ]);
      setInvoiceOptions(
        (invs || []).map((i) => {
          const delivered = i.delivery_status === "delivered";
          return {
            id: i.id,
            number: i.invoice_number,
            date: i.invoice_date,
            partnerName: i.customer_name,
            total: i.grand_total,
            statusLabel: i.delivery_status_display || "غير مسلَّمة",
            disabled: delivered || !!i.stock_on_post,
            hint: i.stock_on_post
              ? "تخصم المخزون عند الترحيل — سُلِّمت لحظة ترحيلها"
              : delivered
                ? "سُلِّمت بالكامل"
                : undefined,
          };
        })
      );
      // الخادم لا يفلتر بالنوع — نُبقي الطرف المطلوب فقط.
      setPartners((parts || []).filter((p) => p.partner_type === "Customer"));
      setProducts(prods || []);
      setWarehouses(whs || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل تحميل بيانات المحرّر");
    }
  }, []);

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
        const data = await getDeliveryLines(Number(invoiceId));
        setInvoiceLines(data.lines || []);
        setFormInvoiceLabel(data.invoice_number || "");
        setInvoiceMeta(data.delivery_status_display || "");
        setErr(
          data.stock_on_post
            ? "هذه الفاتورة تخصم المخزون عند الترحيل — بنودها مسلَّمة بالفعل."
            : null
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
      setFormCustomerRef("");
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
    async (doc: DeliveryNoteDto) => {
      setMode("form");
      setViewDoc(null);
      setEditingId(doc.id);
      setFormDate(doc.delivery_date || todayIso());
      setFormNotes(doc.notes || "");
      setFormCustomerRef(doc.customer_ref || "");
      setFormPartner(doc.is_standalone ? doc.customer ?? "" : "");
      await loadRefs();
      if (doc.invoice) {
        await pickInvoice(doc.invoice, true);
      } else {
        setFormInvoice("");
        setFormInvoiceLabel("");
      }
      setFormLines(
        (doc.lines || []).map((l) => ({
          line_id: l.invoice_line ?? "",
          product_id: l.product,
          product_name: l.product_name || "",
          ordered: Number(l.ordered_quantity) || 0,
          // المسلَّم قبل هذه الإرسالية = التراكمي ناقص كميتها.
          delivered: Math.max(
            0,
            (Number(l.delivered_total) || 0) - (Number(l.quantity) || 0)
          ),
          remaining: (Number(l.remaining_quantity) || 0) + (Number(l.quantity) || 0),
          quantity: String(Number(l.quantity) || 0),
          warehouse_id: l.warehouse ?? "",
        }))
      );
    },
    [loadRefs, pickInvoice]
  );

  // «إرسالية جديدة» من داخل الفاتورة: /sales/delivery-notes/new?invoice=12
  useEffect(() => {
    if (!location.pathname.endsWith("/new")) return;
    const invoiceId = Number(new URLSearchParams(location.search).get("invoice") || 0);
    void openNew(invoiceId > 0 ? invoiceId : undefined);
    navigate("/sales/delivery-notes", { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search]);

  const openView = useCallback(
    async (id: number) => {
      try {
        setViewDoc(await getDeliveryNote(id));
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
    async (doc: DeliveryNoteRow | DeliveryNoteDto) => {
      const label = doc.delivery_number || `#${doc.id}`;
      const ok = await confirm({
        title: "إلغاء الإرسالية",
        message:
          `سيُعكَس أثر ${label}: تُحذف حركات مخزونها وقيدها وتعود الكميات ` +
          "غير مسلَّمة. متابعة؟",
      });
      if (!ok) return;
      try {
        await deleteDeliveryNote(doc.id);
        toast("تم إلغاء الإرسالية وعكس أثرها.", "success");
        closeForm();
      } catch (e) {
        toast(e instanceof Error ? e.message : "تعذر إلغاء الإرسالية", "error");
      }
    },
    [confirm, toast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const usedLines = useMemo(
    () => new Set(formLines.map((l) => l.line_id).filter(Boolean) as number[]),
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
      .filter((l) => Number(l.remaining_quantity) > 0 && !usedLines.has(l.line_id))
      .map((l) => ({
        id: l.line_id,
        label: l.product_name,
        sub: `المتبقي ${formatQuantity(l.remaining_quantity)} من ${formatQuantity(
          l.quantity
        )}`,
      }));
  }, [isStandalone, products, formLines, invoiceLines, usedLines]);

  const addLine = () => setFormLines((ls) => [...ls, blankLine(defaultWarehouse)]);

  const updateLine = (idx: number, patch: Partial<LineState>) =>
    setFormLines((ls) => ls.map((l, i) => (i === idx ? { ...l, ...patch } : l)));

  const pickRowItem = (idx: number, pickedId: number) => {
    if (isStandalone) {
      const p = products.find((x) => x.id === pickedId);
      if (!p) return;
      updateLine(idx, {
        line_id: "",
        product_id: p.id,
        product_name: productLabel(p),
        ordered: 0,
        delivered: 0,
        remaining: 0,
        quantity: "1",
      });
      return;
    }
    const src = invoiceLines.find((l) => l.line_id === pickedId);
    if (!src) return;
    const remaining = Number(src.remaining_quantity) || 0;
    updateLine(idx, {
      line_id: pickedId,
      product_id: src.product,
      product_name: src.product_name,
      ordered: Number(src.quantity) || 0,
      delivered: Number(src.delivered_quantity) || 0,
      remaining,
      quantity: String(remaining),
    });
  };

  const lineColumns: CommercialLineColumn<LineState>[] = [
    {
      key: "product_name",
      header: "المنتج",
      width: isStandalone ? "56%" : "30%",
      render: (line, idx) => (
        <KitAutocomplete
          value={line.product_name}
          options={options}
          onPick={(id) => pickRowItem(idx, Number(id))}
          placeholder={isStandalone ? "ابحث عن منتج…" : "اختر من بنود الفاتورة…"}
        />
      ),
    },
    ...(isStandalone
      ? []
      : ([
          { key: "ordered", header: "المفوتر", width: "10%", type: "number", readOnly: true },
          { key: "delivered", header: "المسلَّم", width: "10%", type: "number", readOnly: true },
          { key: "remaining", header: "الباقي", width: "10%", type: "number", readOnly: true },
        ] as CommercialLineColumn<LineState>[])),
    { key: "quantity", header: "الكمية المسلَّمة", width: "14%", type: "number" },
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
      case "delivered":
        return formatQuantity(line.delivered);
      case "remaining":
        return formatQuantity(line.remaining);
      case "quantity":
        return line.quantity;
      default:
        return "";
    }
  };

  const save = async () => {
    if (isStandalone && !allowStandalone) {
      toast("سند التسليم المستقل معطّل من إعدادات المبيعات.", "error");
      return;
    }
    if (isStandalone && !formPartner) {
      toast("حدّد العميل لسند التسليم.", "error");
      return;
    }
    const payload: DeliveryNoteSaveLine[] = formLines
      .filter((l) => (isStandalone ? l.product_id : l.line_id) && Number(l.quantity) > 0)
      .map((l) => ({
        ...(isStandalone
          ? { product_id: Number(l.product_id) }
          : { line_id: Number(l.line_id) }),
        quantity: Number(l.quantity),
        ...(l.warehouse_id ? { warehouse_id: Number(l.warehouse_id) } : {}),
      }));
    if (!payload.length) {
      toast("أضف بنداً واحداً على الأقل بكمية.", "error");
      return;
    }
    if (!isStandalone) {
      const over = formLines.find((l) => l.line_id && Number(l.quantity) > l.remaining);
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
        customer_ref: formCustomerRef,
        delivery_date: formDate || undefined,
        notes: formNotes,
        lines: payload,
      };
      const saved = editingId
        ? await updateDeliveryNote(editingId, body)
        : await createDeliveryNote(body);
      toast(
        editingId
          ? `تم تعديل ${saved.delivery_number} وتحديث المخزون.`
          : `تم إنشاء ${saved.delivery_number} وتسليم البضاعة.`,
        "success"
      );
      closeForm();
    } catch (e) {
      toast(e instanceof Error ? e.message : "فشل حفظ الإرسالية", "error");
    } finally {
      setSaving(false);
    }
  };

  const printDoc = (doc: DeliveryNoteDto) => {
    const ok = printReport({
      title: doc.doc_label || docLabel,
      subtitle: doc.delivery_number || `#${doc.id}`,
      meta: [
        { label: "التاريخ", value: formatDateLocalized(doc.delivery_date) || "—" },
        { label: "العميل", value: doc.customer_name || "—" },
        { label: "الفاتورة المرتبطة", value: doc.invoice_number || "—" },
        { label: "مرجع العميل", value: doc.customer_ref || "—" },
        ...(doc.notes ? [{ label: "ملاحظات", value: doc.notes }] : []),
      ],
      columns: [
        { header: "المنتج", value: (l: DeliveryNoteDto["lines"][number]) => l.product_name },
        { header: "المفوتر", value: (l) => formatQuantity(l.ordered_quantity), numeric: true },
        { header: "المسلَّم في هذا المستند", value: (l) => formatQuantity(l.quantity), numeric: true },
        { header: "الباقي", value: (l) => formatQuantity(l.remaining_quantity), numeric: true },
        { header: "المستودع", value: (l) => l.warehouse_name || "—" },
      ],
      rows: doc.lines,
      footer: "توقيع المستلم: ______________________",
    });
    if (!ok) toast("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة", "error");
  };

  const printOutstanding = async () => {
    setExporting(true);
    try {
      const outstanding = await getOutstandingDeliveryLines();
      const ok = printReport({
        title: "البواقي غير المسلَّمة",
        subtitle: "بنود فواتير بيع مرحّلة لم تُسلَّم بضاعتها بعد",
        columns: [
          { header: "الفاتورة", value: (r) => r.invoice_number },
          { header: "التاريخ", value: (r) => formatDateLocalized(r.invoice_date) || "—" },
          { header: "العميل", value: (r) => r.partner_name },
          { header: "المنتج", value: (r) => r.product_name },
          { header: "المفوتر", value: (r) => formatQuantity(r.quantity), numeric: true },
          { header: "المسلَّم", value: (r) => formatQuantity(r.delivered_quantity), numeric: true },
          { header: "الباقي", value: (r) => formatQuantity(r.remaining_quantity), numeric: true },
        ],
        rows: outstanding,
        emptyHint: "لا توجد بواقٍ — كل الفواتير المرحّلة مسلَّمة بالكامل.",
      });
      if (!ok) toast("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة", "error");
    } catch (e) {
      toast(e instanceof Error ? e.message : "تعذّر تحضير التقرير", "error");
    } finally {
      setExporting(false);
    }
  };

  const columns: CommercialListColumn<DeliveryNoteRow>[] = [
    {
      key: "delivery_number",
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
          {r.delivery_number || `#${r.id}`}
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
      key: "delivery_date",
      header: "التاريخ",
      width: "100px",
      align: "center",
      render: (r) => (
        <span className="text-xs">{formatDateLocalized(r.delivery_date) || "—"}</span>
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
              openInNewTab(`/sales/invoices/${r.invoice}`);
            }}
          >
            {r.invoice_number}
          </button>
        ) : (
          <span className="text-xs ktra-text-soft">— بلا فاتورة —</span>
        ),
    },
    { key: "customer_name", header: "العميل" },
    {
      key: "customer_ref",
      header: "مرجع العميل",
      width: "110px",
      render: (r) => <span className="text-xs">{r.customer_ref || "—"}</span>,
    },
    {
      key: "total_quantity",
      header: "المسلَّم",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => (
        <span className="ktra-num font-mono text-xs">
          {formatQuantity(r.total_quantity)}
        </span>
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
              color:
                remaining > 0 ? "var(--ktra-warn, #b06800)" : "var(--ktra-ok, #2d7d46)",
            }}
            title="الباقي غير المسلَّم من الفاتورة المرتبطة"
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
                    await openEdit(await getDeliveryNote(r.id));
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
            {viewDoc.doc_label} {viewDoc.delivery_number || `#${viewDoc.id}`}
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
          <span>التاريخ: {formatDateLocalized(viewDoc.delivery_date)}</span>
          <span>الفاتورة المرتبطة: {viewDoc.invoice_number || "— بلا فاتورة —"}</span>
          <span>العميل: {viewDoc.customer_name || "—"}</span>
          {viewDoc.customer_ref && <span>مرجع العميل: {viewDoc.customer_ref}</span>}
          <span>{viewDoc.auto_created ? "أُنشئت مع الترحيل" : "مستند يدوي"}</span>
          {viewDoc.notes && <span>ملاحظات: {viewDoc.notes}</span>}
        </div>
        <table className="ktra-grid">
          <thead>
            <tr>
              <th>المنتج</th>
              <th>المفوتر</th>
              <th>المسلَّم في هذا المستند</th>
              <th>المسلَّم تراكمياً</th>
              <th>الباقي</th>
              <th>المستودع</th>
            </tr>
          </thead>
          <tbody>
            {viewDoc.lines.map((l) => (
              <tr key={l.id}>
                <td>{l.product_name}</td>
                <td className="ktra-num">{formatQuantity(l.ordered_quantity)}</td>
                <td className="ktra-num">{formatQuantity(l.quantity)}</td>
                <td className="ktra-num">{formatQuantity(l.delivered_total)}</td>
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
        label: saving ? "جارٍ الحفظ…" : editingId ? "حفظ التعديل" : "حفظ وتسليم",
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
                    title="اختيار من قائمة فواتير المبيعات"
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
              label: isStandalone ? "العميل (إلزامي)" : "العميل",
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
                    {isStandalone ? "— اختر عميلاً —" : "من الفاتورة المرتبطة"}
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
              key: "customer_ref",
              label: "رقم/مرجع العميل",
              control: (
                <input
                  className="ktra-input"
                  value={formCustomerRef}
                  onChange={(e) => setFormCustomerRef(e.target.value)}
                  placeholder="طلب شراء، إشعار استلام…"
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
          }}
          onAddLine={addLine}
          addLineLabel={isStandalone ? "إضافة منتج" : "إضافة بند من الفاتورة"}
          emptyHint={
            isStandalone
              ? "لا توجد بنود — اضغط «إضافة منتج»"
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
            <span className="ktra-status-item">
              البنود <b>{formLines.length}</b>
            </span>
          }
        />
        {pickerOpen && (
          <InvoicePickerModal
            title="اختيار فاتورة المبيعات المرتبطة"
            rows={invoiceOptions}
            partnerHeader="العميل"
            emptyHint="لا توجد فواتير مبيعات مرحّلة."
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
    <CommercialDocumentsList<DeliveryNoteRow>
      title="إرساليات البيع"
      rows={rows}
      columns={columns}
      getRowKey={(r) => r.id}
      loading={loading}
      error={err}
      emptyHint="لا توجد إرساليات — اضغط «إرسالية جديدة»"
      countLabel={`العدد ${rows.length}`}
      searchValue={search}
      searchPlaceholder="بحث برقم المستند / الفاتورة / العميل…"
      onSearchChange={setSearch}
      onNew={() => void openNew()}
      onReload={() => void load()}
      newLabel="إرسالية جديدة"
      onRowDoubleClick={(r) => void openView(r.id)}
      extraActions={[
        {
          key: "outstanding",
          label: exporting ? "جارٍ التحضير…" : "طباعة البواقي غير المسلَّمة",
          icon: exporting ? <Loader2 className="animate-spin" /> : <Printer />,
          onClick: () => void printOutstanding(),
          separatorBefore: true,
        },
      ]}
    />
  );
};

export default DeliveryNotesPage;
