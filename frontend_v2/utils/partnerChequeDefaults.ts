export type PartnerBankAccount = {
  id: number;
  bank_name: string;
  account_number: string;
  branch_name?: string | null;
  beneficiary_name?: string | null;
  currency?: number | null;
  is_active: boolean;
  is_default: boolean;
};

export type PartnerChequeIdentity = {
  id: number;
  name: string;
  legal_name?: string | null;
};

export function selectPartnerBankAccount(
  accounts: PartnerBankAccount[],
  currencyId?: number | null,
): PartnerBankAccount | null {
  const active = accounts.filter((account) => account.is_active);
  const matching = currencyId == null
    ? active
    : active.filter((account) => account.currency === currencyId);
  return matching.find((account) => account.is_default)
    ?? (matching.length === 1 ? matching[0] : null);
}

/**
 * T-CHQ3/ط — شيك بلا موعد استحقاق ورقة لا تُدار: عليه تقوم المحفظة والآجال
 * و«تم التحصيل» عند الموعد. الخادم يرفضه، وهذا الفحص يمنع الرحلة أصلاً ويقول
 * للمستخدم أي سطر ينقصه بدل رسالة عامة.
 *
 * يُرجع نص الخطأ أو `null` إن كانت السطور سليمة.
 */
export function validateChequeLines(
  lines: { cheque_number?: string; amount?: string; due_date?: string }[],
): string | null {
  for (const [index, line] of lines.entries()) {
    const at = `الشيك #${index + 1}`;
    if (!String(line.cheque_number ?? "").trim()) return `${at}: رقم الشيك مطلوب.`;
    if (!(parseFloat(String(line.amount ?? "")) > 0)) {
      return `${at}: المبلغ مطلوب ويجب أن يكون أكبر من صفر.`;
    }
    if (!String(line.due_date ?? "").trim()) {
      return `${at}: تاريخ الاستحقاق مطلوب — عليه تقوم المحفظة والتحصيل عند الموعد.`;
    }
  }
  return null;
}

/**
 * يملأ الحقول الفارغة من الافتراضيات ولا يمسّ ما كتبه المستخدم.
 *
 * افتراضيات الشيك تصل بعد نداء بطاقة الطرف، فالسطر المُضاف قبلها كان يبقى
 * فارغاً ويُملأ يدوياً. يُرجع السطر نفسه (نفس المرجع) إن لم يتغيّر شيء.
 */
export function applyBlankDefaults<T extends Record<string, unknown>>(
  line: T, defaults: Partial<T>,
): T {
  const patch: Partial<T> = {};
  for (const key of Object.keys(defaults) as (keyof T)[]) {
    const value = defaults[key];
    if (value && !String(line[key] ?? "").trim()) patch[key] = value;
  }
  return Object.keys(patch).length ? { ...line, ...patch } : line;
}

/** حساب الشركة البنكي الذي يُسحب منه الشيك الصادر (البنك المسحوب عليه). */
export type OwnBankAccount = {
  bank_name?: string | null;
  account_number?: string | null;
  branch_name?: string | null;
};

export function buildPartnerChequeDefaults(
  partner: PartnerChequeIdentity,
  account: PartnerBankAccount | null,
  direction: "Incoming" | "Outgoing",
  /** T-CHQ3/هـ: للشيك الصادر — حسابنا نحن، فهو المسحوب عليه لا حساب المورد. */
  ownAccount: OwnBankAccount | null = null,
) {
  const payeeName = account?.beneficiary_name || partner.legal_name || partner.name;
  if (direction === "Outgoing") {
    if (!ownAccount) return { payee_name: payeeName };
    return {
      bank_name: ownAccount.bank_name || "",
      account_number: ownAccount.account_number || "",
      branch: ownAccount.branch_name || "",
      payee_name: payeeName,
    };
  }
  if (!account) return { payee_name: payeeName };
  return {
    bank_name: account.bank_name || "",
    account_number: account.account_number || "",
    branch: account.branch_name || "",
    payee_name: payeeName,
  };
}
