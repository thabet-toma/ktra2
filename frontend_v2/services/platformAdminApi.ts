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
}

export interface PlatformDashboardData {
  companies: { total: number; active: number; trial: number; suspended: number };
  users: { total: number; active: number };
  memberships: number;
  status_distribution: Record<string, number>;
  plan_distribution: Record<string, number>;
  company_rows: PlatformCompanyRow[];
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

export interface PlatformCompanyDetail extends PlatformCompanyRow {
  members: PlatformCompanyMember[];
}

export interface PlatformCompanyPatch {
  name?: string;
  plan?: string;
  status?: string;
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
