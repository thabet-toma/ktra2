import assert from 'node:assert/strict';
import test from 'node:test';

import { enterOfficeShell, enterPlatformShell, platformShellActive } from './officeShell.ts';

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
