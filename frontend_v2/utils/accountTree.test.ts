import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  accountLabel,
  accountMatchesPurpose,
  accountNature,
  accountPath,
  accountStatement,
  ancestorIdsOf,
  buildAccountIndex,
  buildAccountSelectable,
  resolveAccountSelectable,
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

/**
 * شجرة على نسق الشجرة المعيارية بعد تصنيف الخادم (`sub_type`): صناديق وبنوك
 * ومخزون تحت الأصول المتداولة — لاختبار القصّ بالغرض.
 */
const PURPOSE_TREE: AccountNodeLike[] = [
  { id: 1, code: '1', name: 'الأصول', parent: null, account_type: 'Asset' },
  { id: 2, code: '11', name: 'الأصول المتداولة', parent: 1, account_type: 'Asset' },
  { id: 3, code: '1101', name: 'النقدية', parent: 2, account_type: 'Asset', sub_type: 'cash_box' },
  { id: 4, code: '110101', name: 'الصندوق الرئيسي', parent: 3, account_type: 'Asset', sub_type: 'cash_box' },
  { id: 5, code: '110102', name: 'صندوق مقفل', parent: 3, account_type: 'Asset', sub_type: 'cash_box', is_active: false },
  { id: 6, code: '1102', name: 'البنوك', parent: 2, account_type: 'Asset', sub_type: 'bank' },
  { id: 7, code: '110201', name: 'بنك فلسطين', parent: 6, account_type: 'Asset', sub_type: 'bank' },
  { id: 8, code: '1104', name: 'المخزون', parent: 2, account_type: 'Asset', sub_type: 'inventory' },
];
/** كل الفروع مفتوحة — القصّ يُختبَر وحده بلا تداخل مع الطيّ. */
const ALL_OPEN = new Set([1, 2, 3, 6, 8]);

test('الغرض يُقرأ من التصنيف المخزَّن، ويسقط إلى الشرط القديم للحساب غير المصنَّف', () => {
  const stored = (subType: string, name: string): AccountNodeLike =>
    ({ id: 1, code: '1290', name, parent: null, account_type: 'Asset', sub_type: subType });
  assert.equal(accountMatchesPurpose(stored('cash_box', 'صندوق'), 'cash'), true);
  assert.equal(accountMatchesPurpose(stored('bank', 'بنك'), 'cash'), true);
  assert.equal(accountMatchesPurpose(stored('bank', 'بنك'), 'bank'), true);
  assert.equal(accountMatchesPurpose(stored('cash_box', 'صندوق'), 'bank'), false);
  // التصنيف المخزَّن يفوز على الاسم: حسابٌ اسمه «صندوق» صُنّف مخزوناً ليس صندوقاً
  assert.equal(accountMatchesPurpose(stored('inventory', 'صندوق العهدة'), 'cash'), false);
  // بلا تصنيف (شركة لم يمرّ عليها الاشتقاق بعد) ⇒ الشرط القديم كما هو
  assert.equal(
    accountMatchesPurpose({ id: 2, code: '1290', name: 'صندوق الفرع', parent: null, account_type: 'Asset' }, 'cash'),
    true,
  );
  assert.equal(
    accountMatchesPurpose({ id: 3, code: '1104', name: 'المخزون', parent: null, account_type: 'Asset' }, 'cash'),
    false,
  );
});

test('الأغراض غير المصنّفة تُقرأ من نوع الحساب، والمصفوفة تجمع غرضين', () => {
  const typed = (t: string): AccountNodeLike => ({ id: 1, code: '5', name: 'x', parent: null, account_type: t });
  assert.equal(accountMatchesPurpose(typed('Expense'), 'expense'), true);
  assert.equal(accountMatchesPurpose(typed('Revenue'), 'expense'), false);
  assert.equal(accountMatchesPurpose(typed('Asset'), ['expense', 'asset']), true);
  assert.equal(accountMatchesPurpose(typed('Liability'), ['expense', 'asset']), false);
  assert.equal(accountMatchesPurpose(typed('Liability'), 'any'), true);
});

test('غرض cash يقصّ الشجرة: المخزون لا يظهر إطلاقاً وأب النقدية يظهر غير قابل للاختيار', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  const selectable = buildAccountSelectable(index, { purpose: 'cash' })!;
  const rows = visibleAccountRows(PURPOSE_TREE, index, { expanded: ALL_OPEN, isSelectable: selectable });
  assert.deepEqual(
    rows.map((r) => r.account.code),
    ['1', '11', '1101', '110101', '1102', '110201'],
  );
  // 1104 ليست مطابقة ولا أباً لمطابق ⇒ لا تُرسم أصلاً (لا رمادية ولا غيره)
  assert.equal(rows.some((r) => r.account.code === '1104'), false);
  // 1101 تظهر لأنها أبٌ لصندوق — لكنها ليست هدف ترحيل
  assert.equal(selectable(PURPOSE_TREE[2]), false);
  assert.equal(selectable(PURPOSE_TREE[3]), true);
});

