/**
 * SA-7 — جلسة دعم كترا: سوبر أدمن داخل شركةٍ ليس عضواً فيها، بإذنٍ ساري منها.
 *
 * الخادم هو الحَكَم (كل طلب يمرّ بـ`enforce_support_access`)؛ هذه الحالة المحلية
 * للواجهة وحدها: أيُّ شركةٍ نفتحها، وحتى متى، وإلى أين نعود عند الخروج. لذلك لا
 * تُمنح بها صلاحيةٌ ولا تُفترض — انتهاؤها هنا يُظهر «انتهى الإذن»، وانتهاؤها في
 * الخادم قبل ذلك (سحب الشركة) يصل رمزَ `support_access_required`.
 */

export const SUPPORT_SESSION_KEY = "supportSession";

export interface SupportSession {
  grantId: number;
  tenantId: number;
  tenantName: string;
  scope: "read_only" | "full";
  isEmergency: boolean;
  /** ISO — نهاية الإذن كما أعادها الخادم. */
  expiresAt: string;
  /** الشركة التي كانت نشطةً قبل الدخول — يعود إليها الخروج (`null` = بلا شركة). */
  returnTenantId: number | null;
}

type Storage = Pick<globalThis.Storage, "getItem" | "setItem" | "removeItem">;

const defaultStorage = (): Storage | null => {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
};

/** يقرأ الجلسة ويرفض أيَّ شكلٍ ناقص — قيمةٌ عبثَ بها أحدٌ لا تفتح شركة. */
export function parseSupportSession(raw: string | null): SupportSession | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<SupportSession>;
    if (
      typeof value.grantId !== "number" || typeof value.tenantId !== "number"
      || typeof value.expiresAt !== "string" || Number.isNaN(Date.parse(value.expiresAt))
      || (value.scope !== "read_only" && value.scope !== "full")
    ) return null;
    return {
      grantId: value.grantId,
      tenantId: value.tenantId,
      tenantName: typeof value.tenantName === "string" ? value.tenantName : "",
      scope: value.scope,
      isEmergency: value.isEmergency === true,
      expiresAt: value.expiresAt,
      returnTenantId: typeof value.returnTenantId === "number" ? value.returnTenantId : null,
    };
  } catch {
    return null;
  }
}

export function readSupportSession(storage: Storage | null = defaultStorage()): SupportSession | null {
  return parseSupportSession(storage?.getItem(SUPPORT_SESSION_KEY) ?? null);
}

export function writeSupportSession(session: SupportSession, storage: Storage | null = defaultStorage()): void {
  storage?.setItem(SUPPORT_SESSION_KEY, JSON.stringify(session));
}

export function clearSupportSession(storage: Storage | null = defaultStorage()): void {
  storage?.removeItem(SUPPORT_SESSION_KEY);
}

/** الدقائق الباقية (مقرَّبةً لأسفل، لا تنزل تحت الصفر). */
export function supportMinutesLeft(session: SupportSession, now: number = Date.now()): number {
  return Math.max(0, Math.floor((Date.parse(session.expiresAt) - now) / 60000));
}

export function supportSessionExpired(session: SupportSession, now: number = Date.now()): boolean {
  return Date.parse(session.expiresAt) <= now;
}

/** «2 س 15 د» / «40 د» — للشريط؛ الرقم نفسه يمرّ بـ`formatNumber` عند العرض. */
export function splitMinutes(minutes: number): { hours: number; minutes: number } {
  return { hours: Math.floor(minutes / 60), minutes: minutes % 60 };
}
