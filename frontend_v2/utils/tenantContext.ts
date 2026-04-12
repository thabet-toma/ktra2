/**
 * Tenant id for X-Tenant-Id and API query params.
 * Prefer localStorage `tenantId`, then VITE_TENANT_ID, then 1.
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
