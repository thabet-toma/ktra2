/**
 * عميل وثائق يشبه واجهة Firestore لكنه يتحدث مع Django (MySQL) عبر /api/mapper/
 * — لا يستخدم Firebase.
 */
export const db = {};

/** قاعدة عنوان الـ API: يجب أن تنتهي بدون شرطة مكررة؛ المسار النهائي .../api */
const API_BASE = (
    import.meta.env.VITE_API_URL || "http://localhost:8000/api"
).replace(/\/+$/, "");

const mapperUrl = (docPath: string) =>
    `${API_BASE}/mapper/${docPath.replace(/^\/+/, "")}/`;

const NETWORK_HINT =
    "تعذر الاتصال بالخادم (شبكة/CORS). تحقق: (1) تشغيل Django (2) VITE_API_URL يشير لنفس الجهاز/المنفذ وينتهي بـ /api " +
    `(الحالي: ${API_BASE}) (3) إذا تفتح الواجهة من IP الشبكة أضف المصدر في DJANGO_CORS_EXTRA_ORIGINS أو DJANGO_CORS_ALLOW_ALL=1 للتطوير (4) سجّل الدخول ليُرسل التوكن`;

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

import { resolveTenantId } from "../utils/tenantContext";

const getHeaders = () => {
    const token = localStorage.getItem("token");
    return {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Token ${token}` } : {}),
        // Mapper docs are company-scoped on the backend; always send the
        // active company so archive/suppliers/deals follow the switcher.
        "X-Tenant-Id": String(resolveTenantId()),
    };
};

async function throwIfBadResponse(
    res: Response,
    context: string
): Promise<void> {
    if (res.ok) return;
    let detail = `${context}: ${res.status}`;
    try {
        const j = await res.json();
        if (typeof j.detail === "string") detail = j.detail;
        else if (j.detail != null) detail = JSON.stringify(j.detail);
    } catch {
        try {
            const t = await res.text();
            if (t) detail = t.slice(0, 500);
        } catch {
            /* ignore */
        }
    }
    throw new Error(detail);
}

export const collection = (dbInstance: any, path: string, ...segments: string[]) => {
    return { path: [path, ...segments].join("/") };
};

export const doc = (dbInstanceOrCol: any, path?: string, ...segments: string[]) => {
    if (path === undefined) {
        const autoId = crypto.randomUUID();
        return { path: (dbInstanceOrCol?.path || "") + "/" + autoId, id: autoId };
    }
    if (dbInstanceOrCol && dbInstanceOrCol.path) {
        return { path: dbInstanceOrCol.path + "/" + path, id: path };
    }
    const fullPath = [path, ...segments].join("/");
    const parts = fullPath.split("/");
    return { path: fullPath, id: parts[parts.length - 1] };
};

export const getDoc = async (ref: any) => {
    const res = await apiFetch(mapperUrl(ref.path), { headers: getHeaders() });
    if (!res.ok) return { exists: () => false, data: () => null, id: ref.id };
    const data = await res.json();
    return { exists: () => true, data: () => data, id: ref.id };
};

export const getDocs = async (queryRef: any) => {
    let url = mapperUrl(queryRef.path);
    if (queryRef.queryString) url += `?${queryRef.queryString}`;

    const res = await apiFetch(url, { headers: getHeaders() });
    if (!res.ok) return { docs: [], empty: true };
    let data: unknown;
    try {
        data = await res.json();
    } catch {
        return { docs: [], empty: true };
    }
    const results = Array.isArray(data)
        ? data
        : (data as { results?: unknown[] })?.results || [];
    const docs = results.map((item: any) => ({
        id: item.id || item._id,
        data: () => item,
    }));
    return { docs, empty: docs.length === 0 };
};

export const setDoc = async (ref: any, data: any) => {
    const res = await apiFetch(mapperUrl(ref.path), {
        method: "PUT",
        headers: getHeaders(),
        body: JSON.stringify(data ?? {}),
    });
    await throwIfBadResponse(res, "setDoc");
};

export const updateDoc = async (ref: any, data: any) => {
    const res = await apiFetch(mapperUrl(ref.path), {
        method: "PATCH",
        headers: getHeaders(),
        body: JSON.stringify(data ?? {}),
    });
    await throwIfBadResponse(res, "updateDoc");
};

export const deleteDoc = async (ref: any) => {
    const res = await apiFetch(mapperUrl(ref.path), {
        method: "DELETE",
        headers: getHeaders(),
    });
    await throwIfBadResponse(res, "deleteDoc");
};

export const addDoc = async (col: any, data: any) => {
    const res = await apiFetch(mapperUrl(col.path), {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify(data ?? {}),
    });
    await throwIfBadResponse(res, "addDoc");
    const result = await res.json();
    return { id: result.id || result._id };
};

export const query = (col: any, ...constraints: any[]) => {
    const params = new URLSearchParams();
    constraints.forEach((c) => {
        if (c.type === "where")
            params.append(`${c.field}__${c.op}`, c.value);
        if (c.type === "orderBy")
            params.append(
                "ordering",
                c.direction === "desc" ? `-${c.field}` : c.field
            );
        if (c.type === "limit") params.append("limit", c.value);
    });
    return { path: col.path, queryString: params.toString() };
};

export const where = (field: string, op: string, value: any) => {
    const mapOp =
        op === "=="
            ? "exact"
            : op === ">="
              ? "gte"
              : op === "<="
                ? "lte"
                : op === "array-contains"
                  ? "contains"
                  : "exact";
    return { type: "where", field, op: mapOp, value };
};

export const orderBy = (field: string, direction: string = "asc") => ({
    type: "orderBy",
    field,
    direction,
});
export const limit = (value: number) => ({ type: "limit", value });
export const startAfter = (docSnapshot: any) => ({
    type: "startAfter",
    doc: docSnapshot,
});

export const getCountFromServer = async (queryRef: any) => {
    const { docs } = await getDocs(queryRef);
    return { data: () => ({ count: docs.length }) };
};

export const onSnapshot = (ref: any, callbackOrObserver: any) => {
    // Firestore supports both onSnapshot(q, fn) and onSnapshot(q, {next, error}).
    // Passing the observer object straight into Promise.then() silently ignored
    // it (then() drops non-function args) — pages using the {next} form never
    // received data and spun forever.
    const next: ((snap: any) => void) | undefined =
        typeof callbackOrObserver === "function"
            ? callbackOrObserver
            : callbackOrObserver?.next?.bind(callbackOrObserver);
    const onError: ((e: unknown) => void) | undefined =
        typeof callbackOrObserver === "function"
            ? undefined
            : callbackOrObserver?.error?.bind(callbackOrObserver);

    const tick = (silent: boolean) => {
        const p = ref.queryString !== undefined ? getDocs(ref) : getDoc(ref);
        p.then((snap) => next?.(snap)).catch((e) => {
            if (!silent) onError?.(e);
        });
    };
    tick(false);
    const interval = setInterval(() => tick(true), 5000);
    return () => clearInterval(interval);
};

export const serverTimestamp = () => new Date().toISOString();

export class Timestamp {
    private _date: Date;
    constructor(seconds: number, nanoseconds: number = 0) {
        this._date = new Date(seconds * 1000);
    }
    toDate() {
        return this._date;
    }
    toISOString() {
        return this._date.toISOString();
    }
    static now() {
        return new Timestamp(Date.now() / 1000);
    }
    static fromDate(d: Date) {
        return new Timestamp(d.getTime() / 1000);
    }
}

export const runTransaction = async (
    dbInstance: any,
    updateFunction: (transaction: any) => Promise<void>
) => {
    const transaction = {
        get: getDoc,
        set: setDoc,
        update: updateDoc,
        delete: deleteDoc,
    };
    await updateFunction(transaction);
};

export type QueryDocumentSnapshot = any;
