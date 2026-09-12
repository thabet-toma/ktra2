/**
 * خدماتُ واجهة برمجة تطبيقات أوامر العمل ودفتر الوحدات وكتالوجها (التذكرة 210-C).
 *
 * قاعدة عزل الشركات نفسُها في `platformOpsApi.ts`: لا معاملات شركةٍ خامّة في
 * الطلب — الشركاتُ تُشتقّ خادمياً من الارتباطات النشطة، وأمرُ العمل والمُسلَّم
 * يُحدَّدان بمعرّفيهما فقط.
 */
import { apiGetObject, apiPostObject } from "./restApi";
import type { WorkOrderRow } from "./platformOpsApi";

function buildQuery(params: Record<string, any> = {}): string {
  const forbidden = ["tenant", "tenants", "tenant_id", "tenant_ids"];
  const searchParams = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null && val !== "" && !forbidden.includes(key.toLowerCase())) {
      searchParams.set(key, String(val));
    }
  }
  const str = searchParams.toString();
  return str ? `?${str}` : "";
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

export type WorkOrderPriority = "low" | "normal" | "high" | "urgent";
export type WorkOrderSource = "channel" | "staff" | "admin";
export type WorkOrderStatus =
  | "received" | "screening" | "data_entry" | "review" | "approval" | "closed" | "waiting_customer" | "cancelled";

/** مرآةُ `WORK_ORDER_TRANSITIONS` في `platform_ops/services.py` — للعرض فقط، الخادمُ هو الحَكَم. */
export const WORK_ORDER_TRANSITIONS: Record<WorkOrderStatus, WorkOrderStatus[]> = {
  received: ["screening"],
  screening: ["data_entry", "waiting_customer"],
  data_entry: ["review", "waiting_customer"],
  review: ["approval", "waiting_customer"],
  approval: ["closed", "waiting_customer"],
  waiting_customer: ["screening", "data_entry", "review", "approval", "cancelled"],
  closed: [],
  cancelled: [],
};

export const WORK_ORDER_STATUS_LABELS: Record<WorkOrderStatus, string> = {
  received: "مستلم",
  screening: "فرز وفحص",
  data_entry: "إدخال بيانات",
  review: "مراجعة",
  approval: "اعتماد",
  closed: "مغلق",
  waiting_customer: "بانتظار العميل",
  cancelled: "ملغى",
};

export interface WorkOrderDetailRow extends WorkOrderRow {
  description: string;
  source: WorkOrderSource;
  source_display: string;
  priority: WorkOrderPriority;
  priority_display: string;
  return_status: string;
  waiting_seconds_total: number;
  waiting_entered_at: string | null;
  approved_at: string | null;
  closed_at: string | null;
  deadline_at: string | null;
  effective_duration_seconds: number;
  updated_at: string;
}

export interface CreateWorkOrderInput {
  tenant: number;
  title: string;
  description?: string;
  kind?: string;
  priority?: WorkOrderPriority;
  assignee?: number | null;
}

export const createWorkOrder = (input: CreateWorkOrderInput) =>
  apiPostObject<WorkOrderDetailRow>("platform/ops/work-orders/create/", input);

/** طابورُ الموظّف الموحَّد عبر شركاته، مرتَّبٌ بالأولوية ثم الأجل (القصة ٣٤). */
export const getEmployeeWorkOrderQueue = () =>
  apiGetObject<WorkOrderDetailRow[]>("platform/ops/work-orders/queue/");

/**
 * قائمةُ أوامر العمل بنطاقٍ يشتقّه الخادم: مديرُ العمليات يرى كلَّ الشركات
 * المؤهَّلة، والموظّفُ شركاتِ ارتباطاته النشطة وحدَها.
 *
 * `/queue/` لا تصلح للمدير: هي مقصورةٌ على `assignee__user=request.user` عبر
 * ارتباطاته، والمديرُ لا `PlatformEmployee` له ولا ارتباط — فتعود فارغةً دائماً
 * وإن كان هو وحدَه صاحبَ حقّ الإنشاء والمراجعة.
 */
