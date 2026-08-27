/**
 * T-HR M5/M6/M7 — عميل REST للطلبات والإجازات والعقود ومسير الرواتب.
 *
 * الخادم يرد **404** لا 403 على شركةٍ غير مرخّصة (`hr/suite.py`).
 *
 * **ولا حالةَ تُكتب هنا بـPATCH**: الطلب يتحرّك بأفعالٍ صريحة
 * (`submit`/`approve`/`reject`/`cancel`)، والعقد بـ`activate`/`terminate` —
 * كما في الخادم بالضبط، فلا آلةَ حالاتٍ ثانية في الواجهة تنزاح عن الأولى.
 */
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const REQUESTS = "hr/requests/";
const LEAVE_TYPES = "hr/leave-types/";
const HOLIDAYS = "hr/holidays/";
const ADJUSTMENTS = "hr/leave-adjustments/";
const RULES = "hr/approval-rules/";
const ADVANCES = "hr/advances/";
const CONTRACTS = "hr/contracts/";
const RUNS = "hr/payroll-runs/";

const tenantOpts = () => ({ tenantId: resolveTenantId() });

export type RequestKind = "leave" | "advance" | "expense" | "other";
export type RequestStatus = "draft" | "pending" | "approved" | "rejected" | "cancelled";

export const REQUEST_KIND_LABELS: Record<RequestKind, string> = {
  leave: "إجازة",
  advance: "سلفة",
  expense: "تسوية مصروف",
  other: "طلب آخر",
};

export const REQUEST_STATUS_LABELS: Record<RequestStatus, string> = {
  draft: "مسودّة",
  pending: "قيد المراجعة",
  approved: "موافق",
  rejected: "مرفوض",
  cancelled: "ملغى",
};

export interface ApprovalStepRow {
  id: number;
  level: number;
  approver_user: number | null;
  approver_name: string | null;
  status: "pending" | "approved" | "rejected";
  status_label: string;
  acted_by_name: string | null;
  acted_at: string | null;
  note: string;
}

export interface EmployeeRequestRow {
  id: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  kind: RequestKind;
  kind_label: string;
  status: RequestStatus;
  status_label: string;
  leave_type: number | null;
  leave_type_name: string | null;
  date_from: string | null;
  date_to: string | null;
  days: string;
  amount: string | null;
  installments: number | null;
  description: string;
  attachment_url: string;
  execution_date: string | null;
  decided_at: string | null;
  decision_note: string;
  steps: ApprovalStepRow[];
  created_at: string;
}

export interface LeaveTypeRow {
  id: number;
  name: string;
  is_paid: boolean;
  annual_grant: string;
  monthly_accrual: string;
  max_days_per_request: number;
  requires_balance: boolean;
  is_active: boolean;
}

export interface HolidayRow {
  id: number;
  date: string;
  name: string;
}

export interface ApprovalRuleRow {
  id: number;
  kind: string;
  department: number | null;
  department_name: string | null;
  branch: number | null;
  branch_name: string | null;
  level: number;
  approver_user: number | null;
  approver_name: string | null;
  is_active: boolean;
}

export interface LeaveBalanceRow {
  employee: number;
  employee_name: string;
  employee_code: string;
  balances: {
    leave_type: number;
    leave_type_name: string;
    is_paid: boolean;
    year: number;
    accrued: string;
    adjusted: string;
    taken: string;
    remaining: string;
  }[];
}

export interface AdvanceRow {
  id: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  request: number | null;
  date: string;
  total: string;
  monthly_installment: string;
  remaining: string;
  status: "open" | "settled" | "cancelled";
  status_label: string;
  is_disbursed: boolean;
  notes: string;
}

export interface ContractComponentRow {
  id?: number;
  kind: "earning" | "deduction";
  kind_label?: string;
  name: string;
  amount: string;
  position?: number;
}

