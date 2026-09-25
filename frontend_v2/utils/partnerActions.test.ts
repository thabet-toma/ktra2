import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  partnerActionGroups,
  partnerKindFromType,
  partnerTypeLabel,
  partnerVoucherDirections,
  type PartnerActionGroup,
} from './partnerActions.ts';

const keysOf = (groups: PartnerActionGroup[]) =>
  groups.flatMap((g) => g.actions.map((a) => a.key));

test('نوع الطرف في الخادم يُترجَم إلى عميل/مورد أو لا شيء', () => {
  assert.equal(partnerKindFromType('Customer'), 'customer');
  assert.equal(partnerKindFromType('Supplier'), 'supplier');
  // أطراف الشحن تُعامَل معاملة المورد — تُشترى منها خدمات وتُصرف لها سندات.
  assert.equal(partnerKindFromType('FreightForwarder'), 'supplier');
  assert.equal(partnerKindFromType('CustomsBroker'), 'supplier');
  assert.equal(partnerKindFromType('LocalTransporter'), 'supplier');
  assert.equal(partnerKindFromType('Carrier'), 'supplier');
  assert.equal(partnerKindFromType(''), null);
  assert.equal(partnerKindFromType(undefined), null);
  assert.equal(partnerKindFromType('Unknown'), null);
});

test('إجراءات العميل مستندات بيع — ولا تسرّب لمستندات الشراء', () => {
  const groups = partnerActionGroups({ id: '7', name: 'زبون', kind: 'customer' });
  const keys = keysOf(groups);
  assert.ok(keys.includes('card'));
  assert.ok(keys.includes('statement'));
  assert.ok(keys.includes('sales-invoice'));
  assert.ok(keys.includes('fee-invoice'));
  assert.ok(keys.includes('repeat-last-invoice'));
  assert.ok(keys.includes('sales-quotation'));
  assert.ok(keys.includes('sales-order'));
  assert.ok(keys.includes('receipt'));
  assert.ok(!keys.includes('purchase-invoice'));
  assert.ok(!keys.includes('payment'));
});

test('ISSUE #53 — فاتورة الأتعاب تبدأ من بطاقة العميل بعميلٍ مملوء وبندٍ خدمي افتراضاً', () => {
  const groups = partnerActionGroups({ id: '7', name: 'زبون', kind: 'customer' });
  const byKey = new Map(groups.flatMap((g) => g.actions.map((a) => [a.key, a])));
  assert.equal(byKey.get('fee-invoice')?.href, '/sales/invoices/new?customer_id=7&service=1');
});

test('ISSUE #53 — «كرّر فاتورة الشهر الماضي» ليست متاحةً للمورّد', () => {
  const groups = partnerActionGroups({ id: '9', name: 'مورد', kind: 'supplier' });
  const keys = keysOf(groups);
  assert.ok(!keys.includes('fee-invoice'));
  assert.ok(!keys.includes('repeat-last-invoice'));
});

test('إجراءات المورد مستندات شراء — ولا تسرّب لمستندات البيع', () => {
  const groups = partnerActionGroups({ id: '9', name: 'مورد', kind: 'supplier' });
  const keys = keysOf(groups);
  assert.ok(keys.includes('purchase-invoice'));
  assert.ok(keys.includes('payment'));
  assert.ok(keys.includes('purchase-offer'));
  assert.ok(!keys.includes('sales-invoice'));
  assert.ok(!keys.includes('receipt'));
});

test('اتجاه السند الافتراضي من نوع الطرف: الدائنون «سند صرف» والعميل «سند قبض»', () => {
  // المخلّص ووكيل الشحن والناقل كانوا يُعامَلون عميلاً في كرتهم («سند قبض»).
  for (const type of ['Supplier', 'FreightForwarder', 'CustomsBroker', 'LocalTransporter', 'Carrier']) {
    assert.deepEqual(partnerVoucherDirections(type), { primary: 'payment', secondary: 'receipt' }, type);
  }
  assert.deepEqual(partnerVoucherDirections('Customer'), { primary: 'receipt', secondary: null });
  assert.equal(partnerVoucherDirections(''), null);
  assert.equal(partnerVoucherDirections('Unknown'), null);
});

