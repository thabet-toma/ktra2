import { apiGetObject, apiPatchObject, apiPostObject } from './restApi';

const CRM_ROOT = 'platform/crm/';

export type CrmLeadStatus = 'new' | 'contacted' | 'interested' | 'follow_up' | 'customer' | 'not_interested' | 'no_answer' | 'wrong_number' | 'postponed' | 'closed';
export type CrmActivityKind = 'call' | 'whatsapp' | 'visit' | 'note' | 'status_change' | 'assignment' | 'transfer' | 'materials_sent';
export type CrmPhoneKind = 'primary' | 'whatsapp' | 'secondary' | 'owner_mobile';
export type CrmApprovalStatus = 'approved' | 'pending' | 'rejected';
export type CrmFollowUpFilter = 'due' | 'overdue' | 'upcoming';

export interface CrmEmployeeSummary { id: number; name: string; }
export interface CrmPhone { id: number; e164: string; raw: string; kind: CrmPhoneKind; created_at: string; }
export interface CrmLead {
  id: number; store_name: string; owner_name: string; city: string; address: string; activity: string;
  status: CrmLeadStatus; assigned_to: CrmEmployeeSummary | null; assigned_at: string | null;
  next_follow_up_at: string | null; source: string; approval_status: CrmApprovalStatus;
  suggested_by: CrmEmployeeSummary | null; rejection_reason: string; converted_tenant: number | null;
  phones: CrmPhone[]; created_at: string; updated_at: string;
}
export interface CrmActivity {
  id: number; lead: number; employee: CrmEmployeeSummary | null; kind: CrmActivityKind; body: string;
  outcome: string; materials: string[]; status_before: CrmLeadStatus | null; status_after: CrmLeadStatus | null;
  next_follow_up_at: string | null; created_at: string;
}
export interface CrmTransfer {
  id: number; lead: number; from_employee: CrmEmployeeSummary | null; to_employee: CrmEmployeeSummary | null;
  reason: string; status: string; created_at: string; decided_at: string | null;
}
export interface CrmColleague { id: number; name: string; job_title: string; is_me: boolean; }
/**
 * ستاتستكس الرقم الواحد (212-R4) — **مجمَّعةٌ في الخادم**.
 *
 * ولا تُشتقّ من `CrmActivity[]` المحمَّلة: تلك صفحةٌ من خمسين، فالعدُّ منها يكذب
 * على رقمٍ طويل السجلّ. الحكمُ على هذه الأرقام في `utils/leadContactStats.ts`.
 */
export interface CrmLeadContactStats {
  age_days: number;
  contact_attempts: number;
  by_kind: Partial<Record<Extract<CrmActivityKind, 'call' | 'whatsapp' | 'visit'>, number>>;
  last_contact_at: string | null;
  days_since_last_contact: number | null;
  days_in_status: number;
  handlers: number;
  follow_up_state: 'overdue' | 'due_today' | 'upcoming' | 'none';
  next_follow_up_at: string | null;
}
export interface CrmStats { assigned: number; contacted: number; interested: number; follow_up: number; customer: number; not_interested: number; overdue: number; }
export interface CrmOverviewEmployee { employee_id: number; employee_name: string; total: number; overdue: number; by_status: Partial<Record<CrmLeadStatus, number>>; }
export interface CrmOverview { employees: CrmOverviewEmployee[]; pool_size: number; }
export interface CrmImportBatch { id: number; file_name: string; total_rows: number; created_count: number; duplicate_count: number; invalid_count: number; duplicates: unknown[]; created_at: string; }
export interface CrmLookup {
  normalized: string; found: boolean; lead: Pick<CrmLead, 'id' | 'store_name' | 'status'> | null;
  locked_by: CrmEmployeeSummary | null; can_claim: boolean; is_mine: boolean;
}
export interface CrmPage<T> { count: number; next: string | null; previous: string | null; results: T[]; }
export interface CrmDuplicateError { detail: string; code: string; existing_lead_id?: number; existing_lead_name?: string; matched_phone?: string; assigned_to?: CrmEmployeeSummary | null; }
export interface CrmLeadFilters { scope?: 'mine' | 'pool' | 'all'; follow_up?: CrmFollowUpFilter; status?: CrmLeadStatus; q?: string; phone?: string; approval_status?: CrmApprovalStatus; page?: number; }
export interface CrmLeadInput { store_name: string; owner_name?: string; city?: string; address?: string; activity?: string; phones: Array<{ raw: string; kind: CrmPhoneKind }>; }
export interface CrmLeadPatch { owner_name?: string; city?: string; address?: string; activity?: string; }
export interface CrmActivityInput { kind: Extract<CrmActivityKind, 'call' | 'whatsapp' | 'visit' | 'note'>; body?: string; outcome?: string; materials?: string[]; next_follow_up_at?: string | null; }
export interface CrmImportRow { store_name: string; phone: string; owner_name?: string; city?: string; address?: string; activity?: string; }

