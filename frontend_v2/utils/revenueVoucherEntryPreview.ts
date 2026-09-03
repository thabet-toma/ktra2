/**
 * سند إيراد — مرآةُ `expenseVoucherEntryPreview.ts` بعكس الاتجاه (issue #80
 * خادمياً). المنطق مشتقٌّ عن الرسم كي يُختبر وحده لا داخل المكوّن.
 *
 * الدافع اختياريٌّ تماماً كالمستفيد هناك (شريكٌ أو اسمٌ حرّ أو لا شيء)، فلا
 * سطر ذممٍ إلزامي — الجانب **المدين** يتبع مصدر القبض وحده، والدائن هو حساب
 * الإيراد وضريبةُ المخرجات إن وُجدت.
 */
import { CHEQUES_UNDER_COLLECTION_LABEL, type VoucherEntryLine } from "./voucherEntryPreview.ts";

export type RevenuePaymentMethod = "cash" | "cheque" | "on_account";

export const REVENUE_PAYMENT_METHODS: { value: RevenuePaymentMethod; label: string }[] = [
  { value: "cash", label: "صندوق / بنك" },
  { value: "cheque", label: "شيك" },
  { value: "on_account", label: "على الحساب" },
];

export const TRADE_RECEIVABLES_LABEL = "المدينون (1103)";
export const VAT_OUTPUT_LABEL = "ضريبة مخرجات (2104)";

/**
 * صندوق/بنك وحدها تحتاج حقل حساب صريح — الشيك يحلّه الخادم على «شيكات برسم
 * التحصيل» (1107) و«على الحساب» على 1103 أو حساب الدافع.
 */
export function revenueVoucherRequiresCashAccount(method: RevenuePaymentMethod): boolean {
  return method === "cash";
}

export function buildRevenueVoucherEntryPreview(input: {
  revenueAccountLabel: string;
  amount: number;
  taxAmount?: number;
  paymentMethod: RevenuePaymentMethod;
  /** تسمية الصندوق/البنك المختار — لصندوق/بنك فقط. */
  cashAccountLabel?: string | null;
  /** اسم الدافع (شريك أو اسم حر) — لـ«على الحساب» فقط، وإلا «المدينون». */
  payerLabel?: string | null;
}): VoucherEntryLine[] {
  const amount = input.amount > 0 ? input.amount : 0;
  if (amount <= 0) return [];
  const tax = Math.min(Math.max(input.taxAmount ?? 0, 0), amount);
  const net = amount - tax;

  const debitLabel =
    input.paymentMethod === "cheque"
      ? CHEQUES_UNDER_COLLECTION_LABEL
      : input.paymentMethod === "on_account"
        ? (input.payerLabel || TRADE_RECEIVABLES_LABEL)
        : (input.cashAccountLabel || "الصندوق / البنك");

  const lines: VoucherEntryLine[] = [{ side: "Dr", label: debitLabel, amount }];
  if (net > 0) {
    lines.push({ side: "Cr", label: input.revenueAccountLabel || "حساب الإيراد", amount: net });
  }
  if (tax > 0) {
    lines.push({ side: "Cr", label: VAT_OUTPUT_LABEL, amount: tax });
  }
  return lines;
}
