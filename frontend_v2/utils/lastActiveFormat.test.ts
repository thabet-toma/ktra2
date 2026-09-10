import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatLastActive,
  getLastActiveBadge,
  isRecentlyActive,
} from './lastActiveFormat.ts';

test('عتبة الـ 15 دقيقة: 14 دقيقة يعتبر نشطاً بينما 16 دقيقة يعتبر غير نشط', () => {
  const baseNow = new Date('2026-09-10T12:00:00Z');

  // 14 دقيقة مضت (نشط مؤخراً)
  const active14m = new Date(baseNow.getTime() - 14 * 60 * 1000).toISOString();
  assert.equal(isRecentlyActive(active14m, baseNow), true);
  // **طابعُ وقتٍ لا مصباح**: المواصفةُ أسقطت «نشط الآن» صراحةً، والنصُّ يحمل
  // الساعةَ الحقيقيّةَ ومدّةَ الغياب — «المصباحُ يَعِد بدقّةٍ لا يملكها النظام».
  assert.match(formatLastActive(active14m, baseNow), /آخر ظهور \d{2}:\d{2}/);
  assert.match(formatLastActive(active14m, baseNow), /منذ 14 دقيقة/);

  // 16 دقيقة مضت (غير نشط)
  const inactive16m = new Date(baseNow.getTime() - 16 * 60 * 1000).toISOString();
  assert.equal(isRecentlyActive(inactive16m, baseNow), false);
  assert.match(formatLastActive(inactive16m, baseNow), /آخر ظهور \d{2}:\d{2}/);
  assert.match(formatLastActive(inactive16m, baseNow), /منذ 16 دقيقة/);
  assert.doesNotMatch(formatLastActive(inactive16m, baseNow), /نشط/);

  // على الحافة تماماً: 15 دقيقة
  const boundary15m = new Date(baseNow.getTime() - 15 * 60 * 1000).toISOString();
  assert.equal(isRecentlyActive(boundary15m, baseNow), true);
});

test('التعامل مع القيم الفارغة والنشاط الفوري', () => {
  const baseNow = new Date('2026-09-10T12:00:00Z');

  // فارغ أو غير معرف
  assert.equal(isRecentlyActive(null, baseNow), false);
  assert.equal(isRecentlyActive(undefined, baseNow), false);
  assert.equal(formatLastActive(null, baseNow), 'لم يسجل نشاطاً');

  // نشاط فوري (أقل من دقيقة)
  const justNow = new Date(baseNow.getTime() - 10 * 1000).toISOString();
  assert.equal(isRecentlyActive(justNow, baseNow), true);
  // ولا «نشط الآن» حتى لحظةَ الظهور نفسِها — ساعةٌ صادقةٌ أفضلُ من وعدٍ لحظيّ
  assert.match(formatLastActive(justNow, baseNow), /^آخر ظهور \d{2}:\d{2}/);
  assert.doesNotMatch(formatLastActive(justNow, baseNow), /نشط الآن/);
});

test('توليد الشارة مع أصناف Tailwind دون inline styles', () => {
  const baseNow = new Date('2026-09-10T12:00:00Z');

  const activeTime = new Date(baseNow.getTime() - 5 * 60 * 1000).toISOString();
  const activeBadge = getLastActiveBadge(activeTime, baseNow);
  assert.equal(activeBadge.active, true);
  assert.match(activeBadge.className, /emerald/);

  const inactiveTime = new Date(baseNow.getTime() - 60 * 60 * 1000).toISOString();
  const inactiveBadge = getLastActiveBadge(inactiveTime, baseNow);
  assert.equal(inactiveBadge.active, false);
  assert.match(inactiveBadge.className, /slate/);
});