const record = (value: object): Record<string, unknown> => value as Record<string, unknown>;
const pageRows = <T>(value: CrmPage<T> | T[]): CrmPage<T> => Array.isArray(value) ? { count: value.length, next: null, previous: null, results: value } : value;

export const listCrmLeads = async (filters: CrmLeadFilters = {}): Promise<CrmPage<CrmLead>> => pageRows(await apiGetObject<CrmPage<CrmLead> | CrmLead[]>(`${CRM_ROOT}leads/`, { query: { scope: filters.scope, follow_up: filters.follow_up, status: filters.status, q: filters.q, phone: filters.phone, approval_status: filters.approval_status, page: filters.page } }));
export const getCrmLead = (id: number) => apiGetObject<CrmLead>(`${CRM_ROOT}leads/${id}/`);
export const createCrmLead = (input: CrmLeadInput) => apiPostObject<CrmLead>(`${CRM_ROOT}leads/`, record(input));
export const patchCrmLead = (id: number, input: CrmLeadPatch) => apiPatchObject<CrmLead>(`${CRM_ROOT}leads/${id}/`, record(input));
export const lookupCrmPhone = (phone: string) => apiGetObject<CrmLookup>(`${CRM_ROOT}leads/lookup/`, { query: { phone } });
export const claimCrmLead = (id: number) => apiPostObject<CrmLead>(`${CRM_ROOT}leads/${id}/claim/`, {});
export const releaseCrmLead = (id: number, reason: string) => apiPostObject<CrmLead>(`${CRM_ROOT}leads/${id}/release/`, { reason });
export const listCrmActivities = async (id: number): Promise<CrmPage<CrmActivity>> => pageRows(await apiGetObject<CrmPage<CrmActivity> | CrmActivity[]>(`${CRM_ROOT}leads/${id}/activities/`));
export const createCrmActivity = (id: number, input: CrmActivityInput) => apiPostObject<CrmActivity>(`${CRM_ROOT}leads/${id}/activities/`, record(input));
export const getCrmLeadStats = (id: number) => apiGetObject<CrmLeadContactStats>(`${CRM_ROOT}leads/${id}/stats/`);
export const changeCrmLeadStatus = (id: number, status: CrmLeadStatus, body = '') => apiPostObject<CrmLead>(`${CRM_ROOT}leads/${id}/status/`, { status, body });
export const transferCrmLead = (id: number, to_employee: number, reason: string) => apiPostObject<CrmTransfer>(`${CRM_ROOT}leads/${id}/transfer/`, { to_employee, reason });
export const requestCrmLeadTransfer = (id: number, to_employee: number, reason: string) => apiPostObject<CrmTransfer>(`${CRM_ROOT}leads/${id}/transfer-requests/`, { to_employee, reason });
export const approveCrmLead = (id: number) => apiPostObject<CrmLead>(`${CRM_ROOT}leads/${id}/approve/`, {});
export const rejectCrmLead = (id: number, reason: string) => apiPostObject<CrmLead>(`${CRM_ROOT}leads/${id}/reject/`, { reason });
export const importCrmLeads = (rows: CrmImportRow[], file_name = '') => apiPostObject<CrmImportBatch>(`${CRM_ROOT}leads/import/`, { rows, file_name });
export const listCrmTransferRequests = async (): Promise<CrmPage<CrmTransfer>> => pageRows(await apiGetObject<CrmPage<CrmTransfer> | CrmTransfer[]>(`${CRM_ROOT}transfer-requests/`));
export const getCrmTransferRequest = (id: number) => apiGetObject<CrmTransfer>(`${CRM_ROOT}transfer-requests/${id}/`);
export const decideCrmTransferRequest = (id: number, approve: boolean, note = '') => apiPostObject<CrmTransfer>(`${CRM_ROOT}transfer-requests/${id}/decide/`, { approve, note });
export const listCrmColleagues = () => apiGetObject<CrmColleague[]>(`${CRM_ROOT}colleagues/`);
export const getMyCrmStats = () => apiGetObject<CrmStats>(`${CRM_ROOT}stats/me/`);
export const getCrmOverview = () => apiGetObject<CrmOverview>(`${CRM_ROOT}stats/overview/`);
