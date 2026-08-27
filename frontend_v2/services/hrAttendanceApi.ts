/**
 * T-HR M2/M3 — عميل REST للحضور والانصراف والخدمة الذاتية (وحدة `hr_suite`).
 *
 * الخادم يرد **404** لا 403 على شركةٍ غير مرخّصة (`hr/suite.py`).
 *
 * **ولا حساب هنا**: القبول الجغرافي وحدود اليوم والتأخير والإضافي كلّها خادمية
 * (`hr/attendance.py`). ما يفعله هذا الملف نقلُ أرقامٍ محسوبة، والاستثناء
 * الوحيد المعلَن هو عدّاد الثواني الحيّ — وهو يَعُدّ من لحظةٍ **يرسلها الخادم**
 * ولا يخترعها.
 */
import {
  apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostFormData, apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const LOCATIONS = "hr/work-locations/";
const SHIFTS = "hr/shifts/";
const ASSIGNMENTS = "hr/shift-assignments/";
const EVENTS = "hr/check-events/";
const DAYS = "hr/attendance-days/";
const ESS = "hr/ess/";

const tenantOpts = () => ({ tenantId: resolveTenantId() });

/** حالة اليوم — مرآة `AttendanceDay.STATUS_CHOICES` في الخادم. */
export type AttendanceStatus =
  | "present" | "late" | "absent" | "leave" | "holiday" | "off" | "unscheduled";

export const ATTENDANCE_STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: "حاضر",
  late: "متأخّر",
  absent: "غائب",
  leave: "إجازة",
  holiday: "عطلة رسمية",
  off: "عطلة أسبوعية",
  unscheduled: "بلا وردية",
};

/** أيام الأسبوع بترقيم `date.weekday()` — الاثنين 0 … الأحد 6، كما في الخادم. */
export const WEEKDAY_LABELS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"];

export interface WorkLocationRow {
  id: number;
  name: string;
  branch: number | null;
  branch_name: string | null;
  latitude: string | null;
  longitude: string | null;
  radius_m: number;
  require_geo: boolean;
  require_photo: boolean;
  allow_ip_fallback: boolean;
  ip_allowlist: string;
  is_active: boolean;
  notes: string;
}

export interface ShiftRow {
  id: number;
  name: string;
  start1: string;
  end1: string;
  start2: string | null;
  end2: string | null;
  grace_minutes: number;
  overtime_after_minutes: number;
  overtime_multiplier: string;
  weekly_off_days: number[];
  is_active: boolean;
}

export interface ShiftAssignmentRow {
  id: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  shift: number;
  shift_name: string;
  start_date: string;
  end_date: string | null;
  notes: string;
}

export interface CheckEventRow {
  id: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  kind: "in" | "out";
  kind_label: string;
  ts: string;
  attendance_date: string;
  source: "ess" | "manual" | "import";
  source_label: string;
  latitude: string | null;
  longitude: string | null;
  accuracy_m: number | null;
  distance_m: number | null;
  ip: string;
  photo_url: string;
  work_location: number | null;
  work_location_name: string | null;
  accepted: boolean;
  reject_reason: string;
  reject_label: string;
  is_voided: boolean;
  notes: string;
  created_at: string;
}

export interface AttendanceDayRow {
  id: number;
  employee: number;
  employee_name: string;
  employee_code: string;
  department_name: string | null;
  date: string;
  shift: number | null;
  shift_name: string | null;
  status: AttendanceStatus;
  status_label: string;
  worked_minutes: number;
  late_minutes: number;
  early_leave_minutes: number;
  overtime_minutes: number;
  scheduled_minutes: number;
  absence_days: string;
  first_in: string | null;
  last_out: string | null;
  is_manual_override: boolean;
  notes: string;
}

export interface EssSite {
  id: number;
  name: string;
  latitude: string | null;
  longitude: string | null;
  radius_m: number;
  require_geo: boolean;
  require_photo: boolean;
}

/** الجلسة المفتوحة — مصدر العدّاد الحيّ، ولحظتها خادمية. */
export interface EssOpenSession {
  event_id: number;
  since: string;
  attendance_date: string;
  server_now: string;
}

export interface EssToday {
  date: string;
  day: AttendanceDayRow | null;
  shift: {
    id: number; name: string; start1: string; end1: string;
    start2: string | null; end2: string | null; grace_minutes: number;
  } | null;
  open_session: EssOpenSession | null;
}

export interface EssMe {
  id: number;
  code: string;
  name: string;
  job_title: string;
  department_name: string;
  pay_type: string;
  work_location: EssSite | null;
  check_in_sites: EssSite[];
  requires_photo: boolean;
  requires_geo: boolean;
  today: EssToday;
}

export interface EssPunchResult {
  event: CheckEventRow;
  accepted: boolean;
  reject_reason: string;
  reject_label: string;
  today: EssToday;
}

export interface EssMonth {
  month: string;
  from: string;
  to: string;
  summary: {
    worked_minutes: number;
    overtime_minutes: number;
    late_minutes: number;
    present_days: number;
    absent_days: number;
    leave_days: number;
    expected_days: number;
    attendance_rate: number | null;
  };
  days: AttendanceDayRow[];
}

export interface EssScheduleRow {
  id: number;
  shift_name: string;
  start1: string;
  end1: string;
  start2: string | null;
  end2: string | null;
  weekly_off_days: number[];
  start_date: string;
  end_date: string | null;
  is_current: boolean;
}

// ── مواقع العمل ──────────────────────────────────────────────────────────

export const listWorkLocations = () =>
  apiGetList<WorkLocationRow>(LOCATIONS, tenantOpts());

export const createWorkLocation = (draft: Partial<WorkLocationRow>) =>
  apiPostObject<WorkLocationRow>(LOCATIONS, draft, tenantOpts());

