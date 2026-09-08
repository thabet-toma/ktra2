import assert from "node:assert/strict";
import test from "node:test";

import { campaignCountdown, COUNTDOWN_MAX_DAYS } from "./campaignCountdown.ts";

const NOW = new Date("2026-09-08T00:00:00Z").getTime();

test("لا ends_at ⇒ لا عدّاد", () => {
  assert.equal(campaignCountdown(null, NOW), null);
  assert.equal(campaignCountdown(undefined, NOW), null);
});

test("حملةٌ منتهية فعلاً ⇒ لا عدّاد", () => {
  assert.equal(campaignCountdown("2026-09-01T00:00:00Z", NOW), null);
});

test("تاريخٌ غير صالح ⇒ لا عدّاد بدل NaN يتسرّب للواجهة", () => {
  assert.equal(campaignCountdown("ليس-تاريخاً", NOW), null);
});

test("يبقى ٣ أيام و٥ ساعات ⇒ يُحسَب بدقّة", () => {
  const endsAt = new Date(NOW + 3 * 24 * 60 * 60 * 1000 + 5 * 60 * 60 * 1000 + 30 * 60 * 1000).toISOString();
  const result = campaignCountdown(endsAt, NOW);
  assert.deepEqual(result, { days: 3, hours: 5, minutes: 30 });
});

test(`أبعد من ${COUNTDOWN_MAX_DAYS} يوماً ⇒ يختفي العدّاد (عرضٌ «محدود المدّة» يفقد معناه)`, () => {
  const farAway = new Date(NOW + (COUNTDOWN_MAX_DAYS + 1) * 24 * 60 * 60 * 1000).toISOString();
  assert.equal(campaignCountdown(farAway, NOW), null);
});

test(`عند حدّ ${COUNTDOWN_MAX_DAYS} يوماً بالضبط ⇒ ما زال يظهر`, () => {
  const atLimit = new Date(NOW + COUNTDOWN_MAX_DAYS * 24 * 60 * 60 * 1000 + 60_000).toISOString();
  const result = campaignCountdown(atLimit, NOW);
  assert.ok(result);
  assert.equal(result?.days, COUNTDOWN_MAX_DAYS);
});
