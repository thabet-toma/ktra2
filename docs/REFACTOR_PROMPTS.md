# برومتات الفصل المعماري + جاهزية 500 مستخدم — K.T.R.A

> **طريقة الاستخدام:** كل مرحلة = برومت واحد يُنسخ كاملاً في **جلسة وكيل جديدة ومستقلة**.
> ممنوع تشغيل أكثر من مرحلة في نفس الجلسة — هذا يعيد مشكلة انتفاخ السياق نفسها.
>
> **الترتيب المقترح:** ~~0~~ ← 1 ← 4 ← 2 ← 3 ← 5 ← 6
> (المرحلة 4 تحليل خالص بصفر خطر، وتنفيذها مبكراً يعطي صورة الأداء قبل الجراحة.)
>
> **قبل أي مرحلة:** `python manage.py test --settings=core.test_settings` يجب أن تكون خضراء.
> لو مش خضراء — إصلاحها هي المهمة الأولى.

## سجلّ التنفيذ

| المرحلة | الحالة | الفرع / commit | التحقق |
|---|---|---|---|
| 0 — فصل السياق | ✅ منفّذة 2026-08-11 | `newktra` / `7a23fbf` | 1,025 اختباراً خضراء قبل وبعد · صفر تعديل على `.py`/`.ts`/`.tsx` |
| 1 — خريطة اعتماديات + حاجز | ✅ منفّذة 2026-08-11 | `claude/youthful-mccarthy-horm0b` | 1,025 اختباراً خضراء · `lint-imports`: 3 kept, 0 broken |
| 2 — accounting facade | ⬜ | — | — |
| 3 — تفكيك الملفات العملاقة | ⬜ | — | — |
| 4 — تدقيق جاهزية 500 مستخدم | ⬜ | — | — |
| 5 — تنفيذ P0 | ⬜ | — | — |
| 6 — اختبار حمل + قرار Celery | ⬜ | — | — |

### نتائج المرحلة 0 (ما يهم المراحل التالية)

**المُنجَز:** `ARCHITECTURE.md` (141 سطراً) · `docs/modules/*.md` لـ8 apps (1,021 سطراً، من قراءة الكود لا من PROJECT_MAP) · نقل `PROJECT_MAP.md` إلى `docs/history/` بـ`git mv` · قسم «قراءة السياق» في `CLAUDE.md`. رُوجعت عيّنة من مراجع `file:line` عبر الملفات الثمانية ووُجدت دقيقة.

**تصحيحان في `CLAUDE.md` كانا يضلّلان الوكيل:**
- الـviews/serializers في **جذر كل app** (`sales/views.py`) — القاعدة القديمة «في `api/`» لم تكن مطابقة للواقع.
- عدد الاختبارات الفعلي **1,025** لا 70. (وانتبه: `pytest.ini` لا يشمل `accountant_portal`/`after_sales`/`device_registry` — استخدم `manage.py test` للتغطية الكاملة.)

**اكتشافات معمارية للمراحل القادمة:**
- **للمرحلة 2:** المتجاوزون لـ`post_journal` المؤكّدون: `logistics/views.py:1223-1265` و`:2633-2660` (قيد عكسي يدوي + `.update(is_posted=False)`)، و`partners/signals.py:202` (`create_opening_balance_entry` يكتب `is_posted=True` مباشرةً بلا فحص فترة ولا audit log، وأكواد حسابات hardcoded: `2101/1103/2106-2109` والرصيد الافتتاحي `3300`، و`Account.DoesNotExist` تُبتلع بـ`pass`).
- **للمرحلتين 1-2:** اعتماد معكوس الاتجاه: قرار «السماح بالمخزون السالب» يسكن في `sales.SalesSettings`، فتستورده `inventory.services.record_stock_movement` كسولاً (`inventory/services.py:208`) — inventory يعتمد على sales لا العكس.
- **للمرحلة 3:** `hr` لا يملك `services.py` — منطقه في `hr/payroll.py`؛ و`partners` بلا `services.py` إطلاقاً (منطقه في views/signals).
- **بيئة التنفيذ:** حاوية الوكيل لا تأتي بـDjango مثبّتاً — أول أمر في أي جلسة تنفيذ: `pip install -r requirements.txt` (يكفي: Django, DRF, cors-headers, dotenv, cloudinary×2, Pillow, requests, websocket-client, sqlglot, pytest, pytest-django). الاختبارات تأخذ ~3.5 دقيقة.

