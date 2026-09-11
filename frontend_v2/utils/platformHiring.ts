/**
 * دوالٌّ خالصةٌ لواجهة التوظيف المنصّيّ واستهلاك الباقة (#207 م٨).
 *
 * بلا شبكةٍ ولا متصفّح — تُختبَر بـ`node --test`، وهي بوّابةُ الواجهة الوحيدة هنا.
 * والقيودُ المنسوخةُ أدناه (حجمُ السيرة وامتداداتُها وطولُ كلمة المرور) **تنبيهٌ قبل
 * الإرسال لا حكم**: الحكمُ للخادم، ونسخُها هنا يوفّر على المتقدّم رفعَ خمسة ميجا
 * ليُقال له بعدها إنّها أكبرُ من المسموح.
 */
import { formatNumber } from './formatNumber.ts';

/** مرآةُ `MAX_CV_BYTES` في `platform_ops/public_hiring/cv_validation.py`. */
export const MAX_CV_BYTES = 5 * 1024 * 1024;

/** مرآةُ `ALLOWED_CV_EXTENSIONS` في الملفّ نفسِه. */
export const ACCEPTED_CV_EXTENSIONS = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.webp'] as const;

/** قيمةُ `accept` لحقل الملفّ — من القائمة نفسِها لا نصٌّ ثانٍ يتباعد عنها. */
export const CV_ACCEPT_ATTRIBUTE = ACCEPTED_CV_EXTENSIONS.join(',');

/** مرآةُ `min_length=8` في `AcceptInvitationInputSerializer`. */
export const MIN_PASSWORD_LENGTH = 8;

/**
 * خيارات حالات المتقدمين للوظائف لمطابقة choices في Backend (م٨).
 */
export const APPLICANT_STATUS_OPTIONS = [
  { value: 'new', label: 'جديد' },
  { value: 'screening', label: 'فرز أولي' },
  { value: 'interview', label: 'مقابلة' },
  { value: 'offered', label: 'عرض عمل' },
  { value: 'hired', label: 'مقبول' },
  { value: 'rejected', label: 'مرفوض' },
] as const;

/**
 * خيارات أنواع الدوام لمطابقة choices في Backend (م٨).
 */
export const EMPLOYMENT_TYPE_OPTIONS = [
  { value: 'full_time', label: 'دوام كامل' },
  { value: 'part_time', label: 'دوام جزئي' },
  { value: 'contract', label: 'عقد' },
  { value: 'temporary', label: 'مؤقت' },
] as const;

/**
 * مشكلةُ ملفّ السيرة قبل رفعه، أو `null` إن بدا سليماً.
 * الامتدادُ أوّلاً: ملفٌّ من نوعٍ مرفوضٍ لا يعني حجمُه شيئاً.
 */
export function cvFileProblem(file: { name: string; size: number } | null | undefined): string | null {
  if (!file) return null;
  const name = String(file.name || '').trim().toLowerCase();
  const dot = name.lastIndexOf('.');
  const extension = dot > 0 ? name.slice(dot) : '';
  if (!(ACCEPTED_CV_EXTENSIONS as readonly string[]).includes(extension)) {
    return 'نوع الملف غير مسموح. المسموح: PDF أو Word أو صورة.';
  }
  if (!(file.size > 0)) {
    return 'الملف فارغ.';
  }
  if (file.size > MAX_CV_BYTES) {
    return `حجم السيرة الذاتية يتجاوز الحد المسموح (${formatNumber(5)} ميجابايت).`;
  }
  return null;
}

/** مشكلةُ كلمة المرور وتأكيدِها عند قبول الدعوة، أو `null`. */
export function passwordProblem(password: string, confirmation: string): string | null {
  if (String(password || '').length < MIN_PASSWORD_LENGTH) {
    return `كلمة المرور يجب ألّا تقل عن ${formatNumber(MIN_PASSWORD_LENGTH)} محارف.`;
  }
  if (password !== confirmation) {
    return 'كلمتا المرور غير متطابقتين.';
  }
  return null;
}

/**
 * أوّلُ رسالةٍ مقروءةٍ من جسم خطأ DRF — `{detail}` أو `{field: [msg]}` أو `[msg]`.
 *
 * الصفحاتُ العامّةُ تنادي الخادمَ بطلبٍ عارٍ لا بـ`restApi` (لا جلسةَ لزائرٍ مجهول)،
 * فلا تمرّ بمستخرِج أخطاء العميل. وإظهارُ «تعذّر الإرسال» وحدَها يُخفي عن المتقدّم
 * أنّ بريدَه بصيغةٍ خاطئة.
 */
export function firstApiErrorMessage(body: unknown, fallback: string): string {
  if (typeof body === 'string') {
    return body.trim() || fallback;
  }
  if (Array.isArray(body)) {
    for (const item of body) {
      const message = firstApiErrorMessage(item, '');
      if (message) return message;
    }
    return fallback;
  }
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === 'string' && record.detail.trim()) {
      return record.detail.trim();
    }
    for (const value of Object.values(record)) {
      const message = firstApiErrorMessage(value, '');
      if (message) return message;
    }
  }
  return fallback;
}

const APPLICANT_STATUS_BADGE: Record<string, string> = {
  new: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-800',
  screening: 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800',
  interview: 'bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-800',
  offered: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800',
  hired: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800',
  rejected: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800',
};

const NEUTRAL_BADGE = 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700';

/**
 * لونُ شارة حالة المتقدّم. **النصُّ من الخادم** (`status_display`) — هذه ألوانٌ لا
 * تسميات، وحالةٌ جديدةٌ لا يعرفها الجدولُ تُعرض محايدةً لا تختفي.
 */
export function applicantStatusBadgeClass(status: string | null | undefined): string {
  return APPLICANT_STATUS_BADGE[String(status || '')] ?? NEUTRAL_BADGE;
}


export interface ApplicantFilterable {
  name?: string;
  phone?: string;
  email?: string;
  reference_code?: string;
}

/**
 * تصفيةٌ محليةٌ لصفوف المتقدمين بالبحث في الاسم أو الهاتف أو البريد أو رمز المرجع.
 */
export function filterPlatformApplicants<T extends ApplicantFilterable>(rows: T[], query: string): T[] {
  const q = (query || "").trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((applicant) => {
    const name = String(applicant.name || "").toLowerCase();
    const phone = String(applicant.phone || "").toLowerCase();
    const email = String(applicant.email || "").toLowerCase();
    const ref = String(applicant.reference_code || "").toLowerCase();
    return name.includes(q) || phone.includes(q) || email.includes(q) || ref.includes(q);
  });
}

