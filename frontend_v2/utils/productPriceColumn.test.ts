import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PRODUCT_PRICE_COLUMN_OPTIONS,
  productPriceColumnHint,
  productPriceColumnLabel,
  productPriceDetails,
  productPriceValue,
} from './productPriceColumn.ts';

const sample = {
  last_purchase_price: '40.0000',
  indicative_purchase_price: '20.0000',
  method_cost: '35.0000',
  inventory_avg_cost: '32.0000',
  standard_cost: '25.0000',
};

test('PRODUCT_PRICE_COLUMN_OPTIONS has the five options in order', () => {
  assert.deepEqual(PRODUCT_PRICE_COLUMN_OPTIONS, [
    {
      value: 'last_purchase',
      label: 'آخر سعر شراء',
      hint: 'آخر سعر شراء في فاتورة شراء مرحَّلة — لا متوسط التكلفة',
    },
    {
      value: 'lowest_purchase',
      label: 'أقلّ شراء (آخر ٥)',
      hint: 'أقلّ سعر شراء في آخر ٥ فواتير شراء مرحَّلة',
    },
    {
      value: 'method_cost',
      label: 'التكلفة حسب الطريقة المختارة',
      hint: 'التكلفة حسب طريقة تكلفة المبيعات المختارة في إعدادات المبيعات',
    },
    {
      value: 'inventory_avg',
      label: 'متوسط تكلفة المخزون',
      hint: 'قيمة المخزون المفتوح ÷ كميّته — لا متوسط التكلفة المخزَّن',
    },
    {
      value: 'standard',
      label: 'السعر الثابت',
      hint: 'السعر الثابت المسجَّل في بطاقة الصنف',
    },
  ]);
});

test('productPriceColumnHint returns hint per option and falls back to last_purchase', () => {
  assert.equal(
    productPriceColumnHint('last_purchase'),
    'آخر سعر شراء في فاتورة شراء مرحَّلة — لا متوسط التكلفة',
  );
  assert.equal(
    productPriceColumnHint('lowest_purchase'),
    'أقلّ سعر شراء في آخر ٥ فواتير شراء مرحَّلة',
  );
  assert.equal(
    productPriceColumnHint('method_cost'),
    'التكلفة حسب طريقة تكلفة المبيعات المختارة في إعدادات المبيعات',
  );
  assert.equal(
    productPriceColumnHint('inventory_avg'),
    'قيمة المخزون المفتوح ÷ كميّته — لا متوسط التكلفة المخزَّن',
  );
  assert.equal(
    productPriceColumnHint('standard'),
    'السعر الثابت المسجَّل في بطاقة الصنف',
  );
  assert.equal(
    productPriceColumnHint('unknown'),
    'آخر سعر شراء في فاتورة شراء مرحَّلة — لا متوسط التكلفة',
  );
  assert.equal(
    productPriceColumnHint(null),
    'آخر سعر شراء في فاتورة شراء مرحَّلة — لا متوسط التكلفة',
  );
  assert.equal(
    productPriceColumnHint(undefined),
    'آخر سعر شراء في فاتورة شراء مرحَّلة — لا متوسط التكلفة',
  );
});

test('productPriceColumnLabel returns label per option and falls back to last_purchase', () => {
  assert.equal(productPriceColumnLabel('last_purchase'), 'آخر سعر شراء');
  assert.equal(productPriceColumnLabel('lowest_purchase'), 'أقلّ شراء (آخر ٥)');
  assert.equal(productPriceColumnLabel('method_cost'), 'التكلفة حسب الطريقة المختارة');
  assert.equal(productPriceColumnLabel('inventory_avg'), 'متوسط تكلفة المخزون');
  assert.equal(productPriceColumnLabel('standard'), 'السعر الثابت');
  assert.equal(productPriceColumnLabel('unknown'), 'آخر سعر شراء');
  assert.equal(productPriceColumnLabel(null), 'آخر سعر شراء');
  assert.equal(productPriceColumnLabel(undefined), 'آخر سعر شراء');
});

test('productPriceValue returns value per option, falls back on unknown, and preserves null', () => {
  assert.equal(productPriceValue(sample, 'last_purchase'), '40.0000');
  assert.equal(productPriceValue(sample, 'lowest_purchase'), '20.0000');
  assert.equal(productPriceValue(sample, 'method_cost'), '35.0000');
  assert.equal(productPriceValue(sample, 'inventory_avg'), '32.0000');
  assert.equal(productPriceValue(sample, 'standard'), '25.0000');
  assert.equal(productPriceValue(sample, 'bogus'), '40.0000');

  const empty = {
    last_purchase_price: null,
    indicative_purchase_price: null,
    method_cost: null,
    inventory_avg_cost: null,
    standard_cost: null,
  };
  for (const opt of PRODUCT_PRICE_COLUMN_OPTIONS) {
    assert.equal(productPriceValue(empty, opt.value), null);
  }
});

test('productPriceDetails returns the other four options in order', () => {
  const details = productPriceDetails(sample, 'inventory_avg');
  assert.deepEqual(details, [
    { key: 'last_purchase', label: 'آخر سعر شراء', value: '40.0000' },
    { key: 'lowest_purchase', label: 'أقلّ شراء (آخر ٥)', value: '20.0000' },
    { key: 'method_cost', label: 'التكلفة حسب الطريقة المختارة', value: '35.0000' },
    { key: 'standard', label: 'السعر الثابت', value: '25.0000' },
  ]);

  const fallbackDetails = productPriceDetails(sample, 'unknown');
  assert.deepEqual(
    fallbackDetails.map((d) => d.key),
    ['lowest_purchase', 'method_cost', 'inventory_avg', 'standard'],
  );
});
