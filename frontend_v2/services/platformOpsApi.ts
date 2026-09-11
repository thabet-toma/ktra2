/**
 * خدمات واجهة برمجة تطبيقات عمليات المنصة (م٦).
 *
 * قاعدة عزل الشركات:
 * - لا يتم إرسال أي معاملات شركة (tenant, tenants, tenant_id, tenant_ids) في وسائط الطلب.
 * - الشركات تُشتق خادمياً من الارتباطات النشطة حصراً.
 */
import { apiGetObject, apiPostObject } from "./restApi";
import type { PlatformAnomaly } from "../utils/interventionAnomalies";
import type { TwoHealthScores } from "../utils/agentBooks";
import type { PlatformDashboardCompany, PlatformDashboardEmployee } from "../utils/dashboardRanking";

export interface PlatformOpsDashboardData {
  view_unit: "employee" | "company";
  employees: PlatformDashboardEmployee[];
  companies: PlatformDashboardCompany[];
  anomalies: PlatformAnomaly[];
  total_anomalies_count: number;
  generated_at: string;
}

export interface PlatformNotification {
  id: number;
  recipient: number;
  tenant: number | null;
  company_name: string | null;
  notification_type: "sla_breach" | "low_score" | "quota_exceeded" | string;
  notification_type_display: string;
  title: string;
  message: string;
  data: Record<string, any>;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformActivityLog {
  id: number;
  employee: number;
  employee_name: string;
  specialty: string;
  tenant: number | null;
  company_name: string | null;
  action: string;
  action_display: string;
  entity_type: string;
  entity_id: string;
  description: string;
  details: Record<string, any>;
  created_at: string;
}

export interface WorkOrderRow {
  id: number;
  tenant: number;
  company_name: string;
  assignee: number | null;
  assignee_name: string | null;
  title: string;
  kind: string;
  kind_display: string;
  status: string;
  status_display: string;
  deadline_at: string | null;
  received_at: string;
  created_at: string;
  waiting_seconds_total?: number;
}

export interface WorkOrderDrilldownFilter {
  assignee?: number | string;
  /**
   * تضييقٌ على شركةٍ **داخل** النطاق المشتقّ من الارتباطات — لا اختيارُ شركةٍ من
   * الطلب. الخادمُ يطبّقه بعد فلترة النطاق، فشركةٌ خارجه تُعيد صفراً لا تسريباً.
   * (ولهذا اسمُه `company` لا `tenant`: الأخيرةُ ممنوعةٌ صراحةً في `buildCleanQueryString`.)
   */
  company?: number | string;
  /** رقمُ أمرِ عملٍ بعينه — شذوذُ «تأخّرٌ حرج» ينقر إلى صفٍّ واحد. */
  work_order?: number | string;
  status?: string;
  kind?: string;
  metric?: "active" | "overdue" | "completed" | "cancelled" | "rework";
  is_overdue?: boolean | string;
}

function buildCleanQueryString(params: Record<string, any> = {}): string {
  const forbidden = ["tenant", "tenants", "tenant_id", "tenant_ids"];
  const searchParams = new URLSearchParams();

  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null && val !== "") {
      if (!forbidden.includes(key.toLowerCase())) {
        searchParams.set(key, String(val));
      }
    }
  }
  const str = searchParams.toString();
  return str ? `?${str}` : "";
}

/** استرجاع ملخص لوحة القيادة التفاعلية مع شريط التدخل. */
export const getPlatformOpsDashboard = () =>
  apiGetObject<PlatformOpsDashboardData>("platform/ops/dashboard/");

/** استرجاع أوامر العمل المنصية ضمن النطاق المسموح (للتنقيب). */
export const getScopedWorkOrders = (filter: WorkOrderDrilldownFilter = {}) =>
  apiGetObject<{ results: WorkOrderRow[]; count?: number } | WorkOrderRow[]>(
    `platform/ops/work-orders/${buildCleanQueryString(filter)}`
  );

/** استرجاع إشعارات المستخدم المنصية المفلترة خادمياً حصراً. */
export const getPlatformNotifications = (unreadOnly = false) => {
  const query = unreadOnly ? "?is_read=false" : "";
  return apiGetObject<{ results: PlatformNotification[]; count?: number } | PlatformNotification[]>(
    `platform/ops/notifications/${query}`
  );
};

/** عدد الإشعارات غير المقروءة لتحديث شارة الجرس. */
export const getUnreadNotificationsCount = () =>
  apiGetObject<{ unread_count: number }>("platform/ops/notifications/unread-count/");

/** تعليم إشعار واحد كمقروء. */
export const markNotificationRead = (id: number) =>
  apiPostObject<PlatformNotification>(`platform/ops/notifications/${id}/mark-read/`, {});

/** تعليم كافة إشعارات المستخدم كمقروءة. */
export const markAllNotificationsRead = () =>
  apiPostObject<{ marked_count: number }>("platform/ops/notifications/mark-all-read/", {});

/** استرجاع سجل النشاط العابر للشركات. */
export const getPlatformActivityLogs = (params: { employee?: number | string; action?: string } = {}) =>
  apiGetObject<{ results: PlatformActivityLog[]; count?: number } | PlatformActivityLog[]>(
    `platform/ops/activity-logs/${buildCleanQueryString(params)}`
  );

/** استرجاع سجل نشاط موظف محدد عبر كل الشركات. */
export const getEmployeeActivity = (employeeId: number) =>
  apiGetObject<PlatformActivityLog[]>(`platform/ops/employees/${employeeId}/activity/`);

/**
 * حمولةُ `platform_ops/views.py` (`CompanyHealthView`) — و`health_scores` نفسُ شكلِ
 * `/api/my-agent/` لأنّ مصدرَهما دالّةٌ واحدة (`calculate_two_health_scores`).
 */
export interface CompanyHealthData {
  tenant_id: number;
  company_name: string;
  health_scores: TwoHealthScores;
}

/** استرجاع درجتي الصحة لشركة معينة في مسار السوبر أدمن والعمليات المنصية (عند الطلب لمنع N+1). */
export const getCompanyHealth = (tenantId: number) =>
  apiGetObject<CompanyHealthData>(`platform/ops/companies/${tenantId}/health/`);

/** سجلُّ تدقيق الفوترة الشهرية لاشتراك الخدمة (#207 م٨). */
export interface SubscriptionBillingRecordRow {
  id: number;
  subscription: number;
  tenant_id: number;
  company_name: string;
  period_start: string;
  period_end: string;
  invoice: number | null;
  invoice_number: string | null;
  monthly_fee: string;
  included_quota: number;
  consumed_quota: number;
  overage_units: number;
  overage_unit_price: string;
  overage_fee: string;
  total_amount: string;
  created_at: string;
}

/** استرجاع سجلات الفوترة الشهرية لاشتراكات الخدمة المنصية. */
export const listBillingRecords = async (
  filter: { company?: number; subscription?: number } = {},
): Promise<SubscriptionBillingRecordRow[]> => {
  const data = await apiGetObject<
    { results: SubscriptionBillingRecordRow[]; count?: number } | SubscriptionBillingRecordRow[]
  >(`platform/ops/billing-records/${buildCleanQueryString(filter)}`);
  if (Array.isArray(data)) {
    return data;
  }
  return data?.results || [];
};

