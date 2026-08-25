import test from "node:test";
import assert from "node:assert/strict";

// node --test يحتاج امتداداً صريحاً في الاستيراد.
import {
  buildDailySheet, buildPayslipPrint,
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

/* ── الورقتان المطبوعتان ─────────────────────────────────────────────── */

const slip = {
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  pay_type: "monthly" as const,
  rate: "2600.00",
  worked_hours: "0.00",
  absence_days: "1.00",
  late_minutes: 90,
  gross: "2600.00",
  allowances: "100.00",
  absence_deduction: "100.00",
  late_deduction: "0.00",
  other_deductions: "0.00",
  net: "2600.00",
  status_label: "مرحّل",
  paid_total: "1000.00",
};

const employee = { name: "سامي", code: "EMP-2", job_title: "محاسب", balance: "1600.00" };

test("قسيمة الراتب: خمسة سطور ثابتة، والصفر يُطبع ولا يُحذف", () => {
  const doc = buildPayslipPrint(slip, employee);
  assert.equal(doc.title, "كشف راتب — سامي");
  assert.match(doc.period, /01\/08\/2026.*31\/08\/2026/);
  assert.equal(doc.lines.length, 5);
  assert.deepEqual(doc.lines.map((l) => l.label), [
    "الراتب الأساسي", "بدلات ومكافآت", "خصم الغياب", "خصم التأخير", "خصومات أخرى",
  ]);
  // سطر الخصم الصفري موجود بقيمته لا محذوفاً.
  assert.equal(doc.lines[3].deduct, "0");
  assert.equal(doc.lines[3].earn, "");
  assert.equal(doc.lines[0].earn, "2,600");
  assert.equal(doc.net, "2,600");
});

test("قسيمة الراتب لا تشتقّ «المتبقّي» — رصيد الدفاتر بدلاً منه", () => {
  const doc = buildPayslipPrint(slip, employee);
  const labels = doc.meta.map((m) => m.label);
  assert.equal(labels.some((l) => l.includes("المتبقّي")), false);
  assert.ok(labels.includes("المصروف من هذا الكشف"));
  assert.ok(labels.includes("رصيده في الدفاتر"));
  // الدائم يُحاسَب على غيابه وتأخيره لا على ساعاته.
  assert.ok(labels.includes("أيام الغياب"));
  assert.equal(labels.includes("ساعات العمل"), false);
});

test("قسيمة الجزئي تشرح الساعات وأجرها", () => {
  const doc = buildPayslipPrint(
    { ...slip, pay_type: "hourly", rate: "20.00", worked_hours: "62.50", gross: "1250.00" },
    { ...employee, pay_type_label: "بالساعة" },
  );
  assert.equal(doc.lines[0].label, "الأجر عن ساعات العمل");
  const hours = doc.meta.find((m) => m.label === "ساعات العمل");
  assert.equal(hours?.value, "62.5 ساعة");
  assert.equal(doc.meta.find((m) => m.label === "الأجر المحتسب")?.value, "20 / ساعة");
});

test("كشف الدوام: صفٌّ لكل يوم من أيام الشهر لا لكل سجلّ", () => {
  const sheet = buildDailySheet(
    "2026-08",
    [
      { date: "2026-08-03", hours: "8.00", notes: "" },
      { date: "2026-08-04", hours: "7.50", notes: "جرد" },
    ],
    [
      { date: "2026-08-10", kind: "absence", days: "1", minutes: 0, is_deductible: true, notes: "سفر" },
      { date: "2026-08-11", kind: "late", days: "0", minutes: 90, is_deductible: false, notes: "" },
    ],
  );
  assert.equal(sheet.rows.length, 31);
  assert.equal(sheet.rows[0].date, "2026-08-01");
  assert.equal(sheet.rows[30].date, "2026-08-31");

  const third = sheet.rows[2];
  assert.equal(third.hours, "8");
  assert.equal(third.weekday, "الاثنين");
  assert.equal(sheet.rows[3].note, "جرد");

  // اليوم بلا سجلّ يبقى صفّاً فارغاً — الثغرة تُرى ولا تُحذف من الورقة.
  assert.equal(sheet.rows[4].hours, "");
  assert.equal(sheet.rows[4].mark, "");

  assert.equal(sheet.rows[9].mark, "غياب يوم");
  assert.equal(sheet.rows[9].note, "سفر");
  // التأخير المعذور يُقال على الورقة صراحةً.
  assert.equal(sheet.rows[10].mark, "تأخير 1 س 30 د (معذور)");

  assert.equal(sheet.totalHours, "15.5");
  assert.equal(sheet.workedDays, 2);
  assert.equal(sheet.absenceDays, "1");
  assert.equal(sheet.lateMinutes, 90);
});

test("كشف الدوام يحترم طول الشهر ويجمع سجلّات اليوم الواحد", () => {
  const february = buildDailySheet("2026-02");
  assert.equal(february.rows.length, 28);
  assert.equal(february.totalHours, "0");

  const doubled = buildDailySheet("2026-08", [], [
    { date: "2026-08-05", kind: "absence", days: "0.5", minutes: 0, is_deductible: true, notes: "" },
    { date: "2026-08-05", kind: "late", days: "0", minutes: 20, is_deductible: true, notes: "" },
  ]);
  assert.equal(doubled.rows[4].mark, "غياب 0.5 يوم · تأخير 20 د");
  assert.equal(doubled.absenceDays, "0.5");
  assert.equal(doubled.lateMinutes, 20);
});
