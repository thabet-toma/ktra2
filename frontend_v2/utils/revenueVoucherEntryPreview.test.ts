import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildRevenueVoucherEntryPreview,
  revenueVoucherRequiresCashAccount,
  TRADE_RECEIVABLES_LABEL,
  VAT_OUTPUT_LABEL,
} from './revenueVoucherEntryPreview.ts';

// المعيار الحاسم لسند الإيراد: الاتجاه **معكوس** عن سند المصروف. الخطأ الذي
// يحرسه هذا الملف هو أن تُنسخ مرآةُ #56 بلا قلبِ المدين والدائن، فيُقيَّد
// الإيراد كمصروف ويظهر ربحاً سالباً في قائمة الدخل.

test('الصندوق مدينٌ وحساب الإيراد دائن — لا العكس', () => {
  const lines = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: '4210 عمولات',
    amount: 500,
    paymentMethod: 'cash',
    cashAccountLabel: '1101 النقدية',
  });
  assert.deepEqual(lines, [
    { side: 'Dr', label: '1101 النقدية', amount: 500 },
    { side: 'Cr', label: '4210 عمولات', amount: 500 },
  ]);
});

test('الضريبة تُقتطع من المبلغ لا تُضاف عليه، ودائنةٌ مع الإيراد', () => {
  const lines = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: '4210 عمولات',
    amount: 116,
    taxAmount: 16,
    paymentMethod: 'cash',
    cashAccountLabel: '1101 النقدية',
  });
  assert.deepEqual(lines, [
    { side: 'Dr', label: '1101 النقدية', amount: 116 },
    { side: 'Cr', label: '4210 عمولات', amount: 100 },
    { side: 'Cr', label: VAT_OUTPUT_LABEL, amount: 16 },
  ]);
});

test('«على الحساب» بلا دافعٍ مسمّى يقع على المدينين', () => {
  const lines = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: '4210 عمولات',
    amount: 300,
    paymentMethod: 'on_account',
  });
  assert.equal(lines[0].side, 'Dr');
  assert.equal(lines[0].label, TRADE_RECEIVABLES_LABEL);
});

test('«على الحساب» بدافعٍ مسمّى يذكره باسمه', () => {
  const lines = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: '4210 عمولات',
    amount: 300,
    paymentMethod: 'on_account',
    payerLabel: 'شركة الأفق',
  });
  assert.equal(lines[0].label, 'شركة الأفق');
});

test('الشيك يقع على «برسم التحصيل» لا «برسم الدفع»', () => {
  const lines = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: '4210 عمولات',
    amount: 300,
    paymentMethod: 'cheque',
  });
  assert.equal(lines[0].label, 'شيكات برسم التحصيل');
});

test('الضريبة تُقصّ إلى [0, amount] فلا يخرج سطرٌ سالب', () => {
  const over = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: 'x', amount: 100, taxAmount: 500, paymentMethod: 'cash',
  });
  assert.equal(over.filter((l) => l.amount < 0).length, 0);
  assert.equal(over.find((l) => l.label === VAT_OUTPUT_LABEL)?.amount, 100);

  const negative = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: 'x', amount: 100, taxAmount: -5, paymentMethod: 'cash',
  });
  assert.equal(negative.some((l) => l.label === VAT_OUTPUT_LABEL), false);
});

test('مبلغٌ غير موجب لا ينتج قيداً', () => {
  assert.deepEqual(
    buildRevenueVoucherEntryPreview({ revenueAccountLabel: 'x', amount: 0, paymentMethod: 'cash' }),
    [],
  );
});

test('حقل الصندوق مطلوبٌ للنقد وحده', () => {
  assert.equal(revenueVoucherRequiresCashAccount('cash'), true);
  assert.equal(revenueVoucherRequiresCashAccount('cheque'), false);
  assert.equal(revenueVoucherRequiresCashAccount('on_account'), false);
});
