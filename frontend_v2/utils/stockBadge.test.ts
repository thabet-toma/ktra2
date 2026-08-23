import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  availableOf,
  needsAlternative,
  stockAlternatives,
  stockBadgeFor,
} from './stockBadge.ts';

const item = (over: Record<string, unknown> = {}) => ({
  id: 1, stock_status: 'in_stock', quantity_on_hand: '10', ...over,
} as any);

test('الشارة تتبع حالة الخادم ولا تُعيد حسابها', () => {
  assert.equal(stockBadgeFor(item({ stock_status: 'out_of_stock' }))?.text, 'نفذ');
  assert.equal(stockBadgeFor(item({ stock_status: 'out_of_stock' }))?.tone, 'danger');
  assert.equal(stockBadgeFor(item({ stock_status: 'low_stock' }))?.text, 'منخفض');
  assert.equal(stockBadgeFor(item({ stock_status: 'low_stock' }))?.tone, 'warn');
  assert.equal(stockBadgeFor(item()), undefined);
});

test('الخدمة بلا شارة — «نفذ» على بند خدمة إنذار كاذب', () => {
  assert.equal(stockBadgeFor(item({ is_service: true, stock_status: 'out_of_stock' })), undefined);
  assert.equal(needsAlternative(item({ is_service: true, stock_status: 'out_of_stock' })), false);
});

test('المتاح يسبق الرصيد حين يرسله الخادم', () => {
  assert.equal(availableOf(item({ quantity_on_hand: '10', available_quantity: '4' })), 4);
  assert.equal(availableOf(item({ quantity_on_hand: '10' })), 10);
  assert.equal(availableOf(item({ quantity_on_hand: null })), 0);
});

test('البدائل من نفس النوع فقط، وعليها رصيد، والأوفر أولاً', () => {
  const all = [
    item({ id: 1, group_key: '205/65/16', stock_status: 'out_of_stock', quantity_on_hand: '0' }),
    item({ id: 2, group_key: '205/65/16', quantity_on_hand: '12' }),
    item({ id: 3, group_key: '205/65/16', quantity_on_hand: '40' }),
    item({ id: 4, group_key: '205/65/16', quantity_on_hand: '0' }),
    item({ id: 5, group_key: '195/65/15', quantity_on_hand: '99' }),
  ];
  const alts = stockAlternatives(all, all[0]);
  assert.deepEqual(alts.map((a) => a.id), [3, 2]);
});

test('صنف بلا نوع بلا بدائل — لا تخمين من تشابه الأسماء', () => {
  const all = [
    item({ id: 1, group_key: '', stock_status: 'out_of_stock', quantity_on_hand: '0' }),
    item({ id: 2, group_key: '', quantity_on_hand: '30' }),
  ];
  assert.deepEqual(stockAlternatives(all, all[0]), []);
});
