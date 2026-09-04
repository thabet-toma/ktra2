/**
 * SalesOrdersPage — «طلبيات الزبائن» (T-ORDERS).
 *
 * الحلقة بين عرض السعر والفاتورة: الطلبية المؤكَّدة **تحجز الكمية** حتى تاريخ
 * محدَّد (إعداد الشركة)، وتقبل **عربوناً** (سند قبض مرحَّل مربوط بها)، وتُلغى
 * بلا حذف، ثم تُحوَّل إلى فاتورة فينتهي حجزها.
 *
 * لا قيد محاسبي للطلبية نفسها — العربون وحده حدث مالي.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ShareRowButton } from "../shared/ShareRowButton";
import {
  Trash2, Save, Loader2, X, CheckCircle, Banknote, FileText, ExternalLink,
  AlertTriangle, Info, Undo2,
} from "lucide-react";
import {
  listSalesOrders,
  getSalesOrder,
  createSalesOrder,
  updateSalesOrder,
  deleteSalesOrder,
  confirmSalesOrder,
  cancelSalesOrder,
  convertSalesOrderToInvoice,
  recordOrderDeposit,
  getSalesSettings,
  type SalesOrderRow,
} from "../../services/salesApi";
import { accountingApi } from "../../services/accountingApi";
import { apiGetList } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized, formatTimeValue, todayIso } from "../../utils/formatDate";
import { openInNewTab } from "../../utils/openInNewTab";
import { isReservationActive } from "../../utils/documentBadges";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "../../utils/documentDraft";
import { SalesProductPickerModal, type SalesProductPickerItem, formatProductPrimaryName } from "./SalesProductPickerModal";
import {
  CommercialDocumentEditor,
  type CommercialHeaderField,
  type CommercialLineColumn,
  type CommercialToolbarAction,
} from "../shared/CommercialDocumentEditor";
import {
  CommercialDocumentsList,
  type CommercialListColumn,
} from "../shared/CommercialDocumentsList";

type Partner = { id: number; name: string };
type Account = {
  id: number; code: string; name: string; parent: number | null; account_type?: string;
};
type Product = SalesProductPickerItem & { name: string; unit_price?: string };

type LineState = {
  id?: number;
  product_id: string;
  product_name: string;
  quantity: string;
  unit_price: string;
};

const blankLine = (): LineState => ({
  product_id: "", product_name: "", quantity: "1", unit_price: "",
});

/** ISSUE #121: حمولة المسودّة المحلية — خفيفة تكفي وحدها لإعادة بناء الشاشة
 *  (issue #118)، لا صلة بحمولة الحفظ الخادمية التي يبنيها `save`. */
interface SalesOrderDraftPayload {
  formCustomer: string;
  formDate: string;
  formDelivery: string;
  formNotes: string;
  formLines: LineState[];
}

const STATUS_TONE: Record<string, string> = {
  draft: "ktra-bg-panel ktra-text-ink",
  confirmed: "bg-green-100 text-green-700",
  converted: "ktra-bg-panel ktra-text-ink",
  cancelled: "bg-amber-100 text-amber-700",
};

