export interface AccountingLinkedPartner {
  id: number;
  trade_name: string;
  legal_name: string | null;
  /** T-COAMENU: يقود إجراءات كبسة اليمين (عميل ⇒ بيع، مورد ⇒ شراء). */
  partner_type?: string;
}

export interface AccountingAccount {
  id: number;
  code: string | null;
  name: string | null;
  parent: number | null;
  account_type: string | null;
  is_active: boolean;
  /** حساب مرتبط بمورد: الاسم التجاري (المستعار) للعرض في الشجرة */
  linked_partner?: AccountingLinkedPartner | null;
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
  currency?: number | null;
  exchange_rate?: string | number;
  currency_code?: string | null;
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
  account_number?: string | null;
  bank_branch?: string | null;
  /* T-BANKS: الربط بسجل البنوك — النصوص أعلاه لقطة للشيكات القديمة. */
  bank?: number | null;
  bank_branch_ref?: number | null;
  deposit_bank_account?: number | null;
  bank_display?: string | null;
  bank_branch_display?: string | null;
  deposit_bank_account_name?: string | null;
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

/** T-CHQ2: سطر حركة في مسار الشيك. */
export interface ChequeMovementDto {
  id: number;
  cheque: number;
  movement_type: string;
  movement_type_display: string;
  notes?: string | null;
  created_at: string;
  created_by_name?: string | null;
}

/** T-CHQ2: تجميعة محفظة الشيكات لجانب واحد (وارد/صادر). */
export interface ChequeWalletSide {
  open_total: string;
  open_count: number;
  buckets: Array<{ status: string; count: number; amount: string }>;
  due_buckets: Array<{ key: string; label: string; count: number; amount: string }>;
}

export interface ChequeWalletDto {
  as_of: string;
  incoming: ChequeWalletSide;
  outgoing: ChequeWalletSide;
  net_open: string;
}

export interface TrialBalanceRow {
  id: number;
  code: string | null;
  name: string | null;
  account_type?: string | null;
  total_debit: number;
  total_credit: number;
  balance: number;
  opening_debit?: number;
  opening_credit?: number;
  opening_balance?: number;
  period_debit?: number;
  period_credit?: number;
  closing_debit?: number;
  closing_credit?: number;
  closing_balance?: number;
}

export interface TrialBalanceResponse {
  start_date: string;
  end_date: string;
  rows: TrialBalanceRow[];
  totals: {
    period_debit: number;
    period_credit: number;
    closing_debit: number;
    closing_credit: number;
    balanced: boolean;
    period_difference: number;
    closing_difference: number;
  };
}

export interface VatReportResponse {
  start_date: string;
  end_date: string;
  input: {
    accounts: Array<{ id: number; code: string; name: string; type: string }>;
    total_debit: number;
    total_credit: number;
    balance: number;
  };
  output: {
    accounts: Array<{ id: number; code: string; name: string; type: string }>;
    total_debit: number;
    total_credit: number;
    balance: number;
    balance_payable: number;
  };
  net_payable: number;
  input_lines: Array<VatReportLine>;
  output_lines: Array<VatReportLine>;
}

export interface VatReportLine {
  date: string | null;
  journal_id: number;
  reference_type: string | null;
  reference_id: number | null;
  account_code: string | null;
  description: string;
  debit: number;
  credit: number;
  partner: string | null;
}

export interface LandedCostShipment {
  shipment_id: number;
  shipment_number: string;
  status: string;
  arrival_date: string | null;
  shipping_agent: string | null;
  shipping_type: string | null;
  total_merchandise: number;
  total_shipping_cost_usd: number;
  allocated_shipping_total_usd: number;
  clearance_total: number;
  capitalized_fees_total: number;
  expensed_fees_total: number;
  grand_landed_cost_approx: number;
  deals: Array<{
    deal_id: number;
    ref_number: string | null;
    partner_name: string | null;
    currency: string | null;
    merchandise_total: number;
    allocated_shipping_cost_usd: number;
    extra_costs_usd: number;
    items_count: number;
    purchase_invoice: null | {
      id: number;
      invoice_number: string | null;
      currency: string | null;
      exchange_rate: number;
      is_posted: boolean;
      capitalized_fees_total: number;
      expensed_fees_total: number;
      items_count: number;
      fees_count: number;
      items: Array<{
        id: number;
        product_id: number | null;
        name: string;
        quantity: number;
        unit_price: number;
        total_price: number;
        landed_unit_price_ils: number | null;
        landed_line_total_ils: number | null;
      }>;
      fees: Array<{
        id: number;
        description: string;
        amount: number;
        account_code: string | null;
        account_name: string | null;
        capitalize_to_inventory: boolean;
      }>;
    };
  }>;
  clearance: null | {
    id: number;
    declaration_number: string | null;
    clearance_date: string | null;
    status: string;
    cost_lines: Array<{ label: string; amount: number }>;
    cost_lines_total: number;
    posted_payments_total: number;
    broker_name: string | null;
  };
}

export interface LandedCostReport {
  shipments: LandedCostShipment[];
  count: number;
  summary_only: boolean;
}

export interface GeneralLedgerResponse {
  account_name: string;
  account_code: string | null;
  opening_balance: number;
  closing_balance: number;
  /** P1-3: الخادم يقصّ الكشف عند max_rows — القصّ معلَن لا صامت. */
  total_count?: number;
  truncated?: boolean;
  max_rows?: number;
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

export interface ExchangeRateDto {
  id: number;
  from_currency: number;
  to_currency: number;
  from_currency_code?: string;
  to_currency_code?: string;
  rate: string | number;
  effective_date: string;
}

export interface FiscalPeriodDto {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  status: "Open" | "Closed";
  is_closed: boolean;
}

export interface TaxRateDto {
  id: number;
  name: string;
  code: string;
  rate: string | number;
  tax_account: number;
  tax_account_name?: string;
  is_active: boolean;
}

export interface CurrencyDto {
  CurrencyID: number;
  Code: string;
  Name: string | null;
  Symbol: string | null;
  IsBaseCurrency: boolean;
}

/* ── T-BANKS: البنوك وحساباتها والمطابقة البنكية ── */

export interface BankBranchDto {
  id: number;
  bank: number;
  bank_name?: string;
  name: string;
  branch_code?: string | null;
  address?: string | null;
  phone?: string | null;
  is_active: boolean;
}

export interface BankDto {
  id: number;
  name: string;
  code?: string | null;
  swift_code?: string | null;
  country?: string | null;
  notes?: string | null;
  is_active: boolean;
  branches: BankBranchDto[];
  accounts_count: number;
}

export interface BankAccountDto {
  id: number;
  bank: number;
  bank_name?: string;
  branch: number | null;
  branch_name?: string | null;
  name: string;
  account_number?: string | null;
  iban?: string | null;
  currency: number;
  currency_code?: string;
  account: number;
  account_code?: string;
  is_default: boolean;
  is_active: boolean;
  notes?: string | null;
  balance?: string;
}

export interface BankStatementRowDto {
  journal_line_id: number;
  journal_id: number;
  date: string;
  description: string;
  partner: string | null;
  debit: string | number;
  credit: string | number;
  balance: string | number;
  is_cleared: boolean;
  reconciliation_id: number | null;
}

export interface BankStatementDto {
  bank_account: BankAccountDto;
  opening_balance: string | number;
  book_balance: string | number;
  cleared_balance: string | number;
  rows: BankStatementRowDto[];
}

export interface BankReconciliationDto {
  id: number;
  bank_account: number;
  bank_account_name?: string;
  currency_code?: string;
  statement_date: string;
  statement_balance: string | number;
  status: "Open" | "Closed";
  notes?: string | null;
  created_at?: string;
  closed_at?: string | null;
}

export interface BankReconciliationSummaryDto extends BankReconciliationDto {
  book_balance: string | number;
  cleared_balance: string | number;
  difference: string | number;
  uncleared_count: number;
  rows: BankStatementRowDto[];
}
