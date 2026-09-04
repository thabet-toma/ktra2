import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const BASE = "logistics";
const tenantId = () => resolveTenantId();

export type ProcurementScope = "local" | "import";

export type SupplierQuotationStatus =
  | "draft"
  | "sent"
  /** T-OFFERSTATE: حالتان حقيقيتان بعد أن كانتا تُسقَطان على `sent`. */
  | "pending_info"
  | "under_discussion"
  | "accepted"
  | "rejected"
  | "expired"
  | "cancelled"
  | "converted";

export interface SupplierQuotationLineDto {
  id?: number;
  /** T-DRAFTPARTY: null = منتج مكتوب يدوياً داخل العرض، اسمه في name_snapshot. */
  product: number | null;
  product_name?: string;
  seq?: number;
  name_snapshot?: string;
  description_line?: string;
  quantity: string;
  unit_price: string;
  line_total?: string;
}

/**
 * ISSUE #122: من كتب أسعار هذا العرض — `supplier_link` سعّره المورّد بنفسه من
 * رابطه الخاص، و`manual` أدخلناه عنه (هاتفياً غالباً). حقلٌ صريحٌ لا استنتاج:
 * ترك التمييز في `created_by IS NULL` يعمل صدفةً اليوم ويكذب أوّل مرّةٍ
 * يُنشئ فيها مسارٌ ثالثٌ عرضاً.
 */
export type SupplierQuotationEntrySource = "supplier_link" | "manual";

export interface SupplierQuotationDto {
  id: number;
  scope: ProcurementScope;
  quotation_number: string;
  order_name?: string;
  order_description?: string;
  /** T-DRAFTPARTY: null = مورد مبدئي اسمه في supplier_draft_name. */
  supplier: number | null;
  supplier_draft_name?: string;
  supplier_name?: string;
  /** اسم المورد المعروض مبدئيّ لا مسجَّل. */
  is_draft_supplier?: boolean;
  quotation_date: string;
  valid_until?: string | null;
  status: SupplierQuotationStatus;
  currency: number;
  currency_code?: string;
  exchange_rate: string;
  subtotal: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  grand_total: string;
  shipping_cost_estimate: string;
  is_shipping_included: boolean;
  incoterms?: string;
  shipping_method?: string;
  payment_method?: string;
  production_days?: number;
  delivery_days?: number;
  total_cbm?: string;
  total_weight_kg?: string;
  notes?: string;
  // ── T-IMPOFFER: مصدر العرض، قرار الملاءمة، وملفات المورد ──
  alibaba_link?: string;
  supplier_contact?: string;
  decision_reason?: string;
  attachments?: SupplierQuotationAttachmentDto[];
  /** T-OFFERSTATE: دفتر ملاحظات مؤرَّخ — التاريخ والكاتب يُختمان في الخادم. */
  notes_log?: SupplierQuotationNoteDto[];
  // ── ISSUE #122: نسبُ العرض إلى طلبيةٍ ومستقبِلٍ فيها ──
  /**
   * الطلبية التي وُلد منها هذا العرض، والمستقبِلُ الذي يُسعَّر عنه. يُكتبان
   * عند **الإنشاء وحده** — عرضٌ يُنقَل من طلبيةٍ لأخرى بعد كتابته يعني
   * مقارنةً بأسعارٍ قيلت في سياقٍ آخر. `null` = عرضٌ حرٌّ بلا طلبية.
   */
  rfq?: number | null;
  rfq_recipient?: number | null;
  /** يُحسم في الخادم لا هنا — راجع `SupplierQuotationEntrySource`. */
  entry_source?: SupplierQuotationEntrySource;
  /** الصفقة الناتجة عن التحويل — كائن لا رقم، فرقم الصفقة يُعرض بجانب الحالة. */
  converted_deal?: { id: number; ref_number: string; stage?: string | null } | null;
  /** T-PLINEAGE: المستند الناتج محلياً — طلبية أو فاتورة، بالرقم والمعرّف. */
  converted_order?: { id: number; order_number: string; status?: string } | null;
  converted_invoice?: { id: number; invoice_number: string; status?: string } | null;
  created_at?: string;
  updated_at?: string;
  lines: SupplierQuotationLineDto[];
}

export interface SupplierQuotationAttachmentDto {
  name: string;
  url: string;
  type?: string;
  size?: number;
}

export interface SupplierQuotationNoteDto {
  text: string;
  /** ISO — يُختم في الخادم؛ ساعة المتصفح ليست مصدراً موثوقاً. */
  at?: string;
  by?: string;
}

export type SupplierQuotationWrite = Omit<
  SupplierQuotationDto,
  | "id"
  | "supplier_name"
  | "is_draft_supplier"
  | "currency_code"
  | "subtotal"
  | "tax_amount"
  | "grand_total"
  | "converted_deal"
  | "converted_order"
  | "converted_invoice"
  | "created_at"
  | "updated_at"
  /* ISSUE #122: الخادم يحسم مَن سعّر — لا تكتبه الواجهة ولو أرسلته. */
  | "entry_source"
