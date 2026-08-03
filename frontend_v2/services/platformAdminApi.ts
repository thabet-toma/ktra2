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

export interface DevelopmentNote {
  id: number;
  title: string;
  description: string;
  status: DevelopmentNoteStatus;
  priority: DevelopmentNotePriority;
  assignee: string;
  due_date: string | null;
  position: number;
  created_by: number | null;
  created_by_name: string;
  updated_by: number | null;
  updated_by_name: string;
  created_at: string;
  updated_at: string;
}

export type DevelopmentNoteWrite = Pick<
  DevelopmentNote,
  "title" | "description" | "status" | "priority" | "assignee" | "due_date" | "position"
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

export const listDevelopmentNotes = () =>
  apiGetObject<DevelopmentNote[]>("platform/development-notes/");

export const createDevelopmentNote = (note: DevelopmentNoteWrite) =>
  apiPostObject<DevelopmentNote>("platform/development-notes/", { ...note });

export const updateDevelopmentNote = (id: number, note: Partial<DevelopmentNoteWrite>) =>
  apiPatchObject<DevelopmentNote>(`platform/development-notes/${id}/`, { ...note });

export const deleteDevelopmentNote = (id: number) =>
  apiDelete(`platform/development-notes/${id}/`);
