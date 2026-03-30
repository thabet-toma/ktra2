-- SQL Script to set up additional accounting tables if not already present

-- 1. Ensure accounting_audit_logs table exists
CREATE TABLE IF NOT EXISTS `accounting_audit_logs` (
  `LogID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `UserID` int DEFAULT NULL,
  `Action` varchar(20) NOT NULL,
  `ModelName` varchar(100) NOT NULL,
  `ObjectID` int NOT NULL,
  `ChangeDetails` text NOT NULL,
  `Timestamp` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`LogID`),
  KEY `TenantID` (`TenantID`),
  CONSTRAINT `fk_audit_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Ensure chartofaccounts, journal_headers, and journal_lines exist as per dump
-- (These should already be there according to your Dump file)
