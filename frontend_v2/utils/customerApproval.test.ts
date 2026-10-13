import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  approvalWarningReason,
  customerApprovalBadge,
  customerApprovalTooltip,
  pickCustomerApproval,
  needsApprovalWarning,
} from './customerApproval.ts';

test('الشارة: ثلاث حالات بألوان الأخضر والكهرماني والأحمر', () => {
  assert.deepEqual(customerApprovalBadge('pending'), {
    label: 'بانتظار موافقة الزبون', className: 'bg-amber-100 text-amber-700',
  });
  assert.deepEqual(customerApprovalBadge('approved'), {
    label: 'وافق الزبون', className: 'bg-green-100 text-green-700',
  });
  assert.deepEqual(customerApprovalBadge('rejected'), {
    label: 'اعترض الزبون', className: 'bg-red-100 text-red-700',
  });
});

test('الشارة: not_required والغائب والمجهول لا شارة لهم', () => {
  assert.equal(customerApprovalBadge('not_required'), null);
  assert.equal(customerApprovalBadge(undefined), null);
  assert.equal(customerApprovalBadge(null), null);
  assert.equal(customerApprovalBadge('weird'), null);
});

test('الشارة: نص الخادم (display) يسبق النص المحلي', () => {
  assert.equal(customerApprovalBadge('approved', 'موافقة')?.label, 'موافقة');
  assert.equal(customerApprovalBadge('approved', '')?.label, 'وافق الزبون');
});

test('needsApprovalWarning: بانتظار واعتراض فقط', () => {
  assert.equal(needsApprovalWarning('pending'), true);
  assert.equal(needsApprovalWarning('rejected'), true);
  assert.equal(needsApprovalWarning('approved'), false);
  assert.equal(needsApprovalWarning('not_required'), false);
  assert.equal(needsApprovalWarning(undefined), false);
});

test('سبب التحذير يطابق صياغة الخادم', () => {
  assert.equal(approvalWarningReason({ customer_approval_status: 'pending' }), 'بانتظار موافقة الزبون');
  assert.equal(
    approvalWarningReason({
      customer_approval_status: 'rejected', customer_approval_by: 'خالد', customer_approval_note: 'السعر غالٍ',
    }),
    'اعترض الزبون (خالد) — السعر غالٍ',
  );
  assert.equal(approvalWarningReason({ customer_approval_status: 'rejected' }), 'اعترض الزبون');
  assert.equal(approvalWarningReason({ customer_approval_status: 'approved' }), '');
  assert.equal(approvalWarningReason({}), '');
});

test('التلميح: الاسم والتاريخ بصيغة الموقع ثم الملاحظة', () => {
  assert.equal(
    customerApprovalTooltip({
      customer_approval_by: 'خالد', customer_approval_at: '2026-10-11T09:00:00Z', customer_approval_note: 'تمام',
    }),
    'خالد — 11/10/2026\nتمام',
  );
  assert.equal(customerApprovalTooltip({}), '');
});

test('pickCustomerApproval: حقول الموافقة وحدها', () => {
  const picked = pickCustomerApproval({
    id: 1, invoice_number: 'X', customer_approval_status: 'rejected', customer_approval_by: 'خالد',
  } as Parameters<typeof pickCustomerApproval>[0]);
  assert.deepEqual(Object.keys(picked).sort(), [
    'customer_approval_at', 'customer_approval_by', 'customer_approval_note',
    'customer_approval_status', 'customer_approval_status_display',
  ]);
  assert.equal(picked.customer_approval_status, 'rejected');
  assert.equal(picked.customer_approval_by, 'خالد');
});
