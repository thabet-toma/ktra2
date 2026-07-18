/**
 * G10: توطين عرض التاريخ. حقول <input type="date"> الأصلية تعرض mm/dd/yyyy حسب
 * لغة المتصفّح (لا لغة الصفحة)، فنعرض التاريخ بصيغة محلية dd/MM/yyyy عبر Intl.
 *
 * ISO المتوقّع: "YYYY-MM-DD" (أو ISO أطول — نأخذ أول 10). الأرقام لاتينية (خانات
 * النظام المالي كلها لاتينية) لتوافق بقية الواجهة.
 */
export function formatDateLocalized(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = String(iso).slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return s;
  const [, y, mo, d] = m;
  return `${d}/${mo}/${y}`;
}

/** التاريخ الحالي بصيغة ISO المحلية (YYYY-MM-DD) — لا UTC (يتجنّب انزياح اليوم). */
export function todayIso(): string {
  const now = new Date();
  const off = now.getTimezoneOffset();
  return new Date(now.getTime() - off * 60000).toISOString().slice(0, 10);
}
