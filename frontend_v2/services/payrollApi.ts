/**
 * الرواتب — عميل REST رقيق حول restApi.
 *
 * الـbackend: `hr.payroll_api` — معزول بالشركة النشطة (X-Tenant-Id) لا بالمستخدم،
 * بخلاف المصاريف الشخصية. كل الأرقام المشتقّة (الاستحقاق، الخصومات، الصافي)
 * تأتي من الخادم ولا تُحتسب هنا: مصدر احتساب واحد لا اثنان يختلفان.
 */
import {
  apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject,
} from './restApi';
import { resolveTenantId } from '../utils/tenantContext';

export type PayType = 'monthly' | 'hourly';
export type PayslipStatus = 'draft' | 'posted';
export type AdjustmentKind = 'absence' | 'late';

export interface Employee {
  id: number;
  code: string;
  name: string;
  pay_type: PayType;
  pay_type_label: string;
  monthly_salary: string;
  hourly_rate: string;
  standard_hours_per_day: string;
  working_days_per_month: string;
  job_title: string;
  phone: string;
  national_id: string;
  hire_date: string | null;
  is_active: boolean;
  notes: string;
  user: number | null;
  account: number | null;
  account_code: string | null;
  account_name: string | null;
  balance: string;
  created_at: string;
  updated_at: string;
}

export interface WorkLog {
  id: number;
  employee: number;
  employee_name: string;
  date: string;
  hours: string;
  notes: string;
  created_at: string;
}

export interface AttendanceAdjustment {
  id: number;
  employee: number;
  employee_name: string;
  date: string;
  kind: AdjustmentKind;
  kind_label: string;
  days: string;
  minutes: number;
  is_deductible: boolean;
  notes: string;
  created_at: string;
}

export interface Payslip {
  id: number;
  employee: number;
  employee_name: string;
  period_start: string;
  period_end: string;
  pay_type: PayType;
  rate: string;
  worked_hours: string;
  absence_days: string;
  late_minutes: number;
  gross: string;
  allowances: string;
  absence_deduction: string;
  late_deduction: string;
  other_deductions: string;
  net: string;
  status: PayslipStatus;
  status_label: string;
  notes: string;
  posted_at: string | null;
  paid_total: string;
  created_at: string;
  updated_at: string;
}

export interface PayrollPayment {
  id: number;
  employee: number;
  employee_name: string;
  payslip: number | null;
  date: string;
  amount: string;
  cash_account: number | null;
  cash_account_name: string | null;
  notes: string;
  created_at: string;
}

/** أرقام الفترة قبل حفظ الكشف — كلها نصوص كما يرسلها الخادم. */
export type PayslipPreview = Pick<
  Payslip,
  | 'rate' | 'worked_hours' | 'absence_days' | 'gross' | 'allowances'
  | 'absence_deduction' | 'late_deduction' | 'other_deductions' | 'net'
> & { pay_type: PayType; late_minutes: string };

const opts = () => ({ tenantId: resolveTenantId() });

const queryOf = (filters: object) => {
  const q: Record<string, string> = {};
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === '' || value === null) return;
    q[key] = String(value);
  });
  return q;
};

/* — الموظفون — */

export interface EmployeeFilters {
  pay_type?: PayType | '';
  is_active?: 'true' | 'false' | '';
  search?: string;
}

export function listEmployees(filters: EmployeeFilters = {}): Promise<Employee[]> {
  return apiGetList<Employee>('hr/employees/', { ...opts(), query: queryOf(filters) });
}

export type EmployeeDraft = Partial<
  Pick<
    Employee,
    | 'code' | 'name' | 'pay_type' | 'monthly_salary' | 'hourly_rate'
    | 'standard_hours_per_day' | 'working_days_per_month' | 'job_title'
    | 'phone' | 'national_id' | 'hire_date' | 'is_active' | 'notes'
  >
>;

export function createEmployee(input: EmployeeDraft): Promise<Employee> {
  return apiPostObject<Employee>('hr/employees/', input, opts());
}

export function updateEmployee(id: number, patch: EmployeeDraft): Promise<Employee> {
  return apiPatchObject<Employee>(`hr/employees/${id}/`, patch, opts());
}

export function deleteEmployee(id: number): Promise<void> {
  return apiDelete(`hr/employees/${id}/`, opts());
}

export interface EmployeeStatement {
  employee: Employee;
  payslips: Payslip[];
  payments: PayrollPayment[];
  balance: string;
}

