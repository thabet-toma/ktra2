import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_TERMS, resolveTerm } from './terms.ts';

test('مفتاح موجود في حمولة الخادم يفوز', () => {
  assert.equal(resolveTerm({ 'doc.sales_invoice': 'فاتورة أتعاب' }, 'doc.sales_invoice'), 'فاتورة أتعاب');
});

test('مفتاح غائب عن حمولة الخادم يسقط للافتراضي المحلي', () => {
  assert.equal(resolveTerm({}, 'doc.sales_invoice'), DEFAULT_TERMS['doc.sales_invoice']);
});

test('بلا حمولة خادم إطلاقاً (أول رسمة) يسقط للافتراضي المحلي', () => {
  assert.equal(resolveTerm(undefined, 'line.item'), DEFAULT_TERMS['line.item']);
});

test('مفتاح مجهول كلياً يسقط للمفتاح نفسه بلا رمي', () => {
  assert.equal(resolveTerm({}, 'doc.no-such-term'), 'doc.no-such-term');
});

test('general — الافتراضي بلا أي تغيير', () => {
  const generalTerms = { 'doc.sales_invoice': 'فاتورة مبيعات', 'line.item': 'منتج' };
  assert.equal(resolveTerm(generalTerms, 'doc.sales_invoice'), 'فاتورة مبيعات');
  assert.equal(resolveTerm(generalTerms, 'line.item'), 'منتج');
});

test('accounting_firm — فاتورة أتعاب وخدمة', () => {
  const firmTerms = { 'doc.sales_invoice': 'فاتورة أتعاب', 'line.item': 'خدمة' };
  assert.equal(resolveTerm(firmTerms, 'doc.sales_invoice'), 'فاتورة أتعاب');
  assert.equal(resolveTerm(firmTerms, 'line.item'), 'خدمة');
});
