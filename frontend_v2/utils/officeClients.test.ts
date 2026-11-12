import assert from 'node:assert/strict';
import test from 'node:test';

import type { WorkspaceCompany } from '../types/accountant.ts';
import { platformHint, visibleWorkspaceCompanies } from './officeClients.ts';

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

test('ارتباط بلا موافقة يقول ذلك بدل أن يبدو ملفاً جاهزاً', () => {
  const hint = platformHint(company({ accessible: false, status: 'pending' }));
  assert.match(hint, /بانتظار موافقة/);
});

test('ارتباط نشط على شركة غير مرخّصة يقول السبب الحقيقي لا «بانتظار موافقة»', () => {
  const hint = platformHint(company({ accessible: false, status: 'active' }));
  assert.match(hint, /لم تفعّل وحدة بوابة المحاسب/);
  assert.doesNotMatch(hint, /بانتظار موافقة/);
});

test('المفتوح بلا فترات مُراجَعة يقولها صراحةً', () => {
  assert.equal(platformHint(company()), 'لم تُراجَع أي فترة بعد');
});

test('المفتوح مع فترة مُراجَعة يعرض مداها', () => {
  const hint = platformHint(company({
    last_period: { id: 3, period_from: '2026-08-01', period_to: '2026-08-31', status: 'approved' },
  }));
  assert.match(hint, /2026-08-01 → 2026-08-31/);
});

test('المفتوح يتقدّم على المعلّق، وداخل كل فريق ترتيبٌ أبجدي عربي', () => {
  const rows = visibleWorkspaceCompanies([
    company({ engagement_id: 1, company_name: 'شركة ج', accessible: false, status: 'pending' }),
    company({ engagement_id: 2, company_name: 'شركة ب' }),
    company({ engagement_id: 3, company_name: 'شركة أ' }),
    company({ engagement_id: 4, company_name: 'شركة د', accessible: false, status: 'pending' }),
  ], '');
  assert.deepEqual(rows.map((row) => row.company_name), ['شركة أ', 'شركة ب', 'شركة ج', 'شركة د']);
  assert.equal(rows.filter((row) => !row.accessible).length, 2);
});

test('البحث بالاسم لا يميّز حالة الأحرف، والفراغ يعيد القائمة كاملة', () => {
  const rows = [
    company({ engagement_id: 1, company_name: 'شركة الأمل' }),
    company({ engagement_id: 2, company_name: 'مؤسسة النور' }),
  ];
  assert.deepEqual(visibleWorkspaceCompanies(rows, 'الأمل').map((row) => row.engagement_id), [1]);
  assert.equal(visibleWorkspaceCompanies(rows, '   ').length, 2);
  assert.equal(visibleWorkspaceCompanies(rows, 'لا يوجد').length, 0);
});

test('التصفية لا تُعدّل المصفوفة الأصلية', () => {
  const rows = [
    company({ engagement_id: 1, company_name: 'شركة ب' }),
    company({ engagement_id: 2, company_name: 'شركة أ' }),
  ];
  visibleWorkspaceCompanies(rows, '');
  assert.deepEqual(rows.map((row) => row.company_name), ['شركة ب', 'شركة أ']);
});
