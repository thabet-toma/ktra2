-- ============================================================
-- Migration: Fix Payment Currency Mismatch (Critical Bug #2)
-- Date: 2026-04-17
-- Description:
--   Adds amount_in_invoice_currency and conversion_rate columns
--   to payment_allocations to support multi-currency payments.
--   When a payment is in USD but the invoice is in EUR, the
--   system now converts the amount properly before updating
--   the invoice's amount_paid field.
-- ============================================================

-- 1. Add the new columns
ALTER TABLE sales_module_payment_allocations
    ADD COLUMN IF NOT EXISTS AmountInInvoiceCurrency DECIMAL(18,2) NULL DEFAULT NULL
    COMMENT 'المبلغ محولاً لعملة الفاتورة';

ALTER TABLE sales_module_payment_allocations
    ADD COLUMN IF NOT EXISTS ConversionRate DECIMAL(18,6) NULL DEFAULT NULL
    COMMENT 'سعر الصرف المستخدم للتحويل';


-- 2. Backfill existing allocations (same-currency = copy amount as-is)
--    For existing data where payment currency == invoice currency:
UPDATE sales_module_payment_allocations pa
JOIN sales_module_customer_payments cp ON pa.PaymentID = cp.CustomerPaymentID
JOIN sales_module_invoices si ON pa.InvoiceID = si.SalesInvoiceID
SET
    pa.AmountInInvoiceCurrency = pa.Amount,
    pa.ConversionRate = 1.000000
WHERE cp.CurrencyID = si.CurrencyID
  AND pa.AmountInInvoiceCurrency IS NULL;

-- 3. For cross-currency allocations that already exist (edge case):
--    Flag them so they can be reviewed manually
--    (These are the problematic records from before the fix)
SELECT
    pa.PaymentAllocationID,
    cp.CustomerPaymentID AS PaymentID,
    cp.CurrencyID AS PaymentCurrencyID,
    si.SalesInvoiceID AS InvoiceID,
    si.CurrencyID AS InvoiceCurrencyID,
    pa.Amount AS OriginalAmount,
    pa.AmountInInvoiceCurrency
FROM sales_module_payment_allocations pa
JOIN sales_module_customer_payments cp ON pa.PaymentID = cp.CustomerPaymentID
JOIN sales_module_invoices si ON pa.InvoiceID = si.SalesInvoiceID
WHERE cp.CurrencyID != si.CurrencyID
  AND pa.AmountInInvoiceCurrency IS NULL;

-- NOTE: The SELECT above will show cross-currency allocations that need manual review.
-- For each one, you should:
--   1. Look up the exchange rate at the payment date
--   2. Calculate AmountInInvoiceCurrency = Amount * rate
--   3. Update the record
--   4. Recalculate the invoice's AmountPaid field

-- ============================================================
-- Verification query: check no NULL values remain after backfill
-- ============================================================
-- SELECT COUNT(*) as unpatched FROM sales_module_payment_allocations
-- WHERE AmountInInvoiceCurrency IS NULL;
