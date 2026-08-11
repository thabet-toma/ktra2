# تدقيق جاهزية 500 مستخدم متزامن — K.T.R.A

> **المرحلة 4 من خطة `docs/REFACTOR_PROMPTS.md`** — تحليل فقط، صفر تعديل كود.
> **المنهجية:** 4 مسارات تدقيق متوازية (بنية تحتية/نشر · N+1 وترقيم · فهارس وعزل tenant · واجهة أمامية)،
> كل ادعاء أدناه مبني على قراءة الكود الفعلي وموثّق بـ`file:line`.
> **الحالة قبل التدقيق:** 1,025 اختباراً خضراء (`manage.py test --settings=core.test_settings`).

---

## الخلاصة التنفيذية

النظام **لن يصمد أمام 500 مستخدم متزامن** بوضعه الحالي، والسبب ليس بنداً واحداً بل سلسلة من خمسة اختناقات مركّبة:

1. **gunicorn بـ3 workers من نوع sync بلا threads** (`deploy.ps1:189-195`) — السقف المطلق = **3 طلبات متزامنة**. هذا وحده يجعل الهدف مستحيلاً بغضّ النظر عن كل ما بعده.
2. **الترقيم opt-in** (`core/pagination.py:16-19`): بلا `?page=` يُرجَع الجدول **كاملاً**. والواجهة تمرّر `?page=` من ~8 شاشات فقط — **131 استدعاء `apiGetList` غير مرقّم مقابل 16 مرقّماً** (~92% من قوائم الواجهة).
3. **FileBasedCache** (`core/settings.py:352-358`) بسقف افتراضي 300 مدخل وبلا قفل بين العمليات — حذف عشوائي مستمر تحت الحمل + سباق read-modify-write على عدّادات الـthrottle.
4. **لا throttle عام** (`core/settings.py:378-389`): كل مسارات ERP الفعلية بلا أي حدّ معدّل — مستخدم واحد يقدر يشبع الـworkers الثلاثة.
5. **endpoints بآلاف الاستعلامات**: تقرير أعمار الدائنين وحده ينفّذ ~15,000–25,000 استعلام في طلب واحد (`core/reports.py:921-928` + `logistics/services.py:473-518`).

**إضافة خارج نطاق الأداء لكنها لا تحتمل التأجيل:** التدقيق كشف **3 ثغرات عزل tenant حرجة** (SQL خام بلا مصادقة، مجموعات bridge مشتركة بين الشركات، تبنّي وثائق يتيمة) — مصنّفة P0 أمنياً.

**تصحيحان لافتراضات الخطة الأصلية:**
- `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True` **موجودان فعلاً** (`core/settings.py:172-173`) — بند المرحلة 5 رقم 3 ساقط، لا حاجة له.
- عدد الفهارس الفعلي **56 `models.Index`** + 7 `db_index` + 48 قيداً فريداً (لا ~34 كما ورد في التشخيص) — لكن توزيعها مختلّ: `inventory` فيه فهرس مركّب واحد فقط و`StockMovement` (أضخم جدول) بلا أي فهرس.

---

## جدول P0 — يكسر عند 500 مستخدم (أو خرق أمني فعلي)

> **تحديث 2026-08-11:** بنود الأمن الأربعة (P0-2/P0-3/P0-4/P0-8) **نُفِّذت في الجلسة الأمنية** — تفاصيلها في `docs/REFACTOR_PROMPTS.md` («نتائج الجلسة الأمنية»). البنود أدناه تبقى للمرجع مع وسم ✅.

