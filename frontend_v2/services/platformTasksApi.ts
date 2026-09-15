import { apiGetForBlob, apiGetObject, apiPostFormData, apiPostObject } from './restApi';

const ROOT = 'platform/ops/';

export type PlatformTaskAudience = 'INDIVIDUAL' | 'SPECIFIC' | 'ALL' | 'OPEN';
export type PlatformTaskPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT';
export type PlatformTaskAssignmentStatus = 'OFFERED' | 'ACCEPTED' | 'IN_PROGRESS' | 'SUBMITTED' | 'COMPLETED' | 'RETURNED';
export type PlatformTaskReviewDecision = 'APPROVED_FULL' | 'APPROVED_PARTIAL' | 'REJECTED';
export type PlatformEmployeeNoteVisibility = 'EMPLOYEE' | 'MANAGER_ONLY';

export interface PlatformTask {
  id: number;
  title: string;
  description: string;
  priority: PlatformTaskPriority;
  priority_display: string;
  status: string;
  status_display: string;
  audience: PlatformTaskAudience;
  audience_display: string;
  due_date: string | null;
  claim_limit: number | null;
  // عددُ المطالبين من الخادم: قائمةُ إسنادات الموظّف مقصورةٌ عليه فلا يُعَدّ منها.
  claimed_count: number;
  // إجباريّةُ المهمّة: الفرديّةُ دائماً، والمجمَعُ أبداً، والجماعيّةُ خيارُ المدير.
  is_mandatory: boolean;
  // شرحُ المدير وحدَه — ملفّاتُ الموظّفين تخرج من `thread` حيث تُرشَّح بالرائي.
  brief_attachments: PlatformTaskAttachment[];
  created_by_name: string;
  completed_at: string | null;
  created_at: string;
}

export type PlatformTaskAttachmentKind = 'brief' | 'work' | 'delivery';

export interface PlatformTaskAttachment {
  id: number;
  task: number;
  kind: PlatformTaskAttachmentKind;
  kind_display: string;
  // صاحبُ الملفّ — `null` لشرح المدير: الشرحُ ملكُ المهمّة لا ملكُ موظّف.
  employee: number | null;
  employee_name: string;
  submission: number | null;
  url: string;
  name: string;
  content_type: string;
  uploaded_by: number | null;
  uploaded_by_name: string;
  created_at: string;
}

/** حدثٌ في ملفّ المهمّة — مرفقٌ أو ملاحظةٌ أو تسليمٌ أو قرارُ مراجعة. */
export interface PlatformTaskThreadEvent {
  type: 'attachment' | 'manager_note' | 'employee_note' | 'submission' | 'review';
  at: string;
  author_role: 'manager' | 'employee';
  author_name: string;
  employee: number | null;
  body: string;
  attachments: Array<Pick<PlatformTaskAttachment, 'id' | 'kind' | 'url' | 'name' | 'content_type' | 'employee'>>;
  visibility?: PlatformEmployeeNoteVisibility;
  submission?: number;
  decision?: PlatformTaskReviewDecision | null;
  /** نصُّ القرار العربيُّ من الخادم — لا قاموسَ ترجمةٍ ثانٍ في الواجهة. */
  decision_display?: string;
}

/** صفُّ لوحِ المدير: «شو معو مهام وشو استلم» — معدودٌ في القاعدة لا في المتصفّح. */
export interface PlatformTaskBoardRow {
  employee: number;
  employee_name: string;
  /** حالةُ الموظّف نفسِه — الموقوفُ يبقى في اللوح ما دام بيده عمل. */
  employee_status: string;
  employee_status_display: string;
  offered: number;
  accepted: number;
  in_progress: number;
  submitted: number;
  completed: number;
  returned: number;
  /** ما أُسند إليه بلا خيار — يُقرأ بجانب `accepted` لا بدلَها. */
  mandatory: number;
  overdue: number;
  total: number;
}

export interface PlatformTaskAssignment {
  id: number;
  task: number;
  task_title: string;
  task_audience: PlatformTaskAudience;
  task_due_date: string | null;
  /**
   * **تُقرأ من المهمّة لا تُستنتج من الحالة**: إسنادٌ `ACCEPTED` قد يكون إجباريّاً
   * وُلد مقبولاً وقد يكون اختياريّاً قَبِله صاحبُه — والفرقُ هو ما يريد رؤيتَه.
   */
  is_mandatory: boolean;
  employee: number;
  employee_name: string;
  status: PlatformTaskAssignmentStatus;
  status_display: string;
  offered_at: string;
  accepted_at: string | null;
  submitted_at: string | null;
  completed_at: string | null;
}

export interface PlatformTaskSubmission {
  id: number;
  task: number;
  task_title: string;
  employee: number;
  employee_name: string;
  body: string;
  decision: PlatformTaskReviewDecision | null;
  decision_display: string;
  reviewer_name: string;
  reviewer_notes: string;
  reviewed_at: string | null;
  created_at: string;
}

