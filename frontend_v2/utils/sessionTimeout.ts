/**
 * مهلة الخمول القابلة للتهيئة — منطق نقيّ (بلا React) قابل للاختبار.
 * مصدر واحد للحدود والقصّ والتحويل، يستهلكه {@link SessionSettingsContext}.
 */
import { IDLE_TIMEOUT_MS } from "../constants/session.ts";

/** الحدود المسموح بها (تطابق مُدقِّق الخادم: 5 دقائق .. 24 ساعة). */
export const IDLE_MIN_MINUTES = 5;
export const IDLE_MAX_MINUTES = 1440;

/** الافتراضي مشتق من الثابت (3 ساعات) كي يبقى مصدر واحد للقيمة الافتراضية. */
export const DEFAULT_IDLE_MINUTES = Math.round(IDLE_TIMEOUT_MS / 60000);

/** يقصّ الدقائق ضمن النطاق المسموح؛ غير الرقمي ⇒ الافتراضي. */
export function clampIdleMinutes(n: number): number {
  if (!Number.isFinite(n)) return DEFAULT_IDLE_MINUTES;
  return Math.min(IDLE_MAX_MINUTES, Math.max(IDLE_MIN_MINUTES, Math.round(n)));
}

/** يحوّل الدقائق (مقصوصة) إلى مللي ثانية للحارس. */
export function idleMinutesToMs(minutes: number): number {
  return clampIdleMinutes(minutes) * 60000;
}
