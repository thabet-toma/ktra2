import test from 'node:test';
import assert from 'node:assert/strict';

import {
  RFQ_SUPPLIER_XLSX_HEADERS,
  buildRfqSupplierRows,
  buildRfqSupplierXlsxBuffer,
} from './purchaseRfqXlsx.ts';
import { buildPurchaseRfqPrintRows } from './purchaseRfqPrintPayload.ts';
import type { PurchaseRFQDto, PurchaseRFQLineDto } from '../services/procurementDocumentsApi.ts';

const RLM = '‏';
const LRM = '‎';

const line = (overrides: Partial<PurchaseRFQLineDto> = {}): PurchaseRFQLineDto => ({
  id: 1,
  product: 5,
  product_name: 'صنف',
  seq: 1,
  name_snapshot: 'صنف تجريبي',
  specs: 'مواصفات القياس',
  quantity: '10',
  unit_of_measure: 'قطعة',
  estimated_price: null,
  ...overrides,
});

const rfq = (lines: PurchaseRFQLineDto[]): Pick<PurchaseRFQDto, 'rfq_number' | 'lines'> => ({
  rfq_number: 'RFQ-1',
  lines,
});

test('العناوين السبعة معتمَدة — العبرية والعربية معاً، والمفتاح الأخير ملاحظات', () => {
  assert.equal(RFQ_SUPPLIER_XLSX_HEADERS.length, 7);
  assert.deepEqual(
    RFQ_SUPPLIER_XLSX_HEADERS.map((h) => h.key),
    ['seq', 'product', 'specs', 'quantity', 'unitOfMeasure', 'price', 'notes'],
  );
  const priceHeader = RFQ_SUPPLIER_XLSX_HEADERS.find((h) => h.key === 'price');
  assert.equal(priceHeader?.he, 'מחיר מוצע');
  assert.equal(priceHeader?.ar, 'السعر المقترح');
});

test('buildRfqSupplierRows: السعر التقديري لا يظهر في صفّ المورد — قائمة سماح', () => {
  const rows = buildRfqSupplierRows(rfq([line({ estimated_price: '42.50' })]));
  assert.equal(rows.length, 1);
  assert.equal((rows[0] as Record<string, unknown>).estimatedPrice, undefined);
  assert.equal(rows[0].seq, 1);
  assert.equal(rows[0].product, 'صنف تجريبي');
});

test('الملفّ المولَّد: صفّا العناوين موجودان بالترتيب (العبري أولاً)، والورقة rightToLeft', async () => {
  const buffer = await buildRfqSupplierXlsxBuffer(rfq([line()]));
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const sheet = workbook.worksheets[0];

  assert.equal(sheet.views[0]?.rightToLeft, true, 'الورقة تبدأ من اليمين');

  const heRow = sheet.getRow(1);
  const arRow = sheet.getRow(2);
  assert.equal(heRow.getCell(1).value, 'מס׳');
  assert.equal(heRow.getCell(6).value, 'מחיר מוצע');
  assert.equal(arRow.getCell(1).value, 'تسلسل');
  assert.equal(arRow.getCell(6).value, 'السعر المقترح');
});

test('عمود السعر فارغٌ لكل صفوف البيانات، ويحمل allowBlank على data validation', async () => {
  const buffer = await buildRfqSupplierXlsxBuffer(rfq([line(), line({ seq: 2, estimated_price: '99' })]));
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const sheet = workbook.worksheets[0];

  const priceColIndex = 6;
  for (const rowNumber of [3, 4]) {
    const cell = sheet.getRow(rowNumber).getCell(priceColIndex);
    assert.equal(cell.value, null, `عمود السعر في الصفّ ${rowNumber} يجب أن يكون فارغاً`);
    assert.equal(cell.dataValidation?.allowBlank, true, 'allowBlank إلزاميّ على عمود السعر');
  }
});

test('قيم الخلايا خاليةٌ من محارف RLM/LRM كلّها', async () => {
  const buffer = await buildRfqSupplierXlsxBuffer(rfq([line({ specs: 'قياس 10 سم', name_snapshot: 'صنف A' })]));
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const sheet = workbook.worksheets[0];

  sheet.eachRow((row) => {
    row.eachCell({ includeEmpty: false }, (cell) => {
      const value = typeof cell.value === 'string' ? cell.value : String(cell.value ?? '');
      assert.ok(!value.includes(RLM), `RLM موجودٌ في قيمة خلية: ${JSON.stringify(value)}`);
      assert.ok(!value.includes(LRM), `LRM موجودٌ في قيمة خلية: ${JSON.stringify(value)}`);
    });
  });
});

// ── الحارس: رقمٌ مميَّز لا يلتبس (٩٩٩٫٩٩) في السعر التقديري — يُفتَّش عنه
// نصّاً خامّاً في حمولة الطباعة **وملفّ Excel المولَّد معاً**. وجودُه في
// أيٍّ منهما إخفاقٌ صريح (قرار المالك 2026-09-03 على #108 §١١).
test('حارس التسرّب: ٩٩٩٫٩٩ لا يظهر في حمولة طباعة الطلبية ولا في ملفّ Excel', async () => {
  const sentinel = '999.99';
  const doc = rfq([line({ estimated_price: sentinel })]);

  const printRows = buildPurchaseRfqPrintRows(doc);
  assert.ok(!JSON.stringify(printRows).includes(sentinel), 'السعر التقديري تسرّب إلى حمولة الطباعة');

  const buffer = await buildRfqSupplierXlsxBuffer(doc);
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const sheet = workbook.worksheets[0];

  let found = false;
  sheet.eachRow((row) => {
    row.eachCell({ includeEmpty: false }, (cell) => {
      const raw = String(cell.value ?? '');
      if (raw.includes(sentinel)) found = true;
    });
  });
  assert.equal(found, false, 'السعر التقديري تسرّب إلى ملفّ Excel');
});
