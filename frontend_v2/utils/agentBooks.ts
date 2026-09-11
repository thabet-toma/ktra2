/**
 * أدوات مساعدة ونصوص نقية لشاشة «من يمسك دفاتري» والتقييم اليومي (م٧).
 *
 * دوال نقية 100% بدون أي وصول للشبكة أو بيئة المتصفح،
 * متوافقة مع متطلبات node --test في frontend_v2.
 */
import { formatNumber } from './formatNumber.ts';

export interface HealthStatusMeta {
  label: string;
  colorClass: string;
  bgClass: string;
  borderClass: string;
}

/**
 * درجتا الصحّة كما يبنيهما `platform_ops/services.py` (`calculate_two_health_scores`)
 * — **بأسماء مفاتيحه حرفيّاً**. السطحان (`/api/my-agent/` و`/api/platform/ops/…/health/`)
 * يعيدان هذا الشكل نفسَه من الدالّة نفسِها، فالنوع هنا مرّةً واحدةً لا مرّتين.
 *
 * ولا `status_display` فيه: التسميةُ العربيّةُ من `getHealthStatusMeta` أدناه.
 */
export interface HealthCauseItem {
  reason_key: string;
  label: string;
  count: number;
  deduction: number;
}

export interface HealthScoreDimension {
  score: number;
  status: "excellent" | "good" | "needs_attention" | string;
  top_reasons: string[];
  breakdown: HealthCauseItem[];
}

export interface TwoHealthScores {
  service_health: HealthScoreDimension;
  customer_cooperation: HealthScoreDimension;
  ratings_sample: {
    size: number;
    min_sample_size: number;
    counts_against_score: boolean;
  };
  rework_diagnostic: {
    cancelled_work_orders: number;
    counts_against_score: boolean;
  };
}

/**
 * تحديد مظهر وشارة حالة درجة الصحة (صحة الخدمة أو تعاون الزبون).
 */
export function getHealthStatusMeta(status: string | null | undefined): HealthStatusMeta {
  switch (status) {
    case 'excellent':
      return {
        label: 'ممتاز',
        colorClass: 'text-emerald-700 dark:text-emerald-300',
        bgClass: 'bg-emerald-50 dark:bg-emerald-950/40',
        borderClass: 'border-emerald-200 dark:border-emerald-800',
      };
    case 'good':
      return {
        label: 'جيد',
        colorClass: 'text-blue-700 dark:text-blue-300',
        bgClass: 'bg-blue-50 dark:bg-blue-950/40',
        borderClass: 'border-blue-200 dark:border-blue-800',
      };
    case 'needs_attention':
      return {
        label: 'يحتاج انتباه',
        colorClass: 'text-amber-700 dark:text-amber-300',
        bgClass: 'bg-amber-50 dark:bg-amber-950/40',
        borderClass: 'border-amber-200 dark:border-amber-800',
      };
    default:
      return {
        label: 'غير محدد',
        colorClass: 'text-slate-600 dark:text-slate-400',
        bgClass: 'bg-slate-50 dark:bg-slate-800/40',
        borderClass: 'border-slate-200 dark:border-slate-700',
      };
  }
}

/**
 * التحقق مما إذا كانت النجمة ممتلئة أم فارغة بناءً على التقييم الحالي.
 */
export function isStarFilled(starIndex: number, currentRating: number | null | undefined): boolean {
  if (currentRating == null || typeof currentRating !== 'number' || isNaN(currentRating)) {
    return false;
  }
  if (starIndex < 1) {
    return false;
  }
  return currentRating >= starIndex;
}

/**
 * هل يبقى للتقييم المسجَّل حقُّ تعديلٍ؟ التعديل مرّةً واحدة (§١٠).
 *
 * والصفحةُ العامّة لا تستدعيها: هناك يحسب الخادمُ `can_edit` بنفسه ويرسله، فقراءةُ
 * جوابه أصدقُ من إعادة حسابه. (وسيطٌ ثالثٌ «صريح» كان يتجاوز القاعدةَ كلَّها ولا
 * يستدعيه أحدٌ سوى اختباره — أُسقط.)
 */
export function canEditRating(alreadyRated: boolean, editedOnce: boolean): boolean {
  return Boolean(alreadyRated && !editedOnce);
}

/**
 * نص تنبيه تجاوز سقف سجل النشاط المعروض.
 */
export function formatActivityCountNotice(total: number, cap: number): string | null {
  if (typeof total !== 'number' || typeof cap !== 'number') {
    return null;
  }
  if (total > cap) {
    return `تُعرَض آخرُ ${formatNumber(cap)} حركةٍ من أصل ${formatNumber(total)}`;
  }
  return null;
}

/**
 * صياغة تنبيه حجم عينة التقييم (هل تحتسب في أداء الموظف أم للإرشاد فقط).
 */
export function formatRatingSampleNotice(
  size: number,
  minSample: number,
  countsAgainstScore?: boolean,
): string {
  const isSufficient = typeof countsAgainstScore === 'boolean' ? countsAgainstScore : size >= minSample;
  // **«درجة صحّة الخدمة» لا «تقييم الموظف»**: هذا الحدُّ حدُّ الشركة
  // (`RATING_HEALTH_MIN_SAMPLE`) ويقرّر دخولَ التقييمات في درجة الصحّة المعروضة
  // هنا. أمّا دخولُها أداءَ الموظف فحدُّه من `PolicyProfile` وقد يختلف — فنصٌّ
  // يَعِد بغير ما يقيسه يكذب على الزبون.
  if (isSufficient) {
    return `العينة مكتملة (${formatNumber(size)} من أصل ${formatNumber(minSample)} كحد أدنى) ومحتسبة في درجة صحة الخدمة.`;
  }
  return `العينة غير مكتملة (${formatNumber(size)} من أصل ${formatNumber(minSample)} كحد أدنى) — التقييمات لا تدخل درجة صحة الخدمة بعد.`;
}

/**
 * صياغة تنبيه إعادة العمل التشخيصي عند وجود أوامر عمل ملغاة.
 */
export function formatReworkDiagnosticNotice(cancelledCount: number): string | null {
  if (typeof cancelledCount !== 'number' || cancelledCount <= 0) {
    return null;
  }
  return `تنبيه تشخيصي (لا يُخصَم من الدرجة): ${formatNumber(cancelledCount)} أمر عمل ملغى رُصد.`;
}
