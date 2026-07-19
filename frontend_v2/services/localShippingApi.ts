import {
  apiGetList,
  apiGetObject,
  apiPostObject,
  apiPatchObject,
  apiDelete,
} from "./restApi";
import { resolveTenantId } from "@/utils/tenantContext";

const tid = () => resolveTenantId();

export type LocalShipmentStatus =
  | "pending"
  | "in_transit"
  | "delivered"
  | "cancelled";

export type LocalShipmentPaymentType = "credit" | "cash";

export type LocalShipmentPaymentRow = {
  id: number;
  local_shipment: number;
  amount: string;
  currency: number;
  currency_code?: string;
  exchange_rate: string;
  payment_date: string;
  cash_box_external_id: string;
  notes?: string;
  is_posted: boolean;
  journal?: number | null;
  journal_id_display?: number | null;
};

export type LocalShipmentRow = {
  id: number;
  shipment_number: string;
  clearance: number | null;
  clearance_number?: string | null;
  shipment: number | null;
  shipment_number_source?: string | null;
  carrier: number;
  carrier_name?: string;
  driver_name?: string | null;
  vehicle_number?: string | null;
  origin?: string | null;
  destination?: string | null;
  pickup_date?: string | null;
  delivery_date?: string | null;
  amount: string;
  currency: number;
  currency_code?: string | null;
  exchange_rate: string;
  payment_type: LocalShipmentPaymentType;
  expense_account: number | null;
  expense_account_code?: string | null;
  expense_account_name?: string | null;
  cash_or_bank_account: number | null;
  capitalize_to_inventory: boolean;
  status: LocalShipmentStatus;
  notes?: string | null;
  is_posted: boolean;
  journal?: number | null;
  purchase_invoice: number | null;
  purchase_invoice_number?: string | null;
  amount_paid?: string;
  remaining_balance?: string;
  payment_status?: "paid" | "partially_paid" | "unpaid";
  payments?: LocalShipmentPaymentRow[];
  created_at?: string;
  updated_at?: string;
};

export type LocalShipmentCreate = {
  clearance?: number | null;
  shipment?: number | null;
  carrier: number;
  driver_name?: string;
  vehicle_number?: string;
  origin?: string;
  destination?: string;
  pickup_date?: string | null;
  delivery_date?: string | null;
  amount: string | number;
  currency?: number;
  exchange_rate?: string | number;
  payment_type: LocalShipmentPaymentType;
  expense_account?: number | null;
  cash_or_bank_account?: number | null;
  capitalize_to_inventory?: boolean;
  status?: LocalShipmentStatus;
  notes?: string;
};

export async function listLocalShipments(
  query?: Record<string, string | number | boolean | undefined>,
): Promise<LocalShipmentRow[]> {
  return apiGetList<LocalShipmentRow>("logistics/local-shipments/", {
    tenantId: tid(),
    query,
  });
}

export async function getLocalShipment(id: number): Promise<LocalShipmentRow> {
  return apiGetObject<LocalShipmentRow>(`logistics/local-shipments/${id}/`, {
    tenantId: tid(),
  });
}

export async function createLocalShipment(
  body: LocalShipmentCreate,
): Promise<LocalShipmentRow> {
  return apiPostObject<LocalShipmentRow>(
    "logistics/local-shipments/",
    body as unknown as Record<string, unknown>,
    { tenantId: tid() },
  );
}

export async function updateLocalShipment(
  id: number,
  body: Partial<LocalShipmentCreate>,
): Promise<LocalShipmentRow> {
  return apiPatchObject<LocalShipmentRow>(
    `logistics/local-shipments/${id}/`,
    body as unknown as Record<string, unknown>,
    { tenantId: tid() },
  );
}

export async function deleteLocalShipment(id: number): Promise<void> {
  return apiDelete(`logistics/local-shipments/${id}/`, { tenantId: tid() });
}

export async function postLocalShipment(
  id: number,
): Promise<LocalShipmentRow> {
  return apiPostObject<LocalShipmentRow>(
    `logistics/local-shipments/${id}/post-to-accounting/`,
    {},
    { tenantId: tid() },
  );
}

export async function payLocalShipmentFromCashBox(
  id: number,
  payload: {
    amount: number;
    cash_box_external_id: string;
    payment_date?: string;
    notes?: string;
  },
): Promise<{ status: string; journal_id: number; payment: LocalShipmentPaymentRow }> {
  return apiPostObject(
    `logistics/local-shipments/${id}/pay_from_cashbox/`,
    payload,
    { tenantId: tid() },
  );
}

export async function unpostLocalShipment(
  id: number,
): Promise<{ message: string }> {
  return apiPostObject<{ message: string }>(
    `logistics/local-shipments/${id}/unpost/`,
    {},
    { tenantId: tid() },
  );
}
