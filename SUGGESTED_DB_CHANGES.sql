-- Suggested Database Changes for "Al-Aseel" Style Professional Accounting
-- Please execute these commands in your MySQL Database

-- 1. Create Cheques Table
CREATE TABLE IF NOT EXISTS `cheques` (
  `ChequeID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ChequeNumber` varchar(50) NOT NULL,
  `BankName` varchar(100),
  `Amount` decimal(18,2) NOT NULL,
  `CurrencyID` int NOT NULL DEFAULT 1,
  `DueDate` date NOT NULL,
  `IssueDate` date DEFAULT NULL,
  `PayeeName` varchar(150) DEFAULT NULL,
  `PartnerID` int DEFAULT NULL,
  `Status` enum('Draft','Under_Collection','Collected','Bounced','Returned') NOT NULL DEFAULT 'Draft',
  `Direction` enum('Incoming','Outgoing') NOT NULL COMMENT 'Incoming from Customer, Outgoing to Supplier',
  `CreatedBy_UserID` int DEFAULT NULL,
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  `Notes` mediumtext,
  PRIMARY KEY (`ChequeID`),
  KEY `TenantID` (`TenantID`),
  KEY `PartnerID` (`PartnerID`),
  CONSTRAINT `fk_cheque_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `fk_cheque_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Clean up JournalLines to allow Foreign Keys
-- WARNING: This will set invalid IDs to NULL to prevent errors when adding constraints.
-- Make sure to backup your data before running this.

UPDATE `journal_lines` SET `PartnerID` = NULL WHERE `PartnerID` NOT IN (SELECT `PartnerID` FROM `partners`);
-- Assuming cost_centers table exists. If not, create it first or skip the next line.
-- UPDATE `journal_lines` SET `CostCenterID` = NULL WHERE `CostCenterID` NOT IN (SELECT `CostCenterID` FROM `cost_centers`);

-- 3. Add Foreign Key Constraints to JournalLines (Strict Data Integrity)
-- Note: You might need to drop existing indices if they conflic.
ALTER TABLE `journal_lines`
ADD CONSTRAINT `fk_jline_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE SET NULL;

-- Uncomment if you have a cost_centers table
-- ALTER TABLE `journal_lines`
-- ADD CONSTRAINT `fk_jline_costcenter` FOREIGN KEY (`CostCenterID`) REFERENCES `cost_centers` (`CostCenterID`) ON DELETE SET NULL;
