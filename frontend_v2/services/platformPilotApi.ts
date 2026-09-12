/**
 * خدماتُ واجهة برمجة تطبيقات سياسة تقييم الـpilot (40/30/20/10)، سياسة تعويض
 * الموظف، والمحفظة التشغيلية (التذكرة 210-D).
 *
 * قاعدة عزل الشركات نفسُها في `platformOpsApi.ts`/`platformWorkOrdersApi.ts`:
 * لا معاملات شركةٍ خامّة في الطلب.
 */
import { apiGetObject, apiPostObject } from "./restApi";

function buildQuery(params: Record<string, any> = {}): string {
  const searchParams = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null && val !== "") searchParams.set(key, String(val));
  }
  const str = searchParams.toString();
  return str ? `?${str}` : "";
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

// ==============================================================================
// سياسة تقييم الـpilot (§٥، §٨)
// ==============================================================================

export type PilotPolicyStatus = "draft" | "active" | "retired";
export type PilotPolicyEffectiveState = "draft" | "scheduled" | "current" | "retired";

export type PilotAxisKey = "task_completion" | "quality_accuracy" | "sla_adherence" | "customer_satisfaction";

export const PILOT_AXES: PilotAxisKey[] = [
  "task_completion", "quality_accuracy", "sla_adherence", "customer_satisfaction",
];

/** تسميات المحاور الأربعة بتهجئة الخادم — لا جدول ترجمةٍ ثانٍ لأي مسمًّى يعود من الخادم غير هذا. */
export const PILOT_AXIS_LABELS: Record<PilotAxisKey, string> = {
  task_completion: "إنجاز العمل المقبول",
  quality_accuracy: "الدقة والجودة",
  sla_adherence: "الالتزام بالأجل",
  customer_satisfaction: "رضا العملاء",
};

export const PILOT_POLICY_EFFECTIVE_STATE_LABEL: Record<PilotPolicyEffectiveState, string> = {
  draft: "مسودة",
  scheduled: "مجدولة",
  current: "سارية",
  retired: "منتهية",
};

export interface PerformanceEvaluationPolicyRow {
  id: number;
  version: number;
  status: PilotPolicyStatus;
  status_display: string;
  effective_state: PilotPolicyEffectiveState;
  specialty: string;
  weights: Partial<Record<PilotAxisKey, number>>;
  targets: Record<string, unknown>;
  min_sample_size: number;
  review_grace_period_hours: number;
  activation_reason: string;
  effective_from: string | null;
  effective_to: string | null;
  created_by: number | null;
  activated_by: number | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PerformanceEvaluationPolicyDraftInput {
  specialty?: string;
  weights?: Partial<Record<PilotAxisKey, number | string>>;
  min_sample_size?: number;
  review_grace_period_hours?: number;
}

export interface PolicyPreview<T> {
  draft: T;
  active: T | null;
  diff: Record<string, { active: unknown; draft: unknown }>;
  note: string;
}

export const listPerformanceEvaluationPolicies = async (): Promise<PerformanceEvaluationPolicyRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: PerformanceEvaluationPolicyRow[]; count?: number } | PerformanceEvaluationPolicyRow[]>(
      "platform/ops/performance-evaluation-policies/",
    ),
  );

export const createPerformanceEvaluationPolicyDraft = (input: PerformanceEvaluationPolicyDraftInput = {}) =>
  apiPostObject<PerformanceEvaluationPolicyRow>("platform/ops/performance-evaluation-policies/draft/", input);

export const clonePerformanceEvaluationPolicy = (id: number) =>
  apiPostObject<PerformanceEvaluationPolicyRow>(`platform/ops/performance-evaluation-policies/${id}/clone/`, {});

export const updatePerformanceEvaluationPolicyDraft = (id: number, input: PerformanceEvaluationPolicyDraftInput) =>
  apiPostObject<PerformanceEvaluationPolicyRow>(
    `platform/ops/performance-evaluation-policies/${id}/update-draft/`, input,
  );

export const previewPerformanceEvaluationPolicy = (id: number) =>
  apiPostObject<PolicyPreview<PerformanceEvaluationPolicyRow>>(
    `platform/ops/performance-evaluation-policies/${id}/preview/`, {},
  );

export const activatePerformanceEvaluationPolicy = (id: number, activationReason: string, effectiveFrom?: string) =>
  apiPostObject<PerformanceEvaluationPolicyRow>(`platform/ops/performance-evaluation-policies/${id}/activate/`, {
    activation_reason: activationReason,
    effective_from: effectiveFrom || undefined,
  });

// ==============================================================================
// سياسة تعويض الموظف (§٧، §٨)
// ==============================================================================

