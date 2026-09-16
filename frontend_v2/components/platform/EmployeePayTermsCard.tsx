import React, { useCallback, useEffect, useState } from "react";
import { BadgeDollarSign, CalendarDays, Clock3, UsersRound } from "lucide-react";

import {
  getEmployeePayTerms,
  type EmployeePayTerms,
  type EmployeePayTermsSource,
} from "../../services/platformEmployeeSpaceApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton, CcStatTile } from "./ui";
import type { CcTone } from "../../utils/ccTone";

const sourceDetails: Record<EmployeePayTermsSource, { label: string; description: string; tone: CcTone }> = {
  employee: {
    label: "شروط خاصة بك",
    description: "هذه الشروط مكتوبة خصيصاً لك.",
    tone: "success",
  },
  platform: {
    label: "شروط موحدة للمنصة",
    description: "تنطبق عليك السياسة الموحدة لجميع موظفي المنصة.",
    tone: "accent",
  },
  default: {
    label: "إعداد تجريبي افتراضي",
    description: "لم تُنشر شروط راتب بعد؛ المعروض هو الإعداد التجريبي الافتراضي.",
    tone: "warning",
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
    return <CcSkeleton variant="card" className="mb-6" />;
  }

  if (error) {
    return (
      <CcCard tone="danger" className="mb-6 p-4 space-y-3" dir="rtl">
        <p className="text-sm font-semibold text-rose-400">{error}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 px-3 py-1.5 text-xs font-bold transition-colors"
        >
          إعادة المحاولة
        </button>
      </CcCard>
    );
  }

  if (!terms) {
    return (
      <CcEmpty
        title="لا تتوفر شروط صرف راتب منشورة حالياً."
        className="mb-6"
      />
    );
  }

  const source = sourceDetails[terms.source];

  return (
    <CcCard className="mb-6 p-4 sm:p-5 space-y-4" dir="rtl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <CcSectionTitle
          title="الراتب الذي يُصرف لك"
          subtitle="تفاصيل شروط الصرف المطبقة عليك."
        />
        <CcPill tone={source.tone}>
          {source.label}
        </CcPill>
      </div>

      {/* ‏#214-ج (بلاغٌ ثانٍ للمالك): «الراتب لازم عليه شرح لأنو ممكن الأساسي
          قليل ويكون عمولات عالتسويق، مو رقم وخلص». ويسبق الأرقامَ لا يتبعها:
          رقمٌ صغيرٌ يُقرأ أوّلاً يُفهَم غلطاً قبل أن تصل عينُ القارئ إلى شرحه.
          و`whitespace-pre-wrap` لأنّ المدير يكتب فقرات. */}
      {(terms.pay_terms_note || "").trim() && (
        <p className="whitespace-pre-wrap rounded-xl border border-cc-border bg-cc-surface-2 p-3 text-xs leading-relaxed text-cc-text">
          {terms.pay_terms_note}
        </p>
      )}

      <CcCard tone="success" className="p-4">
        <CcStatTile
          label="الراتب الأساسي الشهري"
          value={formatNumber(terms.base_salary, { group: true })}
          unit="شيكل"
          tone="success"
        />
      </CcCard>

      <div className="grid gap-3 sm:grid-cols-2">
        <CcCard className="p-3.5">
          <CcStatTile
            label="عمولة اكتساب العملاء"
            value={`${formatNumber(terms.acquisition_commission_amount, { group: true })} شيكل × ${formatNumber(terms.acquisition_commission_months)} شهر`}
            icon={<BadgeDollarSign className="h-4 w-4" />}
            tone="accent"
          />
        </CcCard>

        <CcCard className="p-3.5">
          <CcStatTile
            label="أساس الدوام"
            value={`${formatNumber(terms.daily_hours)} ساعة يومياً × ${formatNumber(terms.weekly_days)} أيام أسبوعياً`}
            icon={<Clock3 className="h-4 w-4" />}
            tone="neutral"
          />
        </CcCard>

        <CcCard className="p-3.5">
          <CcStatTile
            label="يوم الاستحقاق"
            value={`اليوم ${formatNumber(terms.accrual_day_of_month)}`}
            hint="من كل شهر"
            icon={<CalendarDays className="h-4 w-4" />}
            tone="neutral"
          />
        </CcCard>

        <CcCard className="p-3.5">
          <CcStatTile
            label="مصدر الشروط"
            value={source.label}
            hint={source.description}
            icon={<UsersRound className="h-4 w-4" />}
            tone="neutral"
          />
          {/* لا سطرَ إصدارٍ حين لا نسخةَ منشورةً بعد: `formatNumber(null)` تعيد
              نصّاً فارغاً، فيقرأ الموظّفُ «إصدار السياسة:» بلا رقمٍ بعدها —
              وهي الحالةُ الأشيعُ اليوم لأنّ الـpilot قبل أوّل نشر. */}
          {terms.policy_version !== null && (
            <p className="mt-1 text-[11px] text-cc-text-muted">
              إصدار السياسة: {formatNumber(terms.policy_version)}
            </p>
          )}
        </CcCard>
      </div>
    </CcCard>
  );
};

export default EmployeePayTermsCard;
