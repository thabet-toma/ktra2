-- Fix for logistics_deals
ALTER TABLE `logistics_deals`
ADD COLUMN IF NOT EXISTS `IsPosted` TINYINT(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `JournalID` INT NULL;

-- Fix for logistics_expenses
ALTER TABLE `logistics_expenses`
ADD COLUMN IF NOT EXISTS `IsPosted` TINYINT(1) DEFAULT 0,
ADD COLUMN IF NOT EXISTS `JournalID` INT NULL;
