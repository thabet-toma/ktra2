import assert from "node:assert/strict";
import test from "node:test";

import { formatDateLocalized, formatDateValue } from "./formatDate.ts";

test("formats ISO date as dd/MM/yyyy", () => {
  assert.equal(formatDateLocalized("2026-07-18"), "18/07/2026");
});

test("takes the date part of a longer ISO timestamp", () => {
  assert.equal(formatDateLocalized("2026-07-18T09:30:00Z"), "18/07/2026");
});

test("empty / null yields empty string", () => {
  assert.equal(formatDateLocalized(""), "");
  assert.equal(formatDateLocalized(null), "");
  assert.equal(formatDateLocalized(undefined), "");
});

test("non-ISO input is returned untouched (first 10 chars)", () => {
  assert.equal(formatDateLocalized("not-a-date"), "not-a-date");
});

test("formatDateValue matches the ISO formatter for stored dates", () => {
  assert.equal(formatDateValue("2026-07-18"), "18/07/2026");
  assert.equal(formatDateValue("2026-07-18T09:30:00Z"), "18/07/2026");
});

test("formatDateValue accepts Date and epoch millis (legacy shapes)", () => {
  assert.equal(formatDateValue(new Date(2026, 6, 18)), "18/07/2026");
  assert.equal(formatDateValue(new Date(2026, 6, 18).getTime()), "18/07/2026");
});

test("formatDateValue keeps unparseable input and blanks empties", () => {
  assert.equal(formatDateValue("not-a-date"), "not-a-date");
  assert.equal(formatDateValue(""), "");
  assert.equal(formatDateValue(null), "");
  assert.equal(formatDateValue(undefined), "");
});