export const SalesOrdersPage: React.FC = () => {
  const confirm = useConfirm();
  const toast = useToast();

  const [orders, setOrders] = useState<SalesOrderRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [allowDelete, setAllowDelete] = useState(true);
  const [reserveDays, setReserveDays] = useState(7);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formCustomer, setFormCustomer] = useState("");
  const [formDate, setFormDate] = useState(() => todayIso());
  const [formDelivery, setFormDelivery] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [formLines, setFormLines] = useState<LineState[]>([blankLine()]);
  const [pickerIdx, setPickerIdx] = useState<number | null>(null);

  // ISSUE #121: علامة «لُمِس» — تُرفَع مزامنةً داخل كل معالج تعديل مستخدم.
  const [touched, setTouched] = useState(false);
  const markTouched = () => setTouched(true);
  // شريط اليتامى (issue #119 §٧) — إخفاءٌ محليّ بلا مسّ المسودّات نفسها.
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  // نافذة العربون
  const [depositFor, setDepositFor] = useState<SalesOrderRow | null>(null);
  const [depositAmount, setDepositAmount] = useState("");
  const [depositAccount, setDepositAccount] = useState<number | "">("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setOrders(await listSalesOrders(statusFilter ? { status: statusFilter } : undefined));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const tenantId = resolveTenantId();
        const [parts, prods, accs, settings] = await Promise.all([
          // T-PARTYPURE: طلبية بيع = زبائن فقط — كانت القائمة تعرض الموردين معهم.
          accountingApi.getPartners("Customer") as Promise<Partner[]>,
          listPickerProducts<any>(tenantId),
          accountingApi.getAccounts() as Promise<Account[]>,
          getSalesSettings().catch(() => null),
        ]);
        if (!alive) return;
        setPartners(parts || []);
        setProducts((prods || []).map((p: any) => ({
          id: p.id,
          sku: p.sku || "",
          barcode: p.barcode,
          quantity_on_hand: String(p.available_quantity ?? p.quantity_on_hand ?? "0"),
          name_ar: p.name_ar || p.name || "",
          name_en: p.name_en || "",
          name: p.name_ar || p.name_en || p.name || p.sku || `#${p.id}`,
          unit_price: p.sale_price ?? p.selling_price ?? p.unit_price ?? "",
        })));
        setAccounts(accs || []);
        if (settings) {
          setAllowDelete(settings.allow_document_delete !== false);
          setReserveDays(Number(settings.order_reserve_days ?? 7));
          if (settings.default_cash_account) setDepositAccount(settings.default_cash_account);
        }
      } catch { /* القوائم الفارغة تكفي — الرسالة تظهر عند الحفظ */ }
    })();
    return () => { alive = false; };
  }, []);

  const resetForm = () => {
    setSelectedId(null);
    setFormCustomer("");
    setFormDate(todayIso());
    setFormDelivery("");
    setFormNotes("");
    setFormLines([blankLine()]);
    setTouched(false);
  };

  const openOrder = async (id: number) => {
    try {
      const detail = await getSalesOrder(id);
      setSelectedId(detail.id);
      setFormCustomer(String(detail.customer));
      setFormDate(detail.order_date?.slice(0, 10) || todayIso());
      setFormDelivery(detail.delivery_date?.slice(0, 10) || "");
      setFormNotes(detail.notes || "");
      setFormLines(
        (detail.lines || []).map((l) => ({
          id: l.id,
          product_id: String(l.product),
          product_name: l.product_name || "",
          quantity: l.quantity,
          unit_price: l.unit_price,
        })),
      );
      // تعبئةٌ من الخادم — لا تُعامَل كتعديل مستخدم (issue #121).
      setTouched(false);
      setShowForm(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  };

  // T-SLINEAGE: `?open=12` يفتح الطلبية نفسها — رابط الفاتورة إلى مصدرها يجب أن
  // يصل إلى المستند لا إلى قائمة يبحث فيها المستخدم عنه. نفس عقد شاشة العروض.
  const [pendingDocId, setPendingDocId] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get("open"),
  );
  useEffect(() => {
    if (!pendingDocId || loading) return;
    const target = orders.find((order) => String(order.id) === pendingDocId);
    if (!target) return;
    setPendingDocId(null);
    void openOrder(target.id);
  }, [pendingDocId, loading, orders]);

  const formTotal = useMemo(
    () => formLines.reduce(
      (s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0),
    [formLines],
  );

  const save = async () => {
    if (!formCustomer) { setErr("اختر الزبون."); return; }
    const lines = formLines.filter((l) => l.product_id && Number(l.quantity) > 0);
    if (!lines.length) { setErr("أضف بنداً واحداً على الأقل."); return; }
    setSaving(true);
    setErr(null);
    try {
      const body = {
        customer: Number(formCustomer),
        order_date: formDate,
        delivery_date: formDelivery || null,
        notes: formNotes,
        lines: lines.map((l) => ({
          product: Number(l.product_id),
          quantity: l.quantity,
          unit_price: l.unit_price || "0",
        })),
      };
      if (selectedId) await updateSalesOrder(selectedId, body);
      else await createSalesOrder(body);
      toast(selectedId ? "تم تعديل الطلبية" : "تم إنشاء الطلبية", "success");
      setShowForm(false);
      resetForm();
      await load();
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      void discardDraft();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const act = async (fn: () => Promise<unknown>, okMsg: string) => {
    try {
      await fn();
      toast(okMsg, "success");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذّر تنفيذ الإجراء");
    }
  };

  const doCancel = async (o: SalesOrderRow) => {
    if (!(await confirm({
      title: "إلغاء الطلبية",
      message: `ستُعلَّم الطلبية ${o.order_number} «ملغاة» ويُفرَج عن الكمية المحجوزة — تبقى في السجل ولن تُحذف. متابعة؟`,
      confirmText: "إلغاء الطلبية",
    }))) return;
    await act(() => cancelSalesOrder(o.id), "تم إلغاء الطلبية");
  };

  const doDelete = async (o: SalesOrderRow) => {
    if (!(await confirm({
      title: "حذف الطلبية",
      message: `سيُحذف المستند ${o.order_number} نهائياً. الأفضل «إلغاء» ليبقى في السجل. متابعة؟`,
      confirmText: "حذف",
      danger: true,
    }))) return;
    await act(() => deleteSalesOrder(o.id), "تم الحذف");
  };

  const submitDeposit = async () => {
    if (!depositFor) return;
    if (!(Number(depositAmount) > 0)) { setErr("أدخل مبلغ العربون."); return; }
    if (!depositAccount) { setErr("اختر حساب الصندوق/البنك."); return; }
    await act(
      () => recordOrderDeposit(depositFor.id, {
        amount: depositAmount,
        cash_or_bank_account: Number(depositAccount),
      }),
      "تم تسجيل العربون وترحيل سند القبض",
    );
    setDepositFor(null);
    setDepositAmount("");
  };

  const inputClass =
    "h-9 px-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm outline-none focus:ring-1 focus:ring-emerald-500";

  const selectedOrder = orders.find((order) => order.id === selectedId);
  const toolbarActions: CommercialToolbarAction[] = [
    {
      key: "save",
      label: saving ? "جاري الحفظ…" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: saving ? undefined : () => void save(),
      disabled: saving,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: () => { setShowForm(false); resetForm(); },
      danger: true,
      separatorBefore: true,
    },
    { key: "print", label: "طباعة", icon: <FileText />, onClick: () => window.print() },
  ];
  const headerFields: CommercialHeaderField[] = [
    {
      key: "number",
      label: "رقم الطلبية",
      control: <input className="ktra-input ktra-input--hl" readOnly
        value={selectedOrder?.order_number || (selectedId ? `#${selectedId}` : "تلقائي")} />,
    },
    {
      key: "date",
      label: "تاريخ الطلبية",
      control: <input type="date" className="ktra-input" value={formDate}
        onChange={(event) => { markTouched(); setFormDate(event.target.value); }} />,
    },
    {
      key: "delivery",
      label: "تاريخ التسليم",
      control: <input type="date" className="ktra-input" value={formDelivery}
        onChange={(event) => { markTouched(); setFormDelivery(event.target.value); }} />,
    },
    {
      key: "type",
      label: "نوع المستند",
      control: <input className="ktra-input" readOnly value="طلبية زبون" />,
    },
    {
      key: "customer",
      label: "الزبون / الحساب",
      control: (
        <select className="ktra-input" value={formCustomer}
          onChange={(event) => { markTouched(); setFormCustomer(event.target.value); }}>
          <option value="">— اختر الزبون —</option>
          {partners.map((partner) => (
            <option key={partner.id} value={partner.id}>{partner.name}</option>
          ))}
        </select>
      ),
    },
    {
      key: "customerName",
      label: "الاسم",
      control: <input className="ktra-input" readOnly
        value={partners.find((partner) => String(partner.id) === formCustomer)?.name || ""} />,
    },
    {
      key: "reserve",
      label: "الحجز الافتراضي",
      control: <input className="ktra-input" readOnly
        value={reserveDays ? `${reserveDays} أيام` : "بلا حجز"} />,
    },
    {
      key: "deposit",
      label: "العربون",
      control: <input className="ktra-input" readOnly value={formatMoney(selectedOrder?.deposit_amount || 0)} />,
    },
    {
      key: "status",
      label: "الحالة",
      control: <input className="ktra-input" readOnly
        value={selectedOrder?.status_display || selectedOrder?.status || "مسودة"} />,
    },
  ];
  // الطلبية المحوَّلة تفتح فاتورتها من داخلها أيضاً — لا من القائمة وحدها.
  if (selectedOrder?.invoice) {
    headerFields.push({
      key: "invoice",
      label: "الفاتورة الناتجة",
      control: (
        <button
          type="button"
          data-testid="open-order-invoice"
          className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-3 text-xs font-bold text-white shadow-sm transition-colors hover:bg-blue-700"
          title={`فتح الفاتورة ${selectedOrder.invoice_number || `#${selectedOrder.invoice}`}`}
          onClick={() => openInNewTab(`/sales/invoices/${selectedOrder.invoice}`)}
        >
          <ExternalLink className="h-3.5 w-3.5" />
          <span>فتح الفاتورة</span>
          <b dir="ltr">{selectedOrder.invoice_number || `#${selectedOrder.invoice}`}</b>
        </button>
      ),
    });
  }
  const editorColumns: CommercialLineColumn<LineState>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    {
      key: "name",
      header: "وصف المنتج",
      width: "45%",
      render: (line, index) => (
        <button type="button" className="flex w-full items-center justify-between gap-2 px-1 text-right"
          onClick={() => setPickerIdx(index)}>
          <span className={line.product_name ? "ktra-text-ink" : "ktra-text-soft"}>
            {line.product_name || "اختر منتجاً…"}
          </span>
          <span className="ktra-text-accent">…</span>
        </button>
      ),
    },
    { key: "quantity", header: "الكمية", width: "100px", align: "center", type: "number" },
    { key: "unit_price", header: "سعر الوحدة", width: "120px", align: "center", type: "number" },
    { key: "total", header: "الإجمالي", width: "120px", align: "center", readOnly: true },
    {
      key: "del",
      header: "",
      width: "36px",
      align: "center",
      render: (_line, index) => (
        <button type="button" className="ktra-iconbtn ktra-iconbtn--danger"
          onClick={() => { markTouched(); setFormLines((lines) => lines.length > 1 ? lines.filter((_, rowIndex) => rowIndex !== index) : lines); }}
          title="حذف السطر">
          <Trash2 className="h-3 w-3" />
        </button>
      ),
    },
  ];
  const listColumns: CommercialListColumn<SalesOrderRow>[] = [
    { key: "order_number", header: "رقم الطلبية", width: "130px",
      render: (order) => <b>{order.order_number}</b> },
    { key: "customer", header: "الزبون", render: (order) => <>{order.customer_name || "—"}</> },
    { key: "date", header: "التاريخ", width: "110px",
      render: (order) => <>{formatDateLocalized(order.order_date)}</> },
    // T-RESERVE: التاريخ وحده لا يقول إن كان الحجز سارياً (الملغاة/المحوَّلة/
    // المنتهية تحمله أيضاً) — نفس قاعدة الخادم تُعرض صريحةً.
    { key: "reserve", header: "الحجز", width: "150px",
      render: (order) => (
        isReservationActive(order.status, order.reserved_until, todayIso()) ? (
          <span title="محجوز بطلبية مؤكَّدة سارية"
            style={{ color: "var(--ktra-warn, #b06800)", fontWeight: 600 }}>
            محجوز حتى {formatDateLocalized(order.reserved_until)}
          </span>
        ) : (
          <span className="text-[var(--ktra-ink-soft)]">
            {order.reserved_until
              ? `انتهى الحجز (${formatDateLocalized(order.reserved_until)})`
              : "بلا حجز"}
          </span>
        )
      ) },
    { key: "total", header: "الإجمالي", width: "110px", numeric: true,
      render: (order) => <>{formatMoney(order.grand_total)}</> },
    { key: "deposit", header: "العربون", width: "110px", numeric: true,
      render: (order) => <span className="text-emerald-600">{formatMoney(order.deposit_amount)}</span> },
    { key: "remaining", header: "المتبقي", width: "110px", numeric: true,
      render: (order) => <span className="text-amber-600">{formatMoney(order.remaining_amount)}</span> },
    {
      key: "status",
      header: "الحالة",
      width: "150px",
      // «محوّلة لفاتورة» بلا رقم الفاتورة ولا رابطها تُلزم المستخدم بالبحث عنها
      // في شاشة أخرى — الرقم هنا زرٌّ يفتحها (نفس نمط مستندات الشراء).
      render: (order) => (
        <div className="flex flex-col leading-tight">
          <span className={`self-start rounded px-2 py-0.5 text-xs ${STATUS_TONE[order.status] || ""}`}>
            {order.status_display || order.status}
          </span>
          {order.invoice && (
            <button
              type="button"
              className="ktra-text-accent mt-0.5 text-right text-[10px] hover:underline"
              title={`فتح الفاتورة ${order.invoice_number || `#${order.invoice}`}`}
              onClick={(event) => {
                event.stopPropagation();
                openInNewTab(`/sales/invoices/${order.invoice}`);
              }}
            >
              ← {order.invoice_number || `#${order.invoice}`}
            </button>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "260px",
      render: (order) => (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button onClick={() => void openOrder(order.id)} className="ktra-text-accent hover:underline">تعديل</button>
          {/* DOC-SHARE: الطلبية تُرسَل للزبون ليؤكّدها — والعربون المدفوع
              يظهر عليها مع «المتبقي عند التسليم». */}
          <ShareRowButton
            docType="sales_order"
            docId={order.id}
            docLabel={`طلبية ${order.order_number}`}
            partyName={order.customer_name || undefined}
          />
          {order.status === "draft" && (
            <button onClick={() => void act(() => confirmSalesOrder(order.id), "تم تأكيد الطلبية وحجز الكمية")}
              className="text-green-600 hover:underline">تأكيد وحجز</button>
          )}
          {order.status !== "converted" && order.status !== "cancelled" && (
            <>
              <button onClick={() => { setDepositFor(order); setDepositAmount(""); }}
                className="text-emerald-700 hover:underline">عربون</button>
              <button onClick={() => void act(
                () => convertSalesOrderToInvoice(order.id), "تم تحويل الطلبية إلى فاتورة")}
                className="text-blue-600 hover:underline">تحويل لفاتورة</button>
              <button onClick={() => void doCancel(order)} className="text-amber-600 hover:underline">إلغاء</button>
            </>
          )}
          {allowDelete && (
            <button onClick={() => void doDelete(order)} className="ktra-text-state hover:underline">حذف</button>
          )}
        </div>
      ),
    },
  ];

  /* ISSUE #121: مسودّة محلية (IndexedDB، issue #118) — هذه الشاشة لا تحفظ
   * شيئاً محلياً اليوم. الحمولة كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة؛ لا
   * صلة بحمولة الحفظ الخادمية التي يبنيها `save`. */
  const draftPayload = useMemo<SalesOrderDraftPayload>(
    () => ({ formCustomer, formDate, formDelivery, formNotes, formLines }),
    [formCustomer, formDate, formDelivery, formNotes, formLines],
  );

  const onRestoreDraft = useCallback((restored: SalesOrderDraftPayload) => {
    setFormCustomer(restored.formCustomer);
    setFormDate(restored.formDate);
    setFormDelivery(restored.formDelivery);
    setFormNotes(restored.formNotes);
    setFormLines(restored.formLines);
    setTouched(true);
  }, []);

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft<SalesOrderDraftPayload>({
    docType: "sales_order",
    docId: selectedId,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    // لا حقل `is_posted` حقيقي للطلبية — الحالتان النهائيتان («محوَّلة»/«ملغاة»)
    // تُعامَلان معاملة «مرحَّل»: اطّلاعٌ على المسودّة فقط بلا استعادةٍ تلقائية.
    isPosted: !!selectedOrder && (selectedOrder.status === "converted" || selectedOrder.status === "cancelled"),
    // ختمُ الخادم لحظةَ فتح المستند — كان المُسلسِل لا يكشف `updated_at`
    // فسقط فحصُ «تغيّر المستند بعد مسودتك» (#109 §٩)؛ كُشف ووُصِل.
    docUpdatedAt: selectedOrder?.updated_at ?? null,
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

  /** «تراجع» على شريط الاستعادة: يعيد الشاشة إلى حالتها المحفوظة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    if (selectedId != null) void openOrder(selectedId);
    else resetForm();
    void discardDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, discardDraft]);

  /* ISSUE #120: الحفظ المحلي فشل فعلاً — لافتةٌ لاصقة تطلب حفظاً يدوياً. */
  const draftSaveFailedBanner = draftSaveFailed ? (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="draft-save-failed-banner"
      className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>تعذّر حفظ نسخة محلية من هذه الطلبية — اضغط «تخزين» يدوياً كي لا يضيع عملك.</span>
    </div>
  ) : null;

  /* ISSUE #118: شريط الاستعادة التلقائية — إخبارٌ لا سؤال. */
  const draftRestoreBanner = draftBanner ? (
    <div className="ktra-banner ktra-banner--warn" role="status" data-testid="draft-restored-banner">
      <Info className="h-4 w-4 shrink-0" />
      <span>
        {draftBanner.eligibility === "restore" &&
          `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "stale" &&
          `تغيّرت الطلبية بعد مسودتك (مسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "posted" &&
          `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) لهذه الطلبية المنتهية — للاطّلاع فقط.`}
      </span>
      {draftBanner.eligibility === "restore" && (
        <button type="button" className="ktra-toolbtn" onClick={handleUndoDraft} data-testid="draft-restored-undo">
          <Undo2 className="h-4 w-4" /> تراجع
        </button>
      )}
      {draftBanner.eligibility === "stale" && (
        <>
          <button type="button" className="ktra-toolbtn" onClick={() => onRestoreDraft(draftBanner.payload)} data-testid="draft-stale-preview">
            استعرض مسودتي
          </button>
          <button type="button" className="ktra-toolbtn" onClick={() => void discardDraft()} data-testid="draft-stale-discard">
            تجاهلها
          </button>
        </>
      )}
    </div>
  ) : null;

  /* شريط اليتامى (issue #119 §٧): مسودّات طلبيةٍ جديدة أخرى تُركت في تبويبات أخرى. */
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
        <X className="h-4 w-4" /> إخفاء
      </button>
    </div>
  ) : null;

  if (showForm) {
    return (
      <CommercialDocumentEditor<LineState>
        title="طلبية بيع"
        state={selectedOrder ? `${selectedOrder.status_display || selectedOrder.status} — ${selectedOrder.order_number}` : "مسودة — طلبية جديدة"}
        actions={toolbarActions}
        headerFields={headerFields}
        lines={formLines}
        lineColumns={editorColumns}
        getLineCell={(line, key) => {
          const index = formLines.indexOf(line);
          if (key === "seq") return index + 1;
          if (key === "quantity") return line.quantity;
          if (key === "unit_price") return line.unit_price;
          if (key === "total") return formatMoney((Number(line.quantity) || 0) * (Number(line.unit_price) || 0));
          return "";
        }}
        getLineKey={(line, index) => line.id ?? `new-${index}`}
        onLineChange={(index, key, value) => {
          if (key !== "quantity" && key !== "unit_price") return;
          markTouched();
          setFormLines((lines) => lines.map((line, rowIndex) =>
            rowIndex === index ? { ...line, [key]: value } : line));
        }}
        onAddLine={() => { markTouched(); setFormLines((lines) => [...lines, blankLine()]); }}
        banner={
          <>
            {draftSaveFailedBanner}
            {draftRestoreBanner}
            {orphanDraftsBanner}
            {err ? <div className="ktra-banner ktra-banner--err">{err}</div> : null}
          </>
        }
        tabs={[{
          key: "notes",
          label: "الملاحظات",
          content: <div className="px-1 py-2">
            <textarea className="ktra-input w-full" rows={4} value={formNotes} data-testid="order-notes"
              onChange={(event) => { markTouched(); setFormNotes(event.target.value); }} placeholder="ملاحظات الطلبية…" />
          </div>,
        }]}
        totals={<>
          <div className="ktra-total-row"><span>مجموع البنود</span><span className="ktra-total-value">{formatMoney(formTotal)}</span></div>
          <div className="ktra-total-row"><span>العربون</span><span className="ktra-total-value">{formatMoney(selectedOrder?.deposit_amount || 0)}</span></div>
          <div className="ktra-total-row ktra-total-row--grand"><span>إجمالي الطلبية</span><span className="ktra-total-value">{formatMoney(formTotal)}</span></div>
        </>}
        status={<>
          <span className="ktra-status-item">عدد المنتجات <b>{formLines.length}</b></span>
          <span className="ktra-status-item">
            {reserveDays ? `الحجز ${reserveDays} أيام بعد التأكيد` : "الحجز معطّل"}
          </span>
          {draftSavedAt && (
            <span className="ktra-status-item" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
        </>}
        overlay={pickerIdx !== null ? (
          <SalesProductPickerModal
            isOpen
            products={products}
            onClose={() => setPickerIdx(null)}
            onSelect={(productId) => {
              markTouched();
              const product = products.find((item) => Number(item.id) === Number(productId));
              setFormLines((lines) => lines.map((line, index) => index === pickerIdx ? {
                ...line,
                product_id: String(productId),
                product_name: product ? formatProductPrimaryName(product) : `#${productId}`,
                unit_price: line.unit_price || String(product?.unit_price ?? ""),
              } : line));
              setPickerIdx(null);
            }}
          />
        ) : undefined}
      />
    );
  }

  return (
    <>
      <CommercialDocumentsList<SalesOrderRow>
        title="عروض وطلبيات البيع"
        state="طلبيات الزبائن"
        rows={orders}
        columns={listColumns}
        getRowKey={(order) => order.id}
        loading={loading}
        error={err}
        emptyHint="لا طلبيات — أنشئ طلبية أو حوّل عرض سعر إليها."
        countLabel={`${orders.length} طلبية — ${reserveDays ? `الحجز ${reserveDays} أيام` : "بلا حجز"}`}
        statusValue={statusFilter}
        statusOptions={[
          { value: "", label: "كل الحالات" },
          { value: "draft", label: "مسودة" },
          { value: "confirmed", label: "مؤكَّدة" },
          { value: "converted", label: "محوّلة لفاتورة" },
          { value: "cancelled", label: "ملغاة" },
        ]}
        onStatusChange={setStatusFilter}
        onNew={() => { resetForm(); setShowForm(true); }}
        onReload={() => void load()}
        newLabel="طلبية جديدة"
        onRowDoubleClick={(order) => void openOrder(order.id)}
      />
      {depositFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
              <h3 className="flex items-center gap-2 font-bold text-[var(--color-text)]">
                <Banknote className="w-4 h-4" /> عربون الطلبية {depositFor.order_number}
              </h3>
              <button onClick={() => setDepositFor(null)} className="p-1 text-[var(--color-text-muted)]">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 p-4">
              <div className="text-xs text-[var(--color-text-muted)]">
                إجمالي الطلبية {formatMoney(depositFor.grand_total)} · المقبوض {formatMoney(depositFor.deposit_amount)}
              </div>
              <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                مبلغ العربون
                <input
                  className={inputClass}
                  inputMode="decimal"
                  value={depositAmount}
                  onChange={(e) => setDepositAmount(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                حساب الصندوق / البنك
                <AccountTreeField
                  accounts={accounts}
                  value={depositAccount}
                  onChange={(id) => setDepositAccount(id ?? "")}
                  purpose="cash"
                  className={inputClass}
                  title="اختيار الصندوق / البنك"
                />
              </label>
              <p className="text-[11px] text-[var(--color-text-muted)]">
                يُسجَّل سند قبض مرحَّل «على الحساب» باسم الزبون ويُربط بهذه الطلبية.
              </p>
            </div>
            <div className="flex justify-end gap-2 border-t border-[var(--color-border)] px-4 py-3">
              <button
                onClick={() => setDepositFor(null)}
                className="rounded-lg border border-[var(--color-border)] px-4 py-1.5 text-sm text-[var(--color-text-muted)]"
              >
                إلغاء
              </button>
              <button
                onClick={() => void submitDeposit()}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white"
              >
                <CheckCircle className="w-4 h-4" /> قبض العربون
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default SalesOrdersPage;