export interface ContractRow {
  id: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  start_date: string;
  end_date: string | null;
  pay_type: "monthly" | "hourly";
  pay_type_label: string;
  monthly_salary: string;
  hourly_rate: string;
  overtime_multiplier: string | null;
  status: "draft" | "active" | "expired" | "terminated";
  status_label: string;
  job_title: string;
  notes: string;
  document_url: string;
  components: ContractComponentRow[];
  days_to_expiry: number | null;
}

export interface ContractAlerts {
  within_days: number;
  count: number;
  contracts: {
    id: number; employee: number; employee_name: string;
    end_date: string; days_to_expiry: number | null;
  }[];
}

export interface PayrollRunRow {
  id: number;
  name: string;
  period_start: string;
  period_end: string;
  branch: number | null;
  branch_name: string | null;
  department: number | null;
  department_name: string | null;
  status: "draft" | "computed" | "posted";
  status_label: string;
  notes: string;
  payslip_count: number;
  total_net: string | null;
  posted_at: string | null;
}

// ── الطلبات ─────────────────────────────────────────────────────────────

export const listRequests = (params?: {
  scope?: "mine" | "inbox";
  status?: RequestStatus;
  kind?: RequestKind;
  employee?: number;
}) => apiGetList<EmployeeRequestRow>(REQUESTS, {
  ...tenantOpts(),
  query: {
    scope: params?.scope || undefined,
    status: params?.status || undefined,
    kind: params?.kind || undefined,
    employee: params?.employee || undefined,
  },
});

export const createRequest = (draft: Partial<EmployeeRequestRow>) =>
  apiPostObject<EmployeeRequestRow>(REQUESTS, draft, tenantOpts());

export const updateRequest = (id: number, draft: Partial<EmployeeRequestRow>) =>
  apiPatchObject<EmployeeRequestRow>(`${REQUESTS}${id}/`, draft, tenantOpts());

export const deleteRequest = (id: number) => apiDelete(`${REQUESTS}${id}/`, tenantOpts());

const requestAction = (id: number, verb: string, body: Record<string, unknown> = {}) =>
  apiPostObject<EmployeeRequestRow>(`${REQUESTS}${id}/${verb}/`, body, tenantOpts());

export const submitRequest = (id: number) => requestAction(id, "submit");
export const approveRequest = (id: number, note?: string) =>
  requestAction(id, "approve", { note: note || "" });
export const rejectRequest = (id: number, note?: string) =>
  requestAction(id, "reject", { note: note || "" });
export const cancelRequest = (id: number) => requestAction(id, "cancel");

// ── الإجازات ────────────────────────────────────────────────────────────

export const listLeaveTypes = () => apiGetList<LeaveTypeRow>(LEAVE_TYPES, tenantOpts());
export const createLeaveType = (draft: Partial<LeaveTypeRow>) =>
  apiPostObject<LeaveTypeRow>(LEAVE_TYPES, draft, tenantOpts());
export const updateLeaveType = (id: number, draft: Partial<LeaveTypeRow>) =>
  apiPatchObject<LeaveTypeRow>(`${LEAVE_TYPES}${id}/`, draft, tenantOpts());
export const deleteLeaveType = (id: number) => apiDelete(`${LEAVE_TYPES}${id}/`, tenantOpts());

export const listHolidays = (year?: number) =>
  apiGetList<HolidayRow>(HOLIDAYS, { ...tenantOpts(), query: { year: year || undefined } });
export const createHoliday = (draft: Partial<HolidayRow>) =>
  apiPostObject<HolidayRow>(HOLIDAYS, draft, tenantOpts());
export const deleteHoliday = (id: number) => apiDelete(`${HOLIDAYS}${id}/`, tenantOpts());

export const listLeaveBalances = (employee?: number) =>
  apiGetList<LeaveBalanceRow>(`${ADJUSTMENTS}balances/`, {
    ...tenantOpts(), query: { employee: employee || undefined },
  });

