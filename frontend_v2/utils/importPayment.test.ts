import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyImportUnitCosts, importCostRows, importFinalUnitCost, importPaymentRows, importPaymentTooltip, purchasePayableTotal, purchaseSupplierPayBase, type ImportPaymentBreakdown } from './importPayment.ts';

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

test('أساس دفع المورد: المسودة الدولية بحصّته من الخادم لا بالمحمَّل', () => {
  // INV-0022: المحمَّل 12,896.53؛ الترحيل سيدائن المورد بـ5,856 وحدها.
  const draft = { payableTotal: 12896.53, international: true, isPosted: false };
  assert.equal(purchaseSupplierPayBase({ ...draft, serverSupplierPayable: 5856 }), 5856);
  // مسودةٌ لم تُحفظ بعد: لا رقم من الخادم — الإجمالي كما كان.
  assert.equal(purchaseSupplierPayBase({ ...draft, serverSupplierPayable: undefined }), 12896.53);
  // المرحّلة: `payableTotal` هو حصّة المورد أصلاً (من القيد).
  assert.equal(
    purchaseSupplierPayBase({ payableTotal: 7000, international: true, isPosted: true, serverSupplierPayable: 1 }),
    7000,
  );
  // المحلية: الإجمالي مهما قال الخادم.
  assert.equal(
    purchaseSupplierPayBase({ payableTotal: 115, international: false, isPosted: false, serverSupplierPayable: 1 }),
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

test('تفصيل التكاليف: سطور الخادم بأرقامها، وإجماليها ومدفوعه = المربّع (`payable_total`) — ولا قسم بلا سطور', () => {
  const ip = {
    payment_status: 'partially_paid', payment_status_display: 'مدفوعة جزئياً',
    payable_total: '1135.00', amount_paid: '1035.00', remaining_balance: '100.00',
    components: { supplier: { cost: '1000.00', paid: '1000.00', remaining: '0.00' } },
    cost_rows: [
      { key: 'supplier', label: 'المورد', cost: '1000.00', paid: '1000.00', remaining: '0.00' },
      { key: 'commission', label: 'عمولات التحويل', cost: '35.00', paid: '35.00', remaining: '0.00' },
      { key: 'fee:7', label: 'تكاليف كترا', cost: '100.00', paid: '0.00', remaining: '100.00' },
    ],
  } as unknown as ImportPaymentBreakdown;
  const out = importCostRows(ip);
  assert.ok(out);
  assert.deepEqual(out.rows.map((r) => r.key), ['supplier', 'commission', 'fee:7']);
  assert.equal(out.rows[2].remaining, 100);
  assert.equal(out.totalCost, 1135);
  assert.equal(out.totalPaid, 1035);
  assert.equal(out.totalRemaining, 100);
  assert.equal(importCostRows({ ...ip, cost_rows: undefined }), null);
  assert.equal(importCostRows(null), null);
});

test('التكلفة النهائية/وحدة: من unit_costs الخادم للبند المحفوظ، وإلا السلوك الحالي', () => {
  // INV-0023: سعر البند 41.44، والخادم 46.0506 (رسم كترا المرسمَل + العمولة، بلا الضريبة).
  const ip = {
    unit_costs: [
      { item_id: 7, name: 'أ', quantity: '10', unit_cost: '46.0506' },
      { item_id: 8, name: 'ب', quantity: '5', unit_cost: '53.1354' },
    ],
  } as unknown as ImportPaymentBreakdown;
  assert.equal(importFinalUnitCost(ip, 7, 41.44), 46.0506);
  assert.equal(importFinalUnitCost(ip, 8, 47.81), 53.1354);
  // بندٌ لم يُحفظ بعد (بلا serverId) أو غائبٌ عن التفصيل ⇒ القيمة المحسوبة في الشاشة.
  assert.equal(importFinalUnitCost(ip, undefined, 41.44), 41.44);
  assert.equal(importFinalUnitCost(ip, 99, 54.18), 54.18);
  // بلا unit_costs (المحلية، أو قائمة بلا تفصيل) ⇒ كما كان، حتى الفراغ.
  assert.equal(importFinalUnitCost(undefined, 7, 41.44), 41.44);
  assert.equal(importFinalUnitCost({} as ImportPaymentBreakdown, 7, undefined), null);
});

test('تكلفة البند في الشاشة = unit_costs الخادم (بالضريبة والرسوم والعمولة)، وإلا التوزيع المحلي', () => {
  // INV-0023: التوزيع المحلي بلا العمولة؛ الخادم يحملها — مجموع الأسطر = إجمالي التكلفة.
  const local = [
    { share: 0.6, landedBase: 414.4, taxAndFeesAllocation: 90, preTaxLine: 414.4, finalLine: 504.4, finalUnit: 50.44 },
    { share: 0.4, landedBase: 276.0, taxAndFeesAllocation: 60, preTaxLine: 276.0, finalLine: 336.0, finalUnit: 33.6 },
  ];
  const items = [{ serverId: 7, quantity: 10 }, { quantity: 10 }];
  const ip = { unit_costs: [{ item_id: 7, name: 'أ', quantity: '10', unit_cost: '51.25' }] } as unknown as ImportPaymentBreakdown;
  const out = applyImportUnitCosts(local, items, ip);
  assert.equal(out[0].finalUnit, 51.25);
  assert.equal(out[0].finalLine, 512.5);
  assert.equal(out[0].taxAndFeesAllocation, 512.5 - 414.4);
  assert.equal(out[0].preTaxLine, 414.4);
  // بندٌ لم يُحفظ: التوزيع المحلي كما هو.
  assert.deepEqual(out[1], local[1]);
  // بلا unit_costs: لا تغيير.
  assert.deepEqual(applyImportUnitCosts(local, items, undefined), local);
});
