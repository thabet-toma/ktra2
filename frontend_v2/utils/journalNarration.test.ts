import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildLineNarration,
  buildHeaderNarration,
  isGeneratedNarration,
  isGeneratedLineNarration,
  type NarrationLine,
} from './journalNarration.ts';

const line = (over: Partial<NarrationLine> = {}): NarrationLine => ({
  accountName: '',
  partnerName: '',
  debit: '',
  credit: '',
  ...over,
});

test('بيان السطر يتولد من اسم الحساب وحده', () => {
  assert.equal(
    buildLineNarration(line({ accountName: 'النقدية (Cash)', debit: '500' }), ''),
    'النقدية',
  );
});

test('بيان السطر يلحق اسم الطرف بالحساب', () => {
  assert.equal(
    buildLineNarration(
      line({ accountName: 'المدينون التجاريون', partnerName: 'شركة الأمل', debit: '500' }),
      '',
    ),
    'المدينون التجاريون — شركة الأمل',
  );
});

test('البيان الإجمالي يتقدّم على اسم الحساب في بيان السطر', () => {
  assert.equal(
    buildLineNarration(line({ accountName: 'النقدية', debit: '500' }), 'تحصيل دفعة نقدية'),
    'تحصيل دفعة نقدية',
  );
  assert.equal(
    buildLineNarration(
      line({ accountName: 'النقدية', partnerName: 'شركة الأمل', debit: '500' }),
      'تحصيل دفعة نقدية',
    ),
    'تحصيل دفعة نقدية — شركة الأمل',
  );
});

test('السطر الفارغ بلا حساب يعطي بياناً فارغاً', () => {
  assert.equal(buildLineNarration(line(), ''), '');
  assert.equal(buildLineNarration(line(), 'بيان عام'), '');
});

test('لاحقة اسم الحساب اللاتينية تُحذف والرمز يبقى خارج البيان', () => {
  assert.equal(
    buildLineNarration(line({ accountName: 'البنوك (Banks)', credit: '90' }), ''),
    'البنوك',
  );
});

test('البيان الإجمالي يتولد بصيغة «من ح/ … إلى ح/ …»', () => {
  const lines = [
    line({ accountName: 'النقدية (Cash)', debit: '500' }),
    line({ accountName: 'مبيعات المنتجات', credit: '500' }),
  ];
  assert.equal(buildHeaderNarration(lines), 'من ح/ النقدية إلى ح/ مبيعات المنتجات');
});

test('البيان الإجمالي يجمع الأطراف المتعددة ويختصر ما زاد عن اثنين', () => {
  const lines = [
    line({ accountName: 'النقدية', debit: '300' }),
    line({ accountName: 'البنوك', debit: '200' }),
    line({ accountName: 'مبيعات المنتجات', credit: '400' }),
    line({ accountName: 'إيرادات أخرى', credit: '50' }),
    line({ accountName: 'ضريبة القيمة المضافة - مخرجات', credit: '50' }),
  ];
  assert.equal(
    buildHeaderNarration(lines),
    'من ح/ النقدية، البنوك إلى ح/ مبيعات المنتجات، إيرادات أخرى وغيرها',
  );
});

test('البيان الإجمالي يبقى فارغاً قبل اكتمال طرفَي القيد', () => {
  assert.equal(buildHeaderNarration([]), '');
  assert.equal(buildHeaderNarration([line({ accountName: 'النقدية', debit: '500' })]), '');
});

test('السطر بلا مبلغ لا يدخل البيان الإجمالي', () => {
  const lines = [
    line({ accountName: 'النقدية', debit: '500' }),
    line({ accountName: 'مبيعات المنتجات', credit: '500' }),
    line({ accountName: 'المخزون' }),
  ];
  assert.equal(buildHeaderNarration(lines), 'من ح/ النقدية إلى ح/ مبيعات المنتجات');
});

test('البيان المولَّد يُعرف فيُستبدل، والمكتوب يدوياً يُصان', () => {
  const lines = [
    line({ accountName: 'النقدية', debit: '500' }),
    line({ accountName: 'مبيعات المنتجات', credit: '500' }),
  ];
  assert.equal(isGeneratedNarration('', lines), true);
  assert.equal(isGeneratedNarration('من ح/ النقدية إلى ح/ مبيعات المنتجات', lines), true);
  assert.equal(isGeneratedNarration('النقدية', lines), true);
  assert.equal(isGeneratedNarration('تحصيل دفعة من العميل', lines), false);
});

test('بيان السطر المولَّد يبقى معروفاً بعد تغيّر البيان الإجمالي', () => {
  const l = line({ accountName: 'النقدية (Cash)', partnerName: 'شركة الأمل', debit: '500' });
  assert.equal(isGeneratedLineNarration('', l, 'بيان عام'), true);
  assert.equal(isGeneratedLineNarration('بيان عام — شركة الأمل', l, 'بيان عام'), true);
  // بيان إجمالي قديم: السطر ما زال مولَّداً لأنه يطابق حسابه وطرفه.
  assert.equal(isGeneratedLineNarration('النقدية — شركة الأمل', l, 'بيان جديد'), true);
  assert.equal(isGeneratedLineNarration('دفعة أولى بموجب الاتفاق', l, 'بيان عام'), false);
});
