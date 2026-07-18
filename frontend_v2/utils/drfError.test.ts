import assert from "node:assert/strict";
import test from "node:test";

import { humanizeDrfError, extractDrfFieldErrors } from "./drfError.ts";

test("flat field error gets an Arabic label prefix", () => {
  assert.equal(
    humanizeDrfError({ product: ["هذا الحقل مطلوب."] }),
    "الصنف: هذا الحقل مطلوب.",
  );
});

test("nested many=True item errors never leak raw JSON", () => {
  const out = humanizeDrfError({ items: [{}, { product: ["هذا الحقل مطلوب."] }] });
  assert.equal(out, "الصنف: هذا الحقل مطلوب.");
  assert.doesNotMatch(out, /[{}[\]]/); // لا أقواس JSON
});

test("detail is passed through verbatim without a field label", () => {
  assert.equal(humanizeDrfError({ detail: "غير مصرّح." }), "غير مصرّح.");
});

test("non_field_errors carry no label", () => {
  assert.equal(
    humanizeDrfError({ non_field_errors: ["تكرار غير مسموح."] }),
    "تكرار غير مسموح.",
  );
});

test("common English DRF messages are translated to Arabic", () => {
  assert.equal(
    humanizeDrfError({ quantity: ["This field is required."] }),
    "الكمية: هذا الحقل مطلوب.",
  );
});

test("unknown technical field names are hidden, message kept", () => {
  assert.equal(
    humanizeDrfError({ some_internal_flag: ["قيمة غير صالحة."] }),
    "قيمة غير صالحة.",
  );
});

test("duplicate messages are de-duplicated", () => {
  assert.equal(
    humanizeDrfError({ items: [{ product: ["مطلوب."] }, { product: ["مطلوب."] }] }),
    "الصنف: مطلوب.",
  );
});

test("empty / null input yields empty string (caller supplies fallback)", () => {
  assert.equal(humanizeDrfError(null), "");
  assert.equal(humanizeDrfError({}), "");
});

test("plain string input is returned as-is", () => {
  assert.equal(humanizeDrfError("خطأ عام"), "خطأ عام");
});

test("extractDrfFieldErrors maps leaf field keys to translated messages", () => {
  assert.deepEqual(
    extractDrfFieldErrors({ shipment_date: ["This field may not be blank."], shipping_type: ["مطلوب."] }),
    { shipment_date: "هذا الحقل لا يمكن أن يكون فارغاً.", shipping_type: "مطلوب." },
  );
});

test("extractDrfFieldErrors keeps the first message per field and skips general keys", () => {
  assert.deepEqual(
    extractDrfFieldErrors({ product: ["أ.", "ب."], non_field_errors: ["عام"], detail: "x" }),
    { product: "أ." },
  );
});

test("extractDrfFieldErrors returns empty for strings/null", () => {
  assert.deepEqual(extractDrfFieldErrors(null), {});
  assert.deepEqual(extractDrfFieldErrors("boom"), {});
});
