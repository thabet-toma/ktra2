import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  availableForSale,
  buildReservationIndex,
  reservedSaleWarnings,
  totalReserved,
  type ReservationHold,
} from './reservedStock.ts';

const hold = (over: Partial<ReservationHold> = {}): ReservationHold => ({
  order_id: 1,
  order_number: 'SO-1',
  customer_id: 7,
  customer_name: 'صاحب الطلبية',
  product_id: 100,
  quantity: '8',
  ...over,
});

test('المحجوز يُجمَع لكل منتج مع أصحاب الحجز', () => {
  const index = buildReservationIndex([
    hold(),
    hold({ order_id: 2, order_number: 'SO-2', customer_id: 9, customer_name: 'زبون آخر', quantity: '2' }),
  ]);
  const entry = index.get(100)!;
  assert.equal(entry.reserved, 10);
  assert.equal(entry.ownReserved, 0);
  assert.deepEqual(entry.holders.map((h) => h.orderNumber), ['SO-1', 'SO-2']);
});

test('حجز الزبون نفسه لا يُطرح من متاحه — حجزُه لا يمنعه هو', () => {
  const index = buildReservationIndex([hold()], 7);
  const entry = index.get(100)!;
  assert.equal(entry.reserved, 0);
  assert.equal(entry.ownReserved, 8);
  assert.equal(totalReserved(entry), 8, 'يبقى الحجز ظاهراً في خانة «محجوز»');
  assert.deepEqual(entry.ownHolders.map((h) => h.orderNumber), ['SO-1']);
  assert.equal(availableForSale('10', entry), 10);
});

test('المتاح للبيع = الرصيد − محجوز الآخرين', () => {
  const index = buildReservationIndex([hold()], 9);
  assert.equal(availableForSale('10', index.get(100)), 2);
  assert.equal(availableForSale('10', undefined), 10, 'منتج بلا حجز = رصيده كلّه متاح');
});

test('تجاوز المتاح بعد الحجز يُنبِّه ويسمّي الطلبية الحاجزة', () => {
  const index = buildReservationIndex([hold()], 9);
  const warnings = reservedSaleWarnings(
    [{ productId: 100, quantity: '5', onHand: '10', name: 'منتج محجوز' }],
    index,
  );
  assert.equal(warnings.length, 1);
  assert.equal(warnings[0].available, 2);
  assert.equal(warnings[0].reserved, 8);
  assert.deepEqual(warnings[0].holders, ['SO-1 (صاحب الطلبية)']);
});

test('الكمية داخل المتاح لا تُنبِّه، ولا منتج بلا حجز', () => {
  const index = buildReservationIndex([hold()], 9);
  assert.deepEqual(
    reservedSaleWarnings([{ productId: 100, quantity: '2', onHand: '10', name: 'منتج محجوز' }], index),
    [],
  );
  assert.deepEqual(
    reservedSaleWarnings([{ productId: 200, quantity: '99', onHand: '1', name: 'منتج حر' }], index),
    [],
  );
});

test('سطران من نفس المنتج يزاحمان الحجز مجتمعَين', () => {
  const index = buildReservationIndex([hold()], 9);
  const warnings = reservedSaleWarnings([
    { productId: 100, quantity: '1', onHand: '10', name: 'منتج محجوز' },
    { productId: 100, quantity: '2', onHand: '10', name: 'منتج محجوز' },
  ], index);
  assert.equal(warnings.length, 1);
  assert.equal(warnings[0].quantity, 3);
});

test('الخدمة والمنتج المعفى خارج الحساب — كما في حارس الخادم', () => {
  const index = buildReservationIndex([hold()], 9);
  assert.deepEqual(
    reservedSaleWarnings(
      [{ productId: 100, quantity: '9', onHand: '10', name: 'خدمة', exempt: true }],
      index,
    ),
    [],
  );
});
