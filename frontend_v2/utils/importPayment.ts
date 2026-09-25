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

/**
 * أساس الدفع في محرّر فاتورة الشراء («ادفع الكل» والتعبئة ولوحة الدفع).
 * المحلية: الإجمالي + الرسوم. الدولية المرحّلة: حصّة المورد التي دائنه بها الترحيل
 * (`payable_total` من الخادم — `logistics/services.py` `import_invoice_ap_credit`)،
 * لا الإجمالي المحمَّل الذي يضمّ حصص الوكيل والمخلّص والناقل — تلك تُدفع لأصحابها.
 */
export function purchasePayableTotal(input: {
  grandTotal: number;
  feesTotal: number;
  international: boolean;
  isPosted: boolean;
  serverPayableTotal?: number | null;
}): number {
  const { grandTotal, feesTotal, international, isPosted, serverPayableTotal } = input;
  if (international && isPosted && typeof serverPayableTotal === "number" && Number.isFinite(serverPayableTotal)) {
    return serverPayableTotal;
  }
  return (Number(grandTotal) || 0) + (Number(feesTotal) || 0);
}

export interface ImportPaymentRow {
  key: ImportPaymentComponentKey;
  label: string;
  cost: number;
  paid: number;
  remaining: number;
}

/**
 * طباعة الفاتورة الدولية: التكاليف الأربع بترتيبها (مورد · شحن · تخليص · محلي)، كلٌّ بتكلفته
 * ومدفوعه وباقيه من الخادم — فصفّ المورد متّسقٌ (الحصّة − المدفوع = الباقي) بدل «الإجمالي
 * المحمَّل − مدفوع المورد» الذي لا يساوي باقيه.
 */
export function importPaymentRows(ip: ImportPaymentBreakdown | null | undefined): ImportPaymentRow[] {
  if (!ip?.components) return [];
  return ORDER
    .filter((key) => ip.components[key])
    .map((key) => {
      const c = ip.components[key];
      return {
        key,
        label: IMPORT_PAYMENT_LABELS[key],
        cost: Number(c.cost) || 0,
        paid: Number(c.paid) || 0,
        remaining: Number(c.remaining) || 0,
      };
    });
}

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
