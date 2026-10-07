import { test } from 'node:test';
import assert from 'node:assert/strict';
import { invoiceGrandTotalIls, invoiceVatBaseIls } from './invoiceTaxesAndFees.ts';

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
