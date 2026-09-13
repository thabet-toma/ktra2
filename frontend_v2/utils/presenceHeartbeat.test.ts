import test from 'node:test';
import assert from 'node:assert/strict';

import { presenceHeartbeatEnabled, shouldSendHeartbeat } from './presenceHeartbeat.ts';

test('موظّفُ المنصّة ينبض وهو يعمل في نظام الشركة — وهذه هي التذكرة نفسُها', () => {
  assert.equal(
    presenceHeartbeatEnabled({ pending: false, isPlatformEmployee: true }),
    true,
  );
});

test('مستخدمُ شركةٍ عاديٌّ لا ينبض — لا طلبَ كلَّ دقيقةٍ لكلّ مستخدمٍ في النظام', () => {
  assert.equal(
    presenceHeartbeatEnabled({ pending: false, isPlatformEmployee: false }),
    false,
  );
});

test('لا نبضةَ قبل أن يُحسم مَن هذا المستخدم', () => {
  // لو نبض أثناء الانتظار لنبض **كلُّ** مستخدمٍ مرّةً في كلّ تحميلٍ للصفحة.
  assert.equal(
    presenceHeartbeatEnabled({ pending: true, isPlatformEmployee: true }),
    false,
  );
  assert.equal(
    presenceHeartbeatEnabled({ pending: true, isPlatformEmployee: false }),
    false,
  );
});

test('لسانٌ مخفيٌّ لا ينبض ولو كان صاحبُه موظّفَ منصّة', () => {
  assert.equal(shouldSendHeartbeat({ enabled: true, documentHidden: true }), false);
});

test('لسانٌ ظاهرٌ لموظّفٍ مفعَّلٍ ينبض', () => {
  assert.equal(shouldSendHeartbeat({ enabled: true, documentHidden: false }), true);
});

test('التعطيلُ يغلب الظهور — لا نبضةَ من لسانٍ ظاهرٍ لمن ليس موظّفاً', () => {
  assert.equal(shouldSendHeartbeat({ enabled: false, documentHidden: false }), false);
});