> & {
  quotation_number?: string;
};

export async function listSupplierQuotations(
  scope: ProcurementScope,
): Promise<SupplierQuotationDto[]> {
  return apiGetList(`${BASE}/supplier-quotations/`, {
    tenantId: tenantId(),
    query: { scope },
  });
}

export async function getSupplierQuotation(
  id: number,
): Promise<SupplierQuotationDto> {
  return apiGetObject(`${BASE}/supplier-quotations/${id}/`, {
    tenantId: tenantId(),
  });
}

export async function createSupplierQuotation(
  body: SupplierQuotationWrite,
): Promise<SupplierQuotationDto> {
  return apiPostObject(`${BASE}/supplier-quotations/`, body, {
    tenantId: tenantId(),
  });
}

export async function updateSupplierQuotation(
  id: number,
  body: Partial<SupplierQuotationWrite>,
): Promise<SupplierQuotationDto> {
  return apiPatchObject(`${BASE}/supplier-quotations/${id}/`, body, {
    tenantId: tenantId(),
  });
}

export async function deleteSupplierQuotation(id: number): Promise<void> {
  return apiDelete(`${BASE}/supplier-quotations/${id}/`, {
    tenantId: tenantId(),
  });
}

/* T113-2: `convertSupplierQuotationToImportDeal` حُذفت — لم يعد هناك تحويلٌ
   بضغطة. العرض المقبول يُقرأ بـ`getSupplierQuotation` ويُفتح محرَّراً غير محفوظ
   (`utils/quotationToDraftDeal`)، والصفقة تُنشأ عند «حفظ» فتطالب بعرضها المصدر. */

export type PurchaseOrderStatus =
  | "draft"
  | "confirmed"
  | "converted"
  | "cancelled";

export interface PurchaseOrderLineDto {
  id?: number;
  product: number;
  product_name?: string;
  seq?: number;
  name_snapshot?: string;
  description_line?: string;
  quantity: string;
  unit_price: string;
  line_total?: string;
}

export interface PurchaseOrderDto {
  id: number;
  order_number: string;
  supplier: number;
  supplier_name?: string;
  quotation?: number | null;
  quotation_number?: string | null;
  invoice?: number | null;
  invoice_number?: string | null;
  order_date: string;
  expected_delivery_date?: string | null;
  status: PurchaseOrderStatus;
  status_display?: string;
  currency: number;
  currency_code?: string;
  exchange_rate: string;
  subtotal: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  grand_total: string;
  shipping_cost: string;
  is_shipping_included: boolean;
  shipping_method?: string;
  payment_method?: string;
  delivery_days?: number;
  notes?: string;
  cancel_reason?: string;
  created_at?: string;
  updated_at?: string;
  /** T-RECVIS: تقدّم استلام فاتورة هذه الطلبية — الرحلة تكمل هناك لا هنا. */
  invoice_receipt_status_display?: string | null;
  invoice_receipt_progress?: {
    ordered: string;
    received: string;
    remaining: string;
    lines_total: number;
    lines_remaining: number;
  } | null;
  lines: PurchaseOrderLineDto[];
}

export type PurchaseOrderWrite = Omit<
  PurchaseOrderDto,
  | "id"
  | "quotation_number"
  | "invoice"
  | "invoice_number"
  | "status"
  | "status_display"
  | "currency_code"
  | "subtotal"
  | "tax_amount"
  | "grand_total"
  | "cancel_reason"
  | "created_at"
  | "updated_at"
> & {
  order_number?: string;
};

export async function listPurchaseOrders(): Promise<PurchaseOrderDto[]> {
  return apiGetList(`${BASE}/purchase-orders/`, { tenantId: tenantId() });
}

export async function getPurchaseOrder(id: number): Promise<PurchaseOrderDto> {
  return apiGetObject(`${BASE}/purchase-orders/${id}/`, {
    tenantId: tenantId(),
  });
}

export async function createPurchaseOrder(
  body: PurchaseOrderWrite,
): Promise<PurchaseOrderDto> {
  return apiPostObject(`${BASE}/purchase-orders/`, body, {
    tenantId: tenantId(),
  });
}

export async function updatePurchaseOrder(
  id: number,
  body: Partial<PurchaseOrderWrite>,
): Promise<PurchaseOrderDto> {
  return apiPatchObject(`${BASE}/purchase-orders/${id}/`, body, {
    tenantId: tenantId(),
  });
}

export async function confirmPurchaseOrder(id: number): Promise<PurchaseOrderDto> {
  return apiPostObject(
    `${BASE}/purchase-orders/${id}/confirm/`,
    {},
    { tenantId: tenantId() },
  );
}

