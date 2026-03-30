-- Upgrade Logistics Schema V2
-- Adds dual status tracking and payment schedule support

-- 1. Update logistics_deals table
-- Adding PaymentStatus and OrderStatus columns if they don't exist (using procedure/block logic or just direct ALTERs assuming they don't exist yet)
-- Since MySQL doesn't have IF NOT EXISTS for columns in simple ALTER, we will just try to add them. if they exist it might error, but usually this is a one-time run.

ALTER TABLE `logistics_deals`
ADD COLUMN `PaymentStatus` ENUM('Unpaid', 'Partially Paid', 'Fully Paid') DEFAULT 'Unpaid',
ADD COLUMN `OrderStatus` ENUM('Open', 'Manufacturing', 'ReadyToShip', 'Shipping', 'Clearance', 'Delivered', 'Closed') DEFAULT 'Open',
ADD COLUMN `CurrencyRate` DECIMAL(18, 6) DEFAULT 1.000000;

-- 2. Create logistics_payments table
CREATE TABLE IF NOT EXISTS `logistics_payments` (
    `PaymentID` INT AUTO_INCREMENT PRIMARY KEY,
    `DealID` INT NOT NULL,
    `PaymentNumber` INT NOT NULL,
    `Title` VARCHAR(100) NOT NULL COMMENT 'e.g. Down Payment, Final Payment',
    `DueDate` DATE NULL,
    `Percentage` DECIMAL(5, 2) DEFAULT 0.00,
    `Amount` DECIMAL(18, 2) DEFAULT 0.00 COMMENT 'Amount in Deal Currency (USD)',
    `Amount_Local` DECIMAL(18, 2) DEFAULT 0.00 COMMENT 'Amount in Local Currency (ILS) at time of payment',
    `Status` ENUM('Pending', 'ClaimUploaded', 'Paid', 'Confirmed') DEFAULT 'Pending',
    `ClaimDoc` VARCHAR(255) NULL COMMENT 'Path to Claim Document',
    `InvoiceDoc` VARCHAR(255) NULL COMMENT 'Path to Invoice Document',
    `TransferDate` DATE NULL,
    `ConfirmationDate` DATE NULL,
    `Notes` TEXT NULL,
    `CreatedAt` DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_logistics_payments_deal` FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
