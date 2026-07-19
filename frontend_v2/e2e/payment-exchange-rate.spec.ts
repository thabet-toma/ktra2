import { expect, test } from "@playwright/test";
import { hasPaymentErrors, validatePaymentInput } from "../utils/usePaymentForm";

const base = { amount: "1000", date: "2026-07-18" };

test.describe("سعر التحويل في دفعات العملة الأجنبية", () => {
  test("الحقل الفارغ يُرفض بدل أن يُحفظ كصفر", () => {
    // كان الحقل يبدأ بقيمة افتراضية (3.78) فتُحفظ عند نسيان تعديلها.
    const errs = validatePaymentInput({ ...base, exchangeRate: "" });
    expect(errs.exchangeRate).toBeTruthy();
    expect(hasPaymentErrors(errs)).toBe(true);
  });

  test("سعر صفر أو سالب مرفوض", () => {
    expect(validatePaymentInput({ ...base, exchangeRate: "0" }).exchangeRate).toBeTruthy();
    expect(validatePaymentInput({ ...base, exchangeRate: "-2" }).exchangeRate).toBeTruthy();
  });

  test("سعر صالح يمر", () => {
    const errs = validatePaymentInput({ ...base, exchangeRate: "3.65" });
    expect(errs.exchangeRate).toBeUndefined();
    expect(hasPaymentErrors(errs)).toBe(false);
  });

  test("الدفعات بلا عملة أجنبية لا تتأثر", () => {
    // exchangeRate غير مُمرَّر ⇒ لا قاعدة تُفرض (توافق مع النماذج الأخرى).
    const errs = validatePaymentInput(base);
    expect(errs.exchangeRate).toBeUndefined();
    expect(hasPaymentErrors(errs)).toBe(false);
  });
});
