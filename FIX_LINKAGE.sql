-- ========================================
-- FIX SCRIPT: Ensure Partner-Account Linkage
-- ========================================

USE global_erp_pro;

-- 1. Add LinkedAccountID column if missing
ALTER TABLE partners 
ADD COLUMN IF NOT EXISTS LinkedAccountID INT NULL;

-- 2. Add GroupID column if missing
ALTER TABLE partners 
ADD COLUMN IF NOT EXISTS GroupID INT NULL;

-- 3. Add is_deleted column if missing
ALTER TABLE partners 
ADD COLUMN IF NOT EXISTS is_deleted TINYINT(1) DEFAULT 0;

-- 4. Create Foreign Key for LinkedAccountID
ALTER TABLE partners 
DROP FOREIGN KEY IF EXISTS fk_partner_linked_account;

ALTER TABLE partners 
ADD CONSTRAINT fk_partner_linked_account 
FOREIGN KEY (LinkedAccountID) REFERENCES chartofaccounts(AccountID) 
ON DELETE SET NULL;

-- 5. Create Foreign Key for GroupID
ALTER TABLE partners 
DROP FOREIGN KEY IF EXISTS fk_partner_group;

ALTER TABLE partners 
ADD CONSTRAINT fk_partner_group 
FOREIGN KEY (GroupID) REFERENCES partner_groups(GroupID) 
ON DELETE SET NULL;

-- 6. Verify the changes
SHOW CREATE TABLE partners;

-- 7. Check Partner Groups exist
SELECT * FROM partner_groups;
