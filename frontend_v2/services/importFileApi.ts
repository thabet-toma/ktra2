/**
 * THA-114 T4 — عميل REST لوحدة «ملف الاستيراد».
 *
 * الخادم `import_file/views.py`: بوابة الترخيص تسبق الصلاحية، فترد الشركة غير
 * المرخّصة **404** لا 403 على كل مسار — الفشل هنا يُقرأ «لا وجود للوحدة»، وهو
 * المقصود. الشاشة نفسها محروسة بعَلَم `modules.import_file` قبل تحميل chunkها.
 *
 * **لا مسار رفع ثانٍ:** البايتات تمرّ بمسار المنصة القائم
 * (`cloudinaryService.uploadFile` → `POST /api/media/upload/`) وهذه الوحدة تسجّل
 * الرابط الناتج فقط. مسار ثانٍ كان يعني حدّ حجمٍ ثانياً وقياس تخزينٍ ثانياً.
 *
 * الوحدة محايدة مالياً بالكامل: لا قيد ولا حركة مخزون ولا مبلغ — فلا استيراد
 * هنا من أي خدمة محاسبية.
 */
import { apiDelete, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";
import { cloudinaryService } from "./cloudinaryService";
import { resolveTenantId } from "@/utils/tenantContext";
import type { ImportStageKey } from "@/components/import-flow/importJourneyGuidance";

const BASE = "import-file/";

const tenantOpts = () => ({ tenantId: resolveTenantId() });

/**
 * `derived` نوعٌ يرسله الخادم ولا يُرسَل إليه: الصفّ المشتقّ (سعر الشحن) يُعرض
 * ولا يُخزَّن، فلا يُنشأ ولا يُعدَّل من الشاشة.
 */
export type ImportFileItemType = "document" | "task" | "derived";

export interface ImportFileDocumentRow {
  id: number;
  url: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by: number | null;
  uploaded_by_name: string;
  uploaded_at: string;
}

/**
 * صفّ البند كما يرسله `import_file/serializers.py` — والصفّ المشتقّ يطابق شكله
 * حرفياً (`id: null`, `derived: true`) كي لا تحتاج الشاشة شكلين لصفٍّ واحد.
 */
export interface ImportFileItemRow {
  id: number | null;
  stage: ImportStageKey;
  item_type: ImportFileItemType;
  kind: string;
  label: string;
  required: boolean;
  done: boolean;
  is_done: boolean;
  note: string;
  position: number;
  is_custom: boolean;
  derived: boolean;
  documents: ImportFileDocumentRow[];
  created_at: string | null;
}

export interface ImportFileProgress {
  done: number;
  total: number;
}

export interface ImportFileStageRow {
  stage: ImportStageKey;
  label: string;
  items: ImportFileItemRow[];
  /** يحسبه الخادم — البنود المطلوبة وحدها، والصفّ المشتقّ داخل المقام. */
  progress: ImportFileProgress;
}

export interface ImportFilePayload {
  deal: { id: number; ref_number: string };
  shipment: { id: number; shipment_number: string } | null;
  stages: ImportFileStageRow[];
  progress: ImportFileProgress;
}

/** بند يضيفه المستخدم فوق الكتالوج — مستنداً كان أو مهمّة. */
export interface ImportFileItemDraft {
  /** المرساة: صفقة **أو** شحنة، واحدة بالضبط (يفرضها الخادم والقاعدة معاً). */
  deal?: number;
  shipment?: number;
  stage: ImportStageKey;
  item_type: "document" | "task";
  label: string;
  required?: boolean;
  note?: string;
}

/** `done` لبنود المهامّ وحدها — الخادم يرفضه (400) على بند مستند. */
export interface ImportFileItemPatch {
  done?: boolean;
  required?: boolean;
  note?: string;
  label?: string;
}

export interface ImportFileDocumentDraft {
  url: string;
  filename?: string;
  mime_type?: string;
  size_bytes?: number;
}

/** يفتح ملف الصفقة — والخادم يزرع ما ينقصه من الكتالوج عند الفتح. */
export function fetchDealImportFile(dealId: number): Promise<ImportFilePayload> {
  return apiGetObject<ImportFilePayload>(`${BASE}deals/${dealId}/file/`, tenantOpts());
}

export function createImportFileItem(draft: ImportFileItemDraft): Promise<ImportFileItemRow> {
  return apiPostObject<ImportFileItemRow>(`${BASE}items/`, draft, tenantOpts());
}

export function updateImportFileItem(
  id: number,
  patch: ImportFileItemPatch,
): Promise<ImportFileItemRow> {
  return apiPatchObject<ImportFileItemRow>(`${BASE}items/${id}/`, patch, tenantOpts());
}

/** للمخصّص وحده — بند الكتالوج يُعلَّم «غير مطلوب» ولا يُحذف (الخادم يرفض). */
export function deleteImportFileItem(id: number): Promise<void> {
  return apiDelete(`${BASE}items/${id}/`, tenantOpts());
}

/** يسجّل ملفاً رُفع سلفاً عبر {@link uploadImportFileDocument} — لا بايتات هنا. */
export function attachImportFileDocument(
  itemId: number,
  draft: ImportFileDocumentDraft,
): Promise<ImportFileDocumentRow> {
  return apiPostObject<ImportFileDocumentRow>(
    `${BASE}items/${itemId}/documents/`, draft, tenantOpts(),
  );
}

/** يحذف الصفّ ثم أصل Cloudinary — فلا blob يتيم تُدفع فاتورته. */
export function deleteImportFileDocument(id: number): Promise<void> {
  return apiDelete(`${BASE}documents/${id}/`, tenantOpts());
}

/** الرفع بمسار المنصة القائم (`POST /api/media/upload/`) — لا مسار ثانٍ. */
export function uploadImportFileDocument(file: File): Promise<string> {
  return cloudinaryService.uploadFile(file);
}
