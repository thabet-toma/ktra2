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
import {
  Trash2, Save, Loader2, X, CheckCircle, Banknote, FileText,
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
import { resolveTenantId } from "../../utils/tenantContext";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
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
type Account = { id: number; code: string; name: string; account_type?: string };
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

const STATUS_TONE: Record<string, string> = {
  draft: "aseel-bg-panel aseel-text-ink",
  confirmed: "bg-green-100 text-green-700",
  converted: "aseel-bg-panel aseel-text-ink",
  cancelled: "bg-amber-100 text-amber-700",
};

export const SalesOrdersPage: React.FC = () => {
  const confirm = useConfirm();
  const toast = useToast();

  const [orders, setOrders] = useState<SalesOrderRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [cashAccounts, setCashAccounts] = useState<Account[]>([]);
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
          accountingApi.getPartners() as Promise<Partner[]>,
          apiGetList<any>("inventory/products/", { tenantId }),
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
        setCashAccounts(
          (accs || []).filter((a) => {
            const t = (a.account_type || "").toLowerCase();
            if (t === "cash" || t === "bank") return true;
            return t === "asset" && /^110|صندوق|بنك|cash|bank/i.test(`${a.code} ${a.name}`);
          }),
        );
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
      setShowForm(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  };

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
      control: <input className="aseel-input aseel-input--hl" readOnly
        value={selectedOrder?.order_number || (selectedId ? `#${selectedId}` : "تلقائي")} />,
    },
    {
      key: "date",
      label: "تاريخ الطلبية",
      control: <input type="date" className="aseel-input" value={formDate}
        onChange={(event) => setFormDate(event.target.value)} />,
    },
    {
      key: "delivery",
      label: "تاريخ التسليم",
      control: <input type="date" className="aseel-input" value={formDelivery}
        onChange={(event) => setFormDelivery(event.target.value)} />,
    },
    {
      key: "type",
      label: "نوع المستند",
      control: <input className="aseel-input" readOnly value="طلبية زبون" />,
    },
    {
      key: "customer",
      label: "الزبون / الحساب",
      control: (
        <select className="aseel-input" value={formCustomer}
          onChange={(event) => setFormCustomer(event.target.value)}>
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
      control: <input className="aseel-input" readOnly
        value={partners.find((partner) => String(partner.id) === formCustomer)?.name || ""} />,
    },
    {
      key: "reserve",
      label: "الحجز الافتراضي",
      control: <input className="aseel-input" readOnly
        value={reserveDays ? `${reserveDays} أيام` : "بلا حجز"} />,
    },
    {
      key: "deposit",
      label: "العربون",
      control: <input className="aseel-input" readOnly value={formatMoney(selectedOrder?.deposit_amount || 0)} />,
    },
    {
      key: "status",
      label: "الحالة",
      control: <input className="aseel-input" readOnly
        value={selectedOrder?.status_display || selectedOrder?.status || "مسودة"} />,
    },
  ];
  const editorColumns: CommercialLineColumn<LineState>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    {
      key: "name",
      header: "بيان الصنف",
      width: "45%",
      render: (line, index) => (
        <button type="button" className="flex w-full items-center justify-between gap-2 px-1 text-right"
          onClick={() => setPickerIdx(index)}>
          <span className={line.product_name ? "aseel-text-ink" : "aseel-text-soft"}>
            {line.product_name || "اختر صنفاً…"}
          </span>
          <span className="aseel-text-accent">…</span>
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
        <button type="button" className="aseel-iconbtn aseel-iconbtn--danger"
          onClick={() => setFormLines((lines) => lines.length > 1 ? lines.filter((_, rowIndex) => rowIndex !== index) : lines)}
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
    { key: "reserve", header: "الحجز حتى", width: "120px",
      render: (order) => <>{order.reserved_until ? formatDateLocalized(order.reserved_until) : "—"}</> },
    { key: "total", header: "الإجمالي", width: "110px", numeric: true,
      render: (order) => <>{formatMoney(order.grand_total)}</> },
    { key: "deposit", header: "العربون", width: "110px", numeric: true,
      render: (order) => <span className="text-emerald-600">{formatMoney(order.deposit_amount)}</span> },
    { key: "remaining", header: "المتبقي", width: "110px", numeric: true,
      render: (order) => <span className="text-amber-600">{formatMoney(order.remaining_amount)}</span> },
    {
      key: "status",
      header: "الحالة",
      width: "110px",
      render: (order) => (
        <span className={`rounded px-2 py-0.5 text-xs ${STATUS_TONE[order.status] || ""}`}>
          {order.status_display || order.status}
        </span>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "260px",
      render: (order) => (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button onClick={() => void openOrder(order.id)} className="aseel-text-accent hover:underline">تعديل</button>
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
            <button onClick={() => void doDelete(order)} className="aseel-text-state hover:underline">حذف</button>
          )}
        </div>
      ),
    },
  ];

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
          setFormLines((lines) => lines.map((line, rowIndex) =>
            rowIndex === index ? { ...line, [key]: value } : line));
        }}
        onAddLine={() => setFormLines((lines) => [...lines, blankLine()])}
        banner={err ? <div className="aseel-banner aseel-banner--err">{err}</div> : undefined}
        tabs={[{
          key: "notes",
          label: "الملاحظات",
          content: <div className="px-1 py-2">
            <textarea className="aseel-input w-full" rows={4} value={formNotes}
              onChange={(event) => setFormNotes(event.target.value)} placeholder="ملاحظات الطلبية…" />
          </div>,
        }]}
        totals={<>
          <div className="aseel-total-row"><span>مجموع البنود</span><span className="aseel-total-value">{formatMoney(formTotal)}</span></div>
          <div className="aseel-total-row"><span>العربون</span><span className="aseel-total-value">{formatMoney(selectedOrder?.deposit_amount || 0)}</span></div>
          <div className="aseel-total-row aseel-total-row--grand"><span>إجمالي الطلبية</span><span className="aseel-total-value">{formatMoney(formTotal)}</span></div>
        </>}
        status={<>
          <span className="aseel-status-item">عدد الأصناف <b>{formLines.length}</b></span>
          <span className="aseel-status-item">
            {reserveDays ? `الحجز ${reserveDays} أيام بعد التأكيد` : "الحجز معطّل"}
          </span>
        </>}
        overlay={pickerIdx !== null ? (
          <SalesProductPickerModal
            isOpen
            products={products}
            onClose={() => setPickerIdx(null)}
            onSelect={(productId) => {
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
                <select
                  className={inputClass}
                  value={depositAccount}
                  onChange={(e) => setDepositAccount(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">— اختر —</option>
                  {cashAccounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                  ))}
                </select>
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