export const listWorkOrders = async (
  filter: { company?: number; status?: WorkOrderStatus } = {},
): Promise<WorkOrderDetailRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: WorkOrderDetailRow[]; count?: number } | WorkOrderDetailRow[]>(
      `platform/ops/work-orders/${buildQuery(filter)}`,
    ),
  );

export const assignWorkOrder = (workOrderId: number, assignee: number | null) =>
  apiPostObject<WorkOrderDetailRow>(`platform/ops/work-orders/${workOrderId}/assign/`, { assignee });

export const changeWorkOrderPriority = (workOrderId: number, priority: WorkOrderPriority) =>
  apiPostObject<WorkOrderDetailRow>(`platform/ops/work-orders/${workOrderId}/change-priority/`, { priority });

export interface TransitionConflictResponse {
  detail: string;
  code: "conflict_stale_version";
  current: WorkOrderDetailRow;
}

/**
 * نقلُ حالة أمر العمل (القصة ٣٥). عند تعارضٍ متفائل (`409`) يُرمى استثناءٌ
 * بحقل `.data` (انظر `restApi.ts`) يحمل `current` — النسخة الحالية لإعادة
 * العرض بدل الكتابة فوق تغييرٍ لم يُرَ.
 */
export const transitionWorkOrder = (
  workOrderId: number, targetStatus: WorkOrderStatus, expectedUpdatedAt?: string,
) =>
  apiPostObject<WorkOrderDetailRow>(`platform/ops/work-orders/${workOrderId}/transition/`, {
    target_status: targetStatus,
    expected_updated_at: expectedUpdatedAt || undefined,
  });

export type CommentVisibility = "internal" | "client_visible";

