import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importPaymentRows, importPaymentTooltip, purchasePayableTotal, type ImportPaymentBreakdown } from './importPayment.ts';

test('صفوف طباعة الدولية: بالترتيب، وصفّ المورد حصّته − مدفوعه = باقيه', () => {
  const rows = importPaymentRows({
    payment_status: 'partially_paid',
    payment_status_display: 'مدفوعة جزئياً',
    payable_total: '12165.52',
    amount_paid: '7388.90',
    remaining_balance: '4776.62',
    components: {
      freight: { cost: '4776.62', paid: '0.00', remaining: '4776.62' },
      supplier: { cost: '7388.90', paid: '7388.90', remaining: '0.00' },
    },
  } as unknown as ImportPaymentBreakdown);
  assert.deepEqual(rows.map((r) => r.label), ['مورد', 'شحن']);
  const supplier = rows[0];
  assert.equal(supplier.cost - supplier.paid, supplier.remaining);
  assert.deepEqual(importPaymentRows(undefined), []);
});

test('أساس الدفع: الدولية المرحّلة بحصّة المورد من الخادم لا بالمحمَّل', () => {
  // المحمَّل 8,579.85 (بضاعة + شحن + تخليص + محلي)؛ المورد دائنٌ بـ7,000 وحدها.
  const international = { grandTotal: 8579.85, feesTotal: 0, international: true, serverPayableTotal: 7000 };
  assert.equal(purchasePayableTotal({ ...international, isPosted: true }), 7000);
  // قبل الترحيل لا حصّة بعد: الإجمالي كما كان.
  assert.equal(purchasePayableTotal({ ...international, isPosted: false }), 8579.85);
  // المحلية: الإجمالي + الرسوم مهما قال الخادم.
  assert.equal(
    purchasePayableTotal({ grandTotal: 100, feesTotal: 15, international: false, isPosted: true, serverPayableTotal: 1 }),
    115,
  );
});

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
