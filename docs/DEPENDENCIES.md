# DEPENDENCIES — خريطة الاعتماديات بين الـApps

> المرحلة 1 من `docs/REFACTOR_PROMPTS.md` — تحليل ثابت (AST) للكود بتاريخ 2026-08-11.
> **عند تعارض هذا الملف مع الكود، الكود هو المرجع.**
>
> المنهجية: مسح كل ملفات `.py` في الـ13 app واستخراج كل `import` يعبر حدود app،
> مصنّفاً إلى: **(أ)** استيراد services/api وما شابه — مقبول ·
> **(ب)** استيراد `models` مباشرة — تشابك ·
> **(ج)** استيراد serializers/views/signals/داخليات — تشابك خطير.
> أوامر الإدارة (`management/commands`) محسوبة ضمن الكود؛
> **الاختبارات** مذكورة منفصلة في §2 و**الـmigrations لا تحتوي أي استيراد عابر** (صفر —
> Django يربط الـFKs العابرة بنص `('app','Model')` لا بـimport).

**الخلاصة الرقمية:** 531 استيراداً عابراً في الكود عبر 63 زوج (app→app) ·
647 في الاختبارات · 0 في الـmigrations.
الحاجز الآلي: `.importlinter` (3 عقود، baseline مسجّل) — انظر §6.

---

## §1 — الجدول الكامل: الكود (بدون اختبارات وmigrations)

| # | من → إلى | (أ) services/api | (ب) models | (ج) داخليات | المجموع |
|---:|---|---:|---:|---:|---:|
| 1 | `logistics` → `inventory` | 24 | 10 | 0 | **34** |
| 2 | `logistics` → `accounting` | 18 | 15 | 0 | **33** |
| 3 | `logistics` → `core` | 24 | 6 | 0 | **30** |
| 4 | `core` → `tenants` | 5 | 23 | 0 | **28** |
| 5 | `sales` → `accounting` | 11 | 12 | 0 | **23** |
| 6 | `core` → `sales` | 4 | 17 | 0 | **21** |
| 7 | `accounting` → `sales` | 4 | 15 | 0 | **19** |
| 8 | `core` → `logistics` | 1 | 17 | 0 | **18** |
| 9 | `accounting` → `logistics` | 3 | 14 | 0 | **17** |
| 10 | `accounting` → `tenants` | 0 | 17 | 0 | **17** |
| 11 | `accounting` → `partners` | 0 | 15 | 0 | **15** |
| 12 | `sales` → `core` | 14 | 0 | 0 | **14** |
| 13 | `core` → `inventory` | 0 | 13 | 0 | **13** |
| 14 | `inventory` → `core` | 9 | 4 | 0 | **13** |
| 15 | `accountant_portal` → `core` | 11 | 1 | 0 | **12** |
| 16 | `core` → `accounting` | 3 | 9 | 0 | **12** |
| 17 | `inventory` → `sales` | 3 | 8 | 0 | **11** |
| 18 | `sales` → `inventory` | 7 | 4 | 0 | **11** |
| 19 | `accounting` → `inventory` | 1 | 9 | 0 | **10** |
| 20 | `core` → `accountant_portal` | 6 | 4 | 0 | **10** |
| 21 | `logistics` → `partners` | 0 | 6 | 4 | **10** |
| 22 | `accounting` → `core` | 7 | 2 | 0 | **9** |
| 23 | `hr` → `core` | 9 | 0 | 0 | **9** |
| 24 | `logistics` → `sales` | 4 | 4 | 1 | **9** |
| 25 | `accountant_portal` → `sales` | 1 | 7 | 0 | **8** |
| 26 | `logistics` → `tenants` | 0 | 8 | 0 | **8** |
| 27 | `sales` → `tenants` | 2 | 6 | 0 | **8** |
| 28 | `accountant_portal` → `accounting` | 0 | 7 | 0 | **7** |
| 29 | `partners` → `core` | 5 | 2 | 0 | **7** |
| 30 | `core` → `partners` | 0 | 6 | 0 | **6** |
| 31 | `inventory` → `logistics` | 0 | 6 | 0 | **6** |
| 32 | `sales` → `partners` | 0 | 5 | 1 | **6** |
| 33 | `tenants` → `core` | 6 | 0 | 0 | **6** |
| 34 | `hr` → `tenants` | 1 | 4 | 0 | **5** |
| 35 | `inventory` → `accounting` | 3 | 2 | 0 | **5** |
| 36 | `accountant_portal` → `tenants` | 0 | 4 | 0 | **4** |
| 37 | `after_sales` → `core` | 4 | 0 | 0 | **4** |
| 38 | `device_registry` → `core` | 4 | 0 | 0 | **4** |
| 39 | `partners` → `accounting` | 3 | 1 | 0 | **4** |
| 40 | `hr` → `accountant_portal` | 2 | 1 | 0 | **3** |
| 41 | `hr` → `accounting` | 2 | 1 | 0 | **3** |
| 42 | `inventory` → `tenants` | 0 | 3 | 0 | **3** |
| 43 | `partners` → `logistics` | 1 | 2 | 0 | **3** |
| 44 | `realestate` → `core` | 3 | 0 | 0 | **3** |
| 45 | `sales` → `logistics` | 2 | 1 | 0 | **3** |
| 46 | `accounting` → `bridge` | 0 | 2 | 0 | **2** |
| 47 | `after_sales` → `inventory` | 0 | 2 | 0 | **2** |
| 48 | `bridge` → `inventory` | 1 | 1 | 0 | **2** |
| 49 | `core` → `hr` | 0 | 2 | 0 | **2** |
| 50 | `inventory` → `partners` | 0 | 2 | 0 | **2** |
| 51 | `partners` → `sales` | 0 | 2 | 0 | **2** |
| 52 | `partners` → `tenants` | 0 | 2 | 0 | **2** |
| 53 | `sales` → `after_sales` | 2 | 0 | 0 | **2** |
| 54 | `tenants` → `accounting` | 0 | 2 | 0 | **2** |
| 55 | `after_sales` → `tenants` | 0 | 1 | 0 | **1** |
| 56 | `bridge` → `core` | 1 | 0 | 0 | **1** |
| 57 | `bridge` → `partners` | 0 | 1 | 0 | **1** |
| 58 | `bridge` → `tenants` | 0 | 1 | 0 | **1** |
| 59 | `core` → `bridge` | 0 | 1 | 0 | **1** |
| 60 | `device_registry` → `tenants` | 0 | 1 | 0 | **1** |
| 61 | `hr` → `bridge` | 0 | 1 | 0 | **1** |
| 62 | `realestate` → `tenants` | 0 | 1 | 0 | **1** |
| 63 | `tenants` → `inventory` | 0 | 1 | 0 | **1** |