| # | البند | الدليل | الجهد | النوع |
|---|---|---|---|---|
| ✅ P0-1 | gunicorn: 3 sync workers، بلا `--timeout` مخصص (مهلة المساعد 60–120ث > مهلة gunicorn 30ث)، إعادة تشغيل بـ`pkill` (انقطاع كامل) | `deploy.ps1:189-195` · `core/settings.py:302-304,329` | ساعة | نشر |
| ✅ P0-2 | نقطة SQL خام بلا مصادقة ولا فلترة tenant — قراءة بيانات كل الشركات بمفتاح ثابت واحد، والمرشّح قائمة سوداء regex قابلة للتجاوز | `core/agent_db_view.py:48-51,24-32,81` · `core/urls.py:54` | ساعة (حذف/تقييد) | **أمن — منفّذ** |
| ✅ P0-3 | مجموعات bridge «عالمية» مشتركة: أي مستخدم من أي شركة يقرأ `attendanceRecords`/`pointsHistory`/`attendanceSessions` لكل الشركات | `bridge/views.py` · `bridge/migrations/0005_*` | هجرة نسبة تستخرج المالك من بنية الوثيقة نفسها (مسار `pointsHistory`، أو `userId`/`createdBy` في الحمولة) ثم `UserCompanyMembership`. ما لا يُحسم مالكه يبقى NULL ⇒ لا تقرؤه أي شركة. `departments` محتوى عام فعلاً فبقيت عالمية — لم تكن يوماً جزءاً من التسريب | **أمن — منفّذ 2026-08-11** |
| ✅ P0-4 | bridge يتبنّى الوثائق يتيمة الـtenant: أي وثيقة `tenant_id=NULL` مقروءة وقابلة للكتابة والاستيلاء من أي شركة | `bridge/views.py:353-359,417-420,458-461` | ساعتان | **أمن — منفّذ** |
| ✅ P0-5 | الترقيم opt-in — فرضه على endpoints الفئة أ (حركات مخزون، قيود، فواتير بيع/شراء، صفقات، مدفوعات) مع تعديل مستهلكي الواجهة | `core/pagination.py:16-19` · القائمة الكاملة في §2 | 2-3 أيام (backend+frontend معاً) | أداء |
| ✅ P0-6 | Redis بدل FileBasedCache (أو على الأقل LocMemCache+رفع MAX_ENTRIES مرحلياً) — الكاش الحالي يتصرف كأنه معطّل تحت الحمل وعدّادات الـthrottle عليه | `core/settings.py:352-358` | نصف يوم | أداء |
| ✅ P0-7 | throttle عام: `UserRateThrottle`/`AnonRateThrottle` بمعدلات معقولة (الحالي: 5 نطاقات كلها لـaccountant_portal فقط) | `core/settings.py:378-389` | ساعتان | أداء |
| ✅ P0-8 | رفع وسائط مجهول بلا throttle حتى 25MB — رفع Cloudinary متزامن يقفل worker ومفتوح للعالم | `core/media_views.py:28,44-101` | ساعتان | أمن+أداء — **منفّذ** |
| ✅ P0-9 | تقرير أعمار الدائنين: ≥6 استعلامات لكل فاتورة على كل الفواتير المرحّلة منذ النشأة (بلا فلتر تاريخ) — ~20 ألف استعلام/طلب | `core/reports.py:921-928` → `logistics/services.py:479,489-490,497-498,506` | نصف يوم (prefetch أو تجميع SQL) | أداء |
| ✅ P0-10 | فهارس `StockMovement` — أضخم جدول بلا أي فهرس مركّب، وقائمته بلا `order_by` حتمي | `inventory/models.py:261-264` · استعلامات: `inventory/views.py:694-733`، `inventory/services.py:901-903`، `core/reports.py:1180-1190` | نصف يوم (migration واحد) | أداء |
| ✅ P0-11 | فهارس `JournalLine` — فهرس واحد `(tenant,account)` لأكبر جدول محاسبي؛ تقرير أرصدة الشركاء = full scan | `accounting/models.py:152-155` · `core/reports.py:999-1006` · `accounting/views.py:622-655` | ضمن migration P0-10 | أداء |
| ✅ P0-13 | نقطة تسجيل الدخول **خارج سلسلة throttle كلياً**: دالة Django عادية لا view من DRF ⇒ لا `DEFAULT_THROTTLE_CLASSES` يمسّها، ولا قفل حساب في المشروع ⇒ تخمين كلمات مرور بلا سقف + استنزاف CPU على PBKDF2 | `hr/auth_api.py:165` · `hr/urls.py:35` · التفصيل في §1.7 | ساعتان | **أمن — مكتشَف في المرحلة 5، منفّذ** |
| ✅ P0-12 | شاشة الأصناف: حلقة تجلب كل الصفحات (`page_size=200`) وترندر كل الصفوف بلا virtualization، ويُعاد كل ذلك على كل حرف بحث (debounce 250ms) — 1490 صنفاً = 8 طلبات متسلسلة × كل دورة بحث | `frontend_v2/components/items/ItemsManagement.tsx:102,148-152` · `frontend_v2/services/inventoryApi.ts:124-139` | يوم | واجهة |

## جدول P1 — يبطّئ بوضوح

> **تحديث 2026-08-11 (جلسة «كل النواقص»):** كل بنود P1 القابلة للتنفيذ نُفِّذت.
> المتبقّي منها ثلاثة فقط وبأسباب موثّقة: **P1-11** (مؤجَّل بقرار)، و**P1-12/P1-13**
> (قرارهما Celery وهو معلَّق على قياس المرحلة 6).

