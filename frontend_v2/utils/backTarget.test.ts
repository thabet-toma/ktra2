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
