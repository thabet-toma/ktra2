/**
 * T-CHQ3/و — سطر «القيد» تحت نموذج السند.
 *
 * كان يقول «Dr الصندوق / Cr ذمم العميل» دائماً، ولو كان السند كلّه شيكات —
 * وهو خطأ محاسبي يقرأه المستخدم قبل الحفظ: الشيك لا يدخل الصندوق حتى يُحصَّل،
 * بل يُقيَّد على «شيكات برسم التحصيل» (والصادر على «شيكات برسم الدفع»)، ثم
 * ينتقل إلى الصندوق/البنك عند التحصيل.
 *
 * الخادم يقسم الجانب المدين هكذا أصلاً في `post_customer_payment`؛ هذه الدالة
 * تعرض القسمة نفسها. وحدة نقيّة (بلا تنسيق أرقام) كي تُختبر بـ`node --test`
 * ويبقى عرض المبالغ عبر `formatNumber` في المكوّن (قاعدة G1).
 */

export const CHEQUES_UNDER_COLLECTION_LABEL = "شيكات برسم التحصيل";
export const CHEQUES_PAYABLE_LABEL = "شيكات برسم الدفع";

export type VoucherEntryLine = {
  side: "Dr" | "Cr";
  label: string;
  amount: number;
};

export function buildVoucherEntryPreview(input: {
  cashAmount: number;
  chequesAmount: number;
  cashAccountLabel: string;
  partnerLabel: string;
  direction: "Incoming" | "Outgoing";
}): VoucherEntryLine[] {
  const { cashAmount, chequesAmount, cashAccountLabel, partnerLabel, direction } = input;
  const cash = cashAmount > 0 ? cashAmount : 0;
  const cheques = chequesAmount > 0 ? chequesAmount : 0;
  const total = cash + cheques;
  if (total <= 0) return [];

  const incoming = direction === "Incoming";
  const partnerLine: VoucherEntryLine = {
    side: incoming ? "Cr" : "Dr",
    label: `ذمم ${incoming ? "العميل" : "المورد"} ${partnerLabel}`,
    amount: total,
  };
  const moneyLines: VoucherEntryLine[] = [];
  if (cash > 0) {
    moneyLines.push({
      side: incoming ? "Dr" : "Cr", label: cashAccountLabel, amount: cash,
    });
  }
  if (cheques > 0) {
    moneyLines.push({
      side: incoming ? "Dr" : "Cr",
      label: incoming ? CHEQUES_UNDER_COLLECTION_LABEL : CHEQUES_PAYABLE_LABEL,
      amount: cheques,
    });
  }
  return incoming ? [...moneyLines, partnerLine] : [partnerLine, ...moneyLines];
}
