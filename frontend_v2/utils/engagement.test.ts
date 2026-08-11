import assert from 'node:assert/strict';
import test from 'node:test';

import {
  accountantEngagementActions,
  engagementErrorCode,
  invitationExpired,
  normalizeScope,
} from './engagement.ts';

test('تعرض أفعال الارتباط المناسبة لكل حالة ومبادر', () => {
  assert.deepEqual(accountantEngagementActions({ status: 'pending', initiated_by: 'accountant' }), ['withdraw']);
  assert.deepEqual(accountantEngagementActions({ status: 'pending', initiated_by: 'company' }), ['accept']);
  assert.deepEqual(accountantEngagementActions({ status: 'active', initiated_by: 'company' }), ['resign']);
  assert.deepEqual(accountantEngagementActions({ status: 'revoked', initiated_by: 'company' }), []);
});

test('يكشف انتهاء الدعوة ويطبّع النطاق', () => {
  assert.equal(invitationExpired({ invitation_expires_at: '2025-01-01T00:00:00Z' }, Date.parse('2025-01-02T00:00:00Z')), true);
  assert.deepEqual(normalizeScope([' tax.period.view ', 'sales.invoice.view', 'tax.period.view']), [
    'sales.invoice.view',
    'tax.period.view',
  ]);
});

test('يستخرج رمز خطأ API', () => {
  assert.equal(engagementErrorCode({ data: { code: 'invitation_expired' } }), 'invitation_expired');
});
