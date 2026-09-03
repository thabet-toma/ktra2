import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  getPrintColumns,
  getProcurementColumns,
  getScreenColumns,
  getSupplierColumns,
  pickProcurementRowFields,
  type ProcurementColumnKey,
} from './procurementColumns.ts';

const keysOf = (cols: { key: ProcurementColumnKey }[]) => cols.map((c) => c.key);

test('الطلبية: وحدة القياس والسعر التقديري في الشاشة، وبلا سعر وحدة أو إجمالي أو أقل سعر', () => {
  const keys = keysOf(getScreenColumns('rfq'));
  assert.ok(keys.includes('unitOfMeasure'));
  assert.ok(keys.includes('estimatedPrice'));
  assert.ok(!keys.includes('unitPrice'));
  assert.ok(!keys.includes('lineTotal'));
  // «أقل سعر» في الطلبية مصدر تعبئة لا عمود شاشة.
  assert.ok(!keys.includes('lowestPrice'));
});

test('العرض: سعر الوحدة والإجمالي وأقل سعر في الشاشة، وبلا سعر تقديري', () => {
  const keys = keysOf(getScreenColumns('offer'));
  assert.ok(keys.includes('unitOfMeasure'));
  assert.ok(keys.includes('unitPrice'));
  assert.ok(keys.includes('lineTotal'));
  assert.ok(keys.includes('lowestPrice'));
  assert.ok(!keys.includes('estimatedPrice'));
});

test('كود HS غائبٌ عن كلا النوعين — لا مفتاح hsCode في المصفوفة إطلاقاً', () => {
  for (const docType of ['rfq', 'offer'] as const) {
    const keys = keysOf(getScreenColumns(docType));
    assert.ok(!keys.some((k) => /hs/i.test(k)));
  }
});

test('النطاق لا يغيّر الأعمدة بتاتاً — الحجّة الحاسمة أن بُعد النطاق سقط من المصفوفة', () => {
  for (const docType of ['rfq', 'offer'] as const) {
    const local = getScreenColumns(docType, 'local');
    const imported = getScreenColumns(docType, 'import');
    assert.deepEqual(local, imported, `${docType}: النطاق أثّر في الأعمدة وهذا ممنوع`);
    assert.deepEqual(getPrintColumns(docType, 'local'), getPrintColumns(docType, 'import'));
    assert.deepEqual(getSupplierColumns(docType, 'local'), getSupplierColumns(docType, 'import'));
  }
});

test('السعر التقديري غائبٌ عن الطباعة ومورّد الطلبية — قائمة سماح لا قائمة منع', () => {
  const print = keysOf(getPrintColumns('rfq'));
  const supplier = keysOf(getSupplierColumns('rfq'));
  assert.ok(!print.includes('estimatedPrice'));
  assert.ok(!supplier.includes('estimatedPrice'));
  // مورّد الطلبية فرعي من طباعتها.
  assert.ok(supplier.every((k) => print.includes(k)));
});

test('أقل سعر غائبٌ عن طباعة العرض، والأسعار تُطبَع ولا تخرج إلى المورد', () => {
  const print = keysOf(getPrintColumns('offer'));
  const supplier = keysOf(getSupplierColumns('offer'));
  // «أقل سعر» رقمُنا نحن — لا يُطبَع ولا يخرج (مواصفة #108 §١١).
  assert.ok(!print.includes('lowestPrice'));
  assert.ok(!supplier.includes('lowestPrice'));
  // وسعرُ الوحدة والإجمالي **يُطبَعان**: عرضٌ يُطبَع بلا أسعارٍ ورقةٌ فارغةُ المعنى.
  assert.ok(print.includes('unitPrice'));
  assert.ok(print.includes('lineTotal'));
  // ولا يخرجان إلى المورد — الورقةُ التي تصله فيها خانةُ سعرٍ فارغة يملؤها هو.
  assert.ok(!supplier.includes('unitPrice'));
  assert.ok(!supplier.includes('lineTotal'));
  // ثلاثُ مجموعاتٍ لا اثنتان: الطباعةُ أوسعُ ممّا يخرج إلى المورد فعلاً.
  assert.ok(supplier.length < print.length);
  assert.ok(supplier.every((k) => print.includes(k)));
});

test('getProcurementColumns يعيد الثلاث مجموعات معاً متّسقة مع الدوال المفردة', () => {
  for (const docType of ['rfq', 'offer'] as const) {
    const all = getProcurementColumns(docType);
    assert.deepEqual(all.screen, getScreenColumns(docType));
    assert.deepEqual(all.print, getPrintColumns(docType));
    assert.deepEqual(all.supplier, getSupplierColumns(docType));
  }
});

// ── الاختبار الحارس: رقمٌ مميَّز لا يلتبس (٩٩٩٫٩٩) في السعر التقديري وأقل
// سعر — يُفتَّش عنه في حمولتي الطباعة والمورد المبنيّتين فعلياً عبر
// `pickProcurementRowFields`، لا في وصف الأعمدة فقط. وجوده في أيٍّ منهما
// إخفاقٌ صريح (مواصفة #108 §«ما يُختبَر بالتحديد»).
test('حارس التسرّب: ٩٩٩٫٩٩ (السعر التقديري) لا يظهر في حمولة طباعة أو مورد الطلبية', () => {
  const sentinel = 999.99;
  const row = {
    seq: 1,
    product: 'صنف تجريبي',
    specs: 'مواصفات',
    quantity: 10,
    unitOfMeasure: 'قطعة',
    estimatedPrice: sentinel,
  };
  const printPayload = pickProcurementRowFields(row, getPrintColumns('rfq'));
  const supplierPayload = pickProcurementRowFields(row, getSupplierColumns('rfq'));
  assert.ok(!JSON.stringify(printPayload).includes(String(sentinel)));
  assert.ok(!JSON.stringify(supplierPayload).includes(String(sentinel)));
  assert.equal(printPayload.estimatedPrice, undefined);
  assert.equal(supplierPayload.estimatedPrice, undefined);
});

test('حارس التسرّب: ٩٩٩٫٩٩ (أقل سعر) لا يظهر في حمولة طباعة أو مورد العرض', () => {
  const sentinel = 999.99;
  const row = {
    seq: 1,
    product: 'صنف تجريبي',
    specs: 'مواصفات',
    quantity: 10,
    unitOfMeasure: 'قطعة',
    unitPrice: 50,
    lineTotal: 500,
    lowestPrice: sentinel,
  };
  const printPayload = pickProcurementRowFields(row, getPrintColumns('offer'));
  const supplierPayload = pickProcurementRowFields(row, getSupplierColumns('offer'));
  assert.ok(!JSON.stringify(printPayload).includes(String(sentinel)));
  assert.ok(!JSON.stringify(supplierPayload).includes(String(sentinel)));
  assert.equal(printPayload.lowestPrice, undefined);
  assert.equal(supplierPayload.lowestPrice, undefined);
});

test('pickProcurementRowFields لا ينسخ حقلاً غائباً عن قائمة الأعمدة، ولا يفشل على حقل غائب عن الصفّ', () => {
  const cols = getScreenColumns('offer');
  const partialRow = { seq: 1, product: 'ص' };
  const picked = pickProcurementRowFields(partialRow, cols);
  assert.deepEqual(picked, { seq: 1, product: 'ص' });
});
