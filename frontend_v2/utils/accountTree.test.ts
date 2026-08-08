import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  accountLabel,
  accountNature,
  accountPath,
  accountStatement,
  ancestorIdsOf,
  buildAccountIndex,
  isCashAccount,
  matchesAccountQuery,
  nextChildCode,
  visibleAccountRows,
  type AccountNodeLike,
} from './accountTree.ts';

const acc = (
  id: number, code: string, name: string, parent: number | null = null,
): AccountNodeLike => ({ id, code, name, parent });

/** شجرة مصغّرة على نسق الشجرة المعيارية: أصول ← نقدية/مدينون ← حساب زبون. */
const TREE: AccountNodeLike[] = [
  acc(4, '1103', 'المدينون التجاريون', 2),
  acc(1, '1', 'الأصول', null),
  acc(5, '11030001', 'زبون التجزئة', 4),
  acc(3, '1101', 'النقدية', 2),
  acc(2, '11', 'الأصول المتداولة', 1),
];

test('الأبناء مرتّبون بالكود مهما كان ترتيب المصفوفة الواردة', () => {
  const index = buildAccountIndex(TREE);
  assert.deepEqual(
    (index.childrenOf.get(2) ?? []).map((a) => a.code),
    ['1101', '1103'],
  );
  assert.deepEqual((index.childrenOf.get(null) ?? []).map((a) => a.code), ['1']);
});

test('الحساب اليتيم (أبوه خارج القائمة) يصير جذراً لا يختفي', () => {
  const index = buildAccountIndex([acc(9, '5301', 'رسوم استيراد', 77)]);
  assert.deepEqual((index.childrenOf.get(null) ?? []).map((a) => a.id), [9]);
});

test('آباء الحساب من الأقرب إلى الجذر', () => {
  const index = buildAccountIndex(TREE);
  assert.deepEqual(ancestorIdsOf(index, 5), [4, 2, 1]);
  assert.deepEqual(ancestorIdsOf(index, 1), []);
  assert.deepEqual(ancestorIdsOf(index, null), []);
});

test('حلقة أبوّة معطوبة لا تُعلّق الحساب', () => {
  const index = buildAccountIndex([
    { id: 1, code: 'A', name: 'أ', parent: 2 },
    { id: 2, code: 'B', name: 'ب', parent: 1 },
  ]);
  assert.deepEqual(ancestorIdsOf(index, 1), [2, 1]);
});

test('الجذور وحدها تظهر ما لم يُفتح فرع', () => {
  const index = buildAccountIndex(TREE);
  const rows = visibleAccountRows(TREE, index);
  assert.deepEqual(rows.map((r) => r.account.code), ['1']);
  assert.equal(rows[0].hasChildren, true);
  assert.equal(rows[0].expanded, false);
});

test('فتح الفروع يُظهر الأبناء بعمقهم', () => {
  const index = buildAccountIndex(TREE);
  const rows = visibleAccountRows(TREE, index, { expanded: new Set([1, 2]) });
  assert.deepEqual(
    rows.map((r) => [r.account.code, r.depth]),
    [['1', 0], ['11', 1], ['1101', 2], ['1103', 2]],
  );
});

test('البحث يفتح المطابق وآباءه ويحجب ما سواه', () => {
  const index = buildAccountIndex(TREE);
  const rows = visibleAccountRows(TREE, index, { query: 'زبون' });
  assert.deepEqual(
    rows.map((r) => r.account.code),
    ['1', '11', '1103', '11030001'],
  );
  // النقدية ليست في المسار فتُحجب رغم أن أباها ظاهر
  assert.equal(rows.some((r) => r.account.code === '1101'), false);
});

test('البحث بالكود يطابق كما يطابق الاسم', () => {
  assert.equal(matchesAccountQuery(acc(1, '1101', 'النقدية'), '1101'), true);
  assert.equal(matchesAccountQuery(acc(1, '1101', 'النقدية'), 'نقد'), true);
  assert.equal(matchesAccountQuery(acc(1, '1101', 'النقدية'), 'بنك'), false);
  assert.equal(matchesAccountQuery(acc(1, '1101', 'النقدية'), '  '), true);
});

