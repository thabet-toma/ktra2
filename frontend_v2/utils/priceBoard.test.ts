import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  bestOffer,
  cheapestSupplierIds,
  isHttpUrl,
  offersForItem,
  parseAmount,
  parseCellInput,
  parsePastedItems,
  rankOffers,
  searchBoard,
  spreadPercent,
  supplierRankInItem,
  winsPerSupplier,
} from './priceBoard.ts';

const price = (item: number, board_supplier: number, unit_price: string, unit_price_base: string | null) => ({
  item, board_supplier, unit_price, unit_price_base,
});

test('الأرخص يُقرَّر على سعر الأساس لا على السعر الخام', () => {
  // المورد 1 بالـCNY: 36.5 خام لكنه 5.04 أساس؛ المورد 2 بالـUSD: 5.4 خام وأساس.
  const offers = [price(1, 1, '36.5', '5.037'), price(1, 2, '5.4', '5.4')];
  assert.deepEqual([...cheapestSupplierIds(offers)], [1]);
  assert.equal(bestOffer(offers)?.offer.board_supplier, 1);
});

test('تعادل الأرخص: كلا المتعادلين مظلَّل وترتيبهما 1 والتالي 3', () => {
  const offers = [price(1, 1, '5', '5'), price(1, 2, '5.00', '5.0000'), price(1, 3, '7', '7')];
  assert.deepEqual([...cheapestSupplierIds(offers)].sort(), [1, 2]);
  assert.deepEqual(rankOffers(offers).map((r) => r.rank), [1, 1, 3]);
});

test('صنف بلا عروض: لا أرخص ولا أفضل عرض ولا فرق', () => {
  assert.equal(cheapestSupplierIds([]).size, 0);
  assert.equal(bestOffer([]), null);
  assert.equal(spreadPercent([]), null);
});

test('عرض وحيد لا يُظلَّل (يلزم عرضان) لكنه يظهر في الخلاصة', () => {
  const offers = [price(1, 1, '5', '5')];
  assert.equal(cheapestSupplierIds(offers).size, 0);
  assert.equal(bestOffer(offers)?.base, 5);
  assert.equal(spreadPercent(offers), null);
});

test('سعر بلا قيمة أساس يُستبعد من الترتيب ولا يكسره', () => {
  const offers = [price(1, 1, '3', null), price(1, 2, '5', '5'), price(1, 3, '6', '6')];
  assert.deepEqual([...cheapestSupplierIds(offers)], [2]);
  assert.equal(offersForItem(offers, 1).length, 2);
});

test('spreadPercent: الأغلى فوق الأرخص بنسبة مقرَّبة، وصفر الأرخص بلا نسبة', () => {
  assert.equal(spreadPercent([price(1, 1, '', '4'), price(1, 2, '', '5')]), 25);
  assert.equal(spreadPercent([price(1, 1, '', '0'), price(1, 2, '', '5')]), null);
});

test('winsPerSupplier: يعدّ الأصناف المقارَنة فقط، والتعادل يحسب للجميع', () => {
  const prices = [
    price(1, 1, '', '4'), price(1, 2, '', '5'),   // المورد 1
    price(2, 1, '', '9'), price(2, 2, '', '9'),   // تعادل: كلاهما
    price(3, 2, '', '1'),                         // عرض وحيد: لا يُحسب
  ];
  const wins = winsPerSupplier([1, 2, 3], prices);
  assert.equal(wins.get(1), 2);
  assert.equal(wins.get(2), 1);
});

test('supplierRankInItem: الترتيب من العدد، وnull لمن لم يعرض', () => {
  const prices = [price(1, 1, '', '4'), price(1, 2, '', '5'), price(1, 3, '', '6')];
  assert.deepEqual(supplierRankInItem(prices, 1, 2), { rank: 2, total: 3 });
  assert.equal(supplierRankInItem(prices, 1, 9), null);
  assert.equal(supplierRankInItem(prices, 7, 1), null);
});

