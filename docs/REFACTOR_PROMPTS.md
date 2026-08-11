# برومتات الفصل المعماري + جاهزية 500 مستخدم — K.T.R.A

> **طريقة الاستخدام:** كل مرحلة = برومت واحد يُنسخ كاملاً في **جلسة وكيل جديدة ومستقلة**.
> ممنوع تشغيل أكثر من مرحلة في نفس الجلسة — هذا يعيد مشكلة انتفاخ السياق نفسها.
>
> **الترتيب المقترح:** ~~0~~ ← 1 ← 4 ← 2 ← 3 ← 5 ← 6
> (المرحلة 4 تحليل خالص بصفر خطر، وتنفيذها مبكراً يعطي صورة الأداء قبل الجراحة.)
>
> **قبل أي مرحلة:** `python manage.py test --settings=core.test_settings` يجب أن تكون خضراء.
> لو مش خضراء — إصلاحها هي المهمة الأولى.

## ⬅️ الحالة الآن — تعليمات الجلسة القادمة (آخر تحديث: 2026-08-11)

**المُنجَز:** المراحل 0، 1، 2، 4 + جلسة معالجة ديون المرحلة 2 (`3358bf7`) + **الجلسة الأمنية** (P0-2/3/4/8 — «نتائج الجلسة الأمنية» أدناه). الفرع المعتمد لكل العمل: **`newktra`**.

**المهمة التالية: المرحلة 3 — تفكيك الملفات العملاقة.** انسخ برومت المرحلة 3 أدناه كاملاً في جلسة جديدة. قبلها اقرأ:
1. «نتائج المرحلة 2» أدناه — أرقام أسطر `logistics/views.py` تزحزحت بعد الترحيل (الملف الآن 4,994 سطراً)، والقيود الجديدة على أي كود منقول: كتابة القيود عبر `accounting.api`/`post_journal` فقط
2. «نتائج المرحلة 4» أدناه — فيها تعديلات إلزامية على بنود المرحلة 5. **تحديث:** بنود P0 الأمنية الأربعة (P0-2/3/4/8) نُفّذت في الجلسة الأمنية — تبقى للمرحلة 5 بنود الأداء فقط (P0-1 نشر، P0-5 ترقيم، P0-6 Redis، P0-7 throttle عام، P0-9/10/11 استعلامات وفهارس، P0-12 واجهة).

**دين جانبي مفتوح (أي وقت، جلسة قصيرة مستقلة):** 8 اختبارات pytest حمراء سابقة للمرحلة 2 في `sales/tests/test_quotation_{create,convert,pricing_link}.py` («لا توجد شركة محددة» من `SalesQuotationSerializer`) — لا تظهر في عدّاد `manage.py test`.

**خطوات أول جلسة تنفيذ (إلزامية):**
```bash
# 1. البيئة — الحاوية لا تأتي بـDjango، وmysqlclient يفشل بناؤه (لا حاجة له، الاختبارات SQLite):
pip install Django==5.1.15 djangorestframework==3.16.1 django-cors-headers==4.9.0 \
  python-dotenv django-cloudinary-storage cloudinary Pillow requests \
  websocket-client sqlglot pytest pytest-django
# 2. الفرع:
git fetch origin newktra && git checkout newktra
# 3. تحقق الخط الأساسي (~3.5 دقيقة، المتوقع: 1,025 OK + skipped=2):
python manage.py test --settings=core.test_settings
```

## سجلّ التنفيذ

| المرحلة | الحالة | الفرع / commit | التحقق |
|---|---|---|---|
| 0 — فصل السياق | ✅ منفّذة 2026-08-11 | `newktra` / `7a23fbf` | 1,025 اختباراً خضراء قبل وبعد · صفر تعديل على `.py`/`.ts`/`.tsx` |
| 1 — خريطة اعتماديات + حاجز | ✅ منفّذة 2026-08-11 | `newktra` / `bba8f77` | 1,025 اختباراً خضراء · `lint-imports`: 3 kept, 0 broken |
| 2 — accounting facade | ✅ منفّذة 2026-08-11 | `newktra` / `9801487`→`37efdd1` (5 commits) | 1,025 اختباراً خضراء بعد **كل** commit · +13 اختباراً لـ`api.py` (pytest) · `lint-imports`: 3 kept, 0 broken بعد حذف 6 أسطر baseline |
| 2-م — معالجة ديون المرحلة 2 | ✅ منفّذة 2026-08-11 (بتفويض صاحب المشروع) | `newktra` / `3358bf7` | `manage.py test` OK (skipped=2) · pytest: لا إخفاقات جديدة (الثمانية القديمة فقط) · +5 اختبارات (دورة العكس ×2، القيد الافتتاحي ×3) |
| أمن — عزل الـtenant + الرفع | ✅ منفّذة 2026-08-11 (بتفويض صاحب المشروع) | `newktra` / 3 commits | P0-2 + P0-8 + P0-3/P0-4 · `manage.py test` OK (skipped=2) · +12 اختباراً أمنياً |
| 3 — تفكيك الملفات العملاقة | ⬜ **التالية** | — | — |
| 4 — تدقيق جاهزية 500 مستخدم | ✅ منفّذة 2026-08-11 | `newktra` / `83dba7f` | 1,025 اختباراً خضراء قبل التدقيق · صفر تعديل كود · الخرج: `docs/SCALABILITY_AUDIT.md` |
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
- **للمرحلة 3:** `hr` لا يملك `services.py` — منطقه في `hr/payroll.py`؛ و`partners` بلا `services.py` إطلاقاً (منطقه في views/signals — *تحديث المرحلة 2:* الجانب المحاسبي من signals انتقل لـ`accounting/api.py`؛ بقي في partners الـviews فقط).

