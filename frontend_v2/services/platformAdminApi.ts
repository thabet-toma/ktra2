import {
  apiDelete,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";

export interface PlatformCompanyRow {
  id: number;
  name: string;
  plan: string;
  status: "Active" | "Trial" | "Suspended" | string;
  import_enabled: boolean;
  is_example: boolean;
  member_count: number;
  created_at: string;
  /** آخر يوم كتابة مسموح — `null` اشتراك بلا انتهاء. الصيغة YYYY-MM-DD. */
  subscription_ends_at: string | null;
  /** أيام متبقّية بحساب الخادم: 0 = آخر يوم، سالب = منتهٍ، `null` = بلا انتهاء. */
  subscription_days_left: number | null;
  subscription_expired: boolean;
}

/** حدٌّ بلغ استهلاكه عتبة التحذير — يصل مرتَّباً بالأقرب إلى حدّه أولاً. */
export interface PlatformNearLimit {
  key: string;
  label: string;
  usage: number;
  limit: number;
}

/**
 * صفّ الشركة في لوحة المنصة — أوسع من كرت الشركة: أعمدة القياس (تخزين · فروع ·
 * مستندات · آخر نشاط) يبنيها `platform_dashboard` باستعلامات مجمَّعة، ولا يعيدها
 * نداءُ شركةٍ واحدة. لذلك هي نوعٌ مستقلّ لا توسعةٌ لـ`PlatformCompanyRow`.
 */
export interface PlatformDashboardCompanyRow extends PlatformCompanyRow {
  branch_count: number;
  storage_bytes: number;
  storage_asset_count: number;
  /** فواتير **الشهر الجاري** (بيع + شراء) — نافذة الحدّ نفسها، لا إجمالاً تاريخياً. */
  document_count: number;
  last_login_at: string | null;
  last_activity_at: string | null;
  near_limit: PlatformNearLimit[];
}

export interface PlatformIdleCompany {
  id: number;
  name: string;
  last_activity_at: string | null;
}

export interface PlatformStorageCompany {
  id: number;
  name: string;
  storage_bytes: number;
  storage_asset_count: number;
}

export interface PlatformDashboardKpis {
  active_companies: number;
  /** الشركات التي لم يُسجَّل لها أي فعل (غير العرض) منذ `days` يوماً. */
  idle_companies: { days: number; count: number; companies: PlatformIdleCompany[] };
  top_storage: PlatformStorageCompany[];
  /** لكل شركة أسوأ حدودها فقط — الخادم يرسل أوّل صفوف `near_limit` مفرودةً. */
  near_limit_companies: {
    count: number;
    companies: ({ id: number; name: string } & PlatformNearLimit)[];
  };
}

export interface PlatformDashboardData {
  companies: { total: number; active: number; trial: number; suspended: number };
  users: { total: number; active: number };
  memberships: number;
  status_distribution: Record<string, number>;
  plan_distribution: Record<string, number>;
  company_rows: PlatformDashboardCompanyRow[];
  kpis: PlatformDashboardKpis;
  /**
   * `unattributed_bytes` = مجموع صفوف `tenant = NULL` (رفوعات المنصة وما لم
   * يُنسب). **ليست** «غير المنسوب» في تقرير `backfill_tenant_assets` — ذاك
   * إجمالي Cloudinary ناقص السجلّ كلّه. الشاشة تسمّيها باسمها كي لا يعني لفظٌ
   * واحد رقمين.
   */
  storage: { ledger_total_bytes: number; unattributed_bytes: number };
}

export interface PlatformCompanyMember {
  membership_id: number;
  user_id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_default: boolean;
  can_access_import: boolean;
  /** حساب المنصة — الموقوف يُمنع من تسجيل الدخول كلياً. */
  is_active: boolean;
  created_at: string;
}

/** فرع الشركة كما تراه لوحة المنصة — التعريف الكامل مكانه إعدادات الشركة نفسها. */
export interface PlatformCompanyBranch {
  id: number;
  name: string;
  code: string;
}

export interface PlatformCompanyDetail extends PlatformCompanyRow {
  members: PlatformCompanyMember[];
  /** الرئيسي أولاً ثم بالاسم — الترتيب من الخادم، لا تُعاد ترتيبها هنا. */
  branches: PlatformCompanyBranch[];
  storage_bytes: number;
  last_activity_at: string | null;
}

/** صفٌّ من سجل حركة الشركة — أحداث العرض مستبعدة من المصدر. */
export interface PlatformActivityRow {
  timestamp: string;
  user_name: string;
  action: string;
  action_label: string;
  entity_type: string;
  entity_label: string;
  description: string;
}

export interface PlatformCompanyPatch {
  name?: string;
  plan?: string;
  status?: string;
  /** YYYY-MM-DD لتثبيت الانتهاء، أو `null` لجعل الاشتراك بلا تاريخ. */
  subscription_ends_at?: string | null;
  import_enabled?: boolean;
  is_example?: boolean;
}

export interface PlatformSuperAdmin {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  /** مصدر الصلاحية: علم على الحساب يُسحب من هنا، أو بريد مُهيّأ في إعدادات المنصة. */
  source: "flag" | "settings";
  removable: boolean;
}

export type DevelopmentNoteStatus = "todo" | "in_progress" | "done";
export type DevelopmentNotePriority = "low" | "medium" | "high";

/** صورة توضيحية للملاحظة — الرابط من ‎/api/media/upload/‎ لا محتوى مخزَّن. */
export interface DevelopmentNoteImage {
  url: string;
  caption: string;
}

/** ردّ على ملاحظة — نقاشٌ مؤرَّخ بجانبها، يُكتب ويُحذف بنداء مستقلّ عن حفظها. */
export interface DevelopmentNoteComment {
  id: number;
  body: string;
  created_by: number | null;
  created_by_name: string;
  created_at: string;
}

export interface DevelopmentNote {
  id: number;
  title: string;
  description: string;
  status: DevelopmentNoteStatus;
  priority: DevelopmentNotePriority;
  images: DevelopmentNoteImage[];
  due_date: string | null;
  /** لحظة الإنجاز — يختمها الخادم عند الانتقال لـdone، و`null` للمكتملة قبل الميزة. */
  completed_at: string | null;
  created_by: number | null;
  created_by_name: string;
  updated_by: number | null;
  updated_by_name: string;
  created_at: string;
  updated_at: string;
  comments: DevelopmentNoteComment[];
}

export type DevelopmentNoteWrite = Pick<
  DevelopmentNote,
  "title" | "description" | "status" | "priority" | "images" | "due_date"
>;

export const getPlatformDashboard = () =>
  apiGetObject<PlatformDashboardData>("platform/dashboard/");

export const listSuperAdmins = () =>
  apiGetObject<PlatformSuperAdmin[]>("platform/super-admins/");

/** ترقية مستخدم مسجَّل (باسمه أو بريده) — لا تُنشئ حساباً ولا تمسّ كلمة سر. */
export const grantSuperAdmin = (identifier: string) =>
  apiPostObject<PlatformSuperAdmin>("platform/super-admins/", { identifier });

export const revokeSuperAdmin = (id: number) =>
  apiDelete(`platform/super-admins/${id}/`);

/** كرت الشركة في لوحة المنصة — بياناتها وأعضاؤها في نداء واحد. */
export const getPlatformCompany = (id: number) =>
  apiGetObject<PlatformCompanyDetail>(`platform/companies/${id}/`);

/**
 * آخر مئة حركة للشركة — نداء مستقلّ عن كرت الشركة عمداً: اللوحة تفتح على ثلاثة
 * نداءات أصلاً، وقائمةُ مئةِ صفٍّ لا يطلبها القارئ في كل فتحة تُحمَّل عند طلبها.
 */
export const getPlatformCompanyActivity = (id: number) =>
  apiGetObject<{ results: PlatformActivityRow[] }>(`platform/companies/${id}/activity/`);

export const updatePlatformCompany = (id: number, patch: PlatformCompanyPatch) =>
  apiPatchObject<PlatformCompanyRow>(`platform/companies/${id}/`, { ...patch });

export const addPlatformCompanyMember = (id: number, identifier: string, role: string) =>
  apiPostObject<PlatformCompanyMember>(`platform/companies/${id}/members/`, { identifier, role });

export const updatePlatformCompanyMember = (
  id: number,
  membershipId: number,
  patch: { role?: string; can_access_import?: boolean },
) =>
  apiPatchObject<PlatformCompanyMember>(
    `platform/companies/${id}/members/${membershipId}/`, { ...patch });

export const removePlatformCompanyMember = (id: number, membershipId: number) =>
  apiDelete(`platform/companies/${id}/members/${membershipId}/`);

/** إيقاف/تفعيل حساب على مستوى المنصة — لا يمسّ العضويات ولا البيانات. */
export const setPlatformUserActive = (userId: number, isActive: boolean) =>
  apiPostObject<{ id: number; username: string; is_active: boolean }>(
    `platform/users/${userId}/set-active/`, { is_active: isActive });

/** T-EXTACCT: ترخيص الوحدات لكل شركة — سوبر أدمن فقط. */
export interface PlatformModuleRow {
  module_key: string;
  label: string;
  plans: string[];
  /** هل تشمل خطة الشركة هذه الوحدة؟ الترخيص يبقى يدوياً، والعَلَم يُظهر التعارض. */
  plan_allows?: boolean;
  legacy: boolean;
  enabled: boolean;
  plan_note: string;
  enabled_at: string | null;
}

export const listCompanyModules = (companyId: number) =>
  apiGetObject<{ results: PlatformModuleRow[] }>(`platform/companies/${companyId}/modules/`);

export const setCompanyModule = (
  companyId: number,
  moduleKey: string,
  enabled: boolean,
  planNote = "",
) =>
  apiPostObject<{ module_key: string; enabled: boolean; plan_note: string }>(
    `platform/companies/${companyId}/modules/`,
    { module_key: moduleKey, enabled, plan_note: planNote },
  );

/** T-PLANLIMITS: حدود خطة الشركة — الافتراضي من الخطة، والتجاوز لهذه الشركة. */
export interface PlatformLimitRow {
  key: string;
  label: string;
  unit: string;
  period: "month" | "total" | string;
  period_label: string;
  /** حدّ الخطة — null = بلا حدّ. */
  plan_default: number | null;
  /** تجاوز الشركة (null مع has_override=true يعني «بلا حدّ» صراحةً). */
  override: number | null;
  has_override: boolean;
  effective: number | null;
  usage: number;
}

export interface PlatformLimitsResponse {
  plan: string;
  results: PlatformLimitRow[];
}

export const listCompanyLimits = (companyId: number) =>
  apiGetObject<PlatformLimitsResponse>(`platform/companies/${companyId}/limits/`);

/** يضبط حدّاً (رقم أو null = بلا حدّ) أو يستعيد افتراضي الخطة بـreset. */
export const setCompanyLimit = (
  companyId: number,
  limitKey: string,
  value: { max_value: number | null } | { reset: true },
  note = "",
) =>
  apiPostObject<PlatformLimitsResponse>(
    `platform/companies/${companyId}/limits/`,
    { limit_key: limitKey, note, ...value },
  );

export interface PlatformAccountantProfile {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  professional_type: string;
  license_number: string;
  license_authority: string;
  tax_registration_number: string;
  business_address: string;
  phone: string;
  email_verified: boolean;
  verification_status: string;
  rejection_reason: string;
  barred_until: string | null;
  created_at: string;
}

/** يفتح لسوبر أدمن واجهة المحاسب القانوني كاملةً: ملف مهني + مكتب + ترخيص. */
export const openAccountantWorkspace = () =>
  apiPostObject<{
    profile: PlatformAccountantProfile;
    office: { tenant_id: number; name: string };
    profile_created: boolean;
    office_created: boolean;
  }>("platform/accountant-workspace/", {});

export const listPendingAccountants = () =>
  apiGetObject<{ results: PlatformAccountantProfile[]; count: number }>(
    "platform/accountants/pending/",
  );

export const verifyAccountant = (
  profileId: number,
  decision: "approve" | "reject" | "bar",
  reason = "",
) =>
  apiPostObject<PlatformAccountantProfile>(
    `platform/accountants/${profileId}/verify/`, { decision, reason });

export const listDevelopmentNotes = () =>
  apiGetObject<DevelopmentNote[]>("platform/development-notes/");

export const createDevelopmentNote = (note: DevelopmentNoteWrite) =>
  apiPostObject<DevelopmentNote>("platform/development-notes/", { ...note });

export const updateDevelopmentNote = (id: number, note: Partial<DevelopmentNoteWrite>) =>
  apiPatchObject<DevelopmentNote>(`platform/development-notes/${id}/`, { ...note });

export const deleteDevelopmentNote = (id: number) =>
  apiDelete(`platform/development-notes/${id}/`);

/** يعيد الردّ المُنشأ وحده — الشاشة تضيفه محلياً بلا إعادة تحميل الملاحظات. */
export const addDevelopmentNoteComment = (noteId: number, body: string) =>
  apiPostObject<DevelopmentNoteComment>(
    `platform/development-notes/${noteId}/comments/`, { body });

export const deleteDevelopmentNoteComment = (noteId: number, commentId: number) =>
  apiDelete(`platform/development-notes/${noteId}/comments/${commentId}/`);
