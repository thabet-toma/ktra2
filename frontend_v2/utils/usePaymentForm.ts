/**
 * T2-03: Shared payment-form validation.
 *
 * Single source of truth for the client-side rules that mirror the
 * server's `core/payments.validate_payment` (amount > 0, date required).
 * The 4 payment interfaces (deal / shipment-agent / clearance / local)
 * should call `validate()` so error messages and rules stay identical.
 *
 * STATUS: hook is correct and self-contained. Rollout — replacing each
 * form's bespoke validation with this hook — is tracked in task2.md
 * (T2-03 remaining) and must be verified per-form in the running UI.
 */
import { useState, useCallback } from "react";

export type PaymentFormErrors = {
  amount?: string;
  date?: string;
  /** سعر تحويل الدولار للشيكل — مطلوب لدفعات العملة الأجنبية */
  exchangeRate?: string;
  /** Per-source extra errors (partner/cashbox/currency) merged by the caller. */
  extra?: Record<string, string>;
  general?: string;
};

export type PaymentFormInput = {
  amount: string;
  /** ISO date string. Required — matches server `payment_date` rule. */
  date: string;
  /**
   * سعر التحويل ($ → ₪). يُمرَّر فقط لدفعات العملة الأجنبية. يبدأ فارغاً في
   * الواجهة عمداً: القيمة الافتراضية كانت تُحفظ عند نسيان تعديلها فتُسعَّر
   * الدفعة بسعر غير حقيقي وتتشوّه تكلفة الاستيراد.
   */
  exchangeRate?: string;
};

/** Pure validator (usable outside React, e.g. in tests or submit guards). */
export function validatePaymentInput(form: PaymentFormInput): PaymentFormErrors {
  const errs: PaymentFormErrors = {};
  const raw = (form.amount ?? "").trim();
  const amount = Number(raw);
  if (!raw) {
    errs.amount = "المبلغ مطلوب.";
  } else if (!Number.isFinite(amount) || amount <= 0) {
    errs.amount = "المبلغ يجب أن يكون أكبر من صفر.";
  }
  const d = (form.date ?? "").trim();
  if (!d) {
    errs.date = "تاريخ الدفعة مطلوب.";
  } else if (isNaN(new Date(d).getTime())) {
    errs.date = "التاريخ غير صالح.";
  }
  if (form.exchangeRate !== undefined) {
    const rateRaw = (form.exchangeRate ?? "").trim();
    const rate = Number(rateRaw);
    if (!rateRaw) {
      errs.exchangeRate = "سعر التحويل ($ → ₪) مطلوب.";
    } else if (!Number.isFinite(rate) || rate <= 0) {
      errs.exchangeRate = "سعر التحويل يجب أن يكون أكبر من صفر.";
    }
  }
  return errs;
}

export function hasPaymentErrors(errs: PaymentFormErrors): boolean {
  return Boolean(
    errs.amount ||
      errs.date ||
      errs.exchangeRate ||
      errs.general ||
      (errs.extra && Object.values(errs.extra).some(Boolean)),
  );
}

export function usePaymentForm() {
  const [errors, setErrors] = useState<PaymentFormErrors>({});

  const validate = useCallback((form: PaymentFormInput): PaymentFormErrors => {
    const errs = validatePaymentInput(form);
    setErrors(errs);
    return errs;
  }, []);

  const clearErrors = useCallback(() => setErrors({}), []);

  return { validate, clearErrors, errors, setErrors, hasErrors: hasPaymentErrors };
}
