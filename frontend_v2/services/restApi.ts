/**
 * عنوان الـ API هنا = خادم Django فقط (VITE_API_URL → …/api).
 * المساعد الذكي: المتصفح يطلب /api/assistant/chat/ على Django؛ Django يتصل بـ OpenClaw (72.60…:18789) من السيرفر.
 * لا تضع عنوان OpenClaw في الواجهة — التوكن والبروكسي على Django.
 */
import { clientLogger } from "./logger";
import { humanizeDrfError, extractDrfFieldErrors } from "../utils/drfError";
import { resolveBranchId } from "../utils/tenantContext";
import { emitEngagementRevoked, emitSessionExpired, emitUserActivity } from "../utils/sessionEvents";
import { isUserActivityRequest, writeLastActivity } from "../utils/idleSession";
import {
  remainingRequestBudgetMs,
  retryFitsRequestBudget,
} from "../utils/networkRequestBudget";
import db from "./offline/db";

/** فشل شبكة/مهلة (أوفلاين) — يميّزه عن أخطاء HTTP كي يرجع القارئ لكاش الأوفلاين. */
export class NetworkError extends Error {}

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

// سقف واضح لمسارات التطبيق العادية: يكفي لتذبذب الاستضافة المشتركة، ولا يترك
// المستخدم أمام spinner لدقيقتين. التقارير الثقيلة ينبغي أن تعطي تقدماً بدلاً
// من إبقاء طلب واجهة عادي مفتوحاً بلا تفسير.
export const FETCH_TIMEOUT_MS = 30_000;

// إعادة المحاولة التلقائية لفشل الاتصال العابر (HTTP/3/QUIC أو لحظة توقّف gunicorn).
// تُطبَّق فقط على طلبات القراءة الآمنة (GET/HEAD) لتفادي تكرار عمليات الكتابة.
const MAX_FETCH_ATTEMPTS = 3;
const RETRY_DELAYS_MS = [400, 1200]; // تأخير قبل المحاولة الثانية ثم الثالثة

function isSafeToRetry(init?: RequestInit): boolean {
  const method = (init?.method || "GET").toUpperCase();
  // لا نعيد المحاولة إذا مرّر المتصل signal خاص به (قد يكون للإلغاء)
  return (method === "GET" || method === "HEAD") && !init?.signal;
}

export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  // كل عملية كتابة = المستخدم يعمل الآن؛ تُمدَّد مهلة الخمول ولو لم يلمس فأرة
  // ولا لوحة مفاتيح منذ فترة (إدخال بالباركود، لصق، اختصارات).
  if (isUserActivityRequest(init?.method)) {
    writeLastActivity(localStorage, Date.now());
    emitUserActivity();
  }
  const canRetry = isSafeToRetry(init);
  const maxAttempts = canRetry ? MAX_FETCH_ATTEMPTS : 1;
  // هذا deadline للطلب كله، لا لكل محاولة. سابقاً كانت كل محاولة تحصل على
  // 30 ثانية مستقلة، فكان النص يقول 30 ثانية بينما الانتظار قد يصل 91.6 ثانية.
  const deadlineMs = Date.now() + FETCH_TIMEOUT_MS;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    // AbortSignal.timeout غير متاح في بعض المتصفحات التي ما زالت مستخدمة في
    // بيئة الاستضافة. Controller يدعم المهلة دائماً ويجمعها مع signal المتصل.
    const controller = new AbortController();
    const callerSignal = init?.signal;
    let timedOut = false;
    const remainingMs = remainingRequestBudgetMs(deadlineMs);
    if (remainingMs <= 0) {
      throw new NetworkError(
        "انتهت مهلة انتظار الخادم (30 ثانية). تحقق من الاتصال، ثم أعد المحاولة."
      );
    }
    const abortFromCaller = () => controller.abort(callerSignal?.reason);
    if (callerSignal?.aborted) abortFromCaller();
    else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
    const timeoutId = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, remainingMs);
    const mergedInit: RequestInit = { ...init, signal: controller.signal };
    try {
      return await fetch(url, mergedInit);
    } catch (e) {
      const name = e instanceof Error ? e.name : "";
      const domName = e instanceof DOMException ? e.name : "";
      const isTimeout =
        timedOut ||
        name === "TimeoutError" ||
        domName === "TimeoutError";
      const callerAborted = Boolean(callerSignal?.aborted) && !timedOut;
      const isNetwork = name === "TypeError" || String(e).includes("fetch");

      // إلغاء المكوّن/المستخدم ليس فشل شبكة ولا timeout؛ اترك المستدعي يميّزه.
      if (callerAborted) throw e;

      // فشل شبكة عابر على طلب آمن + ما زال في محاولات → انتظر ثم أعد
      if (canRetry && isNetwork && !isTimeout && attempt < maxAttempts - 1) {
        const retryDelayMs = RETRY_DELAYS_MS[attempt] ?? 1200;
        if (retryFitsRequestBudget(deadlineMs, retryDelayMs)) {
          await new Promise((r) => setTimeout(r, retryDelayMs));
          continue;
        }
        throw new NetworkError(
          "انتهت مهلة انتظار الخادم (30 ثانية). تحقق من الاتصال، ثم أعد المحاولة."
        );
      }

      if (isTimeout) {
        throw new NetworkError(
          "انتهت مهلة انتظار الخادم (30 ثانية). تحقق من الاتصال، ثم أعد المحاولة."
        );
      }
      if (isNetwork) {
        throw new NetworkError(NETWORK_HINT);
      }
      throw e;
    } finally {
      globalThis.clearTimeout(timeoutId);
      callerSignal?.removeEventListener("abort", abortFromCaller);
    }
  }
  // لا يُفترض الوصول هنا (الحلقة إمّا تُرجع استجابة أو ترمي خطأً)
  throw new NetworkError(NETWORK_HINT);
}

