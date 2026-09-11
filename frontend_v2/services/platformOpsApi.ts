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

export type ServiceSubscriptionStatus = "trial" | "active" | "suspended" | "cancelled";

export interface ServiceSubscriptionRow {
  id: number;
  tenant: number;
  company_name: string;
  billing_customer: number | null;
  billing_customer_name: string | null;
  status: ServiceSubscriptionStatus;
  status_display: string;
  plan: string;
  monthly_fee: string;
  included_quota: number;
  overage_unit_price: string;
  consumed_quota: number;
  period_start: string | null;
  period_end: string | null;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  is_trial: boolean;
  is_eligible: boolean;
  active_engagements_count: number;
  pre_suspension_status: string;
  scheduled_cancellation_date: string | null;
  cancellation_reason: string;
  subscription_policy_version: number | null;
  fixed_fee_product: number | null;
  overage_product: number | null;
  created_at: string;
  updated_at: string;
}

export interface ServiceSubscriptionEventRow {
  id: number;
  action: string;
  action_display: string;
  from_status: string;
  to_status: string;
  reason: string;
  actor: number | null;
  actor_name: string;
  correlation_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ServiceSubscriptionSettingsInput {
  plan?: string;
  monthly_fee?: string | number;
  included_quota?: number;
  overage_unit_price?: string | number;
  billing_customer?: number | null;
  /** إلزامي متى تغيّر حقل فعلاً — تعديل شروط اشتراك بعينه استثناء يُدقَّق بسببه. */
  reason?: string;
}

export interface BillingCustomerOption {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
}

export type SubscriptionPolicyStatus = "draft" | "active" | "retired";

/** حالة السريان المحسوبة من نافذة التاريخ لا من `status` وحده: نشطة بتاريخ لاحق = مجدولة. */
export type SubscriptionPolicyEffectiveState = "draft" | "scheduled" | "current" | "retired";

export interface BillingProductOption {
  id: number;
  sku: string;
  name: string;
}

export interface SubscriptionPolicyRow {
  id: number;
  version: number;
  status: SubscriptionPolicyStatus;
  status_display: string;
  effective_state: SubscriptionPolicyEffectiveState;
  plan: string;
  billing_tenant: number;
  billing_tenant_name: string;
  monthly_fee: string;
  included_quota: number;
  trial_days: number;
  overage_unit_price: string;
  fixed_fee_product: number | null;
  fixed_fee_product_name: string | null;
  overage_product: number | null;
  overage_product_name: string | null;
  activation_reason: string;
  effective_from: string | null;
  effective_to: string | null;
  created_by: number | null;
  activated_by: number | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionPolicyInput {
  billing_tenant: number;
  monthly_fee?: string | number;
  included_quota?: number;
  trial_days?: number;
  overage_unit_price?: string | number;
  /** فارغ = نسخة عامة لكل الخطط. */
  plan?: string;
  fixed_fee_product?: number | null;
  overage_product?: number | null;
}

/** قيمتا الحقل في النسخة النشطة والمسودة — المال نصٌّ دقيق، والحصة والأيام أعداد، وشركة الفوترة معرّف. */
export interface SubscriptionPolicyDiffValue {
  active: string | number | null;
  draft: string | number | null;
}

export interface SubscriptionPolicyPreview {
  draft: SubscriptionPolicyRow;
  active: SubscriptionPolicyRow | null;
  diff: Record<string, SubscriptionPolicyDiffValue>;
  note: string;
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

export const listServiceSubscriptions = async (
  filter: { company?: number; status?: ServiceSubscriptionStatus } = {},
): Promise<ServiceSubscriptionRow[]> =>
  unwrapRows(await apiGetObject<{ results: ServiceSubscriptionRow[]; count?: number } | ServiceSubscriptionRow[]>(
    `platform/ops/subscriptions/${buildCleanQueryString(filter)}`,
  ));

export const startServiceTrial = (tenant: number, plan?: string) =>
  apiPostObject<ServiceSubscriptionRow>("platform/ops/subscriptions/start-trial/", {
    tenant,
    plan: plan || undefined,
  });

export const activatePaidSubscription = (tenant: number, billingCustomer: number, plan?: string) =>
  apiPostObject<ServiceSubscriptionRow>("platform/ops/subscriptions/activate-paid/", {
    tenant,
    billing_customer: billingCustomer,
    plan: plan || undefined,
  });

/** تحويل تجربة أو إعادة تفعيل ملغى على صفّه القائم — الخادم يقرّر اللقطة حسب الحالة. */
export const activateExistingSubscription = (id: number, billingCustomer: number, plan?: string) =>
  apiPostObject<ServiceSubscriptionRow>(`platform/ops/subscriptions/${id}/activate-paid/`, {
    billing_customer: billingCustomer,
    plan: plan || undefined,
  });

export const suspendServiceSubscription = (id: number, reason: string) =>
  apiPostObject<ServiceSubscriptionRow>(`platform/ops/subscriptions/${id}/suspend/`, { reason });

export const resumeServiceSubscription = (id: number) =>
  apiPostObject<ServiceSubscriptionRow>(`platform/ops/subscriptions/${id}/resume/`, {});

export const cancelServiceSubscription = (id: number, reason: string, immediate = false) =>
  apiPostObject<ServiceSubscriptionRow>(`platform/ops/subscriptions/${id}/cancel/`, { reason, immediate });

export const withdrawScheduledCancellation = (id: number) =>
  apiPostObject<ServiceSubscriptionRow>(`platform/ops/subscriptions/${id}/withdraw-cancellation/`, {});

export const updateSubscriptionSettings = (id: number, input: ServiceSubscriptionSettingsInput) =>
  apiPostObject<ServiceSubscriptionRow>(`platform/ops/subscriptions/${id}/update-settings/`, input);

export const listSubscriptionEvents = (id: number) =>
  apiGetObject<ServiceSubscriptionEventRow[]>(`platform/ops/subscriptions/${id}/events/`);

/**
 * `plan` ليس زينة: الحفظ يتحقّق من العميل بسياسة نطاق الخطة المطلوبة، فبحثٌ بلا خطة
 * كان يعرض عملاء شركة فوترةٍ أخرى ثم يرفضهم الحفظُ. يُهمَل حين يُمرَّر `subscription`
 * لأن لقطة الاشتراك تحسم الشركة.
 */
export const searchBillingCustomers = (query: string, subscription?: number, plan?: string) =>
  apiGetObject<BillingCustomerOption[]>(
    `platform/ops/subscriptions/billing-customers/${buildCleanQueryString({ q: query, subscription, plan })}`,
  );

export const listSubscriptionPolicies = async (): Promise<SubscriptionPolicyRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: SubscriptionPolicyRow[]; count?: number } | SubscriptionPolicyRow[]>(
      "platform/ops/subscription-policies/",
    ),
  );

export const createSubscriptionPolicyDraft = (input: SubscriptionPolicyInput) =>
  apiPostObject<SubscriptionPolicyRow>("platform/ops/subscription-policies/draft/", input);

export const updateSubscriptionPolicyDraft = (id: number, input: Partial<SubscriptionPolicyInput>) =>
  apiPostObject<SubscriptionPolicyRow>(`platform/ops/subscription-policies/${id}/update-draft/`, input);

export const cloneSubscriptionPolicy = (id: number) =>
  apiPostObject<SubscriptionPolicyRow>(`platform/ops/subscription-policies/${id}/clone/`, {});

export const previewSubscriptionPolicy = (id: number) =>
  apiPostObject<SubscriptionPolicyPreview>(`platform/ops/subscription-policies/${id}/preview/`, {});

/** `effectiveFrom` بصيغة ISO؛ غيابه = سريان فوري. */
export const activateSubscriptionPolicy = (id: number, changeReason: string, effectiveFrom?: string) =>
  apiPostObject<SubscriptionPolicyRow>(`platform/ops/subscription-policies/${id}/activate/`, {
    change_reason: changeReason,
    effective_from: effectiveFrom || undefined,
  });

export const searchPolicyBillingProducts = (policyId: number, query: string) =>
  apiGetObject<BillingProductOption[]>(
    `platform/ops/subscription-policies/${policyId}/billing-products/${buildCleanQueryString({ q: query })}`,
  );
