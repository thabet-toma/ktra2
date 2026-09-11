import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filterBillingRecords, sumDecimalAmounts } from './billingRecords.ts';

test('sumDecimalAmounts يجمع مبالغ نصية عشرية بدقة بالسنتات بلا أخطاء فاصلة عائمة', () => {
  // مبالغ موجبة قياسية
  assert.equal(sumDecimalAmounts(['290.00', '10.50']), '300.50');
  assert.equal(sumDecimalAmounts(['0.10', '0.20']), '0.30');

  // أعداد بدون كسر
  assert.equal(sumDecimalAmounts(['100', '50']), '150.00');

  // كسر من منزلة واحدة
  assert.equal(sumDecimalAmounts(['10.5', '20.25']), '30.75');

  // مبالغ فارغة أو null أو undefined
  assert.equal(sumDecimalAmounts([]), '0.00');
  assert.equal(sumDecimalAmounts([null, undefined, '', '   ']), '0.00');
  assert.equal(sumDecimalAmounts(['100.00', null, '50.00']), '150.00');

  // مبالغ سالبة
  assert.equal(sumDecimalAmounts(['100.00', '-30.00']), '70.00');
  assert.equal(sumDecimalAmounts(['-50.00', '-20.50']), '-70.50');
  assert.equal(sumDecimalAmounts(['30.00', '-50.00']), '-20.00');
});

test('filterBillingRecords يصفي السجلات بالبحث في اسم الشركة أو رقم الفاتورة', () => {
  const records = [
    { company_name: 'شركة النور للتقنية', invoice_number: 'INV-2026-001' },
    { company_name: 'مؤسسة الأفق للتجارة', invoice_number: 'INV-2026-002' },
    { company_name: 'شركة الرواد', invoice_number: null },
  ];

  // بحث فارغ يُعيد الكل
  assert.equal(filterBillingRecords(records, '').length, 3);
  assert.equal(filterBillingRecords(records, '   ').length, 3);

  // بالشركة
  const byCompany = filterBillingRecords(records, 'النور');
  assert.equal(byCompany.length, 1);
  assert.equal(byCompany[0].company_name, 'شركة النور للتقنية');

  // برقم الفاتورة
  const byInvoice = filterBillingRecords(records, '002');
  assert.equal(byInvoice.length, 1);
  assert.equal(byInvoice[0].company_name, 'مؤسسة الأفق للتجارة');

  // عدم وجود تطابق
  assert.equal(filterBillingRecords(records, 'فاتورة_غير_موجودة').length, 0);
});
