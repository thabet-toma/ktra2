-- ========================================
-- VERIFICATION SCRIPT: Partner-Account Linkage
-- ========================================

USE global_erp_pro;

-- 1. Check if tables are linked (Foreign Keys)
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM
    INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE
    TABLE_SCHEMA = 'global_erp_pro'
    AND TABLE_NAME = 'partners'
    AND REFERENCED_TABLE_NAME IS NOT NULL;

-- 2. Check current Partner Groups
SELECT * FROM partner_groups;

-- 3. Check if LinkedAccountID and GroupID columns exist in partners table
DESCRIBE partners;

-- 4. Test: Create a new supplier and verify account creation
-- (This will be done via Django Signals, but we can check the structure)

-- 5. Verify Chart of Accounts structure
SELECT 
    AccountID,
    Code,
    Name,
    Type,
    ParentID,
    (SELECT Code FROM chartofaccounts p WHERE p.AccountID = c.ParentID) as ParentCode
FROM chartofaccounts c
ORDER BY Code;
