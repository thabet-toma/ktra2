import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatProductPrimaryName } from './productDisplayName.ts';

test('display_name القادم من الخادم يُقدَّم على كل شيء', () => {
  assert.equal(
    formatProductPrimaryName({ id: 1, display_name: '215/65/16 (دانتير ايكو جرين)' }),
    '215/65/16 (دانتير ايكو جرين)',
  );
});

test('بلا display_name: عربي وإنكليزي معاً يُدمجان بشرطة', () => {
  assert.equal(
    formatProductPrimaryName({ id: 2, name_ar: 'مضخة', name_en: 'Pump' }),
    'مضخة — Pump',
  );
});

test('بلا display_name: عربي وحده', () => {
  assert.equal(formatProductPrimaryName({ id: 3, name_ar: 'مضخة' }), 'مضخة');
});

test('بلا display_name ولا اسم عربي: إنكليزي', () => {
  assert.equal(formatProductPrimaryName({ id: 4, name_en: 'Pump' }), 'Pump');
});

test('بلا أي اسم: SKU', () => {
  assert.equal(formatProductPrimaryName({ id: 5, sku: 'SKU-9' }), 'SKU-9');
});

test('بلا اسم ولا SKU: رقم المنتج احتياطاً أخيراً', () => {
  assert.equal(formatProductPrimaryName({ id: 6 }), 'منتج #6');
});

test('حقول فارغة (سلاسل بيضاء) تُعامَل كغائبة', () => {
  assert.equal(
    formatProductPrimaryName({ id: 7, name_ar: '   ', name_en: '', sku: 'SKU-7' }),
    'SKU-7',
  );
});
