/**
 * دوالٌّ خالصةٌ لواجهة التوظيف المنصّيّ واستهلاك الباقة (#207 م٨).
 *
 * بلا شبكةٍ ولا متصفّح — تُختبَر بـ`node --test`، وهي بوّابةُ الواجهة الوحيدة هنا.
 * والقيودُ المنسوخةُ أدناه (حجمُ السيرة وامتداداتُها وطولُ كلمة المرور) **تنبيهٌ قبل
 * الإرسال لا حكم**: الحكمُ للخادم، ونسخُها هنا يوفّر على المتقدّم رفعَ خمسة ميجا
 * ليُقال له بعدها إنّها أكبرُ من المسموح.
 */

import type { CcTone } from './ccTone.ts';
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

const APPLICANT_STATUS_TONE: Record<string, CcTone> = {
  new: 'accent',
  screening: 'violet',
  interview: 'violet',
  offered: 'warning',
  hired: 'success',
  rejected: 'danger',
};

/**
 * نغمةُ حالة المتقدّم. **النصُّ من الخادم** (`status_display`) — هذه نغمةٌ لا
 * تسمية، وحالةٌ جديدةٌ لا يعرفها الجدولُ تُعرض محايدةً لا تختفي.
 *
 * كانت هنا `applicantStatusBadgeClass` تُرجع أصنافاً **فاتحةً** (`bg-sky-50
 * text-sky-700`) بلواحق `dark:` — عقدَ شاشةٍ ثنائيّةِ القشرة. ولمّا دخلت شاشاتُ
 * التوظيف الغلافَ الداكنَ صارت تلك الشاراتُ رقعاً باهتةً على الكحليّ، والحالةُ
 * الواحدةُ يلبسها لونان: رقاقةٌ داكنةٌ في تبويب المتقدّمين وشارةٌ فاتحةٌ في شبكة
 * الحضور. **ولا يمسك ذلك حارسُ أصنافٍ ساكن**: اللونُ يأتي من دالّةٍ لا من سلسلةٍ
 * حرفيّةٍ في `className`. فصار المصدرُ نغمةً واحدةً تقرؤها `CcPill`.
 */
export function applicantStatusTone(status: string | null | undefined): CcTone {
  return APPLICANT_STATUS_TONE[String(status || '')] ?? 'neutral';
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

