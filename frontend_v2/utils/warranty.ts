/**
 * THA-24 م2 — قواعد بطاقة الكفالة الصرفة (بلا React وبلا شبكة).
 *
 * قاعدتان تحكمان هذا الملف، وهما نفسهما قاعدتا الخادم (`after_sales/models.py`):
 *
 * - **الحالة مشتقّة** من تاريخ الانتهاء مقابل اليوم — لا حالة تُخزَّن ولا تُرسَل.
 *   ما هنا عرضٌ لما يحسبه الخادم، لا حسابٌ ثانٍ ينافسه.
 * - **الشهور تقويمية**: 31 يناير + شهر = 28/29 فبراير، لا `+30 يوماً`. كفالة سنة
 *   ليست 360 يوماً، والفرق يظهر على أول بطاقة تُفحص في نهاية مدّتها.
 *
 * الاشتقاق هنا **معاينة** للمستخدم قبل الحفظ فقط؛ التاريخ المخزَّن يبقى ما
 * يحسبه الخادم عند الإنشاء.
 */
// الامتداد صريح: `node --test` يشغّل هذا الملف مباشرةً ولا يحلّ الاستيراد بدونه.
import { formatNumber } from "./formatNumber.ts";

/** مصدر البطاقة — تلقائية من ترحيل فاتورة بيع، أو يدوية أنشأها مستخدم. */
export type WarrantySource = "auto_sale" | "manual";

/** الحالة المشتقّة من تاريخ الانتهاء مقابل اليوم. */
export type WarrantyStatus = "active" | "expired";

/** كفالة سارية تنتهي خلال هذه المدة تُعرض بلون تنبيه لا بلون اطمئنان. */
export const WARRANTY_NEAR_EXPIRY_DAYS = 30;

const pad = (n: number) => String(n).padStart(2, "0");

const daysInMonth = (year: number, month1to12: number): number =>
  new Date(Date.UTC(year, month1to12, 0)).getUTCDate();

/**
 * يضيف شهوراً تقويمية إلى تاريخ `YYYY-MM-DD` ويردّ الصيغة نفسها.
 *
 * مرآة `after_sales.models.add_months`: اليوم يُثبَّت على آخر الشهر حين يقصر.
 * الحساب على النص لا على `Date` المحلي — إنشاء `Date` من نص بلا منطقة زمنية
 * يزيح اليوم يوماً كاملاً على أجهزة شرق غرينتش.
 */
export function addWarrantyMonths(startIso: string, months: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec((startIso || "").trim());
  if (!match) return "";
  const [, y, m, d] = match;
  const added = Math.trunc(Number(months) || 0);
  const total = Number(y) * 12 + (Number(m) - 1) + added;
  const year = Math.floor(total / 12);
  const month = (total % 12) + 1;
  const day = Math.min(Number(d), daysInMonth(year, month));
  return `${year}-${pad(month)}-${pad(day)}`;
}

/**
 * تاريخ الانتهاء المعروض قبل الحفظ: الصريح يتقدّم دائماً على المشتقّ — من كتب
 * تاريخاً بيده لا تُعاد كتابته من المدة.
 */
export function deriveWarrantyEnd(
  startIso: string,
  months: number | null,
  explicitEndIso?: string | null,
): string {
  const explicit = (explicitEndIso || "").trim();
  if (explicit) return explicit;
  if (!startIso || !months) return "";
  return addWarrantyMonths(startIso, months);
}

export const warrantyStatusLabel = (status: WarrantyStatus): string =>
  status === "active" ? "سارية" : "منتهية";

/**
 * «باقٍ ١٢ يوماً» / «انتهت منذ ٣٠ يوماً» — الرقم وحده يُقرأ خطأً على المنتهية،
 * إذ يعود من الخادم بإشارة سالبة.
 */
export function warrantyRemainingText(
  status: WarrantyStatus,
  daysRemaining: number,
): string {
  const days = Number(daysRemaining) || 0;
  if (status !== "active") return `انتهت منذ ${formatNumber(Math.abs(days))} يوماً`;
  if (days === 0) return "تنتهي اليوم";
  return `باقٍ ${formatNumber(days)} يوماً`;
}