export interface PlatformEmployee {
  id: number;
  username: string;
  job_title: string;
  specialty: string;
  /** رمزُ الحالة كما في `PlatformEmployee.Status` — **صغيرٌ**: `active` لا `ACTIVE`. */
  status: string;
  status_display: string;
}

export interface PlatformEmployeeNote {
  id: number;
  employee: number;
  // المهمّةُ التي كُتبت عليها — `null` لملاحظةٍ عن الموظّف عموماً (212-M3).
  task: number | null;
  task_title: string;
  body: string;
  author_name: string;
  visibility: PlatformEmployeeNoteVisibility;
  visibility_display: string;
  created_at: string;
}

export interface PlatformWorkspaceNote {
  id: number;
  employee: number;
  employee_name: string;
  task: number | null;
  task_title: string;
  body: string;
  created_at: string;
}

export interface CreatePlatformTaskInput {
  title: string;
  description?: string;
  priority?: PlatformTaskPriority;
  due_date?: string | null;
  audience: PlatformTaskAudience;
  employee_ids?: number[];
  claim_limit?: number | null;
  is_mandatory?: boolean;
}

export const listPlatformTasks = () => apiGetObject<PlatformTask[]>(`${ROOT}tasks/`);
export const getPlatformTask = (id: number) => apiGetObject<PlatformTask>(`${ROOT}tasks/${id}/`);
export const createPlatformTask = (input: CreatePlatformTaskInput) => apiPostObject<PlatformTask>(`${ROOT}tasks/create/`, input);
export const claimPlatformTask = (id: number) => apiPostObject<PlatformTaskAssignment>(`${ROOT}tasks/${id}/claim/`, {});
export const listPlatformTaskAssignments = (employee?: number) => apiGetObject<PlatformTaskAssignment[]>(`${ROOT}assignments/`, { query: { employee } });
export const acceptPlatformTaskAssignment = (id: number) => apiPostObject<PlatformTaskAssignment>(`${ROOT}assignments/${id}/accept/`, {});
export const submitPlatformTaskAssignment = (id: number, body: string, attachment_ids: number[] = []) => apiPostObject<PlatformTaskSubmission>(`${ROOT}assignments/${id}/submit/`, { body, attachment_ids });
export const listPlatformTaskSubmissions = () => apiGetObject<PlatformTaskSubmission[]>(`${ROOT}submissions/`);
export const reviewPlatformTaskSubmission = (id: number, decision: PlatformTaskReviewDecision, reviewer_notes: string) => apiPostObject<PlatformTaskSubmission>(`${ROOT}submissions/${id}/review/`, { decision, reviewer_notes });
export const listPlatformEmployeeNotes = (employee?: number, task?: number) => apiGetObject<PlatformEmployeeNote[]>(`${ROOT}employee-notes/`, { query: { employee, task } });
export const createPlatformEmployeeNote = (employee: number, body: string, visibility: PlatformEmployeeNoteVisibility, task?: number | null) => apiPostObject<PlatformEmployeeNote>(`${ROOT}employee-notes/create/`, { employee, body, visibility, task: task ?? null });
export const listPlatformWorkspaceNotes = () => apiGetObject<PlatformWorkspaceNote[]>(`${ROOT}workspace-notes/`);
export const createPlatformWorkspaceNote = (body: string, task?: number | null) => apiPostObject<PlatformWorkspaceNote>(`${ROOT}workspace-notes/create/`, { body, task: task ?? null });
export const listPlatformEmployees = () => apiGetObject<PlatformEmployee[]>(`${ROOT}employees/`);

/**
 * رفعُ ملفٍّ على مهمّة — **الدورُ لا يُرسَل**: الخادمُ يشتقّه من الفاعل (مديرٌ ⇒ شرح،
 * موظّفٌ ⇒ ملفُّ عمل)، فإرسالُه من هنا كان سيجعل موظّفاً يكتب شرحَ المدير.
 */
export const uploadPlatformTaskAttachment = (taskId: number, file: File, name = '') => {
  const form = new FormData();
  form.append('file', file);
  if (name) form.append('name', name);
  return apiPostFormData<PlatformTaskAttachment>(`${ROOT}tasks/${taskId}/attachments/`, form);
};

/** بايتاتُ المرفق عبر الخادم — رابطُ التخزين صلاحيّةٌ بذاته فلا يصل المتصفّح. */
export const getPlatformTaskAttachmentFile = (taskId: number, attachmentId: number) =>
  apiGetForBlob(`${ROOT}tasks/${taskId}/attachments/${attachmentId}/download/`);

/** ملفُّ المهمّة الكامل — مرشَّحٌ بالرائي في الخادم لا هنا. */
export const getPlatformTaskThread = (taskId: number) =>
  apiGetObject<{ task: number; events: PlatformTaskThreadEvent[] }>(`${ROOT}tasks/${taskId}/thread/`);

/** لوحُ المدير: لكلّ موظّفٍ نشطٍ ما معه وما استلم — لمدير العمليات وحده. */
export const getPlatformTaskBoard = () =>
  apiGetObject<{ rows: PlatformTaskBoardRow[] }>(`${ROOT}tasks/board/`);