| # | البند | الدليل | الجهد |
|---|---|---|---|
| ✅ P1-1 | N+1 في قائمة إرساليات البيع: `partner` خارج `select_related` و`invoice__lines` خارج `prefetch` = استعلانان لكل صف | `sales/serializers.py:901-904,912-921` · الإصلاح سطران في `sales/views.py:737-739` | ساعة |
| ✅ P1-2 | تقرير Landed Cost: N+1 متداخل ثلاثي ≈ 4,000 استعلام/طلب — *(قِيس: 3 شحنات = 41 استعلاماً مقابل 17 لشحنة واحدة؛ صار ثابتاً. `tenant` كان أيضاً خارج select_related)* | `logistics/views/reports.py` | نصف يوم |
| ✅ P1-3 | دفتر الأستاذ العام: توسيع شجرة الحسابات تعاودياً (استعلانان/حساب) + `journal.currency` غير مسبّق (استعلام/سطر) + بلا ترقيم إطلاقاً — *(قِيس: جذر شجرة من ٧ حسابات = 23 استعلاماً مقابل 13 لورقة؛ صار ثابتاً. السقف 5000 سطر مع `truncated`/`total_count` معلَنين)* | `accounting/views.py:594-614,682` | نصف يوم |
| ✅ P1-4 | فهارس المدفوعات: `CustomerPayment`/`SupplierPayment` بلا `indexes` إطلاقاً؛ `PurchaseInvoice` فهارسه لا تطابق أنماط الفلترة الفعلية؛ `Partner` الجدول الأساسي بلا فهارس؛ `SalesInvoice` فهرسه لا يخدم الترتيب `-invoice_date,-id` | `sales/models.py` · `logistics/models.py` · `partners/models.py` | ضمن migration الفهارس |
| ✅ P1-5 | `LogisticsPayment` بلا حقل tenant أصلاً — العزل بـ`OR` عبر جدولين (union/scan) — *(الحقل مشتقّ في `save()` من الصفقة/الشحنة فلا موضع إنشاء يحتاج تعديلاً؛ mig 0072+0073)* | `logistics/models.py` · `logistics/views/deals.py` · `core/dashboard_api.py` | يوم (migration بيانات) |
| ✅ P1-6 | فحص عكس القيد بلا tenant: full scan على قيود كل المنصة + تسريب معلومات جانبي + خلل وظيفي (تصادم reference_id بين شركات) | `accounting/views.py:410` | ساعة |
| ✅ P1-7 | 4 مواضع `get_queryset` بلا `.none()` عند غياب tenant (نفس نمط ثغرة task11 M7 المُصلَحة سابقاً) + `realestate.TenantScopedViewSet` لا يفلتر بنفسه | `tenants/views.py:52,103` · `sales/views.py:751,1567` · `realestate/views.py:20-33` | ساعتان |
| ✅ P1-8 | `PrimaryKeyRelatedField` بـ`objects.all()` يقبل pk من أي شركة عند الكتابة (الـget_queryset يحمي القراءة فقط) | `sales/serializers.py:243` — نمط يستحق مسحاً شاملاً | نصف يوم |
| ✅ P1-9 | واجهة: `listPickerProducts` بلا حدّ (609KB × 9 شاشات، موثّق في الكود نفسه) + إعادة جلب الجداول الكاملة على كل `focus`/`visibilitychange` لكل تبويب مفتوح — *(نافذة 60ث لكل شركة + دمج الطلبات المتزامنة + إفراغ صريح من كل مسارات كتابة الأصناف؛ وتهدئة 60ث على `focus`/`visibilitychange` — عودة تبويب واحدة كانت تُطلق **جلبتين** لأن الحدثين يقعان معاً)* | `frontend_v2/services/inventoryApi.ts` · `firestoreService.ts` · `sqlApiClient.ts` | يوم |
| ✅ P1-10 | واجهة: شاشات تجلب جداول كاملة — **فُحص فوجِد مُغلقاً سلفاً، بلا تغيير:** `GoodsReceiptsPage` يمرّر `page=1` منذ `7460459`، و`activityService` على `PageNumberPagination` عادي (يُرقّم دائماً) فـ`page_size=200` سقفٌ فعلي لا فخّ | `activityService.ts:34` · `GoodsReceiptsPage.tsx:167` | — |
| ⬜ P1-11 | لا virtualization في أي جدول — **مؤجَّل بقرار:** `AseelDenseTable` هدف طباعة (`aseel-print-hidden`)، والنافذة المرئية تعني طباعة ~20 صفاً بدل الجدول كاملاً؛ وقيمته استُهلكت أصلاً بـP0-5/P0-12 (الشاشات صارت 50-200 صفاً خادمياً لا 10 آلاف) | `AseelDenseTable.tsx:232` · `GroupedItemsTable.tsx:59` | يوم-يومان |
| ⬜ P1-12 | ترحيل/إلغاء ترحيل دفعي لفواتير الشحنة داخل طلب واحد و`transaction.atomic` طويلة؛ واستلام مخزون الشحنة داخل signal (مئات الحركات لحفظة واحدة) | `logistics/views/` · `logistics/signals.py` → `inventory/services.py` | **مرشّح Celery — القرار معلَّق على قياس المرحلة 6** |
| ⬜ P1-13 | `_recompute_product_stock`: `select_for_update()` + إعادة تشغيل كل حركات الصنف — تنازع أقفال لا-خطي على الأصناف الشائعة | `inventory/services.py:268-299,323-324` | **مرشّح Celery — نفس القرار** |
| ✅ P1-14 | `BrowsableAPIRenderer` مفعّل في الإنتاج (لا `DEFAULT_RENDERER_CLASSES`) | `core/settings.py` | نصف ساعة |
| ✅ P1-15 | توليد المراجع التسلسلية بتحميل كل الأرقام في بايثون + سباق تحت التزامن — *(الأقصى صار في القاعدة بـ`Cast(Substr(...))`؛ وحلقة الـ9000 `exists()` حُذفت لأن `subtree` يعرف المشغول أصلاً، والحارس الصحيح صار قيد الفريدة مع إعادة محاولة — الفحص المسبق لم يكن يمنع السباق أصلاً)* | `logistics/views/deals.py` · `accounting/services.py` | نصف يوم |

## جدول P2 — دين تقني

> **تحديث 2026-08-11 (جلسة «كل النواقص»):** نُفِّذ 11 من 14. المتبقي ثلاثة،
> اثنان منها **مفتوحان بقرار** لا بإهمال (P2-1 و P2-14) وواحد منفَّذ جزئياً (P2-2).

