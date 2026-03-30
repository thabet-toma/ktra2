-- ERP Refinement Operations
-- This script implements architectural improvements: Soft Delete, Indexing, and Reporting Views.

USE `global_erp_pro`;

-- ==========================================
-- 1. IMPLEMENT SOFT DELETE COLUMNS
-- ==========================================

ALTER TABLE `chartofaccounts` 
ADD COLUMN `is_deleted` TINYINT(1) DEFAULT 0,
ADD COLUMN `deleted_at` DATETIME DEFAULT NULL;

ALTER TABLE `journal_headers` 
ADD COLUMN `is_deleted` TINYINT(1) DEFAULT 0,
ADD COLUMN `deleted_at` DATETIME DEFAULT NULL;

ALTER TABLE `journal_lines` 
ADD COLUMN `is_deleted` TINYINT(1) DEFAULT 0,
ADD COLUMN `deleted_at` DATETIME DEFAULT NULL;


-- ==========================================
-- 2. PERFORMANCE INDEXING (Point 5)
-- ==========================================

CREATE INDEX `idx_journal_lines_reporting` ON `journal_lines` (`TenantID`, `PartnerID`, `AccountID`);
CREATE INDEX `idx_partners_type` ON `partners` (`TenantID`, `Type`);
CREATE INDEX `idx_products_category` ON `products` (`TenantID`, `CategoryID`);


-- ==========================================
-- 3. REPORTING VIEWS (Point 6)
-- ==========================================

-- View for Trial Balance
CREATE OR REPLACE VIEW `vw_trial_balance` AS
SELECT 
    l.TenantID,
    a.AccountID,
    a.Code AS AccountCode,
    a.Name AS AccountName,
    SUM(l.Debit) AS TotalDebit,
    SUM(l.Credit) AS TotalCredit,
    (SUM(l.Debit) - SUM(l.Credit)) AS Balance
FROM `journal_lines` l
JOIN `chartofaccounts` a ON l.AccountID = a.AccountID
JOIN `journal_headers` h ON l.JournalID = h.JournalID
WHERE h.IsPosted = 1 AND l.is_deleted = 0
GROUP BY l.TenantID, a.AccountID, a.Code, a.Name;

-- View for Aged Receivables (Simplified)
CREATE OR REPLACE VIEW `vw_aged_receivables` AS
SELECT 
    TenantID,
    PartnerID,
    SUM(CASE WHEN DATEDIFF(CURDATE(), TransactionDate) <= 30 THEN Balance ELSE 0 END) AS `0_30_Days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), TransactionDate) > 30 AND DATEDIFF(CURDATE(), TransactionDate) <= 60 THEN Balance ELSE 0 END) AS `31_60_Days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), TransactionDate) > 60 THEN Balance ELSE 0 END) AS `Over_60_Days`,
    SUM(Balance) AS TotalOutstanding
FROM (
    -- This would normally join with Sales Invoices, using journals as fallback for now
    SELECT 
        l.TenantID,
        l.PartnerID,
        h.TransactionDate,
        (SUM(l.Debit) - SUM(l.Credit)) AS Balance
    FROM `journal_lines` l
    JOIN `journal_headers` h ON l.JournalID = h.JournalID
    JOIN `chartofaccounts` a ON l.AccountID = a.AccountID
    WHERE h.IsPosted = 1 AND a.Type = 'Asset' AND l.PartnerID IS NOT NULL
    GROUP BY l.TenantID, l.PartnerID, h.TransactionDate, h.JournalID
) AS sub
GROUP BY TenantID, PartnerID;


-- ==========================================
-- 4. SCHEMA CLEANUP: ENG TRANSLATION (Point 7)
-- ==========================================

ALTER TABLE `crm_leads` MODIFY `LeadName` varchar(200) COMMENT 'Lead Person or Company Name';
ALTER TABLE `crm_leads` MODIFY `Source` varchar(100) COMMENT 'Lead Source (e.g. Facebook, Referral)';
ALTER TABLE `chartofaccounts` COMMENT = 'Standard Chart of Accounts (COA) for multi-tenancy';
ALTER TABLE `partners` COMMENT = 'Stores legal partner entities (Customers, Suppliers, etc.)';
