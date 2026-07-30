/**
 * Tenant id for X-Tenant-Id and API query params.
 * Prefer localStorage `tenantId`, then VITE_TENANT_ID, then 1.
 *
 * Diagnostic helper: setting localStorage.tenantId to a value that doesn't
 * match any tenant in the DB caused "0 شحنة / 0 بيان" symptoms while the
 * deals page (which used to be hardcoded to 1) still showed records.
 */
export function resolveTenantId(): number {
  try {
    const raw = localStorage.getItem("tenantId");
    if (raw != null) {
      const n = parseInt(raw, 10);
      if (Number.isFinite(n) && n > 0) return n;
    }
  } catch {
    /* ignore */
  }
  const env = import.meta.env.VITE_TENANT_ID;
  if (env != null && env !== "") {
    const m = parseInt(String(env), 10);
    if (Number.isFinite(m) && m > 0) return m;
  }
  return 1;
}

/**
 * T-IMPOFFER — الشركة المخزَّنة صراحةً في هذا المتصفح، أو null إن لم توجد.
 *
 * `resolveTenantId` تُلفِّق الرقم 1 عند غياب التخزين (لتمرير رأس X-Tenant-Id)،
 * وهذا التلفيق كان يُقرأ كأنه **اختيار المستخدم**: بعد أول تسجيل دخول (والخروج
 * يمحو المفتاح) تُفتَح الشركة رقم 1 إن كان المستخدم عضواً فيها، فلا تُفتح
 * شركته الافتراضية أبداً. من يحتاج «هل اختار المستخدم شركة؟» يسأل هذه لا تلك.
 */
export function storedTenantId(): number | null {
  try {
    const raw = localStorage.getItem("tenantId");
    if (raw == null) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

export interface TenantMembershipLike {
  tenant: { TenantID: number };
  is_default?: boolean;
}

/**
 * T-IMPOFFER — الشركة التي تُفتح عند الدخول.
 *
 * الأولوية: اختيار صريح مخزَّن في هذا المتصفح ← الشركة الافتراضية للمستخدم ←
 * أول شركة. دالة نقيّة كي تُختبر بلا متصفح.
 */
export function pickActiveMembership<T extends TenantMembershipLike>(
  memberships: T[],
  explicitTenantId: number | null,
): T | null {
  if (memberships.length === 0) return null;
  if (explicitTenantId != null) {
    const chosen = memberships.find(
      (m) => m.tenant.TenantID === explicitTenantId,
    );
    if (chosen) return chosen;
  }
  return memberships.find((m) => m.is_default) || memberships[0];
}

/**
 * task11 M4 — الفرع النشط. null = «كل الفروع» (مستوى الشركة).
 * يُخزن في localStorage.branchId ويُمسح تلقائياً عند تبديل الشركة.
 */
export function resolveBranchId(): number | null {
  try {
    const raw = localStorage.getItem("branchId");
    if (raw != null) {
      const n = parseInt(raw, 10);
      if (Number.isFinite(n) && n > 0) return n;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/**
 * Returns true once per session if the resolved tenant id appears suspicious
 * (e.g. localStorage has a value that doesn't match VITE_TENANT_ID).
 * Call this from the app shell to surface a one-time console warning.
 */
let _warned = false;
export function warnIfTenantMismatch(): void {
  if (_warned) return;
  _warned = true;
  try {
    const raw = localStorage.getItem("tenantId");
    const env = (import.meta as any).env?.VITE_TENANT_ID;
    if (raw != null && env != null && String(raw) !== String(env)) {
      console.warn(
        `[tenantContext] localStorage.tenantId=${raw} ≠ VITE_TENANT_ID=${env}. ` +
          "If shipments/clearance pages show 0 records but deals don't, " +
          "run localStorage.removeItem('tenantId') in DevTools and reload.",
      );
    }
  } catch {
    /* ignore */
  }
}

/**
 * Boot-time auto-recovery. Pings `tenants/settings/current/` with the resolved
 * tenant id; if the backend rejects it (404 / 400 / "tenant not found"), it
 * clears localStorage.tenantId so the next reload falls back to the default.
 *
 * Why this exists: the owner saw "0 شحنة / 0 بيان" while Deals worked. The
 * cause was a stale localStorage.tenantId that no longer matched any tenant
 * in the DB. With this auto-recovery, no DevTools intervention is needed —
 * the app self-heals on next boot.
 *
 * Safe to call multiple times: the validation only runs once per session.
 */
let _validated = false;
export async function autoRecoverInvalidTenant(): Promise<void> {
  if (_validated) return;
  _validated = true;
  try {
    const raw = localStorage.getItem("tenantId");
    if (!raw) return; // no override → using default → no need to validate
    const tid = parseInt(raw, 10);
    if (!Number.isFinite(tid) || tid <= 0) {
      localStorage.removeItem("tenantId");
      console.warn("[tenantContext] Cleared invalid localStorage.tenantId");
      return;
    }
    // Validate with a cheap GET. If it fails, the tenant is bad → clear.
    const token = localStorage.getItem("token");
    const apiBase =
      (import.meta as any).env?.VITE_API_URL || "http://localhost:8000/api";
    const url = `${String(apiBase).replace(/\/+$/, "")}/tenants/settings/current/`;
    const res = await fetch(url, {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `Token ${token}` } : {}),
        "X-Tenant-Id": String(tid),
      },
    });
    if (res.status === 400 || res.status === 404) {
      // Backend explicitly rejected the tenant id.
      localStorage.removeItem("tenantId");
      console.warn(
        `[tenantContext] tenantId=${tid} rejected by backend (${res.status}). ` +
          "Cleared localStorage; reloading to recover.",
      );
      try {
        location.reload();
      } catch {
        /* ignore */
      }
    }
    // 401/403/network errors leave the override alone — those are unrelated.
  } catch {
    /* network down or backend offline — leave override intact */
  }
}
