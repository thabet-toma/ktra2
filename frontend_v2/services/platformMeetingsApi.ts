/**
 * عميلُ واجهة برمجة تطبيقات اجتماعات المنصّة (التذكرة 211-G، تكمل الخادمَ 211-F).
 *
 * عشرُ نقاطٍ على `PlatformMeetingViewSet` تحت `/api/platform/ops/meetings/` —
 * القراءةُ مضيَّقةٌ خادمياً حسب الجمهور (مديرٌ يرى الكلّ، موظّفٌ يرى اجتماعاتِه)،
 * فلا تفلترُ هذه الواجهةُ ثانيةً.
 */
import { apiGetObject, apiPostObject } from "./restApi";
import type { MyPlatformEmployeeProfile } from "./platformEmployeeSpaceApi";

export type PlatformMeetingStatus = "scheduled" | "cancelled" | "finished";

export type MeetingAttendanceStatus =
  | "attended"
  | "absent"
  | "excused_pending"
  | "excused_accepted"
  | "excused_rejected";

/** تسمياتٌ عربيّةٌ بتهجئة `PlatformMeeting.Status` الخادميّة — مصدرٌ واحد لكل الشاشات. */
export const MEETING_STATUS_LABEL: Record<PlatformMeetingStatus, string> = {
  scheduled: "مجدول",
  cancelled: "ملغى",
  finished: "منتهٍ",
};

/** تسمياتٌ عربيّةٌ بتهجئة `PlatformMeetingAttendance.Status` الخادميّة. */
export const MEETING_ATTENDANCE_STATUS_LABEL: Record<MeetingAttendanceStatus, string> = {
  attended: "حضر",
  absent: "غائب",
  excused_pending: "عذر بانتظار البتّ",
  excused_accepted: "عذر مقبول",
  excused_rejected: "عذر مرفوض",
};

export interface PlatformMeetingRow {
  id: number;
  title: string;
  agenda: string;
  start: string;
  end: string;
  meeting_link: string;
  status: PlatformMeetingStatus;
  status_display: string;
  created_by_name: string;
  invited_count: number;
  /** حالةُ صاحبِ الجلسة نفسِه في هذا الاجتماع — `null` لمن ليس موظّفَ منصّةٍ أو غير مدعوّ. */
  my_attendance_status: MeetingAttendanceStatus | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformMeetingAttendanceRow {
  id: number;
  meeting: number;
  employee: number;
  employee_name: string;
  status: MeetingAttendanceStatus;
  status_display: string;
  checked_in_at: string | null;
  excuse_note: string;
  excuse_decided_by_name: string;
  excuse_decided_at: string | null;
  created_at: string;
  updated_at: string;
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

export const listPlatformMeetings = async (): Promise<PlatformMeetingRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: PlatformMeetingRow[]; count?: number } | PlatformMeetingRow[]>(
      "platform/ops/meetings/",
    ),
  );

export interface CreatePlatformMeetingInput {
  title: string;
  agenda?: string;
  /** ISO — يُبنى من `<input type="datetime-local">` عبر `utils/dateTimeLocal.ts`. */
  start: string;
  end: string;
  meeting_link: string;
}

export const createPlatformMeeting = (input: CreatePlatformMeetingInput) =>
  apiPostObject<PlatformMeetingRow>("platform/ops/meetings/create/", input);

export interface UpdatePlatformMeetingInput {
  title?: string;
  agenda?: string;
  start?: string;
  end?: string;
  meeting_link?: string;
}

export const updatePlatformMeeting = (id: number, input: UpdatePlatformMeetingInput) =>
  apiPostObject<PlatformMeetingRow>(`platform/ops/meetings/${id}/update/`, input);

export const cancelPlatformMeeting = (id: number) =>
  apiPostObject<PlatformMeetingRow>(`platform/ops/meetings/${id}/cancel/`, {});

export const inviteEmployeesToMeeting = (id: number, employees: number[]) =>
  apiPostObject<PlatformMeetingRow>(`platform/ops/meetings/${id}/invite/`, { employees });

export const listMeetingAttendance = (id: number) =>
  apiGetObject<PlatformMeetingAttendanceRow[]>(`platform/ops/meetings/${id}/attendance/`);

export const decideMeetingExcuse = (id: number, attendance: number, accepted: boolean) =>
  apiPostObject<PlatformMeetingAttendanceRow>(`platform/ops/meetings/${id}/decide-excuse/`, {
    attendance,
    accepted,
  });

export interface MeetingCheckInResult {
  status: MeetingAttendanceStatus;
  checked_in_at: string;
  /** رابطُ الاجتماع من **ردّ الخادم** لحظة الدخول — لا من صفّ القائمة المحلّي. */
  meeting_link: string;
}

export const checkInToMeeting = (id: number) =>
  apiPostObject<MeetingCheckInResult>(`platform/ops/meetings/${id}/check-in/`, {});

export const submitMeetingExcuse = (id: number, note: string) =>
  apiPostObject<PlatformMeetingAttendanceRow>(`platform/ops/meetings/${id}/excuse/`, { note });

/**
 * موظّفو المنصّة النشطون لمنتقي المدعوّين — نفسُ نقطة `platform/ops/employees/`
 * التي تستهلكها `getMyPlatformEmployeeProfile` (`platformEmployeeSpaceApi.ts`)
 * بلا نقطةٍ جديدة: مديرُ العمليات يرى فيها كلَّ الموظفين (`get_queryset`)، وهنا
 * تُقرأ القائمةُ كاملةً لا صفّاً واحداً مطابقاً لهويّة المستخدم الحاليّ.
 */
export const listActivePlatformEmployeesForInvite = async (): Promise<MyPlatformEmployeeProfile[]> => {
  const rows = unwrapRows(
    await apiGetObject<{ results: MyPlatformEmployeeProfile[]; count?: number } | MyPlatformEmployeeProfile[]>(
      "platform/ops/employees/",
    ),
  );
  return rows.filter((row) => row.status === "active");
};
