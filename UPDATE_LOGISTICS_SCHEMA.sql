-- Add professional fields to Logistics Deals table
ALTER TABLE `logistics_deals`
ADD COLUMN `pi_number` VARCHAR(50) NULL COMMENT 'Supplier Proforma Invoice Number',
ADD COLUMN `description` VARCHAR(255) NULL COMMENT 'Short description of the deal payload',
ADD COLUMN `shipping_method` VARCHAR(50) DEFAULT 'Sea' COMMENT 'Sea, Air, Land',
ADD COLUMN `incoterms` VARCHAR(10) DEFAULT 'FOB' COMMENT 'FOB, EXW, CIF, etc.',
ADD COLUMN `payment_method` VARCHAR(50) DEFAULT 'T/T' COMMENT 'T/T 30%, LC, etc.',
ADD COLUMN `production_days` INT DEFAULT 0 COMMENT 'Estimated manufacturing time',
ADD COLUMN `delivery_days` INT DEFAULT 0 COMMENT 'Estimated shipping time',
ADD COLUMN `total_cbm` DECIMAL(10,3) DEFAULT 0.000 COMMENT 'Total Volume in CBM',
ADD COLUMN `total_weight` DECIMAL(10,3) DEFAULT 0.000 COMMENT 'Total Weight in KG',
ADD COLUMN `certificates` VARCHAR(255) NULL COMMENT 'Comma separated list: CE, ISO, etc.',
ADD COLUMN `shipping_cost_estimate` DECIMAL(18,2) DEFAULT 0.00 COMMENT 'Estimated shipping cost',
ADD COLUMN `discount_amount` DECIMAL(18,2) DEFAULT 0.00 COMMENT 'Discount on products',
ADD COLUMN `fees_percentage` DECIMAL(5,2) DEFAULT 0.00 COMMENT 'Additional Tax/Customs Estimate %';

-- Optional: Add IsShippingIncluded flag if needed
ALTER TABLE `logistics_deals` ADD COLUMN `is_shipping_included` TINYINT(1) DEFAULT 0;
