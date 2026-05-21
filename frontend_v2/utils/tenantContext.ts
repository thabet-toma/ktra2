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
