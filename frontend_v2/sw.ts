/// <reference lib="webworker" />
/* eslint-disable no-restricted-globals */

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<{url: string; revision: string | null}> };

const manifestEntries = self.__WB_MANIFEST || [];

// نسخة الكاش مشتقّة من بصمة الأصول المبنية — تتغيّر مع كل بناء جديد، فيُمسح كاش
// الكود القديم تلقائياً عند التفعيل ولا يبقى JS قديم محبوساً في cacheFirst.
function _hash(str: string): string {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h) ^ str.charCodeAt(i);
  return (h >>> 0).toString(36);
}
const BUILD_VERSION = _hash(manifestEntries.map((e) => e.revision || e.url).join('|') || 'dev');
const STATIC_CACHE = `ktra-static-${BUILD_VERSION}`;
const MASTER_DATA_CACHE = 'ktra-master-data';
const API_CACHE = 'ktra-api';
const CURRENT_CACHES = new Set([STATIC_CACHE, MASTER_DATA_CACHE, API_CACHE]);

self.addEventListener('install', (event) => {
  if (manifestEntries.length) {
    event.waitUntil(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.addAll(manifestEntries.map((e) => e.url))
      )
    );
  }
  // فعّل النسخة الجديدة فوراً بدل انتظار إغلاق كل التبويبات.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        // امسح أي كاش لا ينتمي للنسخة الحالية (يشمل كاش الكود القديم بنسخته السابقة).
        keys.filter((k) => !CURRENT_CACHES.has(k)).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  // لا تتدخّل في طلبات أصل آخر (مثل API على :8000 أو CDN) — اترك المتصفح يديرها
  // مباشرة كي لا يُقدَّم رد قديم من الكاش بدل الخادم.
  if (url.origin !== self.location.origin) return;

  // التنقّل (طلب صفحة) → الشبكة أولاً ليصل index.html الأحدث بمراجع الـ chunks
  // الجديدة؛ السقوط للكاش عند انقطاع الشبكة فقط (دعم أوفلاين).
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request, STATIC_CACHE, 8));
    return;
  }

  // أصول مُجزّأة (hashed) — اسمها يتغيّر مع كل بناء، فالـ cacheFirst آمن ولا يُجمِّد كوداً قديماً.
  if (url.pathname.match(/\.(js|css|woff2)$/)) {
    event.respondWith(cacheFirst(event.request, STATIC_CACHE));
    return;
  }

  if (url.pathname.match(/\/api\/(items|partners|accounts|currencies|categories)\/?(\?.*)?$/)) {
    event.respondWith(staleWhileRevalidate(event.request, MASTER_DATA_CACHE, 24 * 3600));
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request, API_CACHE, 8));
    return;
  }

  event.respondWith(networkFirst(event.request, STATIC_CACHE, 8));
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

self.addEventListener('sync', (event) => {
  if (event.tag === 'ktra-mutations') {
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: 'PROCESS_MUTATIONS' });
        });
      })
    );
  }
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
