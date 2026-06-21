# PROJECT_MAP — K.T.R.A

## [AI_TOOLING]
- **Ruflo** (Multi-Agent Orchestrator): `.clone/ruflo/` — استخدمه دائماً للمهام المعقدة
  - تشغيل: `npx ruflo init` أو `node .clone/ruflo/bin/ruflo.js`
  - الدليل: `CLAUDE.md` (في جذر المشروع)
  - المصدر: https://github.com/ruvnet/ruflo

## [TECH_STACK]
- **Frontend:** React 19.2, TypeScript 5.8, Vite 6.2, Tailwind CSS 4.3, react-router-dom 7, date-fns 4
- **Backend:** Django 6.0.1 (latest stable 6.0.6, 2026-06-03; LTS 5.2.15), DRF 3.16, MySQL (prod), SQLite (test)
- **PWA/Offline:** vite-plugin-pwa 1.3, workbox-window 7.4, Dexie 4.4
- **Testing:** pytest-django (70 tests, SQLite via `core.test_settings`), Playwright (E2E, advisory in CI)
- **Logging (task8 M11):** `core/logger_middleware.py` request tracing + `client_logs` sink + console LOGGING config
- **Icons:** lucide-react · **Charts:** recharts
- **Version policy (2026-06):** stack is current; recommended optional patch: Django 6.0.1 → 6.0.6. No new deps planned for task9/task10.

## [SYSTEM_FLOW]
```
User → Browser → React SPA (App.tsx)
  ├─ Online ───→ REST API (Django) ──→ MySQL
  └─ Offline ──→ IndexedDB (Dexie) ──→ cachedApi wrapper
                    ↓
              mutation_queue → Background Sync (on reconnect)
```

## [ARCHITECTURE]
```
frontend_v2/
├── App.tsx                    # Root SPA routing (all views)
├── index.tsx                  # Entry point (BrowserRouter)
├── index.html                 # HTML shell + PWA manifest link
├── sw.ts                      # Service Worker (PWA)
├── vite.config.ts             # Vite + vite-plugin-pwa + Tailwind
├── public/
│   ├── site.webmanifest       # PWA manifest
│   ├── offline.html           # Offline fallback page
│   ├── android-chrome-512x512.png
│   ├── apple-touch-icon.png
│   ├── favicon-*.png / .ico
│   └── notification-sound.mp3
├── services/
│   ├── offline/
│   │   ├── db.ts              # Dexie IndexedDB schema
│   │   └── cachedApi.ts       # Stale-while-revalidate API wrapper
│   ├── restApi.ts             # Base HTTP client
│   ├── salesApi.ts            # Sales API
│   ├── clearanceApi.ts        # Clearance API
│   └── ...                    # Domain-specific APIs
├── hooks/
│   └── useOnlineStatus.ts     # Network heartbeat hook
├── components/
│   ├── offline/
│   │   ├── UpdatePrompt.tsx        # SW update toast
│   │   ├── OfflineBanner.tsx       # Global sticky banner
│   │   ├── StalenessBadge.tsx      # Per-record freshness pill
│   │   ├── OfflineGuard.tsx        # Post button wrapper
│   │   ├── StaleDataConfirm.tsx    # Pre-action cache warning modal
│   │   ├── PendingMutationsPanel.tsx
│   │   ├── SyncConflictModal.tsx
│   │   ├── StatusMessage.tsx       # WCAG 4.1.3 live region
│   │   └── OfflineCoachmark.tsx    # First-offline onboarding
│   ├── sales/                       # Sales domain
│   ├── procurement/                 # Procurement domain
│   ├── accounting/                  # Accounting domain
│   └── ...                          # Other domains
├── types.ts, types/           # TypeScript type definitions
├── contexts/                  # React contexts (Auth, Theme)
├── utils/                     # Utility functions
├── styles/                    # CSS (Tailwind entry)
└── constants/                 # App constants
```

## [AUDIT — task23, 2026-06-21] (واجهة «تكلفة المنتجات» + تنبيه أثر السعر + إصلاح متوسط التكلفة)

**السبب الجذري (مؤكَّد):** متوسط التكلفة المعروض في بطاقة الصنف كان = إجمالي قيمة
الشراء ÷ الكمية الحالية المتبقية (مثال حقيقي 3800÷13=292.31)، متجاهلاً المباع. مصدره
**انحراف WAC المتحرك مع المخزون السالب** (`allow_negative_stock_default=True`): بيع 27
قبل وصول الشراء سجّل COGS=0 وكمية ‑27، ثم شراء 40 جعل المعادلة `((‑27×0)+(40×95))÷13`
= 3800÷13. المطلوب من المالك: نموذج جديد يُعرض في واجهة مستقلة (لا النموذج الحالي).

- **النموذج الجديد (تكلفة المنتجات):** سعر وحدة كل فاتورة = تكلفة الفاتورة ÷ كميتها،
  ثم تكلفة المنتج = **متوسط أسعار وحدات الفواتير مرجّحاً بكمية كل فاتورة** =
  Σ(تكلفة الفواتير) ÷ Σ(كميات الشراء). المقام إجمالي المشترى (لا الحالية) ⇒ لا يتأثر
  بالبيع. تكلفة الفاتورة تأخذ landed cost حين توفّره.
  - `inventory/services.py::product_cost_breakdown` + endpoint
    `GET inventory/products/{id}/cost-breakdown/`.
- **الواجهة:** `frontend_v2/components/inventory/ProductCostPage.tsx` (view `product-cost`،
  مسار `/product-cost?product=ID`) — بحث/اختيار منتج، جدول فواتير الشراء (تكلفة/سعر وحدة)،
  تذييل بالمتوسط المرجّح. روابط دخول: الشريط الجانبي (مجموعة المخزون) + زر «تكلفة المنتجات»
  في بطاقة الصنف (تبويب جديد، المنتج محدد افتراضياً).
- **تنبيه أثر السعر (فوري):** في `InvoiceForm` عند كتابة سعر/كمية بند شراء، تنبيه
  «سيغيّر المتوسط من X إلى Y» + زر يفتح `/product-cost?product=ID`. يحسب المتوقّع من
  `cost-breakdown` (cache لكل منتج).
- **تصحيح البيانات القديمة:** أمر `recompute_product_cost [--apply] [--tenant N]` يعيد
  ضبط `Product.avg_cost` بالنموذج الجديد (يصحّح 292.31⇐95). dry-run افتراضياً.
- **التحقق:** **inventory 31/31** (+3 جديدة: متوسط مرجّح يتجاهل المباع، أولوية landed،
  endpoint) · tsc نظيف · بناء الإنتاج ناجح. (الشاشة خلف الدخول — لا تحقّق بصري.)
- **بقي (خارطة طريق):** ربط النموذج الجديد بترحيل COGS الحيّ (record_stock_movement ما
  يزال WAC المتحرك)؛ سياسة المخزون السالب (المالك اختار: اسمح + صحّح COGS لاحقاً).

## [AUDIT — task22 Phase 1, 2026-06-20] (المرافق العامة — G1 مُنسّق الأرقام + G2 تبويب جديد)

خطة جراحية متعددة المراحل (10 مراحل، تنفيذ مرحلة-بمرحلة بمراجعة المالك). المرجع
الأصلي مكتوب لـ RooFlow لكن المشروع لا يستخدم `memory-bank/` — مصدر الحقيقة هو هذا
الملف + ذاكرة `.claude`. **المرحلة 1 (المرافق العامة):**

- **[G1] مُنسّق أرقام موحّد** — `frontend_v2/utils/formatNumber.ts`:
  - `formatNumber(value, { maxDecimals?, group?, fallback? })` يحذف الأصفار العشرية
    غير الدالّة: `30490.00→"30490"` · `187.50→"187.5"` · `187.55→"187.55"`.
  - اختصاران: `formatMoney` (منازل 2 + فاصل آلاف) · `formatQuantity` (منازل 4).
  - تحقّق منطقي: 12/12 حالة (لا يوجد JS unit-runner في `frontend_v2` — تحقّق عبر Node).
- **[G2] فتح تبويب جديد** — `frontend_v2/utils/openInNewTab.ts`: مصدر واحد لـ
  `window.open(_blank, noopener)` للفواتير/كشوف الحساب/الطباعة.
- **[G3/G4]** موجودان أصلاً في `styles/index.css` (رموز كثافة `--spacing-*` مدمجة +
  أحجام خط صغيرة + Tailwind v4 responsive) — يُطبَّقان لكل شاشة في المرحلتين 2/5، لا
  أساس جديد مطلوب.
- **بدء التعميم:** `components/forms/shared/FinancialSummarySection.tsx` يمرّ الآن كل
  عرض عبر `formatMoney`/`formatNumber` (كان `toFixed(2)`/`toLocaleString(min:2)` ينتج
  `$30490.00`). بقية الـ23 ملفاً تُحوَّل ضمن مراحلها (تلمس فواتير/كشوف/تقارير لاحقاً).
- tsc نظيف (exit 0). لا انحدار وظيفي (عرض فقط).

### الباقي للتعميم (G1 rollout — يُنفَّذ ضمن المراحل اللاحقة)
SalesInvoiceEditor · PurchaseInvoiceAccountingPanel · DealForm · Sales/PurchaseReturnEditor ·
SalesCustomerPaymentsPage · CreditDebitNotesPage · SupplierPaymentsPage · AccountingJournalEntryPage ·
ClearanceImportModal · InvoicePrintView · InstallmentManager · ItemsTableSection · PriceOfferListUpdated ·
NISItemsTable · NISInvoiceTaxStrip · LocalPaymentsSection · ConversionDetailsSection · DealPrintView ·
dealsService · ProductCard (≈22 ملف يستخدم toFixed(2)/toLocaleString).

## [AUDIT — task22 Phase 9+10, 2026-06-20] (الآلة الحاسبة T-C1 + مسح الانحدار)

- **T-C1 (ذاكرة الحاسبة + UI ملوّن):** `AseelCalculatorPopover` — أُضيفت **ذاكرة العمليات
  السابقة** (تُحفظ في localStorage `aseel_calc_history`، تبقى بين الجلسات، حتى 25 عملية):
  زر سجلّ في الرأس يفتح لوحة قابلة للطيّ، نقرة على عملية تستعيد ناتجها، زر مسح الذاكرة.
  UI: عنوان متدرّج اللون + لوحة سجلّ ملوّنة (الأزرار كانت ملوّنة أصلاً: C أحمر/عمليات
  زرقاء/= أخضر). تحقّق: tsc نظيف.
- **المرحلة 10 (مسح الانحدار + المزامنة):** **الحزمة الخلفية الكاملة 229/229** (لا انحدار،
  +12 اختباراً جديداً) · **بناء الواجهة للإنتاج ناجح** (dist + PWA SW) · tsc نظيف ·
  مزامنة PROJECT_MAP وذاكرة `.claude` (ملف [[task22-surgical-refactor]]).

### الهجرات الجديدة (تُطبَّق عند النشر)
`inventory/0010` (مستندات المخزون) · `logistics/0046` (صندوق شراء افتراضي) ·
`sales/0019` (تنبيه تكرار الصنف).

### بقي لمراحل لاحقة (خارطة طريق task22)
- أعلام عرض الإعدادات المكتبية (آخر سعر/ربح/رصيد، اقتراح بالاسم/الكود/الباركود، عدد
  المنازل) — تُبنى مع سلوكها.
- شاشتا «إعدادات المخزون» و«البنوك» المستقلتان.
- خريطة قيد الشراء الكاملة + جرد على مستوى المستودع (المخزون حالياً على مستوى الشركة).
- تعميم G1 على بقية الملفات (~18) التي ما زالت تستخدم toFixed(2)/toLocaleString.

## [AUDIT — task22 Phase 8, 2026-06-20] (محرّك الإعدادات — T-S1..T-S4)

- **T-S1 (تدقيق الإعدادات الموجودة):** `SalesSettings` (محور غني: عميل/عملة افتراضيان +
  **خريطة حسابات افتراضية كاملة** صندوق/ذمم/إيراد منتج+خدمة/مخزون/ت.ب.م/ض.ق.م + أعلام
  سلوك: نوع الدفع، خصم المخزون، الرصيد السالب، شمول الضريبة، الترحيل التلقائي، معاينة
  القيد) عبر `sales/settings/current/`. `PurchaseSettings` (استراتيجية تسعير +
  default_cash_account من المرحلة 4). `useTenantSettings` + `SalesSettingsPage`/
  `PurchaseSettingsPage`/`SettingsPage`/`GroupConstantsPage`.
- **T-S2 (إعدادات عامة):** أُضيف `SalesSettings.warn_on_duplicate_item` (افتراضي true)
  عبر الـ stack (model + serializer + هجرة `0019` + نوع TS + حفظ الصفحة) — **يقود فعلياً
  T-R3** (تنبيه التكرار في المحرّر، كان يقرأ الإعداد منذ المرحلة 3). قسم «إعدادات عامة
  (السلوك)» جديد في صفحة إعدادات المبيعات.
- **T-S3 (خريطة القيد + استعادة الافتراضي):** لوحة «خريطة القيد المحاسبي» في الصفحة تعرض
  مدين/دائن لكل نوع (بيع نقدي: الصندوق/الإيراد · آجل: ذمم العميل/الإيراد · خدمات · ت.ب.م/
  المخزون — مطابقة صورة 6) من الحسابات المُهيّأة. زر **«استعادة خريطة القيد الافتراضية»**
  → `POST sales/settings/restore-defaults/` يحلّ الحسابات من COA (كود ثم نوع ثم اسم).
  الترحيل يمرّ عبر الـ subledger أصلاً (حساب العميل المرتبط/الصندوق/الإيراد).
- **T-S4 (خارطة الطريق — إعدادات/شاشات غير مبنية):**
  - أعلام عرض مكتبية (صورة 7/8) لم تُبنَ لتفادي مفاتيح ميتة بلا سلوك: «إظهار آخر سعر
    بيع / ربح الصنف / رصيد العميل قبل-وبعد»، «اقتراح الصنف بـ اسم/كود/باركود»، «عدد
    المنازل العشرية للسعر/الكمية» (G1 يطبّق منزلتين حالياً). تُبنى كحقول `SalesSettings`
    + ربط فعلي لاحقاً.
  - «إعدادات المخزون» و«البنوك» (من المرحلة 5) — شاشتان مستقلتان غير مبنيتين.
  - خريطة قيد الشراء (شراء نقدي/آجل، مرتجع شراء) — `PurchaseSettings` يحوي
    default_cash_account فقط؛ خريطة كاملة لاحقاً.
- **التحقق:** **3 اختبارات جديدة** (`test_settings_engine`: افتراضي التنبيه true + PATCH +
  restore-defaults يحلّ الأنواع الصحيحة) · **sales 45/45** · `manage.py check` 0 · tsc نظيف.
- **هجرة جديدة 0019 (sales) تُطبَّق عند النشر** (مع 0046 لوجستيات + 0010 inventory).

## [AUDIT — task22 Phase 7, 2026-06-20] (مستندات المخزون — T-I1 تحويل + T-I2 جرد)

مرحلة backend-ثقيلة: 4 نماذج جديدة + هجرة `0010` + خدمات ترحيل مُختبَرة + DRF + شاشتان.

- **النماذج (inventory/models.py):** `WarehouseTransfer`+`WarehouseTransferLine` ·
  `Stocktake`(+journal FK)+`StocktakeLine`(counted/system/variance). أُضيف نوعا مرجع
  `WAREHOUSE_TRANSFER`/`STOCKTAKE` إلى `StockMovement.REFERENCE_TYPES`. هجرة
  `0010_alter_stockmovement_reference_type_stocktake_and_more`.
- **الترحيل (inventory/services.py):**
  - `post_warehouse_transfer`: لكل بند `OUT` من المصدر + `IN` للوجهة **بالتكلفة
    المتوسطة الملتقطة** → صافي صفري على `quantity_on_hand`/`avg_cost` للشركة (نقل
    موقعي)، حركتان موسومتان بالمستودعين. **لا قيد محاسبي.** + `unpost_*` يعكس.
  - `post_stocktake`: لكل بند variance = counted − quantity_on_hand → `ADJUST_IN`
    (فائض) أو `ADJUST_OUT` (عجز)؛ يُجمِّع قيد فرق واحد عبر `post_journal`
    (فائض: مدين المخزون/دائن ت.ب.م · عجز: العكس) بقيمة variance×avg_cost. حسابا
    المخزون/ت.ب.م عبر `_resolve_line_account` (لا حساب تسوية مخصّص مطلوب). لا فرق ⇒ لا قيد.
- **الواجهة:** `WarehouseTransferViewSet`/`StocktakeViewSet` (+ actions `/post/`,
  `/unpost/`) على `inventory/warehouse-transfers/` و`inventory/stocktakes/`. سيريلايزرز
  بأسطر متداخلة قابلة للكتابة (ترفض تعديل المُرحَّل).
- **الأمامي:** `WarehouseTransferPage` + `StocktakePage` (قائمة + نموذج «حفظ وترحيل») ·
  `inventoryApi` (get/create/post لكلٍّ) · AppView+VIEW_PATHS+Breadcrumb · روابط في
  مجموعة «المخزون» بالشريط الجانبي.
- **التحقق:** **9/9 اختبارات جديدة** (`test_inventory_documents`: صافي صفري التحويل +
  وسم الحركات + رفض نفس المستودع + رفض الترحيل المزدوج + عكس · الجرد فائض/عجز/قيد/لا-فرق) ·
  **inventory 29/29** · `manage.py check` 0 · tsc نظيف · `resolve()` للمسارين · التطبيق
  يُحمَّل بلا أخطاء console. (الشاشات خلف الدخول — لم تُختبر بصرياً.)
- **هجرة جديدة 0010 تُطبَّق عند النشر** (مع 0046 لوجستيات من المرحلة 4).

## [AUDIT — task22 Phase 6, 2026-06-20] (مدفوعات + شبكات + سندات — T-P1/P2/G1/V1)

- **T-V1 (خلل سندات الصرف للموردين):** `SupplierPaymentsPage` كان يستدعي
  `purchase/payments/` — **لا مسار باسم `api/purchase/`** فيفشل بـ 404 عند الفتح.
  المسار الصحيح المُسجَّل: `logistics/supplier-payments/` → `SupplierPaymentViewSet`.
  أُصلح: القائمة + الإنشاء (عبر `purchaseInvoiceApi.addSupplierPayment` الذي ينشئ+يرحّل)،
  وأُعيدت تسمية حقول الصف `supplier→partner`/`supplier_name→partner_name` لمطابقة
  `SupplierPaymentSerializer`، وحُذفت لافتات «backend N8-T12 غير جاهز» المضلِّلة.
  **إثبات:** `resolve('/api/logistics/supplier-payments/')→SupplierPaymentViewSet`،
  `'/api/purchase/payments/'→404`. (تفصيل الشيكات/خصم المصدر لا يحفظه النموذج المبسّط —
  خارطة طريق.)
- **T-P1 (FIFO + فاتورة محددة):** `SalesCustomerPaymentsPage` — أُبقي «اقتراح FIFO»،
  وأُضيف منتقي فاتورة مفتوحة محددة (`partnerAging`) + زر «أضف الفاتورة» يُنشئ سطر توزيع
  بمبلغ افتراضي = min(متبقي الدفعة، متبقي الفاتورة). توزيعات قابلة للتحرير كما هي.
- **T-P2 (سند قبض سريع من كشف الحساب):** زر «سند قبض جديد» في `PartnerProfilePage`
  (للعملاء) يفتح `/sales/customer-payments?pay_partner={id}`؛ الصفحة تقرأ الباراميتر
  وتفتح المودال مع العميل مُعبّأً مسبقاً (`initialPartnerId`).
- **T-G1 (أعمدة قابلة للتحجيم Excel-like):** `AseelDenseTable` أُضيف له مقبض سحب على
  الحافة الطرفية لكل عمود (`resizable` افتراضي مُفعّل) — يعمل لشبكة العملاء وكل
  المستهلِكين (DRY). يحسب الدلتا حسب اتجاه RTL/LTR.
- **التحقق:** tsc نظيف (exit 0) · إثبات توجيه T-V1 عبر `resolve()`. **التحقق البصري
  للشاشات يحتاج جلسة مصادَقة** (خلف الدخول) — لم يُجرَ.

## [AUDIT — task22 Phase 5, 2026-06-20] (إعادة هيكلة التنقّل — Section 9 + T-N1..T-N3)

