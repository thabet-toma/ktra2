/**
 * issue #56 — سند مصروف: منطق مشتقّ عن الرسم كي يُختبر وحده لا داخل المكوّن —
 * نفس نهج `voucherEntryPreview.ts` لسندَي القبض والصرف. الفرق الجوهري عن ذينك
 * السندين أن المستفيد هنا اختياريٌّ تماماً (شريكٌ أو اسمٌ حرّ أو لا شيء)، فلا
 * سطر ذممٍ إلزامي في المعاينة — الجانب الدائن يتبع مصدر الدفع وحده.
 */
import { CHEQUES_PAYABLE_LABEL, type VoucherEntryLine } from "./voucherEntryPreview.ts";

export type ExpensePaymentMethod = "cash" | "cheque" | "on_account";

export const EXPENSE_PAYMENT_METHODS: { value: ExpensePaymentMethod; label: string }[] = [
  { value: "cash", label: "صندوق / بنك" },
  { value: "cheque", label: "شيك" },
  { value: "on_account", label: "على الحساب" },
];

export const TRADE_PAYABLES_LABEL = "الدائنون (2101)";
export const VAT_INPUT_LABEL = "ضريبة مدخلات (1105)";

/**
 * صندوق/بنك وحدها تحتاج حقل حساب صريح — الشيك يحلّه الخادم على «شيكات برسم
 * الدفع» (2111) و«على الحساب» يحلّه على 2101 أو حساب المستفيد، بلا اختيار
 * يدوي لحساب في الحالتين.
 */
export function expenseVoucherRequiresCashAccount(method: ExpensePaymentMethod): boolean {
  return method === "cash";
}

/**
 * سطر «القيد» تحت نموذج سند المصروف — نفس شكل `buildVoucherEntryPreview` لكن
 * بجانب دائن واحد يتبع مصدر الدفع، ومدينَين محتملين (المصروف + ضريبة المدخلات
 * الاختيارية). الضريبة تُقصّ إلى [0, amount] فلا يخرج سطر بمبلغ سالب أو أكبر
 * من الإجمالي.
 */
export function buildExpenseVoucherEntryPreview(input: {
  expenseAccountLabel: string;
  amount: number;
  taxAmount?: number;
  paymentMethod: ExpensePaymentMethod;
  /** تسمية الصندوق/البنك المختار — لصندوق/بنك فقط. */
  cashAccountLabel?: string | null;
  /** اسم المستفيد (شريك أو اسم حر) — لـ«على الحساب» فقط، وإلا يُستعمل «الدائنون». */
  beneficiaryLabel?: string | null;
}): VoucherEntryLine[] {
  const amount = input.amount > 0 ? input.amount : 0;
  if (amount <= 0) return [];
  const tax = Math.min(Math.max(input.taxAmount ?? 0, 0), amount);
  const net = amount - tax;

  const lines: VoucherEntryLine[] = [];
  if (net > 0) {
    lines.push({ side: "Dr", label: input.expenseAccountLabel || "حساب المصروف", amount: net });
  }
  if (tax > 0) {
    lines.push({ side: "Dr", label: VAT_INPUT_LABEL, amount: tax });
  }

  const creditLabel =
    input.paymentMethod === "cheque"
      ? CHEQUES_PAYABLE_LABEL
      : input.paymentMethod === "on_account"
        ? (input.beneficiaryLabel || TRADE_PAYABLES_LABEL)
        : (input.cashAccountLabel || "الصندوق / البنك");

  lines.push({ side: "Cr", label: creditLabel, amount });
  return lines;
}
