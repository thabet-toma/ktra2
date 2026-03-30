const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000/api").replace(
  /\/+$/,
  ""
);

const NETWORK_HINT =
  "تعذر الاتصال بالخادم (شبكة/CORS). تحقق: (1) تشغيل Django (2) VITE_API_URL ينتهي بـ /api " +
  `(الحالي: ${API_BASE}) (3) سجّل الدخول ليُرسل التوكن`;

async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e) {
    const name = e instanceof Error ? e.name : "";
    if (name === "TypeError" || String(e).includes("fetch")) {
      throw new Error(NETWORK_HINT);
    }
    throw e;
  }
}

function getHeaders(extra?: Record<string, string>, withJsonContentType: boolean = true) {
  const token = localStorage.getItem("token");
  return {
    ...(withJsonContentType ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...(extra || {}),
  };
}

async function parseJsonSafe(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function toList<T = any>(payload: any): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && Array.isArray(payload.results)) return payload.results as T[];
  return [];
}

export async function apiGetList<T = any>(
  path: string,
  opts?: { tenantId?: number; query?: Record<string, string | number | boolean | undefined> }
): Promise<T[]> {
  const q = new URLSearchParams();
  const query = opts?.query || {};
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined) return;
    q.set(k, String(v));
  });

  const url = `${API_BASE}/${path.replace(/^\/+/, "")}${q.toString() ? `?${q}` : ""}`;
  const res = await apiFetch(url, {
    // GET should avoid Content-Type header to reduce unnecessary CORS preflight failures.
    headers: getHeaders(
      opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : undefined,
      false
    ),
  });

  if (!res.ok) {
    const data = await parseJsonSafe(res);
    const msg =
      (data && (data.detail || data.error)) ||
      `API error: ${res.status} (${path})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return toList<T>(await res.json());
}

export async function apiGetObject<T = any>(
  path: string,
  opts?: { tenantId?: number }
): Promise<T> {
  const url = `${API_BASE}/${path.replace(/^\/+/, "")}`;
  const res = await apiFetch(url, {
    headers: getHeaders(
      opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : undefined,
      false
    ),
  });

  if (!res.ok) {
    const data = await parseJsonSafe(res);
    const msg =
      (data && (data.detail || data.error)) ||
      `API error: ${res.status} (${path})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return (await res.json()) as T;
}

export async function apiPostObject<T = any>(
  path: string,
  body: Record<string, any>,
  opts?: { tenantId?: number }
): Promise<T> {
  const url = `${API_BASE}/${path.replace(/^\/+/, "")}`;
  const res = await apiFetch(url, {
    method: "POST",
    headers: getHeaders(
      opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : undefined,
      true
    ),
    body: JSON.stringify(body ?? {}),
  });

  if (!res.ok) {
    const data = await parseJsonSafe(res);
    const msg =
      (data && (data.detail || data.error || data)) ||
      `API error: ${res.status} (${path})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return (await res.json()) as T;
}

export async function apiPatchObject<T = any>(
  path: string,
  body: Record<string, any>,
  opts?: { tenantId?: number }
): Promise<T> {
  const url = `${API_BASE}/${path.replace(/^\/+/, "")}`;
  const res = await apiFetch(url, {
    method: "PATCH",
    headers: getHeaders(
      opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : undefined,
      true
    ),
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const data = await parseJsonSafe(res);
    const msg = (data && (data.detail || data.error || data)) || `API error: ${res.status} (${path})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return (await res.json()) as T;
}

export async function apiDelete(path: string, opts?: { tenantId?: number }): Promise<void> {
  const url = `${API_BASE}/${path.replace(/^\/+/, "")}`;
  const res = await apiFetch(url, {
    method: "DELETE",
    headers: getHeaders(
      opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : undefined,
      false
    ),
  });
  if (!res.ok) {
    const data = await parseJsonSafe(res);
    const msg = (data && (data.detail || data.error || data)) || `API error: ${res.status} (${path})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
}