export function fetchEmployeeStatement(id: number): Promise<EmployeeStatement> {
  return apiGetObject<EmployeeStatement>(`hr/employees/${id}/statement/`, opts());
}

/* — ساعات العمل اليومية (الموظف الجزئي) — */

export interface DailyFilters {
  employee?: number | '';
  month?: string;
}

export function listWorkLogs(filters: DailyFilters = {}): Promise<WorkLog[]> {
  return apiGetList<WorkLog>('hr/work-logs/', { ...opts(), query: queryOf(filters) });
}

export function createWorkLog(input: {
  employee: number; date: string; hours: string; notes?: string;
}): Promise<WorkLog> {
  return apiPostObject<WorkLog>('hr/work-logs/', input, opts());
}

export function updateWorkLog(
  id: number, patch: Partial<Pick<WorkLog, 'date' | 'hours' | 'notes'>>,
): Promise<WorkLog> {
  return apiPatchObject<WorkLog>(`hr/work-logs/${id}/`, patch, opts());
}

export function deleteWorkLog(id: number): Promise<void> {
  return apiDelete(`hr/work-logs/${id}/`, opts());
}

/* — الغيابات والتأخيرات (الموظف الدائم) — */

export function listAdjustments(
  filters: DailyFilters & { kind?: AdjustmentKind | '' } = {},
): Promise<AttendanceAdjustment[]> {
  return apiGetList<AttendanceAdjustment>('hr/attendance-adjustments/', {
    ...opts(), query: queryOf(filters),
  });
}

export function createAdjustment(input: {
  employee: number; date: string; kind: AdjustmentKind;
  days?: string; minutes?: number; is_deductible?: boolean; notes?: string;
}): Promise<AttendanceAdjustment> {
  return apiPostObject<AttendanceAdjustment>('hr/attendance-adjustments/', input, opts());
}

export function deleteAdjustment(id: number): Promise<void> {
  return apiDelete(`hr/attendance-adjustments/${id}/`, opts());
}

/* — كشوف الرواتب — */

export interface PayslipFilters {
  employee?: number | '';
  month?: string;
  status?: PayslipStatus | '';
}

export function listPayslips(filters: PayslipFilters = {}): Promise<Payslip[]> {
  return apiGetList<Payslip>('hr/payslips/', { ...opts(), query: queryOf(filters) });
}

export function previewPayslip(input: {
  employee: number; period_start: string; period_end: string;
  allowances?: string; other_deductions?: string;
}): Promise<PayslipPreview> {
  const q = new URLSearchParams(queryOf(input)).toString();
  return apiGetObject<PayslipPreview>(`hr/payslips/preview/?${q}`, opts());
}

export function createPayslip(input: {
  employee: number; period_start: string; period_end: string;
  allowances?: string; other_deductions?: string; notes?: string;
}): Promise<Payslip> {
  return apiPostObject<Payslip>('hr/payslips/', input, opts());
}

export function updatePayslip(
  id: number,
  patch: Partial<Pick<Payslip, 'period_start' | 'period_end' | 'allowances' | 'other_deductions' | 'notes'>>,
): Promise<Payslip> {
  return apiPatchObject<Payslip>(`hr/payslips/${id}/`, patch, opts());
}

export function deletePayslip(id: number): Promise<void> {
  return apiDelete(`hr/payslips/${id}/`, opts());
}

export function postPayslip(id: number): Promise<Payslip> {
  return apiPostObject<Payslip>(`hr/payslips/${id}/post_slip/`, {}, opts());
}

export function unpostPayslip(id: number): Promise<Payslip> {
  return apiPostObject<Payslip>(`hr/payslips/${id}/unpost/`, {}, opts());
}

/* — صرف الرواتب — */

export function listPayrollPayments(filters: DailyFilters = {}): Promise<PayrollPayment[]> {
  return apiGetList<PayrollPayment>('hr/payroll-payments/', {
    ...opts(), query: queryOf(filters),
  });
}

export function createPayrollPayment(input: {
  employee: number; payslip?: number | null; date: string; amount: string;
  cash_account?: number | null; notes?: string;
}): Promise<PayrollPayment> {
  return apiPostObject<PayrollPayment>('hr/payroll-payments/', input, opts());
}

export function deletePayrollPayment(id: number): Promise<void> {
  return apiDelete(`hr/payroll-payments/${id}/`, opts());
}
