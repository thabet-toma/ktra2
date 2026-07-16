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
// صيانة 2026-07: أُزيلت MASTER_DATA_CACHE/API_CACHE — كانتا كوداً ميتاً (انظر
// حارس same-origin أدناه)، وإزالتهما من هذه المجموعة تجعل activate يمسح أي
// نسخة قديمة منهما عالقة في متصفحات المستخدمين.
const CURRENT_CACHES = new Set([STATIC_CACHE]);

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
  // لا تتدخّل في طلبات أصل آخر — اترك المتصفح يديرها مباشرة كي لا يُقدَّم رد قديم
  // من الكاش بدل الخادم. ملاحظة مهمة: في الإنتاج الـ API على نطاق فرعي مختلف
  // (api.smart.ktragroup.com مقابل smart.ktragroup.com) وفي التطوير على بورت آخر
  // (:8000) — أي أن **كل** نداءات /api/ عابرة للأصل وتتجاوز هذا الـ SW بالكامل.
  // لذلك حُذف أي منطق كاش لمسارات /api/ من هذا الملف (كان كوداً ميتاً لا يُنفَّذ).
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

  event.respondWith(networkFirst(event.request, STATIC_CACHE, 8));
});

async function cacheFirst(request: Request, cacheName: string): Promise<Response> {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    // لا تحفظ 4xx/5xx كأنها أصل صالح للأوفلاين.
    if (response.ok) {
      const cache = await caches.open(cacheName);
      await cache.put(request, response.clone());
    }
    return response;
  } catch {
    const fallback = await caches.match('/offline.html');
    if (fallback) return fallback;
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request: Request, cacheName: string, timeoutSeconds: number): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutSeconds * 1000);
  try {
    // Promise.race القديمة كانت تسقط للكاش بعد 8 ثوانٍ لكن تترك fetch الحقيقي
    // يعمل في الخلفية. AbortController يحدّ العملية نفسها ويحرر الاتصال.
    const response = await fetch(request, { signal: controller.signal });
    if (response.ok) {
      const cache = await caches.open(cacheName);
      await cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    const fallback = await caches.match('/offline.html');
    if (fallback) return fallback;
    return new Response('Offline', { status: 503 });
  } finally {
    clearTimeout(timeoutId);
  }
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