test('الأب لا يُختار افتراضياً ويُختار مع allowParents', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  const strict = buildAccountSelectable(index, { purpose: 'cash' })!;
  const loose = buildAccountSelectable(index, { purpose: 'cash', allowParents: true })!;
  assert.equal(strict(PURPOSE_TREE[2]), false);
  assert.equal(loose(PURPOSE_TREE[2]), true);
  // الورقة تبقى قابلة للاختيار في الحالتين
  assert.equal(strict(PURPOSE_TREE[3]), true);
  assert.equal(loose(PURPOSE_TREE[3]), true);
});

test('الحساب غير النشط لا يُختار ولا يُبقي فرعه ظاهراً', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  const selectable = buildAccountSelectable(index, { purpose: 'cash' })!;
  assert.equal(selectable(PURPOSE_TREE[4]), false);
  const rows = visibleAccountRows(PURPOSE_TREE, index, { expanded: ALL_OPEN, isSelectable: selectable });
  assert.equal(rows.some((r) => r.account.code === '110102'), false);
});

test('غرض بلا حساب واحد مطابق يعيد الشجرة كاملة — لا طريق مسدود', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  const selectable = buildAccountSelectable(index, { purpose: 'payable' })!;
  const rows = visibleAccountRows(PURPOSE_TREE, index, { expanded: ALL_OPEN, isSelectable: selectable });
  assert.equal(rows.length, PURPOSE_TREE.length);
  assert.equal(rows.some((r) => r.account.code === '1104'), true);
});

test('غرض بلا مطابق: الانتقاء يسقط أيضاً، لا الرسم وحده', () => {
  // اعتراض فيبل 2: الشجرة كانت تعود كاملة والانتقاء يبقى على شرط الغرض،
  // فيرى المستخدم كل الحسابات ولا يستطيع اختيار واحد — طريق مسدود مرئي.
  const index = buildAccountIndex(PURPOSE_TREE);
  const selectable = resolveAccountSelectable(PURPOSE_TREE, index, { purpose: 'payable' });
  assert.equal(
    PURPOSE_TREE.some((a) => (selectable ? selectable(a) : true)),
    true,
    'لا بد من حسابٍ واحد قابل للاختيار على الأقل',
  );
});

test('السقوط يُبقي شرط الشاشة ولا يمنح ما يرفضه الخادم', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  // قائمة خادمية تسمح بحساب واحد، وغرض لا يطابقه أحد
  const selectable = resolveAccountSelectable(PURPOSE_TREE, index, {
    purpose: 'payable',
    isSelectable: (a) => a.id === 7,
  });
  const allowed = PURPOSE_TREE.filter((a) => (selectable ? selectable(a) : true));
  assert.deepEqual(allowed.map((a) => a.id), [7]);
});

test('مع وجود مطابق واحد لا يسقط الغرض', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  const selectable = resolveAccountSelectable(PURPOSE_TREE, index, { purpose: 'cash' })!;
  assert.equal(selectable(PURPOSE_TREE.find((a) => a.code === '1104')!), false);
});

test('البحث يعمل داخل الشجرة المقصوصة', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  const selectable = buildAccountSelectable(index, { purpose: 'cash' })!;
  const rows = visibleAccountRows(PURPOSE_TREE, index, { query: 'بنك', isSelectable: selectable });
  assert.deepEqual(rows.map((r) => r.account.code), ['1', '11', '1102', '110201']);
});

test('القصّ يتبع أي شرط انتقاء ممرَّر، لا الغرض وحده', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  // قائمة خادمية (SettleFromOnAccountModal) — تكسب القصّ بلا غرض
  const selectable = buildAccountSelectable(index, { isSelectable: (a) => a.id === 7 })!;
  const rows = visibleAccountRows(PURPOSE_TREE, index, { expanded: ALL_OPEN, isSelectable: selectable });
  assert.deepEqual(rows.map((r) => r.account.code), ['1', '11', '1102', '110201']);
});

test('بلا غرض ولا شرط: الصفوف والانتقاء كما هما اليوم', () => {
  const index = buildAccountIndex(PURPOSE_TREE);
  assert.equal(buildAccountSelectable(index, {}), undefined);
  assert.equal(buildAccountSelectable(index), undefined);
  const before = visibleAccountRows(PURPOSE_TREE, index, { expanded: ALL_OPEN });
  const after = visibleAccountRows(PURPOSE_TREE, index, { expanded: ALL_OPEN, isSelectable: undefined });
  assert.deepEqual(after.map((r) => r.account.code), before.map((r) => r.account.code));
  assert.equal(before.length, PURPOSE_TREE.length);
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
