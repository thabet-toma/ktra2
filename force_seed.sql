-- Force wipe and seed expert COA
USE `global_erp_pro`;
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE journal_lines;
TRUNCATE TABLE journal_headers;
TRUNCATE TABLE chartofaccounts;
TRUNCATE TABLE accounting_audit_logs;

-- Root Nodes (TenantID 1)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `Type`, `IsActive`) VALUES 
(1, 1, '1', 'الأصول (Assets)', 'Asset', 1),
(2, 1, '2', 'الخصوم (Liabilities)', 'Liability', 1),
(3, 1, '3', 'حقوق الملكية (Equity)', 'Equity', 1),
(4, 1, '4', 'الإيرادات (Revenue)', 'Revenue', 1),
(5, 1, '5', 'المصروفات (Expenses)', 'Expense', 1);

-- Current Assets (Parent 1)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(6, 1, '11', 'الأصول المتداولة (Current Assets)', 1, 'Asset', 1),
(7, 1, '1101', 'النقدية (Cash)', 6, 'Asset', 1),
(8, 1, '1102', 'البنوك (Banks)', 6, 'Asset', 1),
(9, 1, '1103', 'ذمم العملاء (Accounts Receivable)', 6, 'Asset', 1);

-- Current Liabilities (Parent 2)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(10, 1, '21', 'الخصوم المتداولة (Current Liabilities)', 2, 'Liability', 1),
(11, 1, '2101', 'ذمم الموردين (Accounts Payable)', 10, 'Liability', 1);

SET FOREIGN_KEY_CHECKS = 1;