export interface WorkOrderCommentRow {
  id: number;
  work_order: number;
  visibility: CommentVisibility;
  visibility_display: string;
  author: number;
  author_name: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export const listWorkOrderComments = (workOrderId: number) =>
  apiGetObject<WorkOrderCommentRow[]>(`platform/ops/work-orders/${workOrderId}/comments/`);

export const addWorkOrderComment = (workOrderId: number, content: string, visibility: CommentVisibility) =>
  apiPostObject<WorkOrderCommentRow>(`platform/ops/work-orders/${workOrderId}/comments/`, { content, visibility });

export type ServiceDocumentType =
  | "sales_invoice" | "purchase_invoice" | "receipt_or_payment" | "journal_entry"
  | "sales_or_purchase_order" | "inventory_document" | "bank_reconciliation"
  | "import_file_row" | "report_or_check_or_support";

export const SERVICE_DOCUMENT_TYPES: ServiceDocumentType[] = [
  "sales_invoice", "purchase_invoice", "receipt_or_payment", "journal_entry",
  "sales_or_purchase_order", "inventory_document", "bank_reconciliation",
  "import_file_row", "report_or_check_or_support",
];

export const SERVICE_DOCUMENT_TYPE_LABELS: Record<ServiceDocumentType, string> = {
  sales_invoice: "فاتورة بيع",
  purchase_invoice: "فاتورة شراء",
  receipt_or_payment: "سند قبض/صرف أو دفعة",
  journal_entry: "قيد يومية",
  sales_or_purchase_order: "أمر بيع/شراء",
  inventory_document: "مستند مخزون/جرد",
  bank_reconciliation: "تسوية بنكية",
  import_file_row: "ملف إدخال",
  report_or_check_or_support: "تقرير أو فحص أو دعم",
};

export type CatalogComplexity = "" | "low" | "medium" | "high";

export interface WorkOrderDocumentLinkRow {
  id: number;
  work_order: number;
  deliverable: number | null;
  document_type: ServiceDocumentType;
  document_type_display: string;
  document_id: number;
  line_count: number;
  /** `observed` = رُصد من المستند نفسِه · `declared` = صرّح به الرابط (نوعٌ لا نملك عدَّه من هنا). */
  line_count_source: "observed" | "declared";
  line_count_source_display: string;
  recount_reason: string;
  complexity: CatalogComplexity;
  complexity_display: string;
  linked_by: number | null;
  created_at: string;
  updated_at: string;
}

/**
 * `recount_reason` يُرسَل **فقط** لإعادة احتساب مستندٍ سبق احتسابُه: الخادم يردّ
 * 409 `document_already_charged` بلا سبب، و403 `manager_only` إن أرسله غيرُ مدير
 * العمليات. فالسببُ ليس حقلاً روتينيّاً في النموذج بل بابٌ يُفتح بعد الرفض.
 */
export const linkWorkOrderDocument = (
  workOrderId: number,
  input: {
    document_type: ServiceDocumentType;
    document_id: number;
    line_count?: number;
    complexity?: CatalogComplexity;
    recount_reason?: string;
  },
) =>
  apiPostObject<WorkOrderDocumentLinkRow>(`platform/ops/work-orders/${workOrderId}/link-document/`, input);

export const listWorkOrderDocumentLinks = (workOrderId: number) =>
  apiGetObject<WorkOrderDocumentLinkRow[]>(`platform/ops/work-orders/${workOrderId}/document-links/`);

export type DeliverableKind = "note" | "structured_report" | "attachment";
export type DeliverableReviewStatus = "pending" | "approved" | "rejected";
export type RejectionCategory = "" | "employee_error" | "customer_new_info" | "other";

export interface WorkOrderDeliverableRow {
  id: number;
  work_order: number;
  kind: DeliverableKind;
  kind_display: string;
  review_status: DeliverableReviewStatus;
  review_status_display: string;
  content: string;
  payload: Record<string, any>;
  file_url: string;
  content_snapshot: Record<string, any>;
  rejection_reason: string;
  rejection_category: RejectionCategory;
  rejection_category_display: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  submitted_by: number | null;
  document_links: WorkOrderDocumentLinkRow[];
  created_at: string;
  updated_at: string;
}

export const listWorkOrderDeliverables = (workOrderId: number) =>
  apiGetObject<WorkOrderDeliverableRow[]>(`platform/ops/work-orders/${workOrderId}/deliverables/`);

export interface SubmitDeliverableInput {
  kind?: DeliverableKind;
  content?: string;
  payload?: Record<string, any>;
  file_url?: string;
  document_link_ids?: number[];
}

export const submitWorkOrderDeliverable = (workOrderId: number, input: SubmitDeliverableInput) =>
  apiPostObject<WorkOrderDeliverableRow>(`platform/ops/work-orders/${workOrderId}/deliverables/`, input);

export interface ServiceUsageEventRow {
  id: number;
  tenant: number;
  company_name: string;
  subscription: number;
  work_order: number;
  deliverable: number;
  document_link: number;
  event_type: "usage" | "reversal";
  event_type_display: string;
  source_type: ServiceDocumentType;
  source_type_display: string;
  source_id: number;
  line_count_snapshot: number;
  /** مرصودٌ من المستند أم مُصرَّحٌ به — مادّةُ أيّ اعتراضٍ على الوحدات (القصة ١٩). */
  line_count_source: "observed" | "declared";
  line_count_source_display: string;
  catalog_version: number;
  units: string;
  chargeable_to_customer: boolean;
  creditable_to_employee: boolean;
  employee: number | null;
  employee_name: string;
  approved_by: number | null;
  approved_at: string;
  period_start: string | null;
  period_end: string | null;
  idempotency_key: string;
  reversed_event: number | null;
  reason: string;
  correlation_id: string;
  created_at: string;
}

export interface ReviewDeliverableApprovedResponse {
  deliverable: WorkOrderDeliverableRow;
  usage_events: ServiceUsageEventRow[];
}

/** اعتمادٌ أو ردٌّ بسببٍ مصنَّفٍ ومكتوب — الردّ يتطلّب `rejection_reason` و`rejection_category` معاً (القصة ١٤). */
export const reviewWorkOrderDeliverable = (
  workOrderId: number,
  deliverableId: number,
  input:
    | { review_status: "approved" }
    | { review_status: "rejected"; rejection_reason: string; rejection_category: Exclude<RejectionCategory, ""> },
) =>
  apiPostObject<ReviewDeliverableApprovedResponse | WorkOrderDeliverableRow>(
    `platform/ops/work-orders/${workOrderId}/deliverables/${deliverableId}/review/`, input,
  );

export const listUsageEvents = async (
  filter: { company?: number; work_order?: number } = {},
): Promise<ServiceUsageEventRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: ServiceUsageEventRow[]; count?: number } | ServiceUsageEventRow[]>(
      `platform/ops/usage-events/${buildQuery(filter)}`,
    ),
  );

