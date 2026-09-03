import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildSavedVouchers,
  markVoucherUndone,
  mergeSavedVouchers,
  savedVouchersSummary,
  type SavedVoucher,
  type SubmittedRowFacts,
} from './codingSavedVouchers.ts';

const facts = (over: Partial<SubmittedRowFacts> = {}): SubmittedRowFacts => ({
  date: '2026-06-10',
  direction: 'expense',
  accountLabel: '5203 كهرباء',
  partnerLabel: 'شركة الكهرباء',
  docNumber: 'F-1',
  amount: '100',
  taxAmount: '0',
  ...over,
});

const voucher = (over: Partial<SavedVoucher> = {}): SavedVoucher => ({
  id: 1, number: 1, direction: 'expense', date: '2026-06-10',
  accountLabel: '5203 كهرباء', partnerLabel: '', docNumber: '',
  amount: '100', taxAmount: '0', undone: false, ...over,
});

test('الصفّ الناجح يدخل السِجلّ بمعرّفه ورقمه وبيانات صفّه', () => {
  const saved = buildSavedVouchers(
    [{ index: 0, success: true, id: 1001, number: 7, direction: 'expense' }],
    new Map([[0, facts()]]),
  );
  assert.equal(saved.length, 1);
  assert.equal(saved[0].id, 1001);
  assert.equal(saved[0].number, 7);
  assert.equal(saved[0].accountLabel, '5203 كهرباء');
  assert.equal(saved[0].partnerLabel, 'شركة الكهرباء');
  assert.equal(saved[0].undone, false);
});

test('الصفّ الفاشل لا يدخل السِجلّ — مكانه الشبكة برسالة خطئه', () => {
  const saved = buildSavedVouchers(
    [{ index: 0, success: false, error: 'مبلغ المصروف يجب أن يكون أكبر من صفر.' }],
    new Map([[0, facts()]]),
  );
  assert.deepEqual(saved, []);
});

test('نجاحٌ بلا معرّف يُهمَل — بلا معرّف لا تراجعَ ممكن', () => {
  const saved = buildSavedVouchers(
    [{ index: 0, success: true, number: 7, direction: 'expense' }],
    new Map([[0, facts()]]),
  );
  assert.deepEqual(saved, []);
});

// المزلق الحاسم: `direction` اختياريّ في عقد الردّ. بناءُ زرّ التراجع عليه
// وحده يعني استدعاء نقطة **المصروف** على سند إيراد حين يغيب — أي فتحُ قيدٍ
// خاطئ. الصفّ المُرسَل يعرف اتجاهه يقيناً لأنه هو من أرسله.
test('اتجاه غائب في الردّ يُؤخذ من الصفّ المُرسَل لا يُفترَض مصروفاً', () => {
  const saved = buildSavedVouchers(
    [{ index: 0, success: true, id: 5, number: 2 }],
    new Map([[0, facts({ direction: 'revenue' })]]),
  );
  assert.equal(saved[0].direction, 'revenue');
});

test('اتجاه الخادم يفوز حين يُصرَّح به', () => {
  const saved = buildSavedVouchers(
    [{ index: 0, success: true, id: 5, number: 2, direction: 'revenue' }],
    new Map([[0, facts({ direction: 'expense' })]]),
  );
  assert.equal(saved[0].direction, 'revenue');
});

test('اتجاهٌ مجهول في الردّ لا يُقبل — يسقط للصفّ المُرسَل', () => {
  const saved = buildSavedVouchers(
    [{ index: 0, success: true, id: 5, number: 2, direction: 'journal' }],
    new Map([[0, facts({ direction: 'revenue' })]]),
  );
  assert.equal(saved[0].direction, 'revenue');
});

test('الحفظة الثانية تُضاف فوق الأولى ولا تمحوها', () => {
  const first = [voucher({ id: 1, number: 1 })];
  const second = [voucher({ id: 2, number: 2 })];
  const merged = mergeSavedVouchers(first, second);
  assert.deepEqual(merged.map((v) => v.id), [2, 1]);
});

test('المكرَّر يُنقّى بالمعرّف والاتجاه معاً — لا بالرقم', () => {
  // سند مصروف #7 وسند إيراد #7 رقمان مستقلّان في دفترين مختلفين، وقد
  // يتصادف معرّفاهما في جدولين مختلفين كذلك.
  const merged = mergeSavedVouchers(
    [voucher({ id: 7, number: 7, direction: 'expense' })],
    [voucher({ id: 7, number: 7, direction: 'revenue' })],
  );
  assert.equal(merged.length, 2);

  const deduped = mergeSavedVouchers(
    [voucher({ id: 7, direction: 'expense' })],
    [voucher({ id: 7, direction: 'expense' })],
  );
  assert.equal(deduped.length, 1);
});

test('التراجع يشطب ولا يحذف — الاختفاء يُنسي المستخدم فعلَه', () => {
  const list = [voucher({ id: 1 }), voucher({ id: 2 })];
  const after = markVoucherUndone(list, 'expense', 1);
  assert.equal(after.length, 2);
  assert.equal(after[0].undone, true);
  assert.equal(after[1].undone, false);
});

test('التراجع لا يُصيب سنداً بنفس المعرّف في الاتجاه الآخر', () => {
  const list = [
    voucher({ id: 7, direction: 'expense' }),
    voucher({ id: 7, direction: 'revenue' }),
  ];
  const after = markVoucherUndone(list, 'expense', 7);
  assert.equal(after[0].undone, true);
  assert.equal(after[1].undone, false);
});

test('المجاميع تفصل الاتجاهين وتُخرج المتراجَع عنه', () => {
  const list = [
    voucher({ id: 1, direction: 'expense', amount: '100' }),
    voucher({ id: 2, direction: 'revenue', amount: '250' }),
    voucher({ id: 3, direction: 'expense', amount: '999', undone: true }),
  ];
  assert.deepEqual(savedVouchersSummary(list), { count: 2, expense: 100, revenue: 250 });
});

test('مبلغٌ غير رقميّ لا يُفسد المجموع', () => {
  const list = [voucher({ id: 1, amount: '' }), voucher({ id: 2, amount: 'abc' })];
  assert.deepEqual(savedVouchersSummary(list), { count: 2, expense: 0, revenue: 0 });
});

test('سِجلٌّ فارغ يعطي أصفاراً لا NaN', () => {
  assert.deepEqual(savedVouchersSummary([]), { count: 0, expense: 0, revenue: 0 });
});
