import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight, CheckCircle2, ClipboardList, Loader2, Plus, Receipt, RotateCcw,
  ShieldCheck, Trash2, Wrench,
} from "lucide-react";
import {
  addServiceOrderNote,
  addServiceOrderPart,
  approveServiceOrder,
  deleteServiceOrderPart,
  detachServiceInvoice,
  generateServiceInvoice,
  getServiceOrder,
  postCoveredParts,
  transitionServiceOrder,
  unpostCoveredParts,
  updateServiceOrder,
  type PartBilling,
  type ServiceOrderDetail,
  type ServiceOrderOutcome,
  type ServiceOrderStatus,
} from "../../services/afterSalesApi";
import { formatDateTimeValue, formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  PART_BILLING_LABELS,
  SERVICE_FLOW,
  SERVICE_OUTCOME_LABELS,
  SERVICE_STATUS_LABELS,
  isTerminalStatus,
  partBillingPillClass,
  serviceStatusPillClass,
  sumParts,
} from "../../utils/serviceOrder";
import { warrantyRemainingText, warrantyStatusLabel } from "../../utils/warranty";
import { warrantyPillClass } from "./warrantyStatus";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

/**
 * THA-24 م4 — مستند أمر الصيانة: من الشكوى حتى الحل في شاشة واحدة.
 *
 * ثلاثة عقود تحكم هذه الشاشة، وكلها انعكاس لعقود الخادم لا اجتهادٌ فوقها:
 *
 * 1. **الحالة تنتقل بزرّ محروس لا بحقل**: الشاشة لا تُرسل `status` في أي PATCH
 *    (الخادم يرفضه read_only أصلاً)، بل تنادي `transition/` فتمرّ من بواباتها.
 * 2. **أسباب المنع تُعرض لا تُستنتج**: `delivery_blockers` تأتي محسوبةً من
 *    الخادم؛ لو أعادت الشاشة استنتاجها لاختلفت رسالتها عن سبب الرفض الفعلي.
 * 3. **قفل البند يُقرأ من الخادم** (`is_materialized`): البند الذي تجسّد في
 *    مستند لا يُعدَّل ولا يُحذف — التعطيل هنا مجاملةٌ للعين، والمنع الحقيقي هناك.
 *
 * المسار المالي مساران لا يلتقيان: «مغطاة» تُرحَّل من هنا مصروفَ كفالة،
 * و«مفوترة» تُولِّد فاتورة **مسودة** تُراجَع وتُرحَّل من شاشة الفواتير القائمة.
 */

interface ProductOption {
  id: number;
  display_name?: string;
  name_ar?: string;
  name_en?: string;
  sku?: string;
  sale_price?: string | number | null;
}

interface Props {
  orderId: number;
  products: ProductOption[];
  onBack: () => void;
  onChanged?: () => void;
  onOpenInvoice?: (invoiceId: number) => void;
}

const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const cardClass = "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";

const productLabel = (p: ProductOption) =>
  p.display_name || p.name_ar || p.name_en || p.sku || `#${p.id}`;

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

type Tab = "file" | "parts" | "timeline";

