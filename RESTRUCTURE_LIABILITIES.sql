-- =========================================================
-- RESTRUCTURE_LIABILITIES.sql
-- Restructure Logistics Accounts under Current Liabilities (21)
-- =========================================================

USE global_erp_pro;

-- 1. Get the ID of "Current Liabilities" (Code 21)
SET @liabilities_parent_id = (SELECT AccountID FROM chartofaccounts WHERE Code = '21' AND TenantID = 1 LIMIT 1);

-- 2. Create New Liability Accounts (if they don't exist)
-- 2101: Suppliers (Existing)
-- 2102: Freight Forwarders (وكلاء شحن)
-- 2103: Customs Brokers (مخلصين جمركيين)
-- 2104: Local Carriers (ناقل محلي)

INSERT INTO chartofaccounts (TenantID, Code, Name, ParentID, Type, IsActive)
SELECT 1, '2102', 'وكلاء شحن (Freight Forwarders)', @liabilities_parent_id, 'Liability', 1
WHERE NOT EXISTS (SELECT 1 FROM chartofaccounts WHERE Code = '2102' AND TenantID = 1);

INSERT INTO chartofaccounts (TenantID, Code, Name, ParentID, Type, IsActive)
SELECT 1, '2103', 'مخلصين جمركيين (Customs Brokers)', @liabilities_parent_id, 'Liability', 1
WHERE NOT EXISTS (SELECT 1 FROM chartofaccounts WHERE Code = '2103' AND TenantID = 1);

INSERT INTO chartofaccounts (TenantID, Code, Name, ParentID, Type, IsActive)
SELECT 1, '2104', 'ناقل محلي (Local Carriers)', @liabilities_parent_id, 'Liability', 1
WHERE NOT EXISTS (SELECT 1 FROM chartofaccounts WHERE Code = '2104' AND TenantID = 1);

-- 3. Update Partner Groups to point to these new Liability Accounts
-- Note: We are updating the 'AccountPayableID' field.

-- Update Freight Forwarders Group
UPDATE partner_groups
SET AccountPayableID = (SELECT AccountID FROM chartofaccounts WHERE Code = '2102' AND TenantID = 1)
WHERE Name LIKE '%شركات شحن%' AND TenantID = 1;

-- Update Customs Brokers Group
UPDATE partner_groups
SET AccountPayableID = (SELECT AccountID FROM chartofaccounts WHERE Code = '2103' AND TenantID = 1)
WHERE Name LIKE '%مخلصين%' AND TenantID = 1;

-- Update Local Transporters Group
UPDATE partner_groups
SET AccountPayableID = (SELECT AccountID FROM chartofaccounts WHERE Code = '2104' AND TenantID = 1)
WHERE Name LIKE '%ناقلين%' AND TenantID = 1;

-- 4. Clean up old incorrect Expense accounts (Optional - only if no transactions exist)
-- Identify the old incorrect accounts (5301, 5302, 5303)
-- We will just select them to show they exist, but won't delete automatically to avoid key constraint errors if used.
SELECT 'Refactored Accounts created. Old Expense accounts (53xx) might still exist:' AS Status;
SELECT * FROM chartofaccounts WHERE Code LIKE '53%' AND TenantID = 1;

-- 5. Verification
SELECT 'New Usage of Funds (Liabilities) Structure:' AS Verify;
SELECT AccountID, Code, Name, ParentID, Type FROM chartofaccounts WHERE ParentID = @liabilities_parent_id ORDER BY Code;

SELECT 'Partner Groups Linkage:' AS Verify_Groups;
SELECT pg.Name, pg.Type, coa.Code as LinkedAccountCode, coa.Name as LinkedAccountName
FROM partner_groups pg
JOIN chartofaccounts coa ON pg.AccountPayableID = coa.AccountID
WHERE pg.TenantID = 1;
