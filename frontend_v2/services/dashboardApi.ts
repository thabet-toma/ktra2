import type { DashboardData } from "../types/dashboard";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function fetchDashboard(): Promise<DashboardData> {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE}/dashboard/`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`Dashboard API: ${res.status}`);
  return res.json();
}
