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

/**
 * أي قيمة تاريخ (ISO أو Date أو رقم زمني) بصيغة الموقع dd/MM/yyyy.
 *
 * تخدم المواضع التي كانت تستدعي `new Date(x).toLocaleDateString(...)` بلغات
 * مختلفة (ar-EG / ar-SA / en-GB / ar) فتباينت الصيغة بين الشاشات. تقبل ما لا
 * يقبله {@link formatDateLocalized} من أشكال (بيانات Firestore القديمة تحفظ
 * التاريخ كـ Date أو رقم)، وتُعيد القيمة كما هي إن تعذّر تفسيرها.
 */
export function formatDateValue(
  value: string | number | Date | null | undefined,
): string {
  if (value == null || value === "") return "";
  if (typeof value === "string") {
    const iso = formatDateLocalized(value);
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(iso)) return iso;
  }
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return typeof value === "string" ? value : "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

/** يحوّل أي قيمة إلى Date صالح، أو null إن تعذّر. `YYYY-MM-DD` تُقرأ كتاريخ
 *  محلي لا UTC — وإلا انزاح اليوم في المناطق الزمنية الموجبة. */
function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value == null || value === "") return null;
  if (typeof value === "string") {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
    if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

const pad2 = (n: number) => String(n).padStart(2, "0");

/**
 * G10-B: الوقت بصيغة 24 ساعة `HH:mm` بأرقام لاتينية.
 *
 * `toLocaleTimeString('ar-EG')` يُخرج أرقاماً هندية (٠١٢…) على الأجهزة التي
 * تحمل بيانات ICU كاملة ولاتينية على غيرها، فيختلف الشكل بين جهاز وآخر.
 */
export function formatTimeValue(
  value: string | number | Date | null | undefined,
): string {
  const d = toDate(value);
  if (!d) return "";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** التاريخ والوقت معاً بصيغة الموقع: `dd/MM/yyyy HH:mm`. */
export function formatDateTimeValue(
  value: string | number | Date | null | undefined,
): string {
  const d = toDate(value);
  if (!d) return typeof value === "string" ? value : "";
  return `${formatDateValue(d)} ${formatTimeValue(d)}`;
}

/** أسماء الأيام ثابتة — لا تعتمد على بيانات ICU في المتصفّح. */
const WEEKDAYS_AR = [
  "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت",
];

/** اسم اليوم بالعربية (الأحد … السبت)، وفارغ لغير القابل للتفسير. */
export function formatWeekdayName(
  value: string | number | Date | null | undefined,
): string {
  const d = toDate(value);
  if (!d) return "";
  return WEEKDAYS_AR[d.getDay()];
}

/** التاريخ الحالي بصيغة ISO المحلية (YYYY-MM-DD) — لا UTC (يتجنّب انزياح اليوم). */
export function todayIso(): string {
  const now = new Date();
  const off = now.getTimezoneOffset();
  return new Date(now.getTime() - off * 60000).toISOString().slice(0, 10);
}