---

## لماذا هذه الخطة؟ (التشخيص — مرجع سريع)

المشروع: 87,500 سطر Python / 13 Django app / React SPA. بطء الوكيل سببه 4 «ضرائب» يدفعها قبل أول سطر تعديل:

1. **ضريبة السياق:** `PROJECT_MAP.md` = 8,104 سطر changelog، ولا يوجد `ARCHITECTURE.md`. *(عولجت في المرحلة 0.)*
2. **ضريبة الملفات العملاقة:** `logistics/views.py` = 5,050 سطر · `sales/services.py` = 4,087 · `logistics/serializers.py` = 2,466 · `core/reports.py` = 2,350.
3. **ضريبة التشابك:** `accounting.models` (Account/JournalHeader/JournalLine) god module مستورد مباشرة من 8 apps. أمثلة موثّقة:
   - `logistics/views.py:1223-1265` ينشئ ويعكس قيوداً يدوياً متجاوزاً `accounting.services`
   - `partners/signals.py` ينشئ حسابات وقيوداً افتتاحية بأكواد hardcoded (`"Supplier": "2101"`)
   - `logistics/serializers.py:11-12` يستورد داخليات `sales.serializers`
   - 5 نماذج دفع منفصلة (انظر `docs/decisions/payment_model_unification.md`)
4. **ضريبة التحقق:** فشل اختبار بـapp آخر بسبب التشابك = دورة تصليح إضافية.

اختناقات التوسّع المؤكدة (من `core/settings.py` + `requirements.txt`):
`FileBasedCache` (كاش معطّل عملياً مع تعدد workers) · لا Celery/Redis/task queue · الترقيم opt-in فقط (`OptionalPageNumberPagination`) · لا `CONN_MAX_AGE` · 34 فهرساً فقط عبر كل المشروع · throttle مقتصر على accountant_portal · `TokenAuthentication` = استعلام DB لكل request.

---

## المرحلة 0 — فصل السياق (2-3 ساعات · صفر تعديل منطق) — ✅ منفّذة (`newktra` / `7a23fbf`)

```text
اقرأ الكود الفعلي للمشروع (مش PROJECT_MAP.md — هو changelog تاريخي وممكن يكون قديم)
وأنشئ توثيقاً معمارياً مضغوطاً يقرأه وكيل AI بدل ما يقرأ 8,104 سطر تاريخ.

المطلوب بالضبط:

1. ARCHITECTURE.md في جذر المشروع — أقل من 200 سطر:
   - جدول الـ13 app: الاسم، المسؤولية بجملة واحدة، عدد الأسطر
   - مخطط الاعتماديات الحالي بين الـapps (نصي، مش صورة)
   - قواعد عابرة للنظام: عزل الـtenant عبر tenant_id، مكان الـservices، أين توضع الـserializers/views
   - "أين أبدأ" لكل نوع مهمة شائعة (فاتورة بيع، قيد محاسبي، حركة مخزون، رحلة استيراد)

2. docs/modules/<app>.md لكل app من: sales, accounting, inventory, logistics,
   partners, tenants, hr, accountant_portal — كل ملف أقل من 150 سطر ويحتوي:
   - الغرض بفقرة واحدة
   - أهم 5-8 ملفات مع سطر شرح لكل واحد
   - الـmodels الأساسية وعلاقاتها
   - دوال الـservices العامة (التوقيعات فقط)
   - الـAPI endpoints الرئيسية
   - اعتمادياته على apps تانية، ومين بيعتمد عليه
   - قواعد لا يجوز كسرها (مستنتجة من الكود والاختبارات)
   - ملفات الاختبار المهمة

3. انقل PROJECT_MAP.md إلى docs/history/PROJECT_MAP.md بـ git mv (حافظ على التاريخ).

4. عدّل CLAUDE.md: أضف قسم "قراءة السياق" ينص على أن الوكيل يقرأ
   ARCHITECTURE.md + ملف الموديول المعني فقط، وأن docs/history/PROJECT_MAP.md
   مرجع تاريخي لا يُقرأ افتراضياً.

قيود صارمة:
- ممنوع تعديل أي ملف .py أو .ts/.tsx
- ممنوع اختلاق معلومات: أي شي مش متأكد منه اكتبه بصيغة "غير موثّق — يحتاج تأكيد"
- كل ادعاء في التوثيق لازم يكون مبني على ملف قرأته فعلاً

في النهاية: شغّل python manage.py test --settings=core.test_settings وتأكد إنها خضراء
(لازم تكون، لأنك ما لمست كود).
```

