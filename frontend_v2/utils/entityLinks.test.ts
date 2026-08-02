import assert from "node:assert/strict";
import test from "node:test";

import {
  isSafeInternalPath,
  platformNoteTarget,
  statementMovementTone,
  statementToneRowClass,
} from "./entityLinks.ts";

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
