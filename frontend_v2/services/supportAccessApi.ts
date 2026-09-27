/**
 * SA-8 — جهة الشركة من إذن دخول فريق كترا: تراه وتوافق (وقد تقصّر المدة أو
 * تخفّض النطاق) وترفض وتسحب. الصلاحية في الخادم `admin.members.manage`.
 */
import { apiGetObject, apiPostObject } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";
import type { SupportAccessGrant, SupportScope } from "./platformAdminApi";

export type { SupportAccessGrant, SupportScope };

export interface CompanySupportAccessList {
  pending: SupportAccessGrant[];
  active: SupportAccessGrant[];
  history: SupportAccessGrant[];
}

export const listSupportAccess = () =>
  apiGetObject<CompanySupportAccessList>("support-access/", { tenantId: resolveTenantId() });

export const approveSupportAccess = (
  grantId: number, choice: { hours: number; scope: SupportScope; note?: string },
) =>
  apiPostObject<SupportAccessGrant>(
    `support-access/${grantId}/approve/`, { ...choice }, { tenantId: resolveTenantId() });

export const rejectSupportAccess = (grantId: number, note = "") =>
  apiPostObject<SupportAccessGrant>(
    `support-access/${grantId}/reject/`, { note }, { tenantId: resolveTenantId() });

export const revokeSupportAccess = (grantId: number, note = "") =>
  apiPostObject<SupportAccessGrant>(
    `support-access/${grantId}/revoke/`, { note }, { tenantId: resolveTenantId() });
