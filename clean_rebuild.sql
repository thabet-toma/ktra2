-- Clean Rebuild COA
USE `global_erp_pro`;
SET FOREIGN_KEY_CHECKS = 0;

-- Wipe all accounting data
TRUNCATE TABLE journal_lines;
TRUNCATE TABLE journal_headers;
TRUNCATE TABLE chartofaccounts;
TRUNCATE TABLE accounting_audit_logs;
TRUNCATE TABLE partner_groups;
UPDATE partners SET GroupID = NULL, LinkedAccountID = NULL;

-- Seed Root Accounts (Account Types)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `Type`, `IsActive`) VALUES 
(1, 1, '1', 'الأصول (Assets)', 'Asset', 1),
(2, 1, '2', 'الخصوم (Liabilities)', 'Liability', 1),
(3, 1, '3', 'حقوق الملكية (Equity)', 'Equity', 1),
(4, 1, '4', 'الإيرادات (Revenue)', 'Revenue', 1),
(5, 1, '5', 'المصروفات (Expenses)', 'Expense', 1);

-- Current Assets (under 1)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(6, 1, '11', 'الأصول المتداولة (Current Assets)', 1, 'Asset', 1),
(7, 1, '1101', 'النقدية (Cash)', 6, 'Asset', 1),
(8, 1, '1102', 'البنوك (Banks)', 6, 'Asset', 1),
(9, 1, '1103', 'ذمم العملاء (Accounts Receivable)', 6, 'Asset', 1),
(10, 1, '1104', 'المخزون (Inventory)', 6, 'Asset', 1);

-- Non-Current Assets (under 1)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(11, 1, '12', 'الأصول غير المتداولة (Non-Current Assets)', 1, 'Asset', 1),
(12, 1, '1201', 'الأراضي والمباني (Land & Buildings)', 11, 'Asset', 1),
(13, 1, '1202', 'الآلات والمعدات (Machinery & Equipment)', 11, 'Asset', 1);

-- Current Liabilities (under 2)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(14, 1, '21', 'الخصوم المتداولة (Current Liabilities)', 2, 'Liability', 1),
(15, 1, '2101', 'ذمم الموردين (Accounts Payable)', 14, 'Liability', 1),
(16, 1, '2102', 'أوراق الدفع (Notes Payable)', 14, 'Liability', 1);

-- Equity (under 3)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(17, 1, '31', 'رأس المال (Capital)', 3, 'Equity', 1),
(18, 1, '32', 'الأرباح المحتجزة (Retained Earnings)', 3, 'Equity', 1),
(19, 1, '33', 'الأرصدة الافتتاحية (Opening Balances)', 3, 'Equity', 1),
(20, 1, '3300', 'وسيط الأرصدة الافتتاحية', 19, 'Equity', 1);

-- Revenue (under 4)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(21, 1, '41', 'إيرادات المبيعات (Sales Revenue)', 4, 'Revenue', 1);

-- Expenses (under 5)
INSERT INTO `chartofaccounts` (`AccountID`, `TenantID`, `Code`, `Name`, `ParentID`, `Type`, `IsActive`) VALUES 
(22, 1, '51', 'تكلفة البضاعة المباعة (COGS)', 5, 'Expense', 1),
(23, 1, '52', 'المصروفات التشغيلية (Operating Expenses)', 5, 'Expense', 1);

-- Seed Partner Groups
INSERT INTO `partner_groups` (`GroupID`, `TenantID`, `Name`, `Type`, `AccountReceivableID`, `AccountPayableID`) VALUES
(1, 1, 'عملاء محليين (Local Customers)', 'Customer', 9, NULL),
(2, 1, 'موردين محليين (Local Suppliers)', 'Supplier', NULL, 15);

SET FOREIGN_KEY_CHECKS = 1;
