# TASK7 — Offline Mode + PWA + Employee Guidance UI

> **الدور:** Staff SWE / Tech Lead. خُطّة يُنفِّذها موديل أرخص بَعد موافقة المالك.
> **التاريخ:** 2026-05-25.
> **المرجع:** task6.md «الفئة 0» (UX density) + Google PWA criteria + W3C Service Worker spec + WCAG 2.1 (notifications and status messages) + nngroup.com offline-UX guidelines.
> **القاعدة الذهبية:** اقرأ هذا الملف كاملاً + قسم «إرشادات الموظف» قبل أيّ سَطر كود. لا تَختصر التَّحذيرات.

---

## مُقدِّمة: لماذا offline mode في ERP محاسبي مُختَلف

ERP الإدارة المالية ليس social-media app. الـoffline-first البَحت **خَطر**:

- ترحيل قيد بدون `select_for_update` على دفتر الترقيم = أرقام مستندات مُكرَّرة.
- خَصم مخزون من cache قديم = بيع كمية لا تَملكها (مَوقع overselling).
- توليد كشف ضريبة من فواتير محلية = تَجاوُز للـUniqueConstraint عند المُزامنة.

**القاعدة الحاكمة:**
> **القراءات** offline تَحت تَحذير. **الكتابات** offline في مُسوَّدات فقط. **الترحيل** يَتطلَّب اتّصالاً دائماً.

كل قَرار في هذه التاسك يُقاس بهذه القاعدة.

---

## نِطاق ما يَجوز / لا يَجوز offline

| العَمليّة | offline؟ | الإرشاد للموظف |
|----------|--------|---------------|
| قراءة قائمة منتجات/موردين/عملاء | ✅ مع تحذير «cache» | «البيانات من الذاكرة المحلية — قد تكون قديمة» |
| قراءة فاتورة مُرحَّلة | ✅ آمن | (immutable بعد الترحيل) |
| قراءة كمية مخزون / رصيد عميل | ⚠️ تحذير قوي | «هذا رصيد cache. تحقق فعلياً قبل البيع / السحب» |
| إنشاء مُسوَّدة فاتورة/شحنة جديدة | ✅ مع pending badge | «المسوَّدة محفوظة محلياً. لم تُرحَّل بعد» |
| تَعديل مُسوَّدة قائمة | ⚠️ مع conflict warning | «قد يكون شخص آخر عدَّلها — ستُعرَض النسختان عند المزامنة» |
| ترحيل قيد / فاتورة | ❌ مَحظور | «الترحيل يَتطلَّب اتّصالاً. حاول مرّة أخرى عند توفّر الإنترنت» |
| توليد كشف ضريبة | ❌ مَحظور | نفس الشيء |
| تَحويل workflow status (شحنة → جمارك) | ❌ مَحظور | نفس الشيء |
| ترحيل voucher مالي | ❌ مَحظور | نفس الشيء |
| Year-end close | ❌ مَحظور | نفس الشيء |

---

## Pre-Planning Protocols (الـ5 إلزامية — نَفس نَمَط task6.md)

### 1. الوعي الزمني
- التاريخ 2026-05-25. **dependencies جديدة مسموحة** هنا (`vite-plugin-pwa`، `dexie`، `workbox-window`) — هي الـtoolkit القياسي لـPWA الحديث.

### 2. التَّدفُّق المنطقي
- لا ميزات أعمال جديدة. تَحويل سلوك القراءة + إضافة طبقة sync.

### 3. المعمارية
- Service worker مُنفصل (`frontend_v2/sw.ts`).
- Dexie schema في `frontend_v2/services/offline/db.ts`.
- API wrapper موحَّد (`frontend_v2/services/offline/cachedApi.ts`).
- UI primitives في `frontend_v2/components/offline/`.

### 4. التَّتبُّع
- كل offline action تُلَوَّن (info / warn / error) ولا تُسجَّل في console — تَذهب لـIndexedDB log table لـsync.

### 5. الذاكرة الخارجية
- PROJECT_MAP يَتحدَّث بعد كل phase.

---

