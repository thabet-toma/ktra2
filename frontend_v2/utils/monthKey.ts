/**
 * مفتاح الشهر (YYYY-MM) — التنقّل بين الشهور وتسميتها العربية.
 *
 * استُخرج من `utils/personalExpenses` حين احتاجته شاشة الرواتب: متصفّح الشهور
 * واحدٌ في كل شاشة تعرض فترة شهرية، ونسختان منه تفترقان عند أول إصلاح.
 *
 * التسمية عربية ثابتة لا `toLocaleDateString('ar')` — الأخيرة تُخرِج تواريخ
 * هجرية أو أرقاماً هندية حسب إعداد ICU على جهاز المستخدم.
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

/** حدود الشهر ISO — أول يوم وآخر يوم، أساس فترة كشف الراتب. */
export function monthKeyRange(key: string): { start: string; end: string } {
  const [year, month] = key.split("-").map(Number);
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    start: `${year}-${pad(month)}-01`,
    end: `${year}-${pad(month)}-${pad(lastDay)}`,
  };
}
