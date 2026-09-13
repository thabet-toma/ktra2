import assert from 'node:assert/strict';
import test from 'node:test';

import { formatPresenceClock, presenceHours } from './presenceClock.ts';

test('يحوّل الثواني إلى ساعات ودقائق بخانتين', () => {
  assert.equal(formatPresenceClock(0), '00:00');
  assert.equal(formatPresenceClock(59), '00:00');
  assert.equal(formatPresenceClock(60), '00:01');
  assert.equal(formatPresenceClock(9000), '02:30');
  assert.equal(formatPresenceClock(36000), '10:00');
});

test('لا ينتج وقتاً سالباً ولا NaN من قيمة فاسدة', () => {
  assert.equal(formatPresenceClock(-120), '00:00');
  assert.equal(formatPresenceClock(Number.NaN), '00:00');
  assert.equal(formatPresenceClock(Number.POSITIVE_INFINITY), '00:00');
});

test('الساعات العشرية للمقارنة لا للعرض', () => {
  // ‏`02:30` نصٌّ لا يُقارَن بعتبة: مقارنةُ النصوص تجعل '10:00' أصغر من '2:00'.
  assert.equal(presenceHours(9000), 2.5);
  assert.equal(presenceHours(10800), 3);
  assert.ok(presenceHours(36000) > presenceHours(7200));
  assert.equal(presenceHours(-1), 0);
  assert.equal(presenceHours(Number.NaN), 0);
});

test('الدقائق لا تتسرب إلى خانة الساعات', () => {
  assert.equal(formatPresenceClock(3599), '00:59');
  assert.equal(formatPresenceClock(3600), '01:00');
  assert.equal(formatPresenceClock(3660), '01:01');
});
