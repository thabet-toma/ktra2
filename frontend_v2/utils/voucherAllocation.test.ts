import { test } from "node:test";
import assert from "node:assert/strict";

import { docKey, docSettlement, fifoFill, overpaymentExcess, type AllocatableDoc } from "./voucherAllocation.ts";

const clearance = (id: number, remaining: string, date: string): AllocatableDoc => ({
  id, label: `تخليص #${id}`, remaining, date, target: { kind: "clearance", id },
});

test("an invoice and a clearance with the same id are different rows", () => {
  assert.notEqual(docKey({ id: 3 }), docKey({ id: 3, target: { kind: "clearance", id: 3 } }));
});

test("fifo fills the oldest due first regardless of list order", () => {
  const docs = [clearance(2, "400", "2026-07-10"), clearance(1, "600", "2026-06-10")];
  assert.deepEqual(
    fifoFill(docs, 800).map((r) => [r.doc.id, r.amount]),
    [[1, "600.00"], [2, "200.00"]],
  );
});

test("fifo stops when the voucher is spent and skips settled docs", () => {
  const docs = [clearance(1, "0", "2026-06-01"), clearance(2, "100.10", "2026-06-02"), clearance(3, "50", "2026-06-03")];
  assert.deepEqual(fifoFill(docs, 100.1).map((r) => [r.doc.id, r.amount]), [[2, "100.10"]]);
});

test("overpayment excess is what exceeds the remaining, in exact cents", () => {
  assert.equal(overpaymentExcess(9600, { accrual_posted: true, remaining: "7073.00" }), 2527);
  assert.equal(overpaymentExcess("100.30", { accrual_posted: true, remaining: "100.10" }), 0.2);
  assert.equal(overpaymentExcess(500, { accrual_posted: true, remaining: "700" }), 0);
});

test("no split before the accrual is posted — the advance stays on its document", () => {
  assert.equal(overpaymentExcess(9600, { accrual_posted: false, remaining: "0" }), 0);
});

test("after the accrual is posted the screen shows the server's remaining, not lines minus payments", () => {
  // سند مخلّص 500 موزَّع على تخليص 600: الخادم يقول 100، والتقدير المحلي كان 600.
  const server = { amount_paid: "500.00", remaining_balance: "100.00", advance_balance: "0.00" };
  assert.deepEqual(docSettlement(true, server, { due: 600, paid: 0 }), { paid: 500, remaining: 100, advance: 0 });
});

test("before the accrual the draft lines are the estimate", () => {
  assert.deepEqual(docSettlement(false, { remaining_balance: "0" }, { due: 600.1, paid: 700 }), { paid: 700, remaining: 0, advance: 99.9 });
  assert.deepEqual(docSettlement(true, null, { due: 600, paid: 250 }), { paid: 250, remaining: 350, advance: 0 });
});

test("docs without a date come last", () => {
  const docs: AllocatableDoc[] = [{ id: 9, label: "فاتورة", remaining: "50" }, clearance(1, "50", "2026-06-01")];
  assert.deepEqual(fifoFill(docs, 60).map((r) => [docKey(r.doc), r.amount]), [["clearance:1", "50.00"], ["invoice:9", "10.00"]]);
});
