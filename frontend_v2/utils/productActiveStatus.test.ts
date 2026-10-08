import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  familyDeactivationConfirmMessage,
  productDeactivationConfirmMessage,
  type ProductDeactivationImpact,
} from './productActiveStatus.ts';
import { labelWithStatus } from './activeStatus.ts';

const fmt = (v: string) => `#${v}`;

const doc = (number: string, id = 1, kind = 'sales_invoice', kind_label = 'فاتورة بيع') =>
  ({ kind, kind_label, id, number, date: null });

const impact = (over: Partial<ProductDeactivationImpact> = {}): ProductDeactivationImpact => ({
  quantity_on_hand: '0',
  draft_documents_count: 0,
  draft_documents: [],
  ...over,
});

test('بلا رصيد ولا مسوّدات: القاعدة وحدها', () => {
  const msg = productDeactivationConfirmMessage('إطار', impact(), fmt);
  assert.match(msg, /سيصبح «إطار» غير نشط/);
  assert.doesNotMatch(msg, /الكمية الموجودة/);
  assert.doesNotMatch(msg, /مسوّدات تحمله/);
  assert.match(msg, /لن يظهر في المستندات الجديدة، وستُرفض مسوّداته عند الترحيل حتى تنشّطه\./);
});

test('الرصيد الموجود يُعرض بالمُنسِّق الممرَّر', () => {
  const msg = productDeactivationConfirmMessage('إطار', impact({ quantity_on_hand: '12.5000' }), fmt);
  assert.match(msg, /الكمية الموجودة في المخزون: #12\.5000/);
});

test('المسوّدات تُعرض بنوعها ورقمها، وما فوق الخمسة يُختصر بـ«و N أخرى»', () => {
  const docs = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'].map((n, i) => doc(n, i + 1));
  const msg = productDeactivationConfirmMessage(
    'إطار', impact({ draft_documents_count: 9, draft_documents: docs }), fmt);
  assert.match(msg, /مسوّدات تحمله: 9 \(فاتورة بيع A1، فاتورة بيع A2، فاتورة بيع A3، فاتورة بيع A4، فاتورة بيع A5 و4 أخرى\)/);
  assert.doesNotMatch(msg, /A6/);
});

test('عدد مسوّدات أقل من الخمسة لا يضيف «أخرى»', () => {
  const msg = productDeactivationConfirmMessage(
    'إطار', impact({ draft_documents_count: 2, draft_documents: [doc('A1'), doc('B2', 2, 'sales_order', 'طلبية بيع')] }), fmt);
  assert.match(msg, /\(فاتورة بيع A1، طلبية بيع B2\)/);
  assert.doesNotMatch(msg, /أخرى/);
});

test('رصيدٌ سالب يُعرض أيضاً (≠ صفر)', () => {
  const msg = productDeactivationConfirmMessage('إطار', impact({ quantity_on_hand: '-3' }), fmt);
  assert.match(msg, /الكمية الموجودة في المخزون: #-3/);
});

test('صفّ المنتج ببراندات: مجموع الكمية واتحاد المسوّدات بلا تكرار', () => {
  const shared = doc('S1', 5);
  const msg = familyDeactivationConfirmMessage('هاتف', [
    impact({ quantity_on_hand: '3', draft_documents_count: 2, draft_documents: [shared, doc('A1', 1)] }),
    impact({ quantity_on_hand: '4', draft_documents_count: 1, draft_documents: [shared] }),
  ], fmt);
  assert.match(msg, /سيصبح «هاتف» غير نشط بكل براندَاته \(2\)/);
  assert.match(msg, /الكمية الموجودة في المخزون: #7/);
  assert.match(msg, /مسوّدات تحمله: 2 \(فاتورة بيع S1، فاتورة بيع A1\)/);
});

test('صفّ المنتج بلا رصيد ولا مسوّدات: لا أسطر إضافية', () => {
  const msg = familyDeactivationConfirmMessage('هاتف', [impact(), impact()], fmt);
  assert.doesNotMatch(msg, /الكمية الموجودة/);
  assert.doesNotMatch(msg, /مسوّدات تحمله/);
});

test('labelWithStatus: الموقوف صراحةً فقط يحمل الوسم', () => {
  assert.equal(labelWithStatus('إطار', false), 'إطار (غير نشط)');
  assert.equal(labelWithStatus('إطار', true), 'إطار');
  assert.equal(labelWithStatus('إطار', undefined), 'إطار');
  assert.equal(labelWithStatus('إطار', null), 'إطار');
});
