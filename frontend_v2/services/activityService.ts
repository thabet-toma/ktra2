import { apiGetList } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";
import type { ActivityLogEntry, ActivityUserOption } from "../types/activity";

const getTenantId = () => resolveTenantId();

export interface ActivityQuery {
  user?: number | string;
  action?: string;
  entity_type?: string;
  entity_id?: number | string;
  partner_id?: number | string;
  date?: string;        // YYYY-MM-DD (يوم واحد)
  date_from?: string;
  date_to?: string;
  search?: string;
  include_views?: boolean;
  page_size?: number;
}

/** الصفحة العامة (للمدير) أو أي استعلام مفلتر. */
export async function getActivityLog(params: ActivityQuery = {}): Promise<ActivityLogEntry[]> {
  const query: Record<string, string | number | boolean | undefined> = {
    user: params.user,
    action: params.action,
    entity_type: params.entity_type,
    entity_id: params.entity_id,
    partner_id: params.partner_id,
    date: params.date,
    date_from: params.date_from,
    date_to: params.date_to,
    search: params.search || undefined,
    include_views: params.include_views ? "true" : undefined,
    page_size: params.page_size ?? 200,
  };
  return apiGetList<ActivityLogEntry>("activity/", { tenantId: getTenantId(), query });
}

/** سجل نشاط مستند واحد (فاتورة/صفقة) — متاح لأي مستخدم مصرّح. */
export async function getEntityActivity(
  entityType: string,
  entityId: number | string,
): Promise<ActivityLogEntry[]> {
  return apiGetList<ActivityLogEntry>("activity/", {
    tenantId: getTenantId(),
    query: { entity_type: entityType, entity_id: entityId, page_size: 200 },
  });
}

/** سجل نشاط كل المستندات المرتبطة بعميل/مورد/وكيل. */
export async function getPartnerActivity(
  partnerId: number | string,
): Promise<ActivityLogEntry[]> {
  return apiGetList<ActivityLogEntry>("activity/", {
    tenantId: getTenantId(),
    query: { partner_id: partnerId, page_size: 200 },
  });
}

/** قائمة المستخدمين الذين لهم نشاط (لفلتر الصفحة العامة). */
export async function getActivityUsers(): Promise<ActivityUserOption[]> {
  return apiGetList<ActivityUserOption>("activity/users/", { tenantId: getTenantId() });
}
