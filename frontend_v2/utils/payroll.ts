/**
 * الرواتب — منطق صرف (بلا React) تستهلكه شاشة «الرواتب».
 *
 * **لا احتساب هنا**: الاستحقاق والخصومات والصافي كلها من الخادم
 * (`hr/payslips/preview/`) — مصدر احتساب واحد لا اثنان يختلفان بقرش. ما هنا
 * تحقّقٌ من المدخلات قبل إزعاج الشبكة، وصياغة عرض لا أكثر.
 */
import { formatMoney } from "./formatNumber.ts";
import { formatDateLocalized, formatWeekdayName } from "./formatDate.ts";
import { monthKeyRange } from "./monthKey.ts";

export type PayType = "monthly" | "hourly";

export interface EmployeeDraftInput {
  name: string;
  pay_type: PayType;
  monthly_salary: string;
  hourly_rate: string;
  standard_hours_per_day: string;
  working_days_per_month: string;
}

const positive = (value: string) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0;
};

/** رسالة الخطأ الأولى إن كانت بطاقة الموظف غير صالحة، وإلا null. */
export function validateEmployeeDraft(draft: EmployeeDraftInput): string | null {
  if (!draft.name.trim()) return "اسم الموظف مطلوب.";
  if (draft.pay_type === "hourly") {
    if (!positive(draft.hourly_rate)) return "الموظف الجزئي يلزمه أجر الساعة المتفق عليه.";
    return null;
  }
  if (!positive(draft.monthly_salary)) return "الموظف الدائم يلزمه راتب شهري.";
  if (!positive(draft.working_days_per_month)) return "أيام الدوام الشهرية يجب أن تكون أكبر من صفر.";
  if (!positive(draft.standard_hours_per_day)) return "ساعات الدوام اليومية يجب أن تكون أكبر من صفر.";
  return null;
}

/** رسالة الخطأ الأولى إن كان سطر الساعات غير صالح، وإلا null. */
export function validateWorkLogDraft(draft: { date: string; hours: string }): string | null {
  if (!draft.date) return "التاريخ مطلوب.";
  const hours = Number(draft.hours);
  if (!Number.isFinite(hours) || hours <= 0) return "عدد الساعات يجب أن يكون أكبر من صفر.";
  if (hours > 24) return "لا يتجاوز اليوم 24 ساعة.";
  return null;
}

/** رسالة الخطأ الأولى إن كان سطر الغياب/التأخير غير صالح، وإلا null. */
export function validateAdjustmentDraft(draft: {
  date: string; kind: "absence" | "late"; days: string; minutes: string;
}): string | null {
  if (!draft.date) return "التاريخ مطلوب.";
  if (draft.kind === "absence") {
    if (!positive(draft.days)) return "أيام الغياب يجب أن تكون أكبر من صفر.";
    return null;
  }
  if (!positive(draft.minutes)) return "دقائق التأخير يجب أن تكون أكبر من صفر.";
  return null;
}

/** «ساعة ونصف» تُقرأ أسرع من «1.50» في عمود ساعات. */
export function formatHours(value: unknown): string {
  const hours = Number(value);
  if (!Number.isFinite(hours)) return "0";
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(2).replace(/0$/, "");
}

