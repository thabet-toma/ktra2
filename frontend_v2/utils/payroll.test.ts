import test from "node:test";
import assert from "node:assert/strict";

// node --test يحتاج امتداداً صريحاً في الاستيراد.
import {
  formatHours, formatLateMinutes, validateAdjustmentDraft, validateEmployeeDraft,
  validateWorkLogDraft,
} from "./payroll.ts";
import { monthKeyLabel, monthKeyOf, monthKeyRange, shiftMonthKey } from "./monthKey.ts";

const monthly = {
  name: "سامي",
  pay_type: "monthly" as const,
  monthly_salary: "2600",
  hourly_rate: "0",
  standard_hours_per_day: "8",
  working_days_per_month: "26",
};
const hourly = { ...monthly, pay_type: "hourly" as const, monthly_salary: "0", hourly_rate: "20" };

test("الموظف الدائم يلزمه راتب شهري والجزئي أجر ساعة", () => {
  assert.equal(validateEmployeeDraft(monthly), null);
  assert.equal(validateEmployeeDraft(hourly), null);
  assert.match(
    validateEmployeeDraft({ ...monthly, monthly_salary: "0" }) || "", /راتب شهري/);
  assert.match(
    validateEmployeeDraft({ ...hourly, hourly_rate: "" }) || "", /أجر الساعة/);
});

test("الموظف الدائم لا يُقبل بأيام أو ساعات دوام صفرية", () => {
  assert.match(
    validateEmployeeDraft({ ...monthly, working_days_per_month: "0" }) || "", /أيام الدوام/);
  assert.match(
    validateEmployeeDraft({ ...monthly, standard_hours_per_day: "0" }) || "", /ساعات الدوام/);
});

test("سطر الساعات: موجب ولا يتجاوز اليوم", () => {
  assert.equal(validateWorkLogDraft({ date: "2026-08-03", hours: "7.5" }), null);
  assert.match(validateWorkLogDraft({ date: "", hours: "7" }) || "", /التاريخ/);
  assert.match(validateWorkLogDraft({ date: "2026-08-03", hours: "0" }) || "", /أكبر من صفر/);
  assert.match(validateWorkLogDraft({ date: "2026-08-03", hours: "25" }) || "", /24/);
});

test("الغياب يُقاس بالأيام والتأخير بالدقائق", () => {
  const base = { date: "2026-08-03", days: "1", minutes: "0" };
  assert.equal(validateAdjustmentDraft({ ...base, kind: "absence" }), null);
  assert.match(
    validateAdjustmentDraft({ ...base, kind: "late" }) || "", /دقائق التأخير/);
  assert.equal(
    validateAdjustmentDraft({ ...base, kind: "late", minutes: "30" }), null);
});

test("تنسيق الساعات والدقائق للقراءة", () => {
  assert.equal(formatHours("8.00"), "8");
  assert.equal(formatHours("7.50"), "7.5");
  assert.equal(formatLateMinutes(45), "45 د");
  assert.equal(formatLateMinutes(90), "1 س 30 د");
  assert.equal(formatLateMinutes(120), "2 س");
});

test("مفتاح الشهر: الإزاحة والتسمية والحدود", () => {
  assert.equal(monthKeyOf("2026-08-15"), "2026-08");
  assert.equal(shiftMonthKey("2026-01", -1), "2025-12");
  assert.equal(shiftMonthKey("2026-12", 1), "2027-01");
  assert.equal(monthKeyLabel("2026-08"), "آب 2026");
  assert.deepEqual(monthKeyRange("2026-02"), { start: "2026-02-01", end: "2026-02-28" });
  assert.deepEqual(monthKeyRange("2024-02"), { start: "2024-02-01", end: "2024-02-29" });
  assert.deepEqual(monthKeyRange("2026-08"), { start: "2026-08-01", end: "2026-08-31" });
});
