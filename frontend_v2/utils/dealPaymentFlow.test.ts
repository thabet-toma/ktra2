import assert from "node:assert/strict";
import test from "node:test";

import { BANK_SWIFT_IMAGE_REQUIRED } from "./dealPaymentFlow.ts";

test("bank swift image is an optional attachment in the shared payment policy", () => {
  assert.equal(BANK_SWIFT_IMAGE_REQUIRED, false);
});