---

## المرحلة 1 — خريطة اعتماديات + حاجز آلي (2-3 ساعات · صفر تعديل منطق)

```text
حلّل الاعتماديات بين الـDjango apps في هذا المشروع وضع حاجزاً آلياً يمنع تفاقمها.
لا تصلح أي تشابك في هذه المهمة — تحليل وحاجز فقط.

1. أنشئ docs/DEPENDENCIES.md يحتوي:
   - جدول كامل: لكل زوج (app_A → app_B) عدد الـimports العابرة، مقسومة إلى:
     (أ) استيراد services/api — مقبول
     (ب) استيراد models مباشرة — تشابك
     (ج) استيراد serializers/views/داخليات — تشابك خطير
   - استثنِ migrations والاختبارات من العدّ لكن اذكرها منفصلة
   - قائمة أعلى 15 نقطة تشابك مرتّبة بالخطورة، كل وحدة مع file:line
   - تصنيف كل استيراد لـaccounting.models: هل ينشئ/يعدّل قيود (JournalHeader/JournalLine)
     أم مجرد قراءة؟ هذا التصنيف هو مدخل المرحلة الجاية
   - ترتيب مقترح لفكّ التشابك مع تبرير

2. أضف import-linter:
   - أضف import-linter لـrequirements.txt (وrequirements.local.txt إن وجد)
   - أنشئ .importlinter يوثّق العقود المطلوبة
   - **مهم:** ابدأ بالعقود في وضع "تحذير موثّق" — سجّل كل الانتهاكات الحالية
     في docs/DEPENDENCIES.md كـbaseline، ولا تكسر الـCI. الهدف منع تشابك *جديد*،
     مش كسر البناء اليوم.

3. أضف فحص import-linter لأي CI موجود (فتّش عن .github/workflows). إذا ما في CI،
   وثّق الأمر في docs/DEPENDENCIES.md ولا تنشئ CI جديد.

قيود صارمة:
- ممنوع تعديل أي ملف .py غير ما ذُكر أعلاه
- ممنوع نقل أو حذف أو إعادة تسمية أي شي
- شغّل الاختبارات في النهاية للتأكد
```

---

## المرحلة 2 — accounting facade (3-5 ساعات · الجراحة الأهم)

```text
أنشئ واجهة عامة واحدة لموديول المحاسبة وارحّل إليها كل الأماكن اللي بتنشئ قيوداً
من خارج accounting. الهدف: صفر تغيير في السلوك، فقط توحيد نقطة الدخول.

اقرأ أولاً: ARCHITECTURE.md، docs/modules/accounting.md، docs/DEPENDENCIES.md

1. أنشئ accounting/api.py — الواجهة العامة الوحيدة. صمّم التوقيعات من الاستخدامات
   الفعلية اللي رصدتها في DEPENDENCIES.md، وليس من فراغ. توقّع شيئاً قريباً من:
     post_document(tenant, source_doc, lines, *, date, description) -> JournalHeader
     reverse_document(tenant, journal_header, *, reason) -> JournalHeader
     ensure_partner_account(tenant, partner, account_type) -> Account
     get_account_by_code(tenant, code) -> Account
   أضف docstring لكل دالة يوضح الاستدعاء وضمانات الـatomicity.
   أعد استخدام accounting/services.py الموجود — لا تعيد كتابة منطق الترحيل.

2. رحّل نقاط الاستدعاء **واحدة واحدة**، بهذا الترتيب، وبـcommit منفصل لكل وحدة:
   أ. logistics/views.py:1223-1265 (إنشاء/عكس القيود يدوياً) — الأخطر والأوضح
   ب. باقي مواضع logistics
   ج. partners/signals.py — انقل منطق إنشاء الحسابات لـaccounting.api،
      وخلّي الـsignal ينادي الواجهة فقط. حافظ على نفس أكواد الحسابات بالضبط.
   د. باقي الـapps حسب ترتيب DEPENDENCIES.md

3. بعد كل خطوة:
   python manage.py test --settings=core.test_settings
   لو فشل أي اختبار — أصلحه قبل ما تكمل. ممنوع التراكم.

4. أضف اختبارات في accounting/tests/ تغطّي كل دالة في api.py.

قيود صارمة:
- **ممنوع تغيير أي سلوك محاسبي.** نفس القيود، نفس الحسابات، نفس المبالغ، نفس التواريخ.
  لو لقيت bug محاسبي أثناء الترحيل، وثّقه في تقرير منفصل ولا تصلحه هنا.
- ممنوع تعديل الـmodels أو إنشاء migrations. الـFKs المباشرة من sales/logistics
  على accounting.models تبقى كما هي في هذه المرحلة.
- ممنوع تغيير أي API response أو URL.
- لو أي اختبار كان أحمر قبل ما تبدأ، وقّف وأبلغني قبل أي تعديل.

في النهاية: تقرير بكل نقطة رحّلتها، وأي نقطة تركتها ولماذا.
```

