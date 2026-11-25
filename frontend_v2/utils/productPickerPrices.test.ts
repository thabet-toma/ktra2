import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  pickSalesPickerPrices,
  pickPurchasePickerPrices,
  type CustomerPriceEntry,
} from './productPickerPrices.ts';

test('pickSalesPickerPrices يُبقي «آخر» فقط من قائمة الأسعار ويُسقط card وlowest وquote', () => {
  const prices: CustomerPriceEntry[] = [
    { kind: 'last', label: 'آخر فاتورة', unit_price: '120.5000', source_type: 'SALES_INVOICE', document_id: 42 },
    { kind: 'lowest', label: 'أقل سعر', unit_price: '80.0000', source_type: 'SALES_INVOICE', document_id: 11 },
    { kind: 'quote', label: 'عرض السعر', unit_price: '100.0000', source_type: 'QUOTE', document_id: 7 },
    { kind: 'card', label: 'سعر عام (كرت المنتج)', unit_price: '150.0000', source_type: 'PRODUCT', document_id: null },
  ];

  const open = pickSalesPickerPrices(prices, '75.2500', true, 'أقل شراء (آخر ٥)');
  assert.deepEqual(open, {
    lowestPurchase: { label: 'أقل شراء (آخر ٥)', value: '75.25' },
    last: { label: 'آخر', value: '120.5', link: '/sales/invoices/42', isEmpty: false },
  });
});

test('pickSalesPickerPrices يسقط card وquote عند عميل جديد ويُرجع «آخر —»', () => {
  const onlyCardAndQuote: CustomerPriceEntry[] = [
    { kind: 'quote', label: 'عرض السعر', unit_price: '100.0000', source_type: 'QUOTE', document_id: 7 },
    { kind: 'card', label: 'سعر عام (كرت المنتج)', unit_price: '150.0000', source_type: 'PRODUCT', document_id: null },
  ];

  const open = pickSalesPickerPrices(onlyCardAndQuote, '60.0000', true);
  assert.deepEqual(open, {
    lowestPurchase: { label: 'أقل شراء (آخر ٥)', value: '60' },
    last: { label: 'آخر', value: '—', isEmpty: true },
  });

  // تسمية الخادم فارغة ⇒ الثابت الاحتياطي
  const noPrices = pickSalesPickerPrices(undefined, null, true, '');
  assert.deepEqual(noPrices, {
    lowestPurchase: { label: 'أقل شراء (آخر ٥)', value: '—' },
    last: { label: 'آخر', value: '—', isEmpty: true },
  });
});

test('pickSalesPickerPrices يعرض تسمية «أقل شراء» من الخادم بحرفها (حجم النافذة منه لا ثابتاً محلياً)', () => {
  const res = pickSalesPickerPrices([], '75.2500', true, 'أقل شراء (آخر ١٠)');
  assert.deepEqual(res.lowestPurchase, { label: 'أقل شراء (آخر ١٠)', value: '75.25' });

  const nullLabel = pickSalesPickerPrices([], '75.2500', true, null);
  assert.deepEqual(nullLabel.lowestPurchase, { label: 'أقل شراء (آخر ٥)', value: '75.25' });
});

test('pickSalesPickerPrices مع زرّ العين مغلقاً لا يُرجع مفتاح lowestPurchase إطلاقاً', () => {
  const prices: CustomerPriceEntry[] = [
    { kind: 'last', label: 'آخر فاتورة', unit_price: '120.5000', source_type: 'SALES_INVOICE', document_id: 42 },
  ];
  const closed = pickSalesPickerPrices(prices, '75.2500', false);
  assert.equal('lowestPurchase' in closed, false);
  assert.equal(closed.lowestPurchase, undefined);
  assert.deepEqual(closed.last, {
    label: 'آخر',
    value: '120.5',
    link: '/sales/invoices/42',
    isEmpty: false,
  });
});

