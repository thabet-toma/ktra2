-- ========================================
-- ADD LOGISTICS PARTNER ACCOUNTS & GROUPS
-- ========================================

USE global_erp_pro;

-- 1. Add Logistics Accounts under Expenses (5 - المصروفات)
INSERT INTO chartofaccounts (TenantID, Code, Name, ParentID, Type, IsActive) VALUES
(1, '53', 'مصاريف لوجستية (Logistics Expenses)', 5, 'Expense', 1);

-- Get the ID of the new parent account
SET @logistics_parent_id = LAST_INSERT_ID();

-- Add sub-accounts for each logistics partner type
INSERT INTO chartofaccounts (TenantID, Code, Name, ParentID, Type, IsActive) VALUES
(1, '5301', 'شركات الشحن (Freight Forwarders)', @logistics_parent_id, 'Expense', 1),
(1, '5302', 'المخلصين الجمركيين (Customs Brokers)', @logistics_parent_id, 'Expense', 1),
(1, '5303', 'الناقلين المحليين (Local Transporters)', @logistics_parent_id, 'Expense', 1);

-- 2. Create Partner Groups for each type
INSERT INTO partner_groups (TenantID, Name, Type, AccountPayableID) VALUES
(1, 'شركات شحن (Freight Forwarders)', 'Supplier', (SELECT AccountID FROM chartofaccounts WHERE Code = '5301' LIMIT 1)),
(1, 'مخلصين جمركيين (Customs Brokers)', 'Supplier', (SELECT AccountID FROM chartofaccounts WHERE Code = '5302' LIMIT 1)),
(1, 'ناقلين محليين (Local Transporters)', 'Supplier', (SELECT AccountID FROM chartofaccounts WHERE Code = '5303' LIMIT 1));

-- 3. Verify
SELECT 'COA Accounts:' as Info;
SELECT Code, Name, Type FROM chartofaccounts WHERE Code LIKE '53%' ORDER BY Code;

SELECT 'Partner Groups:' as Info;
SELECT GroupID, Name, Type FROM partner_groups;
