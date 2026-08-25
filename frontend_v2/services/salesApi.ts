import { resolveTenantId } from "../utils/tenantContext";
import { eventBus } from "../utils/eventBus";
import {
  apiDelete,
  apiGetList,
  apiGetPagedList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import type { PagedList } from "./restApi";
import type { SerialEntryMode } from "../types/inventory";

const tid = () => resolveTenantId();
const BASE = "sales";

/** حالة تسليم بضاعة الفاتورة للعميل (مرآة حالة الاستلام في الشراء). */
export type DeliveryStatus =
  | "not_delivered"
  | "partially_delivered"
  | "delivered";

/** N8-T11: نوع المستند الموحّد — فاتورة بيع/شراء أو مرجعهما. */
export type InvoiceKind = "sale" | "sale_return" | "purchase" | "purchase_return";

export type SalesInvoiceRow = {
  id: number;
  invoice_number: string;
  /** T-RETURNUI: يميّز مرجع البيع عن الفاتورة في القائمة والعرض. */
  invoice_kind?: InvoiceKind;
  customer: number;
  customer_name?: string;
  invoice_date: string;
  due_date?: string | null;
  invoice_type: "cash" | "credit";
  status: string;
  grand_total: string;
  amount_paid?: string;
  remaining_balance?: string;
  /** T-INTENT: دفعة مرفقة بمسودة لم تُرحَّل بعد — تُعرَض ولا تدخل «المدفوع». */
  pending_payment_total?: string;
  payment_status?: "paid" | "partially_paid" | "unpaid";
  payment_status_display?: string;
  /** T-DUE: التأخّر بُعدٌ فوق حالة الدفع — لا قيمةٌ رابعة فيها. */
  is_overdue?: boolean;
  days_overdue?: number;
  payment_terms_days?: number | null;
  customer_balance?: string;
  currency: number;
  stock_on_post?: boolean;
  delivery_status?: DeliveryStatus;
  delivery_status_display?: string;
  /** M2-T1: book number (0 = manual). */
  book_number?: number;
};

/** M2-T3: cheque attached to a sales invoice (read-side). */
export type AttachedCheque = {
  id: number;
  cheque_number: string;
  bank_name?: string;
  account_number?: string;
  bank_branch?: string;
  amount: string;
  due_date?: string | null;
  issue_date?: string | null;
  payee_name?: string | null;
  status: string;
  notes?: string | null;
};

export type SalesInvoiceDetail = SalesInvoiceRow & {
  /** T-RETURNUI: الفاتورة الأصلية التي يعود إليها المرجع (للمراجيع فقط). */
  original_invoice?: number | null;
  original_invoice_number?: string | null;
  /** T-SLINEAGE: المستند الذي وُلدت منه الفاتورة (طلبية زبون أو عرض سعر). */
  source_document?: {
    kind: "order" | "quotation";
    id: number;
    number: string;
    origin_kind?: "quotation" | null;
    origin_id?: number | null;
    origin_number?: string | null;
  } | null;
  exchange_rate: string;
  subtotal_excl_tax: string;
  invoice_discount: string;
  tax_amount: string;
  revenue_account: number | null;
  cash_or_bank_account: number | null;
  accounts_receivable_account: number | null;
  journal: number | null;
  notes: string;
  lines: {
    id: number;
    product: number;
    product_name?: string | null;
    quantity: string;
    delivered_quantity?: string;
    unit_price: string;
    line_discount: string;
    tax_rate: number | null;
    line_total_excl_tax: string;
    line_tax_amount: string;
    /** M2-T2: Kit line columns */
    unit?: string;
    warehouse?: string;
    catalog_no?: string;
    expiry_date?: string | null;
    extra_quantity?: string | null;
    line_tax_percent?: string | null;
    /** T-SERIAL: الوحدات التي اختارها البائع لهذا البند (تبقى بعد إلغاء الترحيل). */
    serials?: string[] | null;
    /** ملاحظة الموظف على البند — لا تُطبع للعميل. */
    internal_note?: string | null;
    /** ملاحظة تُطبع للعميل تحت اسم الصنف. */
    customer_note?: string | null;
  }[];
  created_at?: string;
  // M2-T1: Kit header fields
  book_number?: number;
  second_date?: string | null;
  licensed_dealer_no?: string;
  settlement_invoice_no?: string;
  prices_include_tax?: boolean;
  discount_percent?: string;
  // M2-T3: Financial instrument + attached voucher
  financial_document_no?: string;
  /**
   * T2: عمودان قديمان صارا **للقراءة فقط** في الخادم — النقد لم يعد يُكتب على
   * الفاتورة (كان يُحفظ ولا يُرحَّل)، وإنما يمرّ من `collectSalesInvoice`. يبقى
   * النوع لأن القراءات ما زالت تُعيدهما على الفواتير القديمة.
   */
  readonly attached_cash_amount?: string;
  readonly attached_cash_account?: number | null;
  cheques?: AttachedCheque[];
  /**
   * THA-132 — تقريبٌ **لا يطابق كشف الحساب**: يطرح «المتبقّي» من رصيد اليوم،
   * فالفاتورة المدفوعة بالكامل تُظهر أثراً صفرياً وهي دائنةُ ذمم بكامل
   * إجماليها. الجواب الصحيح في `getInvoiceCustomerLedger` (تبويب حساب العميل).
   */
  customer_balance_before_invoice?: string;
  customer_balance_after_invoice?: string;
  /** «رقم الحركة» المخزنية — يُعرض في شريط الحالة (سلوك الأصيل). */
  stock_movement_no?: number | null;
  payment_details?: Array<{
    id: number;
    payment_date: string;
    allocated_amount: string;
    total_payment_amount: string;
    currency_code: string;
    exchange_rate: string;
    is_posted: boolean;
    journal: number | null;
    notes?: string;
  }>;
  // M2-T4: source-discount overrides (null = use customer default)
  source_discount_percent_override?: string | null;
  source_discount_amount_override?: string | null;
};

export async function listSalesInvoices(
  query?: Record<string, string | number | boolean | undefined>
): Promise<SalesInvoiceRow[]> {
  return apiGetList(`${BASE}/invoices/`, { tenantId: tid(), query });
}

export async function listSalesInvoicesPage(
  query?: Record<string, string | number | boolean | undefined>
): Promise<PagedList<SalesInvoiceRow>> {
  return apiGetPagedList(`${BASE}/invoices/`, {
    tenantId: tid(),
    query: { ...query, page: query?.page ?? 1 },
  });
}

export async function getSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiGetObject(`${BASE}/invoices/${id}/`, { tenantId: tid() });
}

