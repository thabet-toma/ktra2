import assert from 'node:assert/strict';
import test from 'node:test';

import { remainingPageNumbers } from './paging.ts';

/**
 * الحسابُ الصرف لصفحات `getAllProducts` بعد الأولى. حلقةُ الجلب المتتالية
 * القديمة كانت تكرّر حتى `allRows.length >= count`؛ والموازية تحتاج أن تعرف
 * أرقام الصفحات **قبل** أن تبدأ، فالقاعدة هنا هي نفسها لا قاعدةٌ ثانية.
 */

test('remainingPageNumbers: count = 0 ⇒ لا صفحات', () => {
  assert.deepEqual(remainingPageNumbers(0, 200, 0), []);
});

test('remainingPageNumbers: count ≤ pageSize ⇒ صفحةٌ واحدة فقط', () => {
  assert.deepEqual(remainingPageNumbers(120, 200, 120), []);
  assert.deepEqual(remainingPageNumbers(200, 200, 200), []);
});

test('remainingPageNumbers: مضاعفٌ تامّ ⇒ بلا صفحةٍ فارغة زائدة', () => {
  assert.deepEqual(remainingPageNumbers(400, 200, 200), [2]);
  assert.deepEqual(remainingPageNumbers(600, 200, 200), [2, 3]);
});

test('remainingPageNumbers: باقٍ ⇒ صفحةٌ أخيرة ناقصة', () => {
  assert.deepEqual(remainingPageNumbers(450, 200, 200), [2, 3]);
  assert.deepEqual(remainingPageNumbers(201, 200, 200), [2]);
});

test('remainingPageNumbers: صفحةٌ أولى أقصر من pageSize تُصبح حجم الصفحة الفعلي', () => {
  // `count` هو المرجع لا طول الصفحة: خادمٌ يحدّ `page_size` بأقلّ ممّا طُلب
  // يعيد صفحةً أولى قصيرة وله صفحاتٌ بعدها بحجمها هي — وحسابُها بحجم الطلب
  // (200) يعطي صفحتين ويُفقد الصفوف 361–450 بصمت.
  assert.deepEqual(remainingPageNumbers(450, 200, 120), [2, 3, 4]);
});

test('remainingPageNumbers: صفحةٌ أولى فارغة مع count > 0 ⇒ لا صفحات', () => {
  // الحلقة القديمة كانت تتوقّف عند أول صفحةٍ فارغة مهما قال `count`،
  // والجلبُ الموازي لا يطلب صفحةً لم تُثبت الحلقةُ وجودها.
  assert.deepEqual(remainingPageNumbers(450, 200, 0), []);
});

test('remainingPageNumbers: pageSize غير صالحٍ لا يقسم على صفر', () => {
  assert.deepEqual(remainingPageNumbers(450, 0, 200), []);
  assert.deepEqual(remainingPageNumbers(450, -200, 200), []);
});
