/**
 * ExchangeRateField — حقل سعر الصرف الموحّد للدفعات بعملةٍ غير الأساسية.
 *
 * قاعدة المالك: كل دفعة بعملة أجنبية تحمل سعراً كتبه المستخدم بنفسه — لا افتراضي
 * 1 صامتاً ولا سعر لم يره. وبالشيكل لا يظهر شيء (يعيد المكوّن `null`): لا حقل
 * ولا نقرة ولا تحقّق جديد. التحقّق في `utils/paymentRate.ts` (مصدر واحد).
 *
 * الحقل يبدأ **فارغاً** دائماً. زرّ «آخر سعر X — استعمله» (من
 * `accountingApi.getExchangeRate`؛ 404 = لا سعر مسجَّل فلا زرّ ولا خطأ) وأزرار
 * `suggestions` (مثل «سعر الفاتورة 3.6») تملأ الخانة فقط، فلا يُرسَل شيء لم يره
 * المستخدم فيها.
 *
 * العقد مع الشاشة الأمّ: عند تغيير العملة **تُفرِّغ الشاشةُ القيمةَ** (`onChange("")`)
 * — المكوّن لا يفعل ذلك سحراً. وعند محاولة الحفظ تمرّر الشاشة `error` من
 * `validateRate` ليظهر الخطأ ولو لم تُلمَس الخانة.
 */
import React, { useEffect, useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatNumber } from "../../utils/formatNumber";
import { validateRate } from "../../utils/paymentRate";

export interface RateSuggestion {
  label: string;
  value: string;
}

export interface ExchangeRateFieldProps {
  currencyCode: string;
  /** العملة المختارة أساسية؟ — عندها لا يُرسم شيء. */
  isBase: boolean;
  value: string;
  onChange: (value: string) => void;
  /** YYYY-MM-DD — تاريخ السعر المقترح. */
  date: string;
  fromCurrencyId?: number | string | null;
  baseCurrencyId?: number | string | null;
  label?: string;
  suggestions?: RateSuggestion[];
  /** خطأ من الشاشة الأمّ (يسبق التحقّق الداخلي). */
  error?: string | null;
  disabled?: boolean;
  /** سعرٌ اختياري (فارغٌ مقبول): لا خطأ على الفراغ، ويُتحقَّق مما كُتب فقط. */
  optional?: boolean;
  className?: string;
}

const RATE_DECIMALS = 6;

export const ExchangeRateField: React.FC<ExchangeRateFieldProps> = ({
  currencyCode,
  isBase,
  value,
  onChange,
  date,
  fromCurrencyId,
  baseCurrencyId,
  label,
  suggestions,
  error,
  disabled = false,
  optional = false,
  className = "",
}) => {
  const [touched, setTouched] = useState(false);
  const [lastRate, setLastRate] = useState<string | null>(null);

  useEffect(() => {
    setLastRate(null);
    if (isBase || !fromCurrencyId || !baseCurrencyId || !date) return;
    let alive = true;
    accountingApi
      .getExchangeRate({
        from_currency: String(fromCurrencyId),
        to_currency: String(baseCurrencyId),
        date,
      })
      .then((r: { rate?: string | number } | null) => {
        if (!alive) return;
        const text = formatNumber(r?.rate, { maxDecimals: RATE_DECIMALS });
        // 404 (لا سعر) وأي فشل آخر: لا زرّ ولا خطأ — الحقل اليدوي يكفي.
        setLastRate(text || null);
      })
      .catch(() => {
        if (alive) setLastRate(null);
      });
    return () => {
      alive = false;
    };
  }, [isBase, fromCurrencyId, baseCurrencyId, date]);

  if (isBase) return null;

  const shownError = error ?? (touched && !(optional && !value.trim()) ? validateRate(value) : null);
  const buttons: RateSuggestion[] = [
    ...(lastRate ? [{ label: `آخر سعر ${lastRate} — استعمله`, value: lastRate }] : []),
    ...(suggestions ?? []).filter((s) => s.value),
  ];

  return (
    <div className={`flex flex-col gap-1 ${className}`} data-testid="exchange-rate-field">
      <label className="ktra-field">
        <span className="ktra-field-label">
          {label ?? `سعر صرف ${currencyCode} (كم شيكلاً) *`}
        </span>
        <input
          type="text"
          inputMode="decimal"
          dir="ltr"
          autoComplete="off"
          className={`ktra-input ktra-num ${shownError ? "border-red-500" : ""}`}
          value={value}
          disabled={disabled}
          placeholder="مثال 3.7"
          aria-invalid={shownError ? true : undefined}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => setTouched(true)}
        />
      </label>
      {shownError && (
        <p className="text-[11px] text-red-600" role="alert">
          {shownError}
        </p>
      )}
      {!disabled && buttons.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {buttons.map((b) => (
            <button
              key={`${b.label}|${b.value}`}
              type="button"
              className="ktra-toolbtn text-[11px]"
              onClick={() => {
                onChange(b.value);
                setTouched(true);
              }}
            >
              {b.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default ExchangeRateField;
