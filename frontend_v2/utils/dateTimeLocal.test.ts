import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dateTimeLocalToIso, isoToDateTimeLocal } from './dateTimeLocal.ts';

test('isoToDateTimeLocal يعطي صيغة الحقل بالضبط', () => {
  assert.match(isoToDateTimeLocal('2026-09-11T14:30:00Z'), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
});

test('الذهابُ والإيابُ يحفظان اللحظة نفسَها بدقّة الدقيقة — أيّاً كان توقيتُ الجهاز', () => {
  const iso = '2026-09-11T14:30:00.000Z';
  assert.equal(dateTimeLocalToIso(isoToDateTimeLocal(iso)), iso);
});

test('الفارغُ والتالفُ لا يُلفَّقان تاريخاً', () => {
  assert.equal(isoToDateTimeLocal(null), '');
  assert.equal(isoToDateTimeLocal(''), '');
  assert.equal(isoToDateTimeLocal('not-a-date'), '');
  assert.equal(dateTimeLocalToIso(''), null);
  assert.equal(dateTimeLocalToIso(undefined), null);
  assert.equal(dateTimeLocalToIso('2026-13-45T99:99'), null);
});
