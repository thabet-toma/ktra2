/**
 * مصدر واحد لمنطق «وين أنا وشو الخطوة الجاية» في رحلة الاستيراد.
 *
 * الجزء الأول (`getImportJourneyGuidance`) يخدم شاشة الشحنة التي تعرف بياناتها
 * كاملةً. الجزء الثاني (`buildImportJourney`) يخدم المرشد العام الظاهر في كل
 * الشاشات، ويبني عليه لا بجانبه: مرحلة الشحن والتخليص والفاتورة تُشتقّ من نفس
 * الدالة كي لا ينحرف المرشدان.
 *
 * ملف صرف بلا React ولا شبكة — لذلك يُختبر وحده (`utils/importJourney.test.ts`).
 */
// امتداد `.ts` صريح: هذا الملف يُشغَّل مباشرةً تحت `node --test` الذي لا يخمّن
// الامتدادات (وVite يقبل الامتداد الصريح بلا مشكلة).
import { formatMoney } from "../../utils/formatNumber.ts";

export type ImportJourneyAction =
  | "save_shipment"
  | "link_deals"
  | "pay_freight"
  | "create_clearance"
  | "enter_clearance_costs"
  | "manage_local_transport"
  | "create_invoice"
  | "view_invoice";

export interface ImportJourneyGuidanceInput {
  shipmentSaved: boolean;
  invoiceEligible: boolean;
  dealsCount: number;
  freightTotalUsd: number;
  /** التكلفة مُثبتة: قيد استحقاق على الوكيل، أو دفع كامل، أو شحن بلا تكلفة */
  freightCostEstablished: boolean;
  clearanceExists: boolean;
  clearanceCostTotal: number;
  convertedInvoiceId: number | null;
  remainingDealsCount: number;
}

export interface ImportJourneyGuidance {
  action: ImportJourneyAction;
  step: number;
  title: string;
  description: string;
  actionLabel: string;
}

interface DealMeasureRow {
  deal?: number;
  deal_ref?: string;
  deal_total_cbm?: number | string;
  deal_total_weight_kg?: number | string;
}

export function getMissingDealMeasureRefs(
  allocations: DealMeasureRow[],
  unit: "cbm" | "kg",
): string[] {
  const numberValue = (value: number | string | undefined) => {
    const parsed = typeof value === "string" ? parseFloat(value) : value ?? 0;
    return Number.isFinite(parsed) ? parsed : 0;
  };
  return allocations
    .filter((row) => numberValue(unit === "kg" ? row.deal_total_weight_kg : row.deal_total_cbm) <= 0)
    .map((row) => row.deal_ref || `#${row.deal}`);
}

export function getImportJourneyGuidance(input: ImportJourneyGuidanceInput): ImportJourneyGuidance {
  if (!input.shipmentSaved) {
    return { action: "save_shipment", step: 1, title: "احفظ بيانات الشحنة", description: "أكمل البيانات الأساسية لتبدأ رحلة الاستيراد.", actionLabel: "حفظ الشحنة" };
  }
  if (!input.invoiceEligible) {
    return { action: "manage_local_transport", step: 5, title: "أكمل بيانات النقل المحلي", description: "هذه الشحنة للنقل فقط ولا تحتاج إنشاء فاتورة دولية.", actionLabel: "فتح النقل المحلي" };
  }
  if (input.dealsCount === 0) {
    return { action: "link_deals", step: 2, title: "ضمّ الصفقات إلى الشحنة", description: "اختر الصفقات التي وصلت ضمن هذه الشحنة.", actionLabel: "فتح الصفقات" };
  }
  if (!input.freightCostEstablished) {
    return { action: "pay_freight", step: 3, title: "أثبت استحقاق الشحن الدولي", description: "أدخل سعر الصرف ورحّل الاستحقاق على وكيل الشحن — الدفع إجراء مستقل لاحقاً.", actionLabel: "إثبات استحقاق الشحن" };
  }
  if (!input.clearanceExists) {
    return { action: "create_clearance", step: 4, title: "أنشئ ملف التخليص", description: "سجّل المخلّص ورقم البيان وتكاليف التخليص.", actionLabel: "إنشاء التخليص" };
  }
  if (input.clearanceCostTotal <= 0) {
    return { action: "enter_clearance_costs", step: 4, title: "أدخل تكلفة التخليص", description: "يمكنك إدخال إجمالي واحد أو تفصيل الرسوم إلى بنود.", actionLabel: "إدخال التكلفة" };
  }
  if (input.convertedInvoiceId && input.remainingDealsCount === 0) {
    return { action: "view_invoice", step: 6, title: "رحلة الاستيراد مكتملة", description: `تم إنشاء الفاتورة الدولية #${input.convertedInvoiceId}.`, actionLabel: "فتح الفاتورة" };
  }
  return {
    action: "create_invoice",
    step: 6,
    title: input.convertedInvoiceId ? "توجد صفقات متبقية للتحويل" : "جاهزة لإنشاء الفاتورة الدولية",
    description: input.convertedInvoiceId
      ? `تم تحويل جزء من الشحنة وبقيت ${input.remainingDealsCount} صفقة. يمكنك إنشاء فواتيرها الآن أو لاحقاً.`
      : "لا يشترط دفع التخليص أو النقل المحلي؛ يمكن تسويتهما لاحقاً.",
    actionLabel: input.convertedInvoiceId ? `إنشاء الفواتير المتبقية (${input.remainingDealsCount})` : "إنشاء الفاتورة الدولية",
  };
}