export const createLeaveAdjustment = (draft: {
  employee: number; leave_type: number; date: string; days: string; notes?: string;
}) => apiPostObject<Record<string, unknown>>(ADJUSTMENTS, draft, tenantOpts());

export const listApprovalRules = () => apiGetList<ApprovalRuleRow>(RULES, tenantOpts());
export const createApprovalRule = (draft: Partial<ApprovalRuleRow>) =>
  apiPostObject<ApprovalRuleRow>(RULES, draft, tenantOpts());
export const deleteApprovalRule = (id: number) => apiDelete(`${RULES}${id}/`, tenantOpts());

// ── السلف ───────────────────────────────────────────────────────────────

export const listAdvances = (params?: { employee?: number; status?: string }) =>
  apiGetList<AdvanceRow>(ADVANCES, {
    ...tenantOpts(),
    query: { employee: params?.employee || undefined, status: params?.status || undefined },
  });

export const disburseAdvance = (id: number, body: { cash_account?: number; date?: string }) =>
  apiPostObject<AdvanceRow>(`${ADVANCES}${id}/disburse/`, body, tenantOpts());

export const cancelAdvance = (id: number) =>
  apiPostObject<AdvanceRow>(`${ADVANCES}${id}/cancel/`, {}, tenantOpts());

// ── العقود ──────────────────────────────────────────────────────────────

export const listContracts = (params?: {
  employee?: number; status?: string; expiring?: number;
}) => apiGetList<ContractRow>(CONTRACTS, {
  ...tenantOpts(),
  query: {
    employee: params?.employee || undefined,
    status: params?.status || undefined,
    expiring: params?.expiring || undefined,
  },
});

export const createContract = (draft: Partial<ContractRow>) =>
  apiPostObject<ContractRow>(CONTRACTS, draft, tenantOpts());

export const updateContract = (id: number, draft: Partial<ContractRow>) =>
  apiPatchObject<ContractRow>(`${CONTRACTS}${id}/`, draft, tenantOpts());

export const deleteContract = (id: number) => apiDelete(`${CONTRACTS}${id}/`, tenantOpts());

export const activateContract = (id: number) =>
  apiPostObject<ContractRow>(`${CONTRACTS}${id}/activate/`, {}, tenantOpts());

export const terminateContract = (id: number, body: { end_date?: string; notes?: string }) =>
  apiPostObject<ContractRow>(`${CONTRACTS}${id}/terminate/`, body, tenantOpts());

export const fetchContractAlerts = (within = 30) =>
  apiGetObject<ContractAlerts>(`${CONTRACTS}alerts/?within=${within}`, tenantOpts());

// ── مسير الرواتب ────────────────────────────────────────────────────────

export const listPayrollRuns = () => apiGetList<PayrollRunRow>(RUNS, tenantOpts());

export const createPayrollRun = (draft: Partial<PayrollRunRow>) =>
  apiPostObject<PayrollRunRow>(RUNS, draft, tenantOpts());

export const deletePayrollRun = (id: number) => apiDelete(`${RUNS}${id}/`, tenantOpts());

export interface RunComputeResult {
  created: number;
  updated: number;
  skipped: { employee: number; name: string; reason: string }[];
}

export interface RunPostResult {
  posted?: number;
  reverted?: number;
  failed: { payslip: number; employee_name: string; reason: string }[];
  status: string;
}

export const computePayrollRun = (id: number) =>
  apiPostObject<RunComputeResult>(`${RUNS}${id}/compute/`, {}, tenantOpts());

export const postPayrollRun = (id: number) =>
  apiPostObject<RunPostResult>(`${RUNS}${id}/post/`, {}, tenantOpts());

export const unpostPayrollRun = (id: number) =>
  apiPostObject<RunPostResult>(`${RUNS}${id}/unpost/`, {}, tenantOpts());

export const listRunPayslips = (id: number) =>
  apiGetList<Record<string, unknown>>(`${RUNS}${id}/payslips/`, tenantOpts());
