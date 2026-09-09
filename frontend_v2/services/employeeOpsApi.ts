/**
 * عميل REST لوحدة متابعة الموظفين (employee_ops).
 *
 * الخادم employee_ops/urls.py يفتح المسارات تحت /api/employee-ops/.
 * الترخيص يُفحص قبل الصلاحية فيردّ الخادم 404 للشركة غير المرخصة.
 * كل دالة تمرر الأخطاء دون ابتلاع لتظهر في رسائل useToast.
 */
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const BASE = "employee-ops";

const tenantOpts = (tenantId?: number) => ({
  tenantId: tenantId ?? resolveTenantId(),
});

// ── الأنواع ونماذج البيانات (DTOs) ──────────────────────────────────────────

export interface EmployeeOpsSettingsDto {
  id?: number;
  tenant?: number;
  points_full: number;
  points_partial: number;
  points_attendance: number;
  attendance_daily_cap: number;
  leaderboard_highlight_count: number;
  rejected_retention_months: number;
  invitation_expiry_days: number;
  created_at?: string;
  updated_at?: string;
}

export interface EmployeeDto {
  id: number;
  name: string;
  code: string;
  phone: string;
  job_title: string;
  is_active: boolean;
  has_account: boolean;
  manager: number | null;
  manager_name: string | null;
  invitation_status: "pending" | "accepted" | "none";
  /** أيستطيع الدخولَ الآن؟ عضويّةٌ حيّةٌ في الشركة — لا مجرّدُ وجودِ حساب. */
  has_membership: boolean;
  /** عدّاداتٌ تُحسب في استعلام القائمة نفسه — لا نداءَ كرتٍ لكلّ صفّ. */
  open_tasks: number;
  overdue_tasks: number;
  month_points: number;
  /** وقتُ آخر حدثٍ للموظف في المنصة، أو null لمن لا حسابَ له. */
  last_activity: string | null;
}

/**
 * كرتُ الموظف: حقولُ القائمة **ناقصةً** ما تحسبه القائمةُ وحدها.
 * `employee_card()` لا يُعيد `has_membership` ولا `last_activity`، فمساواةُ
 * النوعين كانت تَعِد بحقلين غيرِ موجودَين — و`tsc` هنا لا يكشف ذلك في JSX.
 */
export type EmployeeCardDto = Omit<EmployeeDto, "has_membership" | "last_activity">;

export interface EmployeeInvitationDto {
  id: number;
  tenant: number;
  employee: number;
  employee_name: string;
  status: "pending" | "accepted" | "cancelled" | "expired";
  expires_at: string;
  created_by: number | null;
  created_at: string;
  accepted_at: string | null;
  accepted_user: number | null;
}

export interface CreateEmployeeResponse {
  employee: EmployeeDto;
  invitation: EmployeeInvitationDto;
  raw_token: string;
  invitation_url: string;
}

