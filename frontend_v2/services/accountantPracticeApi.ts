import type { OfficeDashboardPayload } from '../utils/officeDashboardSections';
import {
  apiDelete,
  apiGetObject,
  apiPatchObject,
  apiPostFormData,
  apiPostObject,
} from './restApi';

/**
 * سطح مكتب المحاسبة (B2) — `/api/accountant/practice/`.
 *
 * **بلا `tenantId` عمداً**: كل صفّ هنا مملوك للمحاسب لا لشركة، والمسارات هوياتية
 * (`accountant=request.user`). إرسال `X-Tenant-Id` يُدخل الطلبَ تحت حارس ترخيص
 * الوحدة، فتختفي شاشات المكتب كلها عند اختيار شركة غير مرخّصة لبوابة المحاسب.
 */
const PRACTICE = 'accountant/practice';

export type PracticeClientStatus = 'active' | 'archived';
export type PracticeProgramStatus = 'planned' | 'in_progress' | 'done';
export type PracticeProgramFrequency = 'annual' | 'monthly' | 'once';
export type PracticeTaskStatus = 'open' | 'done';
export type PracticeTaskKind = 'appointment' | 'deadline';

/**
 * ISSUE #86 (مراجعة 2): زبون المكتب صار `partners.Partner` داخل شركة مكتب
 * المحاسب — لا سجلّ منفصل. `contact_first`/`contact_last`/`notes` بلا حقلٍ
 * بنيويّ على الطرف؛ الخادم يخزّنها في سِجلٍّ جانبيّ ويُظهرها هنا كأي حقلٍ عادي.
 * `status` أرشفةُ **طبقة المكتب** (`PracticeClientArchive`) لا الطرف نفسه.
 * `legacy: true` يعني أن هذا الصفّ لم يُرحَّل بعد (معرّفه سالبٌ عمداً)، فيُقرأ
 * ولا يُكتب حتى يُرحَّل — انظر `docs/decisions/practice_client_retirement.md`.
 */
export interface PracticeClientRecord {
  id: number;
  trade_name: string;
  contact_first: string;
  contact_last: string;
  phone: string;
  mobile: string;
  email: string;
  address: string;
  sector: string;
  tax_number: string;
  notes: string;
  status: PracticeClientStatus;
  /** ارتباط المكتب بشركة هذا الزبون على المنصة — `null` يعني «زبون خارجي». */
  engagement_id: number | null;
  tenant_id: number | null;
  /** ISSUE #52/#57 — دفتر يديره المكتب مباشرة (`Tenant.managed_by`). */
  managed_tenant_id: number | null;
  client_type: 'managed' | 'engaged' | 'hybrid' | 'unlinked';
  created_at: string;
  /** معرّفٌ سالبٌ = زبونٌ قديمٌ لم يُرحَّل بعد — قراءةٌ فقط، لا PATCH عليه. */
  legacy: boolean;
}

export interface PracticeProgramRecord {
  id: number;
  partner_id: number;
  partner_name: string;
  service_type: string;
  frequency: PracticeProgramFrequency;
  team_note: string;
  due_date: string | null;
  status: PracticeProgramStatus;
  notes: string;
  is_overdue: boolean;
}

export interface PracticeTaskRecord {
  id: number;
  partner_id: number | null;
  partner_name: string;
  title: string;
  due_at: string;
  status: PracticeTaskStatus;
  kind: PracticeTaskKind;
  is_overdue: boolean;
}

export interface PracticeDocumentRecord {
  id: number;
  partner_id: number;
  program_id: number | null;
  name: string;
  url: string;
  uploaded_at: string;
}

export interface PracticeSettingsRecord {
  default_program_due_days: number;
  service_types: string[];
}

/** بند في أجندة المكتب — برنامج أو موعد أو موعد تقديم إقرار لشركة مرتبطة. */
export interface PracticeDeadlineItem {
  kind: 'program' | 'appointment' | 'deadline' | 'filing';
  id: number | null;
  title: string;
  partner_id: number | null;
  partner_name: string;
  tenant_id: number | null;
  due_date: string;
  status: string;
  days_left: number;
  is_overdue: boolean;
}

export interface PracticeDeadlines {
  today: string;
  items: PracticeDeadlineItem[];
  totals: { count: number; overdue: number; due_soon: number };
}

export type PracticeClientInput = Partial<Omit<PracticeClientRecord, 'id' | 'tenant_id' | 'client_type' | 'created_at' | 'status' | 'legacy'>>;

// ── الزبائن ──────────────────────────────────────────────────────────────────

export const listPracticeClients = (params: { status?: string; search?: string } = {}) =>
  apiGetObject<{ results: PracticeClientRecord[]; count: number }>(`${PRACTICE}/clients/`, {
    query: { status: params.status || undefined, search: params.search || undefined },
  });

/** `clientId` قد يكون سالباً (زبونٌ قديمٌ لم يُرحَّل بعد) — القراءة تفهمه. */
export const getPracticeClient = (clientId: number) =>
  apiGetObject<{ client: PracticeClientRecord }>(`${PRACTICE}/clients/${clientId}/`);

export const createPracticeClient = (body: PracticeClientInput) =>
  apiPostObject<{ client: PracticeClientRecord }>(`${PRACTICE}/clients/`, body);

export const updatePracticeClient = (clientId: number, body: PracticeClientInput) =>
  apiPatchObject<{ client: PracticeClientRecord }>(`${PRACTICE}/clients/${clientId}/`, body);

