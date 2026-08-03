/**
 * إرساليات الشراء (Goods Receipt Notes) — مستند استلام البضاعة المرتبط بفاتورة.
 *
 * الإنشاء هو فعل الاستلام نفسه على الخادم (نفس خدمة زر «استلام» داخل الفاتورة)،
 * فلا يوجد مساران لإدخال البضاعة للمخزن.
 */
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const BASE = "logistics/goods-receipts/";
const tid = () => resolveTenantId();

export interface GoodsReceiptLineDto {
  id: number;
  item: number | null;
  item_name: string | null;
  product: number;
  product_name: string;
  ordered_quantity: string;
  received_total: string;
  remaining_quantity: string;
  quantity: string;
  unit_price: string;
  warehouse: number | null;
  warehouse_name?: string | null;
}

export interface GoodsReceiptRow {
  id: number;
  receipt_number: string;
  receipt_date: string;
  invoice: number | null;
  invoice_number: string | null;
  partner: number | null;
  partner_name: string;
  supplier_ref: string;
  is_standalone: boolean;
  doc_label: string;
  auto_created: boolean;
  journal: number | null;
  notes: string;
  lines_count: number;
  total_quantity: string;
  total_remaining: string;
  created_at: string;
}

/** سطر باقٍ غير مستلم عبر كل الفواتير — تقرير الطباعة/PDF. */
export interface OutstandingReceiptRow {
  invoice: number;
  invoice_number: string;
  invoice_date: string | null;
  partner_name: string;
  product: number;
  product_name: string;
  quantity: string;
  received_quantity: string;
  remaining_quantity: string;
}

export interface GoodsReceiptDto extends GoodsReceiptRow {
  lines: GoodsReceiptLineDto[];
}

/** بند فاتورة قابل للاستلام — يغذّي منتقي البنود في محرّر الإرسالية. */
export interface ReceivableLineRow {
  item_id: number;
  product: number;
  product_name: string;
  name: string;
  unit_price: string;
  quantity: string;
  received_quantity: string;
  remaining_quantity: string;
}

export interface ReceivableLinesResponse {
  invoice_number: string;
  partner_name: string;
  invoice_date: string | null;
  receipt_status: "not_received" | "partially_received" | "received";
  receipt_status_display?: string;
  is_local: boolean;
  is_posted: boolean;
  lines: ReceivableLineRow[];
}

export async function listGoodsReceipts(
  query?: Record<string, string | number | undefined>
): Promise<GoodsReceiptRow[]> {
  return apiGetList(BASE, { tenantId: tid(), query });
}

export async function getGoodsReceipt(id: number): Promise<GoodsReceiptDto> {
  return apiGetObject(`${BASE}${id}/`, { tenantId: tid() });
}

/** بنود الحفظ: `item_id` للمرتبط بفاتورة، و`product_id`+`unit_price` للسند المستقل. */
export type GoodsReceiptSaveLine = {
  item_id?: number;
  product_id?: number;
  quantity: number;
  unit_price?: number;
  warehouse_id: number;
};

export type GoodsReceiptSaveBody = {
  invoice?: number | null;
  partner?: number | null;
  supplier_ref?: string;
  receipt_date?: string;
  notes?: string;
  lines: GoodsReceiptSaveLine[];
};

export async function createGoodsReceipt(
  body: GoodsReceiptSaveBody
): Promise<GoodsReceiptDto> {
  return apiPostObject(BASE, body, { tenantId: tid() });
}

/** التعديل يعكس أثر الإرسالية القديم ويعيد تطبيق البنود الجديدة (على الخادم). */
export async function updateGoodsReceipt(
  id: number,
  body: GoodsReceiptSaveBody
): Promise<GoodsReceiptDto> {
  return apiPatchObject(`${BASE}${id}/`, body, { tenantId: tid() });
}

export async function deleteGoodsReceipt(id: number): Promise<void> {
  return apiDelete(`${BASE}${id}/`, { tenantId: tid() });
}

export async function getOutstandingReceiptLines(): Promise<OutstandingReceiptRow[]> {
  const data = await apiGetObject<{ rows?: OutstandingReceiptRow[] }>(
    `${BASE}outstanding/`,
    { tenantId: tid() }
  );
  return data?.rows || [];
}

export async function getReceivableLines(
  invoiceId: number
): Promise<ReceivableLinesResponse> {
  return apiGetObject(
    `logistics/purchase-invoices/${invoiceId}/receivable-lines/`,
    { tenantId: tid() }
  );
}
