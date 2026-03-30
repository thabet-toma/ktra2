-- ========================================
-- FIX: Rename LedgerAccountID to LinkedAccountID
-- ========================================

USE global_erp_pro;

-- 1. Drop the old foreign key
ALTER TABLE partners DROP FOREIGN KEY fk_partner_ledger_account;

-- 2. Rename the column
ALTER TABLE partners CHANGE COLUMN LedgerAccountID LinkedAccountID INT NULL;

-- 3. Re-create the foreign key with new name
ALTER TABLE partners 
ADD CONSTRAINT fk_partner_linked_account 
FOREIGN KEY (LinkedAccountID) REFERENCES chartofaccounts(AccountID);

-- 4. Verify
DESCRIBE partners;