---

## المرحلة 3 — تفكيك الملفات العملاقة (3-4 ساعات)

```text
فكّك أكبر ملفات المشروع لملفات أصغر حسب الـdomain، بدون أي تغيير في السلوك.
هذا refactor ميكانيكي بحت — نقل كود فقط.

الهدف بالترتيب:
1. logistics/views.py (5,050 سطر) → logistics/views/ package مقسّم حسب الرحلة:
   deals.py, shipments.py, clearance.py, transport.py, invoices.py, payments.py
   (اقرأ الملف أولاً وحدّد التقسيم الطبيعي — لا تفرض التقسيم أعلاه لو ما بيناسب)
2. sales/services.py (4,087) → sales/services/ package
3. logistics/serializers.py (2,466) → logistics/serializers/ package بنفس تقسيم الviews
4. core/reports.py (2,350) → core/reports/ package

لكل ملف:
- أنشئ package (مجلد + __init__.py) بنفس اسم الملف
- الـ__init__.py يعيد تصدير **كل** الأسماء العامة اللي كانت في الملف الأصلي،
  عشان أي `from logistics.views import X` قائم يظل شغّال
- انقل الكود كما هو حرفياً — ممنوع إعادة صياغة أو تحسين أو إصلاح
- استخدم git mv حيثما أمكن للحفاظ على التاريخ

بعد كل ملف:
python manage.py test --settings=core.test_settings
لو فشل — أصلح قبل الانتقال للملف التالي.

قيود صارمة:
- **صفر تغيير منطقي.** لا إعادة تسمية دوال، لا تحسين استعلامات، لا إصلاح bugs.
  لو شفت مشكلة، وثّقها في تقرير ولا تلمسها.
- ممنوع تغيير أي import path يستخدمه كود خارجي — الـ__init__.py هو ضمان التوافق
- ممنوع لمس urls.py أو أي API route
- commit منفصل لكل ملف مفكّك
```

---

## المرحلة 4 — تدقيق جاهزية 500 مستخدم (2-3 ساعات · تحليل فقط، صفر تعديل)

