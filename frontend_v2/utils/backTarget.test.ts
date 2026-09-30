import { test } from 'node:test';
import assert from 'node:assert/strict';
import { historyCanGoBack, resolveBackTarget } from './backTarget.ts';

test('قراءة سابقة التبويب من حالة الموجّه', () => {
  assert.equal(historyCanGoBack(null), false, 'تبويب فُتح على المستند مباشرةً');
  assert.equal(historyCanGoBack({ idx: 0 }), false, 'أول مُدخل في هذا التبويب');
  assert.equal(historyCanGoBack({ idx: 1 }), true);
  assert.equal(historyCanGoBack({ idx: '2' }), false, 'قيمة غير رقمية لا تُصدَّق');
  assert.equal(historyCanGoBack('idx=3'), false);
});

test('مع سابقة → رجوعٌ عادي', () => {
  const t = resolveBackTarget({ canGoBack: true, currentPath: '/sales/invoices/12' });
  assert.equal(t.kind, 'history');
  assert.equal(t.label, 'رجوع');
});

test('بلا سابقة → قائمة الشاشة نفسها، واسمها على الزرّ', () => {
  const t = resolveBackTarget({
    canGoBack: false,
    currentPath: '/sales/invoices/12',
    listPath: '/sales/invoices',
    listLabel: 'فواتير المبيعات',
  });
  assert.equal(t.kind, 'fallback');
  assert.equal(t.path, '/sales/invoices');
  assert.equal(t.label, 'فواتير المبيعات');
  assert.match(t.hint, /لا توجد صفحة سابقة/);
  assert.ok(t.hint.startsWith('رجوع'), 'اسم الزرّ يبقى «رجوع» مهما تغيّرت الوجهة');
  assert.ok(t.hint.includes(t.label), 'النصّ المرئي محتوىً في الاسم المتاح (WCAG 2.5.3)');
});

test('بلا سابقة ونحن على القائمة ذاتها → الرئيسية لا حلقة على النفس', () => {
  const t = resolveBackTarget({
    canGoBack: false,
    currentPath: '/sales/invoices',
    listPath: '/sales/invoices',
    listLabel: 'فواتير المبيعات',
  });
  assert.equal(t.path, '/dashboard');
  assert.equal(t.label, 'الرئيسية');
});

test('الشرطة المائلة الزائدة لا تخدع المقارنة', () => {
  const t = resolveBackTarget({
    canGoBack: false,
    currentPath: '/sales/invoices/',
    listPath: '/sales/invoices',
    listLabel: 'فواتير المبيعات',
  });
  assert.equal(t.path, '/dashboard');
});

test('شاشة بلا مسار قائمة معروف → الرئيسية', () => {
  const t = resolveBackTarget({ canGoBack: false, currentPath: '/products/5' });
  assert.equal(t.path, '/dashboard');
  assert.equal(t.label, 'الرئيسية');
});

test('#73: تبويبٌ فُتح من قائمة → «رجوع» إلى القائمة نفسها بفلترها وصفحتها لا إلى رأسها', () => {
  const t = resolveBackTarget({
    canGoBack: false,
    currentPath: '/partners/12',
    listPath: '/partners-directory',
    listLabel: 'دليل الأطراف',
    openerPath: '/sales/customers?q=%D8%A3%D8%AD%D9%85%D8%AF&page=3&sel=12',
    openerLabel: 'عملاء المبيعات',
  });
  assert.equal(t.kind, 'fallback');
  assert.equal(t.path, '/sales/customers?q=%D8%A3%D8%AD%D9%85%D8%AF&page=3&sel=12');
  assert.equal(t.label, 'عملاء المبيعات');
  assert.ok(t.hint.startsWith('رجوع') && t.hint.includes(t.label));
});

test('مسار الفاتح لا يُصدَّق إن كان خارجياً أو هو الصفحة نفسها', () => {
  const base = { canGoBack: false, currentPath: '/partners/12', listPath: '/partners-directory', listLabel: 'دليل الأطراف' };
  assert.equal(resolveBackTarget({ ...base, openerPath: '//evil.example/x' }).path, '/partners-directory');
  assert.equal(resolveBackTarget({ ...base, openerPath: 'https://evil.example/' }).path, '/partners-directory');
  assert.equal(resolveBackTarget({ ...base, openerPath: '/partners/12?tab=edit' }).path, '/partners-directory');
  // السابقةُ الحقيقية تبقى أوّلاً: تنقّلٌ داخل التبويب الجديد يرجع خطوةً لا إلى الفاتح.
  assert.equal(resolveBackTarget({ ...base, canGoBack: true, openerPath: '/sales/customers' }).kind, 'history');
});
