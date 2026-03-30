-- Logistics & Imports Module Schema
-- Run this script to create the necessary tables for the new ERP features.

SET FOREIGN_KEY_CHECKS = 0;

-- 1. Deals (الصفقات)
CREATE TABLE IF NOT EXISTS `logistics_deals` (
    `DealID` INT NOT NULL AUTO_INCREMENT,
    `TenantID` INT NOT NULL,
    `RefNumber` VARCHAR(50) NOT NULL COMMENT 'رقم مرجعي للصفقة',
    `PartnerID` INT NOT NULL COMMENT 'المورد - Supplier',
    `OrderDate` DATE NOT NULL,
    `TotalAmount` DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    `CurrencyID` INT NOT NULL,
    `Status` ENUM('Open','Shipped','Cleared','Closed','Cancelled') NOT NULL DEFAULT 'Open',
    `Notes` MEDIUMTEXT,
    `CreatedAt` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `CreatedBy_UserID` INT,
    PRIMARY KEY (`DealID`),
    KEY `idx_tenant_deal` (`TenantID`),
    CONSTRAINT `fk_deal_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
    CONSTRAINT `fk_deal_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Deal Items (منتجات الصفقة)
CREATE TABLE IF NOT EXISTS `logistics_deal_items` (
    `DealItemID` INT NOT NULL AUTO_INCREMENT,
    `DealID` INT NOT NULL,
    `ProductID` INT NOT NULL,
    `Quantity` DECIMAL(18,4) NOT NULL,
    `UnitPrice` DECIMAL(18,4) NOT NULL,
    `TotalPrice` DECIMAL(18,2) NOT NULL,
    `Notes` VARCHAR(255),
    PRIMARY KEY (`DealItemID`),
    KEY `idx_deal_item` (`DealID`),
    CONSTRAINT `fk_dealitem_deal` FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`) ON DELETE CASCADE,
    CONSTRAINT `fk_dealitem_product` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Shipments (الشحنات)
CREATE TABLE IF NOT EXISTS `logistics_shipments` (
    `ShipmentID` INT NOT NULL AUTO_INCREMENT,
    `TenantID` INT NOT NULL,
    `ShipmentNumber` VARCHAR(50) NOT NULL,
    `ShippingAgentID` INT DEFAULT NULL COMMENT 'وكيل الشحن',
    `BillOfLading` VARCHAR(100) COMMENT 'رقم البوليصة',
    `ContainerNumber` VARCHAR(100),
    `DepartureDate` DATE,
    `ArrivalDate` DATE,
    `Status` ENUM('Pending','In-Transit','Arrived','Clearing','Cleared') NOT NULL DEFAULT 'Pending',
    `Notes` MEDIUMTEXT,
    PRIMARY KEY (`ShipmentID`),
    KEY `idx_tenant_shipment` (`TenantID`),
    CONSTRAINT `fk_shipment_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
    CONSTRAINT `fk_shipment_agent` FOREIGN KEY (`ShippingAgentID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Shipment-Deals Link (ربط الصفقات بالشحنة)
CREATE TABLE IF NOT EXISTS `logistics_shipment_deals` (
    `LinkID` INT NOT NULL AUTO_INCREMENT,
    `ShipmentID` INT NOT NULL,
    `DealID` INT NOT NULL,
    PRIMARY KEY (`LinkID`),
    UNIQUE KEY `idx_shipment_deal_unique` (`ShipmentID`, `DealID`),
    CONSTRAINT `fk_link_shipment` FOREIGN KEY (`ShipmentID`) REFERENCES `logistics_shipments` (`ShipmentID`) ON DELETE CASCADE,
    CONSTRAINT `fk_link_deal` FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Customs Clearance (التخليص الجمركي)
CREATE TABLE IF NOT EXISTS `logistics_clearance` (
    `ClearanceID` INT NOT NULL AUTO_INCREMENT,
    `TenantID` INT NOT NULL,
    `ShipmentID` INT NOT NULL,
    `CustomsBrokerID` INT DEFAULT NULL COMMENT 'المخلص الجمركي',
    `DeclarationNumber` VARCHAR(100) COMMENT 'رقم البيان الجمركي',
    `ClearanceDate` DATE,
    `Status` ENUM('Processing','Cleared','Hold') NOT NULL DEFAULT 'Processing',
    `Notes` MEDIUMTEXT,
    PRIMARY KEY (`ClearanceID`),
    UNIQUE KEY `idx_shipment_clearance` (`ShipmentID`),
    CONSTRAINT `fk_clearance_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
    CONSTRAINT `fk_clearance_shipment` FOREIGN KEY (`ShipmentID`) REFERENCES `logistics_shipments` (`ShipmentID`),
    CONSTRAINT `fk_clearance_broker` FOREIGN KEY (`CustomsBrokerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Logistics Expenses (المصاريف - شحن/تخليص/أخرى)
CREATE TABLE IF NOT EXISTS `logistics_expenses` (
    `ExpenseID` INT NOT NULL AUTO_INCREMENT,
    `TenantID` INT NOT NULL,
    `RelatedType` ENUM('Deal','Shipment','Clearance') NOT NULL,
    `RelatedID` INT NOT NULL,
    `ExpenseTypeID` INT DEFAULT NULL COMMENT 'Link to Expense Account in CoA?? Or separate type table?', 
    -- For simplicity, we link directly to GL Accounts (Expenses/Liabilities) via Service
    `Description` VARCHAR(255) NOT NULL,
    `Amount` DECIMAL(18,2) NOT NULL,
    `CurrencyID` INT NOT NULL DEFAULT 1,
    `PayableToID` INT DEFAULT NULL COMMENT 'Partner to whom this is owed (Agent/Broker)',
    `InvoiceNumber` VARCHAR(100),
    `InvoiceDate` DATE,
    `IsPosted` TINYINT(1) DEFAULT 0 COMMENT 'Posted to Accounting?',
    PRIMARY KEY (`ExpenseID`),
    KEY `idx_related` (`RelatedType`, `RelatedID`),
    CONSTRAINT `fk_expense_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
    CONSTRAINT `fk_expense_partner` FOREIGN KEY (`PayableToID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


SET FOREIGN_KEY_CHECKS = 1;
