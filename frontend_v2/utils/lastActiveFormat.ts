import { formatDateTimeValue, formatTimeValue } from './formatDate.ts';

/**
 * تنسيق واحتساب حالة آخر ظهور لموظفي المنصة (م٦).
 *
 * يعتمد عتبة 15 دقيقة صارمة:
 * - خلال 15 دقيقة (<= 15m): نشط مؤخراً.
 * - أكثر من 15 دقيقة (> 15m): غير نشط.
 *
 * الأرقام غربية حصراً (0-9).
 */

export interface LastActiveBadge {
  label: string;
  active: boolean;
  className: string;
}

export function isRecentlyActive(
  lastActiveAt: string | Date | null | undefined,
  now: Date = new Date(),
  thresholdMinutes = 15
): boolean {
  if (!lastActiveAt) {
    return false;
  }

  const date = typeof lastActiveAt === 'string' ? new Date(lastActiveAt) : lastActiveAt;
  const timestamp = date.getTime();
  if (isNaN(timestamp)) {
    return false;
  }

  const nowMs = now.getTime();
  if (timestamp > nowMs) {
    return true;
  }

  const diffMs = nowMs - timestamp;
  const thresholdMs = thresholdMinutes * 60 * 1000;
  return diffMs <= thresholdMs;
}

export function formatLastActive(
  lastActiveAt: string | Date | null | undefined,
  now: Date = new Date(),
  thresholdMinutes = 15
): string {
  if (!lastActiveAt) {
    return 'لم يسجل نشاطاً';
  }

  const date = typeof lastActiveAt === 'string' ? new Date(lastActiveAt) : lastActiveAt;
  const timestamp = date.getTime();
  if (isNaN(timestamp)) {
    return 'لم يسجل نشاطاً';
  }

  // **طابعُ وقتٍ لا مصباح**: المواصفةُ تُسقط «نشط الآن» صراحةً — «المصباحُ يَعِد
  // بدقّةٍ لا يملكها النظام»، والمصدرُ نافذةُ خمسِ دقائقَ على `UserDevice`. فالساعةُ
  // المعروضةُ صادقةٌ بذاتها، والقربُ يُقال بالمدّة لا بلونٍ يوحي بحضورٍ لحظيّ.
  const clock = formatTimeValue(date);
  const nowMs = now.getTime();
  const diffMinutes = Math.floor(Math.max(0, nowMs - timestamp) / 60000);

  if (diffMinutes <= thresholdMinutes) {
    return `آخر ظهور ${clock} (منذ ${diffMinutes} دقيقة)`;
  }

  if (diffMinutes < 60) {
    return `آخر ظهور ${clock} (منذ ${diffMinutes} دقيقة)`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `آخر ظهور ${clock} (منذ ${diffHours} ساعة)`;
  }

  const diffDays = Math.floor(diffHours / 24);
  return `آخر ظهور ${formatDateTimeValue(date)} (منذ ${diffDays} يوم)`;
}

export function getLastActiveBadge(
  lastActiveAt: string | Date | null | undefined,
  now: Date = new Date(),
  thresholdMinutes = 15
): LastActiveBadge {
  const active = isRecentlyActive(lastActiveAt, now, thresholdMinutes);
  const label = formatLastActive(lastActiveAt, now, thresholdMinutes);

  if (active) {
    return {
      label,
      active: true,
      className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    };
  }

  return {
    label,
    active: false,
    className: 'bg-slate-50 text-slate-600 border-slate-200',
  };
}
