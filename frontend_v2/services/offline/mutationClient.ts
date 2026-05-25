import { enqueueMutation } from './cachedApi';
import db from './db';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

function getHeaders(tenantId?: number): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('token');
  if (token) h['Authorization'] = `Token ${token}`;
  if (tenantId) h['X-Tenant-Id'] = String(tenantId);
  return h;
}

export async function offlinePost<T = any>(
  endpoint: string,
  body: Record<string, unknown>,
  tenantId?: number,
): Promise<{ data?: T; tempId: string; isPending: boolean }> {
  const tempId = `temp-${crypto.randomUUID()}`;

  if (!navigator.onLine) {
    await enqueueMutation(endpoint, 'POST', body, tenantId);
    return { tempId, isPending: true };
  }

  try {
    const res = await fetch(`${API_BASE}/${endpoint.replace(/^\/+/, '')}`, {
      method: 'POST',
      headers: getHeaders(tenantId),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(errText || `HTTP ${res.status}`);
    }
    const data = await res.json();
    return { data: data as T, tempId, isPending: false };
  } catch {
    await enqueueMutation(endpoint, 'POST', body, tenantId);
    return { tempId, isPending: true };
  }
}

export async function offlinePatch<T = any>(
  endpoint: string,
  body: Record<string, unknown>,
  tenantId?: number,
): Promise<{ data?: T; isPending: boolean }> {
  if (!navigator.onLine) {
    await enqueueMutation(endpoint, 'PATCH', body, tenantId);
    return { isPending: true };
  }

  try {
    const res = await fetch(`${API_BASE}/${endpoint.replace(/^\/+/, '')}`, {
      method: 'PATCH',
      headers: getHeaders(tenantId),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(errText || `HTTP ${res.status}`);
    }
    const data = await res.json();
    return { data: data as T, isPending: false };
  } catch {
    await enqueueMutation(endpoint, 'PATCH', body, tenantId);
    return { isPending: true };
  }
}

export async function offlineDelete(
  endpoint: string,
  tenantId?: number,
): Promise<{ isPending: boolean }> {
  if (!navigator.onLine) {
    await enqueueMutation(endpoint, 'DELETE', {}, tenantId);
    return { isPending: true };
  }

  try {
    const res = await fetch(`${API_BASE}/${endpoint.replace(/^\/+/, '')}`, {
      method: 'DELETE',
      headers: getHeaders(tenantId),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(errText || `HTTP ${res.status}`);
    }
    return { isPending: false };
  } catch {
    await enqueueMutation(endpoint, 'DELETE', {}, tenantId);
    return { isPending: true };
  }
}

export async function getDrafts<T extends { id?: string; is_pending?: boolean }>(
  store: string,
): Promise<T[]> {
  const items = await db.mutation_queue
    .where('endpoint')
    .startsWith(store)
    .filter((m) => m.status !== 'synced')
    .toArray();
  return items.map((m) => {
    const body = JSON.parse(m.body);
    return { ...body, id: m.temp_id, is_pending: true } as T;
  });
}
