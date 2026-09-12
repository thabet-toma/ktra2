/**
 * عميلُ واجهة التوظيف المنصّيّ (#207 م٨-ب).
 *
 * **أسماءُ الحقول أدناه مأخوذةٌ من مُسلسِلات الخادم حرفيّاً** —
 * `platform_ops/serializers.py` (`JobPostingSerializer` · `JobApplicantSerializer` ·
 * `PlatformRecruiterSerializer`) و`platform_ops/public_hiring/serializers.py`. و`tsc` في
 * هذا المستودع لا يفحص شكلَ ما يصل من الشبكة، فحقلٌ مخترَعٌ يُصيَّر فراغاً بلا شكوى؛
 * يحرسها `platform_ops/tests/test_hiring_frontend_contract.py`.
 *
 * الوظائفُ والمتقدّمون **بلا شركة** (استثناءٌ موثَّق)، فلا معرّفَ شركةٍ يُرسَل من هنا.
 */
import {
  API_BASE,
  apiDelete,
  apiGetForBlob,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";

const OPS = "platform/ops";

/** `GET /api/platform-staff/me/` — ما يُظهره الشريطُ الجانبيُّ لغير السوبر أدمن. */
export interface PlatformStaffCapabilities {
  is_platform_admin: boolean;
  is_platform_recruiter: boolean;
  is_platform_employee: boolean;
}

export interface PlatformJobPosting {
  id: number;
  title: string;
  /** التخصّصُ المنصّيُّ الذي يُنسَخ إلى الموظّف عند قبول دعوته. */
  specialty: string;
  description: string;
  requirements: string;
  location: string;
  employment_type: string;
  employment_type_display: string;
  salary_range: string;
  token: string;
  is_open: boolean;
  is_live: boolean;
  expires_at: string | null;
  closed_at: string | null;
  /** رابطُ **الصفحة** العامّة (`/careers/job/<token>`) لا نقطةُ API. */
  public_url: string;
  applicants_count: number;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

/** ما يُكتب عند إنشاء الإعلان أو تعديله. */
export interface PlatformJobPostingDraft {
  title: string;
  specialty: string;
  description: string;
  requirements: string;
  location: string;
  employment_type: string;
  salary_range: string;
  expires_at: string | null;
}

export interface ApplicantNextStatus {
  value: string;
  label: string;
}

export interface PlatformJobApplicant {
  id: number;
  job: number;
  job_title: string;
  name: string;
  phone: string;
  email: string;
  about: string;
  status: string;
  status_display: string;
  rating: number | null;
  notes: string;
  reference_code: string;
  /** **لا `cv_url` هنا ولا في الخادم**: الرابطُ عند المزوّد هو الصلاحية. */
  has_cv: boolean;
  cv_name: string;
  hired_employee: number | null;
  /** الانتقالاتُ المسموحةُ من الحالة الحاليّة — من جدول الخادم الوحيد. */
  next_statuses: ApplicantNextStatus[];
  created_at: string;
  updated_at: string;
}

/** ردُّ إصدار الدعوة — الرابطُ يُعرض **مرّةً واحدة**: الخادمُ لا يحفظ الرمزَ الخام. */
export interface ApplicantInvitation {
  detail: string;
  invitation_id: number;
  token: string;
  invite_url: string;
  expires_at: string;
  applicant_id: number;
}

export interface PlatformRecruiter {
  id: number;
  user: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** `GET /api/careers/jobs/<token>/` — الإعلانُ وحدَه بلا بياناتٍ داخليّة. */
export interface PublicPlatformJob {
  id: number;
  token: string;
  title: string;
  description: string;
  requirements: string;
  location: string;
  employment_type: string;
  employment_type_display: string;
  salary_range: string;
  created_at: string;
}

/** ردُّ التقديم العامّ — مرجعٌ وحالةٌ واسمُ ملفّ، بلا رابط سيرة. */
export interface PublicApplicationReceipt {
  reference_code: string;
  status: string;
  job_title: string;
  cv_name: string;
}

/** `GET /api/careers/invitations/<token>/`. */
export interface PublicInvitationDetail {
  job_title: string;
  applicant_name: string;
  email: string;
  expires_at: string;
}

/** ردُّ قبول الدعوة — الحسابُ أُنشئ الآن لا قبلها. */
export interface InvitationAcceptance {
  detail: string;
  username: string;
  applicant_status: string;
  /** 211-A: جلسةٌ جاهزةٌ يُصدرها القبولُ نفسُه — الرمزُ المهشَّرُ أُثبت واستُهلك للتوّ. */
  token: string;
  user: { id: string; name: string; email: string } & Record<string, unknown>;
}

export const getPlatformStaffCapabilities = () =>
  apiGetObject<PlatformStaffCapabilities>("platform-staff/me/");

export const listPlatformJobs = () =>
  apiGetList<PlatformJobPosting>(`${OPS}/job-postings/`);

export const createPlatformJob = (draft: PlatformJobPostingDraft) =>
  apiPostObject<PlatformJobPosting>(`${OPS}/job-postings/`, {
    ...draft,
    expires_at: draft.expires_at || null,
  });

export const updatePlatformJob = (id: number, draft: PlatformJobPostingDraft) =>
  apiPatchObject<PlatformJobPosting>(`${OPS}/job-postings/${id}/`, {
    ...draft,
    expires_at: draft.expires_at || null,
  });

export const closePlatformJob = (id: number) =>
  apiPostObject<PlatformJobPosting>(`${OPS}/job-postings/${id}/close/`, {});

export const reopenPlatformJob = (id: number) =>
  apiPostObject<PlatformJobPosting>(`${OPS}/job-postings/${id}/reopen/`, {});

/** إبطالُ الرابط العامّ الحاليّ فوراً وتوليدُ غيره. */
export const regeneratePlatformJobLink = (id: number) =>
  apiPostObject<PlatformJobPosting>(`${OPS}/job-postings/${id}/regenerate-link/`, {});

export const listPlatformApplicants = (filter: { job?: number; status?: string } = {}) =>
  apiGetList<PlatformJobApplicant>(`${OPS}/job-applicants/`, {
    query: { job: filter.job, status: filter.status || undefined },
  });

export const transitionPlatformApplicant = (id: number, status: string) =>
  apiPostObject<PlatformJobApplicant>(`${OPS}/job-applicants/${id}/transition-status/`, { status });

export const ratePlatformApplicant = (id: number, payload: { rating?: number; notes?: string }) =>
  apiPostObject<PlatformJobApplicant>(`${OPS}/job-applicants/${id}/rate/`, payload);

export const invitePlatformApplicant = (id: number, expiresInHours: number) =>
  apiPostObject<ApplicantInvitation>(`${OPS}/job-applicants/${id}/invite/`, {
    expires_in_hours: expiresInHours,
  });

/** بايتاتُ السيرة عبر الخادم — رابطُ التخزين لا يصل إلى المتصفّح. */
export const getPlatformApplicantCv = (id: number) =>
  apiGetForBlob(`${OPS}/job-applicants/${id}/cv/`);

export const listPlatformRecruiters = () =>
  apiGetList<PlatformRecruiter>(`${OPS}/recruiters/`);

/**
 * ملفّاتُ السياسة كخياراتٍ لحقل التخصّص — تخصّصُ الإعلان يُنسخ إلى الموظّف ويُطابَق
 * به `PolicyProfile`، فالاختيارُ من الموجود أصدقُ من الكتابة الحرّة. للسوبر أدمن
 * وحدَه: مسؤولُ التوظيف لا يقرأ ملفّاتِ السياسة (`IsPlatformOperationsManager`).
 */
export interface PolicyProfileOption {
  id: number;
  specialty: string;
  name: string;
  is_active: boolean;
}

export const listPolicyProfileOptions = () =>
  apiGetList<PolicyProfileOption>(`${OPS}/policy-profiles/`);

/** إسنادُ الدور لمستخدمٍ مسجَّلٍ باسمه أو بريده — لا يُنشئ حساباً. */
export const assignPlatformRecruiter = (identifier: string) =>
  apiPostObject<PlatformRecruiter>(`${OPS}/recruiters/`, { identifier });

/** إلغاءُ الدور: تعطيلٌ لا حذف. */
export const revokePlatformRecruiter = (id: number) =>
  apiDelete(`${OPS}/recruiters/${id}/`);

/**
 * مساراتُ البوّابة العامّة. تُنادى **بطلبٍ عارٍ** لا بـ`restApi`: ذلك العميلُ يحمل
 * رأسَ المصادقة وشركةَ الجلسة، وهذه صفحاتٌ يفتحها مجهولٌ لا جلسةَ له.
 */
export const publicCareersJobUrl = (token: string) =>
  `${API_BASE}/careers/jobs/${encodeURIComponent(token)}/`;

export const publicCareersApplyUrl = (token: string) =>
  `${API_BASE}/careers/jobs/${encodeURIComponent(token)}/apply/`;

export const publicInvitationUrl = (token: string) =>
  `${API_BASE}/careers/invitations/${encodeURIComponent(token)}/`;

export const publicInvitationAcceptUrl = (token: string) =>
  `${API_BASE}/careers/invitations/${encodeURIComponent(token)}/accept/`;
