/** عامل الخدمة لا يخزّن ردود `/api/` — حارس عزلٍ لا اختبار تحسين.
 *
 * **لماذا يوجد هذا الملف:** الحارس في `sw.ts` كان مبنياً على أن الـ API على نطاق
 * فرعي منفصل (`url.origin !== self.location.origin`). الانتقال إلى استضافة تخدم
 * الواجهة والـ API من **أصل واحد** أسقط ذلك الافتراض، فصار `networkFirst` يكتب
 * كل رد API ناجح في كاش مشترك مفتاحه **الرابط وحده** — والشركة في هذه المنصة
 * تأتي من التوكن لا من المسار، أي أن `/api/products/` للشركة أ هو حرفياً مفتاح
 * الشركة ب. سقوطٌ واحد للكاش (انقطاع أو تجاوز مهلة 8 ثوانٍ) يعرض بيانات شركة على
 * مستخدم شركة أخرى.
 *
 * والمجموعة كانت خضراء طوال ذلك: **لا اختبار كان يشغّل عامل الخدمة مقابل أصل
 * الـ API.** هذا الملف هو ذلك الاختبار. يستورد `sw.ts` نفسه — لا نسخة من منطقه —
 * فلا يمكن أن يخضرّ بينما الملف المُسلَّم مكسور.
 */
import assert from "node:assert/strict";
import test from "node:test";

const ORIGIN = "https://ktra-pro.tech";

type Handler = (event: unknown) => void;

/** كاش وهميّ يسجّل كل كتابة — `put` هي الفعل الذي نمنعه. */
class FakeCache {
  entries = new Map<string, Response>();
  puts: string[] = [];
  deletes: string[] = [];

  async put(request: Request, response: Response) {
    this.puts.push(request.url);
    this.entries.set(request.url, response);
  }
  async match(request: Request | string) {
    const url = typeof request === "string" ? new URL(request, ORIGIN).href : request.url;
    return this.entries.get(url);
  }
  async keys() {
    return [...this.entries.keys()].map((url) => new Request(url));
  }
  async delete(request: Request) {
    this.deletes.push(request.url);
    return this.entries.delete(request.url);
  }
  async addAll(_urls: string[]) {}
}

class FakeCacheStorage {
  caches = new Map<string, FakeCache>();
  async open(name: string) {
    let cache = this.caches.get(name);
    if (!cache) {
      cache = new FakeCache();
      this.caches.set(name, cache);
    }
    return cache;
  }
  async keys() {
    return [...this.caches.keys()];
  }
  async delete(name: string) {
    return this.caches.delete(name);
  }
  async match(request: Request | string) {
    for (const cache of this.caches.values()) {
      const hit = await cache.match(request);
      if (hit) return hit;
    }
    return undefined;
  }
}

const handlers = new Map<string, Handler>();
const cacheStorage = new FakeCacheStorage();

// عامل الخدمة يعمل في سياق ServiceWorkerGlobalScope؛ نركّب أقلّ ما يحتاجه منه
// **قبل** استيراده، فهو يسجّل مستمعيه لحظة التحميل.
const globalScope = globalThis as Record<string, unknown>;
globalScope.self = {
  __WB_MANIFEST: [{ url: "/index.html", revision: "abc" }],
  location: new URL(ORIGIN),
  addEventListener: (type: string, handler: Handler) => handlers.set(type, handler),
  skipWaiting: () => {},
  clients: { claim: async () => {}, matchAll: async () => [] },
};
globalScope.caches = cacheStorage;

await import("../sw.ts");

const fetchHandler = handlers.get("fetch")!;
const activateHandler = handlers.get("activate")!;

/** يشغّل معالج fetch ويعيد الرد الذي تولّاه العامل — أو `null` إن لم يتدخّل. */
async function runFetch(url: string, networkFetch: typeof fetch) {
  const original = globalThis.fetch;
  globalThis.fetch = networkFetch;
  try {
    let responded: Promise<Response> | null = null;
    fetchHandler({
      request: new Request(url),
      respondWith: (value: Promise<Response>) => {
        responded = value;
      },
    });
    return responded ? await responded : null;
  } finally {
    globalThis.fetch = original;
  }
}

