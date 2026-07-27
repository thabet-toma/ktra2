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
  | "accepted"
  | "rejected"
  | "expired"
  | "cancelled"
  | "converted";

export interface SupplierQuotationLineDto {
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

export interface SupplierQuotationDto {
  id: number;
  scope: ProcurementScope;
  quotation_number: string;
  supplier: number;
  supplier_name?: string;
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
  converted_deal?: number | null;
  created_at?: string;
  updated_at?: string;
  lines: SupplierQuotationLineDto[];
}

export type SupplierQuotationWrite = Omit<
  SupplierQuotationDto,
  | "id"
  | "supplier_name"
  | "currency_code"
  | "subtotal"
  | "tax_amount"
  | "grand_total"
  | "converted_deal"
  | "created_at"
  | "updated_at"
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

export async function convertSupplierQuotationToImportDeal(
  id: number,
): Promise<{
  status: "converted";
  created: boolean;
  deal: { id: number; ref_number: string };
}> {
  return apiPostObject(
    `${BASE}/supplier-quotations/${id}/convert-to-import-deal/`,
    {},
    { tenantId: tenantId() },
  );
}

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
