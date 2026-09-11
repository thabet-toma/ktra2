/** أدوات نصية خالصة لبطاقة خدمة الإدخال وشاشات سياسة الاشتراك (التذكرة 210-A). */

import type { ServiceSubscriptionStatus, SubscriptionPolicyEffectiveState } from "../services/platformOpsApi";
import { humanizeThrown } from "./drfError.ts";
import { formatNumber } from "./formatNumber.ts";

/** تسميات الحالة بتهجئة الخادم (`ServiceSubscription.Status`) — مصدر واحد لكل الشاشات. */
export const SUBSCRIPTION_STATUS_LABEL: Record<ServiceSubscriptionStatus, string> = {
  trial: "تجربة",
  active: "نشط",
  suspended: "معلق",
  cancelled: "ملغى",
};

/** حالة سريان نسخة السياسة كما يحسبها الخادم (`effective_state`). */
export const POLICY_EFFECTIVE_STATE_LABEL: Record<SubscriptionPolicyEffectiveState, string> = {
  draft: "مسودة",
  scheduled: "مجدولة",
  current: "سارية",
  retired: "منتهية",
};

export type SubscriptionAction =
  | "start_trial"
  | "activate_paid"
  | "convert_to_paid"
  | "suspend"
  | "resume"
  | "cancel"
  | "withdraw_cancellation"
  | "edit_settings";

/** الأفعال التي لا تُنفَّذ قبل اختيار عميل الفوترة (لا اشتراك مدفوع بلا من يُفوتَر). */
export const ACTIONS_REQUIRING_BILLING_CUSTOMER: readonly SubscriptionAction[] = ["activate_paid", "convert_to_paid"];

/**
 * الأفعال المسموحة للحالة الحالية — `null` يعني «لا صفّ اشتراك بعد».
 * الإلغاء المجدول يضيف «سحب الجدولة» بمعزل عن الحالة نفسها.
 */
export interface CommercialNumberFields {
  monthly_fee: string;
  included_quota: string;
  overage_unit_price: string;
  /** أيام التجربة تخصّ نسخة السياسة وحدها — تُترك فارغة لشروط اشتراك بعينه. */
  trial_days?: string;
}

/**
 * تحقّق القيم الرقمية التجارية المشترك بين مسودة السياسة وشروط اشتراك بعينه.
 *
 * حقل فارغ ليس صفراً: `Number("")` يساوي 0، فبلا هذا الحارس تُحفظ حصةٌ أو أيامُ تجربةٍ
 * صفريةً بصمت ويُفوتر كلُّ عمليةٍ تجاوزاً. يعيد رسالة الخطأ أو `null` إن صحّت القيم.
 */
export function validateCommercialNumbers(fields: CommercialNumberFields): string | null {
  const entries = Object.entries(fields).filter(([, value]) => value !== undefined) as [string, string][];
  if (entries.some(([, value]) => !value.trim())) return "أدخل كل القيم الرقمية.";
  const monthlyFee = Number(fields.monthly_fee);
  const overageUnitPrice = Number(fields.overage_unit_price);
  if (!Number.isFinite(monthlyFee) || monthlyFee < 0 || !Number.isFinite(overageUnitPrice) || overageUnitPrice < 0) {
    return "الرسوم وأسعار التجاوز يجب أن تكون أرقاماً غير سالبة.";
  }
  const quota = Number(fields.included_quota);
  if (!Number.isInteger(quota) || quota < 0) return "الحصة يجب أن تكون عدداً صحيحاً غير سالب.";
  if (fields.trial_days !== undefined) {
    const trialDays = Number(fields.trial_days);
    if (!Number.isInteger(trialDays) || trialDays < 0) return "أيام التجربة يجب أن تكون عدداً صحيحاً غير سالب.";
  }
  return null;
}

export function getAllowedSubscriptionActions(
  status: ServiceSubscriptionStatus | null,
  hasScheduledCancellation = false,
): SubscriptionAction[] {
  let actions: SubscriptionAction[];
  switch (status) {
    case null:
      actions = ["start_trial", "activate_paid"];
      break;
    case "trial":
      actions = ["convert_to_paid", "suspend", "cancel"];
      break;
    case "active":
      actions = ["suspend", "cancel", "edit_settings"];
      break;
    case "suspended":
      // الخادم يقبل تعديل الشروط على المعلّق أيضاً — الملغى وحده يُرفض؛ إخفاء الزر هنا
      // كان يحجب فعلاً مسموحاً.
      actions = ["resume", "cancel", "edit_settings"];
      break;
    case "cancelled":
      actions = ["activate_paid"];
      break;
    default:
      actions = [];
  }
  if (hasScheduledCancellation && status !== null && status !== "cancelled") {
    actions = [...actions, "withdraw_cancellation"];
  }
  return actions;
}

/** «تبقّى N يوماً» أو «انتهت التجربة» أو نص فارغ إن لم تكن هناك تجربة. */
export function formatTrialRemainingLabel(trialEndsAt: string | null, now: Date = new Date()): string {
  if (!trialEndsAt) return "";
  const end = new Date(trialEndsAt);
  if (Number.isNaN(end.getTime())) return "";
  const msRemaining = end.getTime() - now.getTime();
  if (msRemaining <= 0) return "انتهت التجربة";
  const daysRemaining = Math.ceil(msRemaining / (1000 * 60 * 60 * 24));
  if (daysRemaining === 1) return "يتبقّى يوم واحد على انتهاء التجربة";
  if (daysRemaining === 2) return "يتبقّى يومان على انتهاء التجربة";
  if (daysRemaining <= 10) return `يتبقّى ${formatNumber(daysRemaining)} أيام على انتهاء التجربة`;
  return `يتبقّى ${formatNumber(daysRemaining)} يوماً على انتهاء التجربة`;
}

/** صياغة عربية موجزة لعدد الارتباطات التي ستتأثر بالفعل المدمر. */
export function formatEngagementCount(count: number): string {
  if (count <= 0) return "لا ارتباطات نشطة";
  if (count === 1) return "ارتباطاً واحداً";
  if (count === 2) return "ارتباطين";
  if (count <= 10) return `${formatNumber(count)} ارتباطات`;
  return `${formatNumber(count)} ارتباطاً`;
}

/** رسالة خطأ العرض الموحّدة لشاشات عمليات المنصة: 403 برسالة الصلاحية، وغيرها من جسم DRF. */
export function describePlatformOpsError(cause: unknown, forbiddenMessage: string, fallback: string): string {
  const status = (cause as { status?: number } | null)?.status;
  if (status === 403) return forbiddenMessage;
  return humanizeThrown(cause, fallback);
}