| # | البند | الدليل |
|---|---|---|
| 🔒 P2-1 | `NoStoreAPIMiddleware` يضع `no-store` على كل `/api/` — **قرار نهائي (2026-08-11): يبقى كما هو.** الوسيط ضابط أمني مقصود (بيانات مالية لا تُكتب على قرص المتصفح) وُضع لعلاج بلاغ «بيانات قديمة بعد الترحيل» الحقيقي؛ والواجهة صارت تحمل نوافذها الخاصة (60ث) للثوابت المتكررة (P1-9/P2-9) فمكسب كاش المتصفح صار هامشياً مقابل عودة خطر الكاش العالق. لا يُعاد فتحه إلا ببلاغ نطاق فعلي | `core/cache_control_middleware.py:16-30` |
| 🔒 P2-2 | استعلام DB للتوكن كل طلب + جلسات في القاعدة + `Tenant.objects.count()` مرتين في المسار الساخن. **نُفِّذ شقّ الشركة** (كلاهما محفوظ على الطلب). **شقّ كاش التوكن — قرار (2026-08-11): مؤجَّل حتى قياس المرحلة 6.** البحث أظهر: الخروج يحذف التوكن عبر ORM (فالإبطال قابل للربط بإشارة)، لكن المكسب استعلام PK مفهرس واحد على اتصال دافئ (`CONN_MAX_AGE=60`) بينما بديله قراءة FileBasedCache + pickle — ليس أسرع فعلياً على هذه المنصة، ويضيف سطح إبطال. يُنفَّذ فقط إن أظهره اختبار الحمل ضمن الاختناقات، وحينها على Redis | `core/tenant_utils.py` · `hr/auth_api.py:249` |
| 🟨 P2-3 | لا كاش على أي تقرير + `MAX_ROWS` يقصّ بعد البناء. **نُفِّذ شقّ الكاش** (نافذة 60ث بمفتاح يحمل الشركة والمستخدم، `REPORT_CACHE_SECONDS=0` يعطّله). **وشقّ MAX_ROWS لا يُلمَس عمداً:** القصّ بعد البناء مقصود وموثّق — الإجماليات تُحسب على الصفوف كاملةً قبله، فدفعه داخل الاستعلام يجعل المجموع يكذب | `core/reports_api.py` · `core/reports/_framework.py:198` |
| ✅ P2-4 | `init_command` يعطّل `foreign_key_checks` على كل اتصال إنتاجي — *(الفرض صار الافتراضي مع مخرج طوارئ `MYSQL_DISABLE_FK_CHECKS=1`. ⚠️ يحتاج تحقق دخان على MySQL: اختبارات المشروع على SQLite لا تكشف قيود المفاتيح الأجنبية)* | `core/settings.py` |
| ✅ P2-5 | تناقض النشر: `deploy.ps1` يطالب بـPython 3.12 «لأن المشروع Django 6» بينما requirements يثبّت 5.1 لأن السيرفر 3.10 — *(البوابة كانت تمنع النشر على البيئة الصحيحة نفسها)* | `deploy.ps1` |
| ✅ P2-6 | لا `SECURE_PROXY_SSL_HEADER`/`SECURE_SSL_REDIRECT` خلف الخادم الأمامي؛ CORS regex يسمح بأي منفذ localhost حتى في الإنتاج — *(`SECURE_SSL_REDIRECT` خلف عَلَم: بلا الترويسة يُنتج حلقة توجيه لا نهائية)* | `core/settings.py` |
| ✅ P2-7 | `puppeteer` (~300MB) في `dependencies` بدل `devDependencies` — *(مستهلكه الوحيد `check.cjs`، سكربت تطويري لا يستورده كود التطبيق)* | `frontend_v2/package.json` |
| ✅ P2-8 | `firestoreService` (2,600+ سطر) مستورَد ثابتاً في shell الواجهة — *(**الحزمة الرئيسية 360.59 kB ← 313.63 kB**؛ `AuthContext` كان المرساة الثانية الخفية)* | `frontend_v2/App.tsx` |
| ✅ P2-9 | ~10 طلبات إقلاع مبعثرة قبل رسم أي شاشة (4 منها قابلة للدمج) — *(`tenants/settings/current/` كانت تُجلب **أربع مرات**: سياقا المظهر والجلسة + الخطّاف مرتين. مصدر مشترك واحد، بلا أي تغيير خادمي)* | `frontend_v2/services/tenantSettingsApi.ts` |
| ✅ P2-10 | ثلاث طبقات HTTP متوازية — 109 `fetch` خام بلا مهلة/retry. **فُحص فوجِد مُغلقاً سلفاً، بلا تغيير:** الملفان يُظلّلان `fetch` بـ`apiFetch` (مهلة 30ث + إعادة محاولة لـGET). سطر التدقيق قديم | `inventoryApi.ts` · `accountingApi.ts` |
| ✅ P2-11 | `hr/user_api.py` — `user_detail` متاح لأي `is_staff` عبر الشركات — *(تحقّق سلبي: قبل الإصلاح ردّ 200 ببريد عضو شركة أخرى واسمه ودوره)* | `hr/user_api.py` |
| ✅ P2-12 | مواضع `order_by` غير حتمي تمنع ترقيماً مستقراً — *(`StockMovement` كان قد عولج ضمن P0-5؛ بقي الشيكات والحسابات)* | `accounting/views.py` |
| ✅ P2-13 | ترتيب أعمار الذمم المدينة: حلقة على كل فواتير الآجل منذ البداية بلا فلتر تاريخ — *(شرط «المتبقي > 0» صار في القاعدة + مدى تاريخ اختياري)* | `sales/views.py` |
| 🟨 P2-14 | قائمة أسعار العميل: تحميل كل بنود فواتير العميل + كل عروضه + كل منتجات الشركة. **نُفِّذ تخفيف (2026-08-11):** `select_related("invoice")` كان يبني نموذج بند كاملاً + صفّ فاتورة كاملاً لكل سطر باعه العميل يوماً والمستهلَك خمسة أعمدة — صار إسقاط `values()` بنفس الاستعلام والترتيب والدلالة (العقد لم يتغيّر بايتاً، اختبارات النقطة خضراء). **الإصلاح الجذري** (ترقيم/بحث خادمي) يبقى مفتوحاً بقرار: يكسر عقد `getCustomerPriceList` (يتوقّع مصفوفة كاملة) فيحتاج تغييراً منسّقاً واجهةً وخادماً | `sales/services/pricing.py:208` → `salesApi.ts:447` |

---

## §1 الاختناقات المؤكدة في البنية التحتية

### 1.1 الكاش — `core/settings.py:352-358`
`FileBasedCache` على `BASE_DIR/django_cache` بـTTL 300ث. بلا `MAX_ENTRIES` مخصص ⇒ الافتراضي **300 مدخل** و`CULL_FREQUENCY=3` (حذف ثلث الكاش عشوائياً عند الامتلاء، وكل `_cull` = `os.listdir` كامل). بلا قفل بين العمليات ⇒ عدّادات الـthrottle (تُخزَّن في نفس الكاش) عرضة لسباق. مع 3+ workers ومفاتيح dashboard لكل tenant/فترة، السقف يُتجاوز فوراً.
**جرد الاستخدامات (كلها معزولة بـtenant ✅):** dashboard (`core/dashboard_api.py:110-115,316`، TTL 60ث) · modules (`core/modules.py:44-45,76-83`) · plan_limits (`core/plans.py:227-244`) · reauth (`accountant_portal/services.py:53,69`) · ذاكرة المساعد (`core/assistant_memory.py:23-46`). `@cache_page` غير مستخدم إطلاقاً. **التغطية ضيقة جداً — لا كاش على أي قائمة أو تقرير.**