ملاحظات على القراءة:
- **تصنيف (أ) «مقبول» شكلاً لا مضموناً**: جزء كبير من عمود (أ) في `accounting → sales/logistics`
  هو استيرادات داخل أوامر إدارة لترحيل بيانات تاريخية (`import_jarabaa`,
  `migrate_firebase_*`, `wrap_orphan_cheques_in_vouchers`) — ليست مسار تشغيل يومي.
- **دورات (cycles) مؤكدة على مستوى الكود التشغيلي**:
  `accounting ↔ sales` · `accounting ↔ logistics` · `accounting ↔ inventory` ·
  `accounting ↔ partners` · `inventory ↔ sales` · `inventory ↔ logistics` ·
  `sales ↔ logistics` · `core ↔` (الجميع تقريباً).
  الدورة الأخطر: `accounting/services.py` نفسه يستورد `sales.models`/`logistics.models`
  (`accounting/services.py:930-931`, `:1498-1525`) — الطبقة السفلى تنظر للأعلى.

## §2 — الاختبارات (مذكورة منفصلة — غير محسوبة أعلاه)

647 استيراداً عابراً في ملفات `tests/` عبر 59 زوجاً. الأعلى:

| من → إلى | العدد | | من → إلى | العدد |
|---|---:|---|---|---:|
| `sales` → `tenants` | 65 | | `accounting` → `tenants` | 31 |
| `logistics` → `tenants` | 60 | | `sales` → `inventory` | 29 |
| `sales` → `accounting` | 52 | | `logistics` → `inventory` | 24 |
| `logistics` → `partners` | 40 | | `accountant_portal` → `core` | 23 |
| `logistics` → `accounting` | 37 | | `inventory` → `tenants` | 15 |
| `sales` → `partners` | 35 | | `accounting` → `partners` | 14 |
| `core` → `tenants` | 33 | | *(الباقي ≤13 لكل زوج)* | |

معظمها بناء بيانات اختبار (`Tenant`/`Partner`/`Account` fixtures) — طبيعي في اختبارات
تكاملية، ولا يدخل في الـbaseline لكن `.importlinter` يستثنيه بـwildcard صريح
(`*.tests.* -> accounting.models` وما شابه) حتى لا يمنع كتابة اختبارات جديدة.

**الـmigrations:** صفر استيراد عابر — لا شيء يُذكر.

