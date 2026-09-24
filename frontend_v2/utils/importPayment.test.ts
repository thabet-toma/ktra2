import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importPaymentTooltip, type ImportPaymentBreakdown } from './importPayment.ts';

const comp = (paid: string, cost: string) => ({ paid, cost, remaining: '0' });

test('التفصيل بترتيب الدائنين الأربعة: المدفوع من التكلفة', () => {
  const ip: ImportPaymentBreakdown = {
    payment_status: 'partially_paid',
    payment_status_display: 'مدفوعة جزئياً',
    payable_total: '8579.85',
    amount_paid: '7000',
    remaining_balance: '1579.85',
    components: {
      local: comp('0.00', '149.99'),
      supplier: comp('7000.00', '7000.00'),
      clearance: comp('115.50', '229.98'),
      freight: comp('0.00', '1199.88'),
    },
  };
  assert.equal(
    importPaymentTooltip(ip),
    'مورد 7,000 / 7,000 · شحن 0 / 1,199.88 · تخليص 115.5 / 229.98 · محلي 0 / 149.99',
  );
});

test('بلا تفصيل: نصٌّ فارغ لا انهيار', () => {
  assert.equal(importPaymentTooltip(null), '');
  assert.equal(importPaymentTooltip(undefined), '');
});