function getHeaders(extra?: Record<string, string>, withJsonContentType: boolean = true) {
  const token = localStorage.getItem("token");
  // task11 M4: الفرع النشط يُرسل تلقائياً مع كل طلب — الباك-إند يفلتر
  // الفواتير/المخزون/التقارير به. غيابه = «كل الفروع».
  const branchId = resolveBranchId();
  return {
    ...(withJsonContentType ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...(branchId ? { "X-Branch-Id": String(branchId) } : {}),
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

// ── ترقيم الصفحات (صيانة الأداء 2026-07) ────────────────────────────────────
// الباك-إند يرقّم فقط عند تمرير ?page= (OptionalPageNumberPagination) فيرجع
// {results,count,next}. هذا الشكل الموحّد يتعامل مع الحالتين: مصفوفة خام
// (خادم قديم/بلا ترقيم) أو غلاف DRF — فلا تنكسر الشاشة أثناء تفاوت النشر.
export interface PagedList<T = any> {
  results: T[];
  count: number;
  hasNext: boolean;
}

export function toPagedList<T = any>(payload: any): PagedList<T> {
  if (Array.isArray(payload)) {
    return { results: payload as T[], count: payload.length, hasNext: false };
  }
  if (payload && Array.isArray(payload.results)) {
    return {
      results: payload.results as T[],
      count: Number(payload.count ?? payload.results.length) || payload.results.length,
      hasNext: payload.next != null,
    };
  }
  return { results: [], count: 0, hasNext: false };
}

// ── كاش القراءة أوفلاين (قراءة فقط) ─────────────────────────────────────────
// مفتاح الكاش = URL كامل + المستأجر + الفرع النشط، فلا تتداخل الشركات/الفروع.
function listCacheKey(url: string, tenantId?: number): string {
  const branchId = resolveBranchId();
  return `${url}|t=${tenantId ?? ""}|b=${branchId ?? ""}`;
}

/** يخزّن آخر قائمة ناجحة (fire-and-forget). فشل IndexedDB لا يعطّل الطلب. */
async function writeListCache(key: string, list: unknown[]): Promise<void> {
  try {
    const now = new Date().toISOString();
    await db.api_list_cache.put({ url: key, data: JSON.stringify(list), updated_at: now });
    // علامة تُشعِر OfflineBanner بوجود بيانات محفوظة (لون أصفر بدل الأحمر).
    await db.cache_meta.put({ key: "api_list_cache", updated_at: now });
  } catch { /* IndexedDB غير متاح — تجاهل */ }
}

// سقف عمر كاش الأوفلاين: أقدم من 7 أيام يُرفض بدل تقديمه كأنه حديث —
// فتظهر حالة «غير متصل» الطبيعية بدل بيانات مالية قديمة جداً بصمت.
const MAX_LIST_CACHE_AGE_MS = 7 * 24 * 60 * 60 * 1000;

async function readListCache<T>(key: string): Promise<T[] | null> {
  try {
    const row = await db.api_list_cache.get(key);
    if (row) {
      const age = Date.now() - new Date(row.updated_at).getTime();
      if (!Number.isFinite(age) || age > MAX_LIST_CACHE_AGE_MS) return null;
      return JSON.parse(row.data) as T[];
    }
  } catch { /* تجاهل */ }
  return null;
}

async function handleResponseError(res: Response, path: string): Promise<never> {
  const data = await parseJsonSafe(res);
  // T-CHQ3/و: الخادم يضع `trace_id` في **جسم** استجابة الـ500 (لا في ترويسة)،
  // وقراءة الترويسة وحدها كانت تُسقطه — فيصل المستخدم برسالة «حدث خطأ داخلي في
  // الخادم» بلا أي مفتاح يربطها بسطر اللوغ الذي يحمل الاستثناء.
  const traceId =
    res.headers.get("X-Trace-ID")
    || (data as { trace_id?: string } | null)?.trace_id
    || undefined;
  // G2: أخطاء DRF تُحوَّل لنص عربي مربوط بالحقل (utils/drfError) بدل JSON خام.
  let msg = humanizeDrfError(data) || `تعذّر إتمام العملية (${res.status})`;
  // 401 = التوكن مفقود أو أُبطل (تبويب آخر أنهى الجلسة). رسالة الخادم
  // «لم يتم تزويد بيانات الدخول» لا تقول للمستخدم ماذا يفعل — نستبدلها ونرفع
  // حدث انتهاء الجلسة ليتولّى IdleTimeoutGuard إعادته لتسجيل الدخول.
  if (res.status === 401) {
    msg = "انتهت الجلسة. الرجاء تسجيل الدخول من جديد للمتابعة.";
    emitSessionExpired();
  }
  const responseCode = (data as { code?: string } | null)?.code;
  if (responseCode === "engagement_revoked" || responseCode === "engagement_inactive") {
    emitEngagementRevoked();
  }
  // الخطأ الداخلي بلا مسار = بلاغ لا يمكن تشخيصه («بضرب إيرور» — أيّ نداء؟).
  // و`error` يرسله الخادم في وضع التطوير وحده = نوع الاستثناء ونصّه.
  if (responseCode === "internal_error") {
    const serverError = (data as { error?: string } | null)?.error;
    msg = `${msg} (${path})${serverError ? ` — ${serverError}` : ""}`;
  }
  if (traceId) {
    msg = `${msg} [Trace ID: ${traceId}]`;
  }
  clientLogger.error(`API Error on ${path}: ${msg}`, {
    status: res.status,
    path,
    data: data as Record<string, unknown>,
  }, traceId);
  // G6: أرفق خريطة أخطاء الحقول والحالة على الاستثناء كي تُبرز النماذج الحقل الناقص.
  const err = new Error(msg) as Error & {
    fieldErrors?: Record<string, string>;
    status?: number;
    data?: unknown;
  };
  err.fieldErrors = extractDrfFieldErrors(data);
  err.status = res.status;
  err.data = data;
  throw err;
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
  const cacheKey = listCacheKey(url, opts?.tenantId);
  try {
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

    const list = toList<T>(await res.json());
    void writeListCache(cacheKey, list);
    return list;
  } catch (e) {
    // أوفلاين للقراءة فقط: عند فشل الشبكة نرجع لآخر قائمة محفوظة. أخطاء HTTP/التطبيق
    // (401/500…) تُرمى كما هي — لا نُخفيها بكاش قديم.
    if (e instanceof NetworkError) {
      const cached = await readListCache<T>(cacheKey);
      if (cached) {
        clientLogger.warn("api.offline_cache_hit", { path });
        return cached;
      }
    }
    throw e;
  }
}

/**
 * جلب قائمة مُرقَّمة — مرِّر page (وpage_size اختياري) في query.
 * كاش الأوفلاين: الصفحة الأولى فقط (أحدث الصفوف) تُحفَظ وتُسترجَع عند فشل الشبكة.
 */
export async function apiGetPagedList<T = any>(
  path: string,
  opts?: { tenantId?: number; query?: Record<string, string | number | boolean | undefined> }
): Promise<PagedList<T>> {
  const q = new URLSearchParams();
  const query = opts?.query || {};
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined) return;
    q.set(k, String(v));
  });
  const isFirstPage = String(query.page ?? "1") === "1";

  const url = `${API_BASE}/${path.replace(/^\/+/, "")}${q.toString() ? `?${q}` : ""}`;
  const cacheKey = listCacheKey(url, opts?.tenantId);
  try {
    const res = await apiFetch(url, {
      headers: getHeaders(
        opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : undefined,
        false
      ),
    });
    if (!res.ok) {
      await handleResponseError(res, path);
    }
    const paged = toPagedList<T>(await res.json());
    if (isFirstPage) void writeListCache(cacheKey, paged.results);
    return paged;
  } catch (e) {
    if (e instanceof NetworkError && isFirstPage) {
      const cached = await readListCache<T>(cacheKey);
      if (cached) {
        clientLogger.warn("api.offline_cache_hit", { path });
        return { results: cached, count: cached.length, hasNext: false };
      }
    }
    throw e;
  }
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
  const branchId = resolveBranchId();
  const res = await apiFetch(url, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...(opts?.tenantId ? { "X-Tenant-Id": String(opts.tenantId) } : {}),
      ...(branchId ? { "X-Branch-Id": String(branchId) } : {}),
    },
    body: form,
  });

  if (!res.ok) {
    await handleResponseError(res, path);
  }

  return (await res.json()) as T;
}

/** POST يُعيد ملفاً (CSV مثلاً) بدل JSON — نفس ترويسات المصادقة والشركة. */
export async function apiPostForBlob(
  path: string,
  body: Record<string, any>,
  opts?: { tenantId?: number }
): Promise<Blob> {
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

  return await res.blob();
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