/** اسم كاش النسخة الحالية غير مصدَّر من `sw.ts` — نستخرجه من الكاش الذي يكتب
 * فيه العامل نفسه أصلاً عاماً، بدل تخمين الاسم أو تكرار اشتقاق البصمة هنا. */
async function currentCacheName(): Promise<string> {
  const probe = `${ORIGIN}/cache-name-probe.txt`;
  await runFetch(probe, async () => new Response("x", { status: 200 }));
  const entry = [...cacheStorage.caches.entries()].find(([, cache]) =>
    cache.puts.includes(probe),
  );
  assert.ok(entry, "العامل لم يخزّن أصلاً عاماً — تعذّر تحديد كاش النسخة الحالية");
  return entry[0];
}

test("لا يتدخّل عامل الخدمة في نداءات /api/ من نفس الأصل", async () => {
  const response = await runFetch(
    `${ORIGIN}/api/products/`,
    async () => new Response('{"results":[]}', { status: 200 }),
  );

  // عدم التدخّل = المتصفح يتولّى الطلب مباشرة، بلا مرور بالكاش إطلاقاً.
  assert.equal(response, null, "عامل الخدمة تولّى نداء API — يجب أن يمرّره للشبكة");
  const puts = [...cacheStorage.caches.values()].flatMap((cache) => cache.puts);
  assert.deepEqual(
    puts,
    [],
    "رد API دخل الكاش — مفتاحه الرابط وحده فيُقدَّم لمستخدم شركة أخرى",
  );
});

test("نداء /api/ لا يُقدَّم من الكاش عند فشل الشبكة", async () => {
  // ازرع رداً قديماً في الكاش كما لو تسرّب قبل الإصلاح، ثم أفشِل الشبكة.
  const cache = await cacheStorage.open("ktra-static-seed");
  await cache.put(
    new Request(`${ORIGIN}/api/products/`),
    new Response('{"results":["بيانات شركة سابقة"]}', { status: 200 }),
  );

  const response = await runFetch(`${ORIGIN}/api/products/`, async () => {
    throw new Error("network down");
  });

  assert.equal(
    response,
    null,
    "عامل الخدمة قدّم رداً للـ API عند فشل الشبكة — مصدره الكاش المشترك",
  );
});

test("الأصول الثابتة ما زالت تُخزَّن — الاستثناء على /api/ وحده", async () => {
  const response = await runFetch(
    `${ORIGIN}/offline.html`,
    async () => new Response("<html></html>", { status: 200 }),
  );

  assert.notEqual(response, null, "عامل الخدمة توقّف عن تولّي الأصول العامة");
  const puts = [...cacheStorage.caches.values()].flatMap((c) => c.puts);
  assert.ok(
    puts.some((url) => url.endsWith("/offline.html")),
    "أصل عام لم يُخزَّن — الاستثناء أوسع من المقصود",
  );
});

test("activate يمسح ردود /api/ المتراكمة ويبقي الأصول العامة", async () => {
  const stale = await cacheStorage.open("ktra-static-stale");
  await stale.put(new Request(`${ORIGIN}/api/invoices/`), new Response("{}"));
  await stale.put(new Request(`${ORIGIN}/logo.png`), new Response("png"));

  // نزرع في كاش **النسخة الحالية** أيضاً: هو الوحيد الذي ينجو من مسح النسخ
  // القديمة، فنقيس المسح الصريح لا الحذف بتغيّر البصمة.
  const current = await cacheStorage.open(await currentCacheName());
  await current.put(new Request(`${ORIGIN}/api/invoices/`), new Response("{}"));
  await current.put(new Request(`${ORIGIN}/logo.png`), new Response("png"));

  let pending: Promise<unknown> | null = null;
  activateHandler({ waitUntil: (value: Promise<unknown>) => (pending = value) });
  await pending;

  assert.equal(
    await current.match(new Request(`${ORIGIN}/api/invoices/`)),
    undefined,
    "رد API بقي في الكاش بعد التفعيل — المسرَّب يبقى على الأجهزة القائمة",
  );
  assert.notEqual(
    await current.match(new Request(`${ORIGIN}/logo.png`)),
    undefined,
    "المسح ابتلع أصلاً عاماً",
  );
  assert.equal(cacheStorage.caches.has("ktra-static-stale"), false);
});
