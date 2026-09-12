import test from 'node:test';
import assert from 'node:assert/strict';

import { countPresent, derivePresence, sortByPresence } from './roomPresence.ts';

test('الاجتماع يغلب الاتصال — الضوء الأصفر لا يختفي لأن صاحبه يعمل', () => {
  const busyAndActive = { is_recently_active: true };
  assert.equal(derivePresence(busyAndActive, new Set([7]), 7), 'meeting');
  // لولا الأسبقية لعاد 'online' وضاع الضوء الأصفر في الحالة التي وُجد لها.
  assert.equal(derivePresence(busyAndActive, new Set([9]), 7), 'online');
});

test('الحضور يُقرأ من حساب الخادم لا من ساعة المتصفح', () => {
  // طابعٌ قديمٌ جداً مع `is_recently_active: true` يبقى «متّصلاً»: الخادم هو
  // المرجع، وساعةُ جهازٍ مغلوطةٌ لا تُخرج نصفَ الفريق من الغرفة.
  const staleStampButServerSaysActive = {
    is_recently_active: true,
    last_active_at: '2020-01-01T00:00:00Z',
  };
  assert.equal(derivePresence(staleStampButServerSaysActive, null, 1), 'online');

  const freshStampButServerSaysInactive = {
    is_recently_active: false,
    last_active_at: new Date().toISOString(),
  };
  assert.equal(derivePresence(freshStampButServerSaysInactive, null, 1), 'offline');
});

test('غياب العلم كله يعني غير متصل لا متصل', () => {
  assert.equal(derivePresence({}, null, 1), 'offline');
  assert.equal(derivePresence({ is_recently_active: undefined }, undefined, 1), 'offline');
});

test('الترتيب ثابت بين تحديثين فلا تقفز الوجوه حول الطاولة', () => {
  const rows = [
    { presence: 'offline' as const, name: 'خالد' },
    { presence: 'meeting' as const, name: 'سارة' },
    { presence: 'online' as const, name: 'ريم' },
    { presence: 'online' as const, name: 'أحمد' },
  ];
  const first = sortByPresence(rows).map((r) => r.name);
  // نفس المدخلات بترتيبٍ مختلف يجب أن تعطي نفس المخرَج — وإلاّ تغيّر مقعدُ
  // الموظّف عند كلّ استقصاءٍ بلا أن يتغيّر شيءٌ في حالته.
  const shuffled = [rows[2], rows[0], rows[3], rows[1]];
  const second = sortByPresence(shuffled).map((r) => r.name);
  assert.deepEqual(first, second);
  assert.deepEqual(first, ['أحمد', 'ريم', 'سارة', 'خالد']);
});

test('sortByPresence لا تعدّل المصفوفة الأصلية', () => {
  const rows = [
    { presence: 'offline' as const, name: 'خالد' },
    { presence: 'online' as const, name: 'أحمد' },
  ];
  sortByPresence(rows);
  assert.equal(rows[0].name, 'خالد');
});

test('عدّ المتصلين يحسب المجتمع حاضراً — هو في العمل لا خارجه', () => {
  const occupants = [
    { presence: 'online' as const },
    { presence: 'meeting' as const },
    { presence: 'offline' as const },
  ];
  assert.equal(countPresent(occupants), 2);
  assert.equal(countPresent([]), 0);
  assert.equal(countPresent([{ presence: 'offline' as const }]), 0);
});
