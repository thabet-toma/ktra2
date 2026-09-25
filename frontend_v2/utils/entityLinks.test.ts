import assert from "node:assert/strict";
import test from "node:test";

import {
  entityPathForReference,
  foldStatementReversals,
  isSafeInternalPath,
  platformNoteTarget,
  productGroupPath,
  referenceTypeLabel,
  statementMovementTone,
  statementToneRowClass,
  withStatementLinkSublines,
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

// ── #214-ب: المرتجعُ في الوجه المالي ───────────────────────────────────────
// قيدُ مرتجع البيع يُكتب بـ`reference_type="SALES_INVOICE"` **كالبيعة حرفاً**،
// فكانت هذه الدالّةُ تسمّيه فاتورةَ مبيعات في كشف الحساب وفي عنوان نافذة
// التفاصيل — وهو بلاغُ المالك: «لما اضغط عليه بتبين كلمة فاتورة مبيعات».
test('مرتجع البيع لا يُسمّى فاتورة مبيعات حين يُعرف نوعه', () => {
  assert.equal(referenceTypeLabel('SALES_INVOICE'), 'فاتورة مبيعات');
  assert.equal(referenceTypeLabel('SALES_INVOICE', 'sale_return'), 'مرتجع بيع');
  assert.equal(referenceTypeLabel('SALES_INVOICE', 'sale'), 'فاتورة مبيعات');
});

test('غياب النوع يُبقي السلوك القديم حرفياً — المستدعون الذين لا يملكونه لا ينكسرون', () => {
  assert.equal(referenceTypeLabel('SALES_INVOICE', null), 'فاتورة مبيعات');
  assert.equal(referenceTypeLabel('CUSTOMER_PAYMENT', undefined), 'سند قبض');
  assert.equal(referenceTypeLabel(''), 'حركة');
});

test("سند على ثلاثة مستحقّات: صفّه مرّة واحدة وسطرٌ معلوماتي في كل مجموعة ظاهرة", () => {
  const rows = [
    { id: 1, link_key: "LOGISTICS_CLEARANCE:13", debit: "0", credit: "9000", running_balance: "9000" },
    { id: 2, link_key: "LOGISTICS_CLEARANCE:14", debit: "0", credit: "6000", running_balance: "15000" },
    {
      id: 3, link_key: null, debit: "19000", credit: "0", running_balance: "-4000",
      link_targets: [
        { key: "LOGISTICS_CLEARANCE:13", label: "SH-0019", amount: "9000.00" },
        { key: "LOGISTICS_CLEARANCE:14", label: "SH-0014", amount: "6000.00" },
        // مستندٌ خارج الصفحة — لا سطر له.
        { key: "LOGISTICS_CLEARANCE:15", label: "SH-0015", amount: "4000.00" },
      ],
    },
  ];
  const out = withStatementLinkSublines(rows);
  assert.equal(out.length, 5);
  assert.deepEqual(out.slice(0, 3), rows);
  const infos = out.slice(3);
  assert.deepEqual(infos.map((r) => [r.link_key, r.info_amount]), [
    ["LOGISTICS_CLEARANCE:13", "9000.00"],
    ["LOGISTICS_CLEARANCE:14", "6000.00"],
  ]);
  // لا أثر على الرصيد: لا مدين ولا دائن ولا رصيد جارٍ.
  for (const r of infos) assert.deepEqual([r.debit, r.credit, r.running_balance], ["", "", ""]);
});

/* ── القيد المعكوس وعكسه: سطرٌ رماديٌّ واحد ورصيدٌ مطويّ ── */
const pairRows = [
  { id: 1, journal_id: 10, debit: "0", credit: "11348.22", running_balance: "11348.22",
    running_balance_folded: "11348.22", balance_before_folded: "0", reversal_pair_id: null, reversal_pair: null },
  { id: 2, journal_id: 283, debit: "13928.63", credit: "0", running_balance: "-2580.41",
    running_balance_folded: "11348.22", balance_before_folded: "11348.22", reversal_pair_id: 283,
    reversal_pair: { original_journal_id: 283, reversal_journal_id: 10979, role: "original" as const } },
  { id: 3, journal_id: 10979, debit: "0", credit: "13928.63", running_balance: "11348.22",
    running_balance_folded: "11348.22", balance_before_folded: "11348.22", reversal_pair_id: 283,
    reversal_pair: { original_journal_id: 283, reversal_journal_id: 10979, role: "reversal" as const } },
  { id: 4, journal_id: 10980, debit: "4298.96", credit: "0", running_balance: "7049.26",
    running_balance_folded: "7049.26", balance_before_folded: "11348.22", reversal_pair_id: null, reversal_pair: null },
];

test("foldStatementReversals: a zero-net pair folds into one summary row with no misleading balance", () => {
  const out = foldStatementReversals(pairRows, new Set());
  assert.equal(out.length, 3);
  const summary = out[1];
  assert.deepEqual(summary.reversal_summary, { original_journal_id: 283, reversal_journal_id: 10979 });
  assert.deepEqual([summary.debit, summary.credit, summary.running_balance], ["", "", "11348.22"]);
  assert.ok(!out.some((r) => r.running_balance === "-2580.41"));
  // الختامي نفسه مطويّاً وخاماً.
  assert.equal(out[2].running_balance, pairRows[3].running_balance);
});

test("foldStatementReversals: an expanded pair shows both sides under it without a running balance", () => {
  const out = foldStatementReversals(pairRows, new Set([283]));
  assert.deepEqual(out.map((r) => r.id), [1, "reversal-283", 2, 3, 4]);
  const members = out.filter((r) => r.reversal_member);
  assert.deepEqual(members.map((r) => [r.debit, r.credit, r.running_balance]), [
    ["13928.63", "0", ""],
    ["0", "13928.63", ""],
  ]);
  // السطر وطرفاه في مجموعةٍ واحدة لا في مجموعة فاتورتهم.
  assert.deepEqual(new Set(out.slice(1, 4).map((r) => r.link_key)), new Set(["reversal:283"]));
});

test("foldStatementReversals: rows without a pair pass through untouched", () => {
  const plain = [pairRows[0], pairRows[3]];
  const out = foldStatementReversals(plain, new Set());
  assert.deepEqual(out.map((r) => r.running_balance), ["11348.22", "7049.26"]);
});
