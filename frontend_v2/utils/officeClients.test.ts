import assert from 'node:assert/strict';
import test from 'node:test';

import type { PracticeClientRecord } from '../services/accountantPracticeApi.ts';
import type { WorkspaceCompany } from '../types/accountant.ts';
import { filterOfficeClients, mergeOfficeClients } from './officeClients.ts';

const company = (over: Partial<WorkspaceCompany> = {}): WorkspaceCompany => ({
  engagement_id: 1,
  tenant_id: 10,
  company_name: 'شركة الأمل',
  status: 'active',
  accessible: true,
  open_queries: 0,
  blockers: 0,
  last_period: null,
  ...over,
});

const practiceClient = (over: Partial<PracticeClientRecord> = {}): PracticeClientRecord => ({
  id: 1,
  trade_name: 'مؤسسة النور',
  contact_first: '',
  contact_last: '',
  phone: '',
  mobile: '',
  email: '',
  address: '',
  sector: '',
  tax_number: '',
  notes: '',
  status: 'active',
  engagement_id: null,
  tenant_id: null,
  managed_tenant_id: null,
  client_type: 'unlinked',
  created_at: '2026-08-01T00:00:00Z',
  legacy: false,
  ...over,
});

test('المصدران يظهران في قائمة واحدة، كلٌّ بوسمه', () => {
  const rows = mergeOfficeClients([company()], [practiceClient()]);
  assert.equal(rows.length, 2);
  assert.deepEqual(
    rows.map((row) => [row.name, row.kind]).sort(),
    [['شركة الأمل', 'platform'], ['مؤسسة النور', 'external']].sort(),
  );
});

test('الزبون المربوط بشركة صفٌّ واحد لا صفّان — وله بابا المنصة والمكتب', () => {
  const rows = mergeOfficeClients(
    [company({ engagement_id: 7, tenant_id: 22 })],
    [practiceClient({ id: 5, trade_name: 'مؤسسة النور', engagement_id: 7, tenant_id: 22 })],
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].kind, 'platform');
  assert.equal(rows[0].tenantId, 22);
  assert.equal(rows[0].practiceId, 5);
  // اسم سجل المكتب هو ما يعرفه المحاسب، فهو المعروض.
  assert.equal(rows[0].name, 'مؤسسة النور');
});

test('ارتباط لم يعد في قائمة الشركات لا يبتلع صفّ الزبون', () => {
  const rows = mergeOfficeClients(
    [],
    [practiceClient({ id: 5, trade_name: 'مؤسسة النور', engagement_id: 7 })],
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].kind, 'external');
  assert.equal(rows[0].practiceId, 5);
});

test('الترتيب: المفتوح ثم المعلّق ثم المؤرشف — والأرشفة لا تُخفي الصفّ', () => {
  const rows = mergeOfficeClients(
    [company({ engagement_id: 2, tenant_id: 11, company_name: 'شركة ب', accessible: false, status: 'pending' })],
    [
      practiceClient({ id: 1, trade_name: 'زبون مؤرشف', status: 'archived' }),
      practiceClient({ id: 2, trade_name: 'زبون نشط' }),
    ],
  );
  assert.deepEqual(rows.map((row) => row.group), ['open', 'pending', 'archived']);
  assert.equal(rows[2].name, 'زبون مؤرشف');
});

test('ارتباط بلا موافقة يقول ذلك بدل أن يبدو ملفاً جاهزاً', () => {
  const [row] = mergeOfficeClients([company({ accessible: false, status: 'pending' })], []);
  assert.equal(row.accessible, false);
  assert.match(row.hint, /بانتظار موافقة/);
});

test('ارتباط نشط على شركة غير مرخّصة يقول السبب الحقيقي لا «بانتظار موافقة»', () => {
  const [row] = mergeOfficeClients([company({ accessible: false, status: 'active' })], []);
  assert.equal(row.accessible, false);
  assert.match(row.hint, /لم تفعّل وحدة بوابة المحاسب/);
  assert.doesNotMatch(row.hint, /بانتظار موافقة/);
});

test('التصفية المحلية تطال الاسم والقطاع والرقم الضريبي والهاتف', () => {
  const rows = mergeOfficeClients([], [
    practiceClient({ id: 1, trade_name: 'مؤسسة النور', sector: 'تجارة' }),
    practiceClient({ id: 2, trade_name: 'شركة الفجر', tax_number: '99881' }),
    practiceClient({ id: 3, trade_name: 'محل السلام', mobile: '0555123' }),
  ]);
  assert.deepEqual(filterOfficeClients(rows, 'تجارة').map((row) => row.name), ['مؤسسة النور']);
  assert.deepEqual(filterOfficeClients(rows, '99881').map((row) => row.name), ['شركة الفجر']);
  assert.deepEqual(filterOfficeClients(rows, '0555').map((row) => row.name), ['محل السلام']);
  assert.equal(filterOfficeClients(rows, '   ').length, 3);
});