/* ══════════════════════════════════════════════════════════════════════════
   المرشد العام — الرحلة كاملةً من عرض السعر حتى فاتورة الشراء الدولية
   ══════════════════════════════════════════════════════════════════════════ */

export type ImportStageKey =
  | "offer"
  | "deal"
  | "deal_payments"
  | "shipment"
  | "freight"
  | "clearance"
  | "local"
  | "invoice";

export interface ImportStageDef {
  key: ImportStageKey;
  /** رقم الخطوة كما يراها المستخدم (١..٨). */
  order: number;
  label: string;
  /** ماذا يحدث في هذه المرحلة — جملة واحدة تشرح الغاية لا الآلية. */
  purpose: string;
  /** المسار الافتراضي للمرحلة حين لا توجد رحلة محدَّدة بعد. */
  fallbackRoute: string;
  /** خطوة اختيارية لا تعطّل الوصول للفاتورة. */
  optional?: boolean;
}

export const IMPORT_JOURNEY_STAGES: readonly ImportStageDef[] = [
  { key: "offer", order: 1, label: "عرض سعر الاستيراد", purpose: "اطلب سعراً من المورد الدولي وقرّر ملاءمته قبل الالتزام.", fallbackRoute: "/import-offers" },
  { key: "deal", order: 2, label: "الصفقة", purpose: "العرض المقبول يصير صفقة بأصنافها وقيمتها — وهي المستند الذي يتتبّع كل ما بعده.", fallbackRoute: "/deals" },
  { key: "deal_payments", order: 3, label: "دفعات الصفقة", purpose: "ادفع للمورد على دفعات (عربون ثم رصيد) — كل دفعة مستقلة عن مرحلة الشحن.", fallbackRoute: "/deals" },
  { key: "shipment", order: 4, label: "الشحنة الدولية", purpose: "اضمم الصفقات الجاهزة إلى شحنة واحدة عند الوكيل.", fallbackRoute: "/import-flow" },
  { key: "freight", order: 5, label: "الشحن الدولي", purpose: "أثبت استحقاق الشحن على الوكيل بسعر صرفه — والدفع له خطوة مستقلة متى شئت.", fallbackRoute: "/import-flow" },
  { key: "clearance", order: 6, label: "التخليص الجمركي", purpose: "سجّل المخلّص ورقم البيان وتكاليف التخليص.", fallbackRoute: "/clearance" },
  { key: "local", order: 7, label: "النقل المحلي", purpose: "نقل البضاعة من الميناء إلى المستودع — اختياري، ويُدفع للناقل باستقلال عن استحقاقه.", fallbackRoute: "/local-shipping", optional: true },
  { key: "invoice", order: 8, label: "فاتورة الشراء الدولية", purpose: "الإفراج: تتحول الشحنة إلى فاتورة، فتدخل البضاعة المخزون بتكلفتها الحقيقية.", fallbackRoute: "/international-invoices" },
] as const;