## Milestones — 5 Phases

> **Total:** 5 phases · ~30 task · ~10-15 يوم عَمل · 0 migration backend (frontend-only).

---

## Phase 1 — PWA Foundation (2-3 أيام)

> **الهدف:** الموقع يُصبح «installable» PWA حقيقي. Service worker مُسجَّل. App shell مَكاش.

### 1-1 — Manifest كامل
- [ ] **1-1-a:** أَيقونات: 192/384/512 + maskable في `frontend_v2/public/`.
- [ ] **1-1-b:** `site.webmanifest` يَحوي:
  - `screenshots[]` (3 صور: dashboard، فاتورة، تخليص)
  - `categories: ["business", "finance", "productivity"]`
  - `shortcuts[]`: 3 اختصارات (شحنة جديدة، فاتورة جديدة، قيد جديد)
  - `theme_color` + `background_color` متَّسقان مع Aseel
  - `display: "standalone"`, `orientation: "any"`
- [ ] **1-1-c:** تَأكَّد الـmanifest يَجتاز Lighthouse PWA audit.

### 1-2 — vite-plugin-pwa
- [ ] **1-2-a:** `npm install vite-plugin-pwa workbox-window` (dev).
- [ ] **1-2-b:** أَضِف الـplugin في `vite.config.ts`:
  ```ts
  VitePWA({
    registerType: 'prompt',  // النموذج 1-3-c يَتحكَّم بالـactivate
    workbox: {
      globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
      runtimeCaching: [
        // app-shell first
        { urlPattern: /\.(?:js|css|woff2)$/, handler: 'CacheFirst', options: { cacheName: 'static-assets', expiration: { maxAgeSeconds: 30*24*3600 } } },
        // master-data lookups — stale-while-revalidate, TTL 24h
        { urlPattern: /\/api\/(items|partners|accounts|currencies|categories)\/?(\?.*)?$/, handler: 'StaleWhileRevalidate', options: { cacheName: 'master-data', expiration: { maxAgeSeconds: 24*3600 } } },
        // listings — network-first بـtimeout قصير
        { urlPattern: /\/api\/.*\/(list|).*$/, handler: 'NetworkFirst', options: { cacheName: 'api-cache', networkTimeoutSeconds: 3 } },
      ],
    },
    devOptions: { enabled: false },  // لا SW في dev — يَكسر HMR
  })
  ```

### 1-3 — Update UX
- [ ] **1-3-a:** `frontend_v2/components/offline/UpdatePrompt.tsx` — يَستمع لـ`workbox-window`'s `waiting` event.
- [ ] **1-3-b:** Toast غير-مُلحّ: «تَوَفَّر تَحديث للنظام — أعِد التحميل لتفعيله».
- [ ] **1-3-c:** `Skip waiting` فقط بَعد click صَريح من المستخدم — لا تَفرض التَّحديث.

### 1-4 — Offline fallback page
- [ ] **1-4-a:** `frontend_v2/public/offline.html` — صفحة سَلسة بـAseel branding تَشرح:
  - أنت بدون اتّصال
  - يُمكنك تَصفُّح آخر بيانات شاهَدتها
  - الأعمال المُحفوظة محلياً ستُرسَل عند العَودة

### Verifiable Phase 1
- Lighthouse PWA score ≥ 90.
- Chrome DevTools → Application → Service Workers يَعرض SW مُسجَّل.
- إيقاف الشبكة في DevTools → إعادة تَحميل الصفحة → الـapp shell يَظهر.

---

## Phase 2 — Read-Side Cache + Online/Offline UI (3-4 أيام)

> **الهدف:** master data offline-readable. الموظف يَرى دائماً حالة الاتّصال وعُمر البيانات.

