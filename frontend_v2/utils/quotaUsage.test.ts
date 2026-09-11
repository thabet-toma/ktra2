import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  QUOTA_NEAR_LIMIT_PERCENT,
  quotaBarPercent,
  quotaHeadline,
  quotaOverageNotice,
  quotaTone,
  quotaToneMeta,
} from './quotaUsage.ts';

test('quotaTone على حدود العتبات بالضبط', () => {
  assert.equal(quotaTone(null), 'unmetered');
  assert.equal(quotaTone(Number.NaN), 'unmetered');
  assert.equal(quotaTone(QUOTA_NEAR_LIMIT_PERCENT - 0.01), 'comfortable');
  assert.equal(quotaTone(QUOTA_NEAR_LIMIT_PERCENT), 'near_limit');
  // الحدُّ نفسُه لم يُتجاوَز بعد
  assert.equal(quotaTone(100), 'near_limit');
  assert.equal(quotaTone(100.01), 'over_limit');
});

test('quotaToneMeta يقول الحالة بنصٍّ ولون', () => {
  assert.equal(quotaToneMeta('over_limit').label, 'تجاوزتَ الباقة');
  assert.match(quotaToneMeta('over_limit').barClass, /rose/);
  assert.match(quotaToneMeta('comfortable').barClass, /emerald/);
  assert.equal(quotaToneMeta('unmetered').label, 'بلا عمليات مشمولة');
});

test('quotaBarPercent يقصّ الشريط داخل إطاره', () => {
  assert.equal(quotaBarPercent(130), 100);
  assert.equal(quotaBarPercent(-5), 0);
  assert.equal(quotaBarPercent(42.5), 42.5);
  assert.equal(quotaBarPercent(null), 0);
});

test('quotaHeadline وquotaOverageNotice بأرقام المنصّة', () => {
  assert.equal(quotaHeadline(130, 100), '130 من 100 عملية');
  assert.equal(quotaOverageNotice(0, '0.00'), null);
  const notice = quotaOverageNotice(30, '90.00') ?? '';
  assert.match(notice, /30 عملية/);
  assert.match(notice, /بقيمة 90/);
});
