/** أدوات نصية خالصة لفحص صحة الدفاتر والتشغيل والإسناد/الطاقة (التذكرة 210-B). */

import type {
  EngagementKind,
  EngagementStatus,
  HealthCheckComplexity,
} from "../services/platformOpsApi.ts";
import { formatNumber } from "./formatNumber.ts";

/** تسميات تعقيد الشركة (`CompanyHealthCheck.Complexity`) — الفارغة تعني «لم يُقدَّر بعد». */
export const HEALTH_CHECK_COMPLEXITY_LABEL: Record<HealthCheckComplexity, string> = {
  "": "لم يُقدَّر بعد",
  low: "منخفض",
  medium: "متوسط",
  high: "مرتفع",
};

/** تسميات حالة بند الفحص (`CompanyHealthCheckItem.ItemStatus`). */
export const HEALTH_CHECK_ITEM_STATUS_LABEL: Record<string, string> = {
  healthy: "سليم",
  follow_up: "يحتاج متابعة",
  risk: "خطر",
  not_applicable: "لا ينطبق",
};

/** تسميات حالة الارتباط (`Engagement.Status`). */
export const ENGAGEMENT_STATUS_LABEL: Record<EngagementStatus, string> = {
  active: "نشط",
  suspended: "معلق",
  revoked: "ملغى",
};

/** تسميات نوع الارتباط (`Engagement.Kind`). */
export const ENGAGEMENT_KIND_LABEL: Record<EngagementKind, string> = {
  standard: "عادي",
  onboarding: "تهيئة مؤقتة",
};

interface MandatoryEvidenceItem {
  mandatory: boolean;
  evidence_value: string | null;
  evidence_note: string;
}

/**
 * رموزُ البنود الإلزامية التي لا يزال ينقصها دليل — قبل الاعتماد يجب أن تعود فارغة.
 * تطابق شرط الرفض الخادمي `evidence_missing` حرفياً كي تُعرض الرسالة قبل الإرسال لا بعده.
 */
export function missingMandatoryEvidenceCodes(
  items: readonly (MandatoryEvidenceItem & { code: string })[],
): string[] {
  return items
    .filter((item) => item.mandatory && !item.evidence_value && !item.evidence_note.trim())
    .map((item) => item.code);
}

/** هل يمكن اعتماد الفحص الآن؟ (تعقيد مُقدَّر + لا بنود إلزامية ناقصة الدليل). */
export function canApproveHealthCheck(
  check: { complexity: HealthCheckComplexity } | null,
  items: readonly (MandatoryEvidenceItem & { code: string })[],
): boolean {
  if (!check || !check.complexity) return false;
  return missingMandatoryEvidenceCodes(items).length === 0;
}

/** «تبقّى N يوماً» أو «انتهت مهلة التهيئة» — نظير `formatTrialRemainingLabel` لإسناد onboarding. */
export function formatOnboardingRemainingLabel(expiresAt: string | null, now: Date = new Date()): string {
  if (!expiresAt) return "";
  const end = new Date(expiresAt);
  if (Number.isNaN(end.getTime())) return "";
  const msRemaining = end.getTime() - now.getTime();
  if (msRemaining <= 0) return "انتهت مهلة التهيئة المؤقتة";
  const daysRemaining = Math.ceil(msRemaining / (1000 * 60 * 60 * 24));
  if (daysRemaining === 1) return "يتبقّى يوم واحد على انتهاء التهيئة المؤقتة";
  if (daysRemaining === 2) return "يتبقّيان يومان على انتهاء التهيئة المؤقتة";
  return `يتبقّى ${formatNumber(daysRemaining)} أيام على انتهاء التهيئة المؤقتة`;
}

/** صياغة موجزة لحمل موظف مقابل طاقته المستهدفة — «٢ / ٣» بالأرقام المنسّقة. */
export function formatCapacityLabel(load: number | string, capacityTarget: number | string): string {
  return `${formatNumber(load)} / ${formatNumber(capacityTarget)}`;
}

export type EngagementAction = "transfer" | "suspend" | "resume" | "revoke";

/** الأفعال المسموحة على ارتباط حسب حالته — مطابقة `EngagementViewSet` (نقل/تعليق/استئناف/إلغاء). */
export function getAllowedEngagementActions(status: EngagementStatus): EngagementAction[] {
  switch (status) {
    case "active":
      return ["transfer", "suspend", "revoke"];
    case "suspended":
      return ["resume", "revoke"];
    case "revoked":
    default:
      return [];
  }
}
