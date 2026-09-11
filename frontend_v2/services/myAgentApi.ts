/**
 * خدمات واجهة برمجة التطبيقات لتبويب «من يمسك دفاتري» والتقييم اليومي (م٧).
 *
 * القواعد الصارمة:
 * - لا يتم إرسال أي معاملات tenant صريحة في جسم أو معلمات الطلب (تُشتق خادمياً).
 * - التعامل مع DRF عبر restApi base client.
 */
import { apiGetObject, apiPostObject, apiPatchObject } from "./restApi";
import type { TwoHealthScores } from "../utils/agentBooks";

/**
 * أسماءُ الحقول أدناه **مأخوذةٌ من حمولة الخادم حرفيّاً**
 * (`platform_ops/services.py` (`get_my_books_tab_data`) و`platform_ops/views.py`
 * (`TenantAgentBooksViewSet`)). و`tsc` هنا لا يفحص خصائصَ JSX ولا شكلَ ما يعود من
 * الشبكة، فحقلٌ مخترَعٌ يُصيَّر فراغاً بلا شكوى — وهذا ما حدث في التسليم الأوّل.
 */
export interface AgentInfo {
  id: number;
  user_id: number;
  name: string;
  username: string;
  specialty: string;
  assigned_at: string;
  role_title: string;
  authority_notice: string;
  engagement_id: number;
  engagement_status: string;
  /** هل للوكيل عملٌ فعليٌّ اليوم؟ دونه لا يُطلَب التقييمُ أصلاً (قصّة ٦٠). */
  worked_today: boolean;
  /** تقييمُ اليوم لهذا الوكيل إن سُجّل — من الخادم لا من تخمين الشاشة. */
  today_rating: TodayRating | null;
}

export interface GrantedMembership {
  id: number;
  target_user_name: string;
  role_before: string;
  role_before_display: string;
  role_after: string;
  role_after_display: string;
  created_at: string;
  acting_employee_name: string;
}

export interface ActivityLogItem {
  id: number;
  timestamp: string;
  action: string;
  entity_type: string;
  /** جملةٌ عربيّةٌ جاهزةٌ صاغها الخادم (الفعل + اسم المستند بمعجم الشركة + «من ماذا إلى ماذا»). */
  description: string;
  actor_name: string;
}

/** تقييمُ اليوم إن وُجد — يصل مع التبويب حتى لا تظنّ الشاشةُ نقرةَ تعديلٍ إنشاءً. */
export interface TodayRating {
  id: number;
  service_date: string;
  stars: number;
  note: string;
  edited_once: boolean;
}

export interface MyBooksTabData {
  tenant_id: number;
  tenant_name: string;
  /** كلُّ وكيلٍ نشطٍ على الشركة — الفرادةُ على (موظف، شركة) فقد يكونون أكثر من واحد. */
  agents: AgentInfo[];
  /** يومُ الخدمة بتوقيت الشركة (`Asia/Hebron`) — لا تاريخُ جهاز الزائر. */
  service_date: string;
  granted_memberships: GrantedMembership[];
  activity_log: ActivityLogItem[];
  total_activities_count: number;
  activity_page_cap: number;
  health_scores: TwoHealthScores;
  can_suspend: boolean;
}

export interface DailyRatingPayload {
  employee_id: number;
  service_date: string;
  stars: number;
  note?: string;
}

/** حقولُ `DailyRatingSerializer` حرفيّاً — لا `source_display` ولا `rated_at` فيه. */
export interface DailyRatingRecord {
  id: number;
  tenant: number;
  company_name: string;
  employee: number;
  employee_name: string;
  service_date: string;
  stars: number;
  note: string;
  source: string;
  edited_once: boolean;
  rated_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateLinkPayload {
  employee_id: number;
  service_date: string;
}

export interface GenerateLinkResult {
  token: string;
  public_url: string;
  api_path: string;
  expires_at: string;
}

export interface EmployeeRatingsSummary {
  status: string;
  average_stars: number | null;
  sample_size: number;
  min_sample_size: number;
}

/**
 * جلب بيانات تبويب «من يمسك دفاتري» لصاحب الشركة الحالي.
 */
export async function getMyBooksTabData(): Promise<MyBooksTabData> {
  return apiGetObject<MyBooksTabData>("my-agent/");
}

/**
 * تعليق وصول وكيل منصة محدد (أو الوكيل النشط الوحيد) للشركة.
 */
export async function suspendAgentAccess(
  engagementId?: number,
  reason?: string,
): Promise<{ detail: string; suspended_count: number; engagement_id?: number }> {
  return apiPostObject<{ detail: string; suspended_count: number; engagement_id?: number }>(
    "my-agent/suspend/",
    {
      engagement_id: engagementId,
      reason: reason || "",
    },
  );
}

/**
 * تسجيل تقييم يومي جديد للوكيل.
 */
export async function submitDailyRating(payload: DailyRatingPayload): Promise<DailyRatingRecord> {
  return apiPostObject<DailyRatingRecord>("my-agent/daily-ratings/", payload);
}

/**
 * تعديل تقييم يومي قائم (مسموح لمرة واحدة فقط خادمياً).
 */
export async function updateDailyRating(
  id: number,
  payload: { stars?: number; note?: string },
): Promise<DailyRatingRecord> {
  return apiPatchObject<DailyRatingRecord>(`my-agent/daily-ratings/${id}/`, payload);
}

/**
 * توليد رابط عام مهشر لمشاركة التقييم.
 */
export async function generateRatingLink(payload: GenerateLinkPayload): Promise<GenerateLinkResult> {
  return apiPostObject<GenerateLinkResult>("my-agent/daily-ratings/generate-link/", payload);
}

/**
 * جلب ملخص تقييمات الموظف والحد الأدنى للعينة.
 */
export async function getEmployeeRatingsSummary(employeeId: number): Promise<EmployeeRatingsSummary> {
  return apiGetObject<EmployeeRatingsSummary>("my-agent/daily-ratings/summary/", {
    query: { employee_id: employeeId },
  });
}

/** استهلاكُ الشركة من باقتها الشهرية واقترابُها من الحدّ (#207 م٨). */
export interface QuotaUsage {
  has_subscription: true;
  status: string;
  status_display: string;
  plan: string;
  period_start: string;
  period_end: string;
  monthly_fee: string;
  included_quota: number;
  consumed_quota: number;
  remaining_quota: number;
  usage_percent: number | null;
  overage_units: number;
  overage_unit_price: string;
  overage_fee: string;
  projected_total: string;
}

export type QuotaUsageResponse = QuotaUsage | { has_subscription: false };

/**
 * جلب استهلاك باقة الخدمة الشهرية للشركة الحالية.
 */
export async function getMyQuotaUsage(): Promise<QuotaUsageResponse> {
  return apiGetObject<QuotaUsageResponse>("my-agent/quota/");
}

