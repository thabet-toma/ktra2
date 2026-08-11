import assert from 'node:assert/strict';
import test from 'node:test';

import {
  companyWorkspaceDeepLink,
  enterOfficeShell,
  enterPlatformShell,
  platformShellActive,
} from './officeShell.ts';

/** عيّنة من مسارات الشاشات كما في VIEW_PATHS داخل App. */
const VIEW_PATHS = [
  '/dashboard', '/sales/invoices', '/purchase-invoices', '/items',
  '/accounting/journals', '/accounting/banks', '/deals', '/super-admin',
  '/accountant/company/engagements',
];

const memoryStorage = (seed: Record<string, string> = {}) => {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => (map.has(key) ? map.get(key)! : null),
    setItem: (key: string, value: string) => { map.set(key, String(value)); },
    removeItem: (key: string) => { map.delete(key); },
    clear: () => map.clear(),
    key: () => null,
    length: 0,
  } as unknown as Storage;
};

const withStores = (local: Record<string, string>, session: Record<string, string>) => {
  const stores = { local: memoryStorage(local), session: memoryStorage(session) };
  (globalThis as any).window = { localStorage: stores.local, sessionStorage: stores.session };
  (globalThis as any).localStorage = stores.local;
  (globalThis as any).sessionStorage = stores.session;
  return stores;
};

test('مسار /office يلغي تجاوز قشرة المنصة مهما كان المخزَّن', () => {
  const stores = withStores({}, { ktra_shell: 'platform' });
  assert.equal(platformShellActive('/office/clients/5'), false);
  assert.equal(stores.session.getItem('ktra_shell'), null);
});

test('التجاوز فعّال خارج /office وحدَه حين يكون مخزَّناً', () => {
  const stores = withStores({}, { ktra_shell: 'platform' });
  assert.equal(platformShellActive('/super-admin'), true);
  assert.equal(stores.session.getItem('ktra_shell'), 'platform');
  withStores({}, {});
  assert.equal(platformShellActive('/super-admin'), false);
});

test('الدخول للمكتب يحفظ الشركة التجارية الحالية ويلغي التجاوز', () => {
  const stores = withStores({ tenantId: '4' }, { ktra_shell: 'platform' });
  enterOfficeShell();
  assert.equal(stores.session.getItem('ktra_shell'), null);
  assert.equal(stores.session.getItem('ktra_shell_tenant'), '4');
  assert.equal(stores.local.getItem('tenantId'), '4');
});

test('الخروج للمنصة يعيد الشركة المحفوظة ويمسح الفرع', () => {
  const stores = withStores(
    { tenantId: '9', branchId: '3' },
    { ktra_shell_tenant: '4' },
  );
  enterPlatformShell();
  assert.equal(stores.session.getItem('ktra_shell'), 'platform');
  assert.equal(stores.local.getItem('tenantId'), '4');
  assert.equal(stores.local.getItem('branchId'), null);
  assert.equal(stores.session.getItem('ktra_shell_tenant'), null);
});

test('بلا شركة محفوظة يبقى الاختيار الحالي كما هو', () => {
  const stores = withStores({ tenantId: '7' }, {});
  enterPlatformShell();
  assert.equal(stores.session.getItem('ktra_shell'), 'platform');
  assert.equal(stores.local.getItem('tenantId'), '7');
});

test('رحلة ذهاب وإياب: مكتب ← زبون ← منصة ← مكتب', () => {
  const stores = withStores({ tenantId: '4' }, {});
  enterOfficeShell();                       // فتح واجهة المكتب من لوحة المنصة
  stores.local.setItem('tenantId', '9');    // فتح ملف زبون داخل المكتب
  enterPlatformShell();                     // «العودة للوحة المنصة»
  assert.equal(stores.local.getItem('tenantId'), '4');
  assert.equal(platformShellActive('/super-admin'), true);
  enterOfficeShell();                       // «العودة لواجهة المكتب»
  assert.equal(platformShellActive('/office'), false);
  assert.equal(stores.session.getItem('ktra_shell_tenant'), '4');
});

test('رابط شاشة شركة مباشر يحسم القشرة التجارية لحساب المحاسب', () => {
  // البلاغ: فتح «فاتورة مبيعات جديدة» كان يعرض لوحة المكتب لأن القشرة
  // تُحسم بنوع الحساب وحده والمسار لا رأي له.
  assert.equal(companyWorkspaceDeepLink('/sales/invoices/new', VIEW_PATHS), true);
  assert.equal(companyWorkspaceDeepLink('/sales/invoices', VIEW_PATHS), true);
  assert.equal(companyWorkspaceDeepLink('/accounting/banks', VIEW_PATHS), true);
  assert.equal(companyWorkspaceDeepLink('/deals/12', VIEW_PATHS), true);
});

test('بيت المكتب ومسارات المنصة ليست روابط شاشات شركة', () => {
  assert.equal(companyWorkspaceDeepLink('/', VIEW_PATHS), false);
  assert.equal(companyWorkspaceDeepLink('', VIEW_PATHS), false);
  assert.equal(companyWorkspaceDeepLink('/office', VIEW_PATHS), false);
  assert.equal(companyWorkspaceDeepLink('/office/clients/5', VIEW_PATHS), false);
  // «الرئيسية» وجهة تلقائية لا نيّة صريحة — تبقى للمكتب.
  assert.equal(companyWorkspaceDeepLink('/dashboard', VIEW_PATHS), false);
  // لوحة المنصة تُفتح بزر «العودة للوحة المنصة» لا بالرابط (اختبار قائم يحرسه).
  assert.equal(companyWorkspaceDeepLink('/super-admin', VIEW_PATHS), false);
  assert.equal(companyWorkspaceDeepLink('/accountant/company/engagements', VIEW_PATHS), false);
});

test('مسار مجهول لا يُحسب شاشة شركة', () => {
  assert.equal(companyWorkspaceDeepLink('/nope/whatever', VIEW_PATHS), false);
  // ولا يكفي أن يكون المسار بادئة نصية لشاشة — الحدّ عند الشرطة.
  assert.equal(companyWorkspaceDeepLink('/itemsx', VIEW_PATHS), false);
});
