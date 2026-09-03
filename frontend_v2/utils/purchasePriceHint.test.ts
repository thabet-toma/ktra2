import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildPurchasePriceHintChip,
  buildPurchasePriceHintChips,
  computeDeltaPercent,
  formatLowestPurchaseHint,
  type PurchasePriceListEntry,
} from './purchasePriceHint.ts';

const lastEntry: PurchasePriceListEntry = {
  source_label: 'آخر شراء',
  unit_price: '12.0000',
  document_id: 101,
  document_number: 'PINV-0101',
  document_date: '2026-08-01',
};

const lowestEntry: PurchasePriceListEntry = {
  source_label: 'أقل شراء',
  unit_price: '45.2000',
  document_id: 55,
  document_number: 'PINV-0055',
  document_date: '2026-07-15',
  supplier_id: 9,
  supplier_name: 'شركة الأمل',
};

test('«آخر شراء» يبقى بلا علامة عملة أساسية — عملة السطر كما سُجّلت', () => {
  const chip = buildPurchasePriceHintChip(lastEntry);
  assert.equal(chip.label, 'آخر شراء');
  assert.equal(chip.isBaseCurrency, false);
  assert.equal(chip.supplierName, null);
});

test('«أقل شراء» يحمل علامة صريحة أنه بالعملة الأساسية — لا رقم غامض بجانب آخر شراء', () => {
  const chip = buildPurchasePriceHintChip(lowestEntry);
  assert.equal(chip.label, 'أقل شراء (بالعملة الأساسية)');
  assert.equal(chip.isBaseCurrency, true);
  assert.equal(chip.supplierName, 'شركة الأمل');
  assert.equal(chip.documentDate, '2026-07-15');
});

test('العلامة لا تتكرر إن كانت التسمية تحملها فعلاً من الخادم', () => {
  const chip = buildPurchasePriceHintChip({
    ...lowestEntry,
    source_label: 'أقل شراء (بالعملة الأساسية)',
  });
  assert.equal(chip.label, 'أقل شراء (بالعملة الأساسية)');
});

test('القيمة تمرّ عبر formatMoney لا toFixed — تجميع آلاف بلا كسور صفرية', () => {
  const chip = buildPurchasePriceHintChip({ ...lowestEntry, unit_price: '1234.5000' });
  assert.equal(chip.value, '1,234.5');
});

test('الرابط يُبنى فقط حين تُمرَّر دالّة الربط، ويحمل معرّف المستند', () => {
  const withLink = buildPurchasePriceHintChip(lowestEntry, {
    invoiceLink: (id) => `/purchase-invoices/${id}`,
  });
  assert.equal(withLink.link, '/purchase-invoices/55');
  const withoutLink = buildPurchasePriceHintChip(lowestEntry);
  assert.equal(withoutLink.link, null);
});

test('buildPurchasePriceHintChips يبني آخر وأقل شراء معاً بنفس الترتيب المُستلَم', () => {
  const chips = buildPurchasePriceHintChips([lastEntry, lowestEntry]);
  assert.equal(chips.length, 2);
  assert.equal(chips[0].isBaseCurrency, false);
  assert.equal(chips[1].isBaseCurrency, true);
});

test('buildPurchasePriceHintChips يعيد مصفوفة فارغة بلا رمي على undefined/null', () => {
  assert.deepEqual(buildPurchasePriceHintChips(undefined), []);
  assert.deepEqual(buildPurchasePriceHintChips(null), []);
});

test('formatLowestPurchaseHint يحمل المورد والتاريخ معاً — لا رقم عارٍ', () => {
  const text = formatLowestPurchaseHint([lastEntry, lowestEntry]);
  assert.equal(text, 'أقل شراء (بالعملة الأساسية): 45.2 — شركة الأمل — 2026-07-15');
});

test('formatLowestPurchaseHint يعيد null بلا «أقل شراء» في القائمة', () => {
  assert.equal(formatLowestPurchaseHint([lastEntry]), null);
  assert.equal(formatLowestPurchaseHint([]), null);
  assert.equal(formatLowestPurchaseHint(undefined), null);
});

test('computeDeltaPercent موجب حين سعر المورد أعلى من أقل سعر', () => {
  assert.equal(computeDeltaPercent(55, 50), 10);
});

test('computeDeltaPercent صفر أو سالب حين المورد يساوي أو أرخص من أقل سعر', () => {
  assert.equal(computeDeltaPercent(50, 50), 0);
  assert.equal(computeDeltaPercent(45, 50), -10);
});

test('computeDeltaPercent يعيد null بلا أساس مقارنة — لا مقارنة مُختلَقة', () => {
  assert.equal(computeDeltaPercent(55, null), null);
  assert.equal(computeDeltaPercent(55, undefined), null);
  assert.equal(computeDeltaPercent(55, 0), null);
  assert.equal(computeDeltaPercent(NaN, 50), null);
});
