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

export function buildPartnerChequeDefaults(
  partner: PartnerChequeIdentity,
  account: PartnerBankAccount | null,
  direction: "Incoming" | "Outgoing",
) {
  const payeeName = account?.beneficiary_name || partner.legal_name || partner.name;
  if (direction === "Outgoing") return { payee_name: payeeName };
  if (!account) return { payee_name: payeeName };
  return {
    bank_name: account.bank_name || "",
    account_number: account.account_number || "",
    branch: account.branch_name || "",
    payee_name: payeeName,
  };
}