### 1.2 لا Celery / Redis / task queue
`requirements.txt` كاملاً: Django, DRF, cors-headers, dotenv, cloudinary×2, Pillow, mysqlclient, requests, websocket-client, sqlglot, **gunicorn**, pytest×2, coverage, import-linter. **لا celery، لا redis، لا django-redis، لا whitenoise** (تحقق بـgrep شامل). كل عمل ثقيل داخل دورة الطلب — القائمة الكاملة للمرشّحين في §6-Celery أدناه.

### 1.3 الترقيم — `core/pagination.py:11-19`
```python
def paginate_queryset(self, queryset, request, view=None):
    if 'page' not in request.query_params:
        return None          # ⇒ الجدول كاملاً
```
`page_size=50`، `max_page_size=200`. التعليق في `core/pagination.py:3-6` يوثّق أن الـopt-in مقصود لعدم كسر القوائم المنسدلة. تمييز حاسم للمرحلة 5:
- **`ModelViewSet.list`** → يُرقَّم عند تمرير `?page=` (قابل للإصلاح من العميل).
- **`viewsets.ViewSet.list` و`@action`** → لا يُرقَّم أبداً حتى مع `?page=`: دفتر الأستاذ (`accounting/views.py:576-693`)، تقرير الضريبة (`:865-997` — كل أسطر سنة كاملة)، التقارير الـ40+ (`core/reports_api.py:39-54`)، أعمار الديون (`sales/views.py:1259-1288`).

**قائمة الفئة أ (جداول ضخمة، opt-in فقط):** stock-movements (`inventory/views.py:689`) · journals (`accounting/views.py:277`) · sales/invoices (`sales/views.py:115`) · purchase-invoices (`logistics/views.py:2713`) · delivery-orders (`sales/views.py:726`) · deals (`logistics/views.py:426`) · logistics/payments (`logistics/views.py:1323`) · sales/payments (`sales/views.py:963`) · supplier-payments (`logistics/views.py:4145`).
**الفئة ب (متوسطة):** products (`inventory/views.py:81`) · partners (`partners/views.py:25`) · shipments (`logistics/views.py:1354`) · goods-receipts (`:4783`) · clearances (`:2204`) · quotations/orders/notes (`sales/views.py:1335,1445,1557`) · cheques (`accounting/views.py:176`) · accounts (`:76`).

### 1.4 CONN_MAX_AGE — **موجود، خلافاً لافتراض الخطة**
`core/settings.py:172-173`: `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True`، مع `charset=utf8mb4` ومهلات اتصال/قراءة/كتابة (`:174-180`). **بند المرحلة 5 رقم 3 يُشطب.** الملاحظة المتبقية: `init_command` يعطّل `foreign_key_checks` (P2-4).

### 1.5 TokenAuthentication — استعلام DB كل طلب
`core/settings.py:368-371` — DRF قياسي بلا أي كاش (لا يوجد `BaseAuthentication` مخصص في المشروع). كل طلب مصادَق = `Token.objects.select_related('user').get(key=...)`. يُضاف إليه في المسار الساخن: عضوية الشركة (`core/tenant_utils.py:130-135` — مغطاة بفهرس فريد ✅) و`Tenant.objects.count()` مرتين (`:89,96`). **الاستثناء المقلق:** رفع الوسائط بلا مصادقة أصلاً (`core/media_views.py:44-47`).

### 1.6 Throttle — accountant_portal فقط
6 مواضع كلها في `accountant_portal/views.py` (`:171,254,275,458,490,591`) بمعدلات 5–60/ساعة. **صفر throttle على بقية النظام** (تحقق بـgrep). وعدّادات الـthrottle الموجودة على FileBasedCache ⇒ عرضة للسباق والحذف العشوائي (§1.1).

**تحديث المرحلة 5 (P0-7 منفّذ 2026-08-11):** `UserRateThrottle`/`AnonRateThrottle` صارا في `DEFAULT_THROTTLE_CLASSES` بمعدّلات `300/min` و`60/min` (قابلة للضبط بـ`THROTTLE_RATE_USER`/`THROTTLE_RATE_ANON`). حقيقتان انكشفتا أثناء التنفيذ وتغيّران قراءة هذا البند:
- **نطاق `anon` أضيق مما يبدو:** `APIView.initial` ينفّذ `check_permissions` **قبل** `check_throttles`، فالطلب المجهول على نقطة تتطلب مصادقة يُردّ 401 ولا يُحتسَب في العدّاد. النقطة الوحيدة بـ`AllowAny` في المشروع كله هي `CurrencyViewSet` (`accounting/views.py:1884`) — فـ`anon` عملياً يحرسها وحدها ويبقى احتياطاً لأي نقطة عامة مستقبلية. (مغطّى باختبارين في `core/tests/test_global_throttle.py`.)
- **النافذة بالدقيقة لا بالساعة عمداً:** `SimpleRateThrottle` يخزّن طابعاً زمنياً لكل طلب داخل النافذة ويقرأ/يكتب القائمة كاملة عند كل طلب — نافذة `3000/hour` تعني pickle بـ3000 عنصراً لكل طلب على FileBasedCache، أي أن الحارس نفسه يصير الاختناق.

### 1.7 نقطة تسجيل الدخول خارج سلسلة الـthrottle كلياً — **مكتشَف في المرحلة 5**
`hr/auth_api.py:165` (`login_view`، المربوطة على `api/hr/auth/login/`) **ليست view من DRF** — دالة Django عادية بـ`@csrf_exempt` تُرجِع `JsonResponse`. لا `DEFAULT_THROTTLE_CLASSES` يمسّها ولا أي آلية قفل حساب في المشروع (grep على `ratelimit`/`lockout`/`axes` = صفر نتائج). النتيجة: **تخمين كلمات المرور بلا أي سقف**، وكل محاولة = استعلام `User` + `check_password` (تجزئة PBKDF2 مقصودة البطء) ⇒ سطح استنزاف CPU أيضاً. الإصلاح ليس في `DEFAULT_THROTTLE_RATES` بل حدّ صريح على النقطة نفسها (تحويلها لـ`@api_view` بـ`ScopedRateThrottle`، أو حدّ يدوي على الكاش بمفتاح IP+بريد). مسجَّل كـ**P0-13** في الجدول أعلاه.

