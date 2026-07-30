import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleLinks, groupVisible, type NavAccessLink } from './navAccess.ts';
import { invoiceActionPermissions, memberOverrideForCheckbox } from './viewPermissions.ts';
import { iconForShortcut, SHORTCUTABLE_VIEWS } from './quickShortcuts.ts';

const links: NavAccessLink[] = [
  { key: 'sales-invoices', perm: 'sales.invoice.view' },
  { key: 'sales-settings', perm: 'sales.settings.manage' },
  { key: 'gallery' }, // بلا صلاحية = مفتوح للجميع
];

const canOf = (granted: string[]) => (k: string) => granted.includes(k);

test('يُخفي الرابط الذي لا يملك المستخدم صلاحيته', () => {
  const out = visibleLinks(links, canOf(['sales.invoice.view']));
  assert.deepEqual(out.map((l) => l.key), ['sales-invoices', 'gallery']);
});

test('الرابط بلا perm يبقى ظاهراً دائماً', () => {
  const out = visibleLinks(links, canOf([]));
  assert.deepEqual(out.map((l) => l.key), ['gallery']);
});

test('المجموعة تظهر إن ظهر أحد أبنائها', () => {
  const gated = links.slice(0, 2);
  assert.equal(groupVisible(gated, canOf(['sales.settings.manage'])), true);
  assert.equal(groupVisible(gated, canOf([])), false);
});

test('المجموعة ذات الرابط المفتوح تظهر دائماً', () => {
  assert.equal(groupVisible(links, canOf([])), true);
});

test('roles القديمة تبقى مُحترمة إلى جانب الصلاحيات', () => {
  const legacy: NavAccessLink[] = [
    { key: 'points-history', roles: ['manager', 'employee'] },
    { key: 'users', roles: ['manager'] },
  ];
  const out = visibleLinks(legacy, canOf([]), 'employee');
  assert.deepEqual(out.map((l) => l.key), ['points-history']);
});

test('الرابط الذي يجمع perm و roles يلزمه الاثنان', () => {
  const both: NavAccessLink[] = [
    { key: 'permissions', perm: 'admin.permissions.manage', roles: ['manager'] },
  ];
  assert.equal(visibleLinks(both, canOf(['admin.permissions.manage']), 'manager').length, 1);
  assert.equal(visibleLinks(both, canOf(['admin.permissions.manage']), 'employee').length, 0);
  assert.equal(visibleLinks(both, canOf([]), 'manager').length, 0);
});

test('حفظ وترحيل فاتورة جديدة يحتاج صلاحيتَي الإنشاء والترحيل', () => {
  assert.deepEqual(
    invoiceActionPermissions('sales', true, canOf(['sales.invoice.create', 'sales.invoice.post'])),
    { canSave: true, canPost: true, canSaveAndPost: true },
  );
  assert.equal(
    invoiceActionPermissions('sales', true, canOf(['sales.invoice.create'])).canSaveAndPost,
    false,
  );
});

test('حفظ وترحيل مسودة قائمة يحتاج التعديل والترحيل مع بقاء الترحيل المستقل متاحاً للمحاسب', () => {
  const accountant = invoiceActionPermissions('purchase', false, canOf(['purchase.invoice.post']));
  assert.deepEqual(accountant, { canSave: false, canPost: true, canSaveAndPost: false });

  const editor = invoiceActionPermissions(
    'purchase',
    false,
    canOf(['purchase.invoice.edit', 'purchase.invoice.post']),
  );
  assert.deepEqual(editor, { canSave: true, canPost: true, canSaveAndPost: true });
});

test('خانة صلاحية العضو تُخزَّن تجاوزاً فقط إن خالفت دوره', () => {
  // الدور يمنع والمدير يؤشّر ⇒ منح صريح
  assert.equal(memberOverrideForCheckbox(false, true), true);
  // الدور يمنح والمدير يُزيل التأشير ⇒ منع صريح
  assert.equal(memberOverrideForCheckbox(true, false), false);
  // العودة لما يعطيه الدور ⇒ حذف التجاوز
  assert.equal(memberOverrideForCheckbox(true, true), null);
  assert.equal(memberOverrideForCheckbox(false, false), null);
});

test('كل اختصار في الشريط العلوي يملك رمزاً دلالياً', () => {
  assert.equal(iconForShortcut('sales-invoices'), 'sales-invoice');
  assert.equal(iconForShortcut('purchase-invoices'), 'purchase-invoice');
  for (const shortcut of SHORTCUTABLE_VIEWS) {
    assert.notEqual(iconForShortcut(shortcut.view), 'zap');
  }
});
