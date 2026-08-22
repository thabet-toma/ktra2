import { test } from 'node:test';
import assert from 'node:assert/strict';
import { documentSerialDisplay, elideDocumentNumber } from './documentNumberDisplay.ts';

test('الرقم الذي يتّسع يبقى كاملاً — لا «…» بلا سبب', () => {
  assert.equal(elideDocumentNumber('IQ-00006'), 'IQ-00006');
  // اثنا عشر محرفاً هي الحدّ — تُعرض كاملة.
  assert.equal(elideDocumentNumber('IQ-000000006'), 'IQ-000000006');
});

test('الرقم الطويل يُقصّ من الوسط: تبقى بادئة النوع ويبقى الذيل المميِّز', () => {
  assert.equal(elideDocumentNumber('IQ-0000000123'), 'IQ…000123');
  assert.equal(elideDocumentNumber('PQ-0000000123'), 'PQ…000123');
});

test('الذيل هو ما يفرّق سجلّين — لا يضيع في القصّ', () => {
  assert.notEqual(
    elideDocumentNumber('IQ-0000000006'),
    elideDocumentNumber('IQ-0000000007'),
  );
});

test('البادئة تفرّق النوع — استيراد وشراء لا يصيران رقماً واحداً', () => {
  assert.notEqual(
    elideDocumentNumber('IQ-0000000123'),
    elideDocumentNumber('PQ-0000000123'),
  );
});

test('رقم بلا بادئة حرفية يحتفظ بأول محرفين', () => {
  assert.equal(elideDocumentNumber('20260816000123'), '20…000123');
});

test('الفراغ والقيم الغائبة نصّ فارغ لا «…»', () => {
  assert.equal(elideDocumentNumber(undefined), '');
  assert.equal(elideDocumentNumber(null), '');
  assert.equal(elideDocumentNumber('   '), '');
});

test('رقم يدوي بالعربية (العرض الوارد يُدخَل يدوياً) يُقصّ ولا ينكسر', () => {
  assert.equal(elideDocumentNumber('عرض المورد رقم ٧'), 'عرض… رقم ٧');
});

test('حدود مخصّصة — القصّ الذي لا يقصّر شيئاً يُترك', () => {
  assert.equal(elideDocumentNumber('IQ-12345', 6, 6), 'IQ-12345');
});

test('التسلسل وحده: البادئة الثابتة والأصفار الحاشية لا تُعرَض', () => {
  assert.equal(documentSerialDisplay('IQ-0006'), '6');
  assert.equal(documentSerialDisplay('IQ-000000006'), '6');
  assert.equal(documentSerialDisplay('PQ-0123'), '123');
  assert.equal(documentSerialDisplay('PO/2026-0042'), '42');
});

test('تسلسلان مختلفان يبقيان مختلفين بعد الاختصار', () => {
  assert.notEqual(documentSerialDisplay('IQ-0006'), documentSerialDisplay('IQ-0007'));
});

test('تصادم النوعين حقيقي — ولذلك يقرّره المستدعي لا هذه الدالّة', () => {
  // `PQ-0006` و`PO-0006` يصيران «6» كلاهما: هذا هو الشرط الذي يعيد القائمةَ
  // إلى الأرقام الكاملة في `PriceOfferManagement`.
  assert.equal(documentSerialDisplay('PQ-0006'), documentSerialDisplay('PO-0006'));
});

test('ما ليس تسلسلاً قصيراً يعود إلى القصّ الأوسط بلا تغيير', () => {
  // تاريخ مضغوط: أربع عشرة خانة — ليس تسلسلاً يُقرأ بنظرة.
  assert.equal(documentSerialDisplay('20260816000123'), elideDocumentNumber('20260816000123'));
  // تسلسل أطول من ستّ خانات.
  assert.equal(documentSerialDisplay('IQ-0001234567'), elideDocumentNumber('IQ-0001234567'));
  // رقم يدوي بالعربية بلا أرقام لاتينية.
  assert.equal(documentSerialDisplay('عرض المورد رقم ٧'), elideDocumentNumber('عرض المورد رقم ٧'));
  // ورقم قصير بلا بادئة يبقى كما هو.
  assert.equal(documentSerialDisplay('7'), '7');
});

test('الفراغ والقيم الغائبة نصّ فارغ', () => {
  assert.equal(documentSerialDisplay(undefined), '');
  assert.equal(documentSerialDisplay(null), '');
  assert.equal(documentSerialDisplay('   '), '');
});
