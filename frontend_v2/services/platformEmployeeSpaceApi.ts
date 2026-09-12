/**
 * عميلُ واجهة برمجة تطبيقات مساحة موظّف الإدخال (التذكرة 210-E، §١).
 *
 * `GET /api/platform/ops/employees/` بلا مستدعٍ سلفاً — هي بوّابةُ تعريف الموظّف
 * بنفسه (تُرجِع صفَّه وحدَه لغير المدير، `get_queryset` في `PlatformEmployeeViewSet`)،
 * لا بابَ مديرٍ ميّت.
 */
import { apiGetObject, apiPostObject } from "./restApi";

export type PlatformEmployeeStatus = "active" | "on_leave" | "offboarded";

export interface MyPlatformEmployeeProfile {
  id: number;
  user: number;
  username: string;
  email: string;
  specialty: string;
  capacity_target: string;
  status: PlatformEmployeeStatus;
  created_at: string;
  updated_at: string;
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

/**
 * صفُّ الموظّفِ **المطابقُ للمستخدم الحاليّ** من `/employees/`.
 *
 * **ولا يُؤخذ `rows[0]` أبداً**: `PlatformEmployeeViewSet.get_queryset` يضيّق على
 * `user=request.user` لغيرِ المدير وحدَه — أمّا مديرُ العمليات فيعود له **كلُّ**
 * الموظفين مرتَّبين بـ`-created_at`. فلو أخذنا الأوّلَ لقرأ المديرُ محفظةَ زميلٍ
 * عشوائيٍّ تحت عنوان «محفظتي». العزلُ الخادميُّ سليم، والهويّةُ هي ما كان يَضيع.
 *
 * وحين لا صفَّ للمستخدم (مديرٌ بلا `PlatformEmployee`) تعود `null` فتعرض الشاشةُ
 * «لا يوجد ملفُّ موظّف منصّةٍ مرتبطٌ بحسابك» — وهو الجوابُ الصحيح لا محفظةُ غيرِه.
 */
export const getMyPlatformEmployeeProfile = async (
  currentUserId: string | number | undefined,
): Promise<MyPlatformEmployeeProfile | null> => {
  if (currentUserId === undefined || currentUserId === null || currentUserId === "") return null;
  const rows = unwrapRows(
    await apiGetObject<{ results: MyPlatformEmployeeProfile[]; count?: number } | MyPlatformEmployeeProfile[]>(
      "platform/ops/employees/",
    ),
  );
  return rows.find((row) => String(row.user) === String(currentUserId)) ?? null;
};

// ==============================================================================
// شركاتُ الموظّف: الحصّةُ وبنودُ الصحّة المُسنَدةُ إليه (القصّتان ٣٩ و٤٠)
// ==============================================================================

export interface EmployeeCompanyHealthItem {
  id: number;
  code: string;
  status: string;
  status_display: string;
  mandatory: boolean;
  action: string;
  evidence_note: string;
  due_date: string | null;
  work_order_id: number | null;
}

export interface EmployeeEngagedCompanyRow {
  tenant_id: number;
  company_name: string;
  subscription_status: string;
  included_quota: number;
  consumed_quota: number;
  /** كميّةٌ لا تكون سالبة؛ التجاوزُ يُقرأ من `over_quota` لا من رصيدٍ بالسالب. */
  remaining_quota: number;
  over_quota: number;
  health_items: EmployeeCompanyHealthItem[];
}

/** الشركاتُ تُشتقّ من ارتباطات المستدعي خادمياً — لا يقبل المسارُ معرّفَ شركةٍ إطلاقاً. */
export const listMyEngagedCompanies = () =>
  apiGetObject<EmployeeEngagedCompanyRow[]>("platform/ops/employees/my-companies/");

// ==============================================================================
// اعتراضُ الموظّف على نتيجة شهر (القصة ٤٤)
// ==============================================================================

export type PerformanceReviewStatus = "open" | "accepted" | "rejected";

export interface PerformanceReviewRequestRow {
  id: number;
  employee: number;
  employee_name: string;
  period_year: number;
  period_month: number;
  axis: string;
  reason: string;
  status: PerformanceReviewStatus;
  status_display: string;
  resolution_note: string;
  resolved_by_name: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export const listMyPerformanceReviewRequests = async (): Promise<PerformanceReviewRequestRow[]> =>
  unwrapRows(
    await apiGetObject<
      { results: PerformanceReviewRequestRow[]; count?: number } | PerformanceReviewRequestRow[]
    >("platform/ops/performance-review-requests/"),
  );

/**
 * اسمٌ ثانٍ لنفس النداء لا نسخةٌ ثانيةٌ منه: الخادمُ (`get_queryset`) هو من يفرّق
 * الجمهورَ — مديرُ العمليات يرى كلَّ الاعتراضات، والموظّفُ اعتراضاتِه هو وحدَه.
 * فدالّتان بنفس المسار والنوع كانتا ستنحرفان عند أوّل تعديلٍ يُنسى في إحداهما.
 * وبقاءُ الاسمين يُبقي كلَّ موضعِ نداءٍ صادقاً عن جمهوره.
 *
 * وهذه القراءةُ الإداريّةُ كانت بلا مستدعٍ إطلاقاً — فلا شاشةَ لمدير العمليات
 * يردّ منها على اعتراض موظّف (التذكرة 210-F).
 */
export const listPerformanceReviewRequestsForManager = listMyPerformanceReviewRequests;

/**
 * ردُّ مدير العمليات على اعتراض — قبولاً أو رفضاً، بردٍّ مكتوبٍ إلزامياً في
 * الحالتين. `accepted` مطابقةً حرفيّاً لـ`ResolvePerformanceReviewSerializer`
 * الخادميّ (`platform_ops/serializers.py`) — لا حقل `status` هنا.
 */
export const resolvePerformanceReviewRequest = (
  id: number,
  input: { accepted: boolean; resolution_note: string },
) => apiPostObject<PerformanceReviewRequestRow>(`platform/ops/performance-review-requests/${id}/resolve/`, input);

export interface RecapturedSnapshot {
  id: number;
  employee: number;
  employee_name: string;
  period_year: number;
  period_month: number;
  status: string;
  /** `Decimal` يصل **رقماً** لا نصّاً: مُرمِّزُ DRF يحوّله `float`. */
  composite_score: number | null;
  sample_size: number;
}

/**
 * الخطوةُ الثانيةُ من القبول: تُعاد اللقطةُ على البيانات **بعد** تصحيحها عند
 * المصدر. القبولُ وحدَه لا يمسّ الدرجة عمداً — وبلا هذا الزرّ كان يبقى وعداً
 * بلا أثر، إذ لا مسارَ آخرَ في النظام يستدعي `force_refresh`.
 */
export const recapturePerformanceAfterAcceptedReview = (id: number) =>
  apiPostObject<RecapturedSnapshot>(`platform/ops/performance-review-requests/${id}/recapture/`, {});

/** الموظّفُ يُشتقّ من الجلسة لا من الحمولة — لا يفتح أحدٌ اعتراضاً باسم غيره. */
export const openPerformanceReviewRequest = (input: {
  period_year: number;
  period_month: number;
  axis?: string;
  reason: string;
}) =>
  apiPostObject<PerformanceReviewRequestRow>("platform/ops/performance-review-requests/open/", {
    period_year: input.period_year,
    period_month: input.period_month,
    axis: input.axis || "",
    reason: input.reason,
  });

// ==============================================================================
// KTRA Champions (§١٠)
// ==============================================================================

export interface ChampionEntry {
  employee_id: number;
  employee_name: string;
  /** رقمُ الفئة بوحدتها — **لا مبلغَ أبداً**: الاكتسابُ عددُ عملاء لا قيمةُ عمولة. */
  value: number;
  /** الدليلُ نصّاً: الفئة والفترة ومصدرُ الرقم، بلا اسم عميلٍ ولا راتب. */
  evidence: string;
}

export interface ChampionCategory {
  category: string;
  category_label: string;
  unit: string;
  /** القمّةُ وحدَها — §١٠ تمنع «ترتيب الأسوأ»، وقائمةٌ كاملةٌ تُنتجه ضمناً. */
  entries: ChampionEntry[];
}

export interface ChampionsBoard {
  period_year: number;
  period_month: number;
  categories: ChampionCategory[];
}

export const getChampionsBoard = (year: number, month: number) =>
  apiGetObject<ChampionsBoard>(`platform/ops/champions/?year=${year}&month=${month}`);