### نتائج المرحلة 2 (accounting facade — 5 commits: `9801487`→`37efdd1`)

**المُنجَز — `accounting/api.py` (496 سطراً بعد `3358bf7`) هو الواجهة العامة الوحيدة لكتابة القيود من خارج accounting:**
- `post_document(...)` — تفويض مباشر لـ`services.post_journal` بكل ضماناته.
- `reverse_journal(original, *, ...)` — نمط «القيد العكسي اليدوي» المنسوخ في logistics صار دالة واحدة داخل accounting بنفس السلوك حرفياً (قفل الأصل، فحص الفترة/الأسطر/التوازن بسماحية 0.02 وبنفس نصوص الرسائل، قلب مدين/دائن، خيارات نسخ العملة/`project_id` وإلغاء ترحيل الأصل مع وسمه). **ليست idempotent عمداً** — حارس إعادة الدخول على مستوى المستند (مثل `payment.is_posted`).
- `purge_journals(ids)` — الحذف الجماعي الإداري (كان في `purge_deals`).
- `get_account_by_code(tenant, code, *, active_only)` — قراءة حساب بالكود.
- `sync_partner_accounting` / `ensure_partner_account` / `create_partner_opening_balance` — منطق partners/signals المحاسبي منقولاً حرفياً (نفس الأكواد: آباء 2101/1103/2106-2109، رصيد افتتاحي 3300). *(القيد الافتتاحي صار عبر `post_journal` في `3358bf7` — انظر الديون المعالَجة بند 1.)*
- 13 اختباراً جديداً في `accounting/tests/test_api.py` (**pytest-style — تعمل بـ`python -m pytest` لا بـ`manage.py test`**، مثل بقية ملفات pytest في المشروع).

**النقاط المرحّلة (كلها بصفر تغيير سلوك، اختبارات خضراء بعد كل commit):**
| commit | الموضع | ما تغيّر |
|---|---|---|
| `0771ea6` (2-أ) | عكس قيد دفعة الصفقة (كان `logistics/views.py:1223`) | `reverse_journal(..., copy_project=True, unpost_original=True)` *(في `3358bf7` صار `copy_currency=True` بلا `unpost_original` — انظر الديون المعالَجة بند 3)* |
| `f6cda5f` (2-ب) | عكس قيد دفعة التخليص (كان `:2633`) | `reverse_journal(..., copy_currency=True)` |
| `f6cda5f` (2-ب) | استحقاق الشحن المحلي (كان `logistics/accruals.py:155`) | عبر `post_journal` — **استعاد idempotency المرجع `(LOCAL_SHIPMENT, pk)` وقفل السباق** وفحص طبيعة الحساب |
| `f6cda5f` (2-ب) | `logistics/signals.py:19` | حذف الاستيراد الميت لـ`accounting.models` |
| `4be8c90` (2-ج) | `partners/signals.py` | صار 27 سطراً — الـsignal ينادي `sync_partner_accounting` فقط |
| `37efdd1` (2-د) | المستوردون الأربعة + `purge_deals` + baseline | `ensure_partner_account` من `accounting.api`؛ حذف 6 أسطر من `.importlinter` (4 انتهاكات `partners.signals` + 2 من عقد `accounting.models`) |

