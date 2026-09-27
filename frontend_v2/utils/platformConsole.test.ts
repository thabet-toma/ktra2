import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  EMPTY_COMPANY_FILTER,
  expectedMrr,
  filterCompanies,
  filterFromSearch,
  type CompanySort,
  type ConsoleCompanyRow,
  type ConsoleUsage,
} from './platformConsole.ts';

const NOW = Date.parse('2026-09-27T12:00:00Z');
const row = (id: number, over: Partial<ConsoleCompanyRow> = {}): ConsoleCompanyRow => ({
  id, name: `شركة ${id}`, plan: 'Basic', status: 'Active', subscription_days_left: null,
  last_activity_at: '2026-09-26T00:00:00Z', near_limit: [], created_at: `2026-0${id}-01T00:00:00Z`,
  ...over,
});
const usage = (docs: number, moves: number): ConsoleUsage => ({
  documents_total: docs, documents_month: 0, movements_total: moves, movements_month: 0,
});

test('expected MRR counts active companies only, at the effective plan price', () => {
  const pricing = [{ plan_key: 'Basic', effective_price: '60.00' }, { plan_key: 'Pro', effective_price: '120' }];
  const rows = [
    row(1, { plan: 'Basic' }), row(2, { plan: 'Pro' }),
    row(3, { plan: 'Pro', status: 'Trial' }), row(4, { plan: 'Pro', status: 'Suspended' }),
    row(5, { plan: 'Trial' }),
  ];
  assert.equal(expectedMrr(rows, pricing), 180);
});

test('filters by text, status, plan and flags', () => {
  const rows = [
    row(1, { name: 'مؤسسة النور' }),
    row(2, { status: 'Suspended', plan: 'Pro' }),
    row(3, { last_activity_at: null }),
    row(4, { near_limit: [{}] }),
    row(5, { subscription_days_left: 3 }),
    row(6, { subscription_days_left: -2, status: 'Suspended' }),
  ];
  const run = (over: object) =>
    filterCompanies(rows, new Map(), { ...EMPTY_COMPANY_FILTER, ...over }, NOW).map((r) => r.id);
  assert.deepEqual(run({ q: 'النور' }), [1]);
  assert.deepEqual(run({ q: '4' }), [4]);
  assert.deepEqual(run({ status: 'Suspended' }), [6, 2]);
  assert.deepEqual(run({ plan: 'Pro' }), [2]);
  assert.deepEqual(run({ flag: 'idle' }), [3]);
  assert.deepEqual(run({ flag: 'near' }), [4]);
  assert.deepEqual(run({ flag: 'ending' }), [5]);
});

test('sorts by usage with missing usage as zero', () => {
  const rows = [row(1), row(2), row(3)];
  const byId = new Map([[1, usage(5, 50)], [2, usage(9, 1)]]);
  const run = (sort: CompanySort) =>
    filterCompanies(rows, byId, { ...EMPTY_COMPANY_FILTER, sort }, NOW).map((r) => r.id);
  assert.deepEqual(run('documents'), [2, 1, 3]);
  assert.deepEqual(run('movements'), [1, 2, 3]);
  assert.deepEqual(run('created'), [3, 2, 1]);
});

test('reads overview links and ignores unknown values', () => {
  assert.deepEqual(filterFromSearch('?status=Active&filter=ending&sort=documents'), {
    q: '', status: 'Active', plan: '', flag: 'ending', sort: 'documents',
  });
  assert.deepEqual(filterFromSearch('?filter=drop&sort=hack'), EMPTY_COMPANY_FILTER);
});