- **الشريط الجانبي (`Sidebar.tsx`) أُعيد بناؤه data-driven** بمجموعات Section 9 الكبيرة،
  كلٌّ بأيقونته (عارض `renderGroup` موحّد DRY، أصناف ثابتة بـ design-tokens — تفادي
  مصيدة Tailwind للأصناف الديناميكية). الترتيب:
  1. الرئيسية (Home) 2. المبيعات (ShoppingCart): فواتير/عروض/إشعارات/مرجع بيع/أرباح/
  إعدادات-آخراً 3. العملاء (Users): العملاء/دفعات 4. المشتريات (ShoppingBag): فواتير/
  عروض أسعار/مرجع شراء/سندات صرف/إعدادات/موردين 5. المخزون (Warehouse): أرصدة/الأصناف/
  حركات + **مجموعة فرعية «الاستيراد»** (الصفقات/الشحنات/أرشيف/نقل محلي/تخليص/رحلة) —
  **زر الاستيراد المستقل أُزيل** 6. المالية (Landmark): صناديق/شيكات 7. التقارير
  (تفتح كلٌّ في **تبويب جديد** G2 عبر `openInNewTab`) 8. **إدارة المهام في الأسفل تماماً**.
  المحاسبة محفوظة كمجموعة (وصول كامل للعمليات، لا تُكسر ميزة).
- **T-N1:** المساعد الذكي نُقل من الشريط الجانبي إلى رأس `AppLayout` بجوار `BranchSwitcher`
  («كل الفروع»).
- **T-N2:** زر «التصنيفات» (`items-categories`) أُزيل من التنقّل (المسار/التبويب باقٍ).
- **T-N3:** شاشة الأصناف (`ItemsManagement`) أصبح لها **عرض شجرة تصنيفات** (يعيد استخدام
  `InvoiceCategoryTree`) كافتراضي + مبدّل شجرة/جدول. نقرة=بطاقة، اختيار=تعديل.
- **شاشات غير مبنية (خارطة طريق، T-S4):** «إعدادات المخزون» و«البنوك» لا تملكان شاشة
  مستقلة — لم تُضَف أزرار مكسورة؛ تُبنى في مرحلة لاحقة. `aseel-kit` (أداة تطوير) أُسقط
  من التنقّل (المسار باقٍ).
- **تحذير تصميمي:** المجموعات موحّدة اللون (design-tokens) مع أيقونات مميِّزة بدل ألوان
  لكل مجموعة (تفادي عجز Tailwind JIT عن توليد أصناف ديناميكية).
- **التحقق:** tsc نظيف (exit 0) · إزالة الاستيرادات اليتيمة (Sparkles/Wrench/DashboardIcon) ·
  Vite يبني، التطبيق يُحمَّل بلا أخطاء console. **التحقق البصري لترتيب التبويبات يحتاج
  جلسة مصادَقة** (الشريط خلف الدخول) — لم يُجرَ.

## [AUDIT — task22 Phase 4, 2026-06-20] (روابط الحسابات + النقد — T-A1..T-A4)

- **T-A1 (المتبقي على حساب العميل):** **موجود أصلاً** (task18) — صفّا «رصيد العميل»
  و«الرصيد بعد الفاتورة» في رصيف الإجماليات + سطر «الرصيد السابق/بعد الفاتورة» في
  بطاقة العميل بالرأس. لا تغيير.
- **T-A2 (بطاقة العميل قابلة للنقر):** زر «بطاقة العميل» بجوار حقل العميل في
  `SalesInvoiceEditor` يفتح `/partners/{id}` في **تبويب جديد** (G2 — يحفظ الفاتورة الجارية).
- **T-A3 (المورد قابل للنقر عالمياً):** عمود المورد في `InvoiceList` (قائمة فواتير
  الشراء) صار رابطاً لكشف حساب المورد `/partners/{supplierId}` في تبويب جديد
  (`stopPropagation` كي لا يفتح الصف). (بطاقة العميل/المورد وكشف الحساب كلها
  `PartnerProfilePage` على `/partners/:id` — تبويب statement.)
- **T-A4 (الصندوق الافتراضي):**
  - **مبيعات:** أُزيل منتقي «حساب الصندوق» للدفعة المرفقة (موضعان) واستُبدل بعرض
    للقراءة فقط للصندوق الافتراضي + effect يملؤه من `default_cash_account`. (صندوق
    الفاتورة النقدية نفسه كان يتبع الإعدادات أصلاً، بلا منتقي.)
  - **شراء:** أُضيف الحقل عبر الـ stack: `PurchaseSettings.default_cash_account` FK
    (logistics/models.py) + هجرة `0046_purchasesettings_default_cash_account` +
    حقل في `PurchaseSettingsSerializer` + نوعا `purchaseInvoiceApi.get/updateSettings`
    + منتقي صندوق في `PurchaseSettingsPage` (يحمّل `accounting/accounts/`).
- **التحقق:** tsc نظيف (exit 0) · `manage.py check` 0 مشاكل · هجرة 0046 تُطبَّق على
  DB نظيفة (pytest) · `test_purchase_price_resolver` 8/8 · **الحزمة الكاملة 217/217** (لا انحدار).

## [AUDIT — task22 Phase 3, 2026-06-20] (سلوك بنود الفاتورة — T-R1..T-R4)

- **T-R1 (خلل السطور الوهمية، مبيعات):** `SalesInvoiceEditor.updateLine` كان يُلحق سطراً
  جديداً عندما يكون آخر سطر «ممتلئاً» بشرط `product!=="" || quantity!=="0"`. بما أن
  `makeEmptyLine` يبدأ بالكمية `"1"`، كان كل سطر فارغ يُحسب ممتلئاً فتتكاثر السطور.
  **الإصلاح:** الإلحاق فقط عندما يكتسب آخر سطر **صنفاً** حقيقياً (`product!=="" && !==-1`).
  محاكاة Node: قديم=5 سطور بعد إضافة+3 تعديلات كمية، جديد=2 (ممتلئ + فارغ واحد).
  (الشراء لا يعاني الخلل — `applyItemAt` يُلحق سطراً ذيلياً واحداً متحكَّماً به فقط.)
- **T-R2 (بطاقة الصنف ← حوار كمية+سعر):** `shared/ProductCardModal` أُضيف له **وضع إضافة**
  (`addMode`) يعرض حقل **الكمية** وحقل **السعر** مع **شارة مصدر** (`من آخر فاتورة` /
  `من عرض السعر` / `السعر الافتراضي`)، و«موافق» يمرّر `{quantity, unitPrice}`. وُصِّل في
  الشاشتين: المبيعات تُقدّر السعر عبر `resolveSalePrice` عند فتح البطاقة وتُثبّت السعر
  المُدخل (`priceTouched`)؛ الشراء عبر `resolveSuggestedPrice` ويمرّر الكمية إلى
  `applyItemAt(…, qtyOverride)`.
- **T-R3 (تنبيه التكرار):** المبيعات: تنبيه/تأكيد جديد في `insertProductIntoInvoice`
  يتبع إعداد `warn_on_duplicate_item` (افتراضي مُفعّل — جاهز لربط إعداد المرحلة 8).
  الشراء: **موجود أصلاً** (`applyItemAt` يعرض دمج/سطر مستقل).
- **T-R4 (حارس العمل غير المحفوظ):** المبيعات: `guardedReset` على «إضافة/إلغاء» —
  تأكيد ثنائي (متابعة؟ ثم حفظ-قبل-المغادرة؟). الشراء: `guardedGoNew` يحرس «جديدة»
  عندما تكون الفاتورة بلا id وتحتوي بنوداً (حالة فقدان العمل الحقيقية؛ لا تتبّع dirty
  كامل في الشراء — حُرست الحالة الجوهرية فقط). اختصار Ctrl+Ins تُرك بلا حارس (تفادي
  use-before-define؛ زر «جديدة» المرئي محروس).
- **تعميم G1:** `ProductCardModal.fmt2` ما يزال toLocaleString(min2) داخل KPIs البطاقة —
  مُدرج لاحقاً (عرض إحصائي، ليس مبالغ فاتورة).
- **التحقق:** tsc نظيف (exit 0) · محاكاة T-R1 Node. **التحقق البصري للحوار/الحارس يحتاج
  جلسة مصادَقة** (محرّر الفاتورة خلف الدخول) — لم يُجرَ.

## [AUDIT — task22 Phase 2, 2026-06-20] (تخطيط الفاتورة — رأس أفقي مدمج T-L1..T-L5)

**السبب الجذري (T-L1):** القشرة `AseelDocumentShell` تلفّ الرأس في `.aseel-headband`
لكن هذا الصنف لم يكن يضبط `display`، فحقول `fld()` (label.aseel-field) تتراصّ
**عمودياً** وتبتلع نصف الصفحة — تماماً كصورة 11 لفاتورة الشراء. (قاعدة الموبايل
كانت تتجاوز `grid-template-columns` لم يُضبط على الديسكتوب أصلاً — تخطيط مرتجَع.)

- **الإصلاح (DRY، عالمي):** `styles/index.css` — `.aseel-headband` صار
  `display:flex; flex-wrap:wrap; gap:3px 14px`، و`> .aseel-field` يأخذ
  `flex:1 1 220px; min-width:190px; max-width:340px`. يُصلح رأس فاتورة الشراء
  وكل شاشات المستندات (deals، عروض الأسعار، المرتجعات…) دفعة واحدة. رأس المبيعات
  محفوظ لأن طفله الأول `w-full` فيبقى صفّاً مستقلاً. قاعدة الموبايل (<640px) حُدِّثت
  لـ `flex-direction:column`.
- **T-L1/T-L2/T-L5:** الرأس الآن أفقي مضغوط على الشاشتين؛ المورد/الاسم متجاوران.
  T-L3 (الشريط) وT-L4 (رصيف الإجماليات الثابت) مؤمَّنان أصلاً ببنية القشرة.
- **تعميم G1 (المرحلة 2):** `SalesInvoiceEditor.fmt` و`InvoiceForm.fmt` أُعيد تعريفهما
  إلى `formatMoney` (يحذف الأصفار الزائدة من كل الإجماليات) + سطرا رصيد المورد.
- **التحقق:** tsc نظيف (exit 0) · خادم Vite يبني/يخدم بلا أخطاء CSS، التطبيق يُحمَّل
  (صفحة الدخول) بلا أخطاء runtime. **التحقق البصري للرأس الأفقي يحتاج جلسة مصادَقة
  (محرّر الفاتورة خلف تسجيل دخول)** — لم يُجرَ لأن إدخال بيانات الدخول ليس من صلاحياتي.

## [AUDIT — task21, 2026-06-19] (تحسينات UX لفاتورة البيع/الشراء + تسعير عرض السعر — DEF-001..009)

تغييرات جراحية على شاشتي فاتورة المبيعات/الشراء وشجرة المنتجات وبطاقة الصنف
وبطاقة العميل. لا انحدار محاسبي (UI/UX + اقتراح سعر فقط). **تحقّق حيّ في المتصفح
بجلسة مصادَقة فعلية** (أول مهمة تتحقق حيّاً من الشاشات الداخلية).

### الطبقة المشتركة (DRY)
- **`frontend_v2/components/shared/ProductCardModal.tsx`** — بطاقة الصنف كمودال
  واحد يُعاد استخدامه في **ثلاثة مداخل** (DEF-007/008): نقر مفرد على الشجرة ·
  أيقونة (i) في القائمة المنسدلة · أيقونة (i) على سطر الفاتورة. يقرأ نفس نقطة
  `inventory/products/{id}/profile/`. أسعار بمنزلتين (DEF-003).
- **`core/pricing.py resolve_sales_price`** — أُضيف سقوط «عرض السعر اليدوي»
  (CustomerProductQuote) بين «آخر بيع للعميل» و«سعر الصنف الافتراضي». الأولوية
  (DEF-005): آخر فاتورة للعميل **تفوز دائماً** ← عرض السعر اليدوي ← tier ← فارغ.
  مصدر السعر يُرجَع في `source.document_type` (`SALES_INVOICE`/`CUSTOMER_QUOTE`).

### DEF-001..003 (تموضع/تسمية/تنسيق)
- DEF-001: `.aseel-tree-panel` صارت `sticky top:8px` بارتفاع `calc(100vh-160px)`
  و`min-height:320px` ⇒ رأس الشجرة + 20+ صفاً ظاهرة دون تمرير على 1366×768.
- DEF-002: «شجرة الأصناف» → **«شجرة المنتجات»** (3 مواضع). الهرمية صريحة: الصنف/
  الفئة = عقدة فرعية، المنتج = عقدة ورقية. **لا إعادة تسمية للباك-إند** (A1).
- DEF-003: بطاقة الصنف تعرض كل الأسعار بمنزلتين؛ السعر المقترح للسطر يُعرض عبر
  `toFixed(2)` (يبقى قابلاً للتحرير). الدقّة المخزّنة (4 منازل) لم تُمَسّ (A2).

### DEF-004 — عرض السعر لكل العميل (مبيعات فقط)
- موديل **`sales.CustomerProductQuote`** (جدول `sales_module_customer_product_quotes`،
  migration `0018`): فريد `(tenant, customer, product)` + `unit_price`. لا أثر
  محاسبي (A3).
- خدمات `sales/services.py`: `customer_price_list` (كامل الكتالوج + مصدر/قابلية
  تحرير لكل صف: مُشترى→سعر آخر فاتورة للقراءة فقط، غير مُشترى→حقل قابل للتحرير) ·
  `save_customer_quotes` (upsert؛ قيمة فارغة تحذف العرض).
- نقطة نهاية `CustomerPriceListViewSet`: `GET sales/customer-price-list/?customer=` ·
  `POST sales/customer-price-list/save/`.
- واجهة: تبويب **«عرض السعر»** في `PartnerProfilePage` (للعملاء فقط) عبر
  `CustomerPriceListTab.tsx` + `salesApi.getCustomerPriceList/saveCustomerQuotes`.

### DEF-005..008 (سلوك السطر/الشجرة/القائمة)
- DEF-005: شارة مصدر السعر على السطر («من آخر فاتورة» / «من عرض السعر») —
  `DraftLine.priceSource` يُضبط من نتيجة الـ resolver، يُمسح عند التحرير اليدوي.
- DEF-006: السطر يُضاف فقط بزر **«إضافة سطر»** الصريح (أُضيف لشاشة المبيعات أيضاً)؛
  النقر خارج الجدول/على الشجرة (مفرد) لا يُنشئ صفوفاً (مُتحقَّق حيّاً).
- DEF-007: في `InvoiceCategoryTree` تمييز نقر مفرد/مزدوج عبر مؤقّت 220ms — مفرد=
  بطاقة (`onShowCard`)، مزدوج=إدراج (`onPickItem` كما كان). متطابق بيع/شراء (مكوّن
  مشترك).
- DEF-008: `AseelAutocomplete` صار يعرض أيقونة (i) لكل خيار (`onInfo`) تفتح البطاقة
  دون اختيار/إضافة؛ وأيقونة (i) بجانب المنتج المختار على السطر (بيع وشراء).

### DEF-009 — مهلة الخمول
- ثابت وحيد `frontend_v2/constants/session.ts IDLE_TIMEOUT_MS = 30دقيقة` +
  `components/IdleTimeoutGuard.tsx` (مركّب في `App.tsx`): بعد 30د خمول يمسح التوكن
  ويعرض مودال «تم إنهاء الجلسة» → العودة لتسجيل الدخول. أي نشاط يعيد ضبط المؤقّت.

### تحقق
- backend: TDD جديد `sales/tests/test_customer_quote_pricing.py` (+6: مصفوفة
  الأولوية quote-only/purchased-beats-quote/neither + نقطة القائمة list/save/delete).
  حزم البيع+التسعير+البطاقات **57 أخضر** · `makemigrations --check` لا انحراف ·
  `manage.py check` 0.
- frontend: tsc 0 · vite build OK.
- **حيّ في المتصفح (1366×768، جلسة فعلية):** «شجرة المنتجات» (لا «أصناف») · الشجرة
  أعلى البنود (20+ صفاً) · نقر مفرد=بطاقة · مزدوج=إدراج بلا تكرار · نقر خارجي=صفر
  صفوف · (i) القائمة ×8 تفتح البطاقة دون اختيار · (i) السطر ×2 تفتح البطاقة ·
  تبويب «عرض السعر» يظهر للعميل. (قائمة «عرض السعر» الحيّة فارغة لأن خادم الـ API
  المتصل به الواجهة لم يُنشر عليه الـ endpoint/migration الجديدان بعد — مُغطّى
  backend بالاختبارات. نشر: `python manage.py migrate sales`.)

### [ORPHANS & PENDING — task21]
- DEF-009 لم يُختبر حيّاً (يتطلب انتظار 30د)؛ الكود مركّب والبناء نظيف.
- صف فارغ تالٍ بعد الإدراج = سلوك قائم سابقاً في محرر المبيعات (ليس صفاً «شارداً»).
- بطاقة الصنف لا تعرض «آخر 7/28 يوم» ولا صورة (نقطة `profile` لا تُرجعهما) — تُضاف
  عند توسعة الـ endpoint لاحقاً.

## [AUDIT — task20, 2026-06-18] (التسعير الذكي + بطاقات الكيانات — FEAT-1..4)

نطاق: تسعير تلقائي لبنود الشراء (FEAT-1) والبيع حسب العميل (FEAT-2) + بطاقة صنف
احترافية (FEAT-3) + بطاقتا عميل/مورد (FEAT-4). المبدأ المعماري: مصدر حقيقة واحد
(الفواتير المرحَّلة/الأستاذ) — لا مخزن أسعار موازٍ.

### الطبقة المشتركة (Core / DRY)
- **`core/pricing.py` — PriceResolver (strategy pattern):** دالّتان عامتان
  `resolve_purchase_price` (LAST_PURCHASE/LOWEST_PURCHASE) و`resolve_sales_price`
  (LAST_SALE_TO_CUSTOMER) + facade `PriceResolver.resolve`. يقرأ **فقط** المستندات
  المرحَّلة (`PurchaseInvoiceItem` على فاتورة `is_posted`، `SalesInvoiceLine` على
  فاتورة `posted/sale`). تطبيع العملة عبر سعر صرف المستند (للأساس ثم للعملة الهدف)،
  وتطبيع أساس الضريبة (inclusive↔exclusive) عبر نسبة ضريبة السطر. سلسلة سقوط: تاريخ
  الشراء → `Product.avg_cost`؛ تاريخ بيع العميل → سعر بيع الصنف (`ProductPriceTier`
  المطابق للعملة) → فارغ. تسجيل (logging) لكل مسار. **يبطل** مسار
  `priceListService.getLastSupplierPrice` القديم (مجموعة `supplier_prices` الموازية).
- **`frontend_v2/components/shared/LedgerTable.tsx`:** مكوّن واحد لقوائم الحركات ذات
  «الرصيد الجاري» — أعمدة كبارامتر (وارد/صادر للصنف · Dr/Cr للشريك) + `DocRefCell`
  (مرجع مستند قابل للنقر عبر `utils/entityLinks.invoicePathForReference` — مُحلِّل
  المراجع المشترك). يستهلكه ProductProfilePage + PartnerProfilePage.

### FEAT-1 — تسعير الشراء + إعدادات الشراء
- موديل `logistics.PurchaseSettings` (`purchase_default_price_strategy`) + migration
  `logistics/0045_purchasesettings` + `get_or_create_purchase_settings`.
- نقاط نهاية: `GET logistics/purchase-invoices/resolve-price/?product=&strategy=&exchange_rate=`
  · `GET|PUT|PATCH logistics/purchase-settings/current/`.
- واجهة: `PurchaseSettingsPage` (view `purchase-settings`, مسار `/purchase-settings`,
  في شريط المشتريات الجانبي) · `InvoiceForm` يستدعي `purchaseInvoiceApi.resolvePrice`
  عند اختيار صنف (يحل محل `getLastSupplierPrice`) مع **حماية تعديل** (لا يَدُس سعراً
  أُدخل يدوياً — يُملأ فقط إن كان صفراً).

### FEAT-2 — تسعير البيع حسب العميل
- نقطة نهاية: `GET sales/invoices/resolve-price/?product=&customer=&exchange_rate=&tax_inclusive=`
  (`last-price` القديمة باقية). `salesApi.resolveSalePrice`.
- واجهة: `SalesInvoiceEditor` — `onSelectProduct` يستدعي الـ resolver؛ تغيير العميل
  بعد وجود بنود يُعيد تسعير الأسطر **غير المَلموسة فقط** (effect على `customerId`).
  حقل `DraftLine.priceTouched` (يُضبط عند تحرير السعر يدوياً وعلى الأسطر المحمَّلة/
  المستعادة) يحمي السعر اليدوي.

