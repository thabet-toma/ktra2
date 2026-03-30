-- =============================================
-- LOGISTICS & IMPORTS MODULE (Professional Schema)
-- Description: Complete schema for Deals, Shipments, Clearance, and Expenses.
-- Includes new fields: PI, Dimensions (CBM/KG), Payment Terms, etc.
-- =============================================

-- 1. DEALS (Orders from foreign suppliers)
CREATE TABLE IF NOT EXISTS `logistics_deals` (
  `DealID` INT AUTO_INCREMENT PRIMARY KEY,
  `TenantID` INT NOT NULL,
  `RefNumber` VARCHAR(50) NOT NULL,
  `PartnerID` INT NOT NULL COMMENT 'Supplier / Manufacturer',
  `OrderDate` DATE NOT NULL,
  `TotalAmount` DECIMAL(18,2) DEFAULT 0.00,
  `CurrencyID` INT NOT NULL,
  `Status` VARCHAR(20) DEFAULT 'Open',
  `Notes` TEXT,
  `CreatedAt` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `CreatedBy_UserID` INT,
  
  -- Professional Fields (New)
  `pi_number` VARCHAR(50) NULL COMMENT 'Proforma Invoice Number',
  `description` VARCHAR(255) NULL COMMENT 'e.g. Electrical Devices Order',
  `shipping_method` VARCHAR(50) DEFAULT 'Sea' COMMENT 'Sea, Air, Land',
  `incoterms` VARCHAR(10) DEFAULT 'FOB' COMMENT 'FOB, EXW, CIF, etc.',
  `payment_method` VARCHAR(50) DEFAULT 'T/T',
  `production_days` INT DEFAULT 0,
  `delivery_days` INT DEFAULT 0,
  `total_cbm` DECIMAL(10,3) DEFAULT 0.000 COMMENT 'Volume in Cubic Meters',
  `total_weight` DECIMAL(10,3) DEFAULT 0.000 COMMENT 'Weight in KG',
  `certificates` VARCHAR(255) NULL COMMENT 'CE, ISO, etc.',
  `shipping_cost_estimate` DECIMAL(18,2) DEFAULT 0.00,
  `discount_amount` DECIMAL(18,2) DEFAULT 0.00,
  `fees_percentage` DECIMAL(5,2) DEFAULT 0.00,
  `is_shipping_included` TINYINT(1) DEFAULT 0,

  FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE RESTRICT,
  FOREIGN KEY (`CurrencyID`) REFERENCES `currencies` (`CurrencyID`),
  FOREIGN KEY (`CreatedBy_UserID`) REFERENCES `auth_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. DEAL ITEMS (Products within a deal)
CREATE TABLE IF NOT EXISTS `logistics_deal_items` (
  `DealItemID` INT AUTO_INCREMENT PRIMARY KEY,
  `DealID` INT NOT NULL,
  `ProductID` INT NOT NULL,
  `Quantity` DECIMAL(18,4) NOT NULL DEFAULT 1.0000,
  `UnitPrice` DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
  `Notes` VARCHAR(255),
  
  FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`) ON DELETE CASCADE,
  FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. SHIPMENTS (Containers/Trips)
CREATE TABLE IF NOT EXISTS `logistics_shipments` (
  `ShipmentID` INT AUTO_INCREMENT PRIMARY KEY,
  `TenantID` INT NOT NULL,
  `ShipmentNumber` VARCHAR(50) NOT NULL COMMENT 'Internal Ref like SH-001',
  `ShippingAgentID` INT NULL COMMENT 'Freight Forwarder Partner',
  `BillOfLading` VARCHAR(100) NULL,
  `ContainerNumber` VARCHAR(100) NULL,
  `DepartureDate` DATE NULL,
  `ArrivalDate` DATE NULL,
  `Status` VARCHAR(20) DEFAULT 'Pending',
  `Notes` TEXT,

  FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  FOREIGN KEY (`ShippingAgentID`) REFERENCES `partners` (`PartnerID`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. SHIPMENT-DEAL LINK (Many-to-Many: One shipment can have multiple deals)
CREATE TABLE IF NOT EXISTS `logistics_shipment_deals` (
  `LinkID` INT AUTO_INCREMENT PRIMARY KEY,
  `ShipmentID` INT NOT NULL,
  `DealID` INT NOT NULL,
  
  FOREIGN KEY (`ShipmentID`) REFERENCES `logistics_shipments` (`ShipmentID`) ON DELETE CASCADE,
  FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`) ON DELETE RESTRICT,
  UNIQUE KEY `idx_shipment_deal` (`ShipmentID`, `DealID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. CLEARANCE (Customs process)
CREATE TABLE IF NOT EXISTS `logistics_clearance` (
  `ClearanceID` INT AUTO_INCREMENT PRIMARY KEY,
  `TenantID` INT NOT NULL,
  `ShipmentID` INT NOT NULL,
  `CustomsBrokerID` INT NULL COMMENT 'Customs Broker Partner',
  `DeclarationNumber` VARCHAR(100) NULL COMMENT 'Bayan Customs No',
  `ClearanceDate` DATE NULL,
  `Status` VARCHAR(20) DEFAULT 'Processing',
  `Notes` TEXT,
  
  FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  FOREIGN KEY (`ShipmentID`) REFERENCES `logistics_shipments` (`ShipmentID`) ON DELETE CASCADE,
  FOREIGN KEY (`CustomsBrokerID`) REFERENCES `partners` (`PartnerID`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. EXPENSES (Logistics costs & Accounting Link)
CREATE TABLE IF NOT EXISTS `logistics_expenses` (
  `ExpenseID` INT AUTO_INCREMENT PRIMARY KEY,
  `TenantID` INT NOT NULL,
  `RelatedType` VARCHAR(20) NOT NULL COMMENT 'Deal, Shipment, Clearance',
  `RelatedID` INT NOT NULL,
  `ExpenseAccountID` INT NOT NULL COMMENT 'Debit Account',
  `PayableAccountID` INT NOT NULL COMMENT 'Credit Account',
  `Description` VARCHAR(255) NOT NULL,
  `Amount` DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  `CurrencyID` INT NOT NULL DEFAULT 1,
  `InvoiceNumber` VARCHAR(100) NULL,
  `InvoiceDate` DATE NULL,
  `IsPosted` TINYINT(1) DEFAULT 0,
  `JournalID` INT NULL COMMENT 'Link to Accounting Journal',
  
  FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
  -- Note: FKs for Accounts not added strictly to avoid circular dependency issues if Account table differs, 
  -- but logically they refer to 'accounts' table.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