export const updateWorkLocation = (id: number, draft: Partial<WorkLocationRow>) =>
  apiPatchObject<WorkLocationRow>(`${LOCATIONS}${id}/`, draft, tenantOpts());

export const deleteWorkLocation = (id: number) =>
  apiDelete(`${LOCATIONS}${id}/`, tenantOpts());

// ── الورديات والمناوبات ──────────────────────────────────────────────────

export const listShifts = () => apiGetList<ShiftRow>(SHIFTS, tenantOpts());

export const createShift = (draft: Partial<ShiftRow>) =>
  apiPostObject<ShiftRow>(SHIFTS, draft, tenantOpts());

export const updateShift = (id: number, draft: Partial<ShiftRow>) =>
  apiPatchObject<ShiftRow>(`${SHIFTS}${id}/`, draft, tenantOpts());

export const deleteShift = (id: number) => apiDelete(`${SHIFTS}${id}/`, tenantOpts());

export const listShiftAssignments = (params?: { employee?: number; shift?: number }) =>
  apiGetList<ShiftAssignmentRow>(ASSIGNMENTS, {
    ...tenantOpts(),
    query: { employee: params?.employee || undefined, shift: params?.shift || undefined },
  });

export const createShiftAssignment = (draft: Partial<ShiftAssignmentRow>) =>
  apiPostObject<ShiftAssignmentRow>(ASSIGNMENTS, draft, tenantOpts());

export const deleteShiftAssignment = (id: number) =>
  apiDelete(`${ASSIGNMENTS}${id}/`, tenantOpts());

// ── البصمات والأيام ──────────────────────────────────────────────────────

export interface AttendanceWindow {
  month?: string;
  from?: string;
  to?: string;
  employee?: number;
  department?: number;
  status?: AttendanceStatus;
}

export const listCheckEvents = (params: AttendanceWindow & { accepted?: boolean; source?: string }) =>
  apiGetList<CheckEventRow>(EVENTS, {
    ...tenantOpts(),
    query: {
      month: params.month || undefined,
      from: params.from || undefined,
      to: params.to || undefined,
      employee: params.employee || undefined,
      accepted: params.accepted === undefined ? undefined : params.accepted ? 1 : 0,
      source: params.source || undefined,
    },
  });

export const createManualPunch = (draft: {
  employee: number; kind: "in" | "out"; ts: string; notes?: string;
}) => apiPostObject<CheckEventRow>(EVENTS, draft, tenantOpts());

export const voidCheckEvent = (id: number, notes?: string) =>
  apiPostObject<CheckEventRow>(`${EVENTS}${id}/void/`, { notes: notes || "" }, tenantOpts());

export const listAttendanceDays = (params: AttendanceWindow) =>
  apiGetList<AttendanceDayRow>(DAYS, {
    ...tenantOpts(),
    query: {
      month: params.month || undefined,
      from: params.from || undefined,
      to: params.to || undefined,
      employee: params.employee || undefined,
      department: params.department || undefined,
      status: params.status || undefined,
    },
  });

export const overrideAttendanceDay = (
  id: number,
  draft: Partial<Pick<AttendanceDayRow, "status" | "worked_minutes" | "late_minutes"
    | "overtime_minutes" | "notes">> & { absence_days?: string; is_manual_override?: boolean },
) => apiPostObject<AttendanceDayRow>(`${DAYS}${id}/override/`, draft, tenantOpts());

export interface AttendanceImportResult {
  dry_run: boolean;
  created: number;
  days: number;
  errors: { row: number; message: string }[];
  error_count: number;
}

/**
 * استيراد سجل حضورٍ من CSV (مخرَج أجهزة البصمة وجداول Excel).
 *
 * `dryRun` يفحص الملف ويعدّ أخطاءه بلا كتابة — الاستيراد الأعمى في سجلٍّ لا
 * يُحذف منه شيء خطأٌ لا يُتراجَع عنه بسهولة.
 */
export const importAttendanceCsv = (file: File, dryRun: boolean) => {
  const form = new FormData();
  form.append("file", file);
  if (dryRun) form.append("dry_run", "true");
  return apiPostFormData<AttendanceImportResult>(`${DAYS}import/`, form, tenantOpts());
};

export const recomputeAttendance = (params: { from: string; to: string; employee?: number }) =>
  apiPostObject<{ recomputed: number; from: string; to: string }>(
    `${DAYS}recompute/`, params, tenantOpts());

// ── الخدمة الذاتية ───────────────────────────────────────────────────────

export const fetchEssMe = () => apiGetObject<EssMe>(`${ESS}me/`, tenantOpts());

export const fetchEssToday = () => apiGetObject<EssToday>(`${ESS}my-day/`, tenantOpts());

export const fetchEssMonth = (month?: string) =>
  apiGetObject<EssMonth>(
    `${ESS}my-month/${month ? `?month=${encodeURIComponent(month)}` : ""}`, tenantOpts());

export const fetchEssSchedule = () =>
  apiGetList<EssScheduleRow>(`${ESS}my-schedule/`, tenantOpts());

export const essPunch = (
  kind: "in" | "out",
  payload: { lat?: number; lng?: number; accuracy?: number; photo_url?: string },
) => apiPostObject<EssPunchResult>(
  `${ESS}${kind === "in" ? "check-in" : "check-out"}/`, payload, tenantOpts());

/** يفتح للموظف حساب خدمة ذاتية أو يفصله — مدخله كرت الموظف. */
export const setEssAccess = (employeeId: number, body: { username?: string; detach?: boolean }) =>
  apiPostObject<Record<string, unknown>>(
    `hr/employees/${employeeId}/ess-access/`, body, tenantOpts());
