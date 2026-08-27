import { test } from 'node:test';
import assert from 'node:assert/strict';
import { quotationToDraftDeal, type DraftDealSupplierRef } from './quotationToDraftDeal.ts';

type Quotation = Parameters<typeof quotationToDraftDeal>[0];

/** عرض استيراد مقبول بمورد مسجَّل وبندين مربوطين — الحالة العادية. */
const baseQuotation = (over: Partial<Quotation> = {}): Quotation => ({
  id: 12,
  scope: 'import',
  quotation_number: 'IQ-0007',
  supplier: 5,
  supplier_name: 'Ningbo Tools Co',
  quotation_date: '2026-03-11',
  status: 'accepted',
  currency: 3,
  exchange_rate: '3.65',
  subtotal: '1000.00',
  discount_amount: '50.00',
  tax_rate: '0.00',
  tax_amount: '0.00',
  grand_total: '1070.00',
  shipping_cost_estimate: '120.00',
  is_shipping_included: false,
  incoterms: 'CIF',
  shipping_method: 'Sea',
  payment_method: 'T/T',
  production_days: 25,
  delivery_days: 40,
  total_cbm: '4.500',
  total_weight_kg: '820.000',
  notes: 'ملاحظات المورد',
  alibaba_link: 'https://alibaba.example/order/9',
  lines: [
    {
      id: 41, product: 77, product_name: 'مفك كهربائي', seq: 1,
      name_snapshot: 'مفك', description_line: 'أزرق 18 فولت',
      quantity: '10.000', unit_price: '60.00', line_total: '600.00',
    },
    {
      id: 42, product: 78, product_name: 'صندوق عدّة', seq: 2,
      name_snapshot: 'صندوق', description_line: '',
      quantity: '8.000', unit_price: '50.00', line_total: '400.00',
    },
  ],
  ...over,
});

const suppliers: DraftDealSupplierRef[] = [
  { id: '5', name: 'Ningbo Tools Co' },
  { id: '9', name: 'Shenzhen Lighting', alias: 'شنتشن للإنارة' },
];

test('المورد المسجَّل يُنقل بمعرّفه واسمه', () => {
  const draft = quotationToDraftDeal(baseQuotation(), suppliers);
  assert.equal(draft.supplierId, '5');
  assert.equal(draft.factoryName, 'Ningbo Tools Co');
  assert.equal(draft.sourceQuotationId, '12');
  assert.equal(draft.priceOfferId, '12');
  assert.equal(draft.originalOfferNumber, 'IQ-0007');
  assert.equal(draft.dealDescription, 'طلبية من عرض سعر IQ-0007');
  assert.equal(draft.dealDate, '2026-03-11');
});

test('المورد المبدئي المطابق تماماً يُختار سلفاً — والمطابقة على الاسم البديل أيضاً', () => {
  const byName = quotationToDraftDeal(
    baseQuotation({ supplier: null, supplier_draft_name: '  Shenzhen Lighting ' }),
    suppliers,
  );
  assert.equal(byName.supplierId, '9');
  assert.equal(byName.factoryName, 'Shenzhen Lighting');

  const byAlias = quotationToDraftDeal(
    baseQuotation({ supplier: null, supplier_draft_name: 'شنتشن للإنارة' }),
    suppliers,
  );
  assert.equal(byAlias.supplierId, '9');
});

test('المورد المبدئي بلا مطابقة يصل بلا معرّف — الاسم فقط، والقرار للمستخدم', () => {
  const draft = quotationToDraftDeal(
    baseQuotation({ supplier: null, supplier_draft_name: 'مصنع لم يُسجَّل بعد' }),
    suppliers,
  );
  assert.equal(draft.supplierId, '');
  assert.equal(draft.factoryName, 'مصنع لم يُسجَّل بعد');
});

test('المطابقة تامّة لا تقريبية — اسم قريب لا يُختار', () => {
  const draft = quotationToDraftDeal(
    baseQuotation({ supplier: null, supplier_draft_name: 'Ningbo Tools' }),
    suppliers,
  );
  assert.equal(draft.supplierId, '');
});

test('البند المكتوب يدوياً يصل بلا منتج مربوط — لا يُنشأ منتج نيابةً عن المستخدم', () => {
  const draft = quotationToDraftDeal(
    baseQuotation({
      lines: [
        {
          id: 51, product: null, seq: 1, name_snapshot: 'قاطع ليزر',
          description_line: 'من رسالة المورد', quantity: '2.000', unit_price: '900.00',
        },
        {
          id: 52, product: 77, product_name: 'مفك كهربائي', seq: 2,
          name_snapshot: 'مفك', quantity: '1.000', unit_price: '60.00',
        },
      ],
    }),
    suppliers,
  );
  const items = draft.items || [];
  assert.equal(items.length, 2);
  assert.equal(items[0].itemId, '');
  assert.equal(items[0].name, 'قاطع ليزر');
  assert.equal(items[0].specifications, 'من رسالة المورد');
  assert.equal(items[0].quantity, 2);
  assert.equal(items[0].unitPrice, 900);
  assert.equal(items[0].totalPrice, 1800);
  assert.equal(items[0].seq, 1);
  assert.equal(items[1].itemId, '77');
  assert.equal(items[1].name, 'مفك كهربائي');
  // معرّف الصف غير رقمي كي لا يُرسَل كمعرّف بند صفقة قائم عند الحفظ
  assert.equal(/^\d+$/.test(items[0].id), false);
});

test('العملة والشحن والإجماليات تُحمل كما هي من العرض', () => {
  const draft = quotationToDraftDeal(baseQuotation(), suppliers);
  assert.equal(draft.currencyId, 3);
  assert.equal(draft.currencyRate, 3.65);
  assert.equal(draft.incoterms, 'CIF');
  assert.equal(draft.shippingMethod, 'Sea');
  assert.equal(draft.paymentMethod, 'T/T');
  assert.equal(draft.shippingCost, 120);
  assert.equal(draft.shippingIncluded, false);
  assert.equal(draft.discountAmount, 50);
  assert.equal(draft.subtotal, 1000);
  assert.equal(draft.totalAmount, 1070);
  assert.equal(draft.remainingAmount, 1070);
  assert.equal(draft.totalVolume, 4.5);
  assert.equal(draft.totalWeightKg, 820);
  assert.equal(draft.productionDays, 25);
  assert.equal(draft.deliveryDays, 40);
  assert.equal(draft.internalNotes, 'ملاحظات المورد');
  assert.equal(draft.alibabaOrderLink, 'https://alibaba.example/order/9');
  // الصفقة الدولية بلا ضريبة — تُدفع عند التخليص
  assert.equal(draft.taxRate, 0);
  assert.equal(draft.taxAmount, 0);
});

test('المسودة لا تحمل أي معرّف صفقة ولا دفعات — لا شيء أُنشئ بعد', () => {
  const draft = quotationToDraftDeal(baseQuotation(), suppliers);
  assert.equal(draft.id, undefined);
  assert.equal(draft.dealNumber, undefined);
  assert.deepEqual(draft.payments, []);
  assert.deepEqual(draft.installments, []);
  assert.equal(draft.installmentPlanEnabled, false);
  assert.equal(draft.status, 'initial');
});