```text
دقّق جاهزية هذا المشروع (Django 5.1 + DRF + MySQL + gunicorn) لاستقبال ~500 مستخدم
متزامن مع نمو مستمر في الميزات. **لا تعدّل أي ملف** — التقرير فقط.

أنشئ docs/SCALABILITY_AUDIT.md يغطّي:

1. الاختناقات المؤكدة (تحقّق منها في الكود ووثّق file:line):
   - CACHES = FileBasedCache في core/settings.py — أثره مع gunicorn multi-worker
     ومع أكثر من سيرفر
   - لا Celery/Redis/task queue في requirements.txt — أي عمليات ثقيلة بتصير
     داخل دورة الـrequest؟ عدّد الـendpoints المرشّحة (تقارير، ترحيل دفعي،
     رفع Cloudinary، توليد فواتير، landed_cost)
   - OptionalPageNumberPagination — الترقيم opt-in. عدّد كل ViewSet/endpoint
     ممكن يرجّع قائمة غير محدودة، ورتّبها بحجم الجدول المتوقع
   - غياب CONN_MAX_AGE مع MySQL
   - TokenAuthentication → استعلام DB لكل request
   - DEFAULT_THROTTLE_RATES مقتصر على accountant_portal — لا throttle عام

2. N+1 queries: افحص الـviewsets الأكثر استخداماً (sales, logistics, inventory,
   accounting). حدّد الـendpoints اللي بتعمل استعلامات داخل حلقة أو بدون
   select_related/prefetch_related على FKs مسلسلة. رتّبها بالأثر.

3. الفهارس: 34 فهرس فقط عبر كل المشروع. حدّد الحقول اللي بتُفلتر أو تُرتّب عليها
   كثيراً وما عليها فهرس — خصوصاً tenant_id ومركّباته (tenant_id + date,
   tenant_id + status)، وحقول الربط في logistics/sales.

4. عزل الـtenant: هل في مسار ممكن يسرّب بيانات بين tenants تحت الحمل؟
   افحص أي queryset ما بيفلتر tenant_id، وأي cache key بلا tenant.

5. الواجهة (frontend_v2): أي شاشة بتجيب قوائم كاملة بدون ترقيم أو virtualization؟
   حجم الـbundle؟ عدد الـrequests عند فتح الشاشات الرئيسية؟

6. النشر: هل في إعداد gunicorn (عدد workers، النوع)؟ static files؟ media؟
   DEBUG في الإنتاج؟

الخرج: كل بند مصنّف P0 (يكسر عند 500 مستخدم) / P1 (يبطّئ بوضوح) /
P2 (دين تقني)، مع تقدير جهد لكل واحد، وتوصية بترتيب التنفيذ.
ممنوع الافتراض — كل بند مربوط بـfile:line.
```

---

## المرحلة 5 — تنفيذ P0 من تدقيق التوسّع (حسب نتيجة المرحلة 4)

```text
اقرأ docs/SCALABILITY_AUDIT.md ونفّذ **بنود P0 فقط**، واحداً واحداً بـcommit منفصل.

الأولويات المتوقعة (عدّلها حسب التدقيق الفعلي):

1. Redis بدل FileBasedCache:
   - django-redis في requirements.txt
   - CACHES يقرأ REDIS_URL من البيئة، مع fallback لـLocMemCache في التطوير/الاختبار
   - تأكد إن core.test_settings ما بيعتمد على Redis
   - كل cache key لازم يحتوي tenant_id — افحص كل استخدام موجود للـcache

2. فرض الترقيم:
   - حوّل الترقيم من opt-in لـopt-out على الـendpoints اللي حدّدها التدقيق كخطرة
   - **مهم:** هذا بيكسر الواجهة. لكل endpoint بتغيّره، عدّل مستهلكه في frontend_v2
     في نفس الـcommit. لو الواجهة بتستخدمه لقائمة منسدلة، أضف حد أقصى
     (مثلاً 200 صف) بدل الترقيم الكامل.
   - لا تغيّر endpoint بدون ما تعدّل مستهلكه.

3. CONN_MAX_AGE = 60 و CONN_HEALTH_CHECKS = True في DATABASES

4. الفهارس المفقودة: migration واحد يضيف الفهارس اللي حدّدها التدقيق.
   ركّز على tenant_id المركّب. اختبر زمن الـmigration على حجم بيانات واقعي.

5. throttle عام: DEFAULT_THROTTLE_RATES يضيف user/anon rates معقولة
   بدون كسر الاستخدام الحالي.

6. N+1: أضف select_related/prefetch_related للـendpoints اللي حدّدها التدقيق.
   استخدم assertNumQueries في الاختبارات لتثبيت العدد بعد الإصلاح.

قيود صارمة:
- بند واحد = commit واحد = اختبارات خضراء
- ممنوع تنفيذ P1/P2 في هذه المهمة
- ممنوع إضافة Celery في هذه المرحلة — هي قرار معماري منفصل، وثّق التوصية فقط
- أي تغيير بيمس API response لازم يجي مع تعديل frontend_v2 المقابل
- شغّل python manage.py test --settings=core.test_settings بعد كل بند
```

---

## المرحلة 6 — اختبار حمل 500 مستخدم + قرار Celery (2-3 ساعات)

