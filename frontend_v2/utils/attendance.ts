/**
 * T-HR — دوالّ عرضٍ خالصة للحضور: تنسيق المدد، وعدّاد الجلسة، وشبكة الشهر.
 *
 * **لا حساب مالياً هنا ولا قراراً.** القبول الجغرافي وحدود اليوم والتأخير
 * والإضافي كلّها خادمية (`hr/attendance.py`)؛ ما هنا تحويلُ دقيقةٍ محسوبة إلى
 * نصٍّ يُقرأ، وعدُّ الثواني من لحظةٍ **يرسلها الخادم**.
 *
 * وهي منفصلة عن المكوّن عمداً كي تُختبر بلا متصفّح — نفس سبب `utils/payroll.ts`.
 */

/** «7س 30د» — والصفر يُطبع «0د» ولا يختفي، فالفراغ يُقرأ عطلاً لا صفراً. */
export const formatMinutes = (minutes: number | null | undefined): string => {
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `${rest}د`;
  if (rest === 0) return `${hours}س`;
  return `${hours}س ${rest}د`;
};

/** «2 س 59 د 59 ث» — شكل العدّاد الحيّ كما في تطبيق الخدمة الذاتية. */
export const formatCounter = (totalSeconds: number): string => {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  return `${hours} س ${minutes} د ${seconds} ث`;
};

/**
 * ثواني الجلسة المفتوحة الآن.
 *
 * **الانزياح مقصود**: ساعةُ جهاز الموظف قد تسبق الخادم أو تتأخّر عنه بدقائق،
 * فالعدّ من `since` بساعةٍ محلية يُظهر رقماً كاذباً — أحياناً سالباً. نقيس
 * فرق الخادم عند أول قراءة (`serverNow − since`) ثم نضيف ما مضى محلياً منذ
 * تلك القراءة، فيبقى الرقم صحيحاً مهما انحرفت ساعة الجهاز.
 */
export const sessionSeconds = (
  since: string,
  serverNow: string,
  fetchedAtMs: number,
  nowMs: number,
): number => {
  const sinceMs = Date.parse(since);
  const serverMs = Date.parse(serverNow);
  if (Number.isNaN(sinceMs) || Number.isNaN(serverMs)) return 0;
  const elapsedAtFetch = serverMs - sinceMs;
  const sinceFetch = Math.max(0, nowMs - fetchedAtMs);
  return Math.max(0, Math.floor((elapsedAtFetch + sinceFetch) / 1000));
};

/** «09:00 — 17:00» ومعها الفترة الثانية إن وُجدت. */
export const formatShiftPeriods = (shift: {
  start1: string; end1: string; start2?: string | null; end2?: string | null;
} | null | undefined): string => {
  if (!shift) return "";
  const trim = (value: string) => String(value || "").slice(0, 5);
  const first = `${trim(shift.start1)} — ${trim(shift.end1)}`;
  if (!shift.start2 || !shift.end2) return first;
  return `${first} · ${trim(shift.start2)} — ${trim(shift.end2)}`;
};

/** أيام الشهر كاملةً بصيغة ISO — صفٌّ لكل يوم لا لكل سجل، فتُرى الثغرة. */
export const monthDays = (month: string): string[] => {
  const match = /^(\d{4})-(\d{2})$/.exec(String(month || "").trim());
  if (!match) return [];
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) return [];
  const count = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
  return Array.from({ length: count }, (_, i) =>
    `${match[1]}-${match[2]}-${String(i + 1).padStart(2, "0")}`);
};

/** شهر اليوم بصيغة YYYY-MM بالتقويم المحلي. */
export const currentMonth = (now: Date = new Date()): string =>
  `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

/** لونُ شارة الحالة — الغياب وحده أحمر، والعذر رماديّ لا أخضر ولا أحمر. */
export const statusPillClass = (status: string): string => {
  const base = "inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold";
  switch (status) {
    case "present":
      return `${base} bg-emerald-100 text-emerald-800`;
    case "late":
      return `${base} bg-amber-100 text-amber-900`;
    case "absent":
      return `${base} bg-red-100 text-red-800`;
    case "leave":
    case "holiday":
    case "off":
      return `${base} bg-sky-100 text-sky-800`;
    default:
      return `${base} bg-slate-100 text-slate-700`;
  }
};

/**
 * رسالةُ رفضٍ تُقرأ — ومعها المسافة حين تكون هي السبب.
 *
 * «خارج النطاق» وحدها لا تكفي: الموظف يحتاج أن يعرف كم يبعد وكم مسموح، وإلا
 * وقف يعيد المحاولة من مكانه.
 */
export const rejectMessage = (
  reason: string,
  label: string,
  distanceM?: number | null,
  radiusM?: number | null,
): string => {
  if (reason === "out_of_range" && distanceM != null) {
    const allowed = radiusM != null ? ` (المسموح ${radiusM} م)` : "";
    return `أنت على بعد ${Math.round(distanceM)} م من موقع العمل${allowed} — اقترب وأعد المحاولة.`;
  }
  if (reason === "no_geo") {
    return "لم يصل موقعك الجغرافي — فعّل إذن الموقع في المتصفّح وأعد المحاولة.";
  }
  if (reason === "photo_required") return "هذا الموقع يشترط صورة عند التسجيل.";
  if (reason === "ip_blocked") return "الشبكة التي تستعملها غير مسموحة للتسجيل من هنا.";
  return label || "تعذّر قبول التسجيل.";
};
