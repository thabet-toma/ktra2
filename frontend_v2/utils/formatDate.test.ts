import assert from "node:assert/strict";
import test from "node:test";

import {
  formatDateLocalized,
  formatDateTimeValue,
  formatDateValue,
  formatTimeValue,
  formatWeekdayName,
} from "./formatDate.ts";

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

// G10-B: الوقت والتاريخ+الوقت واسم اليوم بأرقام لاتينية وتقويم ميلادي دائماً —
// `toLocaleTimeString('ar-EG')` كان يعطي أرقاماً هندية و`ar-SA` تقويماً هجرياً
// على أجهزة تحمل بيانات ICU كاملة، فتظهر التواريخ «بأحرف غير مفهومة».
test("formatTimeValue is 24h HH:mm with latin digits", () => {
  assert.equal(formatTimeValue(new Date(2026, 6, 18, 9, 5)), "09:05");
  assert.equal(formatTimeValue(new Date(2026, 6, 18, 21, 40)), "21:40");
});

test("formatTimeValue blanks empties and unparseable input", () => {
  assert.equal(formatTimeValue(""), "");
  assert.equal(formatTimeValue(null), "");
  assert.equal(formatTimeValue(undefined), "");
  assert.equal(formatTimeValue("not-a-date"), "");
});

test("formatDateTimeValue joins the site date format with the time", () => {
  assert.equal(
    formatDateTimeValue(new Date(2026, 6, 18, 9, 5)),
    "18/07/2026 09:05",
  );
});

test("formatDateTimeValue falls back to the date alone for date-only values", () => {
  assert.equal(formatDateTimeValue("2026-07-18"), "18/07/2026 00:00");
  assert.equal(formatDateTimeValue(""), "");
  assert.equal(formatDateTimeValue("not-a-date"), "not-a-date");
});

test("formatWeekdayName returns a fixed Arabic day name (no ICU dependency)", () => {
  // 2026-07-18 = السبت
  assert.equal(formatWeekdayName("2026-07-18"), "السبت");
  assert.equal(formatWeekdayName(new Date(2026, 6, 19)), "الأحد");
  assert.equal(formatWeekdayName(""), "");
  assert.equal(formatWeekdayName("not-a-date"), "");
});
