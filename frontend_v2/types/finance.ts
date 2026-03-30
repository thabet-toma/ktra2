
export type Currency = 'USD' | 'ILS' | 'JOD';

export interface CashBox {
    id: string;
    name: string;
    currency: Currency;
    currentBalance: number;
    createdAt: string;
    updatedAt: string;
    createdBy: string;
}

export type TransactionType = 'deposit' | 'withdrawal' | 'adjustment';

export interface CashBoxTransaction {
    id: string;
    cashBoxId: string;
    type: TransactionType;
    amount: number;
    currency: Currency;
    description: string;
    reference?: string;
    date: string;
    createdBy: string;
    createdAt: string;
    balanceAfter: number;
}
