/**
 * #213-أ — السنة المالية المختارة عند إنشاء شركة (مرآة `tenants/services.py`).
 *
 * شركة بلا فترة مالية تبدو سليمة حتى أول ترحيل، ثم تُردّ بـ«لا توجد فترة مالية
 * مفتوحة تغطي التاريخ …». الخادم صار يزرعها دائماً، وما تختاره الشاشة هو
 * **تاريخ بدئها وتفصيلها** لا وجودهما — فلا زرّ «بلا فترة» هنا عمداً.
 *
 * والبدء **من أيّ تاريخ** لا من كانون الثاني وحده: سنةٌ مالية تبدأ في تموز
 * خيارٌ قياسي (Odoo · Xero · Zoho Books). الافتراض المعبّأ أمام المنشئ هو أول
 * كانون الثاني من السنة الجارية، ويغيّره إن شاء قبل الإنشاء.
 *
 * الحدّان `MIN_FISCAL_YEAR`/`MAX_FISCAL_YEAR` نسخة مطابقة لما يفرضه الخادم:
 * الغرض منع الغلط المطبعيّ (202 أو 20266) قبل رحلة الشبكة، لا استبدال تحقّقه.
 */

export type FiscalGranularity = 'monthly' | 'yearly';

export const MIN_FISCAL_YEAR = 2000;
export const MAX_FISCAL_YEAR = 2100;

export const DEFAULT_FISCAL_GRANULARITY: FiscalGranularity = 'monthly';

export type FiscalGranularityOption = {
  key: FiscalGranularity;
  name: string;
  description: string;
};

export const FISCAL_GRANULARITY_OPTIONS: readonly FiscalGranularityOption[] = [
  {
    key: 'monthly',
    name: 'شهرية',
    description: 'اثنتا عشرة فترة — تُقفل شهراً بعد شهر.',
  },
  {
    key: 'yearly',
    name: 'سنوية',
    description: 'فترة واحدة للسنة كلها — القفل كل شيء أو لا شيء.',
  },
];

/**
 * التاريخ المعبّأ افتراضاً: **أول كانون الثاني من السنة الجارية** بصيغة
 * `YYYY-MM-DD` — وهي الصيغة التي يقبلها `<input type="date">` ويقرؤها الخادم.
 *
 * يُبنى من مكوّنات التاريخ المحلّي لا من `toISOString()`: الأخيرة تحوّل إلى UTC
 * فتُرجع كانون الأول من السنة السابقة لمن كان في منطقة زمنية موجبة أول السنة.
 */
export const defaultFiscalStart = (now: Date = new Date()): string =>
  `${now.getFullYear()}-01-01`;

/** هل التاريخ المكتوب صالح للإرسال؟ الحقل يصل نصّاً أو فارغاً. */
export const isValidFiscalStart = (value: string): boolean => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value).trim());
  if (!match) return false;
  const [, year, month, day] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day));
  // تاريخٌ يطابق الشكل ويستحيل تقويمياً (2026-02-31) يُردّ هنا لا عند الخادم.
  if (
    parsed.getFullYear() !== Number(year) ||
    parsed.getMonth() !== Number(month) - 1 ||
    parsed.getDate() !== Number(day)
  ) {
    return false;
  }
  return Number(year) >= MIN_FISCAL_YEAR && Number(year) <= MAX_FISCAL_YEAR;
};

/**
 * بدايةُ السنة التالية: **اليوم الذي يلي آخرَ فترةٍ قائمة** — أي إكمالُ إيقاع
 * الشركة لا افتراضُ كانون الثاني، فشركةٌ سنتُها تموزيّة تُنشئ سنتها الثانية
 * بضغطة واحدة. وبلا فتراتٍ بعد، الافتراضُ أول كانون الثاني كما في باب الإنشاء.
 */
export const nextFiscalStart = (periodEnds: string[], now: Date = new Date()): string => {
  const last = periodEnds.filter((end) => isValidFiscalStart(end)).sort().pop();
  if (!last) return defaultFiscalStart(now);
  // `new Date('2040-06-30')` وحدَه يُقرأ UTC، ومع الوقت يُقرأ محلّياً — والفرق
  // يومٌ كامل لمن كان في منطقةٍ زمنيّةٍ سالبة.
  const day = new Date(`${last}T00:00:00`);
  day.setDate(day.getDate() + 1);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
};

/** رسالة الرفض الموحّدة — نصّ واحد لا يفترق بين الشاشتين. */
export const FISCAL_START_MESSAGE =
  `تاريخ بداية السنة المالية يجب أن يكون تاريخاً صالحاً بين ${MIN_FISCAL_YEAR} و${MAX_FISCAL_YEAR}.`;