## §3 — أعلى 15 نقطة تشابك (مرتّبة بالخطورة)

الترتيب بمعيار: كتابة قيود خارج `post_journal` أخطر من استيراد داخليات،
وأخطر من استيراد models للقراءة، والاتجاه المعكوس يضاعف الخطورة.

| # | الموضع | الوصف | لماذا خطير |
|---:|---|---|---|
| 1 | `partners/signals.py:202-216` | إنشاء `JournalHeader`+`JournalLine` مباشرة بـ`is_posted=True` (قيد افتتاحي) | **يتجاوز `post_journal`**: بلا فحص فترة مالية، بلا audit log، أكواد حسابات hardcoded (`2101/1103/2106-2109/3300`)، و`Account.DoesNotExist` تُبتلع بـ`pass` (`:104-187`) |
| 2 | `logistics/views.py:1223-1265` | قيد عكسي يدوي (`JournalHeader.objects.create` + قلب مدين/دائن) ثم `.update(is_posted=False)` على الأصلي | **يتجاوز `post_journal`/`unpost_document`** — يفوّت idempotency وقفل `select_for_update` |
| 3 | `logistics/views.py:2633-2660` | نفس النمط العكسي اليدوي — موضع ثانٍ | نفس ما سبق؛ نسخ-لصق يوحي بمواضع مستقبلية |
| 4 | `logistics/accruals.py:155-174` | **موضع كتابة ثالث غير موثّق سابقاً**: ترحيل شحنة محلية بإنشاء قيد يدوي `is_posted=True` | يفحص الفترة ويسجّل audit يدوياً، لكنه يفوّت idempotency الـ`(reference_type, reference_id)` في `post_journal` — والمفارقة أن نفس الملف يستخدم `post_journal` في `:102` و`:226` |
| 5 | `logistics/management/commands/purge_deals.py:81-82` | حذف `JournalLine`/`JournalHeader` جماعي مباشر | مسار الحذف الوحيد للقيود خارج accounting — أمر إدارة، لكنه يعمل على بيانات إنتاج |
| 6 | `partners/signals.py` كـservice بحكم الواقع | `ensure_partner_linked_account` مستورد من `logistics/services.py:654`, `logistics/views.py:43`, `logistics/accruals.py:21`, `sales/services.py:32` | منطق أعمال يسكن في وحدة signals — 4 apps تعتمد على «أثر جانبي» كواجهة؛ مرشّح أول للانتقال لـ`accounting.api` (مرحلة 2-ج) |
| 7 | `inventory/services.py:208` | `record_stock_movement` (الدالة الحرجة) يستورد `sales.SalesSettings` كسولاً لقرار المخزون السالب | **اتجاه معكوس**: inventory (طبقة سفلى) يعتمد على sales؛ القرار يخص المخزون ومكانه الطبيعي inventory |
| 8 | `logistics/serializers.py:12` | `from sales.serializers import CHEQUE_DUE_DATE_REQUIRED` | استيراد ثابت من داخليات serializers لـapp آخر — مذكور في «الديون المؤجلة» |
| 9 | `logistics/serializers.py:230` | `from partners.serializers import PartnerSerializer` | إعادة استخدام serializer عبر الحدود تربط عقد API الخاص بـlogistics بشكل partners الداخلي |
| 10 | `sales/models.py:5` + `logistics/models.py:6` | FKs على مستوى الوحدة إلى `Account`/`JournalHeader`/`TaxRate` | ربط سكيمة: أي تغيير في accounting.models يموّج migrations في 4 apps (موثّق في ARCHITECTURE.md) |
| 11 | `accounting/services.py:930-1013, 1498-1525` | accounting يستورد `sales.models`/`logistics.models`/`sales.services`/`logistics.services` | **دورة كاملة**: الطبقة التي يفترض أنها الأساس تستدعي من فوقها — تمنع أي فصل مستقبلي لـaccounting كحزمة مستقلة |
| 12 | `accounting/serializers.py:75-167` + `accounting/views.py:313-365, 1355` | accounting يقرأ `LogisticsPayment`/`SalesInvoice`/`CustomerPayment` لعرض مراجع القيود | نفس الدورة من جهة العرض — فكّها يحتاج reference-resolver عام بدل استيراد مباشر |
| 13 | `inventory/services.py:447,681,941,997` + `inventory/serials.py:150,162` | inventory يقرأ `logistics.models` و`sales.models` في مسارات التقارير والتسلسلات | اتجاه معكوس إضافي — inventory يعرف تفاصيل فواتير الشراء والبيع |
| 14 | `core/reports.py` (7 مواضع: `:993-1774`) + `core/dashboard_api.py:13` | قراءة `JournalLine`/`JournalHeader`/`Cheque` مباشرة للتقارير | قراءة فقط، لكنها تربط التقارير بسكيمة القيود — أي تعديل سكيمة يكسر التقارير بصمت |
| 15 | `logistics/signals.py:19` | `from accounting.models import JournalHeader, JournalLine` — **استيراد ميت** (غير مستخدم في الملف) | صفر أثر تشغيلي، لكنه يظهر في كل تحليل ويضخّم الغراف — حذفه سطر واحد في المرحلة 2-ب |