test('parseAmount: نصوص الخادم العشرية فقط', () => {
  assert.equal(parseAmount('5.4000'), 5.4);
  assert.equal(parseAmount(''), null);
  assert.equal(parseAmount(null), null);
  assert.equal(parseAmount('abc'), null);
});

test('parsePastedItems: أول خلية، قصّ، وتجاهل المكرَّر بلا حساسية للحالة', () => {
  const text = '  Tile A \t12\r\nTILE a\n\nBasin\tx\nbasin\nMixer';
  const { names, duplicates } = parsePastedItems(text, ['mixer ']);
  assert.deepEqual(names, ['Tile A', 'Basin']);
  assert.equal(duplicates, 3);
});

test('parseCellInput: سعر، سعر وملاحظة، فارغ=حذف، وغير صالح', () => {
  assert.deepEqual(parseCellInput('4.2, MOQ 500'), { kind: 'set', price: '4.2', note: 'MOQ 500' });
  assert.deepEqual(parseCellInput('٤٫٢،درجة أولى'), { kind: 'set', price: '4.2', note: 'درجة أولى' });
  assert.deepEqual(parseCellInput(' 7 '), { kind: 'set', price: '7', note: '' });
  assert.deepEqual(parseCellInput('   '), { kind: 'delete' });
  assert.deepEqual(parseCellInput('abc'), { kind: 'invalid' });
  assert.deepEqual(parseCellInput('1.2.3'), { kind: 'invalid' });
  assert.deepEqual(parseCellInput(', note'), { kind: 'invalid' });
});

test('parseCellInput: فاصلة الآلاف لا تُقرأ فاصلَ ملاحظة فتقصّ السعر بصمت', () => {
  assert.deepEqual(parseCellInput('1,180'), { kind: 'set', price: '1180', note: '' });
  assert.deepEqual(parseCellInput('1,180.5, MOQ 10'), { kind: 'set', price: '1180.5', note: 'MOQ 10' });
  assert.deepEqual(parseCellInput('١,١٨٠'), { kind: 'set', price: '1180', note: '' });
  // فاصلة يليها رقمٌ مباشرة ولا تشكّل آلافاً سليمة: ملتبسة ← تُرفض لا تُخمَّن.
  assert.deepEqual(parseCellInput('12,500 pcs'), { kind: 'invalid' });
  assert.deepEqual(parseCellInput('4.2,500'), { kind: 'invalid' });
  // فاصلةٌ ثم مسافة ثم رقم = ملاحظة صريحة.
  assert.deepEqual(parseCellInput('4.2, 500 pcs'), { kind: 'set', price: '4.2', note: '500 pcs' });
});

test('isHttpUrl: http/https فقط', () => {
  assert.equal(isHttpUrl('https://drive.google.com/x'), true);
  assert.equal(isHttpUrl('HTTP://a.b'), true);
  assert.equal(isHttpUrl('javascript:alert(1)'), false);
  assert.equal(isHttpUrl('drive.google.com'), false);
  assert.equal(isHttpUrl('https://a b'), false);
});

test('searchBoard: صفّ يبقى بمطابقة اسمه أو بسعر مورّد مطابق، والفلتر يُخفي الخالي', () => {
  const items = [{ id: 1, name: 'بلاط' }, { id: 2, name: 'خلاط' }, { id: 3, name: 'مرآة' }];
  const suppliers = [{ id: 10, supplier_name: 'Foshan' }, { id: 20, supplier_name: 'Kale' }];
  const prices = [price(2, 10, '', '5'), price(1, 20, '', '4')];
  const byItem = searchBoard(items, suppliers, prices, 'بلاط', false);
  assert.deepEqual([...byItem.visibleItemIds], [1]);
  assert.deepEqual([...byItem.dimSupplierIds], [10]);
  const bySupplier = searchBoard(items, suppliers, prices, 'foshan', false);
  assert.deepEqual([...bySupplier.visibleItemIds], [2]);
  assert.equal(bySupplier.isCellDim(1, 20), true);
  assert.equal(bySupplier.isCellDim(2, 10), false);
  const only = searchBoard(items, suppliers, prices, '', true);
  assert.deepEqual([...only.visibleItemIds], [1, 2]);
});
