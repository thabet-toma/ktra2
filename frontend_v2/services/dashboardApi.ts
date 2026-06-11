import type { DashboardData } from "../types/dashboard";
import { resolveTenantId } from "../utils/tenantContext";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function fetchDashboard(): Promise<DashboardData> {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE}/dashboard/`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Token ${token}` } : {}),
      // task11 R2: لوحة المؤشرات تتبع الشركة النشطة
      "X-Tenant-Id": String(resolveTenantId()),
    },
  });
  if (!res.ok) throw new Error(`Dashboard API: ${res.status}`);
  return res.json();
}
