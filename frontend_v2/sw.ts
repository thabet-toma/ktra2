/// <reference lib="webworker" />
/* eslint-disable no-restricted-globals */

const CACHE_VERSION = 1;
const STATIC_CACHE = `ktra-static-v${CACHE_VERSION}`;
const MASTER_DATA_CACHE = 'ktra-master-data';
const API_CACHE = 'ktra-api';

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<{url: string; revision: string | null}> };

const manifestEntries = self.__WB_MANIFEST;

self.addEventListener('install', (event) => {
  if (manifestEntries) {
    event.waitUntil(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.addAll(manifestEntries.map((e) => e.url))
      )
    );
  }
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== MASTER_DATA_CACHE && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;

  if (url.pathname.match(/\.(js|css|woff2)$/)) {
    event.respondWith(cacheFirst(event.request, STATIC_CACHE));
    return;
  }

  if (url.pathname.match(/\/api\/(items|partners|accounts|currencies|categories)\/?(\?.*)?$/)) {
    event.respondWith(staleWhileRevalidate(event.request, MASTER_DATA_CACHE, 24 * 3600));
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request, API_CACHE, 3));
    return;
  }

  event.respondWith(networkFirst(event.request, STATIC_CACHE, 3));
});

async function cacheFirst(request: Request, cacheName: string): Promise<Response> {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
    return response;
  } catch {
    const fallback = await caches.match('/offline.html');
    if (fallback) return fallback;
    return new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidate(request: Request, cacheName: string, maxAgeSeconds: number): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  if (cached) {
    const date = cached.headers.get('date');
    const age = date ? (Date.now() - new Date(date).getTime()) / 1000 : Infinity;
    if (age < maxAgeSeconds) {
      fetchAndCache(request, cache);
      return cached;
    }
  }

  try {
    const response = await fetch(request);
    cache.put(request, response.clone());
    return response;
  } catch {
    if (cached) return cached;
    const fallback = await caches.match('/offline.html');
    if (fallback) return fallback;
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request: Request, cacheName: string, timeoutSeconds: number): Promise<Response> {
  try {
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('timeout')), timeoutSeconds * 1000)
    );
    const response = await Promise.race([fetch(request), timeout]);
    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    const fallback = await caches.match('/offline.html');
    if (fallback) return fallback;
    return new Response('Offline', { status: 503 });
  }
}

async function fetchAndCache(request: Request, cache: Cache): Promise<void> {
  try {
    const response = await fetch(request);
    cache.put(request, response.clone());
  } catch {}
}

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
