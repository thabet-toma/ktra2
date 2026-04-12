/**
 * ترحيل قيد استلام المخزون (مدين مخزون | دائن مورد) بعد حفظ الفاتورة في Firestore.
 */
import type { Invoice } from "../types/invoice";
import { accountingApi } from "./accountingApi";

const POST_RECEIPT_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "fully_paid",
  "deposit_paid",
  "partially_paid",
]);

export function invoiceQualifiesForPurchaseReceipt(invoice: {
  status: string;
  glPurchaseReceiptJournalId?: number;
}): boolean {
  if (invoice.glPurchaseReceiptJournalId != null && invoice.glPurchaseReceiptJournalId > 0) {
    return false;
  }
  return POST_RECEIPT_STATUSES.has(invoice.status);
}

/**
 * @returns معرف القيد في SQL أو null إن تُرك (حالة غير مناسبة، مورد غير رقمي، فشل الشبكة)
 */
export async function tryPostPurchaseReceiptFromInvoice(
  invoice: Pick<
    Invoice,
    | "id"
    | "supplierId"
    | "status"
    | "grandTotal"
    | "subtotal"
    | "invoiceNumber"
    | "invoiceDate"
    | "createdAt"
    | "glPurchaseReceiptJournalId"
  >
): Promise<number | null> {
  if (!invoiceQualifiesForPurchaseReceipt(invoice)) return null;

  const pid = Number(String(invoice.supplierId || "").trim());
  if (!Number.isFinite(pid) || pid <= 0) {
    console.warn(
      "[invoiceAccounting] تخطي قيد الاستلام: supplierId ليس معرف شريك SQL رقمياً",
      invoice.supplierId
    );
    return null;
  }

  const amount = Number(invoice.grandTotal ?? invoice.subtotal ?? 0);
  if (!Number.isFinite(amount) || amount <= 0) {
    console.warn("[invoiceAccounting] تخطي قيد الاستلام: المبلغ غير صالح");
    return null;
  }

  const ref = (invoice.invoiceNumber || invoice.id || "").trim();
  const dateRaw = invoice.invoiceDate || invoice.createdAt || "";
  const transaction_date = dateRaw ? String(dateRaw).slice(0, 10) : undefined;

  try {
    const r = await accountingApi.postPurchaseReceipt({
      partner_id: pid,
      amount,
      description: `استلام فاتورة ${ref || invoice.id}`,
      invoice_reference: ref || invoice.id,
      ...(transaction_date ? { transaction_date } : {}),
    });
    const jid = typeof r?.journal_id === "number" ? r.journal_id : Number(r?.journal_id);
    return Number.isFinite(jid) && jid > 0 ? jid : null;
  } catch (e) {
    console.error("[invoiceAccounting] فشل ترحيل قيد الاستلام:", e);
    return null;
  }
}
