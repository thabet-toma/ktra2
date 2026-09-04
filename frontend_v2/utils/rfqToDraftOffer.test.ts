import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rfqToDraftOffer } from './rfqToDraftOffer.ts';

type Rfq = Parameters<typeof rfqToDraftOffer>[0];
type Recipient = Parameters<typeof rfqToDraftOffer>[1];

/** طلبيةٌ مُرسَلة ببندين — الحالة الوحيدة التي يُفتح فيها هذا الطريق. */
const baseRfq = (over: Partial<Rfq> = {}): Rfq => ({
  id: 31,
  rfq_number: 'RFQ-0009',
  scope: 'local',
  rfq_date: '2026-04-02',
  status: 'sent',
  notes: 'ملاحظات داخلية لا تخرج للمورّد',
  lines: [
    {
      id: 71, product: 88, product_name: 'كابل شبكة', seq: 2,
      name_snapshot: 'كابل شبكة Cat6', specs: 'ملفوف 305م',
      quantity: '4.000', unit_of_measure: 'لفة', estimated_price: '210.00',
    },
    {
      id: 70, product: null, seq: 1,
      name_snapshot: 'قابس شبكة', specs: '',
      quantity: '500.000', unit_of_measure: 'حبة', estimated_price: null,
    },
  ],
  recipients: [],
  recipients_count: 2,
  replies_count: 0,
  ...over,
});

const baseRecipient = (over: Partial<Recipient> = {}): Recipient => ({
  id: 55,
  supplier: 9,
  supplier_name: 'مؤسسة النور للكهربائيات',
  share: null,
  quotation: null,
  sent_at: '2026-04-02T09:00:00Z',
  replied_at: null,
  ...over,
});

test('المستقبِل يصير مورد العرض، ورقم الطلبية اسمَه', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  assert.equal(draft.supplierId, '9');
  assert.equal(draft.factoryName, 'مؤسسة النور للكهربائيات');
  assert.equal(draft.orderName, 'RFQ-0009');
  assert.equal(draft.status, 'initial');
});

test('نسبُ العرض يعبر: رقم الطلبية ورقم المستقبِل', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  assert.equal(draft.rfqId, 31);
  assert.equal(draft.rfqRecipientId, 55);
});

test('البنود تُرتَّب بـseq لا بترتيب الاستجابة', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  assert.deepEqual(draft.items?.map((i) => i.name), ['قابس شبكة', 'كابل شبكة Cat6']);
});

test('الكمية والوحدة تعبران، والسعرُ يبقى فارغاً', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  const cable = draft.items?.find((i) => i.name === 'كابل شبكة Cat6');
  assert.equal(cable?.quantity, 4);
  assert.equal(cable?.unitOfMeasure, 'لفة');
  assert.equal(cable?.itemId, '88');
  assert.equal(cable?.specifications, 'ملفوف 305م');
  // هذا كلُّ الغرض: المالك يكتب ما سمعه، لا يصحّح رقماً اخترعه له النظام.
  assert.equal(cable?.unitPrice, 0);
  assert.equal(cable?.totalPrice, 0);
});

test('السعرُ التقديريّ داخليٌّ فلا يتسرّب إلى العرض', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  for (const item of draft.items ?? []) {
    assert.equal(item.unitPrice, 0);
  }
  assert.equal(draft.subtotal, 0);
  assert.equal(draft.grandTotal, 0);
});

test('بندُ الطلبية بلا منتجٍ مسجَّل يصل بلا itemId — لا يُخلَق له منتج', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  const plug = draft.items?.find((i) => i.name === 'قابس شبكة');
  assert.equal(plug?.itemId, '');
  assert.equal(plug?.quantity, 500);
});

test('اسم المورّد الاحتياطيّ يُستعمل حين لا يحمله المستقبِل', () => {
  const draft = rfqToDraftOffer(
    baseRfq(),
    baseRecipient({ supplier_name: undefined }),
    'مؤسسة النور',
  );
  assert.equal(draft.factoryName, 'مؤسسة النور');
});

test('ملاحظاتُ الطلبية الداخلية لا تُنسخ إلى العرض', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  assert.equal(draft.internalNotes, '');
  assert.equal(draft.orderDescription, '');
});

test('طلبيةٌ بلا رقمٍ بعد لا تكتب «undefined» اسماً', () => {
  const draft = rfqToDraftOffer(baseRfq({ rfq_number: null }), baseRecipient());
  assert.equal(draft.orderName, '');
});

test('كلُّ سطرٍ يحمل نَسَبَه إلى بند الطلبية لا ترتيبَه وحده', () => {
  const draft = rfqToDraftOffer(baseRfq(), baseRecipient());
  // الترتيب بـseq، والنَسَب معرّفُ البند نفسه — فحذفُ سطرٍ من الوسط في المحرِّر
  // لا يُزحزح ما بعده صنفاً واحداً في المصفوفة.
  assert.deepEqual(draft.items?.map((i) => i.rfqLineId), [70, 71]);
});
