import assert from "node:assert/strict";
import test from "node:test";
import { getUnpaidImportDeals } from "./importPaymentReadiness.ts";

test("exposes supplier balances that block an international invoice", () => {
  assert.deepEqual(getUnpaidImportDeals({
    deals: [
      { deal_id: 109, ref_number: "D-0109", deal_unpaid_usd: 3000 },
      { deal_id: 108, ref_number: "D-0108", deal_unpaid_usd: 0.02 },
    ],
  }), [{ dealId: "109", dealRef: "D-0109", unpaidUsd: 3000 }]);
});

test("does not block when the server preview reports no supplier balance", () => {
  assert.deepEqual(getUnpaidImportDeals({ deals: [{ deal_id: 108, deal_unpaid_usd: 0 }] }), []);
  assert.deepEqual(getUnpaidImportDeals(null), []);
});
