import test from 'node:test';
import assert from 'node:assert/strict';

import {
  reportToXlsxBuffer,
  xlsxCell,
  xlsxHeaderLines,
  xlsxTotalsRow,
} from './reportXlsx.ts';
import type { ReportResultDto } from './reportFormat.ts';

const RESULT: ReportResultDto = {
  key: 'timesheet-daily',
  title: 'كشف الساعات اليومي',
  category: 'hr',
  description: '',
  columns: [
    { key: 'employee', header: 'الموظف', kind: 'text' },
    { key: 'd1', header: '1 سب', kind: 'text' },
    { key: 'd2', header: '2 أح', kind: 'text' },
    { key: 'total_hours', header: 'مجموع الساعات', kind: 'number', total: true },
    { key: 'net', header: 'الصافي', kind: 'money', total: true },
  ],
  rows: [
    { employee: 'عمر', d1: '8', d2: '', total_hours: '8', net: '2451.25' },
    { employee: 'سامي', d1: 'غ', d2: 'ت 30', total_hours: '0', net: '2600' },
  ],
  totals: { total_hours: '8', net: '5051.25' },
  generated_at: '2026-08-20T10:00:00',
};

test('المال والأرقام تُكتب أعداداً — وإلا لم تعمل SUM في الملف', () => {
  assert.deepEqual(xlsxCell('2451.25', 'money'), { value: 2451.25, numFmt: '#,##0.00' });
  assert.equal(xlsxCell('8', 'number').value, 8);
});

test('خانة الساعات عددٌ ولو كان عمودها نصّياً، و«غ» تبقى نصّاً', () => {
  assert.equal(xlsxCell('7.5', 'text').value, 7.5);
  assert.equal(xlsxCell('غ', 'text').value, 'غ');
  assert.equal(xlsxCell('ت 30', 'text').value, 'ت 30');
});

test('الفارغ خلية فارغة لا شرطة — الشرطة نصّ يكسر الحساب', () => {
  assert.equal(xlsxCell('', 'money').value, null);
  assert.equal(xlsxCell(null, 'text').value, null);
});

test('الترويسة تحمل الشركة والفترة وتاريخ التوليد ومَن ولّده', () => {
  const lines = xlsxHeaderLines(RESULT, {
    company: 'شركة الكشوف', period: 'الفترة من ٠١/٠٨ إلى ٣١/٠٨', generatedBy: 'ثابت',
  });
  assert.equal(lines[0], 'كشف الساعات اليومي');
  assert.equal(lines[1], 'شركة الكشوف');
  assert.ok(lines.some((l) => l.startsWith('تاريخ التوليد:')));
  assert.ok(lines.some((l) => l === 'ولّده: ثابت'));
});

test('صفّ الإجماليات يحاذي الأعمدة ويعنون نفسه في أولها', () => {
  const totals = xlsxTotalsRow(RESULT);
  assert.ok(totals);
  assert.equal(totals[0].value, 'الإجمالي');
  assert.equal(totals[1].value, null);
  assert.equal(totals[4].value, 5051.25);
  assert.equal(xlsxTotalsRow({ ...RESULT, totals: {} }), null);
});

test('الملف المولَّد يُقرأ: خلية مال عدد، والورقة عربية وعناوينها مجمّدة', async () => {
  const buffer = await reportToXlsxBuffer(RESULT, {
    company: 'شركة الكشوف', period: 'آب', generatedBy: 'ثابت',
  });
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const sheet = workbook.worksheets[0];

  const view = sheet.views[0];
  assert.equal(view.rightToLeft, true, 'الورقة تبدأ من اليمين');
  assert.equal(view.state, 'frozen');
  assert.ok((view.ySplit ?? 0) > 0, 'صفّ العناوين مثبَّت');

  const headerRow = sheet.getRow(view.ySplit as number);
  assert.equal(headerRow.getCell(1).value, 'الموظف');

  const firstData = sheet.getRow((view.ySplit as number) + 1);
  assert.equal(firstData.getCell(1).value, 'عمر');
  assert.equal(firstData.getCell(2).value, 8, 'الساعات عدد لا نصّ');
  assert.equal(firstData.getCell(5).value, 2451.25, 'المال عدد لا نصّ');
  assert.equal(firstData.getCell(3).value, null, 'اليوم بلا سجلّ خلية فارغة');

  const marks = sheet.getRow((view.ySplit as number) + 2);
  assert.equal(marks.getCell(2).value, 'غ');

  const totalsRow = sheet.getRow((view.ySplit as number) + 3);
  assert.equal(totalsRow.getCell(1).value, 'الإجمالي');
  assert.equal(totalsRow.getCell(5).value, 5051.25);
});

test('نصٌّ شكله رقم لكنه يفقد شيئاً بالتحويل يبقى نصّاً — رقم الشيك «0042»', () => {
  // THA-474: الزرّ على كل تقارير المنصة، وأعمدة نصّية كثيرة فيها أرقام
  // مستندات — تحويلها يمحو أصفارها البادئة ويسلّم رقماً ليس رقم المستند.
  assert.equal(xlsxCell('0042', 'text').value, '0042');
  assert.equal(xlsxCell('007', 'text').value, '007');
  // والساعات تبقى أرقاماً كما كانت — لا تراجع عن سبب القاعدة أصلاً.
  assert.equal(xlsxCell('8', 'text').value, 8);
  assert.equal(xlsxCell('7.5', 'text').value, 7.5);
  assert.equal(xlsxCell('0', 'text').value, 0);
  assert.equal(xlsxCell('0.5', 'text').value, 0.5);
  // وعمود المال لا يتأثر بالقاعدة: نوعه مُعلَن فيُحوَّل دائماً.
  assert.equal(xlsxCell('0042.50', 'money').value, 42.5);
});