test('الطرف الدائن: «سند قبض» خيارٌ ثانٍ صريح (استرداد) لا الزرّ الافتراضي', () => {
  const groups = partnerActionGroups({ id: '83', name: 'حاييم', kind: 'supplier' });
  const actions = groups.flatMap((g) => g.actions);
  const payment = actions.findIndex((a) => a.key === 'payment');
  const refund = actions.findIndex((a) => a.key === 'refund-receipt');
  assert.ok(payment >= 0 && refund > payment);
  assert.equal(actions[refund].bridge, 'receipt');
  assert.match(actions[refund].label, /استرداد/);
});

test('تسمية نوع الطرف بالعربية — والنوع المجهول يُعرض كما هو', () => {
  assert.equal(partnerTypeLabel('CustomsBroker'), 'مخلّص جمركي');
  assert.equal(partnerTypeLabel('FreightForwarder'), 'وكيل شحن');
  assert.equal(partnerTypeLabel('Customer'), 'عميل');
  assert.equal(partnerTypeLabel('Other'), 'Other');
  assert.equal(partnerTypeLabel(null), '');
});

test('الروابط تُعبَّأ بمعرّف الطرف كي يفتح المستند جاهزاً', () => {
  const groups = partnerActionGroups({ id: '7', name: 'زبون', kind: 'customer' });
  const byKey = new Map(groups.flatMap((g) => g.actions.map((a) => [a.key, a])));
  assert.equal(byKey.get('card')?.href, '/partners/7');
  assert.equal(byKey.get('sales-invoice')?.href, '/sales/invoices/new?customer_id=7');
  assert.equal(byKey.get('statement')?.href, '/partners/7?tab=statement');
  // سند القبض ليس رابطاً — يفتح مودالاً عبر جسر الجلسة.
  assert.equal(byKey.get('receipt')?.href, undefined);
  assert.equal(byKey.get('receipt')?.bridge, 'receipt');
});

test('الإجراءات مجمَّعة بعناوين — قائمة مسطّحة طويلة لا تُقرأ', () => {
  const groups = partnerActionGroups({ id: '1', name: '', kind: 'customer' });
  assert.ok(groups.length >= 2);
  assert.ok(groups.every((g) => g.title.length > 0));
  assert.ok(groups.every((g) => g.actions.length > 0));
  // بلا اسم: البطاقة تبقى مسمّاة بلا «: » معلّقة.
  const card = groups[0].actions.find((a) => a.key === 'card');
  assert.equal(card?.label, 'بطاقة العميل');
});

test("المخلّص/الوكيل/الناقل: سند صرف واسترداد — لا فاتورة شراء ولا عرض سعر شراء ولا «فواتيره»", () => {
  for (const partnerType of ["CustomsBroker", "FreightForwarder", "LocalTransporter", "Carrier"]) {
    const groups = partnerActionGroups({ id: "83", name: "حاييم", kind: "supplier", partnerType });
    const keys = groups.flatMap((g) => g.actions.map((a) => a.key));
    assert.ok(keys.includes("payment"), partnerType);
    assert.ok(keys.includes("refund-receipt"), partnerType);
    for (const hidden of ["purchase-invoice", "purchase-offer", "purchase-invoices"]) {
      assert.ok(!keys.includes(hidden), `${partnerType}: ${hidden}`);
    }
  }
  const broker = partnerActionGroups({ id: "83", name: "حاييم", kind: "supplier", partnerType: "CustomsBroker" });
  assert.equal(broker[0].actions[0].label, "بطاقة مخلّص جمركي: حاييم");
  // المورد نفسه — ومن لا يُعرف نوعه (القائمة العامّة) — كما كان.
  for (const partnerType of ["Supplier", undefined]) {
    const keys = partnerActionGroups({ id: "7", name: "مورد", kind: "supplier", partnerType })
      .flatMap((g) => g.actions.map((a) => a.key));
    assert.ok(keys.includes("purchase-invoice"));
  }
});
