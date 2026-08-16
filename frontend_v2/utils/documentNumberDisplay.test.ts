import { test } from 'node:test';
import assert from 'node:assert/strict';
import { elideDocumentNumber } from './documentNumberDisplay.ts';

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
