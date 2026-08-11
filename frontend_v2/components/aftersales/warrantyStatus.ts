import {
  WARRANTY_NEAR_EXPIRY_DAYS,
  type WarrantyStatus,
} from "../../utils/warranty";

/**
 * THA-24 م2 — شارة حالة الكفالة (اللون وحده؛ النصّ والحساب في `utils/warranty`).
 *
 * الأصفر ليس حالة ثالثة بل كفالة سارية أوشكت: موظف الكاونتر يحتاج أن يرى
 * ذلك قبل أن ينتهي أجلها لا بعده. مصدر واحد للألوان لأن الشارة تُقرأ في الجدول
 * وفي النافذة معاً، واختلاف اللون بين الموضعين يقرأه المستخدم اختلافَ معنى.
 */
export const warrantyPillClass = (
  status: WarrantyStatus,
  daysRemaining: number,
): string => {
  const tone =
    status !== "active"
      ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
      : daysRemaining <= WARRANTY_NEAR_EXPIRY_DAYS
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
        : "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300";
  return `inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${tone}`;
};
