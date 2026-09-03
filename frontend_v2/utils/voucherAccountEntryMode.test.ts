import assert from 'node:assert/strict';
import test from 'node:test';

import {
  VOUCHER_ACCOUNT_ENTRY_MODES,
  voucherAccountEntryIsLinked,
} from './voucherAccountEntryMode.ts';

// القاعدة تفشل **مفتوحةً** عمداً — عكسُ `moduleAllowsView`. غيابُ القيمة يعني
// شركةً أقدم من الحقل أو إعداداتٍ لم تصل بعد، وإغلاقُها عليها كان يمنع إدخال
// المصاريف بالنصّ الحرّ في كل شركةٍ قائمة حتى تصل حمولةُ الإعدادات.
test('غيابُ القيمة = نصٌّ حرّ لا إلزام', () => {
  assert.equal(voucherAccountEntryIsLinked(undefined), false);
  assert.equal(voucherAccountEntryIsLinked(null), false);
  assert.equal(voucherAccountEntryIsLinked(''), false);
});

test('«free» صريحةً = نصٌّ حرّ', () => {
  assert.equal(voucherAccountEntryIsLinked('free'), false);
});

test('«linked» وحدها تُلزِم', () => {
  assert.equal(voucherAccountEntryIsLinked('linked'), true);
});

test('قيمةٌ مجهولة لا تُلزِم — لا تُقرأ كـlinked بالخطأ', () => {
  assert.equal(voucherAccountEntryIsLinked('LINKED'), false);
  assert.equal(voucherAccountEntryIsLinked('strict'), false);
});

test('الخياران المعروضان هما نفسهما اللذان يعرفهما الخادم', () => {
  assert.deepEqual(
    VOUCHER_ACCOUNT_ENTRY_MODES.map((m) => m.value),
    ['free', 'linked'],
  );
});
