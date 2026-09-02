import assert from "node:assert/strict";
import test from "node:test";

import { humanizeDrfError, extractDrfFieldErrors } from "./drfError.ts";

test("flat field error gets an Arabic label prefix", () => {
  assert.equal(
    humanizeDrfError({ product: ["هذا الحقل مطلوب."] }),
    "المنتج: هذا الحقل مطلوب.",
  );
});

test("nested many=True item errors never leak raw JSON", () => {
  const out = humanizeDrfError({ items: [{}, { product: ["هذا الحقل مطلوب."] }] });
  assert.equal(out, "المنتج: هذا الحقل مطلوب.");
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
    "المنتج: مطلوب.",
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

test('humanizeThrown يقرأ رسالة Error وجسم DRF المُسلسَل', async () => {
  const { humanizeThrown } = await import('./drfError.ts');
  assert.equal(humanizeThrown(new Error('الحساب البنكي غير موجود')), 'الحساب البنكي غير موجود');
  assert.equal(
    humanizeThrown(new Error('{"detail": "المطابقة مُقفلة"}')),
    'المطابقة مُقفلة',
  );
  assert.equal(humanizeThrown({ detail: 'خطأ مباشر' }), 'خطأ مباشر');
  assert.equal(humanizeThrown(new Error('')), 'حدث خطأ غير متوقع');
});

test('رسالة حصّة الخطة تصل كما هي بلا مفتاح الحدّ التقني', () => {
  // T-PLANLIMITS: `enforce_limits` يرفع الحقلين معاً؛ المستخدم يقرأ الأول وحده.
  const message = humanizeDrfError({
    plan_limit: 'بلغتَ حدّ خطتك: 3 دفاتر عملاء إجمالاً.',
    limit_key: 'office.managed_books',
  });
  assert.equal(message, 'بلغتَ حدّ خطتك: 3 دفاتر عملاء إجمالاً.');
});
