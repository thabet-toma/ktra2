import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  bulkDeactivationConfirmMessage,
  deactivationConfirmMessage,
  staleCachedPartnerIds,
  visibleCachedPartners,
  type PartnerDeactivationImpact,
} from './partnerActiveStatus.ts';
import { labelWithStatus, parseActiveStatus } from './activeStatus.ts';

const fmt = (v: string) => `#${v}`;

const impact = (over: Partial<PartnerDeactivationImpact> = {}): PartnerDeactivationImpact => ({
  open_balance: '0',
  balance_side_label: '',
  draft_documents_count: 0,
  draft_documents: [],
  ...over,
});

const doc = (number: string) => ({ kind: 'sales_invoice', kind_label: 'فاتورة بيع', id: 1, number, date: null });

test('parseActiveStatus يقبل القيم الثلاث وما سواها نشط', () => {
  assert.equal(parseActiveStatus('inactive'), 'inactive');
  assert.equal(parseActiveStatus('all'), 'all');
  assert.equal(parseActiveStatus('active'), 'active');
  assert.equal(parseActiveStatus('banana'), 'active');
  assert.equal(parseActiveStatus(null), 'active');
});

test('نص التأكيد بلا رصيد ولا مستندات يقول القاعدة فقط', () => {
  const msg = deactivationConfirmMessage('مورد س', impact(), fmt);
  assert.match(msg, /سيصبح «مورد س» غير نشط/);
  assert.doesNotMatch(msg, /رصيده المفتوح/);
  assert.doesNotMatch(msg, /مستندات غير مكتملة/);
  assert.match(msg, /لن يظهر في المستندات الجديدة، والدفعات له تبقى مسموحة/);
});

test('نص التأكيد يعرض الرصيد بقيمته المطلقة وجهته', () => {
  const msg = deactivationConfirmMessage('زبون', impact({ open_balance: '-250', balance_side_label: 'دائن' }), fmt);
  assert.match(msg, /رصيده المفتوح: #250 \(دائن\)/);
});

test('نص التأكيد يختصر المستندات بعد خمسة', () => {
  const docs = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6'].map(doc);
  const msg = deactivationConfirmMessage('زبون', impact({ draft_documents_count: 8, draft_documents: docs }), fmt);
  assert.match(msg, /مستندات غير مكتملة: 8 \(A1، A2، A3، A4، A5 و3 أخرى\)/);
  assert.doesNotMatch(msg, /A6/);
});

test('نص التأكيد بخمسة مستندات أو أقل لا يضيف «أخرى»', () => {
  const msg = deactivationConfirmMessage('زبون', impact({ draft_documents_count: 2, draft_documents: [doc('A1'), doc('A2')] }), fmt);
  assert.match(msg, /\(A1، A2\)/);
  assert.doesNotMatch(msg, /أخرى/);
});

test('الموقوف وحده يحمل وسم «غير نشط» بعد اسمه', () => {
  assert.equal(labelWithStatus('زبون', false), 'زبون (غير نشط)');
  assert.equal(labelWithStatus('زبون', true), 'زبون');
  assert.equal(labelWithStatus('زبون', undefined), 'زبون');
});

const row = (id: number, partner_type: string, is_active?: boolean) => ({
  id, partner_type, data: JSON.stringify(is_active === undefined ? { id } : { id, is_active }),
});

test('التقليم بعد جلب active يحذف الغائب النشط ويُبقي الموقوف المخزَّن', () => {
  const cached = [row(1, 'Customer', true), row(2, 'Customer', true), row(3, 'Customer', false)];
  assert.deepEqual(staleCachedPartnerIds(cached, [1], 'Customer', 'active'), [2]);
});

test('التقليم بعد جلب all يحذف كل غائب حتى الموقوف', () => {
  const cached = [row(1, 'Customer', true), row(2, 'Customer', true), row(3, 'Customer', false)];
  assert.deepEqual(staleCachedPartnerIds(cached, [1], 'Customer', 'all'), [2, 3]);
});

test('التقليم لا يمسّ نوعاً غير مجلوب', () => {
  const cached = [row(1, 'Customer', true), row(2, 'Supplier', true)];
  assert.deepEqual(staleCachedPartnerIds(cached, [], 'Customer', 'active'), [1]);
  assert.deepEqual(staleCachedPartnerIds(cached, [], 'Supplier,Carrier', 'active'), [2]);
  assert.deepEqual(staleCachedPartnerIds(cached, [], undefined, 'active'), [1, 2]);
});

test('صفّ مخزَّن تالف يُعامل نشطاً فيُقلَّم إن غاب', () => {
  const cached = [{ id: 9, partner_type: 'Customer', data: '{not json' }];
  assert.deepEqual(staleCachedPartnerIds(cached, [], 'Customer', 'active'), [9]);
});

test('المعروض دون اتصال: الموقوف مخفيّ إلا مع all أو inactive', () => {
  const cached = [row(1, 'Customer', true), row(2, 'Customer', false), row(3, 'Supplier', true)];
  assert.deepEqual(visibleCachedPartners(cached, 'Customer', 'active').map((r) => r.id), [1]);
  assert.deepEqual(visibleCachedPartners(cached, 'Customer', 'all').map((r) => r.id), [1, 2]);
  assert.deepEqual(visibleCachedPartners(cached, 'Customer', 'inactive').map((r) => r.id), [2]);
  assert.deepEqual(visibleCachedPartners(cached, undefined, 'active').map((r) => r.id), [1, 3]);
});

test('تأكيد الإيقاف الجماعي يعدّ من عليه رصيد والمستندات ولا يجمع الأرصدة', () => {
  const msg = bulkDeactivationConfirmMessage(3, [
    impact({ open_balance: '100' }),
    impact({ open_balance: '-40', draft_documents_count: 2, draft_documents: [doc('A1'), doc('A2')] }),
    impact(),
  ]);
  assert.match(msg, /سيصبح 3 من الأطراف المحدَّدة غير نشطين/);
  assert.match(msg, /عليهم رصيدٌ مفتوح: 2 منهم/);
  assert.match(msg, /مستندات غير مكتملة: 2/);
});

test('تأكيد الإيقاف الجماعي بلا أثر يقول القاعدة فقط', () => {
  const msg = bulkDeactivationConfirmMessage(1, [impact()]);
  assert.doesNotMatch(msg, /رصيدٌ مفتوح/);
  assert.doesNotMatch(msg, /مستندات غير مكتملة/);
  assert.match(msg, /والدفعات لهم تبقى مسموحة/);
});