export const ServiceOrderDocument: React.FC<Props> = ({
  orderId, products, onBack, onChanged, onOpenInvoice,
}) => {
  const { can } = usePermissions();
  const canEdit = can("aftersales.order.edit");
  const canPost = can("aftersales.order.post");
  const canUnpost = can("aftersales.order.unpost");
  const toast = useToast();
  const confirm = useConfirm();

  const [order, setOrder] = useState<ServiceOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("file");

  // مسودة الحقول النصية — تُحفظ بزرّ صريح لا مع كل حرف.
  const [diagnosis, setDiagnosis] = useState("");
  const [resolution, setResolution] = useState("");
  const [estimate, setEstimate] = useState("");
  const [waiver, setWaiver] = useState("");
  const [note, setNote] = useState("");

  const [newPart, setNewPart] = useState<{ product: string; quantity: string; billing: PartBilling; unit_price: string }>({
    product: "", quantity: "1", billing: "billable", unit_price: "0",
  });
  const [outcome, setOutcome] = useState<ServiceOrderOutcome>("repaired");
  const [labour, setLabour] = useState("");

  const absorb = useCallback((fresh: ServiceOrderDetail) => {
    setOrder(fresh);
    setDiagnosis(fresh.diagnosis);
    setResolution(fresh.resolution);
    setEstimate(fresh.estimated_amount ?? "");
    setWaiver(fresh.billing_waived_reason);
    setNewPart((p) => ({ ...p, billing: fresh.warranty_covered ? "covered" : "billable" }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      absorb(await getServiceOrder(orderId));
    } catch (e) {
      setErr(messageOf(e, "تعذّر تحميل أمر الصيانة"));
    } finally {
      setLoading(false);
    }
  }, [orderId, absorb]);

  useEffect(() => { void load(); }, [load]);

  /** كل إجراء يمرّ من هنا: يعرض الخطأ نصّاً كما ردّه الخادم ويُحدّث النسخة. */
  const run = async (
    action: () => Promise<ServiceOrderDetail | void>,
    successText: string,
  ) => {
    setBusy(true);
    setErr(null);
    try {
      const fresh = await action();
      if (fresh) absorb(fresh); else await load();
      toast(successText, "success");
      onChanged?.();
    } catch (e) {
      const text = messageOf(e, "تعذّر تنفيذ الإجراء");
      setErr(text);
      toast(text, "error");
    } finally {
      setBusy(false);
    }
  };

  const frozen = order ? isTerminalStatus(order.status) : true;
  const editable = canEdit && !frozen;

  const coveredPending = useMemo(
    () => (order?.parts || []).filter((p) => p.billing === "covered" && !p.is_materialized).length,
    [order],
  );
  const billablePending = useMemo(
    () => (order?.parts || []).filter((p) => p.billing === "billable" && !p.is_materialized).length,
    [order],
  );

  if (loading && !order) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-sm text-[var(--color-text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…
      </div>
    );
  }
  if (!order) {
    return (
      <div dir="rtl" className="space-y-3 p-4">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-sm text-[var(--color-primary)]">
          <ArrowRight className="h-4 w-4" /> رجوع للقائمة
        </button>
        <div role="alert" className="rounded-lg border border-[var(--color-border)] p-3 text-sm text-red-600 dark:text-red-400">
          {err || "أمر الصيانة غير موجود"}
        </div>
      </div>
    );
  }

  const saveFields = () =>
    run(
      () => updateServiceOrder(order.id, {
        diagnosis,
        resolution,
        estimated_amount: estimate.trim() === "" ? null : estimate.trim(),
        billing_waived_reason: waiver,
      }),
      "حُفظ الملف",
    );

  const move = (to: ServiceOrderStatus) =>
    run(
      () => transitionServiceOrder(order.id, {
        to_status: to,
        outcome: to === "delivered" ? outcome : undefined,
      }),
      to === "delivered" ? "سُلّم الجهاز" : `الحالة الآن: ${SERVICE_STATUS_LABELS[to]}`,
    );

  const cancelOrder = async () => {
    const ok = await confirm({
      title: "إلغاء أمر الصيانة",
      message: "الإلغاء بديل الحذف — يبقى الأمر في السجل بحالة «ملغى». متابعة؟",
    });
    if (!ok) return;
    void run(
      () => transitionServiceOrder(order.id, { to_status: "cancelled" }),
      "أُلغي أمر الصيانة",
    );
  };

  const addPart = () => {
    const productId = Number(newPart.product);
    if (!productId) { setErr("اختر الصنف أولاً"); return; }
    void run(
      async () => {
        await addServiceOrderPart(order.id, {
          product: productId,
          quantity: newPart.quantity || "1",
          billing: newPart.billing,
          unit_price: newPart.billing === "billable" ? newPart.unit_price || "0" : "0",
        });
        setNewPart((p) => ({ ...p, product: "", quantity: "1", unit_price: "0" }));
      },
      "أُضيفت القطعة",
    );
  };

  const removePart = async (partId: number) => {
    const ok = await confirm({ message: "حذف بند القطعة من أمر الصيانة؟" });
    if (!ok) return;
    void run(async () => { await deleteServiceOrderPart(order.id, partId); }, "حُذف البند");
  };

  const makeInvoice = () =>
    run(
      async () => {
        const result = await generateServiceInvoice(order.id, labour.trim() || undefined);
        toast(`وُلّدت الفاتورة ${result.invoice.invoice_number} كمسودة`, "success");
        return result.order;
      },
      "راجِع الفاتورة ورحّلها من شاشة الفواتير",
    );

  const coveredTotal = sumParts(order.parts, "covered");
  const billableTotal = sumParts(order.parts, "billable");

  return (
    <div dir="rtl" className="space-y-4 p-3 md:p-4" data-testid="service-order-document">
      {/* ── الرأس ────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-2.5 py-1.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]">
          <ArrowRight className="h-4 w-4" /> القائمة
        </button>
        <Wrench className="h-5 w-5 text-[var(--color-primary)]" />
        <span className="text-lg font-bold text-[var(--color-text)]">{order.order_number}</span>
        <span className={serviceStatusPillClass(order.status)}>{order.status_label}</span>
        {order.outcome && (
          <span className="text-xs text-[var(--color-text-muted)]">النتيجة: {order.outcome_label}</span>
        )}
        <span className="flex-1" />
        <span className="text-xs text-[var(--color-text-muted)]">
          استُلم {formatDateValue(order.order_date)}
        </span>
      </div>

      {/* ── شريط التغطية ─────────────────────────────────────────────────── */}
      {order.warranty_status ? (
        <div className={`${cardClass} flex flex-wrap items-center gap-2`} data-testid="warranty-banner">
          <ShieldCheck className="h-4 w-4 text-[var(--color-primary)]" />
          <span className={warrantyPillClass(order.warranty_status.status, order.warranty_status.days_remaining)}>
            {warrantyStatusLabel(order.warranty_status.status)}
          </span>
          <span className="text-sm text-[var(--color-text)]">
            الكفالة تنتهي {formatDateValue(order.warranty_status.end_date)} —{" "}
            {warrantyRemainingText(order.warranty_status.status, order.warranty_status.days_remaining)}
          </span>
          {order.warranty_status.supplier_warranty_active && (
            <span className="text-[11px] text-emerald-700 dark:text-emerald-400">
              كفالة المورد سارية حتى {formatDateValue(order.warranty_status.supplier_warranty_end_date)} — طالِب المورد بدل تحمّل الكلفة
            </span>
          )}
        </div>
      ) : (
        <div className={`${cardClass} text-sm text-[var(--color-text-muted)]`} data-testid="warranty-banner">
          لا بطاقة كفالة مربوطة بهذا الأمر — الإصلاح على حساب الزبون ما لم يُوسَم غير ذلك.
        </div>
      )}

      {/* ── شريط الحالة ──────────────────────────────────────────────────── */}
      <section className={cardClass}>
        <div className="flex flex-wrap items-center gap-2">
          {SERVICE_FLOW.map((step) => (
            <button
              key={step}
              type="button"
              disabled={!editable || busy || step === order.status}
              onClick={() => void move(step)}
              className={`rounded-lg px-2.5 py-1.5 text-xs font-bold disabled:opacity-40 ${
                step === order.status
                  ? "bg-[var(--color-primary)] text-white"
                  : "border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
              }`}
            >
              {SERVICE_STATUS_LABELS[step]}
            </button>
          ))}
          <span className="flex-1" />
          {!frozen && canEdit && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void cancelOrder()}
              className="rounded-lg border border-[var(--color-border)] px-2.5 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
              title={order.cancellation_blockers.join(" · ") || "إلغاء الأمر"}
            >
              إلغاء الأمر
            </button>
          )}
        </div>

        {order.cancellation_blockers.length > 0 && !frozen && (
          <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
            يمنع الإلغاء: {order.cancellation_blockers.join(" · ")}
          </p>
        )}

        {/* التسليم: النتيجة إلزامية، والموانع تُعرض كما يحسبها الخادم. */}
        {!frozen && (
          <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-[var(--color-border)] pt-3">
            <div className="w-44">
              <label className={labelClass} htmlFor="svc-outcome">نتيجة الصيانة</label>
              <select
                id="svc-outcome"
                className={inputClass}
                value={outcome}
                onChange={(e) => setOutcome(e.target.value as ServiceOrderOutcome)}
              >
                {Object.entries(SERVICE_OUTCOME_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              disabled={!editable || busy || order.delivery_blockers.length > 0}
              onClick={() => void move("delivered")}
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-bold text-white disabled:opacity-40"
              data-testid="deliver-button"
            >
              <CheckCircle2 className="h-4 w-4" /> تسليم الجهاز
            </button>
            {order.delivery_blockers.length > 0 && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="delivery-blockers">
                يمنع التسليم: {order.delivery_blockers.join(" · ")}
              </p>
            )}
          </div>
        )}
      </section>

      {err && (
        <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
          {err}
        </div>
      )}

      {/* ── التبويبات ────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1">
        {([["file", "الملف"], ["parts", `قطع الغيار (${formatNumber(order.parts.length)})`], ["timeline", "السجل الزمني"]] as [Tab, string][]).map(
          ([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`rounded-lg px-3 py-1.5 text-sm font-bold ${
                tab === key
                  ? "bg-[var(--color-primary)] text-white"
                  : "border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
              }`}
            >
              {label}
            </button>
          ),
        )}
      </div>

      {tab === "file" && (
        <section className={`${cardClass} space-y-3`}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className={labelClass}>الزبون</div>
              <div className="text-sm text-[var(--color-text)]">{order.partner_name || "—"}</div>
              {order.customer_phone && (
                <div className="text-[11px] text-[var(--color-text-muted)]">{order.customer_phone}</div>
              )}
            </div>
            <div>
              <div className={labelClass}>الجهاز</div>
              <div className="text-sm text-[var(--color-text)]">{order.product_name || "—"}</div>
              {order.serial && <div className="font-mono text-[11px] text-[var(--color-text-muted)]">{order.serial}</div>}
            </div>
            <div>
              <div className={labelClass}>حالة الاستلام</div>
              <div className="text-sm text-[var(--color-text)]">{order.received_condition || "—"}</div>
            </div>
            <div>
              <div className={labelClass}>الملحقات</div>
              <div className="text-sm text-[var(--color-text)]">{order.accessories || "—"}</div>
            </div>
          </div>

          <div>
            <div className={labelClass}>شكوى الزبون</div>
            <p className="rounded-lg bg-[var(--color-surface-2)] p-2.5 text-sm text-[var(--color-text)]">
              {order.complaint || "—"}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="svc-diagnosis">التشخيص</label>
              <textarea
                id="svc-diagnosis"
                rows={4}
                disabled={!editable}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60"
                value={diagnosis}
                onChange={(e) => setDiagnosis(e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="svc-resolution">ما جرى فعلاً (النتيجة)</label>
              <textarea
                id="svc-resolution"
                rows={4}
                disabled={!editable}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60"
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={labelClass} htmlFor="svc-estimate">التقدير المبدئي</label>
              <input
                id="svc-estimate"
                inputMode="decimal"
                disabled={!editable}
                className={inputClass}
                value={estimate}
                onChange={(e) => setEstimate(e.target.value)}
              />
              {order.approved_at ? (
                <p className="mt-1 text-[11px] text-emerald-700 dark:text-emerald-400">
                  وافق الزبون في {formatDateTimeValue(order.approved_at)}
                </p>
              ) : (
                editable && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void run(() => approveServiceOrder(order.id), "سُجّلت موافقة الزبون")}
                    className="mt-1 rounded-lg border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                  >
                    تسجيل موافقة الزبون
                  </button>
                )
              )}
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass} htmlFor="svc-waiver">
                سبب الإعفاء من الفوترة (يُحسم به أمر المال حين لا فاتورة)
              </label>
              <input
                id="svc-waiver"
                disabled={!editable}
                className={inputClass}
                value={waiver}
                onChange={(e) => setWaiver(e.target.value)}
                placeholder="مغطى بالكفالة / مجاملة…"
              />
              {editable && !waiver && !order.sales_invoice && (
                <button
                  type="button"
                  onClick={() => setWaiver("مغطى بالكفالة — بلا كلفة على الزبون")}
                  className="mt-1 rounded-lg border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                >
                  إعفاء: مغطى بالكفالة
                </button>
              )}
            </div>
          </div>

          {editable && (
            <div className="flex justify-end">
              <button
                type="button"
                disabled={busy}
                onClick={() => void saveFields()}
                className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} حفظ الملف
              </button>
            </div>
          )}
        </section>
      )}

      {tab === "parts" && (
        <section className={`${cardClass} space-y-3`}>
          {editable && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
              <div className="sm:col-span-2">
                <label className={labelClass} htmlFor="part-product">الصنف</label>
                <select
                  id="part-product"
                  className={inputClass}
                  value={newPart.product}
                  onChange={(e) => {
                    const id = e.target.value;
                    const found = products.find((p) => String(p.id) === id);
                    setNewPart((p) => ({
                      ...p,
                      product: id,
                      unit_price: found?.sale_price != null ? String(found.sale_price) : p.unit_price,
                    }));
                  }}
                >
                  <option value="">— اختر —</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>{productLabel(p)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass} htmlFor="part-qty">الكمية</label>
                <input
                  id="part-qty"
                  inputMode="decimal"
                  className={inputClass}
                  value={newPart.quantity}
                  onChange={(e) => setNewPart((p) => ({ ...p, quantity: e.target.value }))}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="part-billing">المسار</label>
                <select
                  id="part-billing"
                  className={inputClass}
                  value={newPart.billing}
                  onChange={(e) => setNewPart((p) => ({ ...p, billing: e.target.value as PartBilling }))}
                >
                  {Object.entries(PART_BILLING_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass} htmlFor="part-price">السعر</label>
                <input
                  id="part-price"
                  inputMode="decimal"
                  className={inputClass}
                  disabled={newPart.billing === "covered"}
                  value={newPart.billing === "covered" ? "" : newPart.unit_price}
                  onChange={(e) => setNewPart((p) => ({ ...p, unit_price: e.target.value }))}
                  placeholder={newPart.billing === "covered" ? "لا سعر — كلفتها من المخزن" : ""}
                />
              </div>
              <div className="sm:col-span-5 flex justify-end">
                <button
                  type="button"
                  disabled={busy}
                  onClick={addPart}
                  className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" /> إضافة قطعة
                </button>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>الصنف</th>
                  <th>الكمية</th>
                  <th>المسار</th>
                  <th>السعر</th>
                  <th>الحالة</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {order.parts.map((part) => (
                  <tr key={part.id}>
                    <td>{part.product_name}</td>
                    <td className="whitespace-nowrap">{formatNumber(Number(part.quantity))}</td>
                    <td>
                      <span className={partBillingPillClass(part.billing)}>{part.billing_label}</span>
                    </td>
                    <td className="whitespace-nowrap">
                      {part.billing === "billable" ? formatNumber(Number(part.unit_price)) : "—"}
                    </td>
                    <td className="whitespace-nowrap text-[11px] text-[var(--color-text-muted)]">
                      {part.is_materialized
                        ? (part.sales_invoice_line ? "مفوترة" : "مرحَّل صرفها")
                        : "بانتظار"}
                    </td>
                    <td className="whitespace-nowrap">
                      {editable && !part.is_materialized && (
                        <button
                          type="button"
                          onClick={() => void removePart(part.id)}
                          className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                          title="حذف البند"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {order.parts.length === 0 && (
            <p className="p-4 text-center text-sm text-[var(--color-text-muted)]">
              لا قطع غيار على هذا الأمر بعد.
            </p>
          )}

          {/* ── المسار الأول: مغطاة بالكفالة ─────────────────────────────── */}
          <div className="rounded-xl border border-[var(--color-border)] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-indigo-600" />
              <span className="text-sm font-bold text-[var(--color-text)]">
                مغطاة بالكفالة — مصروف علينا بلا إيراد
              </span>
              <span className="text-[11px] text-[var(--color-text-muted)]">
                تُقيَّد بكلفة المخزن التاريخية لا بسعر البيع ({formatNumber(coveredTotal)} بسعر البيع للمقارنة)
              </span>
              <span className="flex-1" />
              {order.covered_posted_at ? (
                <>
                  <span className="text-[11px] text-emerald-700 dark:text-emerald-400">
                    رُحّل في {formatDateTimeValue(order.covered_posted_at)}
                  </span>
                  {canUnpost && !frozen && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void run(() => unpostCoveredParts(order.id), "أُلغي ترحيل صرف القطع")}
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50"
                      data-testid="unpost-covered"
                    >
                      <RotateCcw className="h-4 w-4" /> تراجع عن الترحيل
                    </button>
                  )}
                </>
              ) : (
                canPost && !frozen && (
                  <button
                    type="button"
                    disabled={busy || coveredPending === 0}
                    onClick={() => void run(() => postCoveredParts(order.id), "رُحّل صرف قطع الكفالة")}
                    className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-bold text-white disabled:opacity-40"
                    data-testid="post-covered"
                  >
                    <ClipboardList className="h-4 w-4" /> ترحيل صرف القطع
                  </button>
                )
              )}
            </div>
          </div>

          {/* ── المسار الثاني: مفوترة على الزبون ─────────────────────────── */}
          <div className="rounded-xl border border-[var(--color-border)] p-3">
            <div className="flex flex-wrap items-end gap-2">
              <Receipt className="h-4 w-4 text-[var(--color-primary)]" />
              <span className="text-sm font-bold text-[var(--color-text)]">
                مفوترة على الزبون — {formatNumber(billableTotal)}
              </span>
              <span className="flex-1" />
              {order.sales_invoice ? (
                <>
                  <span className="text-[11px] text-[var(--color-text-muted)]">
                    فاتورة {order.sales_invoice_number} — راجِعها ورحّلها من شاشة الفواتير
                  </span>
                  {onOpenInvoice && (
                    <button
                      type="button"
                      onClick={() => onOpenInvoice(order.sales_invoice!)}
                      className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                    >
                      فتح الفاتورة
                    </button>
                  )}
                  {canPost && !frozen && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void run(() => detachServiceInvoice(order.id), "فُصلت الفاتورة عن الأمر")}
                      className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:opacity-50"
                    >
                      فصل الفاتورة
                    </button>
                  )}
                </>
              ) : (
                canPost && !frozen && (
                  <>
                    <div className="w-40">
                      <label className={labelClass} htmlFor="svc-labour">أجرة الصيانة</label>
                      <input
                        id="svc-labour"
                        inputMode="decimal"
                        className={inputClass}
                        value={labour}
                        onChange={(e) => setLabour(e.target.value)}
                        placeholder={order.estimated_amount ?? "0"}
                      />
                    </div>
                    <button
                      type="button"
                      disabled={busy || (billablePending === 0 && !labour.trim() && !order.estimated_amount)}
                      onClick={() => void makeInvoice()}
                      className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-40"
                      data-testid="generate-invoice"
                    >
                      <Receipt className="h-4 w-4" /> توليد فاتورة الصيانة
                    </button>
                  </>
                )
              )}
            </div>
          </div>
        </section>
      )}

      {tab === "timeline" && (
        <section className={`${cardClass} space-y-3`}>
          {editable && (
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex-1">
                <label className={labelClass} htmlFor="svc-note">ملاحظة على الملف</label>
                <input
                  id="svc-note"
                  className={inputClass}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="اتصلنا بالزبون…"
                />
              </div>
              <button
                type="button"
                disabled={busy || !note.trim()}
                onClick={() => void run(
                  async () => { await addServiceOrderNote(order.id, note.trim()); setNote(""); },
                  "أُضيفت الملاحظة",
                )}
                className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50"
              >
                إضافة
              </button>
            </div>
          )}

          <ol className="space-y-2">
            {order.events.map((event) => (
              <li key={event.id} className="rounded-lg border border-[var(--color-border)] p-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[var(--color-surface-2)] px-2 py-0.5 text-[11px] font-bold text-[var(--color-text)]">
                    {event.event_type_label}
                  </span>
                  <span className="text-[11px] text-[var(--color-text-muted)]">
                    {formatDateTimeValue(event.created_at)}
                    {event.actor_name && ` · ${event.actor_name}`}
                  </span>
                </div>
                <p className="mt-1 text-sm text-[var(--color-text)]">{event.text}</p>
              </li>
            ))}
          </ol>
          {order.events.length === 0 && (
            <p className="p-4 text-center text-sm text-[var(--color-text-muted)]">لا أحداث بعد.</p>
          )}
        </section>
      )}
    </div>
  );
};

export default ServiceOrderDocument;