export interface ImportJourneyDealFacts {
  id: number;
  ref: string;
  title?: string | null;
  partner_name?: string | null;
  currency_code?: string | null;
  stage?: string | null;
  total: string;
  paid: string;
  remaining: string;
  payments_count: number;
  pending_payments_count: number;
  shipment_id: number | null;
  shipment_label?: string | null;
}

export interface ImportJourneyShipmentFacts {
  id: number;
  number: string;
  name?: string | null;
  shipment_type: string;
  deals_count: number;
  freight_total_usd: string;
  freight_paid_usd: string;
  freight_is_posted: boolean;
  clearance_id: number | null;
  clearance_cost: string;
  local_count: number;
  local_remaining: string;
  invoices_count: number;
  invoice_id: number | null;
  remaining_deals: number;
}

export interface ImportJourneySummaryFacts {
  offers: { awaiting_decision: number; accepted_not_converted: number };
  deals: { rows: ImportJourneyDealFacts[]; without_shipment: number };
  shipments: ImportJourneyShipmentFacts[];
}

export type ImportStepState = "done" | "current" | "todo" | "optional";

export interface ImportJourneyStep extends ImportStageDef {
  state: ImportStepState;
  /** إرشاد بالأرقام الفعلية لهذه الرحلة — لا نصّ عام. */
  detail: string;
  /** نص الزر الإرشادي («أضف عرض السعر هنا»، «سجّل الدفعة ٢»…). */
  ctaLabel: string;
  /** وجهة الزر — دائماً المكان الذي يُنفَّذ فيه الإجراء فعلاً. */
  route: string;
}

export interface ImportJourneyFocus {
  kind: "shipment" | "deal" | "empty";
  shipmentId: number | null;
  dealId: number | null;
  label: string;
}

export interface ImportJourneyView {
  focus: ImportJourneyFocus;
  steps: ImportJourneyStep[];
  /** الخطوة التي يقف عندها المستخدم الآن (أول غير منجزة وغير اختيارية). */
  current: ImportJourneyStep;
  /** الخيارات المتاحة للتبديل بين الرحلات النشطة. */
  options: ImportJourneyFocus[];
}

const num = (value: string | number | null | undefined): number => {
  const parsed = typeof value === "string" ? parseFloat(value) : value ?? 0;
  return Number.isFinite(parsed) ? parsed : 0;
};

/** G1: كل عرض رقمي يمرّ عبر المُنسّق الموحّد — لا تنسيق محلي في هذا الملف. */
const money = (value: string | number | null | undefined): string =>
  formatMoney(num(value));

const stage = (key: ImportStageKey): ImportStageDef =>
  IMPORT_JOURNEY_STAGES.find((s) => s.key === key) as ImportStageDef;

/** الإجراء المقترح لمرحلة الشحنة ← مفتاح المرحلة في المرشد العام. */
const ACTION_STAGE: Record<ImportJourneyAction, ImportStageKey> = {
  save_shipment: "shipment",
  // «ضمّ الصفقات» إجراء يقع داخل الشحنة، لا في شاشة الصفقات.
  link_deals: "shipment",
  pay_freight: "freight",
  create_clearance: "clearance",
  enter_clearance_costs: "clearance",
  manage_local_transport: "local",
  create_invoice: "invoice",
  view_invoice: "invoice",
};

/**
 * أين يقف المستخدم الآن حسب المسار المفتوح — يجعل المرشد يقول «أنت هنا» بدل أن
 * يترك الربط بين الشاشة والمرحلة على ذهن المستخدم.
 */
export function matchImportStage(pathname: string, search = ""): ImportStageKey | null {
  const path = String(pathname || "");
  const tab = new URLSearchParams(search || "").get("tab") || "";
  if (/^\/import-offers/.test(path)) return "offer";
  if (/^\/deals/.test(path)) return path.includes("/new") ? "deal" : "deal_payments";
  if (/^\/import-flow/.test(path)) {
    if (tab === "payments") return "freight";
    if (tab === "clearance") return "clearance";
    if (tab === "local") return "local";
    return "shipment";
  }
  if (/^\/clearance/.test(path)) return "clearance";
  if (/^\/local-shipping/.test(path)) return "local";
  if (/^\/(international-invoices|purchase-invoices)/.test(path)) return "invoice";
  if (/^\/shipments/.test(path)) return "shipment";
  return null;
}

