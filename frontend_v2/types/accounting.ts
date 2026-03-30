export interface AccountingAccount {
  id: number;
  code: string | null;
  name: string | null;
  parent: number | null;
  account_type: string | null;
  is_active: boolean;
}

export interface JournalLineDto {
  id?: number;
  account: number;
  debit: string | number;
  credit: string | number;
  partner?: number | null;
  cost_center?: number | null;
  project_id?: number | null;
}

export interface JournalHeaderDto {
  id?: number;
  transaction_date: string | null;
  reference_type?: string | null;
  reference_id?: number | null;
  description?: string | null;
  is_posted?: boolean;
  lines: JournalLineDto[];
}

export interface CostCenterDto {
  id: number;
  name: string;
  code?: string | null;
}

export interface AccountingPartner {
  id: number;
  name: string;
  legal_name?: string | null;
}

export interface ChequeDto {
  id: number;
  cheque_number: string;
  bank_name?: string | null;
  amount: string;
  due_date?: string | null;
  issue_date?: string | null;
  payee_name?: string | null;
  status: string;
  direction: string;
  partner?: number | null;
  currency: number;
  notes?: string | null;
}

export interface TrialBalanceRow {
  id: number;
  code: string | null;
  name: string | null;
  total_debit: number;
  total_credit: number;
  balance: number;
}

export interface GeneralLedgerResponse {
  account_name: string;
  account_code: string | null;
  opening_balance: number;
  closing_balance: number;
  transactions: Array<{
    id: number;
    date: string;
    journal_id: number;
    description: string;
    ref_type?: string | null;
    ref_id?: number | null;
    debit: number;
    credit: number;
    balance: number;
  }>;
}
