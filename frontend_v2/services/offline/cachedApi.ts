import db from './db';

type CacheResult<T> = { data: T; fromCache: boolean; age_ms: number };

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

function getHeaders(tenantId?: number): Record<string, string> {
  const h: Record<string, string> = {};
  const token = localStorage.getItem('token');
  if (token) h['Authorization'] = `Token ${token}`;
  if (tenantId) h['X-Tenant-Id'] = String(tenantId);
  return h;
}

async function log(level: 'info' | 'warn' | 'error', message: string, payload?: unknown) {
  try {
    await db.sync_log.add({
      timestamp: new Date().toISOString(),
      level,
      message,
      payload: payload ? JSON.stringify(payload).slice(0, 2000) : undefined,
    });
  } catch {}
}

export async function cachedGet<T extends { id: number }>(
  path: string,
  store: 'products' | 'partners' | 'accounts' | 'currencies' | 'categories',
  id: number,
  tenantId?: number,
): Promise<CacheResult<T>> {
  const url = `${API_BASE}/${path.replace(/^\/+/, '')}`;
  try {
    const res = await fetch(url, { headers: getHeaders(tenantId), signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      const data = await res.json();
      const t = new Date().toISOString();
      await (db[store] as any).put({ id, tenant_id: tenantId, data: JSON.stringify(data), updated_at: t });
      await log('info', `cachedGet: network success for ${path}`, { id });
      return { data, fromCache: false, age_ms: 0 };
    }
  } catch {}
  const cached = await (db[store] as any).get(id);
  if (cached) {
    const age_ms = Date.now() - new Date(cached.updated_at).getTime();
    await log('warn', `cachedGet: serving from cache for ${path}`, { id, age_ms });
    return { data: JSON.parse(cached.data), fromCache: true, age_ms };
  }
  throw new Error(`البيانات غير متوفرة حالياً (${path})`);
}

export async function cachedGetList<T extends { id: number }>(
  path: string,
  store: 'products' | 'partners' | 'accounts' | 'currencies' | 'categories',
  tenantId?: number,
): Promise<CacheResult<T[]>> {
  const q = tenantId ? `?tenant_id=${tenantId}` : '';
  const url = `${API_BASE}/${path.replace(/^\/+/, '')}${q}`;
  try {
    const res = await fetch(url, { headers: getHeaders(tenantId), signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      const raw = await res.json();
      const items: T[] = Array.isArray(raw) ? raw : raw.results ?? [];
      const t = new Date().toISOString();
      for (const item of items) {
        const key = (item as any).id ?? (item as any).CurrencyID ?? (item as any).Code;
        if (key != null) {
          await (db[store] as any).put({ id: key, tenant_id: tenantId, data: JSON.stringify(item), updated_at: t });
        }
      }
      await log('info', `cachedGetList: network success for ${path}`, { count: items.length });
      return { data: items, fromCache: false, age_ms: 0 };
    }
  } catch {}
  const cached = await (db[store] as any).toArray();
  if (cached.length > 0) {
    const items: T[] = cached.map((c: any) => JSON.parse(c.data));
    const maxAge = Math.max(...cached.map((c: any) => Date.now() - new Date(c.updated_at).getTime()));
    await log('warn', `cachedGetList: serving from cache for ${path}`, { count: items.length, age_ms: maxAge });
    return { data: items, fromCache: true, age_ms: maxAge };
  }
  return { data: [], fromCache: true, age_ms: 0 };
}

export async function enqueueMutation(
  endpoint: string,
  method: 'POST' | 'PATCH' | 'DELETE',
  body: Record<string, unknown>,
  tenantId?: number,
): Promise<number> {
  const entry = {
    status: 'pending' as const,
    created_at: new Date().toISOString(),
    endpoint,
    method,
    body: JSON.stringify(body),
    tenant_id: tenantId,
    temp_id: `temp-${crypto.randomUUID()}`,
  };
  const id = await db.mutation_queue.add(entry);
  await log('info', `enqueueMutation: queued ${method} ${endpoint}`, { temp_id: entry.temp_id });
  if ('serviceWorker' in navigator && 'sync' in navigator.serviceWorker) {
    navigator.serviceWorker.ready.then((reg) => {
      (reg as any).sync?.register('ktra-mutations').catch(() => {});
    });
  }
  return id;
}

// Pub/sub for sync conflicts. UI registers a listener; when a 409 lands here,
// the listener gets a snapshot of (local, server, endpoint) and is expected to
// open `SyncConflictModal` and resolve via the returned promise.
export type ConflictPayload = {
  mutationId: number;
  endpoint: string;
  localBody: string;
  serverBody: string;
};
export type ConflictResolution = 'overwrite' | 'take_server' | 'manual_merge';
type ConflictListener = (p: ConflictPayload) => Promise<ConflictResolution>;
let conflictListener: ConflictListener | null = null;
export function registerConflictListener(fn: ConflictListener | null) { conflictListener = fn; }

export async function processMutationQueue(): Promise<void> {
  const pending = await db.mutation_queue.where('status').equals('pending').sortBy('created_at');
  for (const entry of pending) {
    const url = `${API_BASE}/${entry.endpoint.replace(/^\/+/, '')}`;
    await db.mutation_queue.update(entry.id!, { status: 'syncing' });
    try {
      const res = await fetch(url, {
        method: entry.method,
        headers: { 'Content-Type': 'application/json', ...getHeaders(entry.tenant_id) },
        body: entry.body,
      });
      if (res.ok) {
        const result = await res.json().catch(() => ({}));
        await db.mutation_queue.update(entry.id!, { status: 'synced' });
        if (entry.temp_id && result.id != null) {
          await db.id_mappings.put({
            temp_id: entry.temp_id,
            real_id: result.id,
            model: entry.endpoint.split('/')[0] || 'unknown',
            synced_at: new Date().toISOString(),
          });
          // P4-4: notify other tabs about the temp→real id mapping so any
          // open editor referencing the draft can swap its in-memory id.
          try {
            new BroadcastChannel('ktra-sync').postMessage({
              type: 'MUTATION_UPDATED',
              temp_id: entry.temp_id,
              real_id: result.id,
            });
          } catch { /* BroadcastChannel unavailable in some contexts */ }
        }
        await log('info', `processMutationQueue: synced ${entry.method} ${entry.endpoint}`, { id: entry.id });
      } else if (res.status === 409 && conflictListener) {
        // P3-4: hand the conflict to the UI for resolution. Default if no
        // listener is registered: mark as failed so the user can inspect it
        // in the pending-mutations panel.
        const serverBody = await res.text().catch(() => '');
        try {
          const resolution = await conflictListener({
            mutationId: entry.id!,
            endpoint: entry.endpoint,
            localBody: entry.body,
            serverBody,
          });
          if (resolution === 'overwrite') {
            // Re-issue with force flag; server contract may vary — leaves the
            // entry pending for the next sync round.
            await db.mutation_queue.update(entry.id!, { status: 'pending', error: 'pending overwrite' });
          } else if (resolution === 'take_server') {
            await db.mutation_queue.update(entry.id!, { status: 'synced', error: 'server-wins' });
          } else {
            // Manual merge: the UI is expected to load both bodies into an
            // editor and post the merged result; we just park as failed.
            await db.mutation_queue.update(entry.id!, { status: 'failed', error: 'awaiting manual merge' });
          }
        } catch {
          await db.mutation_queue.update(entry.id!, { status: 'failed', error: 'conflict resolution aborted' });
        }
        await log('warn', `processMutationQueue: 409 conflict for ${entry.endpoint}`, { id: entry.id });
      } else if (res.status >= 400 && res.status < 500) {
        const errBody = await res.text().catch(() => '');
        await db.mutation_queue.update(entry.id!, { status: 'failed', error: errBody.slice(0, 500) });
        await log('error', `processMutationQueue: client error ${res.status}`, { id: entry.id, error: errBody.slice(0, 200) });
      }
    } catch (e) {
      await log('error', `processMutationQueue: fetch failed`, { id: entry.id, error: String(e).slice(0, 200) });
      await db.mutation_queue.update(entry.id!, { status: 'pending' });
    }
  }
}