/** الحذف أرشفة — حالة طبقة المكتب، والاسترجاع من قائمة المؤرشفين. */
export const archivePracticeClient = (clientId: number) =>
  apiDelete(`${PRACTICE}/clients/${clientId}/`);

export const restorePracticeClient = (clientId: number) =>
  apiPostObject<{ client: PracticeClientRecord }>(`${PRACTICE}/clients/${clientId}/restore/`, {});

/** ربط/فكّ الارتباط بشركة على المنصة أو بدفترٍ مُدار — فعلٌ حسّاس مستقلّ عن
 * تعديل بيانات الاتصال العادية (`updatePracticeClient`). */
export const linkPracticeClient = (
  clientId: number,
  body: Partial<{ engagement_id: number | null; managed_tenant_id: number | null }>,
) => apiPatchObject<{ client: PracticeClientRecord }>(`${PRACTICE}/clients/${clientId}/link/`, body);

// ── برامج المراجعة ───────────────────────────────────────────────────────────

export const listPracticePrograms = (params: { clientId?: number; status?: string } = {}) =>
  apiGetObject<{ results: PracticeProgramRecord[]; count: number }>(`${PRACTICE}/programs/`, {
    query: { partner_id: params.clientId, status: params.status || undefined },
  });

export const createPracticeProgram = (body: {
  partner_id: number;
  service_type: string;
  frequency?: PracticeProgramFrequency;
  team_note?: string;
  due_date?: string;
  status?: PracticeProgramStatus;
  notes?: string;
}) => apiPostObject<{ program: PracticeProgramRecord }>(`${PRACTICE}/programs/`, body);

export const updatePracticeProgram = (
  programId: number,
  body: Partial<{
    service_type: string;
    frequency: PracticeProgramFrequency;
    team_note: string;
    due_date: string | null;
    status: PracticeProgramStatus;
    notes: string;
  }>,
) => apiPatchObject<{ program: PracticeProgramRecord }>(`${PRACTICE}/programs/${programId}/`, body);

export const deletePracticeProgram = (programId: number) =>
  apiDelete(`${PRACTICE}/programs/${programId}/`);

// ── المواعيد والمهام ─────────────────────────────────────────────────────────

export const listPracticeTasks = (params: { clientId?: number; status?: string } = {}) =>
  apiGetObject<{ results: PracticeTaskRecord[]; count: number }>(`${PRACTICE}/tasks/`, {
    query: { partner_id: params.clientId, status: params.status || undefined },
  });

export const createPracticeTask = (body: {
  title: string;
  due_at: string;
  partner_id?: number | null;
  kind?: PracticeTaskKind;
  status?: PracticeTaskStatus;
}) => apiPostObject<{ task: PracticeTaskRecord }>(`${PRACTICE}/tasks/`, body);

export const updatePracticeTask = (
  taskId: number,
  body: Partial<{
    title: string;
    due_at: string;
    partner_id: number | null;
    kind: PracticeTaskKind;
    status: PracticeTaskStatus;
  }>,
) => apiPatchObject<{ task: PracticeTaskRecord }>(`${PRACTICE}/tasks/${taskId}/`, body);

export const deletePracticeTask = (taskId: number) =>
  apiDelete(`${PRACTICE}/tasks/${taskId}/`);

// ── المستندات ────────────────────────────────────────────────────────────────

export const listPracticeDocuments = (params: { clientId?: number; programId?: number } = {}) =>
  apiGetObject<{ results: PracticeDocumentRecord[]; count: number }>(`${PRACTICE}/documents/`, {
    query: { partner_id: params.clientId, program_id: params.programId },
  });

/** الرفع multipart — نفس قلب Cloudinary ونفس حصّته في `core/media_views.py`. */
export const uploadPracticeDocument = (input: {
  clientId: number;
  file: File;
  name?: string;
  programId?: number | null;
}) => {
  const form = new FormData();
  form.append('file', input.file);
  form.append('partner_id', String(input.clientId));
  if (input.name) form.append('name', input.name);
  if (input.programId) form.append('program_id', String(input.programId));
  return apiPostFormData<{ document: PracticeDocumentRecord }>(`${PRACTICE}/documents/upload/`, form);
};

export const deletePracticeDocument = (documentId: number) =>
  apiDelete(`${PRACTICE}/documents/${documentId}/`);

// ── الإعدادات والأجندة ───────────────────────────────────────────────────────

export const getPracticeSettings = () =>
  apiGetObject<{ settings: PracticeSettingsRecord }>(`${PRACTICE}/settings/`);

export const updatePracticeSettings = (body: Partial<PracticeSettingsRecord>) =>
  apiPatchObject<{ settings: PracticeSettingsRecord }>(`${PRACTICE}/settings/`, body);

export const getPracticeDeadlines = () =>
  apiGetObject<PracticeDeadlines>(`${PRACTICE}/deadlines/`);

/**
 * ISSUE #58 — لوحة المكتب: العناصر الثلاثة معاً (`practice_dashboard` /
 * `staff_practice_dashboard`). موظفٌ بلا ملف محاسب يصل هذا المسار وحده من كل
 * سطح المكتب (القرار 7) فيرى عملاءه المُسنَدين — بقية `PRACTICE` تبقى خلف
 * ملفٍ مهني.
 */
export const getPracticeDashboard = () =>
  apiGetObject<OfficeDashboardPayload>(`${PRACTICE}/dashboard/`);