### 2-1 — IndexedDB Schema (Dexie)
- [ ] **2-1-a:** `npm install dexie`.
- [ ] **2-1-b:** `frontend_v2/services/offline/db.ts`:
  ```ts
  export const db = new Dexie('ktra_offline');
  db.version(1).stores({
    products: 'id, tenant_id, sku, name_ar, [tenant_id+sku]',
    partners: 'id, tenant_id, name, partner_type, [tenant_id+partner_type]',
    accounts: 'id, tenant_id, code, account_type',
    currencies: 'id, Code',
    categories: 'id, tenant_id, name',
    cache_meta: 'key, updated_at',  // آخر sync per store
    mutation_queue: '++id, status, created_at, endpoint, method',
    sync_log: '++id, timestamp, level, message, payload',
  });
  ```

### 2-2 — Cached API wrapper
- [ ] **2-2-a:** `frontend_v2/services/offline/cachedApi.ts`:
  - `cachedGet(endpoint, opts)` — يُحاول الشبكة، يَسقط على Dexie.
  - `cachedGetList(endpoint, store)` — stale-while-revalidate.
  - يُرجع `{ data, fromCache: boolean, age_ms: number }`.
- [ ] **2-2-b:** Refactor `productsApi`, `partnersApi`, `accountsApi` لتَستهلك الـwrapper.

### 2-3 — Network status hook
- [ ] **2-3-a:** `frontend_v2/hooks/useOnlineStatus.ts`:
  - يَستمع لـ`window.online` / `window.offline` events.
  - يُمرِّر تَأكيد heartbeat كل 30s (HEAD على `/api/health/`).
  - يُرجع `{ online: boolean, lastOnline: Date, latencyMs: number }`.

### 2-4 — Global offline banner
- [ ] **2-4-a:** `frontend_v2/components/offline/OfflineBanner.tsx`:
  - Sticky bar أعلى الصفحة (لا modal).
  - لون: أصفر لـoffline-cache، أحمر لـoffline-no-cache.
  - نَصّ: «🔴 بدون اتّصال — تَعرض آخر بيانات محفوظة منذ <time>. الترحيل والمزامنة معطَّلة.»
  - زر «أعِد المحاولة» يُحاول heartbeat فوراً.
- [ ] **2-4-b:** يَظهر في `App.tsx` فوق الـHeader، تحت الـtitle bar.

### 2-5 — Per-record freshness badges
- [ ] **2-5-a:** `frontend_v2/components/offline/StalenessBadge.tsx`:
  - Pill صغير: «🕒 منذ ساعتين» / «🕒 منذ 3 أيام».
  - أحمر إن > 24h، أصفر 2-24h، أخضر < 2h.
- [ ] **2-5-b:** أَضِفه في:
  - قوائم: `ItemsManagement`, `SupplierManagement`, `CustomersManagement`.
  - دوكيومنت shells: top-right للـheader في فواتير/شحنات/تخليص.

### Verifiable Phase 2
- إيقاف الشبكة → فَتح قائمة المنتجات → يَعرض البيانات من cache + banner أصفر + staleness badges.
- فَتح فاتورة قديمة offline → تُعرَض بكامل تَفاصيلها.
- زر «أعِد المحاولة» في الـbanner يُخفيها عند عَودة الشبكة.

---

## Phase 3 — Employee Guidance UI (إرشادات الموظف) — 3-4 أيام

> **هذه الـphase هي قَلب التاسك** — حتى لو كل البنية التحتيّة صحيحة، الموظف يَحتاج إرشادات صَريحة لِفهم ما يَفعله وما لا يَفعله offline.
>
> **المرجع:** WCAG 2.1 SC 4.1.3 (Status Messages)، nngroup.com/articles/offline-mode، Material Design 3 «Status indicators»، Apple HIG «Connection States».

### 3-1 — Pre-action warnings (تَحذيرات ما قبل الإجراء)

- [ ] **3-1-a:** `frontend_v2/components/offline/OfflineGuard.tsx`:
  - Component يَلفّ زر action مَحظور offline.
  - Online → يُمرِّر النَّقر طبيعياً.
  - Offline → يَعرض tooltip أحمر دائم «الترحيل يَتطلَّب اتّصالاً» ويُعطِّل الزر.
  - props: `{ action, children, allowedOffline?: boolean, warningMessage?: string }`.