export const reverseUsageEvent = (usageEventId: number, reason: string) =>
  apiPostObject<ServiceUsageEventRow>(`platform/ops/usage-events/${usageEventId}/reverse/`, { reason });

// ==============================================================================
// كتالوج وحدات الخدمة بنسخٍ مؤرَّخة (القصص ١٦-١٨)
// ==============================================================================

export type ServiceUnitCatalogStatus = "draft" | "active" | "retired";
export type ServiceUnitCatalogEffectiveState = "draft" | "scheduled" | "current" | "retired";

export interface ServiceUnitCatalogEntryRow {
  id: number;
  catalog: number;
  document_type: ServiceDocumentType;
  document_type_display: string;
  base_units: string;
  per_line_weight: string;
  complexity_low_add: string;
  complexity_medium_add: string;
  complexity_high_add: string;
  created_at: string;
  updated_at: string;
}

export interface ServiceUnitCatalogRow {
  id: number;
  version: number;
  status: ServiceUnitCatalogStatus;
  status_display: string;
  effective_state: ServiceUnitCatalogEffectiveState;
  activation_reason: string;
  effective_from: string | null;
  effective_to: string | null;
  created_by: number | null;
  activated_by: number | null;
  activated_at: string | null;
  entries: ServiceUnitCatalogEntryRow[];
  created_at: string;
  updated_at: string;
}

export interface CatalogEntryInput {
  document_type: ServiceDocumentType;
  base_units?: string | number;
  per_line_weight?: string | number;
  complexity_low_add?: string | number;
  complexity_medium_add?: string | number;
  complexity_high_add?: string | number;
}

export const listServiceUnitCatalogs = async (): Promise<ServiceUnitCatalogRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: ServiceUnitCatalogRow[]; count?: number } | ServiceUnitCatalogRow[]>(
      "platform/ops/service-unit-catalogs/",
    ),
  );

export const getActiveServiceUnitCatalog = () =>
  apiGetObject<ServiceUnitCatalogRow>("platform/ops/service-unit-catalogs/active/");

export const createServiceUnitCatalogDraft = () =>
  apiPostObject<ServiceUnitCatalogRow>("platform/ops/service-unit-catalogs/draft/", {});

export const cloneServiceUnitCatalog = (catalogId: number) =>
  apiPostObject<ServiceUnitCatalogRow>(`platform/ops/service-unit-catalogs/${catalogId}/clone/`, {});

export const updateServiceUnitCatalogEntries = (catalogId: number, entries: CatalogEntryInput[]) =>
  apiPostObject<ServiceUnitCatalogRow>(`platform/ops/service-unit-catalogs/${catalogId}/update-entries/`, { entries });

export const activateServiceUnitCatalog = (catalogId: number, activationReason: string, effectiveFrom?: string) =>
  apiPostObject<ServiceUnitCatalogRow>(`platform/ops/service-unit-catalogs/${catalogId}/activate/`, {
    activation_reason: activationReason,
    effective_from: effectiveFrom || undefined,
  });