export interface EmployeeCompensationPolicyRow {
  id: number;
  version: number;
  status: PilotPolicyStatus;
  status_display: string;
  effective_state: PilotPolicyEffectiveState;
  employee: number | null;
  employee_name: string | null;
  base_salary: string;
  daily_hours: string;
  weekly_days: number;
  acquisition_commission_amount: string;
  acquisition_commission_months: number;
  accrual_day_of_month: number;
  activation_reason: string;
  effective_from: string | null;
  effective_to: string | null;
  created_by: number | null;
  activated_by: number | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeCompensationPolicyDraftInput {
  employee?: number | null;
  base_salary?: string | number;
  daily_hours?: string | number;
  weekly_days?: number;
  acquisition_commission_amount?: string | number;
  acquisition_commission_months?: number;
  accrual_day_of_month?: number;
}

export const listEmployeeCompensationPolicies = async (
  filter: { employee?: number } = {},
): Promise<EmployeeCompensationPolicyRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: EmployeeCompensationPolicyRow[]; count?: number } | EmployeeCompensationPolicyRow[]>(
      `platform/ops/compensation-policies/${buildQuery(filter)}`,
    ),
  );

export const createEmployeeCompensationPolicyDraft = (input: EmployeeCompensationPolicyDraftInput = {}) =>
  apiPostObject<EmployeeCompensationPolicyRow>("platform/ops/compensation-policies/draft/", input);

export const cloneEmployeeCompensationPolicy = (id: number) =>
  apiPostObject<EmployeeCompensationPolicyRow>(`platform/ops/compensation-policies/${id}/clone/`, {});

export const updateEmployeeCompensationPolicyDraft = (id: number, input: EmployeeCompensationPolicyDraftInput) =>
  apiPostObject<EmployeeCompensationPolicyRow>(`platform/ops/compensation-policies/${id}/update-draft/`, input);

export const previewEmployeeCompensationPolicy = (id: number) =>
  apiPostObject<PolicyPreview<EmployeeCompensationPolicyRow>>(`platform/ops/compensation-policies/${id}/preview/`, {});

export const activateEmployeeCompensationPolicy = (id: number, activationReason: string, effectiveFrom?: string) =>
  apiPostObject<EmployeeCompensationPolicyRow>(`platform/ops/compensation-policies/${id}/activate/`, {
    activation_reason: activationReason,
    effective_from: effectiveFrom || undefined,
  });

// ==============================================================================
// المحفظة: سطور الرواتب وعمولات الاكتساب (§٧)
// ==============================================================================

export type WalletLineStatus = "pending" | "eligible" | "approved" | "payable" | "paid" | "reversed";

/** تسميات حالة سطر المحفظة — للعرض حين لا تُرفَق `status_display` من الخادم في سياقٍ ما. */
export const WALLET_LINE_STATUS_LABEL: Record<WalletLineStatus, string> = {
  pending: "معلّق",
  eligible: "مؤهَّل",
  approved: "معتمَد",
  payable: "قابل للصرف",
  paid: "مصروف",
  reversed: "معكوس",
};

/** مرآةُ `_WALLET_ALLOWED_TRANSITIONS` في `platform_ops/services.py` — للعرض فقط، الخادمُ هو الحَكَم. */
export const WALLET_LINE_NEXT_STATUS: Partial<Record<WalletLineStatus, WalletLineStatus>> = {
  pending: "eligible",
  eligible: "approved",
  approved: "payable",
  payable: "paid",
};

