import assert from "node:assert/strict";
import test from "node:test";

import {
  entityPathForReference,
  isSafeInternalPath,
  platformNoteTarget,
  productGroupPath,
  referenceTypeLabel,
  statementMovementTone,
  statementToneRowClass,
} from "./entityLinks.ts";

/* ── A1 (THA-195): القفزة الثالثة — من القيد إلى مستنده المصدر ── */

test("القيد يقود إلى فاتورته وسنده — المسارات التي تقرأ المعرّف فعلاً", () => {
  assert.equal(entityPathForReference("SALES_INVOICE", 12), "/sales/invoices/12");
  assert.equal(entityPathForReference("SALES_DELIVERY_COGS", 12), "/sales/invoices/12");
  assert.equal(entityPathForReference("PURCHASE_INVOICE", 7), "/purchase-invoices/7");
  // الشاشتان تقرآن ?payment_id (SupplierPaymentsPage / SalesCustomerPaymentsPage)
  assert.equal(entityPathForReference("SUPPLIER_PAYMENT", 5), "/supplier-payments?payment_id=5");
  assert.equal(
    entityPathForReference("CUSTOMER_PAYMENT", 5),
    "/sales/customer-payments?payment_id=5",
  );
});

test("مستند قيد العكس هو القيد الأصلي — reference_id رقمه", () => {
  assert.equal(entityPathForReference("JOURNAL_REVERSAL", 44), "/accounting/journals/44");
});

/* ── A3 (THA-188): قيد التسوية يُعرَّف نفسه ── */

test("قيد التسوية له تسميته العربية، ولا يُخلط بالقيد اليدوي العام", () => {
  assert.equal(referenceTypeLabel("ADJUSTMENT"), "قيد تسوية");
  assert.equal(referenceTypeLabel("MANUAL"), "قيد يومية");
});

test("LOGISTICS_PAYMENT بلا مسار عمداً: reference_id رقم الدفعة لا رقم الصفقة", () => {
  // ربطه بـ/deals/<id> يفتح صفقة أخرى بالكامل — الصفقة تُفتح من deal_ref_number.
  assert.equal(entityPathForReference("LOGISTICS_PAYMENT", 92), null);
});

test("المرجع بلا معرّف لا يُنتج مساراً", () => {
  assert.equal(entityPathForReference("SALES_INVOICE", null), null);
  assert.equal(entityPathForReference(null, 3), null);
});

test("سند القبض والصرف نبرتهما «دفعة» (أخضر)", () => {
  assert.equal(statementMovementTone("CUSTOMER_PAYMENT"), "payment");
  assert.equal(statementMovementTone("SUPPLIER_PAYMENT"), "payment");
  assert.match(statementToneRowClass("CUSTOMER_PAYMENT"), /emerald/);
});

test("فواتير البيع والشراء نبرتها «فاتورة» (أحمر)", () => {
  assert.equal(statementMovementTone("SALES_INVOICE"), "invoice");
  assert.equal(statementMovementTone("PURCHASE_INVOICE"), "invoice");
  assert.match(statementToneRowClass("SALES_INVOICE"), /red/);
});

test("الدفعة تسبق الفاتورة في المطابقة (CLEARANCE_PAYMENT ليس مستحقاً)", () => {
  assert.equal(statementMovementTone("CLEARANCE_PAYMENT"), "payment");
  assert.equal(statementMovementTone("LOCAL_SHIPMENT_PAYMENT"), "payment");
  assert.equal(statementMovementTone("LOGISTICS_CLEARANCE"), "invoice");
});

test("ما عدا ذلك محايد بلا لون", () => {
  assert.equal(statementMovementTone("PARTNER_OPENING"), "neutral");
  assert.equal(statementMovementTone(null), "neutral");
  assert.equal(statementToneRowClass("PARTNER_OPENING"), "");
});

test("هدف الملاحظة العامة يحفظ الصفحة ومعامل السجل كرابط داخلي ثابت", () => {
  assert.deepEqual(
    platformNoteTarget(
      "/import-price-offers",
      "?doc=quote-12",
      "عرض استيراد SQ-12",
    ),
    {
      target_type: "page",
      target_id: "/import-price-offers?doc=quote-12",
      target_label: "عرض استيراد SQ-12",
      target_path: "/import-price-offers?doc=quote-12",
    },
  );
});

test("روابط التذكيرات تقبل المسار الداخلي وترفض الخارجي والمزدوج", () => {
  assert.equal(isSafeInternalPath("/sales/invoices/12"), true);
  assert.equal(isSafeInternalPath("https://example.com/phish"), false);
  assert.equal(isSafeInternalPath("//example.com/phish"), false);
  assert.equal(isSafeInternalPath("/\\example.com/phish"), false);
});

/**
 * رابط الكرت المجمّع: التصنيف يسمو على تعداد المعرّفات. تصنيفٌ فيه ~1500 منتج
 * كان يُنتج رابطاً ~7.5KB — فوق حدّ سطر الطلب في nginx (8KB) ⇒ 414 قبل أن
 * تُقلع الواجهة. والتعداد يبقى للمجموعات التي لا تصنيف لها وللروابط القديمة.
 */
test("رابط الكرت المجمّع يفضّل التصنيف ولا يعدّ المعرّفات", () => {
  const many = Array.from({ length: 1500 }, (_, i) => 100000 + i);
  const byCategory = productGroupPath({ name: "منتجات عامة", categoryId: 3, ids: many });
  assert.equal(byCategory, `/product-group?category=3&name=${encodeURIComponent("منتجات عامة")}`);
  assert.ok(byCategory.length < 100);
  // التعداد نفسه كان سيتجاوز حدّ سطر الطلب.
  assert.ok(many.join(",").length > 8 * 1024);
});

test("بلا تصنيف يبقى التعداد — ومجموعةٌ فارغة لا تكسر الرابط", () => {
  assert.equal(
    productGroupPath({ name: "185/65/14", ids: [7, 8] }),
    `/product-group?ids=7,8&name=${encodeURIComponent("185/65/14")}`,
  );
  assert.equal(
    productGroupPath({ name: "بدون تصنيف", categoryId: null, ids: [] }),
    `/product-group?ids=&name=${encodeURIComponent("بدون تصنيف")}`,
  );
});