```text
تحقّق فعلياً من قدرة المشروع على استقبال 500 مستخدم متزامن بعد إصلاحات المرحلة 5،
وأصدر قرار Celery بناءً على القياس مش التخمين.

اقرأ أولاً: docs/SCALABILITY_AUDIT.md وتأكد أن بنود P0 نُفّذت فعلاً (git log).

1. جهّز اختبار الحمل:
   - أضف locust كاعتمادية تطوير فقط (requirements.local.txt أو ملف منفصل
     load_tests/requirements.txt — ممنوع إضافته لـrequirements.txt الإنتاجي)
   - أنشئ load_tests/locustfile.py يحاكي سيناريو واقعي:
     * تسجيل دخول والحصول على token
     * خليط مرجّح: 40% فتح قوائم (فواتير، منتجات، عملاء) · 25% فتح تفاصيل
       مستند · 15% إنشاء فاتورة بيع كاملة · 10% تقرير · 10% بحث/autocomplete
     * كل مستخدم افتراضي مربوط بـtenant — وزّع على 3-5 tenants على الأقل
       عشان نختبر العزل تحت الحمل مش بس الأداء
   - أنشئ سكربت seed (management command) يولّد بيانات بحجم واقعي:
     آلاف الفواتير والقيود والمنتجات لكل tenant. بدون بيانات واقعية
     الاختبار كذبة.

2. شغّل التدرّج: 50 → 150 → 300 → 500 مستخدم متزامن ضد بيئة تشبه الإنتاج
   (gunicorn multi-worker + MySQL — مش runserver ومش SQLite).
   سجّل لكل مستوى: p50/p95/p99 زمن استجابة، معدل الأخطاء، أبطأ 10 endpoints.

3. أنشئ docs/LOAD_TEST_RESULTS.md:
   - جدول النتائج لكل مستوى حمل
   - أبطأ endpoints مع تشخيص السبب (استعلام؟ حساب داخل request؟ serialization؟)
   - عتبة النجاح: p95 أقل من ثانيتين ومعدل أخطاء أقل من 1% عند 500 مستخدم.
     وثّق بوضوح: نجحنا أم لا، وعند أي مستوى بدأ التدهور.

4. قرار Celery (القسم الأهم في التقرير):
   - من نتائج القياس: هل في endpoints تتجاوز 3-5 ثواني تحت الحمل بسبب
     عمل ثقيل داخل دورة الـrequest (تقارير، landed_cost، ترحيل دفعي)؟
   - إذا نعم: وثّق قائمة المهام المرشّحة للنقل لـCelery مرتّبة بالأثر المقاس،
     مع تقدير جهد. إذا لا: وثّق صراحةً "Celery غير مطلوب عند هذا الحجم"
     مع الأرقام اللي تدعم القرار.
   - **لا تنفّذ Celery في هذه المهمة** — القرار والتوثيق فقط.

قيود صارمة:
- ممنوع تعديل أي كود إنتاجي لتحسين الأرقام أثناء هذه المهمة — لو لقيت
  اختناق جديد، وثّقه في التقرير كبند P0/P1 جديد ولا تصلحه هنا
- ممنوع تشغيل اختبار الحمل ضد بيئة إنتاج حقيقية فيها بيانات مستخدمين
- سكربت الـseed يشتغل فقط على قاعدة بيانات اختبار معزولة
```

---

## التحقق بعد كل مرحلة

```bash
python manage.py test --settings=core.test_settings
```

- بعد 1: `lint-imports` يمشي وينتج تقريراً مطابقاً للـbaseline الموثّق.
- بعد 2: اختبارات المحاسبة الموجودة خضراء + اختبارات `accounting/api.py` الجديدة.
- بعد 5: `assertNumQueries` على أثقل endpoints + مقارنة زمن استجابة قبل/بعد.
- بعد 6: `docs/LOAD_TEST_RESULTS.md` فيه حكم صريح نجاح/فشل عند 500 مستخدم + قرار Celery مُسبَّب بالأرقام.

## ديون مؤجلة عمداً (خارج هذه الخطة — مراحل مستقبلية)

- واجهة facade مماثلة لـ`inventory` (reserve/issue/reverse)
- فك `logistics/serializers.py:11` عن داخليات `sales`
- توحيد نماذج الدفع الخمسة (`docs/decisions/payment_model_unification.md`)
- نموذج `Attachment` الموحّد (`docs/decisions/attachments_model.md`)
- تنفيذ Celery إذا أوصت به المرحلة 6
