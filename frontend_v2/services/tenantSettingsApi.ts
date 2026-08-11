/**
 * مصدر واحد لقراءة `tenants/settings/current/` (P2-9).
 *
 * النقطة نفسها كانت تُطلَب أربع مرات متطابقة قبل رسم أول شاشة، لأن كل مستهلك
 * يجلبها بنفسه: `AppearanceContext` (مقاس/عائلة الخط) و`SessionSettingsContext`
 * (مهلة الخمول) و`Sidebar` و`CompanySwitcher` (هوية الشركة عبر
 * `hooks/useTenantSettings`). الجسم واحد والشركة واحدة، فالطلبات الثلاثة
 * الزائدة حمل صافٍ × كل مستخدم × كل إقلاع.
 *
 * الدمج هنا لا يحتاج نقطة خادمية جديدة: طلب طائر واحد يتقاسمه كل المستهلكين،
 * ونافذة قصيرة تغطي التركيب المتدرّج للسياقات. مفتاحها الشركة، وأي كتابة
 * (PATCH) تُفرِغها كي لا يقرأ أحدٌ قيمةً سبقَ أن غيّرها المستخدم.
 */
import { apiGetObject } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const TENANT_SETTINGS_TTL_MS = 60_000;

let cached: { key: string; at: number; data: unknown } | null = null;
let inFlight: { key: string; promise: Promise<unknown> } | null = null;

/** تُستدعى بعد كل PATCH على الإعدادات كي تُقرأ القيمة الجديدة لا المحفوظة. */
export function invalidateTenantSettings(): void {
  cached = null;
}

export function getTenantSettings<T = Record<string, unknown>>(
  tenantId?: number,
): Promise<T> {
  const id = tenantId ?? resolveTenantId();
  const key = String(id ?? "");

  if (cached && cached.key === key && Date.now() - cached.at < TENANT_SETTINGS_TTL_MS) {
    return Promise.resolve(cached.data as T);
  }
  if (inFlight && inFlight.key === key) {
    return inFlight.promise as Promise<T>;
  }

  const promise = apiGetObject<T>("tenants/settings/current/", { tenantId: id })
    .then((data) => {
      cached = { key, at: Date.now(), data };
      return data as unknown;
    })
    .finally(() => {
      if (inFlight?.key === key) inFlight = null;
    });
  inFlight = { key, promise };
  return promise as Promise<T>;
}