/** دقائق التأخير كما يقرأها المستخدم: «1:30 س» بدل 90. */
export function formatLateMinutes(value: unknown): string {
  const minutes = Math.max(0, Math.round(Number(value) || 0));
  if (minutes < 60) return `${minutes} د`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} س ${rest} د` : `${hours} س`;
}

/* ── الورقتان المطبوعتان: قسيمة الراتب وكشف الدوام اليومي ───────────────
 *
 * ما يُبنى هنا محتوى ورقةٍ تُسلَّم بيد الموظف، لا حساب. كل مبلغ في القسيمة
 * لقطةٌ محفوظة في الكشف تُطبع كما هي، ولا طرح ولا جمع على المال — و«المتبقّي»
 * تحديداً لا يُشتقّ هنا: دفعةٌ غير مربوطة بالكشف (`payslip=null`) تجعل
 * `الصافي − المصروف` كذبةً على ورقة يوقّعها الموظف، فيُطبع بدلها رصيده في
 * الدفاتر كما يقوله الخادم. الجمع الوحيد جمعُ ساعاتٍ ودقائق — وهو ما يعدّه
 * الموظف بنفسه على الورقة فلا يحتمل خلافاً.
 *
 * البناء هنا لا في المكوّن كي يُختبر بلا متصفّح: الشاشة تستدعي `printReport`
 * على هذه البنى ولا تعرف كيف تُصاغ.
 */

export interface PrintMetaLine { label: string; value: string }

/** سطر في جدول القسيمة — عمود الاستحقاق أو عمود الخصم، لا كلاهما. */
export interface PayslipPrintLine { label: string; earn: string; deduct: string }

export interface PayslipPrintDoc {
  title: string;
  period: string;
  meta: PrintMetaLine[];
  lines: PayslipPrintLine[];
  net: string;
}

/** ما تحتاجه القسيمة من الكشف — بنيةٌ لا استيراد، فلا يجرّ المُختبِر الشبكة. */
export interface PayslipPrintSlip {
  period_start: string;
  period_end: string;
  pay_type: PayType;
  rate: string;
  worked_hours: string;
  absence_days: string;
  late_minutes: number;
  gross: string;
  allowances: string;
  absence_deduction: string;
  late_deduction: string;
  other_deductions: string;
  net: string;
  status_label: string;
  paid_total: string;
  notes?: string;
}

export interface PayslipPrintEmployee {
  name: string;
  code: string;
  job_title?: string;
  pay_type_label?: string;
  balance?: string;
}

/** محتوى قسيمة راتب موظفٍ واحد لفترة كشفٍ واحد. */
export function buildPayslipPrint(
  slip: PayslipPrintSlip, employee: PayslipPrintEmployee,
): PayslipPrintDoc {
  const hourly = slip.pay_type === "hourly";
  const meta: PrintMetaLine[] = [{ label: "رقم الموظف", value: employee.code || "—" }];
  if (employee.job_title) {
    meta.push({ label: "المسمّى الوظيفي", value: employee.job_title });
  }
  meta.push({
    label: "نوع الأجر",
    value: employee.pay_type_label || (hourly ? "بالساعة" : "شهري"),
  });
  // `rate` لقطةُ الكشف لا أجر البطاقة اليوم: القسيمة تشرح الرقم الذي حُوسب
  // عليه وقتها، وتعديلُ الأجر لاحقاً لا يعيد كتابة ورقةٍ سُلِّمت.
  meta.push({
    label: "الأجر المحتسب",
    value: `${formatMoney(slip.rate)} / ${hourly ? "ساعة" : "شهر"}`,
  });
  if (hourly) {
    meta.push({ label: "ساعات العمل", value: `${formatHours(slip.worked_hours)} ساعة` });
  } else {
    meta.push({ label: "أيام الغياب", value: `${formatHours(slip.absence_days)} يوم` });
    meta.push({ label: "التأخير", value: formatLateMinutes(slip.late_minutes) });
  }
  meta.push({ label: "حالة الكشف", value: slip.status_label });
  meta.push({ label: "المصروف من هذا الكشف", value: formatMoney(slip.paid_total) });
  if (employee.balance !== undefined) {
    meta.push({ label: "رصيده في الدفاتر", value: formatMoney(employee.balance) });
  }
  if (slip.notes) meta.push({ label: "ملاحظات", value: slip.notes });

  const earn = (label: string, value: string): PayslipPrintLine =>
    ({ label, earn: formatMoney(value), deduct: "" });
  const deduct = (label: string, value: string): PayslipPrintLine =>
    ({ label, earn: "", deduct: formatMoney(value) });

  return {
    title: `كشف راتب — ${employee.name}`,
    period: `الفترة من ${formatDateLocalized(slip.period_start)} `
      + `إلى ${formatDateLocalized(slip.period_end)}`,
    meta,
    // الصفر يُطبع ولا يُحذف: «خصم غياب 0» على ورقةٍ يوقّعها الموظف إقرارٌ بأن
    // شيئاً لم يُخصم، وحذفُ السطر يترك السؤال مفتوحاً — وهو أول ما يُسأل عنه.
    lines: [
      earn(hourly ? "الأجر عن ساعات العمل" : "الراتب الأساسي", slip.gross),
      earn("بدلات ومكافآت", slip.allowances),
      deduct("خصم الغياب", slip.absence_deduction),
      deduct("خصم التأخير", slip.late_deduction),
      deduct("خصومات أخرى", slip.other_deductions),
    ],
    net: formatMoney(slip.net),
  };
}

export interface DailySheetLog { date: string; hours: string; notes?: string }

export interface DailySheetAdjustment {
  date: string;
  kind: "absence" | "late";
  days: string;
  minutes: number;
  is_deductible: boolean;
  notes?: string;
}

/** يومٌ من الشهر — موجودٌ في الجدول وإن لم يُسجَّل عليه شيء. */
export interface DailySheetRow {
  date: string;
  weekday: string;
  /** ساعات اليوم، وفراغ ليومٍ بلا تسجيل. */
  hours: string;
  /** «غياب يوم» · «تأخير 30 د (معذور)» · فراغ. */
  mark: string;
  note: string;
}

export interface DailySheet {
  rows: DailySheetRow[];
  totalHours: string;
  workedDays: number;
  absenceDays: string;
  lateMinutes: number;
}

/**
 * كشف دوام موظفٍ واحد لشهر: صفٌّ لكل يومٍ من أيام الشهر لا لكل سجلّ.
 *
 * اليوم الذي لا سجلّ له يبقى صفّاً فارغاً بقصد — الورقة تُقرأ بالعين بحثاً عن
 * الثغرات، وقائمةُ المسجَّل وحده تُخفي اليوم الضائع بدل أن تُظهره.
 */
export function buildDailySheet(
  month: string,
  workLogs: DailySheetLog[] = [],
  adjustments: DailySheetAdjustment[] = [],
): DailySheet {
  const { start, end } = monthKeyRange(month);
  const prefix = start.slice(0, 8);
  const lastDay = Number(end.slice(8, 10));

  const logs = new Map<string, DailySheetLog>();
  workLogs.forEach((row) => logs.set(String(row.date).slice(0, 10), row));
  const marks = new Map<string, string[]>();
  const reasons = new Map<string, string[]>();

  let totalHours = 0;
  let workedDays = 0;
  let absenceDays = 0;
  let lateMinutes = 0;

  adjustments.forEach((row) => {
    const day = String(row.date).slice(0, 10);
    let text: string;
    if (row.kind === "absence") {
      const days = Number(row.days) || 0;
      absenceDays += days;
      text = days === 1 ? "غياب يوم" : `غياب ${formatHours(days)} يوم`;
    } else {
      const minutes = Math.max(0, Math.round(Number(row.minutes) || 0));
      lateMinutes += minutes;
      text = `تأخير ${formatLateMinutes(minutes)}`;
    }
    // «معذور» على الورقة لا في الدفاتر وحدها: الموظف يوقّع على غيابٍ لم يُخصم
    // منه، فلا يقرأ السطر إقراراً بخصمٍ لم يقع.
    if (!row.is_deductible) text += " (معذور)";
    marks.set(day, [...(marks.get(day) || []), text]);
    if (row.notes) reasons.set(day, [...(reasons.get(day) || []), row.notes]);
  });

  const rows: DailySheetRow[] = [];
  for (let day = 1; day <= lastDay; day += 1) {
    const iso = `${prefix}${String(day).padStart(2, "0")}`;
    const log = logs.get(iso);
    const hours = Number(log?.hours) || 0;
    if (hours > 0) {
      totalHours += hours;
      workedDays += 1;
    }
    const notes = [...(log?.notes ? [log.notes] : []), ...(reasons.get(iso) || [])];
    rows.push({
      date: iso,
      weekday: formatWeekdayName(iso),
      hours: hours > 0 ? formatHours(hours) : "",
      mark: (marks.get(iso) || []).join(" · "),
      note: notes.join(" · "),
    });
  }

  return {
    rows,
    totalHours: formatHours(totalHours),
    workedDays,
    absenceDays: formatHours(absenceDays),
    lateMinutes,
  };
}
