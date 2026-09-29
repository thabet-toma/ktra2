import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Search, ShieldAlert, ShieldCheck, X } from "lucide-react";
import {
  createServiceOrder,
  lookupIntakeCard,
  lookupIntake,
  resolveWarrantyScan,
  type IntakeLookup,
  type IntakeMatchKind,
  type IntakeResult,
  type IntakeUnitWithoutCard,
  type ServiceOrderDetail,
  type ServiceOrderDraft,
} from "../../services/afterSalesApi";
import { formatDateValue, formatTimeValue, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { formatProductPrimaryName } from "../../utils/productDisplayName";
import {
  duplicateOpenOrderOf,
  duplicateReasonValid,
  INTAKE_VERDICT_TONE_CLASSES,
  REPAIR_FAULT_CONFIRM_TEXT,
  intakeVerdictLabel,
  intakeVerdictTone,
  INVOICE_PIECE_CONFIRM_TEXT,
  looksLikeWarrantyScan,
  warrantyRemainingText,
  warrantyStatusLabel,
  type DuplicateOpenOrder,
} from "../../utils/warranty";
import { warrantyPillClass } from "./warrantyStatus";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { DocumentDraftBanners } from "../shared/DocumentDraftBanners";
import { ServiceOrderReferralPanel } from "./ServiceOrderReferralPanel";

/**
 * THA-24 م4 — استقبال جهاز: معرّفٌ واحد يُسأل عنه، وثلاثة مصادر تُجيب.
 *
 * #240 — النموذج الموحّد: يُفتح من نافذة البطاقة (`initialCardId`) أو من مسح QR
 * أو من البحث (تسلسلي / فاتورة / هاتف) أو يدوياً. **الحكم يحسبه الخادم**
 * (`verdict`) وهنا يُرسم فقط، وكذلك التعبئة (`prefill`) وقاعدة التكرار — الواجهة
 * لا تكرّر قاعدةً منها، فلا تختلف عمّا سيرفضه الخادم فعلاً.
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
  /** بطاقة تُحمَّل وتُعبَّأ منها الشاشة فور الفتح (من نافذة البطاقة أو رابط عميق). */
  initialCardId?: number | null;
  /** نصٌّ يُبحث عنه فور الفتح (رابط عميق `?serial=`). */
  initialSerial?: string;
  onClose: () => void;
  onCreated: (order: ServiceOrderDetail) => void;
  /** فتح أمرٍ قائم — من نافذة التكرار أو من قائمة الأوامر المفتوحة على النتيجة. */
  onOpenOrder?: (orderId: number) => void;
}

const MATCH_LABELS: Record<IntakeMatchKind, string> = {
  serial: "طابق الرقم التسلسلي",
  invoice: "طابق رقم الفاتورة",
  phone: "طابق هاتف الزبون",
  card: "بطاقة محدَّدة",
};

const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";


const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

/** الحمولة الافتراضية عند فتح المودال — نفس الشكل المطلوب لإعادة بناء الشاشة
 *  من مسودّة محلية (issue #118)، فتُستعمل لكلا الغرضين. */
const buildDefaultDraft = (): Partial<ServiceOrderDraft> => ({
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
  warranty_card: null,
  warranty_covered: false,
});