/** F4: preview the next invoice number for the active tenant/book (non-consuming). */
export async function getNextInvoiceNumber(book: number): Promise<string> {
  const data = await apiGetObject<{ next_number?: string }>(
    `${BASE}/invoices/next-number/?book=${encodeURIComponent(String(book))}`,
    { tenantId: tid() }
  );
  return data?.next_number || "";
}

export async function createSalesInvoice(
  body: Record<string, unknown>
): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/`, body, { tenantId: tid() });
}

export async function patchSalesInvoice(
  id: number,
  body: Record<string, unknown>
): Promise<SalesInvoiceDetail> {
  return apiPatchObject(`${BASE}/invoices/${id}/`, body, { tenantId: tid() });
}

export async function postSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/post/`, {}, { tenantId: tid() });
}

/** T4: شيك داخل تحصيل الفاتورة — تاريخ الاستحقاق إلزامي (يفرضه الخادم أيضاً). */
export type InvoiceCollectCheque = {
  cheque_number: string;
  amount: string;
  due_date: string;
  bank_name?: string;
};

export type InvoiceCollectPayload = {
  /**
   * «غير مذكور» ≠ «صفر»: يُحذف المفتاح حين لا نقد أصلاً — فالفاتورة النقدية
   * يُكمّل الخادم نقدها، أمّا `"0"` فإعلانُ نيّةٍ بعدم دفع نقد يُحاسَب عليه.
   */
  cash?: string;
  cash_account_id?: number;
  cheques?: InvoiceCollectCheque[];
  /** خصمٌ من رصيد العميل «على الحساب» — ربطُ سندٍ مرحّل، بلا قيد جديد. */
  from_on_account?: Array<{ payment_id: number; amount: string }>;
  post_invoice?: boolean;
  payment_date?: string;
};

/**
 * T4: تحصيل الفاتورة من داخلها — نقد و/أو شيكات و/أو رصيد العميل في نداءٍ
 * **واحد ذرّي** يُنتج سند قبض واحداً مرحّلاً (`invoices/{id}/collect/`). على
 * المسودة يُمرَّر `post_invoice: true` فتُرحَّل وتُحصَّل معاً.
 *
 * الردّ = الفاتورة كاملةً بعد التحصيل + `payment_id`، فتُحدَّث الشاشة منه بلا
 * جلبٍ ثانٍ. الفشل يُعيد 400 برسالة عربية جاهزة تُعرض كما هي.
 */
export async function collectSalesInvoice(
  id: number,
  body: InvoiceCollectPayload,
): Promise<SalesInvoiceDetail & { payment_id: number | null }> {
  return apiPostObject(`${BASE}/invoices/${id}/collect/`, body, { tenantId: tid() });
}

/** نيّة دفع تُرفَق بالمسودة — نقد و/أو شيكات، بدلالة الاستبدال. */
export type InvoiceIntentPayload = {
  cash_amount: string;
  cash_account_id?: number | null;
  cheques: Array<{
    cheque_number: string;
    amount: string;
    due_date?: string | null;
    bank_name?: string;
  }>;
};

/**
 * T-INTENT: يسجّل الدفعة على **المسودة** بلا ترحيل ولا سند — نيّةٌ تتحوّل سند
 * قبضٍ واحداً عند ترحيل الفاتورة. بدلالة الاستبدال: كل نداء يحلّ محلّ ما سبقه،
 * ونداءٌ بـ`{cash_amount: "0", cheques: []}` يمسح النيّة كلّها.
 *
 * يقابله `collectSalesInvoice` حين يريد المستخدم الترحيل والتحصيل فوراً.
 */
export async function attachSalesInvoiceIntent(
  id: number,
  body: InvoiceIntentPayload,
): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/payment-voucher/`, body, { tenantId: tid() });
}

/** التراجع عن ترحيل الفاتورة: حذف قيودها وحركات مخزونها وإرجاعها مسودة (Feature 1). */
export async function unpostSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/unpost/`, {}, { tenantId: tid() });
}

export async function deleteSalesInvoice(id: number): Promise<void> {
  return apiDelete(`${BASE}/invoices/${id}/`, { tenantId: tid() });
}

export async function duplicateSalesInvoice(id: number): Promise<SalesInvoiceDetail> {
  return apiPostObject(`${BASE}/invoices/${id}/duplicate/`, {}, { tenantId: tid() });
}

