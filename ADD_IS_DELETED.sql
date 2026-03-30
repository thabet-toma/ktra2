-- ========================================
-- ADD MISSING COLUMNS TO PARTNERS TABLE
-- ========================================

USE global_erp_pro;

-- Add is_deleted column
ALTER TABLE partners 
ADD COLUMN IF NOT EXISTS is_deleted TINYINT(1) DEFAULT 0;

-- Verify
DESCRIBE partners;