---

## §2 N+1 — أسوأ الحالات (مرتّبة بالأثر)

> **تحديث المرحلة 5 (P0-9 منفّذ 2026-08-11):** البند 1 أدناه مُصلَح في
> `core/reports/financial.py` (الملف صار حزمة في المرحلة 3) عبر
> `annotate_purchase_invoice_payment_summary` — الملخّص كله subqueries داخل
> استعلام القائمة الواحد، وهي نفس الدالة المستخدَمة أصلاً في قائمة فواتير
> الشراء فالحساب واحد لا اثنان.
> **وانكشف خلل وظيفي أخطر من الأداء:** التقرير كان يقرأ المفتاح `remaining`
> من `purchase_invoice_payment_summary`، وهو **مفتاح غير موجود** (الفعلي
> `remaining_balance` — `core/payments.py:196-205`) ⇒ كل سطر يُقيَّم بمتبقٍّ صفر
> فيُستبعَد، أي أن **تقرير أعمار الدائنين كان يعود فارغاً دائماً** بعد تنفيذ
> ~20 ألف استعلام. مغطّى الآن بحارسين في `core/tests/test_reports.py`
> (`PayablesAgingTest`): صحّة القيمة، وثبات عدّ الاستعلامات بين فاتورة واحدة
> وسبع فواتير.

1. **🔴 تقرير أعمار الدائنين** — `core/reports.py:921-928` يستدعي `purchase_invoice_payment_summary` (`logistics/services.py:473-518`) لكل فاتورة: `fees` + `supplier_payments`×`allocations` + `payment_allocations`×`payment` + `payments` = ≥6 استعلامات/فاتورة على **كل** الفواتير المرحّلة (بلا فلتر تاريخ — `as_of` للتصنيف فقط `core/reports.py:902`). 3,000 فاتورة ⇒ ~20,000 استعلام/طلب.
2. **🔴 إرساليات البيع** — `sales/serializers.py:901-904` (`obj.partner.name` بلا select_related) و`:912-921` (`obj.invoice.lines.all()` بلا prefetch) = استعلانان/صف على قائمة غير مرقّمة. الإصلاح سطران في `sales/views.py:737-739`.
3. **🔴 Landed Cost** — `logistics/views.py:4612` حلقة 200 شحنة → `:4629` links/شحنة → `:4639` items/صفقة → `:4648-4650` أربعة استعلامات فاتورة/صفقة ⇒ ~4,000 استعلام.
4. **🟠 قائمة القيود** — الأنواع الرئيسية معالجة بخرائط مسبقة (`accounting/views.py:344,357,366` ✅) لكن `LOGISTICS_CLEARANCE_PAYMENT` بلا خريطة ⇒ استعلام/صف (`accounting/serializers.py:127-142`).
5. **🟠 دفتر الأستاذ** — توسيع الشجرة تعاودياً: استعلانان/حساب (`accounting/views.py:594-614`) + `line.journal.currency` غير مسبّق (`:682`).
6. **🟠 ready_to_ship** — `self.action != 'list'` ⇒ يأخذ الفرع التفصيلي من `get_queryset` فيسحب prefetch كامل لكل صفقات الشركة ثم يرمي أغلبها (`logistics/views.py:535-573,485-498`).
7. **🟠 استلام مخزون الشحنة (signal)** — `logistics/signals.py:244-254` → `inventory/services.py:456-481`: استعلام فاتورة/صفقة + `exists()` لكل بند + إعادة حساب رصيد.
8. **🟡 المنتجات** — `reserved_quantity_map` (تجميع على كل بنود الطلبيات المؤكدة) يُستدعى في كل action حتى `retrieve` (`inventory/views.py:122-128`) + 3 تجميعات `Sum` على جدول الحركات لكل صف (`:174-186`).

**حلقات استعلام إضافية:** `logistics/landed_cost.py:723-728,1024-1027,1134-1144` · `logistics/accruals.py:67-77` · `logistics/services.py:73-90` · `accounting/services.py:173-178,226-228` · `JournalLine.objects.create` داخل حلقات بدل `bulk_create` (`accounting/views.py:438-439`، `logistics/views.py:1234-1235,2646-2647`، `sales/views.py:433-434`).

**معالجات موجودة تُحترم ولا تُلمس:** `PagePartnerBalanceMixin` (`core/api_defaults.py:39-53`) · قائمة الشحنات بـSubquery (`logistics/views.py:1396-1443`) · ميزان المراجعة بتجميعتين (`accounting/views.py:749-785`) · شجرة التصنيفات باستعلام واحد (`inventory/views.py:58-75`).

---

## §3 الفهارس

**الجرد الفعلي:** 56 `models.Index` + 7 `db_index=True` + 25 `unique_together` + 23 `UniqueConstraint`. التوزيع مختلّ: logistics 11 و hr 9 و sales 8، مقابل **inventory فهرس مركّب واحد** (`inventory/models.py:363-366`) و**tenants/realestate صفر**.

### المفقود الحرج (كل اقتراح مربوط باستعلام فعلي)

**`StockMovement` (`inventory/models.py:261-264` — بلا أي فهرس):**
```
(tenant, product, movement_date)          ← inventory/services.py:901، views.py:401
(tenant, -movement_date, -id)             ← inventory/views.py:733 + core/reports.py:1180
(tenant, reference_type, reference_id)    ← inventory/services.py:312,385,476 · logistics/views.py:2050
(tenant, warehouse, product)              ← core/reports.py:1188
```

**`JournalLine` (`accounting/models.py:152-155` — فهرس واحد):**
```
(tenant, partner)             ← core/reports.py:999-1006 (أرصدة الشركاء = full scan حالياً)
(tenant, journal)             ← تجميعات الميزان accounting/views.py:735+
(tenant, account, journal)    ← accounting/views.py:650-655
```

