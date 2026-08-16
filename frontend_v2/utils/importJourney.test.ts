import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildImportJourney,
  matchImportStage,
  type ImportJourneyDealFacts,
  type ImportJourneyShipmentFacts,
  type ImportJourneySummaryFacts,
} from "../components/import-flow/importJourneyGuidance.ts";

const deal = (over: Partial<ImportJourneyDealFacts> = {}): ImportJourneyDealFacts => ({
  id: 7,
  ref: "D-7",
  title: "إطارات",
  partner_name: "المصنع",
  currency_code: "USD",
  stage: "sw_mfg_start",
  total: "1000",
  paid: "400",
  remaining: "600",
  payments_count: 2,
  pending_payments_count: 1,
  shipment_id: null,
  shipment_label: null,
  ...over,
});

const shipment = (over: Partial<ImportJourneyShipmentFacts> = {}): ImportJourneyShipmentFacts => ({
  id: 5,
  number: "SH-5",
  name: "شحنة الصيف",
  shipment_type: "invoice",
  deals_count: 1,
  freight_total_usd: "2000",
  freight_paid_usd: "0",
  freight_is_posted: false,
  clearance_id: null,
  clearance_cost: "0.00",
  local_count: 0,
  local_remaining: "0.00",
  invoices_count: 0,
  invoice_id: null,
  remaining_deals: 1,
  ...over,
});

const summary = (over: Partial<ImportJourneySummaryFacts> = {}): ImportJourneySummaryFacts => ({
  offers: { awaiting_decision: 0, accepted_not_converted: 0 },
  deals: { rows: [], without_shipment: 0 },
  shipments: [],
  ...over,
});

const stepOf = (view: ReturnType<typeof buildImportJourney>, key: string) =>
  view.steps.find((s) => s.key === key)!;

test("أنت هنا: كل مسار في المنصة يُترجَم إلى مرحلة استيراد", () => {
  assert.equal(matchImportStage("/import-offers"), "offer");
  assert.equal(matchImportStage("/deals/new"), "deal");
  assert.equal(matchImportStage("/deals/12"), "deal_payments");
  assert.equal(matchImportStage("/import-flow/5", "?tab=deals"), "shipment");
  assert.equal(matchImportStage("/import-flow/5", "?tab=payments"), "freight");
  assert.equal(matchImportStage("/import-flow/5", "?tab=clearance"), "clearance");
  assert.equal(matchImportStage("/import-flow/5", "?tab=local"), "local");
  assert.equal(matchImportStage("/international-invoices"), "invoice");
  assert.equal(matchImportStage("/items"), null);
});

test("بلا أي شيء: الرحلة تبدأ من عرض السعر بزر إرشادي صريح", () => {
  const view = buildImportJourney(summary());
  assert.equal(view.focus.kind, "empty");
  assert.equal(view.current.key, "offer");
  assert.equal(view.current.ctaLabel, "أضف عرض سعر هنا");
  assert.equal(view.steps.length, 8);
});

test("عروض بانتظار قرار: الإرشاد يذكر عددها ويقود إليها", () => {
  const view = buildImportJourney(summary({ offers: { awaiting_decision: 3, accepted_not_converted: 1 } }));
  assert.match(view.current.detail, /3 عرض/);
  assert.equal(view.current.route, "/import-offers");
});

test("صفقة بلا شحنة: الإرشاد يعدّ الدفعات ويسمّي رقم الدفعة التالية", () => {
  const view = buildImportJourney(summary({ deals: { rows: [deal()], without_shipment: 1 } }));
  const payments = stepOf(view, "deal_payments");
  assert.equal(payments.state, "current");
  assert.match(payments.detail, /2 دفعة مسجّلة/);
  assert.match(payments.detail, /بانتظار تأكيد المورد/);
  assert.equal(payments.ctaLabel, "سجّل الدفعة 3");
  assert.equal(payments.route, "/deals/7?tab=payments");
});

