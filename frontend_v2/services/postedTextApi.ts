/**
 * نصوص المستند المرحَّل (`core/posted_text.py`): الملاحظة — ورقم فاتورة المورد لفاتورة
 * الشراء — تُعدَّل بعد الترحيل وحدها. كلُّ مستندٍ بمسار تعديله القائم (PATCH)، ودفعات
 * التخليص والإرسالية بمسارٍ تحت مستحقّها. الخادم يرفض أيّ حقلٍ خارج قائمة نموذجه.
 */
import { apiPatchObject } from "./restApi";
import { resolveTenantId } from "@/utils/tenantContext";

export type PostedTextDoc =
  | { kind: "supplier_payment"; id: number }
  | { kind: "customer_payment"; id: number }
  | { kind: "credit_debit_note"; id: number }
  | { kind: "sales_invoice"; id: number }
  | { kind: "purchase_invoice"; id: number }
  | { kind: "clearance_payment"; id: number; clearanceId: number }
  | { kind: "local_shipment_payment"; id: number; localShipmentId: number }
  | { kind: "logistics_payment"; id: number };

function postedTextPath(doc: PostedTextDoc): string {
  switch (doc.kind) {
    case "supplier_payment": return `logistics/supplier-payments/${doc.id}/`;
    case "customer_payment": return `sales/payments/${doc.id}/`;
    case "credit_debit_note": return `sales/credit-debit-notes/${doc.id}/`;
    case "sales_invoice": return `sales/invoices/${doc.id}/`;
    case "purchase_invoice": return `logistics/purchase-invoices/${doc.id}/`;
    case "clearance_payment": return `logistics/clearances/${doc.clearanceId}/payments/${doc.id}/`;
    case "local_shipment_payment": return `logistics/local-shipments/${doc.localShipmentId}/payments/${doc.id}/`;
    case "logistics_payment": return `logistics/payments/${doc.id}/`;
  }
}

/** يحفظ الحقول النصّية وحدها — `values` مفاتيح القائمة المسموحة لنوع المستند. */
export async function savePostedText(doc: PostedTextDoc, values: Record<string, string>): Promise<unknown> {
  return apiPatchObject(postedTextPath(doc), values, { tenantId: resolveTenantId() });
}
