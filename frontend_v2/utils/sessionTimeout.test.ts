import test from "node:test";
import assert from "node:assert/strict";
import {
  IDLE_MIN_MINUTES,
  IDLE_MAX_MINUTES,
  DEFAULT_IDLE_MINUTES,
  clampIdleMinutes,
  idleMinutesToMs,
} from "./sessionTimeout.ts";

test("الافتراضي 180 دقيقة (3 ساعات)", () => {
  assert.equal(DEFAULT_IDLE_MINUTES, 180);
});

test("clampIdleMinutes يقصّ تحت الحد الأدنى وفوق الأقصى", () => {
  assert.equal(clampIdleMinutes(2), IDLE_MIN_MINUTES);
  assert.equal(clampIdleMinutes(0), IDLE_MIN_MINUTES);
  assert.equal(clampIdleMinutes(-30), IDLE_MIN_MINUTES);
  assert.equal(clampIdleMinutes(5000), IDLE_MAX_MINUTES);
});

test("clampIdleMinutes يبقي القيمة ضمن النطاق ويدوّرها", () => {
  assert.equal(clampIdleMinutes(30), 30);
  assert.equal(clampIdleMinutes(60), 60);
  assert.equal(clampIdleMinutes(45.6), 46);
});

test("clampIdleMinutes يرجّع الافتراضي لغير الرقمي", () => {
  assert.equal(clampIdleMinutes(NaN), DEFAULT_IDLE_MINUTES);
  assert.equal(clampIdleMinutes(Infinity), DEFAULT_IDLE_MINUTES);
});

test("idleMinutesToMs يحوّل الدقائق المقصوصة إلى مللي ثانية", () => {
  assert.equal(idleMinutesToMs(30), 30 * 60000);
  assert.equal(idleMinutesToMs(2), IDLE_MIN_MINUTES * 60000); // مقصوص أولاً
});
