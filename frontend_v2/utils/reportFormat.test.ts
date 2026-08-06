import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  formatReportCell,
  initialFilterValues,
  isNumericKind,
  reportFileName,
  reportQuery,
  reportToCsv,
  type ReportResultDto,
} from './reportFormat.ts';

test('المال بفاصل آلاف وبلا أصفار زائدة', () => {
  assert.equal(formatReportCell('30490.00', 'money'), '30,490');
  assert.equal(formatReportCell('187.50', 'money'), '187.5');
  assert.equal(formatReportCell('1234.56', 'money'), '1,234.56');
});

test('الكميات والأعداد الصحيحة لكلٍّ دقّته', () => {
  assert.equal(formatReportCell('5.000', 'number'), '5');
  assert.equal(formatReportCell('2.125', 'number'), '2.125');
  assert.equal(formatReportCell('7.9', 'int'), '8');
});

test('الفراغ شرطة لا سلسلة خالية', () => {
  assert.equal(formatReportCell(null, 'text'), '—');
  assert.equal(formatReportCell('', 'money'), '—');
  assert.equal(formatReportCell(undefined, 'date'), '—');
  // الصفر قيمة لا فراغ
  assert.equal(formatReportCell(0, 'money'), '0');
});

test('التاريخ يُعرض محلياً ويرتدّ لنصّه إن كان غير قياسي', () => {
  assert.equal(formatReportCell('2026-06-10', 'date'), '10/06/2026');
  assert.equal(formatReportCell('غير معروف', 'date'), 'غير معروف');
});

test('الأعمدة الرقمية وحدها تُحاذى رقمياً', () => {
  assert.equal(isNumericKind('money'), true);
  assert.equal(isNumericKind('number'), true);
  assert.equal(isNumericKind('int'), true);
  assert.equal(isNumericKind('text'), false);
  assert.equal(isNumericKind('date'), false);
});

test('الفلاتر الفارغة لا تدخل الرابط', () => {
  assert.deepEqual(
    reportQuery({ from: '2026-01-01', to: '  ', partner: '', product: '7' }),
    { from: '2026-01-01', product: '7' },
  );
});

test('القيم الابتدائية من افتراضي الخادم ثم البذرة', () => {
  const filters = [
    { key: 'from', label: 'من', kind: 'date', default: '2026-01-01' },
    { key: 'to', label: 'إلى', kind: 'date' },
    { key: 'partner', label: 'العميل', kind: 'customer' },
  ];
  assert.deepEqual(initialFilterValues(filters, { partner: '9' }), {
    from: '2026-01-01', to: '', partner: '9',
  });
});

const RESULT: ReportResultDto = {
  key: 'sales-invoices',
  title: 'سجل فواتير البيع',
  category: 'sales',
  description: '',
  columns: [
    { key: 'invoice_number', header: 'رقم المستند', kind: 'text' },
    { key: 'invoice_date', header: 'التاريخ', kind: 'date' },
    { key: 'grand_total', header: 'الإجمالي', kind: 'money', total: true },
  ],
  rows: [
    { invoice_number: 'SI-1', invoice_date: '2026-06-10', grand_total: '116.00' },
    { invoice_number: 'SI-"2"', invoice_date: null, grand_total: '1000' },
  ],
  totals: { grand_total: '1116.00' },
  generated_at: '2026-08-06T10:00:00',
};

test('CSV يبدأ بـBOM ويهرّب علامات الاقتباس ويُذيَّل بالإجمالي', () => {
  const csv = reportToCsv(RESULT);
  assert.equal(csv.startsWith('﻿'), true, 'بلا BOM تُشوَّه العربية في Excel');
  const lines = csv.replace('﻿', '').split('\n');
  assert.equal(lines[0], '"رقم المستند","التاريخ","الإجمالي"');
  assert.equal(lines[1], '"SI-1","10/06/2026","116"');
  assert.equal(lines[2], '"SI-""2""","—","1,000"');
  assert.equal(lines[3], '"الإجمالي","","1,116"');
});

test('CSV بلا إجماليات لا يضيف سطراً فارغاً', () => {
  const csv = reportToCsv({ ...RESULT, totals: {} });
  assert.equal(csv.replace('﻿', '').split('\n').length, 3);
});

test('اسم الملف يجمع العنوان والتاريخ وينظّف المحارف الممنوعة', () => {
  assert.equal(reportFileName(RESULT), 'سجل فواتير البيع — 2026-08-06.csv');
  assert.equal(
    reportFileName({ ...RESULT, title: 'أرباح/خسائر' }, 'pdf'),
    'أرباح-خسائر — 2026-08-06.pdf',
  );
});