**ما تُرك عمداً ولماذا:**
- **FKs المباشرة** على `accounting.models` في `sales/logistics` — خارج نطاق المرحلة نصاً (لا models ولا migrations).
- **قراءات `accounting.models`** (التقارير، accountant_portal، serializers، وقراءات `purge_deals` لجمع معرّفات القيود) — تحتاج واجهة قراءة (`DEPENDENCIES.md §5` بند 6)، قيمتها تنظيمية لا سلوكية.
- **إنشاء `Account` في** `tenants/services` (زرع الشجرة)، `sales/services:406,1953`، `logistics/services:824`، `hr/payroll:75,129` — كتابة حسابات لا قيود؛ مرشّحة للانتقال التدريجي لـ`accounting.api` عند لمس هذه الملفات (المرحلة 3 فرصة طبيعية).
- **استيرادا `logistics/serializers.py`** من داخليات sales/partners — في «الديون المؤجلة» أصلاً.
- **دورة `accounting → sales/logistics`** — تحتاج reference-resolver (`DEPENDENCIES.md §5` بند 5).

**الديون المحاسبية المكتشفة في المرحلة 2 — عولجت في `3358bf7` بتفويض صاحب المشروع (2026-08-11):**
1. ✅ **قيد الرصيد الافتتاحي** (`accounting/api.py::create_partner_opening_balance`): صار يمرّ عبر `post_journal` — فحص فترة مالية، توازن، audit log، وidempotency ذرّية على `(PARTNER_OPENING, partner.id)` بدل فحص `exists` غير المقفول (كان سباقان متزامنان يكرران القيد). **تغيير السلوك المقصود:** تاريخ رصيد في فترة مقفلة/غائبة لم يعد يُنشئ قيداً — يُسجَّل الخطأ ولا يسقط حفظ الشريك، وتصحيح التاريخ وإعادة الحفظ يعيدان المحاولة (مغطّى باختبارين).
2. ✅ **قرار: القيود العكسية معفاة عمداً من فحص طبيعة الحساب** (`debit_only/credit_only`): قلب الأطراف يعني أن حساباً «مدين فقط» يستقبل دائناً في العكس — فرض الفحص كان سيجعل قيوداً مشروعة غير قابلة للعكس. موثّق في docstring `reverse_journal`.
3. ✅ **توحيد نمطي العكس على نمط «الأصل يبقى مرحّلاً»** (نمط التخليص): إلغاء ترحيل دفعة الصفقة صار يبقي الأصل مرحّلاً وينشئ عكساً بعملته وسعره ⇒ صافي الأثر صفر اسمياً وبالأساسية، وتقارير الفترة الأصلية لا تتغيّر بأثر رجعي. النمط القديم كان **يُظهر أثر العكس وحده بإشارة معكوسة في التقارير المرحّلة** (الأصل يُستبعد والعكس يبقى). واكتُشف أثناء البحث خلل أعمق: **إعادة الترحيل بعد الإلغاء كانت تعيد استخدام قيد الدورة السابقة** (البحث الـidempotent في `post_journal` لا يفلتر `is_posted`) فتُوسم الدفعة مرحّلة بلا قيد جديد في الدفاتر — أُصلح بـ`idempotent=False` في `post_payment` (حارس التكرار الفعلي: قفل صف الدفعة + فحص `is_posted`). مغطّى باختباري دورة كاملة في `logistics/tests/test_deal_payment_unpost_cycle.py`.
   **بيانات تاريخية:** دورات إلغاء ترحيل قديمة (أصل غير مرحّل + عكس مرحّل) تبقى في القاعدة بأثرها المعكوس — فحصها عبر `logistics/payment_posting_diagnostics.py`، وتصحيحها قرار بيانات مستقل لم يُنفَّذ.
4. ⬜ **8 اختبارات pytest حمراء سابقة للمرحلة** (مؤكّدة على `63dbaa1` قبل أي تعديل): `sales/tests/test_quotation_{create,convert,pricing_link}.py` تفشل بـ«لا توجد شركة محددة» من `SalesQuotationSerializer` — لا تظهر في `manage.py test` (لا يجمع pytest-fixtures) فلم تدخل عدّاد 1,025. ما زالت مفتوحة — جلسة إصلاح مستقلة.

### نتائج الجلسة الأمنية (2026-08-11 — 3 commits، بند = commit، بتفويض صاحب المشروع)

بنود P0 الأمنية الأربعة من `docs/SCALABILITY_AUDIT.md` — كلها fail-closed، `manage.py test` أخضر بعد كل commit، +12 اختباراً أمنياً:

| P0 | الموضع | الإصلاح | اختبارات |
|---|---|---|---|
| **P0-2** | `core/agent_db_view.py` (نقطة SQL خام للوكيل، كانت بلا مصادقة إطلاقاً) | 3 طبقات: مصادقة Token لـ**superuser فقط** (`IsSuperUser`) + مفتاح `X-Agent-Key` (غيابه = 401 دائماً) + **تحليل نحوي `sqlglot`** (عبارة واحدة SELECT/WITH/UNION بلا INTO — القائمة السوداء صارت طبقة رابعة لا الوحيدة) + throttle `agent_query=120/hour` | `core/tests/test_agent_db_view.py` (8) |
| **P0-8** | `core/media_views.py` + `frontend_v2/components/PublicGallery.tsx` | `IsAuthenticated` بدل `AllowAny` (لا رفع مجهول يقفل worker) + throttle `media_upload=120/hour` + إخفاء قسم الرفع في PublicGallery للزوار (`canUpload` من وجود token) | `core/tests/test_media_upload.py` (+1، والبقية تصادِق بـToken) |
| **P0-3** | `bridge/views.py` `GLOBAL_COLLECTIONS` | إخراج `attendanceSessions/attendanceRecords/pointsHistory/departments` من العالمية ⇒ tenant-scoped (كانت مقروءة عبر كل الشركات). **الواجهة تقرأها من Firebase مباشرةً لا الـmapper — لا مستهلك مكسور** (تحقّق بالبحث). `departments` أُزيلت أيضاً من `PUBLIC_COLLECTIONS`. | `bridge/tests/test_mapper_isolation.py` (+3) |
| **P0-4** | `bridge/views.py` (`_get_doc_checked`/`_write`/POST) + هجرة `0004` | الوثيقة المُنطاقة بلا مالك (`tenant NULL`) لم تعد تُقرأ/تُكتَب/تُتبنّى من أي شركة (404) — حُذف «adopt legacy/unowned docs». هجرة `0004` تنسب اليتيمة الموجودة للشركة الافتراضية #1 (نمط `0003`) فلا تبقى وثيقة حيّة بلا مالك. | ضمن الملف أعلاه (يشمل P0-4) |

**قرار توثيقي:** الهجرة `0004` تنسب **كل** اليتيمة المُنطاقة لـ`tenant #1` (لا تخمّن المالك الحقيقي) — نفس اختيار `0003` للـ`tasks`. مبرَّر: اليتيمة بحكم التعريف بلا مالك، وفي الإنتاج الشركة #1 هي الأساسية والباقي أحدث؛ إن وُجدت بيانات يتيمة ذات مالك حقيقي مختلف، إعادة نسبتها مهمة بيانات مستقلة.

**لم يُنفَّذ (يبقى للمرحلة 5 — أداء لا أمن):** P0-1 (نشر gunicorn)، P0-5 (فرض الترقيم)، P0-6 (Redis)، P0-7 (throttle عام user/anon)، P0-9/10/11 (استعلامات وفهارس)، P0-12 (واجهة الأصناف). وبنود P1 الأمنية الأخف (P1-6 tenant في فحص العكس، P1-7 `.none()`، P1-8 `PrimaryKeyRelatedField`) بقيت موثّقة في التدقيق ولم تُلمس — أخف خطراً من الأربعة أعلاه.

### نتائج المرحلة 4 (تعدّل مدخلات المرحلة 5 — اقرأ `docs/SCALABILITY_AUDIT.md` كاملاً)

- **بند المرحلة 5 رقم 3 يُشطب:** `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True` موجودان فعلاً (`core/settings.py:172-173`).
- **بنود P0 جديدة غير متوقعة في الخطة الأصلية:** 3 ثغرات عزل tenant حرجة (SQL خام بلا مصادقة في `core/agent_db_view.py`، مجموعات bridge مشتركة بين الشركات، تبنّي وثائق يتيمة في bridge) + رفع وسائط مجهول بلا throttle (`core/media_views.py:44`) — تُنفَّذ أولاً في المرحلة 5.
- **الاختناق الأكبر ليس في كود Python:** gunicorn بـ3 sync workers (`deploy.ps1:189-195`) = سقف 3 طلبات متزامنة. إصلاحه سطر في سكربت النشر.
- عدد الفهارس الفعلي 56 `models.Index` (لا ~34)، لكن `StockMovement` (أضخم جدول) بلا أي فهرس و`JournalLine` بفهرس واحد.
- أسوأ endpoint منفرد: تقرير أعمار الدائنين ~20 ألف استعلام/طلب (`core/reports.py:921-928`).
- الواجهة: 131 استدعاء قائمة غير مرقّم مقابل 16 مرقّماً — فرض الترقيم (بند المرحلة 5 رقم 2) يجب أن يمشي endpoint-by-endpoint مع تعديل المستهلك في نفس الـcommit.

**بيئة التنفيذ:** حاوية الوكيل لا تأتي بـDjango مثبّتاً — أول أمر في أي جلسة تنفيذ: `pip install -r requirements.txt` (يكفي: Django, DRF, cors-headers, dotenv, cloudinary×2, Pillow, requests, websocket-client, sqlglot, pytest, pytest-django). الاختبارات تأخذ ~3.5 دقيقة.

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

## المرحلة 2 — accounting facade (3-5 ساعات · الجراحة الأهم) — ✅ منفّذة (`newktra` / `9801487`→`37efdd1`)

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