export async function createDeliveryOrder(
  invoiceId: number,
  notes?: string
): Promise<{ id: number; invoice: number; status: string }> {
  return apiPostObject(
    `${BASE}/invoices/${invoiceId}/delivery-order/`,
    { notes: notes ?? "" },
    { tenantId: tid() }
  );
}

export async function deliverOrder(deliveryOrderId: number): Promise<unknown> {
  return apiPostObject(
    `${BASE}/delivery-orders/${deliveryOrderId}/deliver/`,
    {},
    { tenantId: tid() }
  );
}

/** بند فاتورة قابل للتسليم — المفوتر/المسلَّم/المتبقي (مصدره الخادم). */
export type DeliveryLineRow = {
  line_id: number;
  product: number;
  product_name: string;
  quantity: string;
  delivered_quantity: string;
  remaining_quantity: string;
};

export type DeliveryLinesResponse = {
  invoice_number: string;
  delivery_status: DeliveryStatus;
  delivery_status_display?: string;
  stock_on_post: boolean;
  lines: DeliveryLineRow[];
};

export async function getDeliveryLines(
  invoiceId: number
): Promise<DeliveryLinesResponse> {
  return apiGetObject(`${BASE}/invoices/${invoiceId}/delivery-lines/`, {
    tenantId: tid(),
  });
}

/* ── THA-132: تبويبات سياق الفاتورة ─────────────────────────────────────────
   ثلاث نقاط قراءة تُطلب **عند فتح تبويبها فقط** — لا شيء منها يُنادى مع فتح
   الفاتورة. يحرس ذلك `e2e/sales-invoice-context-tabs.spec.ts` بعدّ النداءات. */

/** صفّ حركة مخزون سبّبتها هذه الفاتورة («رقم الحركة» في مرجع الأصيل). */
/** T-PCTX: عقد تبويبات السياق لجانب البيع — يستهلكه `DocumentContextTabs`. */
export const salesInvoiceContextApi = {
  getStockMovements: (id: number) => getInvoiceStockMovements(id),
  getPartnerLedger: (id: number) => getInvoiceCustomerLedger(id),
  listAttachments: (id: number) => listInvoiceAttachments(id),
  addAttachment: (id: number, url: string) => addInvoiceAttachment(id, url),
  deleteAttachment: (id: number, attachmentId: number) =>
    deleteInvoiceAttachment(id, attachmentId),
};

export type InvoiceStockMovementRow = {
  id: number;
  date: string | null;
  movement_type: string;
  movement_type_label: string;
  reference_type: string | null;
  product_id: number;
  product_name: string;
  warehouse: string | null;
  qty_in: string;
  qty_out: string;
  quantity_before: string;
  running_balance: string;
  unit_cost: string;
  total_cost: string;
};

export type InvoiceStockMovementsResponse = {
  results: InvoiceStockMovementRow[];
  count: number;
  total_cost: string;
  /** سبب الفراغ يصل مع الحمولة — جدولٌ فارغ بلا تفسير يُقرأ كعطل. */
  is_posted: boolean;
  stock_on_post: boolean;
  delivery_status: DeliveryStatus;
  delivery_status_display?: string;
};

export async function getInvoiceStockMovements(
  invoiceId: number
): Promise<InvoiceStockMovementsResponse> {
  return apiGetObject(`${BASE}/invoices/${invoiceId}/stock-movements/`, {
    tenantId: tid(),
  });
}

/** صفّ من كشف حساب العميل، بنفس شكل صفوف بطاقة الطرف (مصدر واحد). */
export type InvoiceLedgerRow = {
  id: number;
  journal_id: number;
  date: string | null;
  reference_type: string | null;
  reference_id: number | null;
  description: string;
  debit: string;
  credit: string;
  balance_before: string;
  running_balance: string;
  is_anchor?: boolean;
};

export type InvoiceLedgerResponse = {
  results: InvoiceLedgerRow[];
  count: number;
  closing_balance: string;
  customer_name?: string | null;
  /** null = الفاتورة لم تمسّ الحساب بعد (مسودّة) — حالة معلنة لا خطأ. */
  anchor: {
    line_ids: number[];
    balance_before: string;
    balance_after: string;
    effect: string;
  } | null;
  reason?: string;
};

export async function getInvoiceCustomerLedger(
  invoiceId: number,
  limit = 20
): Promise<InvoiceLedgerResponse> {
  return apiGetObject(`${BASE}/invoices/${invoiceId}/customer-ledger/`, {
    tenantId: tid(),
    query: { limit },
  });
}

export type InvoiceAttachmentRow = {
  id: number;
  url: string;
  file_type: string;
  filename: string;
  uploaded_at: string | null;
};

export async function listInvoiceAttachments(
  invoiceId: number
): Promise<InvoiceAttachmentRow[]> {
  return apiGetList(`${BASE}/invoices/${invoiceId}/attachments/`, {
    tenantId: tid(),
  });
}

export async function addInvoiceAttachment(
  invoiceId: number,
  url: string
): Promise<InvoiceAttachmentRow> {
  return apiPostObject(
    `${BASE}/invoices/${invoiceId}/attachments/`, { url }, { tenantId: tid() },
  );
}

export async function deleteInvoiceAttachment(
  invoiceId: number,
  attachmentId: number
): Promise<void> {
  await apiDelete(
    `${BASE}/invoices/${invoiceId}/attachments/${attachmentId}/`,
    { tenantId: tid() },
  );
}

