import test from "node:test";
import assert from "node:assert/strict";

// node --test يحتاج امتداداً صريحاً في الاستيراد.
import {
  currentMonth, formatCounter, formatMinutes, formatShiftPeriods, monthDays,
  rejectMessage, sessionSeconds, statusPillClass,
} from "./attendance.ts";

test("formatMinutes: الصفر يُطبع ولا يختفي", () => {
  assert.equal(formatMinutes(0), "0د");
  assert.equal(formatMinutes(null), "0د");
  assert.equal(formatMinutes(45), "45د");
  assert.equal(formatMinutes(60), "1س");
  assert.equal(formatMinutes(450), "7س 30د");
});

test("formatMinutes: السالب لا يُعرض سالباً", () => {
  assert.equal(formatMinutes(-30), "0د");
});

test("formatCounter: شكل العدّاد الحيّ", () => {
  assert.equal(formatCounter(0), "0 س 0 د 0 ث");
  assert.equal(formatCounter(10799), "2 س 59 د 59 ث");
  assert.equal(formatCounter(-5), "0 س 0 د 0 ث");
});

test("sessionSeconds: يَعُدّ من فرق الخادم لا من ساعة الجهاز", () => {
  // الخادم يقول: مضت ساعتان عند لحظة الجلب.
  const since = "2026-03-02T09:00:00Z";
  const serverNow = "2026-03-02T11:00:00Z";
  const fetchedAt = 1_000_000;
  assert.equal(sessionSeconds(since, serverNow, fetchedAt, fetchedAt), 7200);
  // ومرّت 30 ثانية محلياً منذ الجلب.
  assert.equal(sessionSeconds(since, serverNow, fetchedAt, fetchedAt + 30_000), 7230);
});

test("sessionSeconds: ساعةُ جهازٍ متأخّرة لا تُنتج رقماً كاذباً", () => {
  // لو عُدّ من `since` بساعة الجهاز (وهي متأخّرة ساعةً) لظهر الرقم سالباً.
  const since = "2026-03-02T09:00:00Z";
  const serverNow = "2026-03-02T09:45:00Z";
  const deviceClockMs = Date.parse("2026-03-02T08:45:00Z");
  assert.equal(sessionSeconds(since, serverNow, deviceClockMs, deviceClockMs), 2700);
});

test("sessionSeconds: تاريخ غير صالح يعيد صفراً لا NaN", () => {
  assert.equal(sessionSeconds("لا شيء", "ولا هذا", 0, 0), 0);
});

test("formatShiftPeriods: الفترة الثانية تظهر حين توجد وحدها", () => {
  assert.equal(
    formatShiftPeriods({ start1: "09:00:00", end1: "17:00:00" }),
    "09:00 — 17:00");
  assert.equal(
    formatShiftPeriods({
      start1: "09:00:00", end1: "13:00:00", start2: "16:00:00", end2: "20:00:00",
    }),
    "09:00 — 13:00 · 16:00 — 20:00");
  assert.equal(formatShiftPeriods(null), "");
});

test("monthDays: صفٌّ لكل يوم من الشهر، والكبيسة تُحسب", () => {
  assert.equal(monthDays("2026-03").length, 31);
  assert.equal(monthDays("2026-04").length, 30);
  assert.equal(monthDays("2026-02").length, 28);
  assert.equal(monthDays("2028-02").length, 29);
  assert.equal(monthDays("2026-03")[0], "2026-03-01");
  assert.equal(monthDays("2026-03")[30], "2026-03-31");
});

test("monthDays: صيغة خاطئة تعيد قائمة فارغة لا تنهار", () => {
  assert.deepEqual(monthDays("2026"), []);
  assert.deepEqual(monthDays(""), []);
  assert.deepEqual(monthDays("2026-13"), []);
});

test("currentMonth: يُصفّر الشهر أحاديّ الرقم", () => {
  assert.equal(currentMonth(new Date(2026, 2, 15)), "2026-03");
  assert.equal(currentMonth(new Date(2026, 11, 1)), "2026-12");
});

test("statusPillClass: الغياب وحده أحمر والعذر رماديّ لا أخضر", () => {
  assert.match(statusPillClass("absent"), /red/);
  assert.match(statusPillClass("present"), /emerald/);
  assert.match(statusPillClass("late"), /amber/);
  assert.match(statusPillClass("leave"), /sky/);
  assert.match(statusPillClass("unscheduled"), /slate/);
});

test("rejectMessage: خارج النطاق يقول كم يبعد وكم مسموح", () => {
  const message = rejectMessage("out_of_range", "خارج نطاق موقع العمل", 812, 150);
  assert.match(message, /812/);
  assert.match(message, /150/);
});

test("rejectMessage: بلا مسافة يسقط على تسمية الخادم", () => {
  assert.equal(
    rejectMessage("out_of_range", "خارج نطاق موقع العمل"),
    "خارج نطاق موقع العمل");
});

test("rejectMessage: سببٌ مجهول لا يترك المستخدم بلا رسالة", () => {
  assert.equal(rejectMessage("", ""), "تعذّر قبول التسجيل.");
});
