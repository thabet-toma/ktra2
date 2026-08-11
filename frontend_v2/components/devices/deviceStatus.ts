import type { DeviceStatus } from "../../services/devicesApi";

/**
 * شارة حالة التتبع بألوانٍ متمايزة كما في نموذج THA-45: أخضر «مسجَّل»، برتقالي
 * «في الفحص»، أزرق «تم التسليم». مصدر واحد لأن الشارة تُقرأ في الجدول وفي
 * المعاينة معاً، واختلاف اللون بين الموضعين يقرأه المستخدم اختلافَ معنى.
 */
const TONES: Record<DeviceStatus, string> = {
  registered: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  in_check: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  delivered: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
};

export const statusPillClass = (status: DeviceStatus): string =>
  `inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${
    TONES[status] ?? "bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"
  }`;
