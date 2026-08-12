import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Search, ShieldAlert, ShieldCheck, X } from "lucide-react";
import {
  createServiceOrder,
  lookupIntake,
  type IntakeLookup,
  type ServiceOrderDetail,
  type ServiceOrderDraft,
} from "../../services/afterSalesApi";
import { formatDateValue, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { warrantyRemainingText, warrantyStatusLabel } from "../../utils/warranty";
import { warrantyPillClass } from "./warrantyStatus";
import { useToast } from "../../contexts/ToastContext";

/**
 * THA-24 م4 — استقبال جهاز: معرّفٌ واحد يُسأل عنه، وثلاثة مصادر تُجيب.
 *
 * البحث لا يقرّر شيئاً بل يعرض ما يعرفه النظام: بطاقة كفالة، ووحدة بعناها
 * بنسبها وفاتورتها، وسجل جهازٍ حسّاس **إن كانت وحدته مرخّصة**. لا مفتاح أجنبي
 * بين الجدولين في أي اتجاه — الرابط معرّفٌ نصي وحده، فيبقى إطفاء كل وحدة
 * مستقلاً. والتطابق المزدوج يعرض الشريحتين معاً والمستخدم يختار ما يعبّئ منه.
 *
 * قرار التغطية يُلتقط هنا لأنه لحظة الاستقبال هي لحظته: بعدها يصير كل بند قطعة
 * قراراً منفصلاً، ومن لم يقرّر عند الباب يقرّر عند التسليم وقد فات الأوان.
 */

interface ProductOption {
  id: number;
  display_name?: string;
  name_ar?: string;
  name_en?: string;
  sku?: string;
}

interface PartnerOption {
  id: number;
  name: string;
  phone?: string;
}

interface Props {
  products: ProductOption[];
  customers: PartnerOption[];
  onClose: () => void;
  onCreated: (order: ServiceOrderDetail) => void;
}

const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const productLabel = (p: ProductOption) =>
  p.display_name || p.name_ar || p.name_en || p.sku || `#${p.id}`;

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

export const ServiceOrderIntakeModal: React.FC<Props> = ({
  products, customers, onClose, onCreated,
}) => {
  const toast = useToast();
  const [draft, setDraft] = useState<Partial<ServiceOrderDraft>>({
    order_date: todayIso(),
    partner: null,
    customer_name: "",
    customer_phone: "",
    product: null,
    serial: "",
    device_description: "",
    received_condition: "",
    accessories: "",
    complaint: "",
    warranty_covered: false,
  });
  const [lookup, setLookup] = useState<IntakeLookup | null>(null);
  const [looking, setLooking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const patch = <K extends keyof ServiceOrderDraft>(key: K, value: ServiceOrderDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const serial = (draft.serial || "").trim();

  // البحث يضرب الخادم — نفس إبطاء شاشة الكفالة (500ms) لا طلبٌ لكل حرف.
  useEffect(() => {
    if (!serial) { setLookup(null); return; }
    let cancelled = false;
    const timer = setTimeout(() => {
      setLooking(true);
      lookupIntake(serial)
        .then((result) => { if (!cancelled) setLookup(result); })
        .catch(() => { if (!cancelled) setLookup(null); })
        .finally(() => { if (!cancelled) setLooking(false); });
    }, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [serial]);

  const activeCard = useMemo(
    () => lookup?.warranty.cards.find((c) => c.status === "active") || null,
    [lookup],
  );

  /** التعبئة من الوحدة التي بعناها: الصنف والزبون معروفان، فلا يُعاد إدخالهما. */
  const fillFromUnit = useCallback(() => {
    const unit = lookup?.warranty.unit;
    if (!unit) return;
    setDraft((d) => ({
      ...d,
      product: unit.product ?? d.product ?? null,
      device_description: d.device_description || unit.product_name || "",
      customer_name: d.customer_name || unit.customer_name || "",
      warranty_covered: Boolean(activeCard) || d.warranty_covered,
    }));
    toast("عُبّئ من بيانات الوحدة المباعة", "success");
  }, [lookup, activeCard, toast]);

  const fillFromDevice = useCallback((index: number) => {
    const device = lookup?.sensitive_devices[index];
    if (!device) return;
    setDraft((d) => ({
      ...d,
      device_description: d.device_description || device.model_name,
      customer_name: d.customer_name || device.customer_name,
      customer_phone: d.customer_phone || device.customer_phone,
    }));
    toast("عُبّئ من سجل الأجهزة الحساسة", "success");
  }, [lookup, toast]);

  const problems = useMemo(() => {
    const list: string[] = [];
    const named = draft.partner || (draft.customer_name || "").trim();
    if (!named) list.push("حدّد الزبون أو اكتب اسمه");
    if (!serial && !draft.product && !(draft.device_description || "").trim()) {
      list.push("حدّد الجهاز برقمه التسلسلي أو صنفه أو وصفه");
    }
    if (!(draft.complaint || "").trim()) list.push("اكتب شكوى الزبون");
    return list;
  }, [draft, serial]);

  const save = async () => {
    if (problems.length > 0) { setErr(problems.join(" · ")); return; }
    setBusy(true);
    setErr(null);
    try {
      const order = await createServiceOrder({
        ...draft,
        serial,
        // البطاقة السارية تُربط بالأمر فتظهر تغطيتها في رأسه بلا بحثٍ ثانٍ.
        warranty_card: activeCard?.id ?? null,
      });
      toast(`فُتح أمر الصيانة ${order.order_number}`, "success");
      onCreated(order);
    } catch (e) {
      setErr(messageOf(e, "تعذّر فتح أمر الصيانة"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="استقبال جهاز للصيانة"
      data-testid="service-order-intake"
    >
      <div className="w-full max-w-3xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <header className="flex items-center gap-2 border-b border-[var(--color-border)] p-3">
          <ShieldCheck className="h-5 w-5 text-[var(--color-primary)]" />
          <h2 className="font-bold text-[var(--color-text)]">استقبال جهاز للصيانة</h2>
          <span className="flex-1" />
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 hover:bg-[var(--color-surface-2)]" title="إغلاق">
            <X className="h-4 w-4 text-[var(--color-text-muted)]" />
          </button>
        </header>

        <div className="space-y-4 p-3 md:p-4">
          {/* ── المعرّف والبحث الموحّد ──────────────────────────────────── */}
          <section>
            <label className={labelClass} htmlFor="intake-serial">
              الرقم التسلسلي أو IMEI — يُبحث عنه في الكفالات والمبيعات وسجل الأجهزة معاً
            </label>
            <div className="relative">
              <input
                id="intake-serial"
                className={`${inputClass} pl-9 font-mono`}
                value={draft.serial || ""}
                onChange={(e) => patch("serial", e.target.value)}
                placeholder="SN / IMEI…"
              />
              <span className="absolute inset-y-0 left-2 flex items-center text-[var(--color-text-muted)]">
                {looking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </span>
            </div>

            {lookup && (
              <div className="mt-2 space-y-2" data-testid="intake-lookup-results">
                {lookup.warranty.cards.map((card) => (
                  <div key={card.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={warrantyPillClass(card.status, card.days_remaining)}>
                        {warrantyStatusLabel(card.status)}
                      </span>
                      <span className="text-[var(--color-text)]">
                        بطاقة كفالة تنتهي {formatDateValue(card.end_date)}
                      </span>
                      <span className="text-[11px] text-[var(--color-text-muted)]">
                        {warrantyRemainingText(card.status, card.days_remaining)}
                      </span>
                    </div>
                    {card.supplier_warranty_end_date && (
                      <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                        كفالة المورد{card.supplier_warranty_active ? " سارية" : " منتهية"} حتى{" "}
                        {formatDateValue(card.supplier_warranty_end_date)}
                        {card.supplier_warranty_active && " — لا تتحمّل الشركة كلفةً يتحمّلها المورد"}
                      </div>
                    )}
                  </div>
                ))}

                {lookup.warranty.unit && (
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] p-2.5 text-sm">
                    <span className="text-[var(--color-text)]">
                      وحدة من بضاعتنا: {lookup.warranty.unit.product_name}
                    </span>
                    {lookup.warranty.unit.sales_invoice_number && (
                      <span className="text-[11px] text-[var(--color-text-muted)]">
                        بيعت بفاتورة {lookup.warranty.unit.sales_invoice_number}
                        {lookup.warranty.unit.sale_date && ` بتاريخ ${formatDateValue(lookup.warranty.unit.sale_date)}`}
                        {lookup.warranty.unit.customer_name && ` — ${lookup.warranty.unit.customer_name}`}
                      </span>
                    )}
                    <span className="flex-1" />
                    <button
                      type="button"
                      onClick={fillFromUnit}
                      className="rounded-lg border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                    >
                      تعبئة من الوحدة
                    </button>
                  </div>
                )}

                {lookup.sensitive_devices.map((device, index) => (
                  <div key={device.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] p-2.5 text-sm">
                    <ShieldAlert className="h-4 w-4 text-amber-600" />
                    <span className="text-[var(--color-text)]">
                      مسجَّل في سجل الأجهزة الحساسة: {device.model_name}
                    </span>
                    <span className="text-[11px] text-[var(--color-text-muted)]">
                      {device.status_display} · بتاريخ {formatDateValue(device.registered_at)}
                    </span>
                    <span className="flex-1" />
                    <button
                      type="button"
                      onClick={() => fillFromDevice(index)}
                      className="rounded-lg border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                    >
                      تعبئة من السجل
                    </button>
                  </div>
                ))}

                {lookup.open_orders.length > 0 && (
                  <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                    لهذا الجهاز {formatNumber(lookup.open_orders.length)} أمر صيانة سابق غير ملغى:{" "}
                    {lookup.open_orders.map((o) => `${o.order_number} (${o.status_display})`).join(" · ")}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* ── الزبون والجهاز ─────────────────────────────────────────── */}
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="intake-partner">الزبون من القائمة</label>
              <select
                id="intake-partner"
                className={inputClass}
                value={draft.partner ?? ""}
                onChange={(e) => {
                  const id = e.target.value ? Number(e.target.value) : null;
                  const found = customers.find((c) => c.id === id);
                  setDraft((d) => ({
                    ...d,
                    partner: id,
                    customer_phone: d.customer_phone || found?.phone || "",
                  }));
                }}
              >
                <option value="">— زبون عابر (اكتب اسمه) —</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-customer-name">اسم الزبون</label>
              <input
                id="intake-customer-name"
                className={inputClass}
                value={draft.customer_name || ""}
                onChange={(e) => patch("customer_name", e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-phone">الهاتف</label>
              <input
                id="intake-phone"
                className={inputClass}
                value={draft.customer_phone || ""}
                onChange={(e) => patch("customer_phone", e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-date">تاريخ الاستلام</label>
              <input
                id="intake-date"
                type="date"
                className={inputClass}
                value={draft.order_date || ""}
                onChange={(e) => patch("order_date", e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-product">الصنف</label>
              <select
                id="intake-product"
                className={inputClass}
                value={draft.product ?? ""}
                onChange={(e) => patch("product", e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— بلا صنف (جهاز لم نبعه) —</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{productLabel(p)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-device">وصف الجهاز</label>
              <input
                id="intake-device"
                className={inputClass}
                value={draft.device_description || ""}
                onChange={(e) => patch("device_description", e.target.value)}
                placeholder="لابتوب أسود…"
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-condition">حالة الجهاز عند الاستلام</label>
              <input
                id="intake-condition"
                className={inputClass}
                value={draft.received_condition || ""}
                onChange={(e) => patch("received_condition", e.target.value)}
                placeholder="خدوش على الغطاء…"
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-accessories">الملحقات المستلمة</label>
              <input
                id="intake-accessories"
                className={inputClass}
                value={draft.accessories || ""}
                onChange={(e) => patch("accessories", e.target.value)}
                placeholder="شاحن، حقيبة…"
              />
            </div>
          </section>

          <section>
            <label className={labelClass} htmlFor="intake-complaint">شكوى الزبون (بكلماته)</label>
            <textarea
              id="intake-complaint"
              rows={3}
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              value={draft.complaint || ""}
              onChange={(e) => patch("complaint", e.target.value)}
            />
            <label className="mt-2 flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input
                type="checkbox"
                checked={Boolean(draft.warranty_covered)}
                onChange={(e) => patch("warranty_covered", e.target.checked)}
              />
              الإصلاح مغطى بالكفالة — تُضاف قطع الغيار افتراضياً كمصروف كفالة لا كبند مفوتر
            </label>
          </section>

          {err && (
            <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}
        </div>

        <footer className="flex items-center gap-2 border-t border-[var(--color-border)] p-3">
          <span className="text-[11px] text-[var(--color-text-muted)]">
            {problems.length > 0 ? problems.join(" · ") : "جاهز للفتح"}
          </span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          >
            إلغاء
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void save()}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} فتح أمر الصيانة
          </button>
        </footer>
      </div>
    </div>
  );
};

export default ServiceOrderIntakeModal;
