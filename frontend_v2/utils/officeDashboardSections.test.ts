import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  OFFICE_CLIENT_TYPE_LABELS,
  OFFICE_CLIENT_TYPE_TONES,
  OFFICE_DASHBOARD_SECTIONS,
  summarizeOfficeDashboard,
  type OfficeClientBookType,
  type OfficeDashboardPayload,
} from './officeDashboardSections.ts';

const BOOK_TYPES: OfficeClientBookType[] = ['managed', 'engaged', 'hybrid', 'unlinked'];

test('ثلاثة عناصر لا رابع — قيد المالك في السِّجلّ نفسه', () => {
  assert.deepEqual(OFFICE_DASHBOARD_SECTIONS, ['clients', 'deadlines', 'unpaid_fees']);
  assert.equal(OFFICE_DASHBOARD_SECTIONS.length, 3);
});

const payload: OfficeDashboardPayload = {
  clients: [
    { id: 1, trade_name: 'أ', status: 'active', client_type: 'managed', last_activity: '2026-09-01' },
    { id: 2, trade_name: 'ب', status: 'active', client_type: 'engaged', last_activity: '2026-09-01' },
    { id: 3, trade_name: 'ج', status: 'active', client_type: 'engaged', last_activity: '2026-09-01' },
    { id: 4, trade_name: 'د', status: 'archived', client_type: 'unlinked', last_activity: '2026-08-01' },
  ],
  deadlines: { items: [], totals: { count: 5, overdue: 2, due_soon: 1 } },
  unpaid_fees: {
    invoices: [
      {
        invoice_id: 1, invoice_number: 'SI-1', tenant_id: 9, customer_id: 5,
        customer_name: 'زبون', invoice_date: '2026-08-01', remaining: '500.00',
      },
      {
        invoice_id: 2, invoice_number: 'SI-2', tenant_id: 9, customer_id: 6,
        customer_name: 'زبون آخر', invoice_date: '2026-08-15', remaining: '250.00',
      },
    ],
    total: '750.00',
  },
};

test('الملخّص يعدّ العملاء حسب حالة الدفتر بلا عرض', () => {
  const summary = summarizeOfficeDashboard(payload);
  assert.equal(summary.clientsTotal, 4);
  assert.deepEqual(summary.clientsByType, { managed: 1, engaged: 2, hybrid: 0, unlinked: 1 });
});

test('الملخّص يمرّر عدّادات الاستحقاقات وإجمالي الأتعاب كما وصلا من الخادم', () => {
  const summary = summarizeOfficeDashboard(payload);
  assert.equal(summary.deadlinesOverdue, 2);
  assert.equal(summary.deadlinesDueSoon, 1);
  assert.equal(summary.unpaidFeesTotal, '750.00');
  assert.equal(summary.unpaidFeesCount, 2);
});

test('كل حالة دفتر (ISSUE #52) تحمل تسمية عربية ولوناً — لا حالة صامتة بلا واحدة منهما', () => {
  for (const type of BOOK_TYPES) {
    assert.ok(OFFICE_CLIENT_TYPE_LABELS[type], `بلا تسمية: ${type}`);
    assert.ok(OFFICE_CLIENT_TYPE_TONES[type], `بلا لون: ${type}`);
  }
});

test('لوحة فارغة لا تكسر الملخّص', () => {
  const empty: OfficeDashboardPayload = {
    clients: [],
    deadlines: { items: [], totals: { count: 0, overdue: 0, due_soon: 0 } },
    unpaid_fees: { invoices: [], total: '0.00' },
  };
  const summary = summarizeOfficeDashboard(empty);
  assert.equal(summary.clientsTotal, 0);
  assert.deepEqual(summary.clientsByType, { managed: 0, engaged: 0, hybrid: 0, unlinked: 0 });
  assert.equal(summary.unpaidFeesTotal, '0.00');
});