export async function cancelPurchaseOrder(
  id: number,
  reason = "",
): Promise<PurchaseOrderDto> {
  return apiPostObject(
    `${BASE}/purchase-orders/${id}/cancel/`,
    { reason },
    { tenantId: tenantId() },
  );
}

export async function convertPurchaseOrderToInvoice(id: number): Promise<{
  status: "converted";
  created: boolean;
  invoice: { id: number; invoice_number: string };
}> {
  return apiPostObject(
    `${BASE}/purchase-orders/${id}/convert-to-invoice/`,
    {},
    { tenantId: tenantId() },
  );
}

export async function convertSupplierQuotationToPurchaseOrder(
  id: number,
): Promise<{
  status: "converted";
  created: boolean;
  order: PurchaseOrderDto;
}> {
  return apiPostObject(
    `${BASE}/supplier-quotations/${id}/convert-to-purchase-order/`,
    {},
    { tenantId: tenantId() },
  );
}

/** T-PLINEAGE: عرض شراء محلي مقبول ← فاتورة شراء مسودة مباشرةً (بلا طلبية). */
export async function convertSupplierQuotationToPurchaseInvoice(id: number): Promise<{
  status: "converted";
  created: boolean;
  invoice: { id: number; invoice_number: string };
}> {
  return apiPostObject(
    `${BASE}/supplier-quotations/${id}/convert-to-purchase-invoice/`,
    {},
    { tenantId: tenantId() },
  );
}

// ── ISSUE #112/#113 — الطلبية (PurchaseRFQ): تسبق عرض السعر، بلا سعر إلزامي ──

export type PurchaseRFQStatus = "draft" | "sent" | "awarded" | "cancelled";

export interface PurchaseRFQLineDto {
  id?: number;
  /** بلا منتج مسجَّل مسموح — اسمه النصّي (`name_snapshot`) يكفي داخل الطلبية. */
  product: number | null;
  product_name?: string;
  seq?: number;
  name_snapshot?: string;
  specs?: string;
  quantity: string;
  unit_of_measure?: string;
  /** داخليّ بحت — لا يخرج إلى رابط المورد ولا الطباعة ولا Excel أبداً (#112 §١). */
  estimated_price?: string | null;
}

export interface PurchaseRFQRecipientDto {
  id: number;
  supplier: number;
  supplier_name?: string;
  share: number | null;
  quotation: number | null;
  quotation_number?: string | null;
  sent_at: string | null;
  replied_at: string | null;
  created_at?: string;
  /** رابط مشاركة هذا المستقبِل وحده — ISSUE #115 قصّة ١٣. فارغ إن لم يُرسَل بعد. */
  share_url?: string | null;
  share_expires_at?: string | null;
  share_revoked_at?: string | null;
  share_is_live?: boolean;
}

export interface PurchaseRFQDto {
  id: number;
  /** فارغ حتى أوّل إرسال — لا يُخصَّص عند الإنشاء (#112 §الترقيم). */
  rfq_number: string | null;
  scope: ProcurementScope;
  scope_display?: string;
  rfq_date: string;
  status: PurchaseRFQStatus;
  status_display?: string;
  reply_deadline?: string | null;
  notes?: string;
  lines: PurchaseRFQLineDto[];
  recipients: PurchaseRFQRecipientDto[];
  /** «وردت عروض» — عدّادان مشتقّان لا حقلان مخزَّنان (#112 §٧). */
  recipients_count: number;
  replies_count: number;
  created_at?: string;
  updated_at?: string;
}

export type PurchaseRFQWrite = {
  scope: ProcurementScope;
  rfq_date: string;
  reply_deadline?: string | null;
  notes?: string;
  lines: PurchaseRFQLineDto[];
};

export async function listPurchaseRfqs(
  scope?: ProcurementScope,
  status?: string,
): Promise<PurchaseRFQDto[]> {
  const query: Record<string, string> = {};
  if (scope) query.scope = scope;
  if (status) query.status = status;
  return apiGetList(`${BASE}/purchase-rfqs/`, {
    tenantId: tenantId(),
    query: Object.keys(query).length ? query : undefined,
  });
}

/**
 * ISSUE #112: «نسخةٌ جديدة» من طلبيةٍ مقفلة — مسودّةٌ بلا رقم ولا مستقبِلين،
 * والأصلُ لا يُمَسّ. الترقيمُ يبقى عند أوّل إرسال.
 */
export async function duplicatePurchaseRfq(id: number): Promise<PurchaseRFQDto> {
  return apiPostObject(`${BASE}/purchase-rfqs/${id}/duplicate/`, {}, { tenantId: tenantId() });
}

export async function getPurchaseRfq(id: number): Promise<PurchaseRFQDto> {
  return apiGetObject(`${BASE}/purchase-rfqs/${id}/`, { tenantId: tenantId() });
}

