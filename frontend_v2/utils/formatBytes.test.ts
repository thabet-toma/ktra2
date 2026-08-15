import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatBytes } from './formatBytes.ts';

test('القيم الفارغة أو غير الموجبة شرطة', () => {
  assert.equal(formatBytes(null), '—');
  assert.equal(formatBytes(undefined), '—');
  assert.equal(formatBytes(0), '—');
  assert.equal(formatBytes(-5), '—');
});

test('أقل من 1024 بايت عدداً صحيحاً', () => {
  assert.equal(formatBytes(1), '1 بايت');
  assert.equal(formatBytes(512), '512 بايت');
  assert.equal(formatBytes(1023), '1023 بايت');
});

test('كيلوبايت بمنزلة عشرية واحدة وبلا صفر زائد', () => {
  assert.equal(formatBytes(1024), '1 ك.ب');
  assert.equal(formatBytes(1536), '1.5 ك.ب');
  assert.equal(formatBytes(1024 * 1023), '1023 ك.ب');
});

test('ميجابايت بمنزلة عشرية واحدة وبلا صفر زائد', () => {
  assert.equal(formatBytes(1024 * 1024 * 2.5), '2.5 م.ب');
  assert.equal(formatBytes(1024 ** 2 * 1023), '1023 م.ب');
});

test('جيجابايت بمنزلة عشرية واحدة وبلا صفر زائد', () => {
  assert.equal(formatBytes(1024 ** 3), '1 ج.ب');
  assert.equal(formatBytes(1024 ** 3 * 3.25), '3.3 ج.ب');
});

test('حدّ 1024² بالضبط ينتقل إلى وحدة الميجابايت لا الكيلوبايت', () => {
  assert.equal(formatBytes(1024 ** 2), '1 م.ب');
});
