import assert from "node:assert/strict";
import test from "node:test";

import { PUBLIC_AUTH_ROUTES, resolvePublicAuthView } from "./publicAuthRoutes.ts";

test("لا مسار /accountant/signup في السجلّ — الباب مُغلَق", () => {
  assert.equal(resolvePublicAuthView("/accountant/signup"), null);
  assert.equal(resolvePublicAuthView("/accountant/signup/"), null);
});

test("لا مسار /accountant/verify-email في السجلّ", () => {
  assert.equal(resolvePublicAuthView("/accountant/verify-email"), null);
});

test("السجلّ فارغ كلياً — لا باب عام آخر يفتح authView خاصاً", () => {
  assert.deepEqual(PUBLIC_AUTH_ROUTES, {});
});

test("مسار مجهول لا يُحسب — يبقى null", () => {
  assert.equal(resolvePublicAuthView("/nope/whatever"), null);
  assert.equal(resolvePublicAuthView(""), null);
  assert.equal(resolvePublicAuthView("/"), null);
});