test('تسمية الحقل المغلق تجمع الكود والاسم وتتحمّل الناقص', () => {
  assert.equal(accountLabel(acc(1, '1101', 'النقدية')), '1101 — النقدية');
  assert.equal(accountLabel({ id: 2, code: null, name: 'بلا كود', parent: null }), 'بلا كود');
  assert.equal(accountLabel({ id: 3, code: '9', name: null, parent: null }), '9');
  assert.equal(accountLabel(null), '');
});

test('شرط الصندوق موحّد: النوع أو الكود 110x أو الاسم', () => {
  const asset = (code: string, name: string) =>
    ({ id: 1, code, name, parent: null, account_type: 'Asset' });
  assert.equal(isCashAccount(asset('1101', 'النقدية')), true);
  assert.equal(isCashAccount(asset('1102', 'البنوك')), true);
  assert.equal(isCashAccount(asset('1290', 'صندوق الفرع')), true);
  assert.equal(isCashAccount(asset('1104', 'المخزون')), false);
  assert.equal(
    isCashAccount({ id: 2, code: '9', name: 'خزينة', parent: null, account_type: 'Bank' }),
    true,
  );
  assert.equal(
    isCashAccount({ id: 3, code: '2101', name: 'بنك دائن', parent: null, account_type: 'Liability' }),
    false,
  );
});

test('طبيعة الحساب مشتقّة من نوعه — الأصول والمصروفات مدينة والبقية دائنة', () => {
  const typed = (t: string | null) => ({ id: 1, code: '1', name: 'x', parent: null, account_type: t });
  assert.equal(accountNature(typed('Asset')), 'debit');
  assert.equal(accountNature(typed('Expense')), 'debit');
  assert.equal(accountNature(typed('Liability')), 'credit');
  assert.equal(accountNature(typed('Equity')), 'credit');
  assert.equal(accountNature(typed('Revenue')), 'credit');
  assert.equal(accountNature(typed('asset')), 'debit');
  assert.equal(accountNature(typed(null)), null);
  assert.equal(accountNature(typed('Nonsense')), null);
});

test('الحساب الختامي: الميزانية للأصول والخصوم والملكية، والأرباح للإيراد والمصروف', () => {
  const typed = (t: string | null) => ({ id: 1, code: '1', name: 'x', parent: null, account_type: t });
  assert.equal(accountStatement(typed('Asset')), 'balance');
  assert.equal(accountStatement(typed('Liability')), 'balance');
  assert.equal(accountStatement(typed('Equity')), 'balance');
  assert.equal(accountStatement(typed('Revenue')), 'income');
  assert.equal(accountStatement(typed('Expense')), 'income');
  assert.equal(accountStatement(typed(null)), null);
});

test('مسار الحساب من الجذر إلى الحساب نفسه', () => {
  const index = buildAccountIndex(TREE);
  assert.deepEqual(accountPath(index, 5).map((a) => a.code), ['1', '11', '1103', '11030001']);
  assert.deepEqual(accountPath(index, 1).map((a) => a.code), ['1']);
  assert.deepEqual(accountPath(index, null), []);
  assert.deepEqual(accountPath(index, 999), []);
});

test('كود الابن المقترح يكمل تسلسل الإخوة بنفس الطول', () => {
  const index = buildAccountIndex(TREE);
  // 1103 له ابن واحد 11030001 ⇒ التالي 11030002
  assert.equal(nextChildCode(index, 4), '11030002');
  // 1101 بلا أبناء ⇒ كود الأب + 01
  assert.equal(nextChildCode(index, 3), '110101');
  // الجذور: أعلى جذر «1» ⇒ «2»
  assert.equal(nextChildCode(index, null), '2');
});

test('كود مقترح فارغ حين يتعذّر الاستنتاج بثقة', () => {
  // إخوة بأطوال مختلفة ⇒ لا اقتراح
  const mixed = buildAccountIndex([
    acc(1, '1101', 'النقدية'),
    acc(2, '110101', 'صندوق', 1),
    acc(3, '11010102', 'صندوق فرعي', 1),
  ]);
  assert.equal(nextChildCode(mixed, 1), '');
  // كود غير رقمي ⇒ لا اقتراح
  const alpha = buildAccountIndex([acc(1, 'CASH', 'نقدية')]);
  assert.equal(nextChildCode(alpha, 1), '');
});