export async function createPurchaseRfq(
  body: PurchaseRFQWrite,
): Promise<PurchaseRFQDto> {
  return apiPostObject(`${BASE}/purchase-rfqs/`, body, { tenantId: tenantId() });
}

/** مسموحٌ على المسودة وحدها — البنود تُقفل عند أوّل إرسال (400 بعده، #112 §٧). */
export async function updatePurchaseRfq(
  id: number,
  body: Partial<PurchaseRFQWrite>,
): Promise<PurchaseRFQDto> {
  return apiPatchObject(`${BASE}/purchase-rfqs/${id}/`, body, { tenantId: tenantId() });
}

export async function deletePurchaseRfq(id: number): Promise<void> {
  return apiDelete(`${BASE}/purchase-rfqs/${id}/`, { tenantId: tenantId() });
}

/**
 * أوّل إرسال: يقفل البنود ويخصّص الرقم إن لم يكن مخصّصاً. `supplierIds`
 * اختياري — موردون يُضافون مستقبِلين قبل الإرسال مباشرةً.
 */
export async function sendPurchaseRfq(
  id: number,
  supplierIds: number[] = [],
): Promise<PurchaseRFQDto> {
  return apiPostObject(
    `${BASE}/purchase-rfqs/${id}/send/`,
    { supplier_ids: supplierIds },
    { tenantId: tenantId() },
  );
}

export async function cancelPurchaseRfq(id: number): Promise<PurchaseRFQDto> {
  return apiPostObject(`${BASE}/purchase-rfqs/${id}/cancel/`, {}, { tenantId: tenantId() });
}

/** ISSUE #116 (مواصفة #108 §٨): ترسيةٌ كاملةٌ لموردٍ واحد — `supplierId` يحسم
 * أيّ ردّ فائزٌ، ويعود المستند الناتج (أمر شراء أو فاتورة بحسب المفتاح). */
export interface PurchaseRFQAwardResult extends PurchaseRFQDto {
  awarded_supplier_id: number;
  awarded_document: { type: "purchase_order" | "purchase_invoice"; id: number; number: string };
}

export async function awardPurchaseRfq(
  id: number,
  supplierId: number,
): Promise<PurchaseRFQAwardResult> {
  return apiPostObject(
    `${BASE}/purchase-rfqs/${id}/award/`,
    { supplier: supplierId },
    { tenantId: tenantId() },
  );
}

// ── ISSUE #116 (مواصفة #108 §٨) — مصفوفة الموردين: شاشةٌ مستقلّة عند الطلب ──

export interface RfqComparisonLineDto {
  id: number;
  seq: number;
  product_id: number | null;
  name: string;
  quantity: string;
  unit_of_measure: string;
  /** بالعملة الأساسية دائماً — `null` بلا سعرٍ تقديريّ (فارغ لا صفر). */
  estimated_price: string | null;
}

export interface RfqComparisonSupplierDto {
  supplier_id: number;
  supplier_name: string;
  quotation_id: number;
  quotation_number: string;
  currency_code: string;
  exchange_rate: string;
  replied_at: string | null;
  /** مفتاحٌ = معرّف بند الطلبية (نصّاً) — `null` = لم يُسعّره هذا المورد. */
  prices: Record<string, string | null>;
  /** إجماليّ البضاعة وحده بالعملة الأساسية — لا حقل شحنٍ إطلاقاً. */
  goods_total_base: string;
  /**
   * ISSUE #122: مَن كتب هذا العمود. شارةٌ عرضيّةٌ صرف بلا أيّ حساب — عمودٌ
   * سعّره المورّد بنفسه وعمودٌ أدخلناه عنه ليسا سواءً في الثقة، والمصفوفةُ
   * تقولها بدل أن يتذكّرها المالك.
   */
  entry_source?: SupplierQuotationEntrySource;
}

export interface RfqComparisonDto {
  rfq_id: number;
  rfq_number: string | null;
  status: PurchaseRFQStatus;
  lines: RfqComparisonLineDto[];
  /** موردٌ لم يردّ بعد لا عمود له هنا. */
  suppliers: RfqComparisonSupplierDto[];
}

export async function getRfqComparison(id: number): Promise<RfqComparisonDto> {
  return apiGetObject(`${BASE}/purchase-rfqs/${id}/comparison/`, { tenantId: tenantId() });
}

/** المسموح بعد الإرسال (#112 §٧): مستقبِلٌ جديد بلا مسّ البنود أو الحالة. */
export async function addPurchaseRfqRecipient(
  id: number,
  supplierId: number,
): Promise<PurchaseRFQRecipientDto> {
  return apiPostObject(
    `${BASE}/purchase-rfqs/${id}/recipients/`,
    { supplier: supplierId },
    { tenantId: tenantId() },
  );
}
