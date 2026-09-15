import React, { useCallback, useEffect, useState } from "react";
import { BadgeDollarSign, CalendarDays, Clock3, Loader2, UsersRound } from "lucide-react";

import {
  getEmployeePayTerms,
  type EmployeePayTerms,
  type EmployeePayTermsSource,
} from "../../services/platformEmployeeSpaceApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

const sourceDetails: Record<EmployeePayTermsSource, { label: string; description: string; tone: string }> = {
  employee: {
    label: "شروط خاصة بك",
    description: "هذه الشروط مكتوبة خصيصاً لك.",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
  },
  platform: {
    label: "شروط موحدة للمنصة",
    description: "تنطبق عليك السياسة الموحدة لجميع موظفي المنصة.",
    tone: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-200",
  },
  default: {
    label: "إعداد تجريبي افتراضي",
    description: "لم تُنشر شروط راتب بعد؛ المعروض هو الإعداد التجريبي الافتراضي.",
    tone: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
  },
};

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لاستعراض شروط صرف راتبك.", "تعذّر تحميل شروط صرف راتبك.");

export const EmployeePayTermsCard: React.FC<{ employeeId: number }> = ({ employeeId }) => {
  const [terms, setTerms] = useState<EmployeePayTerms | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTerms(await getEmployeePayTerms(employeeId));
    } catch (cause) {
      setTerms(null);
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return (
      <section className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900" dir="rtl">
        <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <Loader2 className="h-4 w-4 animate-spin text-cyan-600 dark:text-cyan-400" />
          جارٍ تحميل شروط صرف راتبك...
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 shadow-sm dark:border-rose-900 dark:bg-rose-950/30" dir="rtl">
        <p className="text-sm font-semibold text-rose-700 dark:text-rose-300">{error}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 rounded-lg bg-rose-100 px-3 py-1.5 text-xs font-bold text-rose-800 transition hover:bg-rose-200 dark:bg-rose-900/60 dark:text-rose-100 dark:hover:bg-rose-900"
        >
          إعادة المحاولة
        </button>
      </section>
    );
  }

  if (!terms) {
    return (
      <section className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900" dir="rtl">
        <p className="text-sm text-slate-600 dark:text-slate-300">لا تتوفر شروط صرف راتب منشورة حالياً.</p>
      </section>
    );
  }

  const source = sourceDetails[terms.source];

  return (
    <section className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900" dir="rtl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">الراتب الذي يُصرف لك</h2>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">تفاصيل شروط الصرف المطبقة عليك.</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${source.tone}`}>
          {source.label}
        </span>
      </div>

      {/* ‏#214-ج (بلاغٌ ثانٍ للمالك): «الراتب لازم عليه شرح لأنو ممكن الأساسي
          قليل ويكون عمولات عالتسويق، مو رقم وخلص». ويسبق الأرقامَ لا يتبعها:
          رقمٌ صغيرٌ يُقرأ أوّلاً يُفهَم غلطاً قبل أن تصل عينُ القارئ إلى شرحه.
          و`whitespace-pre-wrap` لأنّ المدير يكتب فقرات. */}
      {(terms.pay_terms_note || "").trim() && (
        <p className="mt-4 whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
          {terms.pay_terms_note}
        </p>
      )}

      <div className="mt-4 rounded-xl bg-emerald-50 p-4 dark:bg-emerald-950/30">
        <p className="text-xs font-semibold text-emerald-800 dark:text-emerald-200">الراتب الأساسي الشهري</p>
        <p className="mt-1 text-2xl font-extrabold text-emerald-700 dark:text-emerald-300">
          {formatNumber(terms.base_salary, { group: true })} شيكل
        </p>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
            <BadgeDollarSign className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
            <p className="text-xs font-semibold">عمولة اكتساب العملاء</p>
          </div>
          <p className="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100">
            {formatNumber(terms.acquisition_commission_amount, { group: true })} شيكل × {formatNumber(terms.acquisition_commission_months)} شهر
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
            <Clock3 className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
            <p className="text-xs font-semibold">أساس الدوام</p>
          </div>
          <p className="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100">
            {formatNumber(terms.daily_hours)} ساعة يومياً × {formatNumber(terms.weekly_days)} أيام أسبوعياً
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
            <CalendarDays className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
            <p className="text-xs font-semibold">يوم الاستحقاق</p>
          </div>
          <p className="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100">اليوم {formatNumber(terms.accrual_day_of_month)} من كل شهر</p>
        </div>
        <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
            <UsersRound className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
            <p className="text-xs font-semibold">مصدر الشروط</p>
          </div>
          <p className="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100">{source.description}</p>
          {/* لا سطرَ إصدارٍ حين لا نسخةَ منشورةً بعد: `formatNumber(null)` تعيد
              نصّاً فارغاً، فيقرأ الموظّفُ «إصدار السياسة:» بلا رقمٍ بعدها —
              وهي الحالةُ الأشيعُ اليوم لأنّ الـpilot قبل أوّل نشر. */}
          {terms.policy_version !== null && (
            <p className="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
              إصدار السياسة: {formatNumber(terms.policy_version)}
            </p>
          )}
        </div>
      </div>
    </section>
  );
};

export default EmployeePayTermsCard;