export const ServiceOrderIntakeModal: React.FC<Props> = ({
  products, customers, initialCardId = null, initialSerial = "", onClose, onCreated, onOpenOrder,
}) => {
  const toast = useToast();
  const [draft, setDraft] = useState<Partial<ServiceOrderDraft>>(buildDefaultDraft);
  const [searchText, setSearchText] = useState(initialSerial);
  const [lookup, setLookup] = useState<IntakeLookup | null>(null);
  const [looking, setLooking] = useState(false);
  const [selected, setSelected] = useState<IntakeResult | null>(null);
  const [pieceConfirmed, setPieceConfirmed] = useState(false);
  const [repairConfirmed, setRepairConfirmed] = useState(false);
  // #241: مربوطٌ برقم البطاقة فيسقط تلقائياً عند اختيار بطاقةٍ أخرى أو تفريغ الاختيار.
  const [paidReferralCard, setPaidReferralCard] = useState<number | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateOpenOrder | null>(null);
  const [duplicateReason, setDuplicateReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // ISSUE #121: علامة «لُمِس» — تُرفَع مزامنةً داخل كل معالج تعديل مستخدم (لا
  // مشتقّة داخل useEffect؛ راجع تعليق hooks/useDocumentDraft.ts).
  const [touched, setTouched] = useState(false);
  const markTouched = () => setTouched(true);

  const patch = <K extends keyof ServiceOrderDraft>(key: K, value: ServiceOrderDraft[K]) => {
    markTouched();
    setDraft((d) => ({ ...d, [key]: value }));
  };

  const serial = (draft.serial || "").trim();

  const searchTerm = searchText.trim();
  const paidDespiteReferral = selected?.verdict === "referral" && paidReferralCard === selected.card.id;
  const referralPending = selected?.verdict === "referral" && !paidDespiteReferral;

  /** اختيار صفّ: التعبئة كما يردّها الخادم، وتأكيد القطعة يبدأ غير مؤكَّد دائماً. */
  const applyResult = useCallback((result: IntakeResult, fromUser: boolean) => {
    if (fromUser) markTouched();
    const { prefill } = result;
    setSelected(result);
    setPieceConfirmed(false);
    setRepairConfirmed(false);
    setDraft((d) => ({
      ...d,
      partner: prefill.partner,
      customer_name: prefill.customer_name,
      customer_phone: prefill.customer_phone,
      product: prefill.product,
      serial: prefill.serial,
      device_description: prefill.device_description,
      warranty_card: prefill.warranty_card,
      warranty_covered: prefill.warranty_covered,
    }));
  }, []);

  /** بطاقةٌ معروفة الرقم (نافذة البطاقة، مسح QR، رابط عميق): حكمها يأتي من `lookup/` نفسها. */
  const loadCard = useCallback(async (cardId: number, apply: boolean) => {
    setLooking(true);
    setErr(null);
    try {
      const row = (await lookupIntakeCard(cardId)).results[0];
      if (apply) applyResult(row, false);
      else setSelected(row);
    } catch (e) {
      setErr(messageOf(e, "تعذّر تحميل البطاقة"));
    } finally {
      setLooking(false);
    }
  }, [applyResult]);

  useEffect(() => {
    if (initialCardId) void loadCard(initialCardId, true);
    // مرّةً عند الفتح — تغيّر الخصائص لاحقاً لا يعيد التعبئة فوق ما كتبه المستخدم.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // البحث يضرب الخادم — نفس إبطاء شاشة الكفالة (500ms) لا طلبٌ لكل حرف.
  useEffect(() => {
    if (!searchTerm) { setLookup(null); return; }
    let cancelled = false;
    const timer = setTimeout(() => {
      setLooking(true);
      setErr(null);
      if (looksLikeWarrantyScan(searchTerm)) {
        resolveWarrantyScan(searchTerm)
          .then((card) => {
            if (cancelled) return;
            setLookup(null);
            return loadCard(card.id, true);
          })
          .catch((e) => {
            if (cancelled) return;
            setLookup(null);
            setErr(messageOf(e, "لا توجد كفالة لهذا الرمز في شركتك"));
          })
          .finally(() => { if (!cancelled) setLooking(false); });
        return;
      }
      lookupIntake(searchTerm)
        .then((result) => { if (!cancelled) setLookup(result); })
        .catch(() => { if (!cancelled) setLookup(null); })
        .finally(() => { if (!cancelled) setLooking(false); });
    }, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [searchTerm, loadCard]);

  /** الوحدة التي بعناها بلا بطاقة: المنتج والزبون معروفان، والأمر يُفتح مدفوعاً. */
  const fillFromUnit = useCallback((unit: IntakeUnitWithoutCard) => {
    markTouched();
    setSelected(null);
    setPieceConfirmed(false);
    setRepairConfirmed(false);
    setDraft((d) => ({
      ...d,
      partner: unit.partner?.id ?? d.partner ?? null,
      customer_name: unit.partner?.name ?? d.customer_name ?? "",
      product: unit.product ?? d.product ?? null,
      serial: unit.serial,
      device_description: d.device_description || unit.product_name || "",
      warranty_card: null,
      warranty_covered: false,
    }));
    toast("عُبّئ من بيانات الوحدة المباعة — لا بطاقة كفالة لها", "success");
  }, [toast]);

  const fillFromDevice = useCallback((index: number) => {
    const device = lookup?.sensitive_devices[index];
    if (!device) return;
    markTouched();
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
      list.push("حدّد الجهاز برقمه التسلسلي أو منتجه أو وصفه");
    }
    if (!(draft.complaint || "").trim()) list.push("اكتب شكوى الزبون");
    return list;
  }, [draft, serial]);

  /* ISSUE #121: مسودّة محلية (IndexedDB، issue #118) — هذا المودال يفتح أمر
   * صيانة جديداً دائماً (لا تحرير أمرٍ قائم)، فـ`docId`/`isPosted`/
   * `docUpdatedAt` ثوابت مثل `SalesReturnEditor`. `draft` نفسه خفيفٌ ويكفي
   * وحده لإعادة بناء الشاشة، فيُستعمل كحمولةٍ مباشرةً — لا صلة بحمولة الحفظ
   * الخادمية (`createServiceOrder`) التي تضيف `serial`/`warranty_card`
   * المشتقّين. `lookup`/`looking`/`busy`/`err` مستبعدة عمداً: نتائج بحثٍ
   * وحالة تحميل/خطأ تُعاد اشتقاقها من `draft.serial` عند إعادة التحميل، لا
   * جزءاً من الشاشة المطلوب استعادتها. */
  const draftPayload = draft;

  const onRestoreDraft = useCallback((restored: Partial<ServiceOrderDraft>) => {
    setDraft(restored);
    // استعادةٌ من مسودّة تعني اختلافاً عن الشاشة الفارغة — تُسجَّل «ملموسة»
    // فوراً كي يبقى الحارس وسياسة الحفظ متّسقين مع ما يراه المستخدم فعلاً.
    setTouched(true);
    // الحكم لا يُحفظ في المسودّة (الخادم يحسبه بتاريخ اليوم) — يُجلب من جديد.
    if (restored.warranty_card) void loadCard(restored.warranty_card, false);
  }, [loadCard]);

  // #240: مفتاح المسودّة `service_order_intake` + `card:<id>` حين فُتح النموذج على بطاقة —
  // مسودّةٌ لكل بطاقة فلا تدهس بطاقةٌ أخرى ما كُتب لهذه. بلا بطاقة: مفتاح التبويب كما كان.
  const draftApi = useDocumentDraft<Partial<ServiceOrderDraft>>({
    docType: "service_order_intake",
    docId: initialCardId ? `card:${initialCardId}` : null,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    isPosted: false,
    docUpdatedAt: null,
  });
  const { draftSavedAt, draftSaveFailed, discardDraft } = draftApi;

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

  /** «تراجع» على شريط الاستعادة: يعيد النموذج إلى حالته الفارغة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    setDraft(buildDefaultDraft());
    setLookup(null);
    setSelected(null);
    setPieceConfirmed(false);
    setRepairConfirmed(false);
    setSearchText("");
    setTouched(false);
    void discardDraft();
  }, [discardDraft]);

  /** «تمّ» على شاشة الإحالة: انتهى المسار عمداً بلا أمر، فلا تبقى مسودّةٌ تُعرض للاستعادة. */
  const finishReferral = () => {
    setTouched(false);
    void discardDraft();
    onClose();
  };

  const save = async (openDespiteReason?: string) => {
    if (problems.length > 0) { setErr(problems.join(" · ")); return; }
    setBusy(true);
    setErr(null);
    try {
      const order = await createServiceOrder({
        ...draft,
        serial,
        warranty_card: draft.warranty_card ?? null,
        // القطعة تُؤكَّد على بطاقة الفاتورة وحدها؛ والخادم يفرض ذلك عند الإنشاء.
        invoice_piece_confirmed: Boolean(selected?.prefill.requires_item_confirm && pieceConfirmed),
        repair_fault_confirmed: Boolean(selected?.prefill.requires_repair_confirm && repairConfirmed),
        ...(paidDespiteReferral ? { paid_despite_referral: true, warranty_covered: false } : {}),
        ...(openDespiteReason ? { duplicate_open_reason: openDespiteReason.trim() } : {}),
      });
      toast(`فُتح أمر الصيانة ${order.order_number}`, "success");
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      setTouched(false);
      void discardDraft();
      onCreated(order);
    } catch (e) {
      const existing = duplicateOpenOrderOf(e);
      if (existing) {
        setDuplicate(existing);
        setDuplicateReason("");
      } else {
        setErr(messageOf(e, "تعذّر فتح أمر الصيانة"));
      }
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

        <DocumentDraftBanners draft={draftApi} onApplyDraft={onRestoreDraft} onUndo={handleUndoDraft} isTouched={touched} />

        <div className="space-y-4 p-3 md:p-4">
          {/* ── المعرّف والبحث الموحّد ──────────────────────────────────── */}
          <section>
            <label className={labelClass} htmlFor="intake-serial">
              رقم تسلسلي أو IMEI أو رقم فاتورة أو هاتف الزبون أو رابط QR الكفالة — بحثٌ بمطابقةٍ تامّة
            </label>
            <div className="relative">
              <input
                id="intake-serial"
                className={`${inputClass} pl-9 font-mono`}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="SN / IMEI / فاتورة / 05…"
              />
              <span className="absolute inset-y-0 left-2 flex items-center text-[var(--color-text-muted)]">
                {looking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </span>
            </div>

            {lookup?.message && (
              <div className="mt-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-[var(--color-text)]" data-testid="intake-lookup-message">
                {lookup.message}
              </div>
            )}

            {lookup && (
              <div className="mt-2 space-y-2" data-testid="intake-lookup-results">
                {lookup.results.map((row) => {
                  const dealer = row.card.dealer;
                  const manufacturer = row.card.manufacturer;
                  const isSelected = selected?.card.id === row.card.id;
                  return (
                    <div
                      key={row.card.id}
                      className={`rounded-lg border p-2.5 text-sm ${
                        isSelected
                          ? "border-[var(--color-primary)] bg-[var(--color-surface-2)]"
                          : "border-[var(--color-border)] bg-[var(--color-surface-2)]"
                      }`}
                      data-testid="intake-result"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={warrantyPillClass(dealer.status, dealer.days_remaining)}>
                          {warrantyStatusLabel(dealer.status)}
                        </span>
                        <span className="font-semibold text-[var(--color-text)]">
                          {row.card.device_name || "جهاز"}
                        </span>
                        {row.card.serial && (
                          <span className="font-mono text-[11px] text-[var(--color-text-muted)]">{row.card.serial}</span>
                        )}
                        <span className="rounded-full bg-[var(--color-surface)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">
                          {MATCH_LABELS[row.matched_on]}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                        {row.card.source === "repair" ? "كفالة إصلاح" : "كفالة التاجر"} تنتهي {formatDateValue(dealer.end_date)} — {warrantyRemainingText(dealer.status, dealer.days_remaining)}
                        {row.card.source === "repair" && row.card.origin_order_number && ` · أمر ${row.card.origin_order_number}`}
                        {row.card.source === "repair" && row.card.coverage_scope && ` · ${row.card.coverage_scope}`}
                        {row.card.customer_name && ` · ${row.card.customer_name}`}
                        {row.card.sales_invoice_number && ` · فاتورة ${row.card.sales_invoice_number}`}
                        {row.card.quantity > 0 && ` · المغطّى ${formatNumber(row.card.covered_quantity)} من ${formatNumber(row.card.quantity)}`}
                      </div>
                      {manufacturer && manufacturer.status && (
                        <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                          كفالة المصنع ({manufacturer.warrantor}) {warrantyStatusLabel(manufacturer.status)} حتى{" "}
                          {formatDateValue(manufacturer.end_date)}
                        </div>
                      )}
                      <div
                        className={`mt-2 rounded-lg border px-2.5 py-1.5 text-xs font-bold ${INTAKE_VERDICT_TONE_CLASSES[intakeVerdictTone(row.verdict)]}`}
                        data-testid="intake-result-verdict"
                        data-verdict={row.verdict}
                      >
                        {intakeVerdictLabel(row.verdict)}
                      </div>
                      {row.open_orders.length > 0 && (
                        <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                          أوامر مفتوحة عليها:{" "}
                          {row.open_orders.map((o, index) => (
                            <React.Fragment key={o.id}>
                              {index > 0 && " · "}
                              {onOpenOrder ? (
                                <button type="button" className="underline" onClick={() => onOpenOrder(o.id)}>
                                  {o.order_number}
                                </button>
                              ) : o.order_number}{" "}
                              ({o.status_display})
                            </React.Fragment>
                          ))}
                          {row.duplicate_blocked && " — فتح أمرٍ آخر يطلب سبباً."}
                        </div>
                      )}
                      <div className="mt-2 flex justify-end">
                        <button
                          type="button"
                          onClick={() => applyResult(row, true)}
                          className="rounded-lg border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface)]"
                        >
                          {isSelected ? "مُختارة" : "استقبال على هذه البطاقة"}
                        </button>
                      </div>
                    </div>
                  );
                })}

                {lookup.truncated && (
                  <div className="text-[11px] text-[var(--color-text-muted)]">
                    نتائج كثيرة — عُرضت أحدث {formatNumber(lookup.results.length)} فقط. ضيّق البحث برقم تسلسلي أو فاتورة.
                  </div>
                )}

                {lookup.units_without_card.map((unit) => (
                  <div key={unit.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] p-2.5 text-sm" data-testid="intake-unit-without-card">
                    <span className="text-[var(--color-text)]">
                      وحدة من بضاعتنا بلا بطاقة كفالة: {unit.product_name}
                    </span>
                    <span className="font-mono text-[11px] text-[var(--color-text-muted)]">{unit.serial}</span>
                    {unit.invoice_number && (
                      <span className="text-[11px] text-[var(--color-text-muted)]">
                        بيعت بفاتورة {unit.invoice_number}
                        {unit.sale_date && ` بتاريخ ${formatDateValue(unit.sale_date)}`}
                        {unit.partner && ` — ${unit.partner.name}`}
                      </span>
                    )}
                    <span className="flex-1" />
                    <button
                      type="button"
                      onClick={() => fillFromUnit(unit)}
                      className="rounded-lg border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                    >
                      تعبئة من الوحدة
                    </button>
                  </div>
                ))}

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

                {!lookup.message
                  && lookup.results.length === 0
                  && lookup.units_without_card.length === 0
                  && lookup.sensitive_devices.length === 0 && (
                    <div className="rounded-lg border border-[var(--color-border)] p-2.5 text-sm text-[var(--color-text-muted)]" data-testid="intake-no-match">
                      لا شيء مطابق — أدخل بيانات الجهاز يدوياً (يُفتح الأمر مدفوعاً بلا بطاقة كفالة).
                    </div>
                  )}
              </div>
            )}

            {selected && (
              <div
                className={`mt-2 rounded-lg border p-2.5 text-sm ${INTAKE_VERDICT_TONE_CLASSES[intakeVerdictTone(selected.verdict)]}`}
                data-testid="intake-verdict-banner"
                data-verdict={selected.verdict}
              >
                <div className="font-bold">{intakeVerdictLabel(selected.verdict)}</div>
                <div className="mt-0.5 text-[11px] opacity-80">
                  البطاقة #{formatNumber(selected.card.id)} — {selected.card.device_name || "جهاز"}
                  {selected.card.serial && ` · ${selected.card.serial}`}
                </div>
                {selected.prefill.requires_item_confirm && (
                  <label className="mt-2 flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={pieceConfirmed}
                      onChange={(e) => setPieceConfirmed(e.target.checked)}
                      data-testid="intake-piece-confirm"
                    />
                    <span>
                      {INVOICE_PIECE_CONFIRM_TEXT}
                      <span className="block text-[11px] opacity-80">
                        بدون هذا التأكيد يُفتح الأمر مدفوعاً وتبقى البطاقة مربوطة به.
                      </span>
                    </span>
                  </label>
                )}
                {selected.prefill.requires_repair_confirm && (
                  <label className="mt-2 flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={repairConfirmed}
                      onChange={(e) => setRepairConfirmed(e.target.checked)}
                      data-testid="intake-repair-confirm"
                    />
                    <span>
                      {REPAIR_FAULT_CONFIRM_TEXT}
                      <span className="block text-[11px] opacity-80">
                        بدون هذا التأكيد يُفتح الأمر مدفوعاً وتبقى البطاقة مربوطة به.
                      </span>
                    </span>
                  </label>
                )}
              </div>
            )}

            {referralPending && selected && (
              <ServiceOrderReferralPanel
                cardId={selected.card.id}
                onDone={finishReferral}
                onPaidRepair={() => setPaidReferralCard(selected.card.id)}
              />
            )}
          </section>

          {paidDespiteReferral && (
            <div
              className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200"
              data-testid="intake-referral-paid-banner"
            >
              إصلاح مدفوع بطلب الزبون رغم الإحالة — يُفتح الأمر غير مغطى بالكفالة، ويُسجَّل التحذير وموافقة الزبون في أحداثه.
            </div>
          )}

          {!referralPending && (<>
          {/* ── الزبون والجهاز ─────────────────────────────────────────── */}
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="intake-partner">الزبون من القائمة</label>
              <select
                id="intake-partner"
                className={inputClass}
                value={draft.partner ?? ""}
                onChange={(e) => {
                  markTouched();
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
              <label className={labelClass} htmlFor="intake-product">المنتج</label>
              <select
                id="intake-product"
                className={inputClass}
                value={draft.product ?? ""}
                onChange={(e) => patch("product", e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— بلا منتج (جهاز لم نبعه) —</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{formatProductPrimaryName(p)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="intake-device-serial">الرقم التسلسلي للجهاز</label>
              <input
                id="intake-device-serial"
                className={`${inputClass} font-mono`}
                value={draft.serial || ""}
                onChange={(e) => patch("serial", e.target.value)}
              />
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
                checked={!paidDespiteReferral && Boolean(draft.warranty_covered)}
                disabled={paidDespiteReferral}
                onChange={(e) => patch("warranty_covered", e.target.checked)}
              />
              الإصلاح مغطى بالكفالة — تُضاف قطع الغيار افتراضياً كمصروف كفالة لا كبند مفوتر
            </label>
          </section>
          </>)}

          {err && (
            <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}
        </div>

        <footer className="flex items-center gap-2 border-t border-[var(--color-border)] p-3">
          <span className="text-[11px] text-[var(--color-text-muted)]">
            {referralPending ? "حكم البطاقة إحالة — لا يُفتح أمر" : problems.length > 0 ? problems.join(" · ") : "جاهز للفتح"}
          </span>
          {/* issue #109 §٦: مؤشّر دائم كي لا يضغط المستخدم «حفظ» احتياطاً كل دقيقة — لا يوجد حفظٌ خادميّ فوريّ في هذا المودال أصلاً. */}
          {draftSavedAt && (
            <span className="ktra-status-item text-[11px] text-[var(--color-text-muted)]" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
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
            disabled={busy || referralPending}
            onClick={() => void save()}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} فتح أمر الصيانة
          </button>
        </footer>
      </div>

      {duplicate && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-3"
          role="alertdialog"
          aria-modal="true"
          aria-label="أمر صيانة مفتوح لهذا الجهاز"
          data-testid="intake-duplicate-dialog"
        >
          <div className="w-full max-w-md space-y-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-xl">
            <h3 className="font-bold text-[var(--color-text)]">لهذا الجهاز أمر صيانة مفتوح</h3>
            <p className="text-sm text-[var(--color-text)]">
              الأمر {duplicate.order_number} ({duplicate.status_display}) لم يُسلَّم ولم يُلغَ بعد.
              افتحه بدل أمرٍ ثانٍ، أو اكتب سبب فتح أمرٍ جديد رغم ذلك.
            </p>
            <div>
              <label className={labelClass} htmlFor="intake-duplicate-reason">سبب فتح أمرٍ جديد</label>
              <textarea
                id="intake-duplicate-reason"
                rows={2}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                value={duplicateReason}
                onChange={(e) => setDuplicateReason(e.target.value)}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {onOpenOrder && (
                <button
                  type="button"
                  onClick={() => onOpenOrder(duplicate.id)}
                  className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                >
                  فتح الأمر القائم
                </button>
              )}
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => setDuplicate(null)}
                className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
              >
                رجوع
              </button>
              <button
                type="button"
                disabled={busy || !duplicateReasonValid(duplicateReason)}
                onClick={() => { setDuplicate(null); void save(duplicateReason); }}
                className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                فتح أمر جديد رغم ذلك
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ServiceOrderIntakeModal;