/** إرسالية بيع كما يعيدها الخادم (مستند التسليم المرتبط بفاتورة). */
export type DeliveryNoteLineDto = {
  id: number;
  invoice_line: number | null;
  product: number;
  product_name: string;
  ordered_quantity: string;
  delivered_total: string;
  remaining_quantity: string;
  quantity: string;
  /** المستودع الذي خرجت منه البضاعة (مرآة سطر إرسالية الشراء). */
  warehouse?: number | null;
  warehouse_name?: string | null;
};

export type DeliveryNoteRow = {
  id: number;
  delivery_number: string;
  delivery_date: string | null;
  invoice: number | null;
  invoice_number: string | null;
  customer: number | null;
  customer_name: string;
  customer_ref: string;
  is_standalone: boolean;
  doc_label: string;
  status: string;
  status_display?: string;
  auto_created: boolean;
  notes: string;
  lines_count: number;
  total_quantity: string;
  total_remaining: string;
  delivered_at: string | null;
  created_at: string;
};

export type DeliveryNoteDto = DeliveryNoteRow & { lines: DeliveryNoteLineDto[] };

/** سطر باقٍ غير مسلَّم عبر كل الفواتير — تقرير الطباعة/PDF. */
export type OutstandingDeliveryRow = {
  invoice: number;
  invoice_number: string;
  invoice_date: string | null;
  partner_name: string;
  product: number;
  product_name: string;
  quantity: string;
  delivered_quantity: string;
  remaining_quantity: string;
};

/** بنود الحفظ: `line_id` للمرتبط بفاتورة، و`product_id` للسند المستقل. */
export type DeliveryNoteSaveLine = {
  line_id?: number;
  product_id?: number;
  quantity: number;
  warehouse_id?: number;
};

export type DeliveryNoteSaveBody = {
  invoice?: number | null;
  partner?: number | null;
  customer_ref?: string;
  delivery_date?: string;
  notes?: string;
  lines: DeliveryNoteSaveLine[];
};

export async function listDeliveryNotes(
  query?: Record<string, string | number | undefined>
): Promise<DeliveryNoteRow[]> {
  return apiGetList(`${BASE}/delivery-orders/`, { tenantId: tid(), query });
}

export async function getDeliveryNote(id: number): Promise<DeliveryNoteDto> {
  return apiGetObject(`${BASE}/delivery-orders/${id}/`, { tenantId: tid() });
}

/** إنشاء إرسالية = تسليم البنود المحددة فعلياً (مخزون + قيد تكلفة). */
export async function createDeliveryNote(
  body: DeliveryNoteSaveBody
): Promise<DeliveryNoteDto> {
  return apiPostObject(`${BASE}/delivery-orders/`, body, { tenantId: tid() });
}

/** التعديل يعكس أثر الإرسالية القديم ويعيد تطبيق البنود الجديدة (على الخادم). */
export async function updateDeliveryNote(
  id: number,
  body: DeliveryNoteSaveBody
): Promise<DeliveryNoteDto> {
  return apiPatchObject(`${BASE}/delivery-orders/${id}/`, body, { tenantId: tid() });
}

export async function deleteDeliveryNote(id: number): Promise<void> {
  return apiDelete(`${BASE}/delivery-orders/${id}/`, { tenantId: tid() });
}

export async function getOutstandingDeliveryLines(): Promise<OutstandingDeliveryRow[]> {
  const data = await apiGetObject<{ rows?: OutstandingDeliveryRow[] }>(
    `${BASE}/delivery-orders/outstanding/`,
    { tenantId: tid() }
  );
  return data?.rows || [];
}

/** تسليم بنود مختارة (إرسالية) — خصم مخزون + قيد تكلفة للمُسلَّم فقط. */
export async function deliverInvoiceLines(
  invoiceId: number,
  lines: { line_id: number; quantity: number; warehouse_id?: number }[],
  notes?: string
): Promise<{
  delivery_id: number;
  delivery_status: DeliveryStatus;
  delivery_status_display?: string;
  lines_delivered: number;
}> {
  return apiPostObject(
    `${BASE}/invoices/${invoiceId}/deliver/`,
    { lines, notes: notes ?? "" },
    { tenantId: tid() }
  );
}

export type CreditPreviewResponse = {
  credit_limit: string | null;
  open_balance: string;
  proposed_total: string;
  projected_balance: string;
  would_exceed: boolean;
};