## §4 — تصنيف استيرادات `accounting.models` (مدخل المرحلة 2)

كل مواضع الكود (بدون اختبارات) التي تستورد `accounting.models`، مصنّفة:
هل **تنشئ/تعدّل قيوداً** (`JournalHeader`/`JournalLine`) أم قراءة فقط؟

### ✍️ كتابة قيود مباشرة (4 مواضع تشغيلية + 1 أمر إدارة) — هدف المرحلة 2 الأول

| الموضع | ماذا يكتب |
|---|---|
| `partners/signals.py:202-216` | `JournalHeader.objects.create(is_posted=True)` + 2-4 `JournalLine.objects.create` (قيد افتتاحي) |
| `logistics/views.py:1223-1265` | قيد عكسي + `JournalHeader.objects.filter(pk=…).update(is_posted=False)` |
| `logistics/views.py:2633-2660` | قيد عكسي (النمط نفسه) |
| `logistics/accruals.py:155-174` | `JournalHeader.objects.create(is_posted=True)` + سطران (استحقاق شحن محلي) |
| `logistics/management/commands/purge_deals.py:81-82` | حذف جماعي `JournalLine` ثم `JournalHeader` |

### 🏦 كتابة `Account` (إنشاء حسابات — بلا قيود)

| الموضع | السياق |
|---|---|
| `partners/signals.py:104, 187` | `Account.objects.get_or_create/create` لحساب الشريك وحساب الرصيد الافتتاحي (أكواد hardcoded) |
| `tenants/services.py:107, 151, 241` | زرع شجرة الحسابات عند إنشاء شركة (bootstrap مشروع، لكنه يثبّت الأكواد خارج accounting) |
| `tenants/management/commands/heal_company_seed.py:61` | ترميم شجرة ناقصة |
| `logistics/services.py:824` | `Account.objects.get_or_create` (حساب وسيط) |
| `sales/services.py:406, 1953` | `Account.objects.get_or_create` |
| `hr/payroll.py:75, 129` | `Account.objects.create` لحسابات الرواتب/السلف |

### 👁 قراءة فقط (كل البقية)

- **`accountant_portal`**: `services.py:867-1168` (5 مواضع `JournalLine` aggregate)، `readiness.py:179`، `audit.py:27` (`AccountingAuditLog`).
- **`core`**: `reports.py:993,1360,1420,1474,1630,1701,1774` · `dashboard_api.py:13` · `platform_admin_api.py:16`.
- **`hr`**: `payroll.py:31` (`JournalLine` قراءة؛ الترحيل نفسه عبر `post_journal` — `payroll.py:277,355` ✅).
- **`inventory`**: `services.py:590` (`Account` قراءة) · `management/commands/recompute_moving_wac_cogs.py:51`.
- **`logistics`**: `serializers.py:10,2444` · `landed_cost.py:332` (`ExchangeRate`) · `services.py:13,884,1409` (قراءة — الترحيل عبر `post_journal`: `services.py:1190,1360,1770` ✅) · `payment_posting_diagnostics.py:10` · `models.py:6` (FKs) · `signals.py:19` (**ميت**) · `views.py:40,45,889` (قراءة + المواضع الكاتبة المذكورة أعلاه) · `management/commands/audit_freight_accruals.py:11`.
- **`sales`**: `models.py:5` (FKs) · `serializers.py:6` · `services.py:14,201,784,1072,1513,2128,2519,3881` (قراءة `Cheque`/`TaxRate`/`JournalLine`؛ الترحيل عبر `post_journal`: `services.py:1482,1897,2102,2457,2479,3779,3856` ✅) · `views.py:376` · `management/commands/fix_legacy_cash_partner_tags.py:29`.
- **`tenants`**: `services.py:6` (`Account`, `Currency` — للزرع أعلاه).

> **خلاصة للمرحلة 2:** المسار الصحيح (`post_journal`) مستخدم فعلاً في sales وhr
> ومعظم logistics — المخالفون الفعليون 4 مواضع تشغيلية فقط (§4-أ)، وهم هدف الترحيل
> الأول. البقية إما FKs سكيمة (تبقى كما هي في المرحلة 2) أو قراءات تحتاج واجهة
> قراءة لاحقاً.