test("صفقة بلا دفعات: الإرشاد يطلب الدفعة الأولى بقيمة المستحق", () => {
  const rows = [deal({ payments_count: 0, pending_payments_count: 0, paid: "0", remaining: "1000" })];
  const payments = stepOf(buildImportJourney(summary({ deals: { rows, without_shipment: 1 } })), "deal_payments");
  assert.equal(payments.ctaLabel, "سجّل الدفعة الأولى");
  assert.match(payments.detail, /1,000/);
});

test("صفقة مسدَّدة بلا شحنة: الخطوة الحالية هي بدء الشحن الدولي بضمّها", () => {
  const rows = [deal({ paid: "1000", remaining: "0" })];
  const view = buildImportJourney(summary({ deals: { rows, without_shipment: 1 } }));
  assert.equal(view.current.key, "shipment");
  assert.equal(view.current.route, "/import-flow/new?tab=deals&join_deal=7");
});

test("شحنة بلا صفقات: الخطوة الحالية ضمّ الصفقات داخل الشحنة", () => {
  const view = buildImportJourney(summary({ shipments: [shipment({ deals_count: 0, remaining_deals: 0 })] }));
  assert.equal(view.current.key, "shipment");
  assert.equal(view.current.ctaLabel, "ضمّ الصفقات");
  assert.equal(view.current.route, "/import-flow/5?tab=deals");
});

test("الشحن الدولي: قبل الاستحقاق يوجّه لإثباته لا لدفعه", () => {
  const view = buildImportJourney(summary({ shipments: [shipment()] }));
  const freight = stepOf(view, "freight");
  assert.equal(view.current.key, "freight");
  assert.equal(freight.ctaLabel, "أثبت استحقاق الشحن");
  assert.equal(freight.route, "/import-flow/5?tab=payments");
});

test("بعد الاستحقاق: الدفع خطوة مستقلة ولا تعطّل التقدّم للتخليص", () => {
  const view = buildImportJourney(summary({ shipments: [shipment({ freight_is_posted: true })] }));
  assert.equal(stepOf(view, "freight").state, "done");
  assert.match(stepOf(view, "freight").detail, /الدفع مستقل/);
  assert.equal(view.current.key, "clearance");
  assert.equal(view.current.ctaLabel, "أنشئ ملف التخليص");
});

test("التخليص بلا تكلفة: الإرشاد يطلب التكلفة لا ملفاً جديداً", () => {
  const view = buildImportJourney(summary({
    shipments: [shipment({ freight_is_posted: true, clearance_id: 3, clearance_cost: "0.00" })],
  }));
  assert.equal(view.current.key, "clearance");
  assert.equal(view.current.ctaLabel, "أدخل تكلفة التخليص");
});

test("النقل المحلي يبقى اختيارياً ولا يصير الخطوة الحالية", () => {
  const view = buildImportJourney(summary({
    shipments: [shipment({ freight_is_posted: true, clearance_id: 3, clearance_cost: "500" })],
  }));
  assert.equal(stepOf(view, "local").state, "optional");
  assert.equal(view.current.key, "invoice");
  assert.match(view.current.detail, /لا يشترط/);
});

test("نقص دفعات الصفقة يبقى ظاهراً ولو تقدّمت الشحنة — ولا يُعلَن منجزاً", () => {
  const rows = [deal({ shipment_id: 5, shipment_label: "شحنة الصيف" })];
  const view = buildImportJourney(summary({
    deals: { rows, without_shipment: 0 },
    shipments: [shipment({ freight_is_posted: true, clearance_id: 3, clearance_cost: "500" })],
  }));
  const payments = stepOf(view, "deal_payments");
  assert.equal(payments.state, "todo");
  assert.match(payments.detail, /متبقٍ 600/);
  assert.equal(view.current.key, "invoice");
});

test("رحلة مكتملة: الخطوة الأخيرة منجزة وتفتح الفاتورة", () => {
  const view = buildImportJourney(summary({
    shipments: [shipment({
      freight_is_posted: true, clearance_id: 3, clearance_cost: "500",
      invoices_count: 1, invoice_id: 88, remaining_deals: 0,
    })],
  }));
  const invoice = stepOf(view, "invoice");
  assert.equal(invoice.state, "done");
  assert.equal(invoice.route, "/purchase-invoices/88");
});