- [ ] **3-1-b:** لُفّ كل أزرار الترحيل بـ`<OfflineGuard>`:
  - SalesInvoice → «ترحيل الفاتورة»
  - LogisticsClearance → «ترحيل التخليص»
  - JournalEntry → «ترحيل القيد»
  - VatStatement → «توليد كشف ضريبة»
  - YearEndClose → «تَنفيذ الإغلاق السنوي»
  - Cheque transitions → «تَحويل حالة الشيك»

### 3-2 — Stock/balance confirmation prompts (تأكيد قبل عملية حسّاسة)

- [ ] **3-2-a:** `frontend_v2/components/offline/StaleDataConfirm.tsx`:
  - Modal يَظهر **قبل** إضافة سَطر فاتورة بيع أو إصدار إذن صَرف، إن البيانات > 1h قديمة:
    > «⚠️ تَحذير**
    > كمية المنتج «<اسم>» المعروضة (<qty>) من cache آخر تَحديث: <relative time>.
    > **قد لا تَكون الكمية الفعلية الآن مُتاحة.** تَأكَّد فعلياً (أو تَأخَّر حتى يَعود الاتّصال) قبل المُتابعة.»
  - أزرار: «أَفهم وأَستمرّ» (موصوف clearly) / «إلغاء».
- [ ] **3-2-b:** Hook الـmodal في:
  - `SalesInvoiceEditor` عند إضافة سَطر منتج (إن `stock_on_post=true`).
  - `DealForm` عند تَوزيع كمية على صفقة.
  - `PurchaseInvoice` (للـreturns) عند سَحب كمية.

### 3-3 — Pending mutations panel

- [ ] **3-3-a:** `frontend_v2/components/offline/PendingMutationsPanel.tsx`:
  - أيقونة في الـHeader (next to user menu) بـbadge counter للـpending mutations.
  - النَّقر → AseelSidePanel يَعرض الـqueue:
    - لكل mutation: ID مُؤقَّت، الـendpoint، الـmethod، حجم الـpayload، الـtimestamp، الحالة (pending / syncing / failed / synced).
    - أزرار: «إعادة المحاولة» / «حَذف من الـqueue» / «عرض الـpayload».
- [ ] **3-3-b:** يَظهر دائماً (online + offline) — حتى online بَعد cache write تَكون هناك pending sync.

### 3-4 — Sync conflict resolution

- [ ] **3-4-a:** عند المزامنة، إن server يَرجع 409 (conflict):
  - افتح modal «نُسخة جديدة على الـserver»:
    - Side-by-side: «تَعديلك المحلي» | «الـserver الحالي».
    - أزرار: «احفظ نُسختي (overwrite)» / «خُذ نُسخة الـserver (discard)» / «دَمج يَدوي» (يَفتح editor مع merge markers).
- [ ] **3-4-b:** افتراضياً: لا overwrite تلقائي. المستخدم يَختار.

### 3-5 — Status messages (WCAG 4.1.3 — مَلزِم لـscreen readers)

- [ ] **3-5-a:** كل تَغيُّر حالة (online → offline، sync started، sync failed، mutation queued):
  - `<div role="status" aria-live="polite">` في الـDOM لِيَقرأه الـscreen reader.
  - Toast بَصري متَّسق مع Aseel.
- [ ] **3-5-b:** الـmessages العربية:
  - «أنت الآن بدون اتّصال — الأعمال ستُحفَظ محلياً»
  - «عَود الاتّصال — جارٍ مزامنة 3 عَمليّات معلَّقة»
  - «المزامنة فَشلت — راجع لوحة العَمليّات المعلَّقة»
  - «تَحذير: الكمية المعروضة قد لا تَكون مُحدَّثة»

### 3-6 — Help / onboarding tooltip

- [ ] **3-6-a:** أوّل مرّة يَتحوَّل المستخدم لـoffline:
  - Coach mark بـthird-party-free implementation (CSS + portal):
    > «أنت الآن بدون اتّصال. **ماذا يَعمل / لا يَعمل؟**
    > ✅ تَصفُّح القوائم والفواتير القديمة
    > ✅ إنشاء مُسوَّدات (تُرسَل عند العَودة)
    > ❌ ترحيل القيود/الفواتير
    > ❌ توليد التقارير الضريبية»
  - Checkbox «لا تَعرض هذا مرّة أخرى» يَحفظ في localStorage.

