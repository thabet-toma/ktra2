import assert from "node:assert/strict";
import { test } from "node:test";

import {
  bucketItemPath,
  eligibleTotal,
  fillRefundPicks,
  pickedTotal,
  refundPicksError,
  refundSourcesPayload,
  type SurplusRow,
} from "./partySurplus.ts";

const row = (over: Partial<SurplusRow>): SurplusRow => ({
  source: "note", id: 1, label: "إشعار DN-0001", date: "2026-07-01", amount: "100",
  unallocated: "100", currency: 1, currency_code: "ILS", exchange_rate: "1", ...over,
});

const rows: SurplusRow[] = [
  row({ source: "supplier_payment", id: 7, label: "سند صرف #7", date: "2026-07-05", unallocated: "40.50" }),
  row({ id: 1, date: "2026-07-01", unallocated: "100" }),
  row({ id: 2, date: "2026-07-03", unallocated: "30", currency: 2, currency_code: "USD" }),
];

test("fill takes the oldest eligible source first and never exceeds a source", () => {
  assert.deepEqual(fillRefundPicks(rows, 120, 1), { "note:1": "100.00", "supplier_payment:7": "20.00" });
  assert.deepEqual(fillRefundPicks(rows, 1000, 1), { "note:1": "100.00", "supplier_payment:7": "40.50" });
});

test("another currency is excluded from totals and payload", () => {
  assert.equal(eligibleTotal(rows, 1), 140.5);
  const picks = { "note:1": "10", "note:2": "30" };
  assert.equal(pickedTotal(rows, picks, 1), 10);
  assert.deepEqual(refundSourcesPayload(rows, picks, 1), [{ source: "note", id: 1, amount: "10.00" }]);
});

test("errors name the over-picked source, then the over-voucher total", () => {
  assert.match(refundPicksError(rows, { "note:1": "100.01" }, 500, 1) ?? "", /DN-0001/);
  assert.match(refundPicksError(rows, { "note:1": "100" }, 99.99, 1) ?? "", /يتجاوز مبلغه/);
  assert.equal(refundPicksError(rows, { "note:1": "100" }, 100, 1), null);
});

test("bucketItemPath: السند والإشعار بشاشتيهما، والمستحقّ بتبويبه في ملف شحنته", () => {
  assert.equal(bucketItemPath({ source: "voucher", id: 7 }), "/supplier-payments?payment_id=7");
  assert.equal(bucketItemPath({ source: "note", id: 3 }), "/accounting/credit-debit-notes?note_id=3");
  assert.equal(bucketItemPath({ source: "clearance", id: 5, shipment_id: 12 }), "/import-flow/12?tab=clearance");
  assert.equal(bucketItemPath({ source: "local", id: 5, shipment_id: 12 }), "/import-flow/12?tab=local");
  assert.equal(bucketItemPath({ source: "freight", id: 12, shipment_id: 12 }), "/import-flow/12?tab=deals");
  // إرساليةٌ بلا شحنة: لا ملفّ تُفتح فيه — نصٌّ بلا رابط.
  assert.equal(bucketItemPath({ source: "local", id: 5, shipment_id: null }), null);
});