**المدفوعات:** `CustomerPayment`/`SupplierPayment` (`sales/models.py:818-820,862-864` — صفر فهارس): `(tenant,-payment_date,-id)` + `(tenant,partner,-payment_date)` ← `sales/views.py:972-985`، `logistics/views.py:4148-4162`، `core/reports.py:1282-1311`.

**`PurchaseInvoice`** (`logistics/models.py:1618-1622`): الفهارس الحالية لا تطابق الفلترة الفعلية (`logistics/views.py:2750-2790`): يلزم `(tenant,status,-created_at)` + `(tenant,is_posted,is_return)` ← `core/reports.py:734,921`؛ وفهرس `(status)` المفرد عديم القيمة.

**`SalesInvoice`** (`sales/models.py:544`): `(tenant,status,invoice_date)` لا يُستخدم عند غياب `status` (فجوة عمود أوسط) — يلزم `(tenant,-invoice_date,-id)` + `(tenant,branch,-invoice_date)` ← `sales/views.py:129-180`.

**`Partner`** (`partners/models.py:76` — بلا فهارس): `(tenant,partner_type,-created_at)` ← `partners/views.py:185-199`.

**logistics بلا فهارس:** Deal (`logistics/models.py:558`) · Shipment (`:981`) · Clearance (`:1110`) · SupplierQuotation (`:155`) · PurchaseOrder (`:329`) — اقتراحات `(tenant,status,ترتيب)` موثقة باستعلامات `logistics/views.py:102-120,309-320,436-450,1363-1405`.

**فهرس مُهدَر:** `accounting/views.py:410` يفلتر `reference_type/reference_id` بلا `tenant` ⇒ الفهرس `idx_jh_tenant_ref` (عموده القائد tenant) لا يعمل ⇒ full scan عند كل عكس قيد (انظر أيضاً P1-6).

---

## §4 عزل الـTenant

### خروقات فعلية (P0)
- **`core/agent_db_view.py:48-51`** (`api/agent/query/` في `core/urls.py:54`): `@authentication_classes([])` + `@permission_classes([])`، ينفّذ SQL خاماً (`:81`) بحارس وحيد = مفتاح ثابت مشترك (`:59-61`) ومرشّح regex قائمة-سوداء قابل للتجاوز (`:24-32`). **صفر فلترة tenant — قراءة بيانات كل الشركات.**
- **`bridge/views.py:21-29`**: `GLOBAL_COLLECTIONS` تشمل بيانات حضور ونقاط موظفين، و`_list_under_prefix` (`:200-202`) لا يفلتر tenant لها ⇒ مقروءة عبر الشركات. (`users` محمية جزئياً بـ`:373-380`.)
- **`bridge/views.py:353-359,417-420,458-461`**: وثائق `tenant_id IS NULL` مقروءة/قابلة للكتابة من أي شركة، وأول كاتب «يتبناها» (`doc.tenant = tenant`).

### ثغرات نمطية (P1)
- 4 مواضع `get_queryset` تُرجع غير مفلتر عند `tenant=None` بدل `.none()`: `tenants/views.py:49-54,100-105` · `sales/views.py:748-752,1564-1569` — نفس النمط الذي أُصلح سابقاً باسم task11 M7 في بقية المشروع.
- `realestate/views.py:20-25`: صنف اسمه `TenantScopedViewSet` **لا يفلتر شيئاً** — يوفّر `_tenant()` ويترك الفلترة لكل وارث بنمط `filter(tenant=None)` الهش (`:31-33,51-53,63-65,78-80,97-99`).
- `sales/serializers.py:243` وأشباهه: `PrimaryKeyRelatedField(queryset=X.objects.all())` يقبل pk من أي شركة عند الكتابة.
- `accounting/views.py:315-320`: بحث `icontains` على `LogisticsPayment` بلا tenant (مطابقات زائفة، لا تسريب صفوف).
- `accounting/services.py:592`: `post_journal` لا يتحقق أن الحسابات من نفس الشركة (آمن حالياً لأن الحسابات من كود داخلي — خطر مستقبلي).
- `hr/user_api.py:23-26`: `user_detail` لأي `is_staff` عبر الشركات.

### السليم (تُحقّق منه بالقراءة)
كل `get_queryset` الرئيسية في sales/accounting/inventory/logistics/partners/hr تفلتر tenant وتعيد `.none()` عند غيابه، والـ`@action` الحساسة مقيّدة صراحة (أمثلة: `logistics/views.py:1626,1782`، `inventory/views.py:747`، `accounting/views.py:1637`). `core/reports.py` يمرّر `tenant_id` لكل دالة. كل مفاتيح الكاش تحمل tenant. **الآلية المركزية** `core/mixins.py:7-37` (`BaseTenantViewSet`) موجودة لكنها تغطي ~15 من ~50 ViewSet — الباقي يكرّر المنطق يدوياً، وهذا التكرار هو مصدر كل الثغرات النمطية أعلاه.

---

## §5 الواجهة الأمامية (frontend_v2)

