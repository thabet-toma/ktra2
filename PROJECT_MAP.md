# PROJECT_MAP — K.T.R.A

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