## §5 — الترتيب المقترح لفكّ التشابك (مع التبرير)

1. **المواضع الكاتبة الأربعة (§4-أ) → `accounting.api`** — أصغر جراحة وأكبر أثر:
   توحيد نقطة كتابة القيود يعيد ضمانات الفترة/التوازن/الـidempotency للجميع.
   ترتيبها الداخلي: `logistics/views.py:1223` (الأوضح) ← `logistics/views.py:2633`
   ← `logistics/accruals.py:155` ← `partners/signals.py:202` (الأعقد — يحمل أيضاً
   إنشاء حسابات بأكواد hardcoded).
2. **`ensure_partner_linked_account` من `partners/signals` إلى واجهة عامة** —
   يفكّ 4 استيرادات فئة (ج) دفعة واحدة (`logistics×3` + `sales×1`) ويحرّر
   إنشاء الحسابات من طبقة الـsignals.
3. **الاستيرادان في `logistics/serializers.py:12,230`** — نقل الثابت
   `CHEQUE_DUE_DATE_REQUIRED` لموضع محايد وفكّ `PartnerSerializer` — يصفّر فئة (ج).
4. **قرار المخزون السالب من `sales.SalesSettings` إلى inventory**
   (`inventory/services.py:208`) — يفكّ أخطر اتجاه معكوس. يحتاج قرار منتج:
   نقل الحقل بـmigration أو واجهة قراءة — خارج نطاق المرحلة 2، وثّق فيها فقط.
5. **دورة `accounting → sales/logistics`** (`accounting/services.py:930-1525`,
   `accounting/serializers.py:75-167`) — الأصعب: يحتاج نمط resolver/registry
   للمراجع بدل الاستيراد المباشر. يؤجَّل لما بعد استقرار `accounting.api`.
6. **قراءات التقارير** (`core/reports.py`, `accountant_portal/services.py`) —
   واجهة قراءة (`accounting.api.get_ledger_lines(...)`) — قيمتها تنظيمية أكثر منها
   سلوكية، آخر الأولويات.

## §6 — الحاجز الآلي: import-linter

- **الأداة:** `import-linter>=2.0` — أُضيفت لـ`requirements.txt`
  (لا يوجد `requirements.local.txt` في المستودع — متجاهَل في git حسب ترويسة requirements.txt).
- **الإعداد:** `.importlinter` في جذر المشروع — 3 عقود، كلها على الاستيراد
  **المباشر** فقط (`allow_indirect_imports = True`):
  1. `no-cross-app-internals` — داخليات (serializers/views/signals/admin/urls)
     ليست واجهات عامة. baseline: **6 انتهاكات** (§3 بنود 6، 8، 9).
  2. `no-direct-accounting-models` — `accounting.models` ليس واجهة عامة.
     baseline: **27 وحدة مستورِدة** (كل مواضع §4) + استثناء wildcard للاختبارات.
  3. `inventory-independent-of-sales-logistics` — الاتجاه المعكوس لا يتمدد.
     baseline: **8 وحدات** (§3 بنود 7، 13).
- **الوضع:** «تحذير موثّق» — الانتهاكات القائمة مسجّلة كـ`ignore_imports`
  فلا يفشل البناء اليوم؛ أي استيراد **جديد** يخالف عقداً يُفشِل `lint-imports`
  (تم التحقق عملياً بإضافة استيراد مخالف مؤقت). **قاعدة الصيانة:** ممنوع إضافة
  أسطر لـ`ignore_imports` لتمرير كود جديد — الاتجاه الوحيد المسموح هو الحذف
  (فكّ الـbaseline).
- **CI:** يوجد `.github/workflows/ci.yml` — أُضيفت خطوة `lint-imports` في job
  الـbackend قبل pytest (تثبيت الأداة يتم أصلاً عبر `pip install -r requirements.txt`).
- **التشغيل محلياً:** `lint-imports` من جذر المشروع (تحليل ثابت — لا يحتاج
  إعدادات Django ولا قاعدة بيانات). النتيجة المتوقعة: `Contracts: 3 kept, 0 broken`.

## التحقق

- `python manage.py test --settings=core.test_settings` → **1,025 اختباراً، OK (skipped=2)** قبل التغيير وبعده (التغيير لم يلمس أي `.py`).
- `lint-imports` → `Contracts: 3 kept, 0 broken` (مطابق للـbaseline أعلاه).