test('pickSalesPickerPrices لا يفلتر على النص العربي بل على kind', () => {
  // حتى لو حمل العنصر تسمية عربية مشابهة لـ«آخر فاتورة» لكن kind=card، لا يُقبل
  const spoofed: CustomerPriceEntry[] = [
    { kind: 'card', label: 'آخر فاتورة', unit_price: '999.0000', source_type: 'PRODUCT', document_id: null },
  ];
  const res = pickSalesPickerPrices(spoofed, null, false);
  assert.deepEqual(res.last, { label: 'آخر', value: '—', isEmpty: true });
});

test('pickPurchasePickerPrices يُبقي «آخر شراء» من المورد فقط ويُسقط «أقل شراء» و«متوسط التكلفة»', () => {
  const entries = [
    { kind: 'last' as const, source_label: 'آخر شراء من المورد', unit_price: '48.5000', source_type: 'PURCHASE_INVOICE', document_id: 91 },
    { kind: 'lowest' as const, source_label: 'أقل شراء (آخر ٥)', unit_price: '35.0000', source_type: 'PURCHASE_INVOICE', document_id: 50 },
  ];
  const res = pickPurchasePickerPrices(entries, true, {
    invoiceLink: (id) => `/purchase-invoices/${id}`,
  });
  assert.deepEqual(res, {
    label: 'آخر شراء',
    value: '48.5',
    link: '/purchase-invoices/91',
    isEmpty: false,
  });
});

test('pickPurchasePickerPrices يفلتر على kind لا على النص العربي', () => {
  // تسمية توحي بـ«آخر شراء من المورد» لكن kind=lowest ⇒ يُسقط ويعيد «آخر —»
  const spoofedLowest = [
    { kind: 'lowest' as const, source_label: 'آخر شراء من المورد', unit_price: '35.0000', source_type: 'PURCHASE_INVOICE', document_id: 50 },
  ];
  assert.deepEqual(pickPurchasePickerPrices(spoofedLowest, true), {
    label: 'آخر',
    value: '—',
    isEmpty: true,
  });

  // تسمية غير اعتيادية لكن kind=last ⇒ تُؤخذ قيمتها
  const unusualLast = [
    { kind: 'last' as const, source_label: 'تسمية غير معتادة', unit_price: '63.2500', source_type: 'PURCHASE_INVOICE', document_id: 77 },
  ];
  assert.deepEqual(pickPurchasePickerPrices(unusualLast, true), {
    label: 'آخر شراء',
    value: '63.25',
    isEmpty: false,
  });
});

test('pickPurchasePickerPrices يرجع «آخر —» عند غياب شراء سابق من المورد أو وجود متوسط تكلفة فقط أو بلا مورد', () => {
  const onlyLowestAndAvg = [
    { kind: 'lowest' as const, source_label: 'أقل شراء (آخر ٥)', unit_price: '35.0000', source_type: 'PURCHASE_INVOICE', document_id: 50 },
    { kind: 'avg_cost' as const, source_label: 'متوسط التكلفة', unit_price: '40.0000', source_type: 'PRODUCT_AVG_COST', document_id: null },
  ];
  assert.deepEqual(pickPurchasePickerPrices(onlyLowestAndAvg, true), {
    label: 'آخر',
    value: '—',
    isEmpty: true,
  });

  assert.deepEqual(pickPurchasePickerPrices(undefined, true), {
    label: 'آخر',
    value: '—',
    isEmpty: true,
  });

  // بلا مورد مختار على الفاتورة: لا يُعرض سعر مورد آخر
  const withLast = [
    { kind: 'last' as const, source_label: 'آخر شراء', unit_price: '48.5000', source_type: 'PURCHASE_INVOICE', document_id: 91 },
  ];
  assert.deepEqual(pickPurchasePickerPrices(withLast, false), {
    label: 'آخر',
    value: '—',
    isEmpty: true,
  });
});
