/**
 * عنوان الـ API هنا = خادم Django فقط (VITE_API_URL → …/api).
 * المساعد الذكي: المتصفح يطلب /api/assistant/chat/ على Django؛ Django يتصل بـ OpenClaw (72.60…:18789) من السيرفر.
 * لا تضع عنوان OpenClaw في الواجهة — التوكن والبروكسي على Django.
 */
import { clientLogger } from "./logger";

/** إذا وُضع عنوان الخادم بدون مسار (مثل http://localhost:8000) يُضاف /api تلقائياً. */
export function resolveApiBase(raw: string): string {
  const trimmed = raw.replace(/\/+$/, "");
  try {
    const u = new URL(trimmed);
    const path = u.pathname.replace(/\/+$/, "") || "/";
    if (path === "/") return `${trimmed}/api`;
    return trimmed;
  } catch {
    return trimmed;
  }
}

export const API_BASE = resolveApiBase(import.meta.env.VITE_API_URL || "http://localhost:8000/api");

const NETWORK_HINT =
  "تعذر الاتصال بالخادم (شبكة/CORS). تحقق: (1) تشغيل Django (2) VITE_API_URL يشير إلى جذر الخادم أو ينتهي بـ /api " +
  `(المُحلّى: ${API_BASE}) (3) سجّل الدخول ليُرسل التوكن`;

const FETCH_TIMEOUT_MS = 120_000;

async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const signalFromCaller = init?.signal;
  const timeoutFn = (AbortSignal as unknown as { timeout?: (ms: number) => AbortSignal })
    .timeout;
  const mergedInit: RequestInit = {
    ...init,
    signal:
      signalFromCaller ??
      (typeof timeoutFn === "function" ? timeoutFn(FETCH_TIMEOUT_MS) : undefined),
  };
  try {
    return await fetch(url, mergedInit);
  } catch (e) {
    const name = e instanceof Error ? e.name : "";
    const domName = e instanceof DOMException ? e.name : "";
    if (
      name === "TimeoutError" ||
      domName === "TimeoutError" ||
      domName === "AbortError"
    ) {
      throw new Error(
        "انتهت مهلة انتظار الخادم (دقيقتان). تحقق من تشغيل Django والشبكة، ثم أعد المحاولة."
      );
    }
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

/** يسطح أخطاء DRF المتداخلة (مثل {lines: [{product: ["..."]}]} أو {customer: ["..."]}) إلى نص واحد. */
function flattenDrfError(data: any): string {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (data.detail) return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
  if (data.error) return typeof data.error === "string" ? data.error : JSON.stringify(data.error);
  const parts: string[] = [];
  function walk(obj: any, prefix: string) {
    if (typeof obj === "string") { parts.push(obj); return; }
    if (Array.isArray(obj)) { obj.forEach(v => parts.push(typeof v === "string" ? v : JSON.stringify(v))); return; }
    if (typeof obj === "object" && obj !== null) {
      Object.entries(obj).forEach(([k, v]) => walk(v, prefix ? `${prefix}.${k}` : k));
    }
  }
  walk(data, "");
  return parts.join("; ") || JSON.stringify(data);
}

async function handleResponseError(res: Response, path: string): Promise<never> {
  const traceId = res.headers.get("X-Trace-ID") || undefined;
  const data = await parseJsonSafe(res);
  let msg = flattenDrfError(data) || `API error: ${res.status} (${path})`;
  if (traceId) {
    msg = `${msg} [Trace ID: ${traceId}]`;
  }
  clientLogger.error(`API Error on ${path}: ${msg}`, {
    status: res.status,
    path,
    data: data as Record<string, unknown>,
  }, traceId);
  throw new Error(msg);
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
    await handleResponseError(res, path);
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
    await handleResponseError(res, path);
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
    await handleResponseError(res, path);
  }

  return (await res.json()) as T;
}

/** POST multipart (لا تضف Content-Type يدوياً — المتصفح يضيف boundary) */
export async function apiPostFormData<T = any>(
  path: string,
  form: FormData,
  opts?: { tenantId?: number }
): Promise<T> {
  const url = `${API_BASE}/${path.replace(/^\/+/, "")}`;
  const token = localStorage.getItem("token");
  const res = await apiFetch(url, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...(opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : {}),
    },
    body: form,
  });

  if (!res.ok) {
    await handleResponseError(res, path);
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
    await handleResponseError(res, path);
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
    await handleResponseError(res, path);
  }
}

