import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleLinks, groupVisible, type NavAccessLink } from './navAccess.ts';
import {
  devicesNavPlacement,
  invoiceActionPermissions,
  memberOverrideForCheckbox,
  moduleAllowsView,
  moduleForView,
  permForView,
} from './viewPermissions.ts';
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

test('تبويب المحاسب القانوني يُمنع قبل أي import ما لم يصل عَلَم ترخيصه', () => {
  assert.equal(moduleForView('company-accountant-engagements'), 'accountant_portal');
  // فشل مغلق: لا أعلام أصلاً، أو عَلَم مطفأ، أو حمولة بلا المفتاح.
  assert.equal(moduleAllowsView('company-accountant-engagements', null), false);
  assert.equal(moduleAllowsView('company-accountant-engagements', {}), false);
  assert.equal(moduleAllowsView('company-accountant-engagements', { accountant_portal: false }), false);
  assert.equal(moduleAllowsView('company-accountant-engagements', { accountant_portal: true }), true);
});

test('شاشة الأجهزة الحساسة تُمنع قبل أي import ما لم يصل عَلَم ترخيص وحدتها', () => {
  assert.equal(moduleForView('sensitive-devices'), 'sensitive_devices');
  assert.equal(permForView('sensitive-devices'), 'devices.registry.view');
  // فشل مغلق كسابقتها: بلا أعلام، أو بعَلَم مطفأ، أو بحمولة لا تحمل المفتاح.
  assert.equal(moduleAllowsView('sensitive-devices', null), false);
  assert.equal(moduleAllowsView('sensitive-devices', {}), false);
  assert.equal(moduleAllowsView('sensitive-devices', { sensitive_devices: false }), false);
  // ترخيص وحدةٍ أخرى لا يفتح هذه.
  assert.equal(moduleAllowsView('sensitive-devices', { accountant_portal: true }), false);
  assert.equal(moduleAllowsView('sensitive-devices', { sensitive_devices: true }), true);
});

test('بند الأجهزة الحساسة يلزمه الترخيص والصلاحية معاً', () => {
  const link: NavAccessLink[] = [
    { key: 'sensitive-devices', perm: permForView('sensitive-devices') },
  ];
  // الصلاحية وحدها لا تكفي — الترخيص يُفحَص بجانبها في الشريط الجانبي.
  assert.equal(visibleLinks(link, canOf(['devices.registry.view'])).length, 1);
  assert.equal(visibleLinks(link, canOf([])).length, 0);
  assert.equal(
    visibleLinks(link, canOf(['devices.registry.view'])).length === 1
      && moduleAllowsView('sensitive-devices', { sensitive_devices: false }),
    false,
  );
});

test('شاشة بطاقات الكفالة تُمنع قبل أي import ما لم يصل عَلَم ترخيص وحدتها', () => {
  assert.equal(moduleForView('after-sales'), 'after_sales');
  assert.equal(permForView('after-sales'), 'aftersales.warranty.view');
  // فشل مغلق: بلا أعلام، أو بعَلَم مطفأ، أو بحمولة لا تحمل المفتاح.
  assert.equal(moduleAllowsView('after-sales', null), false);
  assert.equal(moduleAllowsView('after-sales', {}), false);
  assert.equal(moduleAllowsView('after-sales', { after_sales: false }), false);
  // ترخيص وحدة الأجهزة الحساسة لا يفتح خدمة ما بعد البيع — وحدتان مستقلتان.
  assert.equal(moduleAllowsView('after-sales', { sensitive_devices: true }), false);
  assert.equal(moduleAllowsView('after-sales', { after_sales: true }), true);
});

test('بند بطاقات الكفالة يلزمه الترخيص والصلاحية معاً', () => {
  const link: NavAccessLink[] = [
    { key: 'after-sales', perm: permForView('after-sales') },
  ];
  assert.equal(visibleLinks(link, canOf(['aftersales.warranty.view'])).length, 1);
  assert.equal(visibleLinks(link, canOf([])).length, 0);
  // الصلاحية وحدها لا تكفي — الترخيص يُفحَص بجانبها في الشريط الجانبي.
  assert.equal(
    visibleLinks(link, canOf(['aftersales.warranty.view'])).length === 1
      && moduleAllowsView('after-sales', { after_sales: false }),
    false,
  );
});

test('موضع بند الأجهزة الحساسة يتبع ترخيص الوحدتين — بند واحد لا اثنان', () => {
  // بلا ترخيص سجل الأجهزة لا يظهر البند أصلاً، ولو رُخِّصت ما بعد البيع.
  assert.equal(devicesNavPlacement(null), 'hidden');
  assert.equal(devicesNavPlacement({}), 'hidden');
  assert.equal(devicesNavPlacement({ after_sales: true }), 'hidden');
  // سجل الأجهزة وحده ⇒ يبقى حيث هو اليوم (عقد THA-45: تُطفأ وتُشغَّل باستقلال).
  assert.equal(devicesNavPlacement({ sensitive_devices: true }), 'standalone');
  assert.equal(
    devicesNavPlacement({ sensitive_devices: true, after_sales: false }),
    'standalone',
  );
  // الوحدتان معاً ⇒ ينتقل تحت «خدمة ما بعد البيع» (طلب المالك: السجل إجراء ضمن النظام).
  assert.equal(
    devicesNavPlacement({ sensitive_devices: true, after_sales: true }),
    'after-sales',
  );
});

test('الشركة التجارية لا تحمل أي شاشة من شاشات مكتب المحاسبة', () => {
  // شاشات المكتب تعيش في قشرته المستقلة، فلا تُذكر في خريطة الشاشات التجارية.
  for (const officeView of ['accountant-companies', 'accountant-tax-periods', 'accountant-profile']) {
    assert.equal(moduleForView(officeView), undefined);
  }
  assert.equal(moduleAllowsView('sales-invoices', null), true);
});

test('كل اختصار في الشريط العلوي يملك رمزاً دلالياً', () => {
  assert.equal(iconForShortcut('sales-invoices'), 'sales-invoice');
  assert.equal(iconForShortcut('purchase-invoices'), 'purchase-invoice');
  for (const shortcut of SHORTCUTABLE_VIEWS) {
    assert.notEqual(iconForShortcut(shortcut.view), 'zap');
  }
});
