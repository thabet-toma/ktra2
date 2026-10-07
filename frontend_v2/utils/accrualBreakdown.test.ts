import { test } from "node:test";
import assert from "node:assert/strict";

import {
  accrualTypeLabel, accrualTypeOptions, diffRowClass, diffRowBadge, diffTotals, fillProgress, signedMoney, toCents,
  type AccrualDiffRow,
} from "./accrualBreakdown.ts";

test("cents are rounded half-up so decimal strings never drift", () => {
  assert.equal(toCents("0.1") + toCents("0.2"), toCents("0.3"));
  assert.equal(toCents("1234.565"), 123457);
  assert.equal(toCents("-5.5"), -550);
  assert.equal(toCents(""), 0);
  assert.equal(toCents("abc"), 0);
});

test("fill is saveable only when the sum equals the total to the cent", () => {
  const lines = [{ label: "رسوم", type: "declaration_fee", amount: "100.10" }, { label: "نقل", type: "other", amount: "50.20" }];
  assert.deepEqual(fillProgress(lines, "150.30"), { sumCents: 15030, totalCents: 15030, matches: true, canSave: true });
  const off = fillProgress(lines, "150.31");
  assert.equal(off.matches, false);
  assert.equal(off.canSave, false);
});

test("float-unsafe sums still match (0.1 + 0.2 = 0.3)", () => {
  const lines = [{ label: "أ", type: "other", amount: "0.1" }, { label: "ب", type: "other", amount: "0.2" }];
  assert.equal(fillProgress(lines, "0.30").canSave, true);
});

test("a blank label or no lines blocks saving even when the sum matches", () => {
  assert.equal(fillProgress([{ label: "  ", type: "other", amount: "10" }], "10").canSave, false);
  assert.equal(fillProgress([], "0").canSave, false);
});

test("decrease is green, increase is red, no change is neutral", () => {
  assert.match(diffRowClass("-0.01"), /emerald/);
  assert.match(diffRowClass("12.5"), /red/);
  assert.doesNotMatch(diffRowClass("0.00"), /emerald|red/);
});

test("new and removed rows carry a badge, others none", () => {
  assert.equal(diffRowBadge("new"), "جديد");
  assert.equal(diffRowBadge("removed"), "محذوف");
  assert.equal(diffRowBadge("changed"), null);
  assert.equal(diffRowBadge("same"), null);
});

test("diff totals add up before, after and difference in cents", () => {
  const rows: AccrualDiffRow[] = [
    { label: "أ", type: "other", before: "100.00", after: "80.00", difference: "-20.00", status: "changed" },
    { label: "ب", type: "other", before: "0.00", after: "5.05", difference: "5.05", status: "new" },
    { label: "ج", type: "other", before: "10.00", after: "0.00", difference: "-10.00", status: "removed" },
  ];
  assert.deepEqual(diffTotals(rows), { before: 11000, after: 8505, difference: -2495 });
});

test("signed money puts a plus on increases and keeps the minus", () => {
  assert.equal(signedMoney("1500"), "+1,500");
  assert.equal(signedMoney("-20.5"), "-20.5");
  assert.equal(signedMoney("0"), "0");
});

test("type label falls back to the raw value; options differ by kind", () => {
  assert.equal(accrualTypeLabel("vat"), "ضريبة القيمة المضافة");
  assert.equal(accrualTypeLabel("freight"), "شحن دولي");
  assert.equal(accrualTypeLabel("local"), "نقل محلي");
  assert.equal(accrualTypeLabel("total"), "إجمالي");
  assert.equal(accrualTypeLabel("custom_x"), "custom_x");
  assert.ok(accrualTypeOptions("clearance").includes("broker_commission"));
  assert.deepEqual(accrualTypeOptions("freight"), ["freight", "other"]);
  assert.deepEqual(accrualTypeOptions("local"), ["local", "other"]);
});
