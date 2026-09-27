import {
  apiDelete,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
  apiPutObject,
} from "./restApi";

/** خطة اشتراك باسمها العربي — من `PLAN_LABELS` في الخادم، لا نسخة هنا. */
export interface PlanChoice {
  key: string;
  label: string;
}

export interface PlatformCompanyRow {
  id: number;
  name: string;
  plan: string;
  plan_label: string;
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
  plan_choices: PlanChoice[];
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
  plan_choices: PlanChoice[];
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

// ── SA-3: حجم استعمال الشركات ──

export interface UsageCounterDef {
  key: string;
  label: string;
  kind: "movement" | "document";
}

export interface UsageCounterValue {
  total: number;
  month: number;
}

export interface CompanyUsageRow {
  counters: Record<string, UsageCounterValue>;
  movements_total: number;
  movements_month: number;
  documents_total: number;
  documents_month: number;
  active_users_30d: number;
  last_document_date: string | null;
}

export interface PlatformUsageResponse {
  /** وقت الحساب — نتيجة المنصة من كاش عشر دقائق، و`refresh` يعيدها الآن. */
  computed_at: string;
  counter_catalog: UsageCounterDef[];
  results: (CompanyUsageRow & { tenant_id: number; name: string })[];
}

export interface CompanyUsageResponse extends CompanyUsageRow {
  computed_at: string;
  counter_catalog: UsageCounterDef[];
  tenant_id: number;
  name: string;
}

export const getPlatformUsage = (refresh = false) =>
  apiGetObject<PlatformUsageResponse>(`platform/usage/${refresh ? "?refresh=1" : ""}`);

export const getPlatformCompanyUsage = (companyId: number) =>
  apiGetObject<CompanyUsageResponse>(`platform/companies/${companyId}/usage/`);

// ── SA-1: سجلّ تدقيق المنصة ──

export type AuditSeverity = "info" | "warning" | "high";

export interface PlatformAuditRow {
  id: number;
  action: string;
  action_label: string;
  severity: AuditSeverity;
  actor_id: number | null;
  actor: string;
  tenant_id: number | null;
  tenant: string;
  target_user_id: number | null;
  target_user: string;
  reason: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  trace_id: string;
  created_at: string;
}

export interface PlatformAuditResponse {
  count: number;
  page: number;
  page_size: number;
  results: PlatformAuditRow[];
  events: { action: string; label: string; severity: AuditSeverity }[];
}

export interface PlatformAuditFilters {
  page?: number;
  tenant?: number | null;
  action?: string;
  severity?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
}

export const listPlatformAudit = (filters: PlatformAuditFilters = {}) => {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return apiGetObject<PlatformAuditResponse>(`platform/audit-log/${query ? `?${query}` : ""}`);
};

// ── SA-2: إذن الدخول للدعم ──

export type SupportScope = "read_only" | "full";
export type SupportGrantStatus =
  "pending" | "active" | "rejected" | "revoked" | "cancelled" | "expired";

export interface SupportAccessGrant {
  id: number;
  tenant_id: number;
  tenant_name: string;
  requested_by_id: number;
  requested_by: string;
  reason: string;
  requested_scope: SupportScope;
  requested_hours: number;
  is_emergency: boolean;
  status: SupportGrantStatus;
  scope: SupportScope | "";
  expires_at: string | null;
  decided_by: string;
  decided_at: string | null;
  decision_note: string;
  revoked_by: string;
  revoked_at: string | null;
  first_used_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export const listCompanySupportAccess = (companyId: number) =>
  apiGetObject<{ results: SupportAccessGrant[] }>(`platform/companies/${companyId}/support-access/`);

export const requestSupportAccess = (
  companyId: number, reason: string, scope: SupportScope, hours: number,
) =>
  apiPostObject<SupportAccessGrant>(
    `platform/companies/${companyId}/support-access/`, { reason, scope, hours });

/** دخولٌ فوريّ بلا انتظار — أربع ساعات، خطورة عالية، والشركة تُبلَّغ فوراً. */
export const emergencySupportAccess = (companyId: number, reason: string) =>
  apiPostObject<SupportAccessGrant>(
    `platform/companies/${companyId}/support-access/`, { reason, emergency: true });

export const listPlatformSupportAccess = (status?: "pending" | "active") =>
  apiGetObject<{ results: SupportAccessGrant[] }>(
    `platform/support-access/${status ? `?status=${status}` : ""}`);

/** إنهاء إذنٍ ساري (خروج) أو سحب طلبٍ معلّق قبل أن تقرّر فيه الشركة. */
export const endSupportAccess = (grantId: number) =>
  apiPostObject<SupportAccessGrant>(`platform/support-access/${grantId}/end/`, {});

// ── أسعار الخطط ──

export interface PlanPricingRow {
  plan_key: string;
  label: string;
  /** أرقام عشرية تصل نصّاً من DRF — تُحوَّل عند العرض. */
  default_price: string;
  override: string | null;
  has_override: boolean;
  effective_price: string;
}

export const listPlanPricing = () =>
  apiGetObject<{ results: PlanPricingRow[] }>("platform/plan-pricing/");

/** مساواة السعر بالافتراض = استعادة (يحذف الخادم التجاوز). */
export const setPlanPricing = (planKey: string, monthlyPrice: string, note = "") =>
  apiPutObject<{ results: PlanPricingRow[] }>(
    "platform/plan-pricing/", { plan_key: planKey, monthly_price: monthlyPrice, note });

// ── SA-9: company creation for a customer + system health ──

export interface CompanyCreationOptions {
  templates: { key: string; label: string }[];
  plans: PlanChoice[];
  default_trial_days: number;
  max_trial_days: number;
}

export interface CompanyCreationInput {
  name: string;
  owner_email: string;
  template: string;
  plan: string;
  trial_days?: number;
  subscription_ends_at?: string;
}

export const getCompanyCreationOptions = () =>
  apiGetObject<CompanyCreationOptions>("platform/companies/");

export const createPlatformCompany = (input: CompanyCreationInput) =>
  apiPostObject<PlatformCompanyRow>("platform/companies/", input as unknown as Record<string, unknown>);

export interface PlatformHealth {
  checked_at: string;
  database: {
    vendor: string;
    ok: boolean;
    ping_ms: number | null;
    size_bytes: number | null;
    largest_tables: { name: string; rows: number; bytes: number }[];
  };
  migrations: { ok: boolean; pending: string[] };
  cache: { ok: boolean; backend: string };
  backup: {
    configured: boolean;
    readable?: boolean;
    latest_file?: string | null;
    latest_at?: string;
    latest_bytes?: number;
    age_hours?: number;
    stale?: boolean;
    file_count?: number;
  };
  storage: { ledger_bytes: number; unattributed_bytes: number };
  heaviest_companies: {
    tenant_id: number;
    name: string;
    movements_total: number;
    documents_total: number;
    storage_bytes: number;
  }[];
  usage_computed_at: string;
  failed_logins_24h: number;
  app: { django: string; python: string; debug: boolean; timezone: string };
}

export const getPlatformHealth = () => apiGetObject<PlatformHealth>("platform/health/");