- **~92% من القوائم غير مرقّمة:** 131 `apiGetList` مقابل 16 `apiGetPagedList` (`services/restApi.ts:265-306,312-349`). لا page افتراضي في الـclient.
- **أخطر الشاشات:** ItemsManagement (P0-12) · InventoryValuationPage تجلب **كل حركات المخزون** (`:130-136`) · AccountingJournalEntryPage تجلب **كل القيود** لأزرار سابق/تالي (`:291`) · فخّ `page_size` بلا `page` = بلا أي تقييد (`activityService.ts:34`، `GoodsReceiptsPage.tsx:167`).
- **Virtualization: صفر** — كل الجداول `rows.map()` في DOM (`AseelDenseTable.tsx:232`، `GroupedItemsTable.tsx:59`).
- **حمل خفي:** `listPickerProducts` بلا حد — موثّق في الكود: «1490 صنفاً → 609KB / 331ms» (`inventoryApi.ts:471-480`) × 9 شاشات؛ وإعادة جلب الكتالوج/المهام الكاملة على كل `focus`/`visibilitychange` لكل تبويب (`firestoreService.ts:1406-1411`، `sqlApiClient.ts:224-231`) — مصدر spikes غير متوقعة مع 500 مستخدم.
- **طلبات الإقلاع:** ~10 طلبات قبل أول شاشة (`contexts/*.tsx`، `App.tsx:515,722,732`) — 4 منها قابلة للدمج في bootstrap واحد. Dashboard الشاشة الوحيدة المجمّعة خادمياً ✅ (`dashboardApi.ts:8-19`).
- **Bundle:** 97 صفحة lazy ✅ (`App.tsx:65+`) لكن `firestoreService` (2,600+ سطر بمنطق المشتريات كله) مستورد ثابتاً في الـshell (`App.tsx:32-47`)؛ `puppeteer` في dependencies؛ `manualChunks` يغطي react/dexie/icons فقط (`vite.config.ts:48-56`).
- **لا caching/dedup:** لا react-query/swr؛ كاش IndexedDB يُكتب على كل استجابة ولا يُقرأ إلا أوفلاين (`restApi.ts:184-215,292`)؛ 109 استدعاء fetch خام بلا مهلة في `inventoryApi`/`accountingApi`.

---

## §6 النشر

- **الأمر الفعلي** (`deploy.ps1:189-195`): `gunicorn --bind 127.0.0.1:8000 --workers 3 --daemon` — sync workers، بلا `--threads`، بلا `--timeout`، بلا `--pid`؛ إعادة تشغيل بـ`pkill` + `sleep 1` (انقطاع كامل). **السعة القصوى = 3 طلبات متزامنة.**
- مهلة gunicorn الافتراضية 30ث < مهلة المساعد 60–120ث (`core/settings.py:302-304,329`) ⇒ الـworker يُقتل أثناء استدعاء المساعد.
- `DEBUG` آمن افتراضياً (`core/settings.py:58`)؛ `ALLOWED_HOSTS` قائمة صلبة (`:60-65`)؛ HSTS + secure cookies عند الإنتاج (`:75-79`) لكن بلا `SECURE_PROXY_SSL_HEADER`.
- static/media: لا whitenoise؛ `collectstatic` في النشر (`deploy.ps1:334`) والتقديم موكول لخادم أمامي خارج الريبو؛ الرفع الفعلي إلى Cloudinary (`core/media_views.py:45-52`).
- لا نشر من CI — `.github/workflows/ci.yml` اختبارات وبناء فقط (على SQLite ⇒ **لا شيء يختبر MySQL أو الكاش الحقيقي تحت تزامن**).
- تناقض موثّق: `deploy.ps1:228-231` يطالب بـPython 3.12 بحجة Django 6، وrequirements يثبّت 5.1 للسيرفر 3.10 (`requirements.txt:9-11`).

### مرشّحو Celery (للمرحلة 6 — القرار بالقياس لا هنا)
رفع Cloudinary المتزامن (`core/media_views.py:79`) · الترحيل الدفعي لفواتير الشحنة (`logistics/views.py:3260-3360`) · استلام مخزون الشحنة عبر signal (`logistics/signals.py:244-261`) · إعادة حساب أرصدة الأصناف (`inventory/services.py:268-299`) · التقارير الـ40+ (`core/reports.py:203-233`) · ترحيل فاتورة الشراء ~640 سطر منطق (`logistics/views.py:3398-4040`) · إقفال السنة (`accounting/views.py:1773,1821`) · Landed Cost (`logistics/views.py:4588`) · إعادة مطابقة COGS والجرد (`inventory/services.py:1107-1150,1274-1310`).

---

## التوصية: ترتيب تنفيذ المرحلة 5

> P0 فقط، بند = commit = اختبارات خضراء. بنود الأمن أولاً لأنها الأرخص والأخطر.

1. **أمن (يوم واحد):** P0-2 (حذف/تقييد `agent_db_view`) ← P0-3 + P0-4 (bridge) ← P0-8 (مصادقة+throttle على الرفع).
2. **إعدادات (يوم واحد):** P0-6 (Redis مع fallback LocMemCache للتطوير/الاختبار، وتأكد أن `core/test_settings.py` يبقى على Dummy) ← P0-7 (throttle عام) ← P1-14 (إيقاف BrowsableAPIRenderer — شبه مجاني، يُضم هنا).
3. **نشر (ساعة):** P0-1 — رفع workers (مثلاً `--workers 2×cores+1` أو gthread بـ`--threads`) + `--timeout` يناسب المساعد + graceful reload. *(ملاحظة: تعديل `deploy.ps1` وليس كود Python — الأثر الأكبر بأقل خطر.)*
4. **فهارس (migration واحد، نصف يوم):** P0-10 + P0-11 + P1-4 معاً — الفهارس لا تكسر سلوكاً.
5. **استعلامات (يوم):** P0-9 (أعمار الدائنين) ← P1-1 (سطرا الإرساليات) ← P1-6 (tenant في فحص العكس).
6. **الترقيم (الأكبر — 2-3 أيام):** P0-5 endpoint-by-endpoint مع مستهلك الواجهة في نفس الـcommit، بدءاً بـstock-movements ثم journals ثم الفواتير. القوائم المنسدلة تأخذ حداً أقصى (النمط الموجود في `partners/views.py:218-222` سقف 500) بدل ترقيم كامل. **يتطلب أولاً إضافة `order_by` حتمي حيث ينقص** (P2-12).
7. **واجهة (يوم-يومان):** P0-12 (ItemsManagement: بحث خادمي + ترقيم فعلي) وأسوأ شاشات P1-10.

**خارج المرحلة 5 صراحةً:** Celery (قرار المرحلة 6 بالقياس) · P1-5 (tenant FK على LogisticsPayment — migration بيانات يستحق مهمة مستقلة) · بنود P2.