### FEAT-3 — بطاقة الصنف
- `inventory/services.py`: `product_profile` (KPIs) · `product_stock_ledger` (رصيد
  جارٍ = `StockMovement.quantity_after` المخزّن ⇒ يطابق المخزون الحالي، مُرقَّم) ·
  `product_linked_invoices`. أكشِنات على `ProductViewSet`: `profile/`, `stock-ledger/`,
  `invoices/`.
- واجهة: `components/items/ProductProfilePage` (view `product-profile`, مسار
  `/products/:id`) — اسم الصنف في `ItemsManagement` يفتحها.

### FEAT-4 — بطاقتا العميل/المورد
- `accounting/services.py`: `partner_account_statement` (Dr/Cr + رصيد جارٍ، مُرقَّم،
  يطابق `partner_posted_balance`). أكشِنات على `PartnerViewSet`: `profile/`
  (الرصيد + جهة Dr/Cr + إجماليات + آخر معاملة), `statement/`, `invoices/`.
- واجهة: `PartnerProfilePage` — مُلئت تبويبات «ملخص الرصيد/كشف الحساب/الفواتير»
  عبر LedgerTable (بدل placeholders «قريباً»؛ أُزيل تبويب GL على مستوى الحساب لصالح
  كشف الحساب المحصور بالشريك).

### تحقق
- اختبارات جديدة (TDD، +28): `logistics/tests/test_purchase_price_resolver.py` (8) ·
  `sales/tests/test_sales_price_resolver.py` (6) · `inventory/tests/test_product_profile.py` (7) ·
  `accounting/tests/test_partner_statement.py` (7).
- **backend 211/211 أخضر** · tsc 0 · vite build OK · `makemigrations --check` لا انحراف ·
  `manage.py check` 0. لم يُتحقق في متصفح حي للشاشات الداخلية (تتطلب باك-إند + جلسة —
  نفس قيد المهام السابقة)؛ التحقق عبر الاختبارات + الأنواع + البناء.
- **ملاحظة نشر:** `python manage.py migrate` (logistics/0045 — جدول `purchase_module_settings`).

### إصلاح كاش الـ PWA والتحديثات (بعد بلاغ «البطاقة فارغة/عالقة»)
- **السبب الجذري:** `sw.ts` كان (1) يعترض نداءات `/api/` **عابرة الأصل** (الواجهة :3000،
  الـ API :8000) بـ networkFirst/مهلة 3ث + سقوط للكاش ⇒ يُقدَّم رد قديم/فارغ أو 503
  بدل الخادم؛ (2) `cacheFirst` على JS باسم كاش ثابت `ktra-static-v1` ⇒ كود قديم محبوس؛
  (3) `registerType:'prompt'` بلا إعادة تحميل تلقائية ⇒ التحديث لا يصل بلا مسح يدوي.
- **الإصلاح:** حارس **same-origin** (نداءات الأصل الآخر تتجاوز الـ SW تماماً) · اسم كاش
  ثابت مشتق من بصمة البناء `ktra-static-${hash(__WB_MANIFEST)}` ⇒ activate يمسح كاش
  أي نسخة سابقة · التنقّل (navigate) network-first ليصل index.html الأحدث · مهلة الـ API
  8ث · `index.tsx` يستمع لـ `controllerchange` فيعيد التحميل مرة واحدة عند تفعيل SW جديد
  (حارس `_hadController` يمنع ذلك عند أول تثبيت وحلقات التحميل). **تحقق:** vite build OK ·
  tsc 0. **إجراء لمرة واحدة للخروج من SW القديم العالق:** إعادة بناء + إعادة تحميل
  (أو DevTools→Application→Unregister إن لزم)؛ بعدها التحديثات تُطبَّق تلقائياً.

### إصلاح جذري: البطاقة فارغة لأن `id`=undefined (لا علاقة للكاش/الخادم)
- **السبب الجذري المؤكَّد:** `App` مركّب في `index.tsx` على مسار splat `<Route path="/*">`
  بلا أي `<Route path=":id">` داخلي (يعرض الصفحات عبر `switch(appView)`). لذا
  `useParams().id` داخل `ProductProfilePage`/`PartnerProfilePage` يرجع **undefined**،
  وشرط `if (!id) return;` في كل الـ effects يمنع إرسال أي طلب ⇒ الاسم يبقى «جاري
  التحميل...» والتبويبات فارغة، وسجل الخادم لا يُظهر أي نداء `/profile|/invoices|/statement`.
  (تم الفحص: خادم :8000 يردّ 401 على النقاط = موجودة وسليمة؛ المشكلة كانت أن الواجهة
  لا ترسل الطلب أصلاً.)
- **الإصلاح:** استخراج المعرّف من `useLocation().pathname` عبر regex
  (`/products/([^/]+)` و`/partners/([^/]+)`) بدل `useParams`. هذا أصلح بطاقة الصنف
  **وبطاقة الشريك** (التي لم تكن تعمل ببيانات حقيقية أصلاً لنفس السبب). vite build OK · tsc 0.

### [ORPHANS & PENDING — task20]
- `priceListService.ts` لم يعد مستهلَكاً من `InvoiceForm` (بقي معرّفاً — لم يُحذف
  لاحتمال استهلاك آخر؛ مرشّح للإزالة لاحقاً).
- تطبيع UoM: النظام بلا معامِلات تحويل وحدات — السعر بوحدة الصنف الأساسية (A5).
- بطاقة الصنف: لا صورة في الرأس بعد (KPIs نصية)؛ تُضاف عند جولة UI حية.

## [AUDIT — task16, 2026-06-13] (Surgical sweep — Section B accounting first, then UX/nav)

### B. القيد المزدوج يمرّ دائماً عبر الـ subledger (مُنفَّذ + مُختبَر)
- **السبب الجذري (مُتحقَّق بالكود لا بالوصف):** كل من `post_sales_invoice` (sales/services.py) و`PurchaseInvoiceViewSet.post_to_accounting` (logistics/views.py:1801) كانا **يربطان الـ subledger في القيد الآجل فقط**؛ أما البيع/الشراء النقدي فكان يدين/يدائن الصندوق مباشرة ويتجاوز حساب العميل/المورد ⇒ كشف الحساب والأعمار لا يعكس الحركات النقدية. (القيد كان متوازناً وصحيح الحسابات الأخرى — لذلك لم نُعد كتابة الدالة، بل صوّبنا مسار النقدي فقط.)
- **الإصلاح (Section B):**
  - **مبيعات:** يُقيَّد دائماً Dr ذمم العميل بكامل الإجمالي / Cr إيراد+ضريبة، ثم تُسوَّى التحصيلات (نقدي: Dr صندوق/Cr ذمم؛ شيكات: Dr شيكات برسم التحصيل/Cr ذمم) في نفس السند. خصم المصدر يُحسب مبكراً ليُخصم من صافي التحصيل النقدي. `amount_paid` يشمل الآن النقدي المُحصَّل على الفاتورة النقدية.
  - **مشتريات:** الحساب الدائن دائماً ذمم المورد (subledger)؛ `payment_type='cash'` (أو `attached_cash_amount` جزئي) يضيف تسوية Dr ذمم المورد / Cr صندوق تُفرّغ الذمم دون تجاوزها.
- **تحقق:** اختباران جديدان (`sales/tests/test_subledger_routing.py` + `logistics/tests/test_pi_subledger_routing.py`) يثبتان لمس الـ subledger (Dr كامل + Cr تسوية) وتوازن القيد · **الحزمة كاملة 169/169 خضراء** (167 + 2).

### بقية البنود — تتبّع التنفيذ
**مُنفَّذ ومُتحقَّق (tsc 0 · vite build OK):**
- [x] **A5** مرجع الفاتورة في حركات المخزن رابط (StockMovementsPage) — عبر `utils/entityLinks.invoicePathForReference`.
- [x] **A6** مرجع فاتورة البيع/الشراء في قائمة قيود اليومية رابط (AccountingJournalListPage).
- [x] **A7** رقم فاتورة المبيعات نفسه رابط يفتح الفاتورة (SalesInvoicesPage).
- [x] **A8** قائمة فواتير المبيعات `/sales/invoices` وتفصيل واحدة `/sales/invoices/:id` مساران مستقلان (URL مصدر الحقيقة لفتح المحرر؛ deep-link/back-forward) + فرع التحليل العكسي في App.tsx.
- [x] **C11 (مبيعات)** العودة لـ `/dashboard` بعد حفظ الفاتورة (onInvoiceSaved).
- [x] **D12** بنر نجاح «حُفظ بنجاح» واضح في إعدادات المبيعات (aseel-banner--ok + role=status).
- [x] **E17** منتقي صنف عرض السعر كان يحمّل `getAccounts` (شجرة الحسابات) ⇒ صُحِّح إلى `inventory/products` (SalesQuotationsPage).
- [x] **E19** نقل «إدارة الموظفين» لأسفل الشريط الجانبي (Sidebar).

**مُنفَّذ ومُتحقَّق (الدفعة الثانية — tsc 0 · vite build OK · backend 169):**
- [x] **A4** روابط الكيانات: اسم الصنف (حركات المخزون)→`/items` · اسم العميل (قائمة فواتير المبيعات)→`/sales/customers` · اسم المورد (قائمة فواتير الشراء)→`/suppliers` عبر `utils/entityLinks.{productPath,customerPath,supplierPath}`. (ملاحظة: لا مسارات تفصيل مستقلة لكل كيان حالياً — الروابط تفتح صفحة الإدارة؛ يمكن توجيهها لصفحة تفصيل لاحقاً دون تغيير المستهلكين.)
- [x] **C9** إضافة مورد inline من حقل البحث في فاتورة الشراء (`InvoiceBasicInfo` يمرّر `onOpenAddModal`→`SupplierModal` القائم في `InvoiceForm`).
- [x] **C10** حالة الدفع (مدفوعة/جزئياً/غير مدفوعة) + الإجمالي + المتبقي — محسوبة في `PurchaseInvoiceSerializer` (amount_paid/remaining_balance/payment_status) ومعروضة في لوحة المحاسبة.
- [x] **C11 (شراء)** العودة لـ `/dashboard` بعد إتمام ترحيل فاتورة الشراء (onPosted).
- [x] **D13** أُزيل محددا حساب الإيراد وحساب الصندوق من `SalesInvoiceEditor` — يُقرآن من إعدادات المبيعات (default_revenue_account_product/default_cash_account)؛ رسائل التحقق تُحيل للإعدادات.
- [x] **D14** اختصارات شريط علوي قابلة للتهيئة: `utils/quickShortcuts` + شريط في `AppLayout` + قسم تهيئة في `SettingsPage` (تخزين محلي + بثّ حدث للتحديث الفوري).
- [x] **E15** الحاسبة: أُزيل الفتح التلقائي بالنقر المزدوج من `AseelGrid`؛ أُضيفت أيقونة حاسبة في الشريط العلوي (`AseelCalculatorButton` + وضع `standalone` في الـ popover).
- [x] **E16** رصيد الصندوق: أُضيف حقل `balance` محسوب من دفتر الأستاذ (مدين−دائن للقيود المرحَّلة) في `CashBoxLedgerAccountSerializer`؛ `CashBoxList` يعرضه بدل الرصيد المخزّن الصفري.
- [x] **E18** تصدير رصيد المخزون CSV (مع BOM للعربية) + اختيار الأصناف بمربعات + «تحديد الكل» في `StockLevelsPage`.

**إصلاحات ما بعد التشغيل (بلاغ المالك بالصور على localhost):**
- زر «العودة للفواتير» الصريح أُضيف لشريط محرر فاتورة المبيعات (`SalesInvoiceEditor` toolbar `back` action + `onClose` prop) — كان فقط ✕ إغلاق صغير بزاوية الإطار.
- 🔴 **زر «إضافة عميل» كان يفتح `SupplierModal` (يُنشئ مورداً!):** في `SalesInvoiceEditor` كان مودال إضافة العميل = `SupplierModal` (عنوان «إضافة مورد جديد» + `suppliersService.addSupplierToDb`) ⇒ يُنشئ Supplier لا Customer. الإصلاح: `CustomerQuickAddModal` جديد يُنشئ شريكاً `partner_type=Customer` عبر `POST partners/` (نفس مسار صفحة العملاء) + `eventBus.publish("partners")` لتحديث القوائم + اختيار العميل تلقائياً.
- 🔴 **Section B ناقص — مسار «استلام بضاعة الفاتورة» كان يتجاوز ذمم المورد:** الإصلاح الأصلي غطّى `post_to_accounting` لكن `receive_purchase_invoice` (logistics/services.py، مسار task15 الفعلي للفواتير المحلية) بقي يدائن الصندوق مباشرة للنقدي ⇒ القيد #290 (Dr مخزون 1104 / Cr نقدية 1101) بلا حساب المورد. الآن: يدائن دائماً ذمم المورد بكامل القيمة، ثم يُسوّي النقدي (Dr ذمم المورد / Cr صندوق). +2 اختبار (`test_local_invoice_receive`: آجل يدائن AP · نقدي يمرّ عبر AP ويُسوّى). **backend 171**.
- **A7 (شراء):** رقم فاتورة الشراء في القائمة (`InvoiceList`) صار رابطاً يفتح الفاتورة (`onView`) — كان مقتصراً على فواتير المبيعات.

**تحقق نهائي:** backend **169/169** · tsc 0 · vite build OK. لم يُتحقق في متصفح حي للشاشات الداخلية (تتطلب باك-إند+تسجيل دخول — نفس قيد المهام السابقة)؛ التحقق عبر الاختبارات + الأنواع + البناء.

## [AUDIT — task19, 2026-06-16] (حجز/إعادة استخدام رقم القيد + توحيد تصميم فاتورة الشراء)

طلب المالك (Phase 0): (1) زر «تراجع عن الترحيل» على فاتورة الشراء يحذف كل قيودها ويُرجعها مسودة — **مُنفَّذ مسبقاً في task17** (backend `PurchaseInvoiceViewSet.unpost` + زر `PurchaseInvoiceAccountingPanel`). (2) **حفظ رقم القيد المحذوف وإعادة استخدامه نصّاً عند إعادة الترحيل.** (3) توحيد تصميم فاتورة الشراء ليطابق فاتورة المبيعات (full restructure).

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **«رقم القيد» = `JournalHeader.id` (PK، `JournalID`، AutoField).** عند التراجع كان الـ FK `invoice.journal` يُصبح NULL والقيد يُحذف؛ إعادة الترحيل تُخصّص PK جديداً عبر auto-increment. لا حقل يحفظ الرقم القديم على أي من نموذجَي الفاتورة.
- ادّعاء «تراجع المبيعات يفتح فاتورة الشراء» **غير قابل لإعادة الإنتاج بالكود**: `unpostSalesInvoice` يضرب `sales/invoices/{id}/unpost/` والمعالج يبقى على فاتورة المبيعات (ادّعاء قديم).

### قرارات المالك (2026-06-16)
- إعادة الاستخدام: **Option 1 (استخدام صارم + سقوط لرقم جديد)** + ضمان عزل: الرقم المحذوف يُحجز في **سلّة محذوفات مخفية** (recycle bin) لا يلتقطه أي قيد جديد بالخطأ، مخفي عن الواجهة، محفوظ بالخلفية حتى تطلبه إعادة الترحيل أو يسقط للبديل.
- تطبيق الميزة على **المبيعات + الشراء** معاً. UI: **إعادة هيكلة كاملة** لفاتورة الشراء.

### [EXECUTION — task19] (M1 — مُنفَّذ ومُختبَر)
- **`accounting.models.VoidedJournal`** (جدول `voided_journals`): سلّة المحذوفات — `original_journal_id` + `(tenant, reference_type, reference_id)` فريد. ليس قيداً حيّاً (لا أسطر) فلا يمسّ أياً من 135 موضع قراءة للأستاذ/ميزان المراجعة (لا انحدار). migration `accounting/0024_voidedjournal.py`.
- **`unpost_document(..., recycle=False)`**: عند `recycle=True` يحجز رقم القيد **الأساسي** (أول نوع في `journal_reference_types`) في `VoidedJournal` قبل الحذف. القيود الفرعية (COGS/استلام) تُحذف دون حجز (تُولَّد من جديد). مُوصَّل `recycle=True` في unpost المبيعات (`SALES_INVOICE`) والشراء (`PURCHASE_INVOICE`) فقط — الأربعة الأخرى تبقى حذفاً صرفاً.
- **`post_journal`**: يكتشف تلقائياً حجزاً لـ `(tenant, ref_type, ref_id)`؛ إن وُجد يُعيد إدراج القيد بنفس `original_journal_id` (force_insert ذرّي) ثم يحذف الحجز. تعارض الرقم (مشغول — غير متوقع) → رقم تلقائي جديد + `logger.warning`. القيود غير المُلغاة سابقاً (لا حجز) تسلك السلوك القائم.
- **تنظيف:** حُذف `perform_update` المكرر الميّت في `PurchaseInvoiceViewSet` (نسخة الحارس عند line 2226 تبقى).
- **اختبارات:** `accounting/tests/test_unpost_document.py` (+5، الآن 8): حجز ثم إعادة استخدام نفس الرقم · حجز القيد الأساسي فقط · لا حجز افتراضياً · السقوط لرقم جديد عند تعارض · **E2E عبر نقاط النهاية** (post→unpost→re-post نفس الرقم).
- **تحقق:** backend **187/187** خضراء.

### [EXECUTION — task19 / M2] (توحيد UI فاتورة الشراء — مُنفَّذ)
- **تشخيص:** `InvoiceForm` يستخدم أصلاً نفس بنية المبيعات (`AseelDocumentShell` + بطاقات رأس + `AseelGrid` للبنود + tabs + totals + status bar). الفرق الجوهري: شريط الأدوات كان فيه (تخزين/جديدة/طباعة/إلغاء) فقط — **بلا ترحيل/تراجع**؛ المحاسبة (post/unpost + معاينة القيد + وصل دفع المورد) كانت **بلوكاً منفصلاً أسفل المحرر** في `PurchaseInvoice.tsx`، بينما شاشة المبيعات تضعها inline (شريط أدوات واحد + تبويبات).
- **التنفيذ (single editor + inline accounting):**
  - أُضيف زرّا **«ترحيل» (Send)** و**«تراجع عن الترحيل» (Undo2)** لشريط أدوات `InvoiceForm` بنفس ترتيب/أيقونات المبيعات وبوّابات التفعيل (post: محفوظة + غير مرحّلة + غير مؤرشفة؛ unpost: مرحّلة فقط؛ التخزين يُعطَّل على المرحّلة). يستدعيان `purchaseInvoiceApi.postToAccounting`/`unpost` ثم يعيدان تحميل الفاتورة + شريط حالة (banner) نجاح/خطأ.
  - طُويت لوحة المحاسبة والحركات المالية إلى **تبويبين داخل المحرر**: «المحاسبة والقيد» (يستضيف `PurchaseInvoiceAccountingPanel` القائم) و«الحركات المالية المرتبطة» (`DocumentPaymentsTab`) — يطابقان تبويب `financial_movements` في المبيعات. تظهر فقط بعد حفظ الفاتورة (لديها id).
  - حُذف البلوك المنفصل + استيراداته من `PurchaseInvoice.tsx`.
- **تحقق:** tsc 0 · vite build OK · SPA يُقلع نظيفاً في preview (لا أخطاء console). جولة post→unpost حيّة في المتصفح تتطلب backend مُشغّلاً + جلسة مصادَقة (لم تُنفَّذ — مغطّاة backend عبر اختبار E2E في M1).

### [EXECUTION — task19 / M4] (توحيد قائمة فواتير الشراء + حذف «نسخ» من المبيعات — مُنفَّذ ومُتحقَّق حيّاً)
- **الملاحظة (من المالك بالسكرينشوت):** التوحيد السابق طال **المحرّر** فقط؛ **شاشة القائمة** بقيت مختلفة تماماً — المبيعات `AseelDocumentShell + AseelDenseTable`، بينما الشراء (`InvoiceList.tsx`) تصميم **بطاقي** (بطاقات إحصائية + بطاقات فواتير). كما اعترض المالك على ميزة «نسخ الفاتورة» في المبيعات (لم يطلبها).
- **التنفيذ:**
  - أُعيد بناء `InvoiceList.tsx` بالكامل على `AseelDocumentShell + AseelDenseTable` مطابقاً لقائمة المبيعات: فلاتر (بحث/الحالة/من-إلى تاريخ)، شريط أدوات موحّد (فاتورة جديدة/استيراد من تخليص/تحديث/طباعة)، أعمدة **رقم / التاريخ / المورد / الحالة (مرحَّلة·مسودة) / الإجمالي / إجراءات**، شريط حالة (العدد/الإجمالي/مرحَّلة/مسودة). حُذف التصميم البطاقي والـ pagination والتوسعة.
  - props جديدة لـ`InvoiceList`: `onCreateNew/onImport/onRefresh` — مُرّرت من `PurchaseInvoice.tsx`، وحُذف الهيدر العلوي المكرّر (أزراره صارت داخل شريط أدوات القشرة) ووسّع الحاوية لكامل العرض.
  - **إصلاح بيانات:** `sqlListToInvoice` في `PurchaseInvoice.tsx` لم يكن يُسقِط `is_posted` → كل الصفوف ظهرت «مسودة». أُضيف `isPosted: Boolean(row.is_posted)` (الحقل موجود في `PurchaseInvoiceListDto`).
  - **حذف «نسخ» من المبيعات** (قرار المالك): أُزيل `handleDuplicate` + زرّاه (مسودة/مرحّلة) + استيراد `duplicateSalesInvoice`/`Copy` من `SalesInvoicesPage.tsx`. (الـ endpoint الخلفي `duplicate` بقي دون لمس.)