export interface EmployeeSalaryLineRow {
  id: number;
  employee: number;
  employee_name: string;
  period_year: number;
  period_month: number;
  sequence: number;
  amount: string;
  status: WalletLineStatus;
  status_display: string;
  pending_reason: string;
  compensation_policy: number | null;
  monthly_close: number | null;
  adjustment_of: number | null;
  reason: string;
  approved_by: number | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AcquisitionCommissionLineRow {
  id: number;
  acquisition: number;
  company_name: string;
  employee: number;
  employee_name: string;
  period_year: number;
  period_month: number;
  sequence: number;
  commission_month_index: number;
  amount: string;
  status: WalletLineStatus;
  status_display: string;
  pending_reason: string;
  compensation_policy: number | null;
  monthly_close: number | null;
  adjustment_of: number | null;
  reason: string;
  approved_by: number | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export const transitionSalaryLine = (id: number, toStatus: WalletLineStatus) =>
  apiPostObject<EmployeeSalaryLineRow>(`platform/ops/salary-lines/${id}/transition/`, { to_status: toStatus });

export const reverseSalaryLine = (id: number, reason: string) =>
  apiPostObject<EmployeeSalaryLineRow>(`platform/ops/salary-lines/${id}/reverse/`, { reason });

export const adjustSalaryLine = (id: number, amount: string | number, reason: string) =>
  apiPostObject<EmployeeSalaryLineRow>(`platform/ops/salary-lines/${id}/adjust/`, { amount, reason });

export const transitionCommissionLine = (id: number, toStatus: WalletLineStatus) =>
  apiPostObject<AcquisitionCommissionLineRow>(`platform/ops/commission-lines/${id}/transition/`, { to_status: toStatus });

export const reverseCommissionLine = (id: number, reason: string) =>
  apiPostObject<AcquisitionCommissionLineRow>(`platform/ops/commission-lines/${id}/reverse/`, { reason });

export const adjustCommissionLine = (id: number, amount: string | number, reason: string) =>
  apiPostObject<AcquisitionCommissionLineRow>(`platform/ops/commission-lines/${id}/adjust/`, { amount, reason });

// ==============================================================================
// إغلاق الشهر (§٥، §٧)
// ==============================================================================

export interface MonthlyCompensationCloseRow {
  id: number;
  period_year: number;
  period_month: number;
  performance_policy: number | null;
  employees_processed: number;
  snapshots_captured: number;
  salary_lines_created: number;
  commission_lines_created: number;
  closed_by: number | null;
  correlation_id: string;
  created_at: string;
}

export interface CompensationMonthClosePreview {
  already_closed: boolean;
  close: MonthlyCompensationCloseRow | null;
  blockers: number[];
  eligible_employees: number;
  review_grace_period_hours: number;
}

export const previewCompensationMonthClose = (periodYear: number, periodMonth: number) =>
  apiGetObject<CompensationMonthClosePreview>(
    `platform/ops/compensation/close/${buildQuery({ period_year: periodYear, period_month: periodMonth })}`,
  );

export const closeCompensationMonth = (periodYear: number, periodMonth: number) =>
  apiPostObject<MonthlyCompensationCloseRow>("platform/ops/compensation/close/", {
    period_year: periodYear, period_month: periodMonth,
  });

// ==============================================================================
// أداء الموظف عبر محاور الـpilot، ومحفظته (على أفعال PlatformEmployeeViewSet)
// ==============================================================================

export interface PilotAxisBreakdown {
  applicable: boolean;
  weight: number;
  weight_pct: number;
  /**
   * الوزنُ **كما وضعته السياسة** قبل إعادة التوزيع — يعلنه الخادم لأنّ الفعليَّ
   * وحدَه يُخفي أنّ محوراً غيرَ منطبقٍ أُسقط ووُزّع وزنُه، فيقرأ الموظّفُ وزناً لم
   * تضعه السياسةُ قطّ ولا يعرف أنّ محوراً غاب (التذكرة 210-D، §٥).
   */
  weight_original: number;
  weight_original_pct: number;
  score: number;
  score_pct: number;
  /**
   * النسبةُ الخامُّ لمحور إنجاز العمل قبل القصّ عند 100 — منها يُقرأ الفائضُ فوق
   * الطاقة. لا تصل إلا لهذا المحور، و`null` حين لا مقامَ له.
   */
  raw_percent?: number | null;
  /**
   * روابطُ مستنداتٍ من نوعٍ لا بندَ له في الكتالوج النشط: مقامٌ ناقصٌ يرفع الدرجةَ
   * بغير حقّ، فيُعرَض تحذيراً بدل أن يُطرح صامتاً. لمحور إنجاز العمل وحدَه.
   */
  uncatalogued_document_links?: number;
  weighted_contribution: number;
  numerator: number;
  denominator: number;
  exclusions: string[];
  sample_size?: number;
  min_sample_size?: number;
}

export interface EmployeePilotPerformance {
  status: "calculated" | "insufficient_data";
  status_message: string;
  composite_score: number | null;
  sample_size: number;
  min_sample_size: number;
  axes: Partial<Record<PilotAxisKey, PilotAxisBreakdown>>;
  weights_sum: number;
  policy_used: Record<string, unknown>;
}

export const getEmployeePilotPerformance = (
  employeeId: number, year?: number, month?: number,
) =>
  apiGetObject<EmployeePilotPerformance>(
    `platform/ops/employees/${employeeId}/pilot-performance/${buildQuery({ year, month })}`,
  );

export interface EmployeeWalletSummary {
  employee_id: number;
  period_year: number;
  period_month: number;
  /** §٧: ثلاثةُ أرقام. `expected` = المؤكَّد + المعلَّق، أي حصيلةُ الشهر لو تحقّق كلُّ شرطٍ ناقص. */
  totals: { confirmed: string; pending: string; expected: string };
  salary_lines: EmployeeSalaryLineRow[];
  commission_lines: AcquisitionCommissionLineRow[];
}

export const getEmployeeWallet = (employeeId: number, year?: number, month?: number) =>
  apiGetObject<EmployeeWalletSummary>(
    `platform/ops/employees/${employeeId}/wallet/${buildQuery({ year, month })}`,
  );