### Verifiable Phase 3
- إيقاف الشبكة → ضَغط «ترحيل فاتورة» → الزر مُعطَّل بـtooltip أحمر.
- إضافة سَطر فاتورة بَيع بـcache قديم → modal تَحذير قبل الإضافة.
- queue 3 mutations offline → الـPanel يَعرضها صَحيحاً.
- محاكاة 409 من الـserver → modal دَمج يَظهر.
- screen reader (NVDA) يَقرأ كل تَحوُّل حالة.

---

## Phase 4 — Draft-Mode Writes + Sync Queue (5-7 أيام)

> **الهدف:** الموظف يُنشئ مُسوَّدات offline، تُرسَل تلقائياً عند العَودة.

### 4-1 — Mutation queue
- [ ] **4-1-a:** Dexie `mutation_queue` table موجود من Phase 2.
- [ ] **4-1-b:** API client wrapper:
  - Online → POST/PATCH عادي.
  - Offline → enqueue `{endpoint, method, body, tenant_id, temp_id, created_at}` + retrieve a `pending` document بـ`is_pending: true`.
- [ ] **4-1-c:** كل draft document يَحصل على `temp-<uuid>` كـID. الـbackend يُعطيه id حقيقي عند المزامنة. الـUI يَستبدل الـmapping عبر `temp_id → real_id`.

### 4-2 — Background Sync API
- [ ] **4-2-a:** Register sync in SW عند enqueue:
  ```js
  navigator.serviceWorker.ready.then(reg => reg.sync.register('ktra-mutations'));
  ```
- [ ] **4-2-b:** Fallback for browsers without Sync API: `setInterval` polling في `useOnlineStatus`.
- [ ] **4-2-c:** Sync algorithm:
  - Iterate `mutation_queue` بـ`status=pending` بـtimestamp order.
  - Send بـ`X-Tenant-Id` المُسجَّل في الـmutation.
  - 2xx → mark `synced`، update `temp_id` mapping.
  - 4xx (validation) → mark `failed`، اعرض في الـPanel.
  - 5xx → leave as `pending`، retry بـexponential backoff.

### 4-3 — Drafts visible in lists
- [ ] **4-3-a:** قوائم الفواتير/الشحنات تَعرض الـdrafts المحلية مَع badge «● معلَّقة».
- [ ] **4-3-b:** فَتح draft → نفس الـeditor، لكن:
  - زر «حفظ» يُعدِّل الـqueue entry (لا يُرسِل الـserver فوراً).
  - زر «ترحيل» مُعطَّل (يَتطلَّب اتّصال + sync).

### 4-4 — Temp-ID mapping
- [ ] **4-4-a:** Dexie store `id_mappings: 'temp_id, real_id, model, synced_at'`.
- [ ] **4-4-b:** عند sync ناجح: store mapping + emit `BroadcastChannel` event لتَحديث الـtabs الأخرى.

### Verifiable Phase 4
- إيقاف الشبكة → إنشاء فاتورة بـ3 lines → حفظ draft → تَظهر في القائمة بـbadge.
- إعادة الشبكة → خلال 10s تُرسَل تلقائياً → الـbadge يَختفي، الـID يَتحدَّث.
- صنع conflict عَمداً (تَعديل نفس الفاتورة من tab آخر online) → modal دَمج.

---

## Phase 5 — Tests + Storage Quotas + Multi-Tab (3-5 أيام)

### 5-1 — Storage quota handling
- [ ] **5-1-a:** `navigator.storage.estimate()` تُستدعى كل ساعة:
  - usage > 80% → toast تَحذير + اقترح مَسح cache قديم.
  - usage > 95% → block writes جديدة + modal صارم.
- [ ] **5-1-b:** زر «امسح cache قديم» في settings → يَحذف entries أقدم من 7 أيام.

