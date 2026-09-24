/**
 * 3ب: تسوية الفاتورة الدولية — تكاليفها الأربع مقابل دفعاتها الأربع.
 * الخادم يحسب (`logistics/domain/import_settlement.py`)، وهنا العرض وحده.
 */
import { formatMoney } from "./formatNumber.ts";

export type ImportPaymentComponentKey = "supplier" | "freight" | "clearance" | "local";

export interface ImportPaymentComponent {
  cost: string;
  paid: string;
  remaining: string;
}

export interface ImportPaymentBreakdown {
  payment_status: "paid" | "partially_paid" | "unpaid";
  payment_status_display: string;
  payable_total: string;
  amount_paid: string;
  remaining_balance: string;
  components: Record<ImportPaymentComponentKey, ImportPaymentComponent>;
}

export const IMPORT_PAYMENT_LABELS: Record<ImportPaymentComponentKey, string> = {
  supplier: "مورد",
  freight: "شحن",
  clearance: "تخليص",
  local: "محلي",
};

const ORDER: ImportPaymentComponentKey[] = ["supplier", "freight", "clearance", "local"];

/** «مورد X · شحن X · تخليص X · محلي X» — المدفوع لكل دائن من تكلفته. */
export function importPaymentTooltip(ip: ImportPaymentBreakdown | null | undefined): string {
  if (!ip?.components) return "";
  return ORDER
    .filter((key) => ip.components[key])
    .map((key) => {
      const c = ip.components[key];
      return `${IMPORT_PAYMENT_LABELS[key]} ${formatMoney(c.paid)} / ${formatMoney(c.cost)}`;
    })
    .join(" · ");
}
