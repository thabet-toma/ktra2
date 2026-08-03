/**
 * مصاريف شخصية — منطق صرف (بلا React) تستهلكه شاشة «مصاريفي الشخصية».
 *
 * التنقّل بين الشهور والتحقق من المسودة منطقٌ يستحق اختباراً وحده؛ أما الجمع
 * والتصنيف فمن الخادم (hr.PersonalExpenseViewSet.summary) — مصدر حقيقة واحد.
 */
const MONTH_NAMES = [
  "كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
  "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول",
];

/** مفتاح الشهر (YYYY-MM) من تاريخ ISO. */
export function monthKeyOf(iso: string): string {
  return String(iso).slice(0, 7);
}

/** إزاحة مفتاح الشهر بعدد أشهر (سالب للخلف) مع عبور حدود السنة. */
export function shiftMonthKey(key: string, delta: number): string {
  const [year, month] = key.split("-").map(Number);
  const total = year * 12 + (month - 1) + delta;
  const y = Math.floor(total / 12);
  const m = total - y * 12 + 1;
  return `${y}-${String(m).padStart(2, "0")}`;
}

/** «تموز 2026» — تسمية عربية للشهر المعروض. */
export function monthKeyLabel(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

export interface ExpenseDraft {
  date: string;
  title: string;
  amount: string;
}

/** رسالة الخطأ الأولى إن كانت المسودة غير صالحة، وإلا null. */
export function validateExpenseDraft(draft: ExpenseDraft): string | null {
  if (!draft.date) return "التاريخ مطلوب.";
  if (!draft.title.trim()) return "البيان مطلوب.";
  const amount = Number(draft.amount);
  if (!Number.isFinite(amount) || amount <= 0) return "المبلغ يجب أن يكون أكبر من صفر.";
  return null;
}
