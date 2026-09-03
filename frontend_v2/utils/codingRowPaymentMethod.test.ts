/**
 * issue #85 متابعة — عمود «طريقة الدفع»: الصفّ يحمل طريقته، والتبديل بلوحة
 * المفاتيح دالّةٌ صرفة قابلة للاختبار بلا متصفح.
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  CODING_PAYMENT_METHODS,
  DEFAULT_CODING_PAYMENT_METHOD,
  paymentFieldsForRow,
  togglePaymentMethod,
} from "./codingRowPaymentMethod.ts";

test("الافتراضي نقد — تحقّقٌ لا حدس: resolve_cash_account يحلّه بلا تعثّر على دفترٍ طازج", () => {
  assert.equal(DEFAULT_CODING_PAYMENT_METHOD, "cash");
});

test("قائمة طريقتَي الدفع اثنتان لا أكثر — نقد وعلى الحساب", () => {
  assert.deepEqual(CODING_PAYMENT_METHODS.map((m) => m.value), ["cash", "on_account"]);
});

test("التبديل بلوحة المفاتيح يقلب بين الحالتين ويعود كما بدأ", () => {
  assert.equal(togglePaymentMethod("cash"), "on_account");
  assert.equal(togglePaymentMethod("on_account"), "cash");
  assert.equal(togglePaymentMethod(togglePaymentMethod("cash")), "cash");
});

test("صفٌّ نقديٌّ بصندوقٍ افتراضي معلوم يحمل cash_or_bank_account في الحمولة", () => {
  assert.deepEqual(
    paymentFieldsForRow("cash", 501),
    { payment_method: "cash", cash_or_bank_account: 501 },
  );
});

test("صفٌّ نقديٌّ بلا صندوقٍ افتراضي معلوم — الحقل يُترك للخادم لا يُزوَّر", () => {
  assert.deepEqual(paymentFieldsForRow("cash", null), { payment_method: "cash" });
});

test("«على الحساب» لا يحمل صندوقاً مهما وُجد افتراضي", () => {
  assert.deepEqual(paymentFieldsForRow("on_account", 501), { payment_method: "on_account" });
  assert.deepEqual(paymentFieldsForRow("on_account", null), { payment_method: "on_account" });
});
