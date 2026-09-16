import test from "node:test";
import assert from "node:assert/strict";

import type { CcTone } from "./ccTone.ts";
import {
  ccSurfaceClasses,
  ccPillClasses,
  ccScoreTone,
  ccPresenceTone,
} from "./ccTone.ts";

test("ccScoreTone: null و undefined يعودان neutral", () => {
  assert.equal(ccScoreTone(null), "neutral");
  assert.equal(ccScoreTone(undefined), "neutral");
  assert.equal(ccScoreTone(Number.NaN), "neutral");
});

test("ccScoreTone: قص القيم خارج المدى 0..100 (-5 و 140)", () => {
  // -5 يُقصّ إلى 0 => danger
  assert.equal(ccScoreTone(-5), "danger");
  // 140 يُقصّ إلى 100 => success
  assert.equal(ccScoreTone(140), "success");
});

test("ccScoreTone: فحص حدود 85 (84.9 و 85)", () => {
  assert.equal(ccScoreTone(84.9), "accent");
  assert.equal(ccScoreTone(85), "success");
  assert.equal(ccScoreTone(85.1), "success");
});

test("ccScoreTone: فحص حدود 70 (69.9 و 70)", () => {
  assert.equal(ccScoreTone(69.9), "warning");
  assert.equal(ccScoreTone(70), "accent");
  assert.equal(ccScoreTone(70.1), "accent");
});

test("ccScoreTone: فحص حدود 50 (49.9 و 50)", () => {
  assert.equal(ccScoreTone(49.9), "danger");
  assert.equal(ccScoreTone(50), "warning");
  assert.equal(ccScoreTone(50.1), "warning");
});

test("ccPresenceTone: أسبقية الاجتماع على الاتصال", () => {
  assert.equal(ccPresenceTone(true, true), "meeting");
  assert.equal(ccPresenceTone(false, true), "meeting");
  assert.equal(ccPresenceTone(true, false), "online");
  assert.equal(ccPresenceTone(false, false), "offline");
  assert.equal(ccPresenceTone(), "offline");
});

test("ccPillClasses: كل صنف نص حرفي غير فارغ ولا يحتوي على ${", () => {
  const tones: CcTone[] = ["neutral", "accent", "success", "warning", "danger", "violet"];
  for (const tone of tones) {
    const classes = ccPillClasses(tone);
    assert.ok(typeof classes === "string");
    assert.ok(classes.length > 0, `ccPillClasses(${tone}) must be non-empty`);
    assert.ok(!classes.includes("${"), `ccPillClasses(${tone}) must not contain interpolation: ${classes}`);
  }
});

test("ccSurfaceClasses: كل صنف نص حرفي غير فارغ ولا يحتوي على ${", () => {
  const tones: (CcTone | "default" | "raised")[] = [
    "default",
    "raised",
    "neutral",
    "accent",
    "success",
    "warning",
    "danger",
    "violet",
  ];
  for (const tone of tones) {
    const classes = ccSurfaceClasses(tone);
    assert.ok(typeof classes === "string");
    assert.ok(classes.length > 0, `ccSurfaceClasses(${tone}) must be non-empty`);
    assert.ok(!classes.includes("${"), `ccSurfaceClasses(${tone}) must not contain interpolation: ${classes}`);
  }
});
