import assert from 'node:assert/strict';
import test from 'node:test';

import { capabilitiesPending, staffGate } from './staffAccess.ts';

const NONE = { is_platform_employee: false, is_platform_admin: false };
const EMPLOYEE = { is_platform_employee: true, is_platform_admin: false };
const ADMIN = { is_platform_employee: false, is_platform_admin: true };

// ═══ المرساة: «لم أسأل بعد» ليست «قيل لا» ═════════════════════════════════
// هذا هو العطبُ الذي أخرج الموظّفَ من مساحته: لحظةَ انتهاءِ المصادقةِ يصير
// `fetching` كاذباً والجوابُ ما زال فارغاً ولم يُسأل عن هذا المستخدم قطّ.
// بلا `answeredFor` يقرأ الشرطُ «ممنوع» فيطرده قبل انطلاق النداء.
test('انتهاءُ المصادقة قبل طرح السؤال يبقى انتظاراً لا رفضاً', () => {
  assert.equal(
    capabilitiesPending({ isSuperAdmin: false, fetching: false, answeredFor: null, userId: '7' }),
    true,
  );
  assert.equal(
    staffGate({ authLoading: false, hasUser: true, pending: true, capabilities: NONE }),
    'loading',
  );
});

test('جوابٌ يخصُّ مستخدماً آخرَ لا يُحسب جواباً عن هذا', () => {
  assert.equal(
    capabilitiesPending({ isSuperAdmin: false, fetching: false, answeredFor: '3', userId: '7' }),
    true,
  );
});

test('جوابٌ حاسمٌ بالرفض يُنهي الانتظار ويُخرج', () => {
  const pending = capabilitiesPending({ isSuperAdmin: false, fetching: false, answeredFor: '7', userId: '7' });
  assert.equal(pending, false);
  assert.equal(staffGate({ authLoading: false, hasUser: true, pending, capabilities: NONE }), 'leave');
});

test('النداءُ الجاري انتظارٌ ولو كان الجوابُ السابقُ لهذا المستخدم', () => {
  assert.equal(
    capabilitiesPending({ isSuperAdmin: false, fetching: true, answeredFor: '7', userId: '7' }),
    true,
  );
});

test('زائرٌ بلا مستخدمٍ لا يُعلَّق انتظاراً أبداً', () => {
  const pending = capabilitiesPending({ isSuperAdmin: false, fetching: false, answeredFor: null, userId: null });
  assert.equal(pending, false);
  assert.equal(staffGate({ authLoading: false, hasUser: false, pending, capabilities: NONE }), 'login');
});

test('السوبر أدمن لا يسأل ولا ينتظر', () => {
  assert.equal(
    capabilitiesPending({ isSuperAdmin: true, fetching: true, answeredFor: null, userId: '1' }),
    false,
  );
});

test('البابُ يُفتَح لموظّف المنصّة ولمديرها كليهما', () => {
  assert.equal(staffGate({ authLoading: false, hasUser: true, pending: false, capabilities: EMPLOYEE }), 'render');
  assert.equal(staffGate({ authLoading: false, hasUser: true, pending: false, capabilities: ADMIN }), 'render');
});

test('المصادقةُ الجاريةُ انتظارٌ مهما كان الجواب', () => {
  assert.equal(staffGate({ authLoading: true, hasUser: false, pending: false, capabilities: NONE }), 'loading');
  assert.equal(staffGate({ authLoading: true, hasUser: true, pending: false, capabilities: EMPLOYEE }), 'loading');
});
