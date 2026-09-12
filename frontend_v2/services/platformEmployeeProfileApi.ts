/**
 * عميلُ بطاقة الموظّف الشخصيّة (التذكرة 211-Q) وأداء المحاور الخمسة الرسميّة
 * (#207 — التذكرة 211-J). هما النقطتان الوحيدتان بلا عميلٍ سابق على الإطلاق:
 * `/employees/{id}/performance/` كانت جاهزةً خادمياً منذ #207 ولا شاشةَ تستدعيها.
 *
 * **البقيّةُ عملاؤها قائمون فلا تُكرَّر هنا**: المستهدفان في
 * `platformEmployeeTargetsApi.ts`، تفصيلُ محاور الـpilot والمحفظة في
 * `platformPilotApi.ts`، وسجلُّ النشاط في `platformOpsApi.ts` — الدرجُ يستوردها
 * مباشرةً منها.
 */
import { apiGetObject, apiPatchObject, apiPostFormData } from "./restApi";

export interface EmployeeProfileCardInput {
  photo_url?: string;
  phone?: string;
  job_title?: string;
}

/** يطابق حقول `PlatformEmployeeSerializer` تماماً — يُفحص بحارس العقد. */
export interface PlatformEmployeeRow {
  id: number;
  user: number;
  username: string;
  email: string;
  specialty: string;
  capacity_target: string;
  monthly_units_target: string;
  photo_url: string;
  phone: string;
  job_title: string;
  status: "active" | "on_leave" | "offboarded";
  created_at: string;
  updated_at: string;
}

export const EMPLOYEE_STATUS_LABEL: Record<PlatformEmployeeRow["status"], string> = {
  active: "نشط",
  on_leave: "في إجازة",
  offboarded: "خارج الخدمة",
};

export const getPlatformEmployee = (employeeId: number) =>
  apiGetObject<PlatformEmployeeRow>(`platform/ops/employees/${employeeId}/`);

export const setEmployeeProfileCard = (employeeId: number, input: EmployeeProfileCardInput) =>
  apiPatchObject<PlatformEmployeeRow>(`platform/ops/employees/${employeeId}/profile-card/`, input);

export const uploadEmployeePhoto = (employeeId: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiPostFormData<{ photo_url: string }>(`platform/ops/employees/${employeeId}/photo/`, form);
};

/**
 * المحاور الخمسة الرسميّة (#207) — لا تُخلط بمحاور الـpilot الأربعة
 * (`PilotAxisKey` في `platformPilotApi.ts`): وحدتان مستقلّتان بتسميتَين مختلفتين
 * تماماً كما يفرضه `test_pilot_axis_keys_do_not_collide_with_207_axis_keys`.
 */
export type PerformanceAxisKey =
  | "kpi_results"
  | "quality"
  | "customer_rating"
  | "sla_compliance"
  | "attendance_regularity";

export const PERFORMANCE_AXES: PerformanceAxisKey[] = [
  "kpi_results",
  "quality",
  "customer_rating",
  "sla_compliance",
  "attendance_regularity",
];

export const PERFORMANCE_AXIS_LABELS: Record<PerformanceAxisKey, string> = {
  kpi_results: "نتائج الأداء (الإنتاجيّة المنجزة)",
  quality: "الجودة — نسبة القبول من أوّل مراجعة",
  customer_rating: "تقييم الزبون",
  sla_compliance: "الالتزام بالأجل",
  attendance_regularity: "الحضور والانضباط",
};

export interface PerformanceAxisBreakdown {
  applicable: boolean;
  weight_pct: number;
  score_pct: number;
  weighted_contribution: number;
}

export interface EmployeePerformance {
  status: "insufficient_data" | "calculated";
  status_message: string;
  composite_score: number | null;
  sample_size: number;
  min_sample_size: number;
  rework_rate: number | null;
  processed_sales_value: number;
  axes: Partial<Record<PerformanceAxisKey, PerformanceAxisBreakdown>>;
  weights_sum: number;
}

export const getEmployeePerformance = (employeeId: number, year?: number, month?: number) => {
  const params = new URLSearchParams();
  if (year) params.set("year", String(year));
  if (month) params.set("month", String(month));
  const qs = params.toString();
  return apiGetObject<EmployeePerformance>(
    `platform/ops/employees/${employeeId}/performance/${qs ? `?${qs}` : ""}`,
  );
};
