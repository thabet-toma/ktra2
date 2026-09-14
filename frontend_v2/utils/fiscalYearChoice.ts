/**
 * #213-أ — السنة المالية المختارة عند إنشاء شركة (مرآة `tenants/services.py`).
 *
 * شركة بلا فترة مالية تبدو سليمة حتى أول ترحيل، ثم تُردّ بـ«لا توجد فترة مالية
 * مفتوحة تغطي التاريخ …». الخادم صار يزرعها دائماً، وما تختاره الشاشة هو
 * **السنة وتفصيلها** لا وجودهما — فلا زرّ «بلا فترة» هنا عمداً.
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

/** السنة المعروضة افتراضاً: سنة اليوم. */
export const currentFiscalYear = (now: Date = new Date()): number => now.getFullYear();

/** هل السنة المكتوبة صالحة للإرسال؟ نصّ الحقل يصل رقماً أو فارغاً. */
export const isValidFiscalYear = (value: number | string): boolean => {
  const year = typeof value === 'number' ? value : Number(String(value).trim());
  return Number.isInteger(year) && year >= MIN_FISCAL_YEAR && year <= MAX_FISCAL_YEAR;
};

/** رسالة الرفض الموحّدة — نصّ واحد لا يفترق بين الشاشتين. */
export const FISCAL_YEAR_RANGE_MESSAGE =
  `السنة المالية يجب أن تقع بين ${MIN_FISCAL_YEAR} و${MAX_FISCAL_YEAR}.`;