export async function getCreditPreview(params: {
  customer: number;
  proposed_total: string | number;
  excludeInvoice?: number;
}): Promise<CreditPreviewResponse> {
  const q = new URLSearchParams();
  q.set("customer", String(params.customer));
  q.set("proposed_total", String(params.proposed_total));
  if (params.excludeInvoice != null) q.set("exclude_invoice", String(params.excludeInvoice));
  return apiGetObject(`sales/invoices/credit-preview/?${q.toString()}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// task18 DEF-C2: آخر سعر بيع للوحدة (عام أو لعميل محدّد)
// -------------------------------------------------------------
export type LastSalePriceResponse = {
  unit_price: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
};

export async function getLastSalePrice(params: {
  product: number;
  customer?: number | "";
}): Promise<LastSalePriceResponse> {
  const q = new URLSearchParams();
  q.set("product", String(params.product));
  if (params.customer != null && params.customer !== "") q.set("customer", String(params.customer));
  return apiGetObject(`sales/invoices/last-price/?${q.toString()}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// FEAT-2: السعر المقترح لبند البيع عبر PriceResolver المشترك
// (آخر سعر دفعه العميل ← سعر البيع الافتراضي ← فارغ) مع تطبيع العملة/الضريبة.
// -------------------------------------------------------------
export type ResolvedPriceResponse = {
  unit_price: string | null;
  strategy_used: string | null;
  strategy_requested: string;
  source: { document_type: string; document_number?: string } | null;
};

export async function resolveSalePrice(params: {
  product: number;
  customer?: number | "";
  currency?: number | "";
  exchange_rate?: number | string;
  tax_inclusive?: boolean;
}): Promise<ResolvedPriceResponse> {
  const q = new URLSearchParams();
  q.set("product", String(params.product));
  if (params.customer != null && params.customer !== "") q.set("customer", String(params.customer));
  if (params.currency != null && params.currency !== "") q.set("currency", String(params.currency));
  if (params.exchange_rate != null) q.set("exchange_rate", String(params.exchange_rate));
  if (params.tax_inclusive) q.set("tax_inclusive", "true");
  return apiGetObject(`sales/invoices/resolve-price/?${q.toString()}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// DEF-004: عرض السعر لكل العميل (قائمة الكتالوج + حفظ العروض اليدوية)
// -------------------------------------------------------------
export type CustomerPriceRow = {
  product_id: number;
  sku: string | null;
  name: string;
  price: string | null;
  /** «default» = السعر العام في كرت الصنف (أضعف المصادر). */
  source: "last_invoice" | "quote" | "default";
  source_label: string;
  editable: boolean;
  invoice_number: string | null;
  prices?: Array<{
    label: string;
    unit_price: string;
    source_type: string;
    document_id: number | null;
    invoice_number: string | null;
  }>;
};

export async function getCustomerPriceList(customerId: number | string): Promise<CustomerPriceRow[]> {
  const q = new URLSearchParams({ customer: String(customerId) });
  return apiGetList(`sales/customer-price-list/?${q.toString()}`, { tenantId: tid() });
}

export async function saveCustomerQuotes(
  customerId: number | string,
  entries: { product: number; unit_price: string }[],
): Promise<{ saved: number }> {
  return apiPostObject(
    `sales/customer-price-list/save/`,
    { customer: Number(customerId), entries },
    { tenantId: tid() },
  );
}

// -------------------------------------------------------------
// task18 DEF-C1: رصيد الشريك (قبل/بعد) — يعمل للعميل والمورد
// -------------------------------------------------------------
export type PartnerBalanceResponse = {
  partner: number;
  partner_type: string;
  debit: string;
  credit: string;
  open_balance: string;
  proposed_total: string;
  projected_balance: string;
};

export async function getPartnerBalance(params: {
  partnerId: number | string;
  proposedTotal?: string | number;
}): Promise<PartnerBalanceResponse> {
  const q = new URLSearchParams();
  if (params.proposedTotal != null) q.set("proposed_total", String(params.proposedTotal));
  const qs = q.toString();
  return apiGetObject(`partners/${params.partnerId}/balance/${qs ? `?${qs}` : ""}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// task18 DEF-C4: تقرير أرباح الفواتير
// -------------------------------------------------------------
export type InvoiceProfitRow = {
  invoice: number;
  invoice_number: string;
  invoice_date: string | null;
  customer: number | null;
  customer_name: string;
  revenue: string;
  cost: string;
  profit: string;
  margin_pct: string;
};

export type InvoiceProfitsResponse = {
  rows: InvoiceProfitRow[];
  totals: {
    count: number;
    revenue: string;
    cost: string;
    profit: string;
    margin_pct: string;
  };
};

export async function getInvoiceProfits(params: {
  dateFrom?: string;
  dateTo?: string;
  customer?: number;
}): Promise<InvoiceProfitsResponse> {
  const q = new URLSearchParams();
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  if (params.customer != null) q.set("customer", String(params.customer));
  const qs = q.toString();
  return apiGetObject(`sales/invoices/profits/${qs ? `?${qs}` : ""}`, { tenantId: tid() });
}

export type FifoAllocationRow = {
  invoice: number;
  invoice_number: string;
  amount: string;
};

export async function suggestFifoAllocations(params: {
  partner: number;
  amount: string | number;
}): Promise<FifoAllocationRow[]> {
  return apiPostObject(
    `${BASE}/payments/suggest-fifo-allocations/`,
    { partner: params.partner, amount: params.amount },
    { tenantId: tid() }
  );
}

// -------------------------------------------------------------
// Customer Payments (دفعات العملاء)
// -------------------------------------------------------------
export type CustomerPaymentAllocation = {
  id?: number;
  invoice: number;
  amount: string;
  amount_in_invoice_currency?: string;
  conversion_rate?: string;
};

export type CustomerPaymentRow = {
  id: number;
  partner: number;
  partner_name?: string;
  payment_date: string;
  amount: string;
  currency: number;
  exchange_rate: string;
  cash_or_bank_account: number;
  journal: number | null;
  is_posted: boolean;
  notes: string;
  allocations: CustomerPaymentAllocation[];
  /** T-ONACC: المُوزَّع على الفواتير والمتبقّي «على الحساب» (محسوبان في الخادم). */
  allocated_amount?: string;
  unallocated_amount?: string;
  created_at?: string;
};

export async function listCustomerPayments(
  query?: Record<string, string | number | boolean | undefined>,
): Promise<CustomerPaymentRow[]> {
  // P0-5: القائمة مُرقَّمة إلزامياً — apiGetList يفكّ غلاف results (صفحة
  // واحدة). مرِّر page/page_size صراحةً؛ الاستدعاءات المفلترة بشريك تكتفي
  // بسقف 200.
  return apiGetList(`${BASE}/payments/`, { tenantId: tid(), query });
}

export async function listCustomerPaymentsPage(
  query?: Record<string, string | number | boolean | undefined>,
): Promise<{ results: CustomerPaymentRow[]; count: number; hasNext: boolean }> {
  return apiGetPagedList(`${BASE}/payments/`, { tenantId: tid(), query });
}

export async function getCustomerPayment(id: number): Promise<CustomerPaymentRow> {
  return apiGetObject(`${BASE}/payments/${id}/`, { tenantId: tid() });
}

export async function createCustomerPayment(
  body: {
    partner: number;
    payment_date: string;
    amount: string | number;
    currency: number;
    exchange_rate?: string | number;
    cash_or_bank_account: number;
    notes?: string;
    allocations?: Array<{ invoice: number; amount: string | number }>;
    /** T-ONEPAY: شيكات داخل السند — مبالغها جزء من `amount` لا إضافة عليه. */
    cheques?: Array<{
      cheque_number: string;
      amount: string | number;
      bank_name?: string;
      account_number?: string;
      bank_branch?: string;
      payee_name?: string;
      due_date?: string | null;
      issue_date?: string | null;
    }>;
    /** T-AUTOPOST: يسمو على إعداد الشركة — true = حفظ وترحيل، false = مسودة. */
    auto_post?: boolean;
  },
): Promise<CustomerPaymentRow & { auto_post_error?: string }> {
  return apiPostObject(`${BASE}/payments/`, body, { tenantId: tid() });
}

export async function postCustomerPayment(id: number): Promise<CustomerPaymentRow> {
  return apiPostObject(`${BASE}/payments/${id}/post/`, {}, { tenantId: tid() });
}

export async function deleteCustomerPayment(id: number): Promise<void> {
  return apiDelete(`${BASE}/payments/${id}/`, { tenantId: tid() });
}

/**
 * التراجع عن ترحيل سند قبض: يحذف قيوده ويُرجِع ما سدّده من الفواتير
 * (فكّ التوزيعات) ويعيد شيكاته إلى مسودة — السند نفسه يبقى مسودةً قابلة
 * للتعديل أو الحذف. الصلاحية: sales.payment.unpost.
 */
export async function unpostCustomerPayment(id: number): Promise<CustomerPaymentRow> {
  return apiPostObject(`${BASE}/payments/${id}/unpost/`, {}, { tenantId: tid() });
}

/**
 * T-ONACC: توزيع سند قبض على فواتير — يعمل قبل الترحيل وبعده. بعد الترحيل هو
 * ربط فقط (لا قيد جديد): الذمم خُفِّضت وقت الترحيل «على الحساب».
 */
export async function allocateCustomerPayment(
  id: number,
  allocations: Array<{ invoice: number; amount: string | number }>,
): Promise<CustomerPaymentRow> {
  return apiPostObject(`${BASE}/payments/${id}/allocate/`, { allocations }, { tenantId: tid() });
}

// -------------------------------------------------------------
// Sales Settings (إعدادات المبيعات المركزية)
// -------------------------------------------------------------
export type SalesSettings = {
  id: number;
  default_customer: number | null;
  default_customer_name?: string;
  default_currency: number | null;
  default_currency_code?: string;
  default_revenue_account_product: number | null;
  default_revenue_account_product_name?: string;
  default_revenue_account_service: number | null;
  default_revenue_account_service_name?: string;
  default_cash_account: number | null;
  default_cash_account_name?: string;
  default_inventory_account: number | null;
  default_cogs_account: number | null;
  default_ar_account: number | null;
  default_payment_type: "cash" | "credit";
  stock_on_post_default: boolean;
  allow_negative_stock_default: boolean;
  default_vat_rate: number | null;
  default_vat_rate_code?: string;
  default_vat_rate_value?: string;
  prices_include_tax: boolean;
  auto_post_invoices: boolean;
  /** T-AUTOPOST: ترحيل سندات القبض/الصرف فور الحفظ (الافتراضي: مُفعَّل). */
  auto_post_payments: boolean;
  show_journal_preview: boolean;
  /** T-S2: تنبيه عند تكرار الصنف (يقود T-R3). */
  warn_on_duplicate_item: boolean;
  /** منع حفظ/ترحيل فاتورة بيع بخسارة (الافتراضي مُعطّل). */
  block_loss_invoices: boolean;
  /** T-DORMANT: أيام صمت العميل قبل إشعار «عميل مختفٍ» (0 = تعطيل، الافتراضي 30). */
  dormant_customer_days: number;
  /** T-ORDERS: أيام صلاحية عرض السعر افتراضياً (0 = بلا انتهاء، الافتراضي 14). */
  quotation_valid_days: number;
  /** T-ORDERS: أيام حجز الكمية للطلبية المؤكَّدة (0 = بلا حجز، الافتراضي 7). */
  order_reserve_days: number;
  /** T-ORDERS: إظهار «حذف» للعروض والطلبيات (الإلغاء متاح دائماً). */
  allow_document_delete: boolean;
  /** T-RESERVEGUARD: رفض ترحيل فاتورة تسحب كمية محجوزة لطلبية زبون آخر (مُفعَّل افتراضياً). */
  block_reserved_stock_sale: boolean;
  /** T-SERIAL: نمط إدخال الرقم التسلسلي في بنود فاتورة البيع (الافتراضي «معطّل»). */
  serial_entry_mode: SerialEntryMode;
  default_shipping_origin: string;
  default_shipping_destination: string;
  /** تسمية مستند التسليم المرتبط بفاتورة (يحرّرها المستخدم). */
  delivery_doc_label: string;
  /** تسمية المستند بلا فاتورة مرتبطة. */
  standalone_delivery_label: string;
  allow_standalone_delivery: boolean;
  allow_edit_delivery: boolean;
  updated_at?: string;
};

export async function getSalesSettings(): Promise<SalesSettings> {
  return apiGetObject(`${BASE}/settings/current/`, { tenantId: tid() });
}

/** T-S3: استعادة خريطة القيد الافتراضية (الحسابات الافتراضية لكل نوع فاتورة). */
export async function restoreSalesSettingsDefaults(): Promise<SalesSettings> {
  const settings = await apiPostObject(`${BASE}/settings/restore-defaults/`, {}, { tenantId: tid() });
  try { eventBus.publish("settings", tid()); } catch (e) { console.error(e); }
  return settings as SalesSettings;
}

export async function updateSalesSettings(
  body: Partial<SalesSettings>,
): Promise<SalesSettings> {
  const settings = await apiPatchObject(`${BASE}/settings/current/`, body, { tenantId: tid() });
  try {
    eventBus.publish("settings", tid());
  } catch (e) {
    console.error("Failed to publish settings event:", e);
  }
  return settings;
}

export async function getAgingReport(): Promise<
  {
    invoice_id: number;
    invoice_number: string;
    customer_id: number;
    customer_name: string;
    invoice_date: string;
    due_date?: string | null;
    grand_total: string;
    amount_paid: string;
    remaining: string;
  }[]
> {
  return apiGetList(`${BASE}/reports/aging/`, { tenantId: tid() });
}

/** T-DORMANT: عملاء توقّفوا عن الشراء منذ عتبة الإعدادات (يغذّي إشعار «عميل مختفٍ»). */
export type DormantCustomerRow = {
  partner_id: number;
  partner_name: string;
  last_sale_date: string;
  last_invoice_number: string | null;
  days_since: number;
};

export async function getDormantCustomers(days?: number): Promise<DormantCustomerRow[]> {
  const qs = days != null ? `?days=${days}` : "";
  return apiGetList(`${BASE}/reports/dormant-customers/${qs}`, { tenantId: tid() });
}

/**
 * T-RESERVEGUARD: «تقرير المحجوزات» — بنود الطلبيات المؤكَّدة التي ما زال حجزها
 * سارياً. نفس مصدر الحارس الذي يرفض بيع الكمية المحجوزة لزبون آخر.
 */
export type ReservedStockRow = {
  order_id: number;
  order_number: string;
  order_date: string | null;
  reserved_until: string | null;
  days_left: number | null;
  customer_id: number;
  customer_name: string;
  product_id: number;
  product_sku: string;
  product_name: string;
  quantity: string;
  unit_price: string;
  line_total: string;
  quantity_on_hand: string;
  reserved_quantity: string;
  available_quantity: string;
};

export async function getReservedStock(params?: {
  product?: number;
  customer?: number;
  /** نافذة «الحجز حتى» (ISO) — ما ينتهي داخل مدّة بعينها. */
  from?: string;
  to?: string;
}): Promise<ReservedStockRow[]> {
  const q = new URLSearchParams();
  if (params?.product != null) q.set("product", String(params.product));
  if (params?.customer != null) q.set("customer", String(params.customer));
  if (params?.from) q.set("from", params.from);
  if (params?.to) q.set("to", params.to);
  const qs = q.toString();
  return apiGetList(`${BASE}/reports/reserved-stock/${qs ? `?${qs}` : ""}`, { tenantId: tid() });
}

// -------------------------------------------------------------
// Sales Quotations (العروض والطلبيات — T4-01)
// -------------------------------------------------------------
export type SalesQuotationRow = {
  id: number;
  quotation_number: string;
  customer: number;
  customer_name?: string;
  quotation_date: string;
  valid_until?: string | null;
  status: string;
  status_display?: string;
  grand_total: string;
  notes?: string;
};

export type SalesQuotationDetail = SalesQuotationRow & {
  currency: number;
  currency_code?: string;
  exchange_rate: string;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  lines: {
    id: number;
    product: number;
    product_name?: string;
    quantity: string;
    unit_price: string;
    line_discount: string;
    tax_rate: number | null;
    line_total: string;
  }[];
};

export async function listQuotations(): Promise<SalesQuotationRow[]> {
  return apiGetList(`${BASE}/quotations/`, { tenantId: tid() });
}

export async function listQuotationsPage(
  query?: Record<string, string | number | boolean | undefined>
): Promise<PagedList<SalesQuotationRow>> {
  return apiGetPagedList(`${BASE}/quotations/`, {
    tenantId: tid(),
    query: { ...query, page: query?.page ?? 1 },
  });
}

export async function getQuotation(id: number): Promise<SalesQuotationDetail> {
  return apiGetObject(`${BASE}/quotations/${id}/`, { tenantId: tid() });
}

export async function createQuotation(
  body: Record<string, unknown>,
): Promise<SalesQuotationDetail> {
  return apiPostObject(`${BASE}/quotations/`, body, { tenantId: tid() });
}

export async function updateQuotation(
  id: number,
  body: Record<string, unknown>,
): Promise<SalesQuotationDetail> {
  return apiPatchObject(`${BASE}/quotations/${id}/`, body, { tenantId: tid() });
}

export async function deleteQuotation(id: number): Promise<void> {
  return apiDelete(`${BASE}/quotations/${id}/`, { tenantId: tid() });
}

/**
 * T-ORDERS: تحويل عرض السعر — الهدف يختاره المستخدم من حوار داخل الموقع:
 * `invoice` (فاتورة) أو `order` (طلبية تحجز الكمية).
 */
export async function convertQuotation(
  id: number,
  target: "invoice" | "order" = "invoice",
): Promise<{
  status: string;
  target: string;
  invoice?: { id: number; invoice_number: string };
  order?: SalesOrderRow;
}> {
  return apiPostObject(
    `${BASE}/quotations/${id}/convert/`,
    { target },
    { tenantId: tid() },
  );
}

/** إلغاء عرض السعر — يُبقي المستند (بديل الحذف). */
export async function cancelQuotation(
  id: number,
  reason = "",
): Promise<SalesQuotationDetail> {
  return apiPostObject(`${BASE}/quotations/${id}/cancel/`, { reason }, { tenantId: tid() });
}

// -------------------------------------------------------------
// T-ORDERS — طلبيات الزبائن (حجز كمية + عربون)
// -------------------------------------------------------------

export type SalesOrderLineRow = {
  id?: number;
  product: number;
  product_name?: string;
  quantity: string;
  unit_price: string;
  line_discount?: string;
  line_total?: string;
};

export type SalesOrderRow = {
  id: number;
  order_number: string;
  customer: number;
  customer_name?: string;
  order_date: string;
  delivery_date?: string | null;
  reserved_until?: string | null;
  status: string;
  status_display?: string;
  grand_total: string;
  deposit_amount: string;
  remaining_amount: string;
  quotation?: number | null;
  quotation_number?: string | null;
  invoice?: number | null;
  invoice_number?: string | null;
  notes?: string | null;
  cancel_reason?: string;
  lines: SalesOrderLineRow[];
};

export async function listSalesOrders(
  query?: Record<string, string | number | boolean | undefined>,
): Promise<SalesOrderRow[]> {
  return apiGetList(`${BASE}/orders/`, { tenantId: tid(), query });
}

export async function getSalesOrder(id: number): Promise<SalesOrderRow> {
  return apiGetObject(`${BASE}/orders/${id}/`, { tenantId: tid() });
}

export async function createSalesOrder(
  body: Record<string, unknown>,
): Promise<SalesOrderRow> {
  return apiPostObject(`${BASE}/orders/`, body, { tenantId: tid() });
}

export async function updateSalesOrder(
  id: number,
  body: Record<string, unknown>,
): Promise<SalesOrderRow> {
  return apiPatchObject(`${BASE}/orders/${id}/`, body, { tenantId: tid() });
}

export async function deleteSalesOrder(id: number): Promise<void> {
  return apiDelete(`${BASE}/orders/${id}/`, { tenantId: tid() });
}

export async function confirmSalesOrder(id: number): Promise<SalesOrderRow> {
  return apiPostObject(`${BASE}/orders/${id}/confirm/`, {}, { tenantId: tid() });
}

export async function cancelSalesOrder(id: number, reason = ""): Promise<SalesOrderRow> {
  return apiPostObject(`${BASE}/orders/${id}/cancel/`, { reason }, { tenantId: tid() });
}

export async function convertSalesOrderToInvoice(
  id: number,
): Promise<{ status: string; invoice: { id: number; invoice_number: string } }> {
  return apiPostObject(`${BASE}/orders/${id}/convert/`, {}, { tenantId: tid() });
}

/** عربون الطلبية — سند قبض مرحَّل «على الحساب» مربوط بها. */
export async function recordOrderDeposit(
  id: number,
  body: { amount: string | number; cash_or_bank_account: number; payment_date?: string },
): Promise<SalesOrderRow> {
  return apiPostObject(`${BASE}/orders/${id}/deposit/`, body, { tenantId: tid() });
}

// -------------------------------------------------------------
// M4-T4 — Credit / Debit notes (إشعارات مدينة/دائنة)
// -------------------------------------------------------------
export type CreditDebitNoteRow = {
  id: number;
  note_number: string;
  note_date: string;
  note_type: "credit" | "debit";
  customer: number;
  customer_name?: string;
  related_invoice: number | null;
  related_invoice_number?: string | null;
  amount: string;
  reason?: string;
  status: string;
  journal?: number | null;
  created_at?: string;
};

export async function listCreditDebitNotes(): Promise<CreditDebitNoteRow[]> {
  return apiGetList(`${BASE}/credit-debit-notes/`, { tenantId: tid() });
}

export async function getCreditDebitNote(id: number): Promise<CreditDebitNoteRow> {
  return apiGetObject(`${BASE}/credit-debit-notes/${id}/`, { tenantId: tid() });
}

export async function createCreditDebitNote(
  body: {
    note_date: string;
    note_type: "credit" | "debit";
    customer: number;
    related_invoice?: number | null;
    amount: string | number;
    reason?: string;
  },
): Promise<CreditDebitNoteRow> {
  return apiPostObject(`${BASE}/credit-debit-notes/`, body, { tenantId: tid() });
}

export async function updateCreditDebitNote(
  id: number,
  body: Partial<{
    note_date: string;
    note_type: "credit" | "debit";
    customer: number;
    related_invoice: number | null;
    amount: string | number;
    reason: string;
  }>,
): Promise<CreditDebitNoteRow> {
  return apiPatchObject(`${BASE}/credit-debit-notes/${id}/`, body, { tenantId: tid() });
}

export async function deleteCreditDebitNote(id: number): Promise<void> {
  return apiDelete(`${BASE}/credit-debit-notes/${id}/`, { tenantId: tid() });
}

export async function postCreditDebitNote(id: number): Promise<CreditDebitNoteRow> {
  return apiPostObject(
    `${BASE}/credit-debit-notes/${id}/post/`,
    {},
    { tenantId: tid() },
  );
}
