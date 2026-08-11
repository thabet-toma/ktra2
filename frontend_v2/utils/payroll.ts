/**
 * الرواتب — منطق صرف (بلا React) تستهلكه شاشة «الرواتب».
 *
 * **لا احتساب هنا**: الاستحقاق والخصومات والصافي كلها من الخادم
 * (`hr/payslips/preview/`) — مصدر احتساب واحد لا اثنان يختلفان بقرش. ما هنا
 * تحقّقٌ من المدخلات قبل إزعاج الشبكة، وصياغة عرض لا أكثر.
 */
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
