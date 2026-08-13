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
// صيانة 2026-07: أُزيلت MASTER_DATA_CACHE/API_CACHE — لا كاش لردود الـ API (انظر
// حارس المسار في معالج fetch)، وإزالتهما من هذه المجموعة تجعل activate يمسح أي
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
    ).then(purgeCachedApiResponses)
  );
  self.clients.claim();
});

/** يمسح ردود `/api/` التي تسرّبت إلى الكاش قبل استثناء المسار في معالج fetch.
 *
 * الاستثناء يمنع تخزيناً جديداً ولا يلمس ما تراكم على أجهزة المستخدمين. ولا يكفي
 * أن اسم الكاش مشتقّ من بصمة البناء: تعديل `sw.ts` وحده لا يغيّر بصمة الأصول
 * المبنية ⇒ نفس اسم الكاش ⇒ يبقى المسرَّب. فالمسح صريح ومستقلّ عن البصمة.
 */
async function purgeCachedApiResponses(): Promise<void> {
  const cache = await caches.open(STATIC_CACHE);
  const requests = await cache.keys();
  await Promise.all(
    requests
      .filter((request) => new URL(request.url).pathname.startsWith('/api/'))
      .map((request) => cache.delete(request))
  );
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;

  // ── لا كاش لردود الـ API، أبداً ─────────────────────────────────────────────
  // الحارس على **المسار** لا على الأصل، عمداً. الـ API اليوم على **نفس أصل**
  // الصفحة (`ktra-pro.tech/api/`) بعد الانتقال إلى nginx واحد؛ الحارس السابق كان
  // يعتمد على كونه نطاقاً فرعياً منفصلاً، فسقطت الحماية بلا إشارة لحظة النشر —
  // وهي حماية عزلٍ لا تحسين: مفتاح `Cache API` هو الرابط وحده، والشركة تأتي من
  // التوكن لا من المسار، أي أن `/api/products/` للشركة أ هو حرفياً مفتاح الشركة ب.
  // فأي سقوط للكاش (انقطاع أو تجاوز مهلة الثماني ثوانٍ) كان يعرض بيانات شركة على
  // مستخدم شركة أخرى. حارس المسار لا يتأثر بانتقال استضافة ولا بتغيير دومين.
  if (url.pathname.startsWith('/api/')) return;

  // لا تتدخّل في طلبات أصل آخر — اترك المتصفح يديرها مباشرة كي لا يُقدَّم رد قديم
  // من الكاش بدل الخادم (يغطّي أيضاً الـ API على بورت آخر في التطوير: ‎:8000).
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