/* ══════════════════════════════════════════════════════════════════════════
   شارة ملف الاستيراد — وحدة مرخّصة، فمفتاحها قد يغيب بالكامل
   ══════════════════════════════════════════════════════════════════════════ */

/** ما يرسله الخادم لصفقةٍ فُتح ملفها: بنودها وبنود شحنتها بمراحلها. */
const FILE_PROGRESS = {
  offer: { done: 0, total: 2 },
  deal: { done: 1, total: 2 },
  shipment: { done: 2, total: 4 },
  clearance: { done: 0, total: 2 },
} as const;

const withShipmentSummary = (over: Partial<ImportJourneyDealFacts> = {}) =>
  summary({
    deals: { rows: [deal({ shipment_id: 5, ...over })], without_shipment: 0 },
    shipments: [shipment({ freight_is_posted: true })],
  });

test("ملف مسجَّل: أرقام الخادم تُعلَّق على مراحلها كما هي، ولا رقم لمرحلة بلا بنود", () => {
  const view = buildImportJourney(withShipmentSummary({ file_progress: { ...FILE_PROGRESS } }));

  assert.equal(view.file.state, "tracked");
  assert.equal(view.file.route, "/deals/7?tab=import_file");
  assert.deepEqual(stepOf(view, "shipment").fileProgress, { done: 2, total: 4 });
  assert.deepEqual(stepOf(view, "clearance").fileProgress, { done: 0, total: 2 });
  // مرحلة بلا بنود في الملف لا تحمل شارة — الصفر هنا كذبة لا معلومة
  assert.equal(stepOf(view, "freight").fileProgress, undefined);
  assert.equal(stepOf(view, "local").fileProgress, undefined);
});

test("ملف لم يُفتح بعد ({}): دعوةٌ صريحة لا شارة صامتة ولا ٠/٠", () => {
  const view = buildImportJourney(withShipmentSummary({ file_progress: {} }));

  assert.equal(view.file.state, "unopened");
  assert.equal(view.file.route, "/deals/7?tab=import_file");
  assert.equal(view.steps.some((s) => s.fileProgress !== undefined), false);
});

test("بلا ترخيص (المفتاح غائب): الخطوات مطابقة حرفياً لما كانت عليه", () => {
  const licensed = buildImportJourney(withShipmentSummary({ file_progress: { ...FILE_PROGRESS } }));
  const unlicensed = buildImportJourney(withShipmentSummary());

  assert.equal(unlicensed.file.state, "absent");
  // إسقاط الشارة وحدها يُعيد الخطوة كما هي — فالإضافة إضافةٌ لا تعديل
  assert.deepEqual(
    unlicensed.steps,
    licensed.steps.map(({ fileProgress: _ignored, ...step }) => step),
  );
});

test("شحنة بلا صفقة في البؤرة: الشارة من صفّ الشحنة وبلا وجهة تُفتح", () => {
  const view = buildImportJourney(summary({
    shipments: [shipment({ file_progress: { shipment: { done: 1, total: 4 } } })],
  }));

  assert.equal(view.file.state, "tracked");
  assert.equal(view.file.route, null);
  assert.deepEqual(stepOf(view, "shipment").fileProgress, { done: 1, total: 4 });
});

test("التبديل بين الرحلات: كل شحنة وكل صفقة بلا شحنة خيارٌ مستقل", () => {
  const view = buildImportJourney(summary({
    deals: { rows: [deal(), deal({ id: 9, ref: "D-9", shipment_id: 5 })], without_shipment: 1 },
    shipments: [shipment()],
  }));
  assert.deepEqual(view.options.map((o) => o.kind), ["shipment", "deal"]);
  const picked = buildImportJourney(
    summary({ deals: { rows: [deal()], without_shipment: 1 }, shipments: [shipment()] }),
    { dealId: 7 },
  );
  assert.equal(picked.focus.kind, "deal");
  assert.equal(picked.focus.dealId, 7);
});
