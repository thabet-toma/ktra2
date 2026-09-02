import { test } from 'node:test';
import assert from 'node:assert/strict';
import { effectiveHandoverStatus } from './handoverRequestStatus.ts';

test('معلَّق ولم تفت صلاحيته ⇒ يبقى pending', () => {
  assert.equal(
    effectiveHandoverStatus('pending', '2026-09-16T00:00:00Z', '2026-09-02T00:00:00Z'),
    'pending',
  );
});

test('معلَّق وفاتت صلاحيته ⇒ expired رغم أن الصفّ ما زال pending', () => {
  assert.equal(
    effectiveHandoverStatus('pending', '2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z'),
    'expired',
  );
});

test('اللحظة الأخيرة (تساوٍ) تُعامَل منتهيةً — طبق حَكَم الخادم `<=`', () => {
  assert.equal(
    effectiveHandoverStatus('pending', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
    'expired',
  );
});

test('accepted لا يتراجع أبداً — الانتهاء لا يُقرأ إلا على pending', () => {
  assert.equal(
    effectiveHandoverStatus('accepted', '2026-01-01T00:00:00Z', '2026-09-02T00:00:00Z'),
    'accepted',
  );
});

test('cancelled يبقى كما هو أيضاً', () => {
  assert.equal(
    effectiveHandoverStatus('cancelled', '2026-01-01T00:00:00Z', '2026-09-02T00:00:00Z'),
    'cancelled',
  );
});