function focusOptions(summary: ImportJourneySummaryFacts): ImportJourneyFocus[] {
  const options: ImportJourneyFocus[] = summary.shipments.map((s) => ({
    kind: "shipment" as const,
    shipmentId: s.id,
    dealId: null,
    label: `شحنة ${s.name || s.number}`,
  }));
  summary.deals.rows
    .filter((d) => d.shipment_id === null)
    .forEach((d) => options.push({
      kind: "deal", shipmentId: null, dealId: d.id,
      label: `صفقة ${d.ref}${d.title ? ` — ${d.title}` : ""}`,
    }));
  return options;
}

function dealSteps(deal: ImportJourneyDealFacts | null, offersWaiting: number): ImportJourneyStep[] {
  const remaining = deal ? num(deal.remaining) : 0;
  const currency = deal?.currency_code || "USD";
  const offerDone = Boolean(deal);
  const offer: ImportJourneyStep = {
    ...stage("offer"),
    state: offerDone ? "done" : "current",
    detail: offerDone
      ? "الصفقة قائمة — العرض أدّى دوره."
      : offersWaiting > 0
        ? `${offersWaiting} عرض استيراد بانتظار قرارك (ملائم / غير ملائم).`
        : "لا يوجد عرض استيراد مفتوح — ابدأ بطلب سعر من المورد.",
    ctaLabel: offerDone ? "فتح العروض" : offersWaiting > 0 ? `راجع العروض (${offersWaiting})` : "أضف عرض سعر هنا",
    route: "/import-offers",
  };
  const dealStep: ImportJourneyStep = {
    ...stage("deal"),
    state: deal ? "done" : offerDone ? "current" : "todo",
    detail: deal
      ? `${deal.ref}${deal.partner_name ? ` · ${deal.partner_name}` : ""} · قيمتها ${money(deal.total)} ${currency}.`
      : "حوّل العرض المقبول إلى صفقة، أو أنشئ صفقة مباشرةً.",
    ctaLabel: deal ? "فتح الصفقة" : "أنشئ صفقة",
    route: deal ? `/deals/${deal.id}` : "/deals/new",
  };
  const payments: ImportJourneyStep = {
    ...stage("deal_payments"),
    state: !deal ? "todo" : remaining <= 0.01 ? "done" : "current",
    detail: !deal
      ? "تُسجَّل بعد إنشاء الصفقة."
      : deal.payments_count === 0
        ? `لا توجد دفعات بعد — المستحق للمورد ${money(deal.total)} ${currency}.`
        : `${deal.payments_count} دفعة مسجّلة` +
          (deal.pending_payments_count > 0 ? ` (${deal.pending_payments_count} بانتظار تأكيد المورد)` : "") +
          ` · مدفوع ${money(deal.paid)} من ${money(deal.total)} ${currency}` +
          (remaining > 0.01 ? ` · متبقٍ ${money(deal.remaining)}` : " · مسدَّدة بالكامل"),
    ctaLabel: !deal
      ? "فتح الصفقات"
      : deal.payments_count === 0
        ? "سجّل الدفعة الأولى"
        : remaining > 0.01
          ? `سجّل الدفعة ${deal.payments_count + 1}`
          : "عرض الدفعات",
    route: deal ? `/deals/${deal.id}?tab=payments` : "/deals",
  };
  return [offer, dealStep, payments];
}

/**
 * يبني الرحلة كاملةً لبؤرة واحدة. مرحلة الشحن وما بعدها تُشتقّ من
 * `getImportJourneyGuidance` نفسها التي تستعملها شاشة الشحنة.
 */
