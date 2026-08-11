import { resolveTenantId } from "../utils/tenantContext";
import { apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";

const tid = () => resolveTenantId();

/**
 * T-PERM: محرّك الصلاحيات. الخادم هو المرجع (core/access.py) — هذه الأعلام
 * للعرض فقط (إخفاء الأزرار)؛ كل إجراء محميّ يُفرض ثانيةً على الـ endpoint.
 */
export type PermissionEntry = { key: string; label: string; group: string };

export type MyPermissions = {
  role: string;
  is_manager: boolean;
  permissions: string[];
  /** T-EXTACCT: ترخيص الوحدات لهذه الشركة — حقل واحد يخدم كل الوحدات. */
  modules?: Record<string, boolean>;
};

export type PermissionsMatrix = {
  roles: { key: string; label: string }[];
  permissions: PermissionEntry[];
  defaults: Record<string, string[]>;
  matrix: Record<string, Record<string, boolean>>;
};

export async function getMyPermissions(): Promise<MyPermissions> {
  return apiGetObject("permissions/me/", { tenantId: tid() });
}

export async function getPermissionsMatrix(): Promise<PermissionsMatrix> {
  return apiGetObject("permissions/matrix/", { tenantId: tid() });
}

export async function savePermissionsMatrix(
  changes: { role: string; permission_key: string; allowed: boolean }[],
): Promise<PermissionsMatrix> {
  return apiPatchObject("permissions/matrix/", { changes }, { tenantId: tid() });
}

export async function resetPermissionsMatrix(): Promise<PermissionsMatrix> {
  return apiPostObject("permissions/matrix/reset/", {}, { tenantId: tid() });
}

/** عضو الشركة كما تعرضه شاشة الصلاحيات: دوره + تجاوزاته الفردية + الفعلي. */
export type PermissionMember = {
  membership_id: number;
  user_id: number;
  name: string;
  email: string;
  role: string;
  /** المفاتيح المتجاوَزة فردياً فقط (منح=true / منع=false). */
  overrides: Record<string, boolean>;
  effective: string[];
  /** يملك كل مفاتيح الكتالوج فعلياً — مشتقّ على الخادم لا مخزَّن. */
  grant_all: boolean;
};

export async function getPermissionMembers(): Promise<PermissionMember[]> {
  return apiGetList("permissions/members/", { tenantId: tid() });
}

/**
 * تغيير دور العضو من داخل شاشة الصلاحيات. يُعاد استخدام منفذ إدارة الأعضاء
 * القائم (فيه حماية «آخر مدير») بدل تكرار منطقه — يتطلب `admin.members.manage`.
 */
export async function changeMemberRole(
  membershipId: number,
  role: string,
): Promise<{ membership_id: number; role: string }> {
  return apiPostObject(
    `tenants/companies/${tid()}/members/change-role/`,
    { membership_id: membershipId, role },
    { tenantId: tid() },
  );
}

/** `allowed: null` يحذف التجاوز فيعود العضو لما يمليه دوره. */
export async function saveMemberPermissions(
  membershipId: number,
  changes: { permission_key: string; allowed: boolean | null }[],
): Promise<PermissionMember> {
  return apiPatchObject(
    "permissions/member/",
    { membership_id: membershipId, changes },
    { tenantId: tid() },
  );
}

/**
 * منح العضو **كل** الصلاحيات بخانة واحدة، أو إعادته لما يمليه دوره (`false`
 * يحذف كل تجاوزاته الفردية). الدور لا يتبدّل في الحالتين.
 */
export async function setMemberGrantAll(
  membershipId: number,
  grantAll: boolean,
): Promise<PermissionMember> {
  return apiPatchObject(
    "permissions/member/",
    { membership_id: membershipId, grant_all: grantAll },
    { tenantId: tid() },
  );
}
