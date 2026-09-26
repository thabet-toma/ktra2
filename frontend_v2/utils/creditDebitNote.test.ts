import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  noteBalanceDelta,
  noteExplanation,
  noteMeaning,
  partyBalancePhrase,
} from './creditDebitNote.ts';

test('a debit note raises what a customer owes and lowers what a creditor is owed', () => {
  assert.equal(noteBalanceDelta('debit', false, 100), 100);
  assert.equal(noteBalanceDelta('credit', false, 100), -100);
  assert.equal(noteBalanceDelta('debit', true, 100), -100);
  assert.equal(noteBalanceDelta('credit', true, 100), 100);
});

test('balance phrase speaks from the party side, not the sign', () => {
  assert.equal(partyBalancePhrase(250, false), 'عليه 250');
  assert.equal(partyBalancePhrase(-40, false), 'له 40');
  assert.equal(partyBalancePhrase(1000, true), 'له 1,000');
  // المخلّص بعد إشعارٍ مدين أكبر مما له: صار مديناً لنا.
  assert.equal(partyBalancePhrase(-250, true), 'عليه 250');
  assert.equal(partyBalancePhrase(0, true), 'مسدَّد');
});

test('explanation names the party and the side', () => {
  assert.equal(noteExplanation('حاييم', 'debit', 250), 'هذا الإشعار سيجعل حاييم مديناً لنا بمبلغ 250');
  assert.equal(noteExplanation('', 'credit', 1500.5), 'هذا الإشعار سيجعل الطرف دائناً لنا بمبلغ 1,500.5');
  assert.match(noteMeaning('debit', true), /مطالبة/);
  assert.match(noteMeaning('credit', false), /ينقص ما عليه/);
});