### 5-2 — Multi-tab coordination
- [ ] **5-2-a:** `BroadcastChannel('ktra-sync')` لمزامنة:
  - mutation queue updates عبر tabs.
  - تَحوُّل online/offline.
  - tenant switch (يَمسح cache الـtenant السابق).

### 5-3 — Cache versioning
- [ ] **5-3-a:** `CACHE_VERSION` constant في الـSW.
- [ ] **5-3-b:** على breaking change: `CACHE_VERSION++` → SW يَمسح الـcaches القديمة.

### 5-4 — Tests
- [ ] **5-4-a:** Playwright tests مع `context.setOffline(true)`:
  - Test 1: offline list browsing.
  - Test 2: offline draft creation + reconnect sync.
  - Test 3: offline blocked actions (post invoice).
  - Test 4: stale data warning before sensitive action.
  - Test 5: conflict resolution flow.
- [ ] **5-4-b:** Lighthouse audit في CI — يَفشل لو PWA score < 90.

### Verifiable Phase 5
- محاكاة quota 95% → الـapp تَرفض writes جديدة بـmodal صارم.
- 2 tabs مَفتوحَين → mutation في tab A تَنعكس في الـpanel في tab B.
- 5 Playwright tests تَنجح.

---

## Verification Matrix

| Phase | Verifiable Goals |
|------|------------------|
| 1 | Lighthouse PWA ≥ 90 · SW مُسجَّل · offline fallback page · update prompt |
| 2 | Master data offline-readable · banner + staleness badges · heartbeat working |
| 3 | OfflineGuard على 6+ posting buttons · stale-data confirm modal · pending panel · conflict UI · status messages |
| 4 | Drafts queueable offline · auto-sync on reconnect · temp-id → real-id mapping · conflict resolution |
| 5 | Storage quota warnings · multi-tab sync · cache versioning · 5 Playwright tests · CI Lighthouse gate |

---

## Execution Rules

1. **اقرأ هذا الملف كاملاً + قسم «إرشادات الموظف» (Phase 3) قبل أيّ سَطر.**
2. **Phase 3 ليس اختياري** — الـoffline بدون إرشادات أَخطر من بدون offline mode أصلاً.
3. **لا تَنفِّذ Phase 4 قبل Phase 3.** الـdraft mode بدون pending panel = الموظف لا يَرى ما هو معلَّق.
4. **commit-per-task** بـرسالة `task7 <phase>-<num>: <description>`.
5. **اعمل على branch `claude/task7`، لا في main.**
6. **بَعد كل phase توقَّف وانتظر مراجعة.**
7. **لا overwrite تلقائي عند conflict.** المستخدم يَختار دائماً.
8. **الـmessages العربية تَخضع لـreview لُغوي** قبل الإطلاق.
9. **اختبر مع screen reader (NVDA)** — WCAG 4.1.3 مَلزِم.
10. **لا تَستخدم `alert()`** — كل toasts تَمرّ عبر `aria-live="polite"`.
11. **لا dependencies غير الـ3 المذكورة** (`vite-plugin-pwa`, `dexie`, `workbox-window`). أي مكتبة أخرى → `[QUESTION]` في commit body.
12. **`tsc --noEmit`** يَبقى = 0 بعد كل phase.

---

## Status

> **Status:** `[ ]` Phases 1-5 pending owner approval · 2026-05-25
>
> **Total:** 5 phases · ~30 task · 0 backend migration · 3 dependencies جديدة (vite-plugin-pwa، dexie، workbox-window).
>
> **Estimated execution:** 60-90 ساعة موديل أرخص + 10 ساعة مراجعة.
>
> **القاعدة:** بَعد التاسك، الموظف بدون اتّصال يَستطيع:
> - تَصفُّح آخر بيانات شاهَدها (مع تَحذيرات staleness).
> - إنشاء مُسوَّدات (تَتزامن تلقائياً عند العَودة).
> - **لا يَستطيع** ترحيل أيّ شيء مالي.
> - يَرى بوضوح ما يَعمل وما لا يَعمل (Phase 3).