export function buildImportJourney(
  summary: ImportJourneySummaryFacts,
  requested?: { shipmentId?: number | null; dealId?: number | null },
): ImportJourneyView {
  const options = focusOptions(summary);
  const shipment =
    summary.shipments.find((s) => s.id === requested?.shipmentId) ||
    (requested?.dealId
      ? summary.shipments.find(
          (s) => s.id === summary.deals.rows.find((d) => d.id === requested.dealId)?.shipment_id,
        )
      : undefined) ||
    (requested?.shipmentId || requested?.dealId ? undefined : summary.shipments[0]);

  const deal =
    summary.deals.rows.find((d) => d.id === requested?.dealId) ||
    (shipment ? summary.deals.rows.find((d) => d.shipment_id === shipment.id) : undefined) ||
    (requested?.dealId ? undefined : summary.deals.rows.find((d) => d.shipment_id === null)) ||
    null;

  const focus: ImportJourneyFocus = shipment
    ? { kind: "shipment", shipmentId: shipment.id, dealId: deal?.id ?? null, label: `شحنة ${shipment.name || shipment.number}` }
    : deal
      ? { kind: "deal", shipmentId: null, dealId: deal.id, label: `صفقة ${deal.ref}${deal.title ? ` — ${deal.title}` : ""}` }
      : { kind: "empty", shipmentId: null, dealId: null, label: "لا توجد رحلة نشطة" };

  const steps = dealSteps(deal, summary.offers.awaiting_decision);

  if (!shipment) {
    const joinRoute = deal
      ? `/import-flow/new?tab=deals&join_deal=${deal.id}`
      : "/import-flow/new?tab=deals";
    steps.push(
      {
        ...stage("shipment"),
        state: deal ? "current" : "todo",
        detail: deal
          ? "الصفقة ليست ضمن شحنة بعد — ابدأ الشحن الدولي بضمّها إلى شحنة."
          : "تبدأ بعد وجود صفقة جاهزة للشحن.",
        ctaLabel: "ابدأ الشحن الدولي",
        route: joinRoute,
      },
      ...(["freight", "clearance", "local", "invoice"] as ImportStageKey[]).map((key) => ({
        ...stage(key),
        state: (stage(key).optional ? "optional" : "todo") as ImportStepState,
        detail: "تُفتح بعد ضمّ الصفقة إلى شحنة.",
        ctaLabel: "غير متاحة بعد",
        route: joinRoute,
      })),
    );
    return { focus, steps, current: pickCurrent(steps), options };
  }

  const freightTotal = num(shipment.freight_total_usd);
  const freightPaid = num(shipment.freight_paid_usd);
  const freightCostEstablished =
    shipment.freight_is_posted || freightTotal <= 0 || freightPaid >= freightTotal - 0.02;
  const clearanceCost = num(shipment.clearance_cost);
  const guidance = getImportJourneyGuidance({
    shipmentSaved: true,
    invoiceEligible: shipment.shipment_type !== "transport",
    dealsCount: shipment.deals_count,
    freightTotalUsd: freightTotal,
    freightCostEstablished,
    clearanceExists: Boolean(shipment.clearance_id),
    clearanceCostTotal: clearanceCost,
    convertedInvoiceId: shipment.invoice_id,
    remainingDealsCount: shipment.remaining_deals,
  });
  const guidedStage = ACTION_STAGE[guidance.action];
  const base = `/import-flow/${shipment.id}`;

  steps.push({
    ...stage("shipment"),
    state: shipment.deals_count > 0 ? "done" : "current",
    detail: shipment.deals_count > 0
      ? `شحنة ${shipment.name || shipment.number} تضمّ ${shipment.deals_count} صفقة.`
      : "الشحنة محفوظة بلا صفقات — اضمم إليها الصفقات التي وصلت ضمنها.",
    ctaLabel: shipment.deals_count > 0 ? "فتح الشحنة" : "ضمّ الصفقات",
    route: `${base}?tab=deals`,
  });

  steps.push({
    ...stage("freight"),
    state: freightCostEstablished ? "done" : "current",
    detail: freightTotal <= 0
      ? "لا توجد تكلفة شحن على هذه الشحنة — لا استحقاق ولا دفعة."
      : shipment.freight_is_posted
        ? `الاستحقاق مُثبَّت · مدفوع للوكيل $${money(freightPaid)} من $${money(freightTotal)}` +
          (freightPaid < freightTotal - 0.02 ? " — الدفع مستقل ولا يعطّل الفاتورة." : ".")
        : `تكلفة الشحن $${money(freightTotal)} — أثبت الاستحقاق بسعر الصرف أولاً، والدفع لاحقاً.`,
    ctaLabel: freightTotal <= 0
      ? "فتح الدفعات"
      : shipment.freight_is_posted
        ? (freightPaid < freightTotal - 0.02 ? "ادفع للوكيل" : "عرض دفعات الشحن")
        : "أثبت استحقاق الشحن",
    route: `${base}?tab=payments`,
  });

  steps.push({
    ...stage("clearance"),
    state: shipment.clearance_id && clearanceCost > 0 ? "done" : "current",
    detail: !shipment.clearance_id
      ? "لا يوجد ملف تخليص — أنشئه وسجّل المخلّص ورقم البيان."
      : clearanceCost > 0
        ? `تكلفة التخليص ${money(clearanceCost)} ₪ مسجّلة.`
        : "ملف التخليص موجود وينقصه إدخال التكلفة (إجمالي واحد يكفي).",
    ctaLabel: !shipment.clearance_id ? "أنشئ ملف التخليص" : clearanceCost > 0 ? "فتح التخليص" : "أدخل تكلفة التخليص",
    route: `${base}?tab=clearance`,
  });

  steps.push({
    ...stage("local"),
    state: shipment.local_count > 0 ? "done" : "optional",
    detail: shipment.local_count === 0
      ? "لا يوجد نقل محلي — أضِفه إن نقلت البضاعة بناقل داخلي."
      : `${shipment.local_count} سجل نقل` +
        (num(shipment.local_remaining) > 0.01
          ? ` · متبقٍ للناقل ${money(shipment.local_remaining)} ₪ (الدفع مستقل عن الفاتورة).`
          : " · مسدَّد بالكامل."),
    ctaLabel: shipment.local_count === 0 ? "أضف نقلاً محلياً" : "إدارة النقل والدفعات",
    route: `${base}?tab=local`,
  });

  const invoiceDone = shipment.invoices_count > 0 && shipment.remaining_deals === 0;
  steps.push({
    ...stage("invoice"),
    state: invoiceDone ? "done" : "current",
    detail: invoiceDone
      ? `اكتملت الرحلة — ${shipment.invoices_count} فاتورة دولية.`
      : guidance.description,
    ctaLabel: guidance.action === "create_invoice" || guidance.action === "view_invoice"
      ? guidance.actionLabel
      : "بانتظار الخطوات السابقة",
    route: invoiceDone && shipment.invoice_id
      ? `/purchase-invoices/${shipment.invoice_id}`
      : `/international-invoices?import_shipment=${shipment.id}`,
  });

  // الخطوة الحالية هي التي يرشد إليها محرّك الشحنة نفسه، فلا ينحرف المرشد العام
  // عن المرشد داخل شاشة الشحنة. أما دفعات الصفقة فبُعد مالي مستقل عن المراحل
  // (قرار معماري مثبت): تبقى ظاهرة كنقص قائم ولا تُعلَن «منجزة» لمجرد تقدّم الشحن.
  const guidedIndex = steps.findIndex((s) => s.key === guidedStage);
  const resolved = steps.map((step, i) => {
    if (i < DEAL_PHASE_LENGTH) {
      return step.state === "current" && guidedIndex > i
        ? { ...step, state: "todo" as ImportStepState }
        : step;
    }
    // الاختيارية لا تُعلَن منجزة لمجرد تجاوزها، والمنجزة لا تُعاد «حالية».
    if (step.state === "done" || step.state === "optional") return step;
    if (i < guidedIndex) return { ...step, state: "done" as ImportStepState };
    if (i === guidedIndex) return { ...step, state: "current" as ImportStepState };
    if (step.state === "current") return { ...step, state: (step.optional ? "optional" : "todo") as ImportStepState };
    return step;
  });
  return { focus, steps: resolved, current: resolved[guidedIndex] || pickCurrent(resolved), options };
}

/** عدد خطوات ما قبل الشحنة (عرض السعر، الصفقة، دفعاتها). */
const DEAL_PHASE_LENGTH = 3;

function pickCurrent(steps: ImportJourneyStep[]): ImportJourneyStep {
  return steps.find((s) => s.state === "current") || steps.find((s) => s.state === "todo") || steps[0];
}
