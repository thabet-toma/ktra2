import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isInactiveRecord, missingRecordIds, parseActiveStatus } from './activeStatus.ts';

test('parseActiveStatus: القيم الثلاث صالحة وما سواها نشط', () => {
  assert.equal(parseActiveStatus('inactive'), 'inactive');
  assert.equal(parseActiveStatus('all'), 'all');
  assert.equal(parseActiveStatus('weird'), 'active');
});

test('isInactiveRecord: الموقوف صراحةً فقط — الغائب والفارغ نشط', () => {
  assert.equal(isInactiveRecord({ is_active: false }), true);
  assert.equal(isInactiveRecord({ is_active: true }), false);
  assert.equal(isInactiveRecord({}), false);
  assert.equal(isInactiveRecord(null), false);
  assert.equal(isInactiveRecord(undefined), false);
});

test('missingRecordIds: ما يحمله المستند وغاب عن القائمة ولم يُجرَّب، دون تكرار', () => {
  const known = [{ id: 1 }, { id: '2' }];
  assert.deepEqual(missingRecordIds([1, 2, 3, 3, '4'], known, new Set()), [3, 4]);
});

test('missingRecordIds: يتجاهل الفارغ والصفر وغير الرقمي والمجرَّب مسبقاً', () => {
  assert.deepEqual(missingRecordIds(['', null, undefined, 0, 'abc', -5, 1.5], [], new Set()), []);
  assert.deepEqual(missingRecordIds([7, 8], [], new Set([7])), [8]);
});

test('missingRecordIds: معرّف نصّي ورقمي لنفس السجل يُعدّان واحداً', () => {
  assert.deepEqual(missingRecordIds(['9', 9], [{ id: 9 }], new Set()), []);
});