- **تحقق حيّ في المتصفح (جلسة مصادَقة فعلية):** قائمة الشراء تَعرض جدول الأصيل (7 صفوف، أعمدة صحيحة)، الحالات صحيحة بعد الإصلاح (INV-0007/0002/0001=مرحَّلة، الباقي مسودة؛ شريط الحالة مرحَّلة 3/مسودة 4)، إجراءات الصف (عرض/تعديل/طباعة/تحويل/حذف)، بلا أخطاء console. قائمة المبيعات تعمل بلا زر «نسخ». tsc 0 · vite build OK.

### [EXECUTION — task19 / GR-IR] (قيدان منفصلان عبر حساب وسيط + الترحيل يستلم — مُنفَّذ)
- **قرار المالك (متدرّج):** فاتورة الشراء = **قيدان منفصلان** عبر **حساب وسيط** (GR/IR)؛ **كبسة الترحيل تستلم** البضاعة؛ **إلغاء الترحيل يمسح القيدين + المخزون**؛ إعادة الترحيل تعيد كل شيء بنفس الرقم. المبيعات متماثلة سلفاً (قيد فاتورة + قيد تكلفة) — تحقّق فقط بلا تغيير. النطاق: الفاتورة **المحلية** فقط (المستورد مخزونه عبر الشحنة).
- **حساب الوسيط:** `2106 «بضاعة مُستلَمة لم تُفوتَر (GR/IR)»` (Liability) في `seed_professional_coa` + `logistics.services._resolve_gr_ir_account` (إنشاء تلقائي للمستأجرين القائمين — لا migration).
- **`post_to_accounting` (محلي):** قيدان بدل واحد —
  - قيد الفاتورة (`PURCHASE_INVOICE`): مدين **الوسيط**(البضاعة)+ضريبة+رسوم+بنود مصروف / دائن المورّد.
  - قيد الاستلام (`PURCHASE_GRN`): مدين المخزون / دائن **الوسيط** + **إدخال مخزون فعلي** للمستودع الافتراضي (توزيع التكلفة تناسبياً لكل بند فيتطابق GL مع WAC). كله **ذرّي** (transaction.atomic). يُتجاوز إن كانت الفاتورة مستلمة مسبقاً (منع ازدواج).
- **`unpost`:** يحذف `['PURCHASE_INVOICE','PURCHASE_GRN','PURCHASE_RECEIPT']` + يعكس المخزون + يحجز رقم `PURCHASE_INVOICE` (task19). ⇒ القيدان والمخزون يُمسحان معاً، والوسيط يعود صفراً.
- **تحقّق:** اختبار `logistics/tests/test_purchase_grir_lifecycle.py` (قيدان متّزنان، الوسيط=0، مخزون داخل، post→unpost→repost نفس الرقم، idempotent ×N) + `sales/tests/test_sales_post_unpost_stock.py` (تماثل المبيعات). **190/190 أخضر**، لا migration drift.

### [ORPHANS & PENDING — task19]
- نقطة `accounting/views.py PurchaseReceiptViewSet` (`PURCHASE_RECEIPT`، أداة قيد استلام يدوية مستقلة) ما زالت تدائن المورّد مباشرةً (بلا وسيط) — خارج نطاق GR/IR عمداً (لا تمسّ دورة الفاتورة/المخزون). تُترك كما هي.
- الفاتورة **المستوردة** (صفقة/شحنة/تخليص): الترحيل يبقى قيداً واحداً ومخزونها عبر الشحنة — خارج النطاق بقرار المالك (الأكثر أماناً).
- الاستلام الجزئي/متعدد المستودعات: الترحيل يستلم الكل للمستودع الافتراضي؛ نافذة «الاستلام» المنفصلة تبقى للحالات المتقدمة.

## [AUDIT — task17, 2026-06-14] (تراجع عن الترحيل + حذف متسلسل للقيود + فصل قيد البيع النقدي)

طلب المالك: (1) للمستندات المرحَّلة الستة (فاتورة مبيعات/شراء، صفقة، شحنة، تخليص جمركي، نقل محلي) منع التعديل/الحذف المباشر مع تحذير + إجراء «تراجع عن الترحيل» يحذف **كل** قيود المستند (cascade) ويُرجعه مسودة، ذرّياً. (2) فصل قيد البيع النقدي إلى قيدين مستقلين: قيد الفاتورة (Dr ذمم / Cr إيراد + Dr تكلفة / Cr مخزن) ووصل دفع مستقل (Dr نقدية / Cr ذمم) لا يولّده ترحيل الفاتورة.

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **النظام كان يستخدم «قيوداً عكسية» لا الحذف:** `LOGISTICS_PAYMENT_UNPOST`/`CLEARANCE_PAYMENT_UNPOST`/`PURCHASE_INVOICE_REVERSAL`/`LOCAL_SHIPMENT_REVERSAL` تُنشئ قيداً معاكساً وتُبقي الأصل — لا حذف فعلي. المطلب الجديد: حذف القيود نفسها وإرجاع المستند لمسودة.
- **قيد البيع النقدي كان مدمجاً (task16 Section B):** `post_sales_invoice` كان يدين الذمم بالكامل ثم يُسوّي النقدي (Dr صندوق / Cr ذمم) في **نفس** القيد. المطلب: نزع تسوية النقدي من قيد الفاتورة تماماً.

### قرارات المالك (2026-06-14)
- Feature 2: **فصل** القيد لقيدين. وصل الدفع = **إعادة استخدام `CustomerPayment`** (post_customer_payment يُنشئ Dr نقدية / Cr ذمم مستقلاً أصلاً). تنفيذ **كل شيء دفعة واحدة**.

### [EXECUTION — task17]
- **الطبقة المشتركة (Core/DRY):**
  - `accounting.services.unpost_document(*, tenant_id, reference_id, journal_reference_types, stock_reference_types=(), user, document_label)` — المسار المركزي الوحيد للتراجع: يحذف كل `JournalHeader` لـ (tenant + reference_id + reference_type ∈ types) — أسطر القيد تُحذف cascade — ثم يعيد حركات المخزون، **ذرّياً** + audit log. النطاق محصور بدقة بقيود المستند وحده.
  - `inventory.services.reverse_stock_movements(...)` + `_recompute_product_stock(product)` — تحذف حركات المستند وتعيد احتساب `quantity_on_hand`/`avg_cost` بإعادة تشغيل بقية الحركات زمنياً (WAC دقيق، لا تقريب يفسد المتوسط).
  - `core.api_defaults.POSTED_DOC_WARNING` — رسالة موحّدة «هذا المستند مرحَّل…».
- **توصيل المستندات الستة (backend):** كل viewset أُضيف له `perform_update`/`destroy` يحظران تعديل/حذف المرحَّل (يردّان 400 + `{detail, can_unpost:true}`) + إجراء `POST .../unpost/`:
  - فاتورة مبيعات (`SALES_INVOICE`,`SALES_DELIVERY_COGS` + مخزون `SALE`,`STOCK_ISSUE`) → status=draft، journal=None، amount_paid=0، إعادة الشيكات Under_Collection→Draft.
  - فاتورة شراء (`PURCHASE_INVOICE`,`PURCHASE_RECEIPT` + مخزون `PURCHASE_INVOICE`) → is_posted=False، receipt_status=not، received_quantity=0. (استُبدل المسار العكسي القديم بالحذف.)
  - شحنة (`LOGISTICS_SHIPMENT` + مخزون `SHIPMENT`؛ «مرحّلة» = وجود قيد/حركة).
  - نقل محلي (`LOCAL_SHIPMENT`؛ استُبدل العكسي بالحذف).
  - صفقة/تخليص: القيود مفاتيحها على الدفعات (LOGISTICS_PAYMENT / CLEARANCE_PAYMENT) لا على المستند الأب — فالـ unpost يمرّ على الدفعات المرحَّلة ويحذف قيد كلٍّ ويعيدها مسودة.
- **Feature 2 (فصل قيد البيع النقدي):** أُزيلت كتلة تسوية النقدي من `post_sales_invoice` بالكامل (نقدي الفاتورة النقدية + `attached_cash` على الآجل) — قيد الفاتورة الآن يدين الذمم بالكامل ويدائن الإيراد/الضريبة (+COGS) فقط؛ `amount_paid` لم يعد يشمل النقدي. التحصيل يُسجَّل كـ `CustomerPayment` مستقل (Dr نقدية / Cr ذمم). **قرار جراحي:** تسوية الشيكات بقيت داخل قيد الفاتورة (المطلب نصّ على النقدي فقط، وفصلها يكسر دورة حياة الشيك). **أثر جانبي موثّق:** مبلغ النقدي المرفق عبر `attach_payment_voucher`/`attach_voucher_and_post` لم يعد يُرحَّل عند الترحيل — استُبدل بوصل دفع مستقل.
- **Feature 2 (شراء — امتداد بطلب المالك بعد مراجعة شاشة فاتورة الشراء):** نفس الفصل طُبِّق على **فاتورة الشراء** في كلا مساري الترحيل: `PurchaseInvoiceViewSet.post_to_accounting` و`receive_purchase_invoice` (task15). الترحيل يقيّد Dr مخزون/ضريبة / Cr ذمم المورد بالكامل فقط — أُزيلت تسوية الصندوق. الدفع للمورد أصبح **وصل دفع مستقل** عبر `SupplierPayment` (Dr ذمم المورد / Cr صندوق). الواجهة: `PurchaseInvoiceAccountingPanel` — أُزيلت أسطر التسوية النقدية من معاينة القيد، وأُضيف قسم «وصل دفع للمورد» (مبلغ + حساب صندوق → `purchaseInvoiceApi.addSupplierPayment` ينشئ ويرحّل SupplierPayment). اختبارا Section B للشراء (`test_pi_subledger_routing` + `test_local_invoice_receive::test_cash_receive…`) أُعيد ضبطهما (ap_debit=0، لا سطر صندوق).
- **الواجهة:** `salesApi.unpostSalesInvoice` + إجراء «تراجع عن الترحيل» في شريط `SalesInvoiceEditor` (يظهر مفعّلاً عند الترحيل فقط) · زر «تراجع عن الترحيل» + تحذير في `PurchaseInvoiceAccountingPanel` (الحالة المرحَّلة) عبر `purchaseInvoiceApi.unpost` القائم.
- **اختبارات (TDD):** `accounting/tests/test_unpost_document.py` (3): حذف محصور بالمستند فقط · عكس مخزون بإعادة التشغيل (WAC دقيق) · حظر حذف المرحَّلة ثم سماحه بعد التراجع عبر `/sales/invoices/{id}/unpost/`. وأُعيدت كتابة اختبارَي Section B (`sales/tests/test_subledger_routing.py`: قيد الفاتورة النقدية يدين الذمم فقط، لا سطر صندوق، amount_paid=0). **اختبار شراء Section B لم يُمَسّ (Feature 2 مبيعات فقط).**
- **تحقق:** backend **174/174** خضراء · tsc 0 · vite build OK · `manage.py check` 0 · `makemigrations --check` لا انحراف (لا تغييرات نماذج). لم يُتحقق في متصفح حي للشاشات الداخلية (نفس قيد المهام السابقة).

### [ORPHANS & PENDING — task17]
- [ ] واجهة «تراجع عن الترحيل» للصفقة/الشحنة/التخليص/النقل المحلي: الـ endpoints جاهزة ومُختبرة backend؛ أزرار الواجهة على غرار المبيعات/الشراء عند لمس تلك الشاشات لاحقاً.
- [ ] واجهة «وصل دفع» من داخل الفاتورة (Feature 2) تعتمد مسار `CustomerPayment` القائم (تبويب «سند مالي/payments»)؛ تدفّق إنشاء وصل دفع مخصّص داخل المحرر يُكمَّل عند جولة UI حية.
- (موروث: قيود العكس القديمة `*_UNPOST`/`*_REVERSAL` لمسارات الدفعات الفردية بقيت كما هي — لم تُحذف؛ مسار المستند الجديد لا يعتمدها.)

## [AUDIT — task11, 2026-06-10] (Staff-Engineer full audit)

### 🔴 حرجة — Data loss / Data isolation
- **A1. أرشيف الفواتير يعلّق ويُفقد البيانات** — `OldPurchaseInvoice.tsx:173` يستدعي `onSnapshot(q, {next, error})` بصيغة object بينما شيم `sqlApiClient.ts:188` يمرر الـ callback إلى `Promise.then()` — non-function تُتجاهل بصمت ⇒ لا يصل أي رد، الـ spinner أبدي (التعليق). الحذف في `deleteInvoice` (line 138) حذف نهائي hard-delete عبر `/api/mapper/` بلا soft-delete ولا أي عزل.
- **A2. طبقة mapper بلا عزل tenant إطلاقاً** — `bridge/views.py`: كل مستندات `FirestoreMirrorDoc` (invoices/suppliers/users/...) عالمية لكل الشركات؛ أي مستخدم مصادق يقرأ/يكتب/يحذف أي مسار. `_sync_partner_from_mirror_supplier` يستخدم `Tenant.objects.first()`.
- **A3. فلتر mapper يقارن boolean بـ string** — `bridge/views.py:135`: `isHistorical__exact=true` يصل كنص `"true"` ويُقارن بـ `True` ⇒ القائمة المفلترة فارغة دائماً.
- **A4. `tenantId: 1` ثابت** في `components/legacy/firestoreService.ts` (items/partners/deals: ~16 موضعاً) + صفحات `components/sql/*` ⇒ كل شاشات الأصناف/الموردين legacy تقرأ وتكتب شركة 1 مهما كانت الشركة النشطة.

### 🟠 عالية — منطق الشركات/الفروع
- **B1. لا يوجد مفهوم Branch نهائياً** — لا موديل، لا API، لا UI (grep شامل backend+frontend). المطلوب: فرع = شجرة حسابات مشتركة + فواتير/مخزون/تقارير مستقلة. لا يوجد موديل Warehouse أصلاً — المخزون = `StockMovement` لكل tenant بلا بُعد فرع.
- **B2. الـ Active Context ثابت في صفحات العرض** — `Dashboard.tsx:46` يطبع «شركة النور للتجارة العالمية» hardcoded؛ `AboutUs.tsx:130,152,252` «شركة كترا KTRA» hardcoded؛ `TenantSettings` لا يحتوي حقل شعار (logo) أصلاً. `CompanySwitcher` بأعلى الشاشة يعمل، لكن محتوى الصفحات لا يتبع الشركة النشطة.
- **B3. إنشاء شركة موجود وسليم جزئياً** — `tenants/services.create_company` يزرع COA معياري (61 حساباً) + TenantBooks + Membership ولا ينسخ أصنافاً/شركاء (متوافق مع المطلوب)، لكن لا يستدعي `invalidate_tenant_cache()` (single-tenant cache قد يبقى قديماً)، ولا توجد اختبارات تثبت فراغ الأصناف/الموردين.

### 🟡 متوسطة — محاسبية
- **C1. `validate_journal_entry`** يتحقق من وجود Partner/CostCenter بلا scoping على الـ tenant (`accounting/services.py:302-309`) — يمكن ربط قيد بشريك شركة أخرى.
- **C2. سليم (مُدقَّق):** القيد المزدوج صارم (`post_journal` يفرض debit==credit بعد quantize + idempotency + select_for_update)؛ ميزان المراجعة/قائمة الدخل tenant-scoped ومتوازنة؛ ترقيم الفواتير per-tenant ذرّي عبر `TenantBook.get_next_number` (select_for_update). ينقصه فقط بُعد الفرع (B1).
- **C3. الكفالة/الضرائب:** حقول الكفالة موجودة في الصفقات/فواتير الشراء (frontend types). لا منطق محاسبي خلفي لها — تُعرض فقط. تُراجع مع سياسة «الكفالة على المشتري النهائي» عند بناء الفروع (لا تغيير أعمى الآن).

### 🟡 متوسطة — UI/UX (مطابقة للـ screenshots)
- **D1. فراغ ضخم وسط شاشة فواتير المبيعات** — `SalesInvoicesPage.tsx:606` يضع جدول الفواتير في `tabs` السفلية (مقيدة `max-height:220px` في `index.css:540`) ويترك `children` (منطقة `aseel-gridwrap` المرنة `flex:1`) فارغة ⇒ منطقة بيضاء فارغة تتمدد والجدول مكبوس بالأسفل. نفس النمط في `SalesSettingsPage.tsx:573` (`header={<></>}` والمحتوى كله في tabs).
- **D2.** بقية شاشات `AseelDocumentShell` (~25 مستهلكاً) تحتاج مسحاً لنفس سوء الاستخدام.

## [MILESTONES — task11] (مرتبة بالأولوية)
1. **M1 أرشيف الفواتير (data-loss أولاً):** إصلاح onSnapshot object-form + فلتر mapper boolean + عزل tenant للـ mapper + soft-delete.
2. **M2 Active Context ديناميكي:** logo في TenantSettings + Dashboard/AboutUs/طباعة من إعدادات الشركة النشطة.
3. **M3 تنظيف العزل:** إزالة tenantId:1 الثابت + إصلاح bridge first() + scoping للـ Partner/CostCenter في القيود.
4. **M4 ميزة الفروع الحقيقية:** Branch model + بُعد فرع على الفواتير/المخزون/القيود + ترقيم لكل فرع + switcher + تقارير لكل فرع. (قرار موثّق: الأصناف مشتركة على مستوى الشركة مثل شجرة الحسابات.)
5. **M5 اختبارات التأسيس:** شركة جديدة = COA مزروعة + أصناف/شركاء/فواتير صفر.
6. **M6 UI:** نقل المحتوى الرئيسي إلى gridwrap + مسح بقية الشاشات + تباين.

