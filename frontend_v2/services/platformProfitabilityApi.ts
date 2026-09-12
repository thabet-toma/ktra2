/**
 * ربحيّةُ العميل ومطابقةُ الخطة — `GET /api/platform/ops/profitability/` (§٩ من #210).
 *
 * ملفٌّ منفصلٌ عن `platformEmployeeSpaceApi.ts` عمداً: جمهورُ تلك مساحةُ الموظّف،
 * وهذه نقطةُ مديرٍ تحمل إيراداً وتكلفةً مشتقّةً من الرواتب. وخلطُهما كان سيُغري
 * باستيرادِ الربحيّة في شاشةِ موظّفٍ بلا صلاحيّة، فتُرى 403 حيث لا ينبغي طلبٌ أصلاً.
 */
import { apiGetObject } from "./restApi";

export type ProfitabilityState = "profitable" | "watch" | "reprice_or_upgrade" | "losing";

export type PlanFitCode =
  | "upgrade_plan"
  | "buy_extra_units"
  | "adjust_sla"
  | "request_customer_data"
  | "health_remediation_plan";

export interface ProfitabilityContributor {
  employee_id: number;
  units: number;
  unit_cost: number;
  cost: number;
}

export interface PlanFitSuggestion {
  code: PlanFitCode;
  label: string;
  reason: string;
  evidence: Record<string, number | null>;
}

export interface ProfitabilityRow {
  tenant_id: number;
  company_name: string;
  period_year: number;
  period_month: number;
  revenue: number;
  monthly_fee: number;
  included_quota: number;
  chargeable_units: number;
  overage_units: number;
  human_cost: number;
  allocated_expenses: number;
  total_cost: number;
  margin: number;
  /** `null` حين يكون الإيرادُ صفراً — النسبةُ غيرُ معرَّفةٍ لا صفر. */
  margin_pct: number | null;
  state: ProfitabilityState;
  state_label: string;
  contributors: ProfitabilityContributor[];
  suggestions: PlanFitSuggestion[];
}

export interface ProfitabilityBoard {
  period_year: number;
  period_month: number;
  allocated_expenses_per_tenant: number;
  rows: ProfitabilityRow[];
}

export const getCustomerProfitability = (
  year: number,
  month: number,
  allocatedExpenses = 0,
): Promise<ProfitabilityBoard> =>
  apiGetObject<ProfitabilityBoard>(
    `platform/ops/profitability/?year=${year}&month=${month}&allocated_expenses=${allocatedExpenses}`,
  );