export interface EmployeeNoteDto {
  id: number;
  employee: number;
  body: string;
  author: number | null;
  author_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityEventDto {
  id: number;
  action: string;
  entity_type: string;
  entity_id: number | null;
  entity_label: string;
  description: string;
  timestamp: string;
}

export interface TaskAssignmentDto {
  id: number;
  tenant: number;
  task: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  status: "not_started" | "in_progress" | "submitted" | "completed" | "rejected";
  started_at: string | null;
  completed_at: string | null;
  work_started_at: string | null;
  total_work_seconds: number;
  extra?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface TaskSubmissionAttachmentDto {
  id?: number;
  url: string;
  name?: string;
  position?: number;
  created_at?: string;
}

export interface TaskSubmissionItemDto {
  id?: number;
  product_link?: string;
  product_price?: string | number | null;
  notes?: string;
  attachment_url?: string;
  attachment_name?: string;
  images?: string[];
  position?: number;
  created_at?: string;
}

export interface TaskSubmissionDto {
  id: number;
  tenant: number;
  task: number;
  employee: number;
  employee_name: string;
  body: string;
  decision: "pending" | "approved_full" | "approved_partial" | "rejected";
  reviewer: number | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  reviewer_notes: string;
  items: TaskSubmissionItemDto[];
  attachments: TaskSubmissionAttachmentDto[];
  extra?: Record<string, any>;
  source_path?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskDto {
  id: number;
  tenant: number;
  title: string;
  description: string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "URGENT";
  status: "NEW" | "IN_PROGRESS" | "WAITING_FOR_REVIEW" | "COMPLETED" | "REJECTED" | "ACCEPTED";
  due_date: string | null;
  category: string;
  tags: string[];
  target_price: string | number | null;
  allowed_sites: string[];
  created_by: number | null;
  created_by_name: string | null;
  completed_at: string | null;
  assignments: TaskAssignmentDto[];
  my_assignment: TaskAssignmentDto | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskDto {
  title: string;
  description?: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "URGENT";
  due_date?: string | null;
  category?: string;
  tags?: string[];
  target_price?: number | string | null;
  allowed_sites?: string[];
  assignee_ids?: number[];
}

export interface UpdateTaskDto {
  title?: string;
  description?: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "URGENT";
  due_date?: string | null;
  category?: string;
  tags?: string[];
  target_price?: number | string | null;
  allowed_sites?: string[];
  assignee_ids?: number[];
}

export interface PointEntryDto {
  id: number;
  employee: number;
  employee_name: string;
  points: number;
  source: "task_full" | "task_partial" | "attendance" | "manual" | "reversal";
  awarded_on: string;
  submission: number | null;
  reverses: number | null;
  reason: string;
  created_by: number | null;
  created_at: string;
}

export interface PointsSummaryDto {
  employee: number | null;
  employee_name: string;
  points: number;
  rank: number | null;
  open_tasks_count: number;
}

export interface AttendanceCheckInResultDto {
  points_awarded: number;
  today_points: number;
  daily_cap: number;
  capped: boolean;
}

export interface LeaderboardEntryDto {
  employee: number;
  employee_name: string;
  points: number;
  rank: number;
}

export interface LeaderboardDto {
  month: string;
  highlight_count: number;
  results: LeaderboardEntryDto[];
}

// ── دوال الـ API ─────────────────────────────────────────────────────────────

// 1) الإعدادات
export async function getEmployeeOpsSettings(tenantId?: number): Promise<EmployeeOpsSettingsDto> {
  return apiGetObject<EmployeeOpsSettingsDto>(`${BASE}/settings/`, tenantOpts(tenantId));
}

export async function updateEmployeeOpsSettings(
  data: Partial<EmployeeOpsSettingsDto>,
  tenantId?: number,
): Promise<EmployeeOpsSettingsDto> {
  return apiPatchObject<EmployeeOpsSettingsDto>(`${BASE}/settings/`, data, tenantOpts(tenantId));
}

// 2) الموظفون
export async function listEmployees(tenantId?: number): Promise<EmployeeDto[]> {
  const res = await apiGetList<EmployeeDto>(`${BASE}/employees/`, tenantOpts(tenantId));
  return res;
}


export async function createEmployee(
  data: {
    name: string;
    phone?: string;
    job_title?: string;
    manager?: number | null;
  },
  tenantId?: number,
): Promise<CreateEmployeeResponse> {
  return apiPostObject<CreateEmployeeResponse>(`${BASE}/employees/`, data, tenantOpts(tenantId));
}

export async function updateEmployee(
  id: number,
  data: {
    name?: string;
    phone?: string;
    job_title?: string;
    manager?: number | null;
  },
  tenantId?: number,
): Promise<EmployeeDto> {
  return apiPatchObject<EmployeeDto>(`${BASE}/employees/${id}/`, data, tenantOpts(tenantId));
}

export async function inviteEmployee(
  id: number,
  tenantId?: number,
): Promise<{ invitation: EmployeeInvitationDto; raw_token: string; invitation_url: string }> {
  return apiPostObject<{ invitation: EmployeeInvitationDto; raw_token: string; invitation_url: string }>(
    `${BASE}/employees/${id}/invite/`,
    {},
    tenantOpts(tenantId),
  );
}

export async function deactivateEmployee(
  id: number,
  tenantId?: number,
): Promise<{ status: string; id: number }> {
  return apiPostObject<{ status: string; id: number }>(
    `${BASE}/employees/${id}/deactivate/`,
    {},
    tenantOpts(tenantId),
  );
}

export async function reactivateEmployee(
  id: number,
  tenantId?: number,
): Promise<{ status: string; id: number }> {
  return apiPostObject<{ status: string; id: number }>(
    `${BASE}/employees/${id}/reactivate/`,
    {},
    tenantOpts(tenantId),
  );
}

export async function getEmployeeCard(id: number, tenantId?: number): Promise<EmployeeCardDto> {
  return apiGetObject<EmployeeCardDto>(`${BASE}/employees/${id}/card/`, tenantOpts(tenantId));
}

export async function getEmployeeActivity(
  id: number,
  params?: { date_from?: string; date_to?: string },
  tenantId?: number,
): Promise<{ limit: number; results: ActivityEventDto[] }> {
  return apiGetObject<{ limit: number; results: ActivityEventDto[] }>(
    `${BASE}/employees/${id}/activity/`,
    {
      ...tenantOpts(tenantId),
      query: params,
    },
  );
}

// 3) الملاحظات
export async function listEmployeeNotes(employeeId: number, tenantId?: number): Promise<EmployeeNoteDto[]> {
  const res = await apiGetList<EmployeeNoteDto>(`${BASE}/notes/`, {
    ...tenantOpts(tenantId),
    query: { employee: employeeId },
  });
  return res;
}

export async function createEmployeeNote(
  employeeId: number,
  body: string,
  tenantId?: number,
): Promise<EmployeeNoteDto> {
  return apiPostObject<EmployeeNoteDto>(
    `${BASE}/notes/`,
    { employee: employeeId, body },
    tenantOpts(tenantId),
  );
}

// 4) الدعوات
export async function listPendingInvitations(tenantId?: number): Promise<EmployeeInvitationDto[]> {
  const res = await apiGetList<EmployeeInvitationDto>(`${BASE}/invitations/`, tenantOpts(tenantId));
  return res;
}

export async function resendInvitation(
  id: number,
  tenantId?: number,
): Promise<{ invitation: EmployeeInvitationDto; raw_token: string; invitation_url: string }> {
  return apiPostObject<{ invitation: EmployeeInvitationDto; raw_token: string; invitation_url: string }>(
    `${BASE}/invitations/${id}/resend/`,
    {},
    tenantOpts(tenantId),
  );
}

export async function cancelInvitation(
  id: number,
  tenantId?: number,
): Promise<{ invitation: EmployeeInvitationDto }> {
  return apiPostObject<{ invitation: EmployeeInvitationDto }>(
    `${BASE}/invitations/${id}/cancel/`,
    {},
    tenantOpts(tenantId),
  );
}

// 5) المهام
export async function listTasks(tenantId?: number): Promise<TaskDto[]> {
  const res = await apiGetList<TaskDto>(`${BASE}/tasks/`, tenantOpts(tenantId));
  return res;
}

export async function listMyTasks(tenantId?: number): Promise<TaskDto[]> {
  const res = await apiGetList<TaskDto>(`${BASE}/tasks/mine/`, tenantOpts(tenantId));
  return res;
}

export async function getTask(id: number, tenantId?: number): Promise<TaskDto> {
  return apiGetObject<TaskDto>(`${BASE}/tasks/${id}/`, tenantOpts(tenantId));
}

export async function createTask(data: CreateTaskDto, tenantId?: number): Promise<TaskDto> {
  return apiPostObject<TaskDto>(`${BASE}/tasks/`, data, tenantOpts(tenantId));
}

export async function updateTask(id: number, data: UpdateTaskDto, tenantId?: number): Promise<TaskDto> {
  return apiPatchObject<TaskDto>(`${BASE}/tasks/${id}/`, data, tenantOpts(tenantId));
}

export async function deleteTask(id: number, tenantId?: number): Promise<void> {
  return apiDelete(`${BASE}/tasks/${id}/`, tenantOpts(tenantId));
}

export async function startTaskTimer(id: number, tenantId?: number): Promise<TaskAssignmentDto> {
  return apiPostObject<TaskAssignmentDto>(`${BASE}/tasks/${id}/start/`, {}, tenantOpts(tenantId));
}

export async function stopTaskTimer(id: number, tenantId?: number): Promise<TaskAssignmentDto> {
  return apiPostObject<TaskAssignmentDto>(`${BASE}/tasks/${id}/stop/`, {}, tenantOpts(tenantId));
}

export async function submitTask(
  id: number,
  data: {
    body?: string;
    items?: Array<{
      product_link?: string;
      product_price?: number | string | null;
      notes?: string;
      attachment_url?: string;
      attachment_name?: string;
      images?: string[];
      position?: number;
    }>;
    attachments?: Array<{
      url: string;
      name?: string;
      position?: number;
    }>;
  },
  tenantId?: number,
): Promise<TaskSubmissionDto> {
  return apiPostObject<TaskSubmissionDto>(`${BASE}/tasks/${id}/submit/`, data, tenantOpts(tenantId));
}

// 6) التسليمات والمراجعة
/**
 * تسليماتُ الشركة، مُفلترةً **في الخادم**.
 * جلبُ الكلّ ثمّ الفلترةُ في المتصفّح كان يُنزل سجلَّ التسليمات كاملاً — بنصوصه
 * وبنوده ومرفقاته — لفتحِ مهمّةٍ واحدة.
 */
export async function listSubmissions(
  params?: { task?: number; decision?: "pending" | "approved_full" | "approved_partial" | "rejected" },
  tenantId?: number,
): Promise<TaskSubmissionDto[]> {
  const res = await apiGetList<TaskSubmissionDto>(`${BASE}/submissions/`, {
    ...tenantOpts(tenantId),
    query: params,
  });
  return res;
}


export async function reviewSubmission(
  id: number,
  data: {
    decision: "approved_full" | "approved_partial" | "rejected";
    reviewer_notes?: string;
  },
  tenantId?: number,
): Promise<TaskSubmissionDto> {
  return apiPostObject<TaskSubmissionDto>(`${BASE}/submissions/${id}/review/`, data, tenantOpts(tenantId));
}

export async function unreviewSubmission(
  id: number,
  data: { reason: string },
  tenantId?: number,
): Promise<TaskSubmissionDto> {
  return apiPostObject<TaskSubmissionDto>(`${BASE}/submissions/${id}/unreview/`, data, tenantOpts(tenantId));
}

// 7) النقاط والحضور ولوحة الشرف
export async function listPoints(
  params?: { month?: string; employee?: number },
  tenantId?: number,
): Promise<PointEntryDto[]> {
  const res = await apiGetList<PointEntryDto>(`${BASE}/points/`, {
    ...tenantOpts(tenantId),
    query: params,
  });
  return res;
}

export async function getPointsSummary(tenantId?: number): Promise<PointsSummaryDto> {
  return apiGetObject<PointsSummaryDto>(`${BASE}/points/summary/`, tenantOpts(tenantId));
}

export async function recordManualPoints(
  data: { employee: number; points: number; reason: string },
  tenantId?: number,
): Promise<PointEntryDto> {
  return apiPostObject<PointEntryDto>(`${BASE}/points/manual/`, data, tenantOpts(tenantId));
}

export async function checkInAttendance(tenantId?: number): Promise<AttendanceCheckInResultDto> {
  return apiPostObject<AttendanceCheckInResultDto>(`${BASE}/attendance/check-in/`, {}, tenantOpts(tenantId));
}

export async function getLeaderboard(
  params?: { month?: string },
  tenantId?: number,
): Promise<LeaderboardDto> {
  return apiGetObject<LeaderboardDto>(`${BASE}/leaderboard/`, {
    ...tenantOpts(tenantId),
    query: params,
  });
}
