import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  invoiceGrandTotalIls,
  invoiceVatBaseIls,
  supplierFeesTotalIls,
  vatBaseFeesIls,
} from './invoiceTaxesAndFees.ts';

// عمولات الحوالات مصروفٌ بنكي في قيد الدفعة (قرار المالك 2026-10-07) — لا أساس ضريبة
// الفاتورة الدولية ولا إجماليها. كانت تدخل الأساس وسطر «قبل الضريبة» وتخرج من الإجمالي:
// 11,259.52 «قبل الضريبة» فوق 11,125.12 «بعد الضريبة» بضريبةٍ صفر.
const meta = {
  allocation_method: 'server_pro_rata',
  line_meta: { deal_transfer_commissions_ils: 134.4 },
};

test('أساس الضريبة: البضاعة المحمَّلة وحدها، بلا عمولات الحوالات', () => {
  assert.equal(invoiceVatBaseIls(11125.12, meta, null), 11125.12);
  const detailed = {
    includedInPrice: false,
    calculationMethod: 'detailed' as const,
    customsClearanceFees: 0,
    customsDuties: 0,
    portFees: 0,
    palestinianTaxCustoms: 0,
  };
  assert.equal(invoiceVatBaseIls(100, { line_meta: { deal_transfer_commissions_ils: 5 } }, detailed), 100);
});

test('الإجمالي = الأساس + الضريبة أياً كان مسار المدفوعات المحلية', () => {
  const detailed = {
    includedInPrice: false,
    calculationMethod: 'detailed' as const,
    customsClearanceFees: 0,
    customsDuties: 0,
    portFees: 0,
    palestinianTaxCustoms: 0,
  };
  assert.equal(invoiceGrandTotalIls(11125.12, 0, meta, null), 11125.12);
  assert.equal(invoiceGrandTotalIls(11125.12, 0, meta, detailed), 11125.12);
});

// الطرف الدائن للرسم وأساس الضريبة — مرآة `logistics/services.py`
// (`purchase_invoice_fees_total`، `purchase_invoice_vat_base_fees_total`).
const fee = (over: Record<string, unknown>) => ({
  amount: 0, calculationType: 'amount' as const, calculationValue: 0,
  percentageBasis: 'goods' as const, isTaxable: false, ...over,
});

test('رسوم المورد بلا الرسوم ذات الطرف الدائن (جهة أو حساب)', () => {
  const fees = [
    fee({ amount: 100 }),
    fee({ amount: 4234.9, creditPartnerId: 7 }),
    fee({ amount: 194.4, creditAccountId: 52 }),
  ];
  assert.equal(supplierFeesTotalIls(fees), 100);
  assert.equal(supplierFeesTotalIls([]), 0);
  assert.equal(supplierFeesTotalIls(undefined), 0);
});

test('«ضمن أساس الضريبة» وحده يدخل الأساس، والنسبة على البضاعة تُحلّ أولاً', () => {
  const fees = [
    fee({ amount: 100, calculationValue: 100, isTaxable: true }),
    fee({ amount: 50, calculationValue: 50 }),
    fee({ calculationType: 'percentage', calculationValue: 10, isTaxable: true }),
    // نسبة «بعد الضريبة» لا تدخل الأساس الذي تُحسب منه.
    fee({ calculationType: 'percentage', calculationValue: 10, percentageBasis: 'after_main_vat', isTaxable: true }),
  ];
  // 100 + 10% × 2000
  assert.equal(vatBaseFeesIls(fees, 2000), 300);
  assert.equal(vatBaseFeesIls([fee({ amount: 80, calculationValue: 80 })], 2000), 0);
});
