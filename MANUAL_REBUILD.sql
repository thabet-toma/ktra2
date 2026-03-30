-- ========================================
-- MANUAL COA REBUILD SCRIPT
-- Execute this in MySQL Workbench
-- ========================================

USE global_erp_pro;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. DELETE ALL OLD ACCOUNTS
DELETE FROM chartofaccounts;
DELETE FROM journal_lines;
DELETE FROM journal_headers;
DELETE FROM accounting_audit_logs;
UPDATE partners SET LinkedAccountID = NULL, GroupID = NULL;

-- 2. INSERT ROOT ACCOUNTS (Account Types)
INSERT INTO chartofaccounts (AccountID, TenantID, Code, Name, Type, IsActive) VALUES
(1, 1, '1', 'الأصول (Assets)', 'Asset', 1),
(2, 1, '2', 'الخصوم (Liabilities)', 'Liability', 1),
(3, 1, '3', 'حقوق الملكية (Equity)', 'Equity', 1),
(4, 1, '4', 'الإيرادات (Revenue)', 'Revenue', 1),
(5, 1, '5', 'المصروفات (Expenses)', 'Expense', 1);

-- 3. INSERT SUB-ACCOUNTS
INSERT INTO chartofaccounts (AccountID, TenantID, Code, Name, ParentID, Type, IsActive) VALUES
-- Current Assets
(6, 1, '11', 'الأصول المتداولة', 1, 'Asset', 1),
(7, 1, '1101', 'النقدية', 6, 'Asset', 1),
(8, 1, '1102', 'البنوك', 6, 'Asset', 1),
(9, 1, '1103', 'ذمم العملاء', 6, 'Asset', 1),
(10, 1, '1104', 'المخزون', 6, 'Asset', 1),

-- Non-Current Assets
(11, 1, '12', 'الأصول غير المتداولة', 1, 'Asset', 1),
(12, 1, '1201', 'الأراضي والمباني', 11, 'Asset', 1),
(13, 1, '1202', 'الآلات والمعدات', 11, 'Asset', 1),

-- Current Liabilities
(14, 1, '21', 'الخصوم المتداولة', 2, 'Liability', 1),
(15, 1, '2101', 'ذمم الموردين', 14, 'Liability', 1),
(16, 1, '2102', 'أوراق الدفع', 14, 'Liability', 1),

-- Equity
(17, 1, '31', 'رأس المال', 3, 'Equity', 1),
(18, 1, '32', 'الأرباح المحتجزة', 3, 'Equity', 1),
(19, 1, '33', 'الأرصدة الافتتاحية', 3, 'Equity', 1),
(20, 1, '3300', 'وسيط الأرصدة', 19, 'Equity', 1),

-- Revenue
(21, 1, '41', 'إيرادات المبيعات', 4, 'Revenue', 1),

-- Expenses
(22, 1, '51', 'تكلفة البضاعة المباعة', 5, 'Expense', 1),
(23, 1, '52', 'المصروفات التشغيلية', 5, 'Expense', 1);

SET FOREIGN_KEY_CHECKS = 1;

-- Verify
SELECT COUNT(*) as TotalAccounts FROM chartofaccounts;
SELECT Code, Name, Type FROM chartofaccounts WHERE ParentID IS NULL ORDER BY Code;
