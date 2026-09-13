import { apiGetObject, apiPostObject } from './restApi';

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
  created_by_name: string;
  completed_at: string | null;
  created_at: string;
}

export interface PlatformTaskAssignment {
  id: number;
  task: number;
  task_title: string;
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
  status: string;
}

export interface PlatformEmployeeNote {
  id: number;
  employee: number;
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
}

export const listPlatformTasks = () => apiGetObject<PlatformTask[]>(`${ROOT}tasks/`);
export const getPlatformTask = (id: number) => apiGetObject<PlatformTask>(`${ROOT}tasks/${id}/`);
export const createPlatformTask = (input: CreatePlatformTaskInput) => apiPostObject<PlatformTask>(`${ROOT}tasks/create/`, input);
export const claimPlatformTask = (id: number) => apiPostObject<PlatformTaskAssignment>(`${ROOT}tasks/${id}/claim/`, {});
export const listPlatformTaskAssignments = () => apiGetObject<PlatformTaskAssignment[]>(`${ROOT}assignments/`);
export const acceptPlatformTaskAssignment = (id: number) => apiPostObject<PlatformTaskAssignment>(`${ROOT}assignments/${id}/accept/`, {});
export const submitPlatformTaskAssignment = (id: number, body: string) => apiPostObject<PlatformTaskSubmission>(`${ROOT}assignments/${id}/submit/`, { body });
export const listPlatformTaskSubmissions = () => apiGetObject<PlatformTaskSubmission[]>(`${ROOT}submissions/`);
export const reviewPlatformTaskSubmission = (id: number, decision: PlatformTaskReviewDecision, reviewer_notes: string) => apiPostObject<PlatformTaskSubmission>(`${ROOT}submissions/${id}/review/`, { decision, reviewer_notes });
export const listPlatformEmployeeNotes = () => apiGetObject<PlatformEmployeeNote[]>(`${ROOT}employee-notes/`);
export const createPlatformEmployeeNote = (employee: number, body: string, visibility: PlatformEmployeeNoteVisibility) => apiPostObject<PlatformEmployeeNote>(`${ROOT}employee-notes/create/`, { employee, body, visibility });
export const listPlatformWorkspaceNotes = () => apiGetObject<PlatformWorkspaceNote[]>(`${ROOT}workspace-notes/`);
export const createPlatformWorkspaceNote = (body: string, task?: number | null) => apiPostObject<PlatformWorkspaceNote>(`${ROOT}workspace-notes/create/`, { body, task: task ?? null });
export const listPlatformEmployees = () => apiGetObject<PlatformEmployee[]>(`${ROOT}employees/`);
