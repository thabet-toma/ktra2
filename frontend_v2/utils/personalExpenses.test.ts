import assert from "node:assert/strict";
import test from "node:test";

import { monthKeyOf, shiftMonthKey, monthKeyLabel, validateExpenseDraft } from "./personalExpenses.ts";

test("month key is the first 7 chars of an ISO date", () => {
  assert.equal(monthKeyOf("2026-07-18"), "2026-07");
  assert.equal(monthKeyOf("2026-01-01T09:00:00Z"), "2026-01");
});

test("shifting a month key crosses year boundaries in both directions", () => {
  assert.equal(shiftMonthKey("2026-07", 1), "2026-08");
  assert.equal(shiftMonthKey("2026-12", 1), "2027-01");
  assert.equal(shiftMonthKey("2026-01", -1), "2025-12");
  assert.equal(shiftMonthKey("2026-03", -3), "2025-12");
});

test("month key label is the Arabic month with the year", () => {
  assert.equal(monthKeyLabel("2026-07"), "تموز 2026");
  assert.equal(monthKeyLabel("2026-01"), "كانون الثاني 2026");
});

test("draft validation refuses empty title, non-positive amount and missing date", () => {
  assert.equal(validateExpenseDraft({ date: "2026-07-18", title: "قهوة", amount: "12.5" }), null);
  assert.equal(validateExpenseDraft({ date: "2026-07-18", title: "  ", amount: "12" }), "البيان مطلوب.");
  assert.equal(validateExpenseDraft({ date: "2026-07-18", title: "قهوة", amount: "0" }), "المبلغ يجب أن يكون أكبر من صفر.");
  assert.equal(validateExpenseDraft({ date: "2026-07-18", title: "قهوة", amount: "" }), "المبلغ يجب أن يكون أكبر من صفر.");
  assert.equal(validateExpenseDraft({ date: "", title: "قهوة", amount: "12" }), "التاريخ مطلوب.");
});
