-- Adding new columns to logistics_payments for accounting integration
ALTER TABLE logistics_payments
ADD COLUMN IsPosted tinyint(1) NOT NULL DEFAULT 0,
ADD COLUMN JournalID int DEFAULT NULL,
ADD COLUMN BankAccountID int DEFAULT NULL;

-- Adding foreign key constraints
ALTER TABLE logistics_payments
ADD CONSTRAINT fk_logistics_payments_journal 
FOREIGN KEY (JournalID) REFERENCES journal_headers(JournalID) ON DELETE SET NULL,
ADD CONSTRAINT fk_logistics_payments_bank 
FOREIGN KEY (BankAccountID) REFERENCES chartofaccounts(AccountID) ON DELETE SET NULL;