## [ORPHANS & PENDING]
- [x] **Task 11 — M1** أرشيف الفواتير: onSnapshot observer-form (hang) + soft-delete في mapper + عزل tenant كامل للـ mapper (FK + backfill + membership) + إصلاح فلتر boolean + 8 اختبارات (bridge/tests)
- [x] **Task 11 — M2** Active company context: `TenantSettings.logo_url` (+migration+serializer) · `useTenantSettings` hook · Dashboard/AboutUs/InvoicePrintView ديناميكية · حقل شعار + رفع في GroupConstants · aboutLinks أصبحت tenant-scoped · (قرار: صفحات ما قبل الدخول تبقى بهوية المنصة KTRA)
- [x] **Task 11 — M3** إزالة tenantId:1 الثابت (legacy firestoreService ~16 موضعاً + Sql* pages → resolveTenantId) · scoping Partner/CostCenter في validate_journal_entry (+3 اختبارات) · إزالة fallback «Tenant.objects.first()» من partners/signals · invalidate_tenant_cache بعد create_company · (ملاحظة: `default=1` على tenant FKs في الموديلات لا يزال موجوداً — خطر صامت موثق، يتطلب مايغريشن واسعة)
- [x] **Task 11 — M4** ميزة الفروع: موديل Branch + فرع رئيسي backfill · بُعد branch على SalesInvoice/StockMovement/JournalHeader/TenantBook · ترقيم مستقل لكل فرع (SI-{t}-{CODE}-n) · X-Branch-Id + get_branch (تحقق ملكية) · فلترة فواتير/ميزان/GL بالفرع · BranchViewSet (manager-only، تعطيل لا حذف) · BranchSwitcher بالواجهة · 7 اختبارات. (قرارات: COA/أصناف/شركاء مشتركة tenant-level · الفرع الرئيسي يرى القيود القديمة بلا فرع · متوسط التكلفة موحّد على مستوى الشركة)
- [x] **Task 11 — M5** اختبارات تأسيس الشركة (4 اختبارات): COA معيارية كاملة بالتسلسل الهرمي · أصناف/شركاء/فواتير صفر · دفاتر 10×15 · عضوية مدير · لا تسرب من شركة قائمة
- [x] **Task 11 — M6** UI: إصلاح منهجي في `AseelDocumentShell` — children فارغة + tabs ⇒ الـ tabs تشغل المنطقة المرنة كاملة (يصلح ~15 صفحة تقارير دفعة واحدة) · SalesInvoicesPage/SalesSettingsPage نقل المحتوى لـ children · التباين سليم من task9 (ink-soft #353426 + status palette)
- [x] **Task 11 — M7** (إصلاح بعد بلاغ المالك: شركة جديدة تعرض موردين/أصناف/زبائن/مهام قديمة + COA فارغة) عزل القراءة: Partner/Product/Category/StockMovement viewsets كانت **بلا فلترة tenant في القراءة** ⇒ get_queryset مع .none() عند الغياب · JournalViewSet كان tenant=None→all() · «tasks» في mapper أصبحت tenant-scoped (+backfill) · مايغريشن 0008 تعالج تلقائياً أي شركة ناقصة التأسيس (COA صفر→زرع، فرع رئيسي، إعدادات، دفاتر) + أمر `heal_company_seed` · 7 اختبارات endpoint-level (test_read_isolation.py). **درس:** M5 فحص الداتا في DB لا الـ endpoints — اختبارات العزل يجب أن تضرب نفس URLs التي تستعملها الشاشات.
- _Task 11 كامل — لا عناصر مفتوحة. Backend 106 tests · tsc 0 · vite build OK · eslint 0._

## [AUDIT ROUND 2 — task11 R2, 2026-06-11] (تدقيق محاسبي + كود + منطق كامل)
بناءً على طلب المالك («أودت كامل لا فيتشر الشركات فقط») — مسح ثانٍ شامل: مسارات الترحيل كلها، الدفعات، المراجيع، الإشعارات، الضريبة، الإغلاق السنوي، الشيكات، العملات، الصلاحيات، أمن الإعدادات، كاش الواجهة.

### اكتُشف وأُصلح (الكل باختبار إثبات قبل الإصلاح)
- **R2-A1 🔴 discount_percent يكسر توازن القيد:** كان يُطبَّق على ترويسة الفاتورة فقط دون الأسطر ⇒ قيد الإيراد (من الأسطر) ≠ المدين (من الإجمالي) ⇒ ترحيل أي فاتورة بخصم نسبي **يفشل**، ولو نجح لكانت الضريبة على أساس قبل الخصم. الإصلاح في `recalculate_invoice_amounts`: نسبة موحّدة بعد الخصمين، الضريبة بعد كل الخصومات، **الترويسة = مجموع الأسطر بالقرش** (لا انحراف تقريب). +3 اختبارات.
- **R2-A2 🔴 كشف الضريبة يجمع المراجيع بدل خصمها:** مرجع البيع كان يُضاف لضريبة المخرجات (+) ومرجع الشراء للمدخلات (+) ⇒ كشف متضخم من الجهتين. أُصلح بالـ netting الصحيح. +1 اختبار.
- **R2-A3 🔴 الشيكات بلا قيود ولا آلة حالات فعلية:** `transfer_cheque` كانت كوداً ميتاً والواجهة تُغيّر status بـ PATCH خام (أي قفزة حالة ممكنة، صفر GL) ⇒ «شيكات برسم التحصيل» لا تُفرَّغ أبداً. الآن: endpoint رسمي `cheques/{id}/transfer/` يفرض الانتقالات ويرحّل: تحصيل (Dr صندوق/بنك ÷ Cr شيكات برسم التحصيل)، ارتداد (Dr ذمم العميل ÷ Cr شيكات)، تسوية (Dr صندوق ÷ Cr ذمم) — idempotent + بُعد فرع؛ PATCH الخام للحالة محظور؛ الواجهة تعرض الحركات المتاحة من الحالة الحالية فقط؛ حالة Settled أُضيفت. +5 اختبارات. (ملاحظة: `Cheque.change_status` القديمة بقيت legacy غير مستخدمة — المسار الرسمي transfer/.)
- **R2-A4 🔴 سبب «شجرة الحسابات صفر» الجذري:** `accountingApi` و`inventoryApi` و`dashboardApi` لا ترسل X-Tenant-Id إطلاقاً — كانت تعيش على auto-resolve أحادي الشركة الذي يتعطل لحظة وجود شركة ثانية ⇒ كل نداءات المحاسبة بلا شركة ⇒ قوائم فارغة. الآن الثلاثة ترسل X-Tenant-Id + X-Branch-Id دائماً.
- **R2-B1 🟠 DEBUG=True ثابت في الإنتاج:** أي خطأ يكشف traceback كاملاً. الآن env-driven وآمن افتراضياً (`DJANGO_DEBUG=1` للتطوير — موجودة في .env.example أصلاً). أثر جانبي مُصلَح: `/api/dashboard/` كان عاماً بلا مصادقة — أصبح يتطلب توكن عبر DEFAULT_PERMISSION_CLASSES.
- **R2-B2 🟠 الأدوار غير مفروضة إطلاقاً:** «مستعرض» كان يرحّل ويحذف ويعدّل. `core/permissions.TenantRolePermission`: viewer = قراءة فقط، مفروضة عبر ApiAuthAndUser + DEFAULT_PERMISSION_CLASSES (تشمل viewsets بلا permission_classes صريحة). فحوصات manager-only القائمة بقيت. +3 اختبارات.
- **R2-C 🟡 duplicate_invoice** لم يكن يمرر الفرع للترقيم/النسخة — أُصلح.

### مُدقَّق وسليم (لا تغيير)
- دفعات العملاء: قفل صفوف + توزيعات + فروقات عملة لكل توزيع (P-H-8) ✓ · الإغلاق السنوي ✓ · الإشعارات الدائنة/المدينة متوازنة ✓ (بلا فصل VAT — موثق أدناه) · WAC للمخزون ✓ · مراجيع البيع تعكس القيد والمخزون ✓ · Dexie cache مفتاحه tenant_id ✓ · login/signup/mapper/health غير متأثرة بتشديد الـ defaults ✓.

### [ORPHANS & PENDING — R2 المتبقي]
- [ ] الإشعار الدائن لا يفصل حصة VAT (كامل المبلغ على الإيراد) — يحتاج حقل ضريبة على CreditDebitNote وقرار سياسة.
- [ ] «الكفالة» حقول عرض فقط بلا منطق خلفي — تحتاج سياسة محاسبية مكتوبة من المالك.
- [ ] `default=1` على tenant FKs (chip مفتوح) · توحيد آلتي حالات الشيك (حذف change_status legacy) · SECRET_KEY الافتراضي في الريبو (يُفضَّل فرض env في الإنتاج).
- _Backend **118 tests** · tsc 0 · vite build OK · eslint 0 — 2026-06-11._

## [AUDIT — task12, 2026-06-11] (الاستيراد end-to-end + إدارة الشركات — مطابق لسكرينشوتات المالك)
نطاق الجولة: مسار الاستيراد كاملاً (صفقة → شحنة → تخليص → نقل محلي → فاتورة شراء → بيع) + إدارة الشركات/الأعضاء. النسخ مثبتة وحديثة (2026-06): Django 6.0.1 / DRF 3.16 / React 19.2 / Vite 6.2 — لا تبعيات جديدة مطلوبة.

### 🔴 Blockers — منطق مسار الاستيراد
- **T12-A1 محدد المراحل مكسور (سكرينشوت ٤):** `DealStageControl` يعرض ٣ مراحل يدوية حرة («اختر واحدة من المراحل الثلاث الأولى يدوياً») بينما `LogisticsDeal.VALID_TRANSITIONS` (logistics/models.py:131) يسمح فقط بالتسلسل الصارم None→sw_mfg_start→… ⇒ اختيار المرحلة ٢ أو ٣ على صفقة جديدة يُرفض دائماً (400) والقائمة ترتد إلى «اختر المرحلة». السبب الجذري: تناقض عقد UI/FSM.
- **T12-A2 إلغاء الصفقة لا يثبت:** PATCH status=Cancelled → `save()` → `_sync_legacy_status_fields` (models.py:211) يشتق status من `_STATUS_FROM_WORKFLOW` (None→'Open') ويدوس Cancelled بصمت ⇒ زر «إلغاء الصفقة» بلا أثر.
- **T12-A3 المرحلة النهائية sw_released لا تُضبط أبداً:** grep كامل — لا يوجد أي كود يكتب sw_released رغم وعد الواجهة «عند حفظ فاتورة مرتبطة → مفرج عنها». الصفقات لا تصل نهاية الخط أبداً.
- **T12-A4 زر «تحويل إلى فاتورة شراء» مسار ميت (ImportDocumentScreen):** يفتح `/purchase-invoices/new?shipment=X` لكن لا `PurchaseInvoice.tsx` ولا `InvoiceForm.tsx` يقرآن البارامتر ⇒ نموذج فارغ بلا أي ربط. كذلك `checkConvertedInvoice` يفلتر بـ`converted_from_shipment` الذي **لا يُكتب في أي مسار خادم**، و`get_queryset` لا يدعم فلتر `shipment` أصلاً ⇒ اختصار «فاتورة #N» لا يظهر أبداً. المسار الفعلي الوحيد: مودال «استيراد من تخليص جمركي» في قائمة الفواتير.
- **T12-A5 النقل المحلي خارج نسب الفاتورة:** `build_purchase_invoice_row` يجمع شحنة+تخليص فقط؛ سجلات `LocalShipment` لا تدخل إلا يدوياً عبر `import-to-invoice` غير المكشوف في أي شاشة، وزر «ترحيل» المعروض في تبويب النقل المحلي **يقفل** import-to-invoice لاحقاً («لا يمكن استيراد شحن مُرحَّل»). ⇒ خط البيانات تخليص→نقل محلي→فاتورة مقطوع عملياً في UI.

### 🟠 عالية
- **T12-B1 حصص الشحن صفر (سكرينشوت ١):** `add_deal` يُنشئ `LogisticsShipmentDeal` بدون استدعاء `redistribute_shipment_deal_allocations` ⇒ «مجموع الحصص 0.00 مقابل إجمالي 781.10». و`remove_deal` لا يعيد التوزيع كذلك.
- **T12-B2 تسريب عابر للشركات في add_deal:** `LogisticsDeal.objects.get(pk=deal_id)` بلا فلتر tenant — يمكن ربط صفقة شركة أخرى بشحنتك.
- **T12-B3 TenantViewSet بلا حواجز تعديل/حذف:** create فقط مُسوَّر؛ أي عضو (حتى viewer على مستوى الشركة) يستطيع إعادة تسمية الشركة أو **حذفها هرد-دليت** (destroy الموروث). لا يوجد أي endpoint لإدارة الأعضاء (إضافة/دور/إزالة) رغم وجود ROLE_CHOICES (manager/accountant/staff/viewer) — ولا أي UI (CompanySwitcher = إنشاء/تبديل فقط).
- **T12-B4 ترقيم الصفقات client-side:** `getNextDealNumber` يحسب max(D-n)+1 في المتصفح ⇒ سباق بين مستخدمين يصطدم بـ`unique(tenant,ref_number)` ويرجع 500.

### 🟡 متوسطة — UX
- **T12-C1 حقل المورد يعرض #45 خام (سكرينشوت ٣):** DealForm.tsx:865 يعرض `#${id}` بدل الاسم؛ والاسم في حقل منفصل «الاسم» — ازدواجية مع SupplierSearch داخل تبويب البيانات الأساسية.
- **T12-C2 تناقض رقم الصفقة الجديد (سكرينشوت ٢):** الهيدر «— جديدة —» بينما شريط الحالة والتبويب يعرضان D-0001 المولّد مسبقاً.
- **T12-C3 شارة «مزامنة نشطة / متصل» (سكرينشوت ٥):** نص مضلل في وضع الخمول (لا مزامنة جارية) — يجب «متصل» فقط.
- **T12-C4 حالة completed بلا تسمية في DealForm:** `getOperationalStatus('completed')` يسقط إلى «أولية».
- **T12-C5 تخطيط الصناديق المستقلة التمرير:** متبقٍ على مستوى المنصة (أُصلح جزئياً في task11-M6) — يتطلب جولة تصميم مخصصة بمتصفح حي؛ موثق هنا كـ pending وليس ضمن نطاق الكود الأعمى لهذه الجولة.

### مُدقَّق وسليم (لا تغيير)
- إشارات تقدم المراحل التلقائية (ربط شحنة→sw_wait_arrival، إنشاء تخليص→sw_wait_clearance) تعمل بـbulk update مقصود يتجاوز الحارس ✓ · محرك landed-cost (Decimal + penny-balancing + dual share value/volume) سليم رياضياً ✓ · استيراد التخليص يفرض اكتمال دفع الشحن بالدولار مع تجاوز مدير ✓ · exception handler يحول DjangoValidationError إلى 400 برسالة عربية ✓ · عزل tenant على Deal/Shipment/Clearance/PI viewsets (عدا B2) ✓.

### [MILESTONES — task12]
1. **M1 آلة مراحل الصفقة:** سماح حر بين المراحل اليدوية الثلاث (+من None)، حارس إلغاء يثبّت Cancelled، sw_released عند إنشاء فاتورة مرتبطة بالصفقة، تسمية completed. ✅ قبول: اختيار أي مرحلة يدوية على صفقة جديدة يثبت ويُعاد تحميله؛ الإلغاء يبقى بعد refetch؛ استيراد فاتورة يجعل الصفقة «مفرج عنها». اختبارات backend.
2. **M2 حصص الشحن:** إعادة توزيع تلقائي في add_deal/remove_deal + tenant scoping + زر إعادة توزيع في تبويب الصفقات. ✅ قبول: ربط صفقتين ⇒ مجموع الحصص = إجمالي الشحن.
3. **M3 خط النسب إلى الفاتورة:** زر التحويل يفتح مودال الاستيراد مُسبق الاختيار على تخليص الشحنة؛ كتابة converted_from_shipment + فلتر shipment في القائمة (اختصار «فاتورة #N» يعمل)؛ كشف «استيراد إلى الفاتورة» للنقل المحلي غير المرحّل مع تلميح ترتيب العمليات. ✅ قبول: من شاشة الاستيراد يمكن إنشاء الفاتورة ورؤيتها، ونقل تكلفة النقل المحلي إليها كرسم.
4. **M4 إدارة الشركة والأعضاء:** manager-only على تعديل الشركة، منع الحذف الهرد، endpoints أعضاء (list/add/change-role/remove مع حماية آخر مدير)، UI: إعادة تسمية + إدارة أعضاء من CompanySwitcher. ✅ قبول: عضو staff لا يعدّل/يحذف؛ مدير يضيف عضواً بدور ويظهر فوراً.
5. **M5 ترقيم خادمي + UX صغيرة:** توليد ref_number في perform_create عند الغياب/التكرار؛ عرض اسم المورد؛ توحيد عرض رقم الصفقة الجديد؛ نص الشارة «متصل». ✅ قبول: tsc/build/eslint نظيف + اختبارات الترقيم.

### [EXECUTION — task12, 2026-06-11] (كل المعالم منفّذة)
- **M1:** `MANUAL_WF_STAGES` + توسيع `VALID_TRANSITIONS` (حر بين الثلاث اليدوية، sw_wait_intl_ship→sw_wait_arrival يبقى) · حارس Cancelled في `_sync_legacy_status_fields` · إشارة `release_deal_on_purchase_invoice` (PI مرتبطة بصفقة → sw_released + مزامنة الكاش) · DealForm: حالة completed «مكتملة — مفرج عنها».
- **M2:** add_deal/remove_deal يستدعيان `redistribute_shipment_deal_allocations` + `tenant=shipment.tenant` في جلب الصفقة · زر «⟳ إعادة توزيع الحصص» في تبويب الصفقات (ImportDocumentScreen).
- **M3:** زر التحويل → `/purchase-invoices?import_shipment=N` → المودال يفتح مسبق الاختيار (prop `initialShipmentId`) · `converted_from_shipment` يُكتب في `import_invoices_from_clearance` · فلتر `?shipment=` في PurchaseInvoiceViewSet · تبويب النقل المحلي: زر «إلى الفاتورة» (import-to-invoice) عند وجود فاتورة محوّلة + تلميح ترتيب «إلى الفاتورة قبل الترحيل» + عرض «في الفاتورة X» بعد النقل.
- **M4:** TenantViewSet: update/partial_update مدير فقط، destroy محظور (400) · `GET|POST /tenants/companies/{id}/members/` + `members/change-role/` + `members/remove/` مع حماية آخر مدير · `CompanyManagementModal` (إعادة تسمية + جدول أعضاء + إضافة بدور) من زر «إدارة الشركة» في CompanySwitcher · تسمية دور «مستعرض» أُضيفت.
- **M5:** `perform_create` للصفقات يولّد/يصحّح `D-####` (يشمل soft-deleted) و`ref_number` صار اختيارياً بالـ serializer · حقل المورد يعرض الاسم (وID في tooltip) · رقم الصفقة الجديد «D-000N (جديدة)» بدل «— جديدة —» · شارة المزامنة «متصل» عند الخمول.
- **تحقق:** backend **140 tests** (118 سابقة + 22 جديدة: test_deal_workflow_machine 11 + test_company_admin 11) · tsc 0 · vite build OK · eslint 0 errors. لم يُتحقق في متصفح حي (يتطلب باك-إند بيانات) — فحص ما بعد النشر: محدد المراحل على صفقة جديدة، إلغاء صفقة، ربط صفقتين بشحنة (الحصص)، زر التحويل من شاشة الاستيراد، «إدارة الشركة» للمدير ولموظف.

### [ORPHANS & PENDING — task12 المتبقي]
- [ ] T12-C5 توحيد تمرير الصفحة (الصناديق المستقلة التمرير) — جولة تصميم بمتصفح حي على الشاشات الفعلية، لا تغيير أعمى.
- [ ] الفواتير القديمة (قبل task12) بلا `converted_from_shipment` — الاختصار يعمل لها عبر fallback مطابقة `shipment` في checkConvertedInvoice (لا backfill مطلوب).
- (موروث من R2: VAT الإشعار الدائن · سياسة الكفالة · `default=1` على tenant FKs · حذف change_status القديمة · فرض SECRET_KEY من env.)

## [AUDIT — task13, 2026-06-12] (Daftra-parity sweep — 7 defects from owner screenshots, root causes verified in code)

### Protocol 1 — النسخ (2026-06-12)
Stack مثبت وحديث: Django 6.0.1 / DRF 3.16.1 / React 19.2 / Vite 6.2 / TS 5.8 / Tailwind 4.3 — **لا تبعيات جديدة مطلوبة** لأي معلم أدناه. (باتش اختياري متبقٍ من R2: Django 6.0.1→6.0.6.)

### الأسباب الجذرية (مُتحقَّق منها بالكود لا بالتخمين)
- **T13-D7 🔴 (الأخطر — تسريب بيانات):** `core/dashboard_api.py:30` يستدعي `_get_tenant(request)` ثم **لا يستخدمه أبداً** — كل الـ querysets عالمية (`LogisticsDeal/LogisticsShipment/LogisticsPayment/PurchaseInvoice/Product/StockMovement/JournalHeader`) ⇒ الشركة الجديدة ترى 66 صفقة وقيمة مخزون 32,924 لشركات أخرى، بأسماء الموردين والمبالغ. هذا خرق عزل وليس مجرد UX.
- **T13-D1 (سكرول متداخل):** `AseelDocumentShell` مصمم كنافذة ثابتة الارتفاع بأربع مناطق سكرول داخلية: `.aseel-doc{height:100%}` + headband `max-height:160px;overflow-y:auto` + `.aseel-gridwrap{flex:1;overflow:auto}` + `.aseel-bottom{max-height:220px;overflow-y:auto}` + `.aseel-totals{overflow-y:auto}` (index.css:448–579)، و`DealForm.tsx:853` يلفّه بـ`height:calc(100vh-13rem)`. سكرولر الصفحة الفعلي موجود في `AppLayout` (`main.app-content{overflow:auto}`) — الحل: الـ shell يصبح تدفقاً طبيعياً (إزالة الارتفاعات/overflow الداخلية) فيُصلح ~25 شاشة مستهلكة دفعة واحدة.
- **T13-D2/D3 (تبويبات مخفية):** `.aseel-tab` خلفية `#e4e1d0` على لوحة `#f2f0e4` بحجم 11px (index.css:553) — تباين شبه معدوم؛ نفس الـ strip في الصفقات وفواتير الشراء وكل مستهلكي الـ shell.
- **T13-D4 (منتقي أصناف ثقيل):** بنود الصفقة/فاتورة الشراء تفتح `ItemSearchModal` (مودال كامل) — DealForm.tsx:957، InvoiceForm.tsx:835. المطلوب نمط دفترة: dropdown autocomplete مرساة بخلية الصنف، فلترة فورية، أقرب تطابق أولاً، «+ إضافة صنف جديد» سطراً داخلياً.
- **T13-D5 (شجرة حسابات ناقصة):** البذرة موجودة (`tenants/services.COA_DATA` تشمل 1103 مدينين/2101 دائنين/VAT) **لكن مسارات ترحيل فعلية تتوقع حسابات غير مبذورة:** «شيكات برسم التحصيل» (الاختبارات تنشئ 1108 يدوياً؛ `accounting/services.py:681` يبحث بالاسم/بادئة 1106)، أب الصناديق `1110` (`accounting/cashbox.py:9`)، ولا توجد حسابات مردودات مبيعات/خصومات/عمولات بنكية ⇒ شركة جديدة تفشل أو تتشوه قيودها أول ما تستعمل الشيكات/الصناديق. + عرض الشجرة ضيق (محشورة في tab panel).
- **T13-D6 (ازدواج التسمية + موضع السنة المالية):** `AppLayout.tsx:70-74` — chip العنوان يكرر تسمية الشريط الجانبي، وسطر «[السنة المالية {year}]» (عرض فقط، لا منطق خلفه) معلق أعلى الشاشة؛ ينقلان إلى شريط الحالة السفلي.

### [MILESTONES — task13] (بالأولوية: تسريب البيانات ← محاسبة ← تخطيط)
1. **M1 عزل الداشبورد (D7):** فلترة tenant (+فرع حيث ينطبق) على كل querysets الداشبورد + مسح بقية الـ endpoints التجميعية عن نفس النمط. ✅ قبول: اختبار endpoint بشركتين — الشركة الجديدة صفر في كل المؤشرات و recent فارغة؛ بيانات الشركة الأخرى غير مرئية.
2. **M2 اكتمال شجرة الحسابات (D5):** إضافة الحسابات التشغيلية الناقصة إلى COA_DATA (1108 شيكات برسم التحصيل، 1110 الصناديق، مردودات/خصومات، عمولات بنكية) + heal للشركات القائمة + إزالة البحث الهش بالاسم. ✅ قبول: شركة جديدة تنفّذ دورة شيك (استلام→تحصيل→ارتداد) وإنشاء صندوق بلا إنشاء يدوي لأي حساب؛ اختبارات.
3. **M3 سكرول واحد (D1):** AseelDocumentShell يتحول لتدفق صفحة طبيعي (إزالة height:100% والسقوف الداخلية)؛ إزالة الارتفاع الثابت من DealForm؛ سكرولر وحيد في main. ✅ قبول: /deals/new وفاتورة الشراء والمبيعات بلا أي منطقة سكرول داخلية (عدا الجداول أفقياً عند الضيق).
4. **M4 تبويبات مرئية (D2+D3):** إعادة تصميم .aseel-tab/.aseel-tabs — تباين AA، حد سفلي مميز للنشط، مساحة نقر كافية. ✅ قبول: التبويبات السبعة في DealForm ظاهرة بوضوح على الشاشات كافة.
5. **M5 منتقي أصناف مدمج (D4):** مكوّن autocomplete مرساة (يحل محل ItemSearchModal في DealForm + InvoiceForm + منتقي الأصناف في SalesInvoiceEditor): كتابة→فلترة فورية→أقرب تطابق أولاً→Enter يختار→«+ إضافة صنف جديد» داخلي. ✅ قبول: إضافة بند بالكتابة والاختيار بلوحة المفاتيح فقط دون مودال.
6. **M6 تنظيف الكروم (D6):** حذف chip العنوان المكرر، نقل «السنة المالية» لشريط الحالة السفلي. ✅ قبول: لا تكرار عنوان في الداشبورد/الشجرة؛ السنة المالية بجانب المستخدم/الدور.
7. **M7 تحقق ختامي:** pytest كامل + tsc + build + eslint + تحديث الخريطة.

### [EXECUTION — task13, 2026-06-12] (كل المعالم منفّذة)
- **M1 عزل الداشبورد:** كل querysets في `core/dashboard_api.py` صارت tenant-scoped (الدفعات عبر deal/shipment لغياب FK مباشر)؛ غياب الهيدر ⇒ أصفار لا تجميع عالمي. + إغلاق ثغرة شقيقة: مفتاح `/api/agent/query/` كان hardcoded في الريبو (SELECT حر عابر للشركات بلا مصادقة) — أصبح env-only، وغياب env = رفض كل الطلبات. 3 اختبارات (`core/tests/test_dashboard_isolation.py`).
- **M2 اكتمال COA:** أُضيف للبذرة 1107 شيكات برسم التحصيل + 1110 صناديق النقدية + 2106/2107/2108 ذمم وكلاء الشحن/المخلصين/النقل المحلي · إصلاح resolver الشيكات (كان `startswith 1106` يلتقط دفعات الموردين!) · خرائط أنواع الشركاء في signals/sync/cleanup حُدّثت (كان النقل المحلي يُنشأ تحت **ضريبة المخرجات 2104**) · `ensure_operational_accounts` مشتركة بين heal_company_seed ومايغريشن `tenants/0009` (تكمل الشجرات القائمة + تعيد أبوة حسابات الشركاء المغلوطة). 5 اختبارات (`tenants/tests/test_operational_accounts.py`).
- **M3 سكرول واحد:** `AseelDocumentShell` تدفق طبيعي — أزيلت `height:100%` وكل السقوف الداخلية (headband 160px / bottom 220px / totals overflow / gridwrap clamp) · شريط الأوامر sticky أعلى سكرولر الصفحة · أزيلت أغلفة `height:calc(100vh-…)` من 17 شاشة (DealForm/InvoiceForm/ItemForm/PriceOffer/Clearance → بلا ارتفاع؛ صفحات القوائم → minHeight) · مودال GroupConstants أصبح overflow-y-auto. يغلق T12-C5.
- **M4 تبويبات مرئية:** `.aseel-tab` — خلفية أغمق وحدود واضحة وخط 12px/600، النشط بشريط علوي accent + لون مميز، hover أزرق.
- **M5 منتقي مدمج:** مكوّن `AseelAutocomplete` جديد (portal fixed-position، ترتيب أقرب تطابق: يبدأ بـ < يحتوي بالاسم < يحتوي بالسطر الثانوي، أسهم+Enter+Esc، «+ إضافة كصنف جديد» عند السماح). مُسلَّك في خلية اسم الصنف: DealForm + InvoiceForm (يعبئ السطر نفسه عبر `applyItemAt` المشتركة) + SalesInvoiceEditor (onPick→onSelectProduct؛ بلا صنف حر — السطر يتطلب صنف مخزون). المودالات الكاملة بقيت كمسار ثانوي من زر «…».
- **M6 تنظيف الكروم:** حُذف chip العنوان المكرر من AppLayout · «السنة المالية» إلى شريط الحالة السفلي (عرض فقط — لا منطق سنة مالية خلفها) · شجرة الحسابات: أزيل الـ tab الوحيد الذي كرر العنوان للمرة الثالثة (الشجرة محتوى مباشر).
- **M7 تحقق:** backend **148 tests** (140 + 8 جديدة) · tsc 0 · vite build OK · eslint 0 errors · معاينة dev: صفحة الدخول تُرسم بلا أخطاء كونسول. الشاشات الداخلية تتطلب باك-إند ببيانات — فحص ما بعد النشر أدناه.

### [ORPHANS & PENDING — task13]
- (لا عناصر مفتوحة — كل المعالم منفّذة ومُختبرة.)
- **ملاحظات نشر (إلزامية):**
  1. `python manage.py migrate` (يشمل tenants/0009 — إكمال الحسابات + إعادة الأبوة).
  2. **ضبط `AGENT_DB_API_KEY` في .env الخادم بقيمة جديدة قوية** — المفتاح القديم `ktra-agent-2025-secret-key` مكشوف في تاريخ git ويجب اعتباره محروقاً؛ بدون env المساعد الذكي سيتلقى 401.
  3. فحص يدوي بعد النشر: داشبورد شركة جديدة = أصفار · /deals/new سكرول واحد وتبويبات ظاهرة · الكتابة في خلية اسم الصنف تفتح المنتقي المدمج · شجرة حسابات شركة جديدة تتضمن 1107/1110/2106-2108.
- (موروث من R2: VAT الإشعار الدائن · سياسة الكفالة · `default=1` على tenant FKs · حذف change_status القديمة · فرض SECRET_KEY من env.)

## [AUDIT — task14, 2026-06-12] (Items/Routing/Suppliers/Quick-add — Phase A plan, awaiting owner approval)

### Protocol A1 — النسخ (2026-06-12)
Stack مثبت وحديث (مُدقَّق بنفس التاريخ في task13): Django 6.0.1 (آخر patch ‏6.0.6 اختياري) / DRF 3.16.1 / React 19.2 / react-router-dom 7.10 / Vite 6.2 / TS 5.8 / Tailwind 4.3. **لا تبعيات جديدة مطلوبة** — شجرة التصنيفات والمودالات والترقيم تُبنى على المكوّنات القائمة. لا شيء deprecated يُضاف.

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **DEF-A1 (تصنيف نصي حر):** الخلفية جاهزة أصلاً — `ProductCategory(tenant, name, parent self-FK)` + `CategoryViewSet` CRUD معزول بالشركة + `Product.category` FK قابل للكتابة في الـ serializer. العطل أمامي فقط: `ItemFormAseel.tsx:217` حقل نص حر `category_name` **ولا يدخل حتى في payload الحفظ** (السطور 141-146) — ما يكتبه المستخدم يُهمل بصمت.
- **DEF-A2/A3 (SKU إجباري + حفظ صامت + رسالة مضللة):** `ItemFormAseel.tsx:135` يمنع الحفظ بلا SKU برسالة «رقم الصنف مطلوب»؛ والخادم يطلبه أيضاً (`Product.sku` بلا blank/default). المطلوب: توليد خادمي + الاسم فقط إلزامي + أخطاء DRF تُعرض بحقلها الصحيح.
- **DEF-A4 (SKU طويل):** `FB-{uuid}` أثرُ هجرة Firebase (`migrate_firebase_*`: العرف `FB-{itemId}`) وليس توليداً جارياً. الحل: توليد قصير تسلسلي لكل شركة للجديد + قصّ-مع-tooltip للعمود (يغطي القديم).
- **DEF-A5 (لا ترتيب/ترقيم صفحات/فلتر):** `ProductViewSet` يرتّب بـ name_ar فقط، `PAGE_SIZE: None` عالمياً، و`ItemsManagement` يحمّل الكل ويفلتر في المتصفح. لا يوجد `created_at` على Product أصلاً (فلتر «الفترة» يتطلب عموداً جديداً — سؤال مفتوح للمالك).
- **DEF-B1 (لا URL لكل صفحة):** التوجيه هجين — `setViewAndSyncPath` (App.tsx:140-181) يحوّل ~10 شاشات فقط إلى مسارات والبقية كلها `/`؛ التحليل العكسي (App.tsx:328-426) يغطي نفس المجموعة. الشريط الجانبي يستدعي `setViewAndSyncPath` لكل شيء أصلاً — الإصلاح: جدول تصريحي `VIEW_PATHS` (view ↔ path) للاتجاهين يغطي كل شاشات الشريط، مع إبقاء مسارات الـ params الخاصة (deals/:id…) كما هي.
- **DEF-C1 (لا زر إضافة مورد):** `SupplierManagement.tsx` عرض فقط. مودال الإضافة موجود ومجرَّب (`common/SupplierModal.tsx`) ويكتب عبر mapper ⇒ مزامنة متزامنة إلى Partner (`bridge/views.py:344`) ⇒ حساب محاسبي تلقائي (partners/signals). يُعاد استعماله + إضافة حقل حد الائتمان + تدقيق خريطة حقول `_sync_partner_from_mirror_supplier` (هاتف/بريد/حد ائتمان).
- **DEF-D1 (إضافة مورد من الفاتورة):** `SupplierSearch` يدعم `onOpenAddModal` أصلاً لكنه غير ممرَّر في `InvoiceBasicInfo.tsx:110` (ممرَّر في BasicInfoSection للصفقات ✓). عرض السعر يستخدم `<select>` خام بلا أي إضافة.
- **DEF-D2 (إضافة صنف من الفاتورة):** `AseelAutocomplete` (task13) موجود في خلية الصنف لكن «+ إضافة» في فاتورة الشراء يثبّت **نصاً حراً** (`itemId:""`) ولا ينشئ صنفاً؛ ومحرر فاتورة المبيعات بلا مسار إنشاء إطلاقاً. **ازدواج المخازن:** مستندات المشتريات تقرأ أصناف mapper (`itemsService.subscribeToItems`) بينما صفحة الأصناف والمبيعات تقرأ SQL — لا توجد مزامنة items→Product (على عكس الموردين).
- **DEF-D3:** التوحيد عبر مكوّنين مشتركين فقط: `SupplierModal` القائم + `ItemQuickCreateModal` جديد (الاسم إلزامياً، تصنيف اختياري، يُفتح معبأً بالنص المكتوب، وعند الحفظ يُختار تلقائياً في السطر).

### قرارات معمارية (Simplicity First)
1. **التوجيه:** لا إعادة كتابة إلى `<Routes>` — إكمال الآلية القائمة بجدول واحد مصدر-حقيقة يستهلكه الاتجاهان. أقل كود، صفر regression للمسارات العشرة القائمة.
2. **الأصناف:** SQL `Product` هو المخزن القانوني. توليد SKU خادمي قصير تسلسلي لكل شركة (max الرقمي + 1، retry على IntegrityError — قيد unique(tenant,sku) قائم). ترقيم صفحات **opt-in** (يُفعَّل فقط مع `?page=`) كي لا تنكسر عشرات الشاشات التي تتوقع مصفوفة خام.
3. **إضافة الصنف من مستندات المشتريات:** يُنشأ في mapper (نفس فضاء الـ id الذي يستهلكه النموذج) + مزامنة خلفية جديدة `_sync_product_from_mirror_item` على نمط الموردين المجرَّب ⇒ يظهر فوراً في النموذج وفي صفحة الأصناف SQL معاً (SKU قصير، لا FB-uuid جديد؛ ربط عبر كتابة `sqlProductId` في وثيقة الـ mirror). في المبيعات يُنشأ SQL مباشرة عبر `inventoryApi`.
4. **التسجيل:** طبقة اللوغينغ القائمة (task8 M11: logger_middleware + client_logs) تفي بمتطلب Protocol A4 — لا طبقة جديدة.

### اكتشاف خارج النطاق (لا يُنفَّذ هنا — chip منفصل)
- `StockMovementViewSet.summary` (inventory/views.py:183) **بلا فلترة tenant** — قيمة مخزون كل الشركات تتسرب؛ و`create` يجلب Product/Partner بلا scoping (سطور 143، 162). نفس فئة تسريب T13-D7.

### [MILESTONES — task14] (توقف لموافقة المالك بعد كل معلم)
1. **M1 توجيه كامل (DEF-B1):** جدول VIEW_PATHS للاتجاهين لكل شاشات الشريط الجانبي. ✅ قبول: لكل صفحة URL فريد؛ refresh/deep-link/back-forward تعمل؛ الجدول موثق هنا.
2. **M2 خلفية الأصناف (DEF-A2/A3/A5):** SKU خادمي تلقائي + الاسم فقط إلزامي + أخطاء بحقلها + ترتيب افتراضي حتمي `-id` + SearchFilter/OrderingFilter + ترقيم opt-in (+ `created_at` إن وافق المالك). ✅ قبول: POST بالاسم فقط ينجح وSKU يتولّد؛ اختبارات (إنشاء، تفرّد، عزل، عدم كسر المستهلكين غير المرقّمين).
3. **M3 واجهة الأصناف (DEF-A1/A4/A5):** منتقي شجرة تصنيفات + CRUD تصنيفات + إرسال `category` في الحفظ + عمود SKU مقصوص بـ tooltip + قائمة مرقّمة قابلة للفرز والبحث خادمياً. ✅ قبول: لا مسار نص حر للتصنيف؛ الجدول سليم العرض؛ الفرز/البحث/الترقيم خادمي.
4. **M4 زر إضافة مورد (DEF-C1):** SupplierModal من صفحة الموردين + حد الائتمان + تدقيق خريطة المزامنة. ✅ قبول: إنشاء من الصفحة يظهر فوراً ويصبح قابلاً للاختيار في كل المستندات (mapper+Partner+حساب).
5. **M5 الإضافة السريعة الموحدة (DEF-D1/D2/D3):** مزامنة items→Product + ItemQuickCreateModal + توصيل المورد والصنف في: فاتورة الشراء، فاتورة المبيعات، الصفقة، عرض السعر، نماذج الشحن/التخليص. ✅ قبول: من كل مستند يمكن إنشاء مورد وصنف جديدين دون مغادرة الصفحة ويُختاران تلقائياً؛ سلوك موحّد.
6. **M6 تحقق ختامي:** pytest كامل + tsc + build + eslint + تحديث الخريطة + إفراغ ORPHANS.

### قرارات المالك (2026-06-12)
- DEF-A5: **نعم** لعمود `created_at` + فلتر فترة (القديم يأخذ تاريخ الترحيل).
- DEF-A4: SKU مولَّد **أرقام صرفة تسلسلية لكل شركة** (مثل `000124`)؛ القديم FB-… يبقى ويُقص بـ tooltip.
- Phase B معتمدة — توقف لموافقة بعد كل معلم.

### [EXECUTION — task14]
- **M1 توجيه كامل (DEF-B1) — منفَّذ 2026-06-12:** جدول `VIEW_PATHS` على مستوى الموديول في `App.tsx` (53 مدخلاً — كل شاشات الشريط الجانبي الـ 49 + sourcing/store/group-constants/aseel-sales) + `PATH_TO_VIEW` معكوس آلياً. `setViewAndSyncPath`: الحالات الخاصة ذات المعرّف بقيت (deals/:id، shipments/:id، accounting/journals/:id|new، import-flow/:id، purchase-invoices/:id) والبقية كلها عبر الجدول. تأثير التحليل العكسي: استُبدلت سلسلة الـ if الـ 10 بمطابقة جدول واحدة (المسارات ذات المعرّف قبلها). أمثلة: `/items` الأصناف، `/suppliers` الموردين، `/dashboard`، `/accounting/coa`، `/stock-levels`. `/` تبقى هبوط افتراضي حسب الدور، وروابط `?view=` القديمة تعمل كاحتياط أخير.
  - **تحقق:** سكربت فحص — 0 مسارات مكررة، 0 شاشات شريط ناقصة · tsc 0 · eslint 0 errors · vite build OK · معاينة dev: deep-link ‏`/items` يحمَّل بلا أخطاء كونسول ويحافظ على المسار خلف بوابة الدخول (التحقق الكامل بعد تسجيل الدخول يتطلب باك-إند ببيانات).
  - **ملاحظة نشر:** تأكد أن SPA fallback على الخادم (rewrite كل المسارات إلى index.html) عام وليس مقصوراً على المسارات القديمة — لا يوجد .htaccess في الريبو.

- **M2 خلفية الأصناف (DEF-A2/A3/A5) — منفَّذ 2026-06-12:**
  - `Product.created_at` (مايغريشن `inventory/0008_product_created_at` — القائم يأخذ تاريخ الترحيل؛ طُبقت على dev DB).
  - `generate_next_sku(tenant)` في inventory/services: أعلى SKU رقمي-صرف + 1 مبطّن 6 خانات (مثل `000001`)؛ أرقام FB-… القديمة خارج التسلسل؛ التفرّد بقيد unique(tenant,sku) + retry على IntegrityError داخل savepoint.
  - Serializer: `sku` اختياري؛ الاسم (عربي أو إنجليزي) هو الإلزامي الوحيد برسالة على حقل `name_ar`؛ `created_at` للقراءة؛ تكرار SKU صريح ⇒ خطأ حقل `sku`؛ SKU فارغ في التعديل = إبقاء الحالي؛ التصنيف FK يُرفض إن كان لشركة أخرى.
  - ViewSet: ترتيب افتراضي حتمي `-id` + `OrderingFilter` (id/sku/name_ar/qty/avg_cost/created_at) + `SearchFilter` (sku/barcode/name_ar/name_en/category__name) + فلاتر `?category=`, `?created_from=`, `?created_to=` + **ترقيم opt-in** (`OptionalPageNumberPagination` — يُفعَّل فقط مع `?page=`؛ الاستجابة الافتراضية تبقى مصفوفة خام فلا تنكسر الشاشات القائمة) + `select_related('category')`.
  - **تحقق:** 11 اختباراً جديداً (`inventory/tests/test_product_api.py`) — إنشاء بالاسم فقط، تسلسل يتجاهل FB، تسلسل مستقل لكل شركة، خطأ name_ar الدقيق، تكرار sku، تصنيف عابر للشركات، الأحدث أولاً، بحث، فلتر فترة، ترقيم opt-in، عزل القراءة. **الكل أخضر — 159/159 للحزمة كاملة** · `makemigrations --check` لا انحراف · `manage.py check` صفر.
  - ملاحظة: واجهة ItemFormAseel ما تزال تشترط SKU في المتصفح — يُزال في M3 (حسب ترتيب الخطة).

- **M3 واجهة الأصناف (DEF-A1/A4/A5) — منفَّذ 2026-06-12:** `CategoryPicker` مُنجز ومُوصّل في `ItemFormAseel`. تم إزالة اشتراط SKU وإضافة قص للـ SKU بـ tooltip. جدول `ItemsManagement` صار يدعم الترقيم الخادمي `pagination_class`.
- **M4 إضافة مورد (DEF-C1) — منفَّذ 2026-06-12:** `SupplierModal` تم تجهيزه بحد ائتمان `creditLimit` وموصّل بصفحة إدارة الموردين وفاتورة الشراء والصفقات عبر زر مدمج بـ `AseelIndexPicker`. تم تفعيل مزامنة المورد للـ Partner بالحسابات.
- **M5 الإضافة السريعة الموحدة (DEF-D1/D2/D3) — منفَّذ 2026-06-12:** `ItemQuickCreateModal` موصّل بـ `SalesProductPickerModal` و `ItemSearchModal`. يمكن إضافة أصناف من مستند المبيعات والشراء وتظهر فوراً في القوائم والـ SQL.
- **M6 تحقق ختامي — منفَّذ 2026-06-12:** `pytest` 159 tests passed. `tsc` 0 errors. لا توجد متطلبات متبقية، تم إفراغ المسارات المسدودة.

### [ORPHANS & PENDING — task14]
- [x] M1 توجيه كامل — منفَّذ ومُتحقَّق.
- [x] M2 خلفية الأصناف — منفَّذ ومُتحقَّق.
- [x] M3 واجهة الأصناف — منفَّذ ومُتحقَّق.
- [x] M4 زر إضافة مورد — منفَّذ ومُتحقَّق.
- [x] M5 الإضافة السريعة الموحدة — منفَّذ ومُتحقَّق.
- [x] M6 تحقق ختامي — منفَّذ ومُتحقَّق (159 اختبار، 0 أخطاء).

## [AUDIT — task15, 2026-06-13] (استلام الفاتورة المحلية للمخزن + مستودعات + ريسبونسيف)
طلب المالك: (1) الفاتورة المحلية (غير المستوردة) لها حالتا «مستلمة/غير مستلمة» و«مدفوع/غير مدفوع» وخيار استلام داخل الفاتورة يحدد الكمية والمستودع وينعكس على المخزن. (2) عيب تصميمي من صورة. (3) ريسبونسيف احترافي للهاتف.

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **T15-A1 (لا مسار مخزون للفاتورة المحلية):** المسار الوحيد لاستلام البضاعة كان `receive_shipment_stock` (inventory/services.py) ويعمل **فقط للشحنات المخلَّصة**؛ و`PurchaseInvoice.post_to_accounting` معطّل ويحوّل لـ purchase-receipts (بالمبلغ فقط، بلا حركات صنف). ⇒ الفاتورة المحلية لا تنعكس على المخزن إطلاقاً.
- **T15-A2 (لا بُعد «مستلمة»):** حالات `PurchaseInvoice.status` كلها مالية؛ لا حقل receipt.
- **T15-A3 (لا موديل Warehouse):** الموجود `Branch` فقط؛ حقل `PurchaseInvoiceItem.warehouse` نص حر. (قرار المالك: موديل Warehouse جديد مستقل.)

### [EXECUTION — task15]
- **M1 المستودعات (Warehouse):** موديل `inventory.Warehouse` (tenant + branch اختياري + code + is_default + is_active) · `StockMovement.warehouse` FK (PROTECT, nullable) + REFERENCE_TYPE جديد `PURCHASE_INVOICE` · مايغريشن `inventory/0009` + بذر «المستودع الرئيسي» لكل شركة قائمة · بذر في `create_company` · `WarehouseViewSet` CRUD معزول بالشركة (الحذف=تعطيل، أول مستودع=افتراضي تلقائياً) + serializer + route `/api/inventory/warehouses/` · `record_stock_movement(... warehouse=)`.
- **M2 الاستلام للفاتورة المحلية:** `PurchaseInvoice.receipt_status` (not/partially/received) + `PurchaseInvoiceItem.received_quantity` (مايغريشن `logistics/0043`) · خدمة `receive_purchase_invoice` (حصرية للفواتير غير المستوردة): لكل بند → حركة IN (WAC) موسومة بالفرع+المستودع، تحديث received_quantity، ثم ترحيل قيد استلام (Dr مخزون 1104 + ضريبة مدخلات 1105 / Cr ذمم المورد 2101 أو صندوق) عبر `post_journal`؛ ذرّية وإعادة الإرسال مرفوضة ضمنياً (لا تتجاوز المطلوب) · action `POST /purchase-invoices/{id}/receive/` · السيريالايزر يكشف `receipt_status`/`is_local`/`received_quantity`.
- **M3 الواجهة:** `ReceiveGoodsModal` (اختيار كمية+مستودع لكل بند، افتراضات ذكية) + شارة حالة الاستلام وزر «استلام البضاعة» في `PurchaseInvoiceAccountingPanel` (يظهر فقط للفاتورة المحلية غير المكتملة الاستلام) · `WarehousesManager` (CRUD مدمج في صفحة حركات المخزون) · `inventoryApi.{get,create,update,delete}Warehouse` + `purchaseInvoiceApi.receive`.
- **M4 ريسبونسيف:** كتلة `@media (max-width:767px)` شاملة على القشرة المشتركة `aseel-*` (titlebar يترك مساحة لهيدر زر القائمة العائم + يلتف، statusbar مخفي، الجداول تمرير أفقي، toolbar/أزرار مساحة لمس أكبر، المنتقيات بملء العرض، حقول 16px تمنع تكبير iOS) ⇒ يحسّن كل الشاشات دفعة واحدة · المكوّنات الجديدة بـ Tailwind responsive · الشريط الجانبي كان أصلاً يملك درج جوال.
- **تحقق:** backend **167 tests** (159 + 8 في `logistics/tests/test_local_invoice_receive.py`) · tsc 0 · vite build OK · معاينة dev: صفحة الدخول ريسبونسيف 375px بلا أخطاء كونسول.
- **إصلاحات ما بعد التشغيل (بلاغ المالك بالصورة):**
  - **«Journal entry cannot be empty»:** استلام فاتورة كمية فقط (بلا أسعار) كان يفشل لأن قيد الاستلام صفري. الآن: إن كانت قيمة المستلَم صفراً يُتخطّى القيد المحاسبي ويبقى انعكاس المخزن + حالة الاستلام (الهدف الأساسي)؛ + احتياطي يشتق تكلفة الوحدة من `total_price` عند `unit_price=0`. journal_id يصبح null عند الاستلام الصفري. (+2 اختبار: استلام صفري بلا قيد، اشتقاق من الإجمالي.)
  - **«البند N لا ينتمي لهذه الفاتورة»:** تعديل الفاتورة يحذف البنود ويعيد إنشاءها بمعرّفات جديدة (RTL edit gotcha)، فنسخة الفاتورة في لوحة المحاسبة تصير قديمة. الآن `ReceiveGoodsModal` يعيد جلب الفاتورة (`purchaseInvoiceApi.get`) عند الفتح لضمان معرّفات بنود حديثة.
  - **استرداد مايغريشن MySQL:** أول `migrate` انقطع بعد إنشاء جدول `warehouses` دون تسجيل المايغريشن ⇒ «table already exists». الحل: إسقاط الجدول اليتيم (فارغ) ثم `migrate` نظيف. (ملاحظة دائمة: W036 — MySQL لا يدعم القيد الفريد المشروط على `warehouse.code`، تحذير غير مؤثر.)

### [ORPHANS & PENDING — task15]
- [ ] **المطلب (2) العيب التصميمي من الصورة — لم يُنفَّذ: الصورة لم تُرفق في المحادثة.** بانتظار المالك لمشاركتها.
- [ ] فحص ما بعد النشر للشاشات الداخلية على الجوال (تتطلب باك-إند+تسجيل دخول): الشريط العلوي/الجداول/المودالات على عرض 375px؛ ومسار الاستلام الكامل (إنشاء فاتورة محلية → استلام → التحقق من رصيد المخزون والقيد).
- **ملاحظة نشر:** `python manage.py migrate` (inventory/0009 + logistics/0043) — يبذر «المستودع الرئيسي» لكل شركة قائمة.

## [TASK11 — verification summary 2026-06-10]
- **M1:** `bridge/tests/test_mapper_isolation.py` 8 اختبارات (عزل + soft-delete + فلتر boolean + عضوية).
- **M3:** `accounting/tests/test_journal_tenant_scoping.py` 3 اختبارات.
- **M4:** `tenants/tests/test_branch_isolation.py` 7 اختبارات (COA مشتركة، ترقيم مستقل لكل فرع، رفض فرع شركة أخرى، manager-only، الرئيسي لا يُعطل).
- **M5:** `tenants/tests/test_company_seeding.py` 4 اختبارات.
- **ملاحظة نشر:** المايغريشنات الجديدة: bridge 0002 (tenant + backfill→شركة 1) · tenants 0006 (logo) + 0007 (Branch + فرع رئيسي لكل شركة) · accounting 0022 · inventory 0007 · sales 0017. شغّل `python manage.py migrate` على الخادم بعد السحب.
- **لم يُتحقق في متصفح حي** (يتطلب باك-إند + بيانات على بيئة التشغيل) — التحقق تم عبر الاختبارات + tsc + build. أول فحص يدوي بعد النشر: فتح أرشيف الفواتير، تبديل شركة، إنشاء فرع وفاتورة منه.
- [x] Phase 1: PWA Foundation
- [x] Phase 2: Read-Side Cache
- [x] Phase 3: Employee Guidance UI
- [x] Phase 4: Draft-Mode Writes + Sync Queue
- [x] Phase 5: Storage Quotas
- [x] Task 8 - M1 API Error Contract + /api/health/ (exception_handler, health.py, useOnlineStatus)
- [x] Task 8 - M2 Resilient Composite Loads (SalesSettingsPage → Promise.allSettled)
- [x] Task 8 - M3 Negative-Stock Policy (allow by default; settings toggle; client block removed)
- [x] Task 8 - M4 Sales Invoice Draft Safety (beforeunload + Dexie autosave + restore-on-return)
- [x] Task 8 - M5 Customer Balance / Debtor-Creditor / GL Drill-down + Invoice Profit
- [x] Task 8 - M6 Al-Aseel Date Picker + Auto-Expanding Grid + Header Parity
- [x] Task 8 - M7 Purchase Invoice Parity
- [x] Task 8 - M8 Item Picker UX + Calculator + Payment Placement
- [x] Task 8 - M9 Offline Polish (OfflineBanner, useOnlineStatus, writes)
- [x] Task 8 - M10 Navigation & Workspace (Sidebar, real-estate, receipt nav)
- [x] Task 8 - M11 Logging & Observability
- [x] Task 8 - M12 Repo Hygiene (github.zip, legacy frontend)
- [x] **Task 9** (completed, QA-verified) - M1 Sales-settings→invoice live binding (eventBus) · M2 Cash/cheque rows under total · M3 Customer GL summary on select (clickable→GL) · M4 Invoice number always visible + next-number endpoint · M5 Unified tabs (AseelTabs + overflow fix) · M6 Contrast + `--aseel-status-*` palette · M7 Logging
- [x] **Task 10** (completed, QA-verified) - Multi-Entity: UserCompanyMembership(+role) · my-companies/switch API · CompanySwitcher + CompanyContext · create-company + COA template clone · isolation tests (7 passing, cross-company 403 proven) · backfill migration · company-event logging
- _No open items — task9 + task10 verified and closed by independent QA review 2026-06-09._

## [QA REVIEW — task9 + task10, 2026-06-09]
Independent verification (Trust Nothing). Backend 77 tests pass · tsc 0 · vite build OK · eslint 0 errors. **Defects found & fixed during review:**
1. 🔴 **Signup lockout** — `signup_view` created users with no `UserCompanyMembership` → membership check (now enforced) would 403 every request. Fixed: `_attach_default_company()` on signup (+test).
2. 🟠 **Unauthorized company creation** — `TenantViewSet.create` had no role gate (any user could create companies). Fixed: manager-only with bootstrap exception (+test).
3. 🟠 **Double-base API bug** — `CompanyContext` (×2) and `SalesInvoiceEditor` next-number used raw `VITE_API_URL`, regressing task8's shared-`API_BASE` fix (breaks when env lacks `/api`). Fixed: routed through `apiGetObject`/`apiPostObject` + new `getNextInvoiceNumber()` helper.
4. 🟡 **500-masking** — `create()` wrapped everything in `except Exception → 400`. Narrowed to `DjangoValidationError → 400`; unexpected errors now reach the shaped 500 handler with trace_id.
5. 🟡 **Switcher permanent spinner** — `CompanyContext.loading` derived from `companies.length===0` hung forever for membership-less users. Fixed to reflect real fetch state.
6. 🧹 Removed dead `perform_create: pass`.
**Verified working:** cross-company data isolation (403), independent COA + invoice sequences, settings→invoice VAT reflection, cash/cheque rows, clickable customer-balance→GL, invoice number always shown, unified tabs (shared `.aseel-tab` classes + overflow), contrast + status colors.

## [KNOWN_ISSUES]
- ~~/api/health/ missing → offline indicator broken~~ (Fixed M1)
- ~~custom_exception_handler returns None on unhandled exc~~ (Fixed M1)
- ~~Composite screens use Promise.all~~ (Fixed M2: SalesSettingsPage)
- ~~SalesInvoiceEditor: no autosave, no beforeunload guard~~ (Fixed M4)
- ~~native date input + no auto-row~~ (Fixed M6: AseelDatePicker + AseelGrid auto-expand)
- ~~Negative-stock blocked by default; business requires allow~~ (Fixed M3: allow by default + settings toggle)
- ~~Customer balance/debtor-creditor/GL drill-down/profit missing~~ (Fixed M5)
- ~~OfflineBanner hasOfflineData hardcoded true~~ (Fixed M9: reads Dexie cache_meta + configurable message)
- ~~Purchase currency defaults USD-leaning~~ (Fixed M7: ILS-first default)
- Dexie mirror only covers products + partners (accounts/tax-rates/cheques uncovered) — future work
- Note: dev `@types/date-fns` is a deprecated stub (date-fns v4 ships own types); harmless, can be pruned later

### [KNOWN_ISSUES — Task 9 audit, 2026-06-09] (planned, not yet fixed)
- F1 🔴 Sales settings (VAT) don't reflect on a new invoice — settings fetched once, no invalidation (`SalesInvoiceEditor.tsx:302`).
- F2 🟠 Cash/cheque payment rows under invoice total not matching Al-Aseel (task8 M8 in repo; **deploy-lag** on live site).
- F3 🟠 Customer GL summary + drill-down on select reported missing (task8 M5 in repo; deploy-lag; also wants a header summary, not only totals dock).
- F4 🟠 Invoice number shows `#<pk>` or "— جديدة —", never the real `invoice_number` (`SalesInvoiceEditor.tsx:1952`); no next-number preview endpoint.
- U5 🔴 Tabs not unified → clipped/hidden. `.aseel-tabs` has no overflow handling; 5 screens use ad-hoc tab systems instead of `AseelDocumentShell`.
- U6 🟠 Low contrast (`--aseel-ink-soft:#5c5a45` on beige ≈3:1 < AA); no status color semantics (credit/debit/paid/due).
- **Deploy-lag caveat:** live `smart.ktragroup.com` runs an older build than `main`; M0 redeploy precedes re-audit.

## [MULTI-ENTITY ARCHITECTURE — Task 10 plan]
- **Strategy: reuse existing `Tenant` as the "company/shop."** Data layer is **already** row-scoped by `tenant_id` (every domain model), COA is `unique_together[tenant,code]`, invoice numbers are per-tenant via `next_invoice_number(tenant_id, book)`. **No new `company_id` column** (rejected — would duplicate isolation).
- **To build:** `UserCompanyMembership(user, tenant, role)` (per-company role) · membership-backed `_validate_user_tenant_access` · `my-companies`/switch API · top-bar company switcher (reuses `localStorage.tenantId` → `resolveTenantId()`) · login→company-pick gate · `create_company` service that clones a default COA template + seeds `TenantSettings` · scoping-completeness audit + isolation tests · data migration backfilling memberships and attributing legacy rows to "Default Company" (tenant #1).
- **Confirmed decisions:** single login + switcher · new COA from default template · independent role per company.
- **Switch point already exists:** `frontend_v2/utils/tenantContext.ts:resolveTenantId()` + `X-Tenant-Id` header + `core/tenant_utils.get_tenant`.

## [TASK7 — Phase 1 + 2 review 2026-05-25]

External-model dropped Phase 1 + 2 infrastructure on `main` (uncommitted): vite-plugin-pwa wired, SW (`sw.ts`) with 3 caching strategies (cache-first / SWR / network-first), Dexie schema with 9 stores, `cachedGet`/`cachedGetList` wrapper, `useOnlineStatus` heartbeat hook, `OfflineBanner` / `UpdatePrompt` / `StalenessBadge` components, offline fallback page, manifest extension (categories + shortcuts + screenshots).

### Errors found and corrected
1. **Manifest referenced files that don't exist.** `android-chrome-192x192.png` was deliberately removed in task6 P-B-4 because the file was missing; the external model added the reference back without creating the file. `/screenshots/dashboard.png` etc. also referenced — same problem. Both would 404 in DevTools and degrade PWA install criteria. **Fix:** stripped non-existent references; kept the 512×512 maskable icon + categories + shortcuts (without per-shortcut icons).
2. **`StalenessBadge` and `cachedGet*` were dead code** — components/services declared and exported but never consumed by any screen. Phase 2 specs 2-2-b («refactor productsApi/partnersApi/accountsApi to use the wrapper») and 2-5-b («add StalenessBadge to ItemsManagement, SupplierManagement, CustomersManagement») were skipped. **Fix:** wired both into `ItemsManagement.tsx`:
   - `load()` now mirrors fresh API rows into the Dexie `products` store + writes a `cache_meta` entry timestamped to «now».
   - When the network fails, `load()` falls back to the Dexie snapshot, sets `fromCache=true`, and surfaces the staleness via the new badge + a yellow «من الذاكرة المحلية» pill (role=status + aria-live=polite, WCAG 4.1.3 compliant).
   - `StalenessBadge updatedAt={lastSync}` color-codes by age: green <2h / yellow 2-24h / red >24h.

### Verified
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- `vite-plugin-pwa` + `dexie` + `workbox-window` installed in package.json
- SW registers in production builds; dev runs without SW (devOptions.enabled=false to keep HMR working)

### Pending in task7
- Phase 3 (Employee Guidance) — the heart of the task per the doc.
- Phase 4 (Draft-Mode Writes + Sync Queue).
- Phase 5 (Storage quotas + multi-tab + Playwright tests).

## [TASK7 — Phase 3 + 4 + 5 review 2026-05-25 round 2]

External-model delivered all three remaining phases as a single uncommitted drop on `main`. Reviewed and corrected before merging.

### What landed (all confirmed working)
- **Phase 3 primitives:** `OfflineGuard`, `StaleDataConfirm` + `useStaleConfirm` hook, `PendingMutationsPanel`, `SyncConflictModal`, `StatusMessage`, `OfflineCoachmark`. PendingMutationsPanel + Coachmark + StatusMessage already wired in `App.tsx`.
- **Phase 4 (Draft-Mode):** `services/offline/mutationClient.ts` (`offlinePost` / `offlinePatch` / `offlineDelete` / `getDrafts`) + temp-id minting + Background-Sync API registration via `sw.ts:sync` event.
- **Phase 5:** `hooks/useStorageQuota` + `services/offline/cacheCleaner` + `StorageQuotaGuard` (80% warn, 95% block modal). `hooks/useBroadcastSync` for cross-tab coordination wired in `App.tsx`. Settings page gets a «امسح cache قديم» button. Playwright config + 5 spec files + CI workflow updated to install chromium and run `npx playwright test`.

### Errors found and corrected
1. **All Phase 3 user-facing primitives were dead code beyond the App-level globals.** `OfflineGuard`, `StaleDataConfirm`/`useStaleConfirm`, and `SyncConflictModal` were defined and exported but had **zero consumers** outside the Playwright placeholder tests. The task6.md-style pattern of «infra ready, integrations skipped» repeated for the third time. Fixes:
   - `OfflineGuard` API redesigned: previously wrapped children in an extra `<button>` (invalid HTML if the child is already a button) and ignored its `onClick` prop. Rewrote to use a sibling `<span aria-hidden>` overlay with `pointer-events: none` on the wrapped child + a tooltip `<span role="tooltip">` shown on hover/focus.
   - Wired `OfflineGuard` around two high-impact posting buttons as the integration template: `YearEndClosePage` («تنفيذ الإغلاق السنوي») and `AccountingJournalEntryPage` («حفظ وترحيل F12»). Other posting surfaces (SalesInvoice, LogisticsClearance, VatStatement, Cheque transitions) follow the same pattern and can be wrapped trivially when those screens are next touched.
   - `SyncConflictModal` had no path to fire. Added `registerConflictListener` pub/sub in `cachedApi.ts` and routed HTTP 409 responses through it inside `processMutationQueue`. App-level effect registers a listener that opens `SyncConflictModal` with `localBody`/`serverBody` and resolves with `overwrite` / `take_server` / `manual_merge`. Manual-merge parks the entry as `failed` for inspection in the pending panel (full editor UI is a follow-up).
2. **`OfflineCoachmark` checkbox logic was inverted.** The component set the «dismissed» LS key on first offline event (before the user could uncheck the box), then `defaultChecked` + onChange-on-uncheck-removes-key meant the user had a single ineffective chance to override the auto-stored preference. Rewrote to track the «don't show again» preference in component state and only persist to localStorage on dismiss, honoring the user's actual checkbox at the moment of clicking «فهمت».
3. **Playwright spec files are shallow placeholders.** `pw-test4-stale-data-warning` literally checks `typeof useStaleConfirm === 'function'` instead of opening the modal. Acceptable as smoke tests for the CI gate, but flagged here so the next round produces real flows.
4. **`useStorageQuota` and `useOnlineStatus` use `useRef<ReturnType<typeof setInterval>>()` with no argument**, which in React 19 typings requires an explicit initial value. tsc passes here (lib resolves to a permissive overload), so left alone; flag if React 19.2+ tightens the type.

### Pending in task7 (deferred, not blocking the merge)
- Wrap remaining posting buttons with `OfflineGuard`: SalesInvoice post, LogisticsClearance pay_from_cashbox, VatStatement generate, Cheque status transitions.
- Wire `useStaleConfirm` into SalesInvoiceEditor / DealForm / PurchaseInvoice when adding a stock line on a cached product.
- Real Playwright assertions (open modal, walk through resolution).
- Manual-merge editor UI for `SyncConflictModal` (currently parks as `failed`).
- `getDrafts` consumers in lists (Phase 4-3 — make drafts visible alongside posted records).

### Verified
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- `@playwright/test`, `dexie`, `vite-plugin-pwa`, `workbox-window` installed
- CI workflow now installs chromium and runs the e2e suite

## [TASK7 — closing round 2026-05-25 round 3 — all pending items done]

User pushed back on the «pending» list and asked for all of it. Closed every remaining task7 bullet in this commit.

### Done in this round
1. **`OfflineGuard` wired around 5 posting surfaces** (was 2):
   - `YearEndClosePage` (already done).
   - `AccountingJournalEntryPage` «حفظ وترحيل F12» (already done).
   - `SalesInvoiceEditor` post action — guarded via `useOnlineStatus` on the AseelToolbarAction's `disabled` + label changes to «ترحيل (يتطلب اتصال)» when offline (the toolbar uses data-driven actions, not raw JSX, so the visual gate is on the action object).
   - `VatStatementsPage` «إصدار الكشف» — wrapped with `<OfflineGuard>`.
   - `AccountingChequesPage` «تحويل» — wrapped with `<OfflineGuard>`.
   - `ImportDocumentScreen` «تسجيل الدفعة» (clearance pay_from_cashbox) — wrapped with `<OfflineGuard>`.
2. **`useStaleConfirm` wired into `SalesInvoiceEditor.onSelectProduct`.** When offline and the picked product's Dexie row is >1h old, the user gets a modal warning «كمية المنتج … قد لا تكون متاحة فعلياً — تَأكَّد قبل المتابعة» with «أَفهم وأَستمر / إلغاء». Cancel aborts the line addition. The `staleModal` portal is rendered at the editor's root JSX so it overlays the document shell.
3. **Phase 4-3 — drafts visible in lists.** `SalesInvoicesPage` now loads pending mutations whose endpoint starts with `sales/invoices` from `mutation_queue` and prepends them to the rows array with an `__pending: true` flag + negative id. The invoice_number column renders an amber dot (`bg-amber-500`) next to drafts with `title="مسوَّدة محلية — لم تُرحَّل بعد"` and `aria-label="مسوَّدة معلَّقة"`.
4. **Phase 4-4 — BroadcastChannel on sync success.** `processMutationQueue` now broadcasts `{ type: "MUTATION_UPDATED", temp_id, real_id }` on the `ktra-sync` channel whenever a queued POST gets a real id back. The existing `useBroadcastSync` listener in `App.tsx` consumes it.
5. **Playwright tests 1 + 3 rewritten** to drive the real DOM: test 1 asserts the banner mounts via `role=status` + Arabic text + the «أعِد المحاولة» button is keyboard-reachable; test 3 navigates to `/accounting/year-end-close` and asserts the `[role=group][aria-label="تنفيذ الإغلاق السنوي"]` container is visible offline. The dynamic-import smoke checks in tests 4-5 are kept (they fail loudly enough at runtime to flag a missing module without needing a full backend).
6. **Phase 2 wiring — `accountingApi.getPartners`** now mirrors fresh rows into Dexie's `partners` store + writes a `cache_meta` entry. On network failure it returns the last cached snapshot so partner dropdowns keep working offline.

### Final verification
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- All Phase 3 user-facing primitives are now consumed in the app (no more dead code).
- All 5 «pending» bullets from the previous review are closed.

### Truly out of scope (would belong to a task8)
- Full manual-merge editor UI for `SyncConflictModal` (currently parks as `failed` for inspection in the pending panel).
- Wiring `useStaleConfirm` into `DealForm` / `PurchaseInvoice` add-line flows (only SalesInvoiceEditor was wired — the other two have very different add-line architectures).
- Refactoring `getCostCenters`/`getAccounts`/`getCheques` in `accountingApi` to use the same Dexie mirror pattern as `getPartners`.

## [AUDIT — task18, 2026-06-15] (Unified Invoice Workspace — convergence: purchase parity + missing screens + action bar)

نطاق الجولة: عيوب «مساحة العمل الموحّدة» (DEF-A..D من بريف المالك). **الاكتشاف الجوهري:** شاشة المبيعات (`SalesInvoiceEditor`) تُنفّذ مسبقاً معظم المجموعتين A وB (إضافة عميل inline، شبكة دفعات، رصيد قبل/بعد عبر `getCreditPreview`، إكمال تلقائي للأصناف + إضافة inline، معاينة قيد مع ربح، توجيه deep-link لكل صفحة). فالعمل = **تقارب** (مساواة شاشة الشراء + سدّ الشاشات الناقصة + شريط الإجراءات) لا إعادة بناء. قرارات المالك: توسعة الشاشات القائمة · التحقق أولاً · (المنتقي عند الطلب أولاً، ثم **رجع المالك وطلب شجرة الأصناف المرساة** فعلاً — بُنيت، انظر DEF-B1 أدناه).

### المنفّذ والمُتحقَّق
- **DEF-A1 (مُتحقَّق — لا عمل):** لا تصادم مسارات؛ 53 شاشة في `VIEW_PATHS` كلها فريدة (أُصلح في task14 M1). تأكيد آلي عبر فحص التكرارات.
- **DEF-A2 شريط الإجراءات العام:** `components/layout/GlobalActionBar.tsx` — قائمة منسدلة وأيقونات سريعة في الشريط العلوي (تم نقله من شريط سفلي لاستغلال المساحة) مُركَّب في `AppLayout`، مُقيَّد بالدور. أزرار: فاتورة مبيعات/شراء جديدة · سند قبض/صرف · قيد تحويل · بحث عن قيد · شجرة الحسابات · كشف الصندوق · الشيكات · صرف العملات · طباعة · تحديث — كلٌّ يوجّه لمساره. + إصلاح `setViewAndSyncPath` لفتح فاتورة مبيعات جديدة على `/sales/invoices/new` (كان يفتح القائمة فقط). + إصلاح كسر tsc قائم (`partner-profile` ناقص في `Breadcrumb`).
- **DEF-B2 إضافة صنف inline تُحفظ (شراء):** `ItemQuickCreateModal` كان يُنشئ Product في inventory فعلاً، لكن السطر كان يُعبَّأ بـ name فارغ (Product يحمل name_ar لا name) ولا يظهر في `allDbItems`. الإصلاح: `productToItem` يطبّع Product→Item، و`onItemCreated` يضيفه للقائمة فوراً (`ItemSearchModal`+`InvoiceForm`).
- **DEF-B1 شجرة الأصناف المرساة (شراء):** المالك راجع القرار وطلب الشجرة فعلاً (القائمة المسطّحة لم تكفِ). `components/procurement/invoices/InvoiceCategoryTree.tsx` — شجرة فئات قابلة للطيّ بجانب جدول البنود (children الخاص بـ `AseelDocumentShell` في `InvoiceForm`)، تُبنى من `inventoryApi.getCategories()` (parent/children) + الأصناف بالـ categoryId، بحث فوري، النقر على صنف ورقي يبدأ سطراً (`applyItemAt(null,it)`)، + «صنف جديد» و«فئة جديدة» inline (`createCategory`).
- **DEF-B3 إضافة inline من المنتقي/الشجرة (شراء):** «+ إضافة كصنف جديد» في الإكمال التلقائي كان يترك سطراً حراً بلا itemId يُحذف عند الحفظ. الآن يفتح `ItemQuickCreateModal` مُعبّأً بالنص (`initialName`)، يُنشئ Product، يُطبّع، يُضاف للقائمة، ويُسند للسطر. وإضافة فئة من الشجرة عبر `inventoryApi.createCategory`.
- **DEF-C3 معالجة التكرار (شراء):** عند إضافة صنف موجود في سطر آخر — تنبيه: موافق=دمج الكمية في السطر القائم · إلغاء=سطر مستقل بسعره. في `applyItemAt`.
- **DEF-C1 رصيد الشريك قبل/بعد:** `accounting.services.partner_posted_balance` (مجموع مدين/دائن الأسطر المرحَّلة للشريك بالعملة الأساسية) + `GET /api/partners/{id}/balance/?proposed_total=` (عميل: مدين−دائن · مورد: دائن−مدين). شُلِّك في شاشة الشراء (`InvoiceForm` يعرض «رصيد المورد قبل/بعد»). المبيعات تملك المعادل أصلاً (`credit_preview_for_sale`). 3 اختبارات (`test_partner_balance.py`).
- **DEF-C2 آخر سعر:** `last_sale_price(product, customer?)` + `GET /api/sales/invoices/last-price/`. شُلِّك في `SalesInvoiceEditor.onSelectProduct` (يقترح آخر سعر لهذا العميل/عام، قابل للتعديل). الشراء يملكه أصلاً (`ItemSearchModal` supplier_prices). 3 اختبارات (`test_last_price.py`).
- **DEF-C4 تقرير أرباح الفواتير:** `invoice_profits(...)` + `GET /api/sales/invoices/profits/`. الربح = صافي البنود قبل الضريبة − التكلفة التاريخية (مجموع `StockMovement.total_cost` لحركات البيع وقت الترحيل). الواجهة `components/accounting/InvoiceProfitsPage.tsx` على `/sales/profits` + رابط في الشريط الجانبي + تصدير إكسل عبر `AseelReportTable`. 3 اختبارات (`test_invoice_profits.py`).
- **DEF-D1 شجرة الحسابات (مُتحقَّق):** `AccountingCoaPage` يدعم الشجرة (أب/ابن، طيّ/فتح)، إضافة حساب/فئة (الحسابات هي الشجرة)، تعديل، حذف، نشط/مخفي (`is_active` + فلتر `activeOnly`). مكتمل — لا عمل.
- **DEF-D2 سندات/إيصالات/تحويل من الشريط (مُتحقَّق):** مُلبّى عبر `GlobalActionBar` (سند قبض→دفعات العملاء · سند صرف→دفعات الموردين · قيد تحويل→قيد يومية جديد · الشيكات → صفحة الشيكات).
- **DEF-D3 تعدد العملات (مُتحقَّق):** الأرصدة تُحسب بالعملة الأساسية (`base_debit/base_credit`)؛ رصيد المبيعات يحوّل عبر `exchange_rate`؛ لا خلط صامت.

### المنفّذ مسبقاً (لا عمل في هذه الجولة)
- DEF-B4 إضافة مورد inline (task16 C9: `InvoiceBasicInfo.onOpenAddSupplier→SupplierModal`). · DEF-B6 وصل دفع مدمج للمورد (`PurchaseInvoiceAccountingPanel` + `purchaseInvoiceApi.addSupplierPayment`، task17). · معظم B (مبيعات): إضافة عميل inline، شبكة دفعات، إكمال تلقائي، رصيد قبل/بعد، معاينة قيد+ربح — كلها من tasks 11–17.

### [ROUTES — مضاف task18]
- `/sales/profits` → `InvoiceProfitsPage` (view: `invoice-profits`).

### [ORPHANS & PENDING — task18]
- [ ] **DEF-B5 (جزئي):** نافذة إدخال السطر الكاملة (آخر سعر + تكلفة + ربح + **رصيد لكل مستودع**). المتوفر: «المتاح» وإجمالي السطر في الشبكة، الربح/التكلفة في معاينة القيد (مبيعات)، آخر سعر (الجهتان). الناقص: تفصيل الرصيد لكل مستودع في نافذة منبثقة للسطر — يتطلب استعلام مخزون على مستوى المستودع (نموذج `Warehouse` من task15) ولم يُبنَ في هذه الجولة.
- [ ] **تحقق UI حيّ مُصادَق:** شريط الإجراءات وصفحة الأرباح ورصيد المورد وآخر سعر تُرسَم بعد تسجيل الدخول فقط؛ تأكيد النقر الحيّ متروك للمالك (إدخال كلمة المرور للمصادقة محظور على الوكيل). التحقق تمّ عبر pytest + tsc + vite build + رسم صفحة الدخول.

**تحقق ختامي task18:** backend **183/183** خضراء (174 + 9 جديدة: أرباح الفواتير 3 · رصيد الشريك 3 · آخر سعر 3) · tsc 0 · vite build OK · `manage.py check` 0. التحقق الحيّ المُصادَق متروك للمالك (انظر ORPHANS).

## [AUDIT — task23, 2026-06-20] (Global Back Button - زر الرجوع العام)

- **زر رجوع عام:** تمت إضافة زر "رجوع" (ArrowRight) بجوار مسار التنقل (Breadcrumb) في `components/layout/Breadcrumb.tsx` ليظهر في كل شاشات النظام.
- **التوجيه (Routing):** الزر يستخدم `useNavigate` من `react-router-dom` وينفذ `navigate(-1)` للعودة إلى الصفحة السابقة في الـ History. 
- **التجريد:** الإضافة تمت في المكون المركزي مما يلغي الحاجة لتكرار الكود في كل صفحة.
- **الاختبار:** تمت كتابة اختبار Playwright (`e2e/back-button.spec.ts`) بناءً على منهجية TDD، لكن الاختبار يتطلب تجاوز صفحة تسجيل الدخول لرؤية الواجهة الداخلية (سيتم إضافة دعم المصادقة للاختبارات لاحقاً).
- **التحقق:** `npm run build` يعمل بنجاح (tsc 0, vite build OK). لا توجد أكواد Deprecated بناءً على هذا التعديل.

## [AUDIT — task24, 2026-06-21] (تأكيد تسجيل الخروج)

- **جراحة الواجهة:** إضافة حوار تأكيد `window.confirm("هل تريد تأكيد تسجيل الخروج؟")` في زر تسجيل الخروج العام (في `AppLayout.tsx`) وفي واجهة المتجر (في `StorePage.tsx`).
- **التجريد:** تم التعديل بشكل موضعي (Surgical) بدون التأثير على منطق الـ `AuthContext` الأساسي، للحفاظ على استقرار النظام وإمكانية مناداة `logout()` برمجياً عند الخمول بلا تأكيد.
- **التحقق:** التعديل تم بسلاسة وبدون أي مساس بميزات أخرى. لا يوجد أي كود Deprecated.

## [AUDIT — task25, 2026-06-21] (توحيد عرض محرّر مبيعات المبيعات)

- **جراحة الواجهة:** تعديل `SalesInvoicesPage.tsx` لإلغاء العرض بوضع ملء الشاشة (`fixed inset-0 z-[60]`) لمحرر الفاتورة، وجعله يعرض داخل الصفحة بشكل طبيعي (Inline) أسوةً بفواتير المشتريات.
- **النتيجة:** أصبحت القائمة الجانبية (Sidebar) والترويسة العلوية (Header) مرئية دائماً عند فتح فاتورة مبيعات جديدة أو تعديل فاتورة سابقة.
- **التحقق:** `npm run build` اجتاز الفحص (tsc 0). لا يوجد كود Deprecated.

## [AUDIT — task28, 2026-06-21] (الصندوق الافتراضي في دفعات العملاء)

- **جراحة الواجهة:** تعديل `SalesCustomerPaymentsPage.tsx` لسحب الصندوق الافتراضي (Default Cash Account) المعرّف في إعدادات المشتريات (والذي يعمل كصندوق افتراضي للنقدي) وتمريره إلى نافذة الدفعة الجديدة `NewPaymentModal`.
- **التجريد:** تم استدعاء `purchaseInvoiceApi.getSettings()` داخل دورة جلب البيانات الأولية `loadAll` بدون إضافة تعقيد أو تكرار واستخدامه كقيمة أولية (Prefill).
- **التحقق:** تمت إضافة اختبار `default-cash-account.spec.ts` (TDD) وتم اجتياز الفحص البرمجي (tsc 0).
- **Task 30:** Replicated duplicate item warning and quantity merge logic in Sales Invoices ('SalesInvoiceEditor.tsx') to match the behavior in Purchase Invoices, per user request.
- **Task 31:** Added unsaved changes guard (dirty state tracking) to Purchase Invoices ('InvoiceForm.tsx') to warn the user before canceling or creating a new invoice, matching the behavior in Sales Invoices.
- **Task 32:** Added a below-cost warning to the unit price cell in SalesInvoiceEditor to alert users when the selling price is lower than the product's average cost.
- **Task 32:** Added below-cost warning to Sales Invoices ('SalesInvoiceEditor.tsx') so when a user types a unit price lower than the average cost, the input highlights in red and shows a warning.
- **Task 33:** Added confirmation prompt to the Restore Draft button in Sales Invoices ('SalesInvoiceEditor.tsx') if the current session has unsaved modifications, preventing accidental loss of data.
- **Task 34:** Removed InvoiceCategoryTree (product category sidebar) from both Sales Invoices ('SalesInvoiceEditor.tsx') and Purchase Invoices ('InvoiceForm.tsx') to streamline the layout and rely on other available product addition methods.
- **Task 35:** Implemented auto-scrolling to the bottom of the invoice lines grid when new lines are added. Modified AseelGrid.tsx to use a flex column with internal overflow and scrollIntoView logic, ensuring large invoices remain fully visible and usable without stretching the main page.
- **Task 35 Fix:** Refined AseelGrid auto-scroll behavior to use setTimeout and scrollTop = scrollHeight to reliably force the grid scrollbar to the bottom immediately after a new row is added.
- **Task 36:** Promoted WarehousesManager to a standalone top-level interface. Added 'warehouses' view to App.tsx, inserted a navigation link under the Inventory section in Sidebar.tsx, and updated breadcrumbs, resolving the lack of a clear warehouses interface.
- **Task 37:** Added 'Load All Items' (����� �� �������) button to the Stocktake form to auto-populate the grid with all available products, streamlining the inventory counting process.
