# ACCOUNTANT_PORTAL_PLAN — بوابة المحاسب القانوني الخارجي (T-EXTACCT)

> **الحالة: `DONE` للمراحل M0–M5 وM7 (2026-08-05)؛ M6 خارج النطاق بشروطه المذكورة في §13.**
> نتائج البوابات مسجَّلة في [PROJECT_MAP.md](docs/history/PROJECT_MAP.md). يبقى هذا الملف **مرجع
> القرارات**: كل القرارات المفتوحة محسومة هنا، والبديل الثاني لكل قرار موجود
> **كإعداد** في `accountant_portal.PortalSettings` لا كسؤال يُعاد على المالك.
>
> تاريخ الخطة: 2026-08-03 · الفرع: `local` · مرجع الإنتاج: Django 5.1.15 / Python 3.10

---

## 0. قواعد التنفيذ — اقرأها قبل أي سطر كود

1. **التزم [CLAUDE.md](CLAUDE.md) و[AGENTS.md](AGENTS.md)**: نفّذ ما طُلب فقط، عدّل ملفاً موجوداً
   بدل إنشاء جديد ما أمكن، اقرأ الملف قبل تعديله، لا تحفظ أسراراً في git.
2. **تصحيحان في ملفات التوثيق** (طبّقهما في المرحلة M7 لا قبلها):
   - `AGENTS.md` يقول Django 6.0.1 — **الإنتاج 5.1.15** ([requirements.txt:10](requirements.txt:10)).
     لا تستعمل أي ميزة حصرية بـ6.0.
   - `CLAUDE.md` يقول `frontend_v2/src/` — **لا وجود لـ`src/`**؛ الملفات في
     `frontend_v2/components/` و`frontend_v2/services/` مباشرة.
3. **الاختبارات**: `python manage.py test --settings=core.test_settings` (وليس `pytest`
   مباشرة). اختبارات الواجهة: `node --test` — الاستيراد يلزمه لاحقة `.ts` صريحة.
4. **خط أساس معروف**: 8 اختبارات في `sales/tests/test_quotation_*` **فاشلة أصلاً على HEAD**
   (عيب سياق شركة، T-PLINEAGE). لا تعدّها ارتداداً ولا تُصلحها ضمن هذه المهمة.
5. **قاعدة الأرقام G1**: كل عرض رقمي عبر `frontend_v2/utils/formatNumber` — ممنوع
   `toFixed(2)` أو `toLocaleString({minimumFractionDigits:2})`.
6. **TDD**: لكل مرحلة، اكتب اختبار البوابة أحمرَ أولاً ثم نفّذ. البوابة في §13 ليست
   اقتراحاً — لا تبدأ مرحلةً قبل خضرة بوابة سابقتها.
7. **MySQL لا SQLite وحدها**: ثلاثة فحوص في هذه الخطة (طول عمود التدقيق، القيود
   الفريدة، القفل المتزامن) **تمرّ على SQLite وتفشل على MySQL**. بوابة M1 وM7 تشترط
   تشغيلاً على MySQL.

---

## 1. القرار في سطور

| البند | القرار النهائي |
|---|---|
| **الشكل** | وحدة (module) مستقلة داخل المونوليث: تطبيق Django واحد `accountant_portal/` |
| **الترخيص** | مفعّلة لكل شركة عبر سجل وحدات (`core.TenantModule`) يضبطه السوبر أدمن. الشركة غير المرخَّصة: **صفر مسارات، صفر استعلامات، صفر JS مُحمَّل، صفر صلاحيات في الكتالوج** |
| **نموذج العلاقة** | `AccountantEngagement` يملك دورة الحياة، و**يُنشئ/يحذف** صفَّ `UserCompanyMembership` بدور `legal_accountant` |
| **الصلاحيات** | كتالوج `core/access.py` القائم + 11 مفتاحاً جديداً موسومة بالوحدة؛ نطاق كل ارتباط = صفوف `MemberPermission` القائمة. **لا مخزن صلاحيات ثانٍ، ولا JSON للإنفاذ** |
| **الافتراضي للمحاسب** | قراءة مالية + طلب توضيح + تجهيز مسودة الفترة. كل فعل كتابي يُمنح صراحةً لكل ارتباط |
| **الفترة الضريبية** | جدول الوحدة `TaxPeriodReview` مربوط `OneToOne` بـ`VatStatement` — **صفر تعديل على `sales/models.py`** |
| **قفل الفترة** | حارس واحد عند نقطة الاختناق الوحيدة [accounting/services.py:509](accounting/services.py:509) بجانب `validate_fiscal_period` |
| **مكتب المحاسب** | شركة `Tenant` هو مديرها؛ فواتير أتعابه وسنداتُ قبضه بالآلات القائمة — **بلا وحدة فوترة جديدة** |
| **الولاية** | فلسطين (قرار بقانون 26/2024). المقاصة يدوية. لا ربط حكومي في هذا النطاق |
| **الاعتماديات** | **صفر جديدة**. throttling وhashing وHMAC من DRF/Django/stdlib |

**الحجم الإجمالي:** 5 جداول جديدة (كلها داخل الوحدة) + 1 جدول سجل وحدات في `core` + **صفر
عمود جديد على أي جدول ساخن** + 11 مفتاح صلاحية + دور واحد + سطرا حراسة.

---

## 2. الأساس القانوني والمصادر

الولاية المقرَّة: **فلسطين**. المرجع: [قرار بقانون رقم (26) لسنة 2024 بشأن ضريبة القيمة المضافة](http://muqtafi.birzeit.edu/pg/getleg.asp?id=18929).

| المادة | ما تقرره | أين تظهر في التنفيذ |
|---|---|---|
| **م(2)** | الضريبة **16%** | `TenantSettings.default_vat_rate = 16.00` القائمة **صحيحة — لا تغيّرها** |
| **م(13)** | سعر صرف الصفقة الأجنبية = سعر **تاريخ إصدار الفاتورة**، ويلزم إدراجه على الفاتورة | فحص الجاهزية #5 |
| **م(36.1)** | خصم المدخلات خلال **ستة أشهر** من تاريخ الفاتورة، **ولا يُدوَّر** للسنة التالية | فحص الجاهزية #11 |
| **م(49)** | فاتورة ضريبية عن **كل صفقة أو جزء منها حتى لو معفاة** | فحص الجاهزية #1، #7 |
| **م(50.1)** | إصدار الفاتورة خلال **14 يوماً** من موعد التكليف | فحص الجاهزية #12 |
| **م(53.2)** | الثمن الأقل ⇐ **فاتورة ضريبية تكميلية بالفرق** | قاعدة التصحيح بعد الترحيل |
| **م(54)** | فاتورة عن صفقة ملغاة/خاطئة: الضريبة واجبة **ما لم تُلغَ أو تُصحَّح بالطريقة التي يحددها المدير العام** | يمنع «تعديل التاريخ»؛ التصحيح بعكس/إشعار دائن |
| **م(55.1)** | مَن أصدر فاتورة ضريبية بلا حق يدفع **ضعف** الضريبة | مبرر منع `sales.invoice.create` افتراضاً |
| **م(60)** | **نموذج الفاتورة وبياناتها وحفظها ونسخها = تعليمات الوزير** | ⇒ **لا تُرمّز قائمة حقول**؛ انظر §4/ق2 |
| **م(75.1)** | تقرير دوري **شهري خلال 15 يوماً** من الشهر التالي | نوع الفترة الافتراضي + فحص #10 |
| **م(75.7)** | محتوى التقرير: مجموع الصفقات بأنواعها + الضريبة على كل نوع + المعفاة + إجمالي المدخلات شاملاً المشتريات والمصروفات والأصول | بنية ملخص ض.ق.م |
| **م(78)** | للمدير طلب بيانات **مصادَق عليها من مدقق حسابات قانوني** مع التقرير | الأساس التجاري للميزة كلها |
| **م(79.1)** | الاحتفاظ بالدفاتر و**قاعدة البيانات** والسجلات والفواتير **خمس سنوات** | `engagement_retention_years = 5` |
| **م(116.1)** | يحق تمثيل المكلف لـ: محامٍ · **مدقق حسابات قانوني** · محاسب (بكالوريوس مالية/محاسبة + دورة ضريبية) · دبلوم مالية ومصرفية + خبرة 5 سنوات + دورة ضريبية · موظف ضريبة سابق ≥5 سنوات. **بشرط أن يكون مسجَّلاً ضريبياً وله عنوان عمل دائم** | `professional_type` (5 قيم) + حقلان إلزاميان |
| **م(116.2)** | لمفوض عام الإيرادات **منع** شخص من المراجعة، **وعدم قبول الحسابات التي يعدّها أو يدققها** لمدة يراها | حالة `barred` + `barred_until` |

**تنبيهان مثبتان:**
- كلمة «مقاصة» **لا ترد في نص 26/2024 إطلاقاً** (فُحص النص كاملاً). فاتورة المقاصة أساسها
  بروتوكول باريس وتعليمات إدارية، ولا API عام موثّق. ⇒ المقاصة **يدوية** في هذه الخطة.
- «رقم التخصيص» الإسرائيلي خدمة **للمشتغلين المرخصين الإسرائيليين** فقط
  ([المصدر الرسمي](https://www.gov.il/ar/service/request-assignment-number-for-tax-invoice)،
  العتبة: 20,000₪ حتى 2025 → 10,000₪ من 1/1/2026 → **5,000₪ من 1/6/2026**).
  و«فاتورة I» يُصدرها **الإسرائيلي للفلسطيني**، بينما الفلسطيني يُصدر **فاتورة P**
  ([المصدر](https://www.gov.il/he/service/producing-invoice)). ⇒ لا ينطبق على التاجر
  الفلسطيني إلا إن كان مسجَّلاً أيضاً كمشتغل مرخص إسرائيلي — وهو **إعداد افتراضه معطّل**.

---

## 3. المعمارية المعيارية (Modular Monolith)

### 3.1 حدود الوحدة

```
accountant_portal/                 ← تطبيق Django واحد، هو كل الوحدة
    __init__.py                    ← لا تنسَه (hr/__init__.py الناقص عطّل جمع الاختبارات سابقاً)
    apps.py                        ← AppConfig.ready() يسجّل الحارس فقط
    models.py                      ← 5 جداول، كلها بادئة db_table = "acct_portal_*"
    services.py                    ← منطق العمل (لا منطق في الـviews)
    readiness.py                   ← الفحوص الاثنا عشر (دوال نقية، قابلة للاختبار وحدياً)
    api.py                         ← ViewSets + APIViews
    serializers.py
    urls.py
    guards.py                      ← حارس قفل الفترة
    permissions.py                 ← مفاتيح الوحدة (تُقرأ من core/access.py لا تُكرَّر)
    migrations/0001_initial.py
    tests/
```

**قاعدة الاعتماد باتجاه واحد:**
`accountant_portal` **يستورد من** `core`/`tenants`/`sales`/`accounting`/`partners`.
**ولا يستوردُه أحد** — عدا سطرين محدَّدين في §3.4. أي استيراد عكسي آخر = خطأ معماري يُرفض
في المراجعة.

### 3.2 سجل الوحدات — الترخيص لكل شركة

**جدول جديد في `core`** (وليس في الوحدة — لأنه يجب أن يعمل والوحدة مطفأة):

`core.TenantModule` → `db_table = "tenant_modules"`
```
tenant       FK(Tenant, CASCADE, db_column='TenantID')
module_key   CharField(40, db_column='ModuleKey')
enabled      BooleanField(default=False, db_column='Enabled')
enabled_by   FK(auth.User, SET_NULL, null=True, db_column='EnabledBy_UserID')
enabled_at   DateTimeField(null=True, db_column='EnabledAt')
plan_note    CharField(120, blank=True, default='', db_column='PlanNote')  # سبب تجاري للتدقيق
unique_together = [['tenant', 'module_key']]
```

**سجل الوحدات في الكود** — `core/modules.py` (جديد):
```python
MODULES = {
    "accountant_portal": {
        "label": "بوابة المحاسب القانوني الخارجي",
        "plans": ("Pro", "Enterprise"),   # للعرض التجاري فقط — لا يُنفَّذ منه شيء
        "legacy_flag": None,
    },
    "import": {                            # توثيق الوحدة القائمة بلا هجرة بياناتها
        "label": "الاستيراد والشحن والتخليص",
        "plans": ("Enterprise",),
        "legacy_flag": "import_enabled",   # يقرأ Tenant.import_enabled كما هو
    },
}

def module_enabled(tenant, key: str) -> bool:
    """مصدر حقيقة واحد لسؤال «هل هذه الوحدة مرخَّصة لهذه الشركة؟»"""
```

**قواعد `module_enabled` الملزمة:**
- `tenant is None` ⇒ `False` دائماً.
- إذا كان للوحدة `legacy_flag` ⇒ اقرأ الحقل القديم على `Tenant` ولا تلمس `TenantModule`
  (فوحدة الاستيراد تبقى على مسارها بلا migration بيانات، ويبقى الاستعلام واحداً).
- خلاف ذلك ⇒ صفّ `TenantModule`؛ الغياب = معطّلة.
- **كاش لكل طلب**: خزّن النتيجة على `request` عبر `core.logger_middleware.get_current_request`
  إن توفّر، وإلا على كاش مفتاحه `f"modules:{tenant_id}"` في `FileBasedCache` القائم بـTTL
  300 ثانية، ويُبطَل صراحةً عند التبديل. **الهدف الملزم: ≤1 استعلام لكل طلب مهما تكرر السؤال.**
- **السوبر أدمن لا يتجاوز التعطيل** — تماماً كسلوك `user_can_access_import`
  ([core/import_access.py:46](core/import_access.py:46)): الوحدة قدرةٌ على مستوى الشركة.

**منفذ السوبر أدمن** (يُضاف إلى [core/platform_admin_api.py](core/platform_admin_api.py) بجوار
`set-import-enabled` القائم):
`POST /api/platform/companies/{tenant_id}/modules/` → `{module_key, enabled, plan_note}`
محروس بـ`core.import_access.is_super_admin`، ويكتب حدث تدقيق `MODULE_TOGGLED`.

### 3.3 «صفر أثر» حين تكون الوحدة مطفأة — البنود الملزمة

| الطبقة | الإجراء | معيار القبول |
|---|---|---|
| **المسارات** | `accountant_portal/urls.py` مُضمَّن مرة واحدة في `core/urls.py`. كل view يبدأ بـ`require_module(request, "accountant_portal")` التي ترفع **404** (لا 403 — منع كشف الوحدة) | اختبار: شركة غير مرخَّصة ⇒ كل مسارات الوحدة 404 |
| **الاستعلامات** | لا إشارة، لا `post_save`, لا مهمة دورية، لا استعلام في لوحة الأعمال، لا مفتاح كاش | `assertNumQueries` على `/api/dashboard/summary` **متطابق** قبل وبعد الميزة |
| **الصلاحيات** | مفاتيح الوحدة موسومة `"module": "accountant_portal"`؛ `permission_keys()` و`/api/permissions/me` وشاشة الصلاحيات **تفلترها** للشركة غير المرخَّصة | اختبار: الكتالوج المُعاد لا يحوي أي `tax.*` |
| **الأدوار** | `legal_accountant` موسوم بالوحدة ولا يظهر في منتقي الأدوار للشركة غير المرخَّصة | اختبار على `/api/permissions/roles` |
| **الحارس** | `guards.py` أول سطر: `if not module_enabled(tenant, ...): return` — بوليان مكيَّش | قياس: `post_journal` بلا زيادة استعلامات |
| **الواجهة (الأهم للذاكرة)** | كل شاشات الوحدة عبر `lazyPage(() => import(...))` في `App.tsx` بنمط [App.tsx:124](frontend_v2/App.tsx:124)، **ومحروسة بعَلَم الوحدة قبل الاستيراد** فلا يُنزَّل الـchunk أصلاً | قياس: حجم الحزمة الأولية **بلا زيادة**؛ chunk الوحدة منفصل ولا يُطلب |
| **الشريط الجانبي** | بنود الوحدة تُبنى من `modules.accountant_portal` في حمولة الصلاحيات | اختبار واجهة |

**عَلَم الواجهة**: يُضاف إلى استجابة `/api/permissions/me` القائمة حقلٌ
`"modules": {"accountant_portal": true|false, "import": true|false}` — **حقل واحد** يخدم كل
الوحدات الحالية والمستقبلية، بلا نقطة نهاية جديدة وبلا طلب شبكة إضافي.

### 3.4 نقاط الالتحام الوحيدة المسموح بها

الوحدة معزولة، عدا **أربعة** التحامات — لا تزد عليها:

| # | المكان | التغيير | الحجم |
|---|---|---|---|
| L1 | [core/access.py:39](core/access.py:39) | +11 مدخلة كتالوج بمفتاح `"module"`، +`legal_accountant` في `ROLE_DEFAULTS`/`ROLE_LABELS`/`ROLE_ORDER`، وفلترة الكتالوج بالوحدات المرخَّصة | ~35 سطراً |
| L2 | [core/tenant_utils.py:119](core/tenant_utils.py:119) | داخل `_validate_user_tenant_access`: إن كان دور العضوية `legal_accountant` فاشترط ارتباطاً `active` | 6 أسطر |
| L3 | [accounting/services.py:509](accounting/services.py:509) | سطر واحد بجوار `validate_fiscal_period`: `run_tax_period_guards(tenant_id, transaction_date)` — وهي في `core/hooks.py` تُنادي الحرّاس المسجَّلين | 1 سطر + ملف hooks صغير |
| L4 | [tenants/views.py:229](tenants/views.py:229) | `_can_create_company` تتجاهل عضويات `legal_accountant` عند حساب «لا عضويات» | 3 أسطر |

**لماذا L3 سطر واحد فقط:** `post_journal` هي **نقطة الاختناق الوحيدة** لكل قيد في النظام —
موثّقة نصّاً في [accounting/services.py:492](accounting/services.py:492): «الدالة المركزية الذرّية —
المسار الوحيد لإنشاء + ترحيل أي قيد محاسبي». المبيعات والمشتريات واللوجستيات والسندات كلها
تمرّ بها. لا تضف الحارس في خدمات الترحيل الفردية.

---

## 4. القرارات المحسومة — والإعداد الذي يحمل البديل الثاني

كل إعداد يعيش في `accountant_portal.PortalSettings` (`OneToOne(Tenant)`) — **لا تضف أي عمود
إلى `TenantSettings`**، فذلك يخرق «صفر أثر حين الإطفاء».

| ق# | القرار المحسوم (الافتراضي) | الإعداد الحامل للبديل | القيمة الافتراضية |
|---|---|---|---|
| ق1 | الولاية: فلسطين وحدها | `tax_jurisdiction` = `PS` \| `PS_IL_DUAL` | `PS` |
| ق2 | **الحقول الإلزامية للفاتورة غير مؤكَّدة (م60 تُحيلها للوزير)** ⇒ تُبنى قائمة تحقق قابلة للتهيئة، وتُصنَّف نتائجها **تحذيرات** لا موانع | `strict_invoice_field_validation` = `False` (تحذير) \| `True` (مانع) | `False` |
| ق3 | المقاصة يدوية بالكامل | `clearance_mode` = `manual` \| `api_reserved` (المسار موجود ويعيد **501 Not Implemented**) | `manual` |
| ق4 | الشركة ليست مشتغلاً مرخصاً إسرائيلياً ⇒ رقم التخصيص محجوب | `is_israeli_registered_dealer` = bool | `False` |
| ق5 | الأفعال الحساسة تتطلب **إعادة إدخال كلمة المرور** (لا TOTP) | `require_reauth_for_sensitive` + `reauth_window_minutes` | `True` / `15` |
| ق6 | التحقق المهني **يدوي من السوبر أدمن** | `verification_mode` = `manual` \| `self_declared` (يُقبل التصريح الذاتي وتبقى الشارة «غير موثّق») — **إعداد منصة** في `core/settings.py` | `manual` |
| ق7 | الاحتفاظ بسجل الارتباط والتدقيق **5 سنوات** (م79) | `engagement_retention_years` | `5` |
| ق8 | المحاسب **لا يرى** التكاليف وهوامش الربح | يُمنح `inventory.cost.view` لهذا الارتباط من شاشة النطاق؛ ويُقفل بالكامل بـ`allow_grant_cost_view=False` | ممنوع / السماح بالمنح `True` |
| ق9 | الدعوة تنتهي بعد **14 يوماً** | `invitation_expiry_days` (1..90) | `14` |
| ق10 | لا حدّ لعدد الشركات لكل محاسب | `max_active_engagements` (0 = بلا حد) | `0` |
| ق11 | قفل الفترة **يمنع** الترحيل وإلغاء الترحيل بتاريخ داخلها | `lock_blocks_posting` | `True` |
| ق12 | **نطاق المنح الافتراضي عند الموافقة = مراجعة فقط** | `default_grant_profile` = `review_only` \| `review_and_prepare` \| `full_accounting` | `review_only` |
| ق13 | الفترة الضريبية **شهرية** (م75.1) | `tax_period_type` = `monthly` \| `custom` | `monthly` |
| ق14 | مهلة تسليم التقرير **15 يوماً** بعد نهاية الفترة | `filing_due_days` | `15` |
| ق15 | نافذة خصم المدخلات **6 أشهر** (م36.1) | `input_vat_window_months` | `6` |
| ق16 | إعادة فتح فترة معتمدة: **للمدير فقط وبسبب إلزامي** | `allow_accountant_reopen` | `False` |
| ق17 | تصدير حزمة المراجعة: **CSV + PDF-for-print** (النمط القائم في المستودع) | `export_formats` = قائمة | `["csv","pdf"]` |
| ق18 | إشعار الشركة بكل فعل حسّاس للمحاسب عبر منظومة الإشعارات القائمة | `notify_company_on_accountant_action` | `True` |

**قواعد على الإعدادات:** كلها تُقرأ داخل الوحدة فقط · كلها لها افتراض صالح فلا يعطّل غيابُ
الصفِّ شيئاً (`get_or_create` كسول) · تعديلها يتطلب `admin.settings.manage` **لمدير الشركة**
ولا يملكه المحاسب أبداً · كل تعديل يُسجَّل في `AccountingAuditLog`.

---

## 5. النماذج

كلها في `accountant_portal/models.py`، `managed = True`، وبادئة جدول `acct_portal_`.

### 5.1 `AccountantProfile` — `acct_portal_profiles`
```
user                     OneToOne(auth.User, CASCADE)
account_type             CharField(30, default='legal_accountant')
professional_type        CharField(30)   # م116.1 — القيم الخمس حرفياً:
                                         # lawyer | licensed_auditor | accountant
                                         # | finance_diploma | ex_tax_officer
license_number           CharField(60, blank=True, default='')
license_authority        CharField(120, blank=True, default='')
tax_registration_number  CharField(50)             # إلزامي — م116.1
business_address         TextField()               # إلزامي — م116.1 «عنوان عمل دائم»
phone                    CharField(30, blank=True, default='')
email_verified_at        DateTimeField(null=True)
verification_status      CharField(20, default='unverified')
                         # unverified | pending_review | verified | rejected | barred
verified_by / verified_at / rejection_reason
barred_until             DateField(null=True)      # م116.2
created_at / updated_at
constraints: UniqueConstraint(tax_registration_number) — يمنع الحساب المشترك
```

### 5.2 `AccountantEngagement` — `acct_portal_engagements`
```
accountant        FK(auth.User, PROTECT, related_name='accountant_engagements')
tenant            FK(tenants.Tenant, CASCADE)
status            CharField(20, default='pending')
                  # pending | active | suspended | revoked | declined | expired
initiated_by      CharField(10)          # accountant | company
requested_by      FK(auth.User, SET_NULL, null=True)
approved_by / approved_at
suspended_at / revoked_at / revoked_by / revocation_reason
invitation_token_hash  CharField(64, null=True, db_index=True)   # SHA-256 فقط
invitation_expires_at  DateTimeField(null=True)
invitation_used_at     DateTimeField(null=True)
approved_scope_snapshot  JSONField(default=list)  # لقطة تدقيق — لا يقرؤها الإنفاذ إطلاقاً
engagement_note   TextField(blank=True, default='')
created_at / updated_at
unique_together = [['accountant', 'tenant']]
indexes: (tenant, status) · (accountant, status)
```

> **قاعدة صارمة:** `approved_scope_snapshot` **ممنوع** أن يُقرأ في أي مسار تفويض. الإنفاذ
> مصدره `MemberPermission` وحدها. اختبار §12/ت41 يحرس هذا.

### 5.3 `PortalSettings` — `acct_portal_settings`
`OneToOne(Tenant)` + الحقول الثمانية عشر في §4.

### 5.4 `TaxPeriodReview` — `acct_portal_period_reviews`
```
tenant          FK(Tenant, CASCADE)
vat_statement   OneToOne(sales.VatStatement, CASCADE, null=True)  # يُملأ عند التجهيز
period_from / period_to   DateField
status          CharField(24, default='in_review')
                # in_review | needs_company_action | ready | approved | submitted | locked
prepared_by / prepared_at
approved_by / approved_at
submitted_by / submitted_at / submission_reference CharField(120, blank=True)
locked_at
reopen_count    PositiveSmallIntegerField(default=0)
last_reopen_reason  TextField(blank=True, default='')
constraints: UniqueConstraint(tenant, period_from, period_to)
```
**«OPEN» ليست حالةً مخزَّنة** — هي غياب الصف. لا تُنشئ صفوفاً فارغة.

### 5.5 `ReviewQuery` — `acct_portal_review_queries`
```
tenant / engagement FK
period_review   FK(TaxPeriodReview, SET_NULL, null=True)
entity_type     CharField(40)   # نفس اصطلاح core.ActivityLog — قائمة مغلقة
entity_id       IntegerField(null=True)
entity_label    CharField(200, blank=True, default='')
title           CharField(200)
body            TextField()
severity        CharField(10, default='warning')   # blocker | warning | info
status          CharField(12, default='open')      # open | answered | resolved | withdrawn
raised_by / raised_at
answered_by / answered_at / answer_body
attachment_url  CharField(500, blank=True, default='')
indexes: (tenant, status, severity) · (tenant, entity_type, entity_id)
```

### 5.6 خارج الوحدة
- `core.TenantModule` (§3.2).
- `tenants.UserCompanyMembership.ROLE_CHOICES` += `('legal_accountant', 'محاسب قانوني خارجي')`
  — **قيمة في choices، لا عمود جديد**.

### 5.7 ترتيب الـmigrations
1. `core/migrations/00XX_tenant_module.py` — الجدول + فهرس.
2. `tenants/migrations/00XX_membership_legal_accountant_role.py` — `AlterField` على `role`.
3. `accountant_portal/migrations/0001_initial.py` — الجداول الخمسة.
4. `accounting/migrations/00XX_widen_audit_action.py` — **انظر §11 قبل تنفيذها**.

`makemigrations --check` يجب أن يكون نظيفاً بعد كل مرحلة.

---

## 6. الصلاحيات

### 6.1 المفاتيح الجديدة
تُضاف إلى `PERMISSIONS` في [core/access.py:39](core/access.py:39) بمجموعة جديدة
`GROUP_TAX = "الضريبة والمراجعة"` وبمفتاح `"module": "accountant_portal"`:

| المفتاح | التسمية العربية | افتراضي `legal_accountant` |
|---|---|---|
| `tax.period.view` | عرض فترات المراجعة الضريبية | ✅ |
| `tax.period.prepare` | تجهيز الفترة وتشغيل قائمة الجاهزية | ✅ |
| `tax.period.approve` | اعتماد الفترة الضريبية | ❌ |
| `tax.period.reopen` | إعادة فتح فترة معتمدة | ❌ |
| `tax.filing.submit` | تسجيل تقديم الإقرار | ❌ |
| `tax.clearance.issue` | إصدار فاتورة مقاصة (P) | ❌ + محجوبة بـق3 |
| `tax.assignment.request` | طلب رقم تخصيص إسرائيلي | ❌ + محجوبة بـق4 |
| `tax.integration.manage` | إدارة تفويض التكامل الضريبي | ❌ **ولا تُمنح للمحاسب أبداً** |
| `review.query.create` | إنشاء طلب توضيح | ✅ |
| `review.query.respond` | الرد على طلب توضيح | ❌ (للشركة) |
| `finance.export.package` | تصدير حزمة المراجعة | ✅ |

### 6.2 `ROLE_DEFAULTS['legal_accountant']` — القائمة الكاملة والنهائية
```python
_LEGAL_ACCOUNTANT = {
    "sales.invoice.view", "purchase.invoice.view",
    "sales.customer.view", "purchase.supplier.view",
    "accounting.journal.view", "accounting.report.view",
    "tax.period.view", "tax.period.prepare",
    "review.query.create", "finance.export.package",
}
```
**عشرة مفاتيح. لا تزد.** خصوصاً: **لا `inventory.*`، لا `hr.*`، لا `import.*`، لا `admin.*`،
لا `*.post`، لا `*.unpost`، لا `*.create`، لا `*.delete`، لا `finance.cashbox.manage`،
لا `accounting.period.manage`.**

> **تحذير للمنفّذ:** لا تُعِد استخدام `_ACCOUNTANT` ([core/access.py:140](core/access.py:140)).
> فهو يمنح `inventory.doc.post` و`inventory.doc.unpost` و`inventory.cost.view` و
> `hr.attendance.view` و`import.doc.unpost` — وهذا يخرق شرط «لا وصول تشغيلي» جوهرياً.

### 6.3 نطاق الارتباط = `MemberPermission`
عند الموافقة، `approve_engagement()` تكتب صفوف `MemberPermission` للمفاتيح **الزائدة** عن
افتراضي الدور فقط. حزم `default_grant_profile` (ق12):

| الحزمة | المفاتيح الإضافية |
|---|---|
| `review_only` (افتراضي) | — لا شيء |
| `review_and_prepare` | `sales.invoice.create`, `sales.invoice.edit`, `purchase.invoice.create`, `purchase.invoice.edit`, `accounting.journal.create` |
| `full_accounting` | ما سبق + `sales.invoice.post/unpost`, `purchase.invoice.post/unpost`, `accounting.journal.post/unpost`, `tax.period.approve` |

`tax.filing.submit` و`tax.clearance.issue` و`tax.assignment.request` **ليست في أي حزمة** —
تُمنح فردياً بنقرة واعية من شاشة النطاق.

### 6.4 مصفوفة الممنوعات المطلقة
هذه **لا تُمنح ولو أرادها المدير** — الخادم يرفضها لدور `legal_accountant` قبل الوصول إلى
`MemberPermission`:
`admin.members.manage` · `admin.permissions.manage` · `admin.settings.manage` ·
`tax.integration.manage` · `inventory.doc.post` · `inventory.doc.unpost` ·
`inventory.item.manage` · `import.*` · `hr.*` · `sales.invoice.delete` ·
`purchase.invoice.delete`.

التنفيذ: مجموعة `LEGAL_ACCOUNTANT_FORBIDDEN` في `accountant_portal/permissions.py`، تُفحص
في نقطتين — عند كتابة النطاق (422) وفي `user_permissions` (طرح نهائي).

---

## 7. الحالات والانتقالات

### 7.1 الارتباط
| من → إلى | مَن | الشرط | حدث التدقيق |
|---|---|---|---|
| — → `pending` | محاسب (طلب) أو مدير (دعوة) | بريد محقَّق + ملف مكتمل + لا ارتباط قائم + `max_active_engagements` | `ENG_REQUESTED` |
| `pending` → `active` | **مدير الشركة** (`admin.members.manage`) | `select_for_update` + الدعوة سارية وغير مستعملة + الملف ليس `barred` | `ENG_APPROVED` |
| `pending` → `declined` | مدير | — | `ENG_DECLINED` |
| `pending` → `expired` | النظام (كسول عند القراءة، لا مهمة دورية) | تجاوز `invitation_expiry_days` | `ENG_EXPIRED` |
| `active` → `suspended` | مدير | — | `ENG_SUSPENDED` — **العضوية تُحذف** |
| `suspended` → `active` | مدير | الملف ليس `barred` | `ENG_RESUMED` — العضوية والنطاق يُعادان |
| `active`\|`suspended` → `revoked` | مدير **أو المحاسب نفسه** | — | `ENG_REVOKED` — **نهائي** |

`revoked` **لا رجعة منه**؛ العودة تتطلب ارتباطاً جديداً بموافقة جديدة.
**التعليق والإلغاء يحذفان صفَّ العضوية وكل صفوف `MemberPermission` التابعة** — داخل
`transaction.atomic` واحدة.

### 7.2 الفترة الضريبية
```
OPEN (مشتقّة — لا صف)
 → in_review              [tax.period.prepare]
 → needs_company_action   [تلقائي عند ReviewQuery(severity=blocker, status∉{resolved,withdrawn})]
 → ready                  [تلقائي: لا blockers]
 → approved               [tax.period.approve + إعادة مصادقة]
 → submitted              [tax.filing.submit]
 → locked                 [تلقائي فور submitted]
```
**التراجع:** `needs_company_action → in_review` تلقائي عند حل آخر blocker ·
`ready → needs_company_action` عند ظهور مانع جديد · `approved → in_review` بـ`tax.period.reopen`
(المدير فقط، سبب إلزامي، `reopen_count += 1`) · **`locked` لا رجعة**.

### 7.3 قائمة الجاهزية — 12 فحصاً، كلها مشتقّة
تُنفَّذ في `accountant_portal/readiness.py` كدوال نقية تأخذ `(tenant_id, period_from,
period_to, settings)` وتعيد `list[Finding(code, severity, entity_type, entity_id, message, count)]`.

| # | الكود | الفحص | المرجع | التصنيف |
|---|---|---|---|---|
| 1 | `MISSING_PARTY_TAX_NO` | فاتورة لطرف بلا `tax_number` | م49 | blocker |
| 2 | `DUPLICATE_INVOICE_NO` | تكرار `invoice_number` داخل الشركة | — | blocker |
| 3 | `UNPOSTED_DOCS` | مستندات `status='draft'` في النافذة | — | blocker |
| 4 | `LINE_VAT_MISMATCH` | مجموع ضريبة الأسطر ≠ `tax_amount` | — | blocker |
| 5 | `FX_RATE_MISSING` | عملة ≠ الأساس و`exchange_rate` غير مُثبت بتاريخ الفاتورة | **م13** | blocker |
| 6 | `ORPHAN_CREDIT_NOTE` | مرجع/إشعار بلا `original_invoice` | — | blocker |
| 7 | `UNCLASSIFIED_ZERO_RATED` | `tax_amount=0` بلا `TaxRate` مرتبط | م32/م33 | warning |
| 8 | `UNCLASSIFIED_EXPENSE` | قيد مصروف على حساب عام غير مصنَّف | م75.7 | warning |
| 9 | `MISSING_ATTACHMENT` | `ReviewQuery` مفتوح من نوع مرفق | — | warning |
| 10 | `FILING_DUE_SOON` | `period_to + filing_due_days` يقترب/فات | **م75.1** | warning |
| 11 | `INPUT_VAT_EXPIRED` | فاتورة مدخلات أقدم من `input_vat_window_months` | **م36.1** | warning |
| 12 | `LATE_DOCUMENT` | مستند `created_at > period_review.prepared_at` | — | info→warning |

**إضافي مشروط بـق2:** `INVOICE_FIELD_RULES` — يقرأ قائمة الحقول القابلة للتهيئة، ويصنّف
النتيجة `warning` افتراضاً و`blocker` إذا `strict_invoice_field_validation=True`.

**قاعدة الأداء الملزمة:** الفحوص الاثنا عشر مجتمعةً **≤6 استعلامات**. لا حلقة بايثون على
الفواتير — كل فحص تجميعة SQL (`annotate`/`Sum`/`HAVING`). سابقة المستودع: تحسين «الكرت المجمّع»
من 3501 استعلام إلى 3 بدمج التكرار في SQL لا في بايثون.

---

## 8. عقود API

الجذر `/api/accountant/`. الترويسات: `Authorization: Token …` + `X-Tenant-Id` على كل مسار
داخل شركة. كل مسارات الوحدة تبدأ بـ`require_module(...)` ⇒ **404** إن كانت الوحدة معطّلة.

### 8.1 هوية المحاسب (بلا `X-Tenant-Id`)
| Method | Path | Input | Output | أخطاء |
|---|---|---|---|---|
| POST | `/accountant/signup/` | `fullName,email,password,professional_type,tax_registration_number,business_address,license_number?,license_authority?,phone?` | `201 {user, profile}` | 400 `weak_password`·`invalid_email`·`missing_tax_registration`·`missing_business_address` · 429 `throttled` · **تكرار البريد ⇒ 201 أيضاً** (منع التعداد؛ يُرسل بريد «حسابك موجود») |
| POST | `/accountant/verify-email/` | `token` | `200 {verified:true}` | 400 `token_invalid`\|`token_expired`\|`token_used` |
| POST | `/accountant/resend-verification/` | `email` | `202` دائماً | 429 |
| GET·PATCH | `/accountant/me/` | حقول الملف | `200 {profile}` | 403 `email_unverified` |
| POST | `/accountant/me/submit-verification/` | — | `202 {status:'pending_review'}` | 400 `incomplete_profile` · 409 `already_pending` |

### 8.2 الارتباط — جانب المحاسب
| Method | Path | Output | أخطاء |
|---|---|---|---|
| POST | `/accountant/engagements/request/` | `201 {engagement}` | 403 `email_unverified` · **404 `company_not_found`** (رسالة موحّدة لغير الموجود وغير المرخَّص) · 409 `engagement_exists` · 422 `max_engagements_reached` · 429 |
| POST | `/accountant/engagements/accept-invite/` | `200 {engagement}` | 400 `token_invalid` · 410 `invitation_expired` · 409 `invitation_used` |
| GET | `/accountant/engagements/` `?status=&search=&page=` | `200 {results[],count}` | — |
| POST | `/accountant/engagements/{id}/withdraw/` | `200` | 409 `not_pending` |
| POST | `/accountant/engagements/{id}/resign/` | `200` | 409 `not_active` |

### 8.3 الارتباط — جانب الشركة (`admin.members.manage`)
| Method | Path | Input | أخطاء |
|---|---|---|---|
| POST | `/accountant/company/engagements/invite/` | `email, scope[], note` | 403 · 409 `engagement_exists` · 429 |
| GET | `/accountant/company/engagements/` | `?status=` | 403 |
| POST | `…/{id}/approve/` | `scope[]` | 403 · 409 `not_pending` · 410 `invitation_expired` · 422 `unknown_permission_key`\|`forbidden_permission_key` |
| POST | `…/{id}/decline/` | `reason` | 409 |
| POST | `…/{id}/suspend/` | `reason` | 409 `not_active` |
| POST | `…/{id}/resume/` | — | 409 · 422 `accountant_barred` |
| POST | `…/{id}/revoke/` | `reason` | 409 `already_revoked` |
| PATCH | `…/{id}/scope/` | `scope[]` | 403 · 422 |
| GET·PATCH | `/accountant/company/settings/` | إعدادات §4 | 403 `admin.settings.manage` |

**الموافقة ذرّية:** `transaction.atomic` + `select_for_update` على صف الارتباط ⇒ قبولان
متزامنان: أحدهما `200` والآخر `409`. **عضوية واحدة دائماً.**

### 8.4 مساحة العمل
| Method | Path | ملاحظات |
|---|---|---|
| GET | `/accountant/workspace/companies/` | لوحة الشركات: `?search=&status=&page=&page_size=`. تجميع **خادمي**: عدد الموانع، آخر فترة وحالتها، الاستعلامات المفتوحة. **≤4 استعلامات لأي عدد شركات** |
| GET | `/accountant/tax/periods/` · `/{id}/` | `?from=&to=&status=` |
| POST | `/accountant/tax/periods/prepare/` | `{period_from, period_to}` → `201`. `409 period_overlap`. **Idempotency:** `UniqueConstraint(tenant, period_from, period_to)` + قيد `unique_vat_statement_period` القائم + `select_for_update` ⇒ التكرار يعيد `409` لا صفاً ثانياً |
| GET | `/accountant/tax/periods/{id}/readiness/` | الفحوص الاثنا عشر مصنَّفة ومجمَّعة |
| POST | `…/{id}/approve/` | `{reauth_password}` → `403 reauth_required` · `409 has_blockers` · `403` بلا المفتاح |
| POST | `…/{id}/reopen/` | `{reason}` — مدير فقط (ق16) |
| POST | `…/{id}/mark-submitted/` | `{submission_reference, submitted_on}` → `locked` |
| GET·POST | `/accountant/review/queries/` | `review.query.create`؛ `entity_type` من قائمة مغلقة |
| POST | `…/{id}/answer/` | `review.query.respond` (الشركة) |
| POST | `…/{id}/resolve/` · `…/{id}/withdraw/` | المحاسب |
| POST | `…/tax/periods/{id}/export/` | `{format}` — `finance.export.package`؛ يسجّل حدث تصدير |
| POST | `/accountant/tax/clearance/` | **501 `not_implemented`** ما لم يكن `clearance_mode='api_reserved'` — ومع ذلك 501 (ق3) |

### 8.5 المنصة (سوبر أدمن)
`POST /api/platform/companies/{tenant_id}/modules/` · `GET /api/platform/accountants/pending/` ·
`POST /api/platform/accountants/{profile_id}/verify/` `{decision, reason}`

### 8.6 قواعد أخطاء موحَّدة
- كل الرسائل بالعربية عبر `core.exception_handler.custom_exception_handler` القائم.
- **شركة غير مرتبطة ⇒ `404` لا `403`** (منع تعداد الشركات) — نفس نمط المصاريف الشخصية.
- **وحدة غير مرخَّصة ⇒ `404`** (منع كشف وجود الوحدة).
- كل 403 يحمل `{code, detail}` وتسمية الصلاحية العربية، كما تفعل
  [core/access.py:299](core/access.py:299).

---

## 9. الشاشات

تُضاف إلى `frontend_v2/components/accountant/`، وتُسجَّل في
[App.tsx:157](frontend_v2/App.tsx:157) (`AuthView`/`View`) و`types/common.ts` و`Sidebar.tsx`
و`utils/viewPermissions.ts` و`layout/Breadcrumb.tsx` و`e2e/parity-baseline.json`.

| # | الشاشة | loading | empty | error | forbidden | revoked |
|---|---|---|---|---|---|---|
| 1 | تسجيل المحاسب `/accountant/signup` | زر معطّل | — | خطأ حقلي | — | — |
| 2 | الملف المهني وحالة التحقق | هيكل | «أكمل ملفك» | إعادة | — | — |
| 3 | طلبات الارتباط (مرسلة/مستلمة) | هيكل | «لا طلبات» | إعادة | — | شارة «ملغى» |
| 4 | **موافقة المدير** — جدول الصلاحيات بنداً بنداً قبل الموافقة | هيكل | — | إعادة | 403 | 410 «انتهت الدعوة» |
| 5 | **لوحة الشركات** (100+) | 8 بطاقات هيكلية | «أرسل طلب ارتباط» | إعادة | — | بطاقة رمادية غير قابلة للنقر |
| 6 | مساحة العمل — **اسم الشركة ظاهر دائماً في الشريط** | هيكل | «لا مستندات» | إعادة | 403 عربية | **حوار مانع + عودة للوحة** |
| 7 | مراجعة الفترة + قائمة الجاهزية | هيكل | «لا فترات» | إعادة | 403 | مانع |
| 8 | النواقص وطلبات التوضيح | هيكل | «لا نواقص» | إعادة | 403 | مانع |
| 9 | ملخص ض.ق.م والاعتماد | هيكل | «لم تُجهَّز» | إعادة | 403 | مانع |
| 10 | سجل عمليات المحاسب | هيكل | «لا عمليات» | إعادة | 403 | قراءة فقط |
| 11 | إعدادات البوابة + تفويض التكامل — **شاشة الشركة** | هيكل | — | إعادة | **403 للمحاسب دائماً** | — |

**ملزم:** كل شاشة عبر `lazyPage` ومحروسة بعَلَم الوحدة **قبل** `import()` · إخفاء الأزرار
عرضٌ لا أمان — كل فعل يُفحص خادمياً · RTL كامل · Tailwind فقط بلا inline styles · إعادة استعمال
`ToastContext`/`ConfirmContext` القائمين (**ممنوع `alert`/`confirm`**) · حدث
`ENGAGEMENT_REVOKED` على نمط `SESSION_EXPIRED_EVENT` القائم.

---

## 10. الأمان

| # | التهديد | الضابط |
|---|---|---|
| T1 | وصول أفقي بتبديل `X-Tenant-Id` | العضوية + **شرط الارتباط النشط** (L2) |
| T2 | IDOR | كل `get_queryset`/`get_object`/تصدير/مرفق/مفتاح كاش مقيَّد بالـtenant |
| T3 | امتياز بالتسجيل | التسجيل لا يُنشئ عضوية إطلاقاً |
| T4 | صف عضوية شارد | الحارس المزدوج (L2) |
| T5 | إعادة استعمال الدعوة | token عشوائي 32 بايت (`secrets.token_urlsafe`)، **يُخزَّن hash فقط**، أحادي الاستعمال، ينتهي بـق9 |
| T6 | قبول متزامن | `select_for_update` + `unique_together` |
| T7 | وصول بعد الإلغاء (توكن DRF لا ينتهي) | الفحص **لكل طلب** لا لكل جلسة ⇒ الإلغاء فوري بحكم التصميم. **لا تمسّ توكن المستخدم** — فذلك يُخرجه من شركاته الأخرى |
| T8 | تعداد الشركات | `404` موحّد |
| T9 | تعداد المستخدمين | `201` دائماً عند التسجيل |
| T10 | حشو كلمات المرور | `ScopedRateThrottle` (مدمج في DRF): `signup=5/h`, `verify=10/h`, `invite=20/h`, `engagement_request=10/h` — يُضاف `DEFAULT_THROTTLE_CLASSES` إلى [core/settings.py:360](core/settings.py:360) |
| T11 | تسريب أسرار | لا credentials في المُسلسِلات ولا في السجلات؛ حجب صريح |
| T12 | تجاوز عبر endpoint بديل | الحرّاس في **الخدمة** لا في الـview |
| T13 | Log injection | تنقية CR/LF لكل قيمة من المستخدم قبل الكتابة |
| T14 | تسريب بالتصدير | نطاق tenant + `finance.export.package` + تسجيل كل تصدير |
| T15 | تسريب بالكاش | كل مفتاح كاش يحمل `tenant_id` |
| T16 | مرفق مخمَّن | مسار المرفق يحمل tenant + فحص ملكية |
| T17 | فعل حسّاس بجلسة مسروقة | **إعادة إدخال كلمة المرور** (ق5) للاعتماد/التقديم/إعادة الفتح/تغيير النطاق |
| T18 | حساب مشترك بين محاسبين | ملف `OneToOne` + **رقم ضريبي فريد** (م116) |

**سياسة كلمة المرور للمحاسب** (المسار الجديد فقط، لا تُشدَّد على التجار في M2 — انظر R5):
≥10 محارف + ليست ضمن قائمة Django الشائعة (`CommonPasswordValidator` المدمج).

---

## 11. السجلات والتدقيق

### تشغيلي — `core.ActivityLog` عبر `log_activity` (غير حاظر)
`timestamp, tenant_id, user_id, action, entity_type, entity_id, ip_address, metadata`.
يُضاف داخل `metadata`: `correlation_id`, `latency_ms`, `module="accountant_portal"`.
المستويات `INFO/WARNING/ERROR` فقط (`DEBUG` للتطوير).
**ممنوع تسجيل:** كلمات مرور · توكنات · cookies · credentials ضريبية · بيانات بنكية كاملة ·
حمولات ضريبية حساسة.

### تدقيق مالي — `accounting.AccountingAuditLog` (متزامن داخل المعاملة)
إلزامي لكل من: موافقة/تعليق/استئناف/إلغاء ارتباط · تغيير نطاق · اعتماد الفترة · التقديم ·
إعادة الفتح · القفل · تصدير الحزمة · تبديل الوحدة · تغيير إعدادات البوابة.

> ### ⚠️ عائق مؤكَّد يجب حلّه في M1 قبل أي كتابة تدقيق
> `AccountingAuditLog.action` هو **`varchar(20)`** ([accounting/models.py:400](accounting/models.py:400)).
> على MySQL، قيمة أطول من 20 **تُلغي المعاملة بصمت** فيظهر «تم بنجاح» بلا أثر — وSQLite
> **لا تكشف العيب**. هذا عطل موثَّق سابقاً في هذا المستودع.
>
> **الحل المعتمد (لا تختر غيره):** استعمل رموزاً **≤20 محرفاً** ولا تُجرِ `ALTER` على عمود
> جدولٍ تدقيقيٍّ كبير في الإنتاج:
> `ENG_REQUESTED`(13) · `ENG_APPROVED`(12) · `ENG_DECLINED`(12) · `ENG_SUSPENDED`(13) ·
> `ENG_RESUMED`(11) · `ENG_REVOKED`(11) · `ENG_SCOPE_SET`(13) · `TAX_PREPARED`(12) ·
> `TAX_APPROVED`(12) · `TAX_SUBMITTED`(13) · `TAX_REOPENED`(12) · `TAX_LOCKED`(10) ·
> `PKG_EXPORTED`(12) · `MODULE_TOGGLED`(14) · `PORTAL_CFG_SET`(14).
> **اختبار إلزامي على MySQL** يتحقق أن كل رمز ≤20 وأن الصف كُتب فعلاً بعد commit.

**منع المصدرين:** لا نظام سجل ثالث. التشغيلي في `ActivityLog`، المالي في `AccountingAuditLog`،
والفعل الحسّاس يُكتب في الاثنين **بغرضين مختلفين** لا بتكرار.

---

## 12. الاختبارات

### أ) الوحدة والترخيص (M1)
1. شركة غير مرخَّصة ⇒ كل مسارات الوحدة **404**.
2. `/api/permissions/me` لشركة غير مرخَّصة **لا يحوي أي `tax.*`** ولا الدور `legal_accountant`.
3. **`assertNumQueries` على `/api/dashboard/summary` متطابق قبل/بعد إضافة الوحدة.**
4. `module_enabled` ≤1 استعلام مهما تكرر النداء في الطلب الواحد.
5. تبديل الوحدة يُبطل الكاش فوراً.
6. `import` ما زال يقرأ `Tenant.import_enabled` ولم يتغير سلوكه.

### ب) العزل والتفويض (M1 — بوابة zero leakage)
7. محاسب مرتبط بـA يصل A. · 8. `X-Tenant-Id=B` ⇒ **404**. · 9. ارتباط B مرفوض/معلّق/ملغى ⇒ 404.
10. محاسب ثانٍ لا يرى بيانات الأول. · 11. تسجيل وحده: `memberships.count()==0` وكل مسار 403.
12. عضوية `legal_accountant` بلا ارتباط `active` ⇒ **رفض** (T4).
13. مدير في A ومحاسب في B: كل دور بصلاحياته بلا تسرّب.
14. **مصفوفة 403 جدولية:** كل مسارات `inventory/*`, `hr/*`, `logistics/*`, `admin.members.manage`,
    `admin.settings.manage` ⇒ 403 للمحاسب. (اختبار واحد يمرّ على القائمة كاملة.)
15. منح `inventory.doc.post` لمحاسب ⇒ **422** (قائمة الممنوعات المطلقة §6.4).

### ج) الارتباط (M2)
16. دعوة منتهية ⇒ 410. · 17. مستعملة ⇒ 409. · 18. ملغاة ⇒ 409.
19. **قبول متزامن (خيطان)** ⇒ عضوية واحدة، الثاني 409.
20. الإلغاء يُبطل الوصول **في الطلب التالي مباشرة**.
21. التعليق ثم الاستئناف يستعيد النطاق نفسه بالضبط.
22. `revoked` لا يُستأنف. · 23. التوكن يبقى صالحاً لشركات المحاسب الأخرى بعد إلغاء واحدة.
24. تكرار البريد عند التسجيل ⇒ **201** لا 400. · 25. throttling ⇒ 429.
26. `max_active_engagements` يُحترم. · 27. ملف `barred` لا يُوافَق عليه.
28. **محاسب عضويتُه الوحيدة `legal_accountant` يستطيع إنشاء مكتبه الخاص** (L4).

### د) الفترة (M5)
29. اعتماد مع blocker ⇒ 409. · 30. بلا `tax.period.approve` ⇒ 403. · 31. بلا إعادة مصادقة ⇒ 403.
32. كل انتقال يولّد حدث تدقيق. · 33. `locked` يرفض الترحيل بتاريخ داخلها (L3) و`lock_blocks_posting=False` يسمح.
34. **حدود التاريخ:** مستند في `period_to` داخل، وفي `period_to + 1` خارج.
35. المراجيع تُخصم لا تُضاف (تغطية قائمة في `test_vat_statement_returns`).
36. صفري/معفى بلا تصنيف ⇒ warning. · 37. عملة ≠ الأساس بلا سعر صرف ⇒ blocker (م13).
38. مدخلات أقدم من 6 أشهر ⇒ warning (م36). · 39. `prepare` مرتين لنفس النافذة ⇒ 409 وصف واحد.
40. **الفحوص الاثنا عشر مجتمعة ≤6 استعلامات** على 1000 فاتورة.
41. **`approved_scope_snapshot` لا يؤثر في التفويض:** عدّله يدوياً ⇒ الصلاحيات الفعلية لا تتغير.

### هـ) أمن وأداء (M7)
42. لا أسرار في السجلات (فحص المخرجات). · 43. CR/LF في الاسم لا يكسر سطر السجل.
44. **لوحة 200 شركة ≤4 استعلامات** (`assertNumQueries`) وبلا N+1.
45. تعديل مستند مرحّل عبر endpoint بديل ⇒ 403.
46. حدث تدقيق لكل فعل حسّاس (اختبار جدولي).
47. **كل رمز `action` ≤20 محرفاً والصف مكتوب فعلاً — على MySQL.**
48. `makemigrations --check` نظيف.

### و) الواجهة (`node --test`)
49. `viewPermissions` تخفي كل عنصر ممنوع. · 50. `ENGAGEMENT_REVOKED` يعيد للوحة.
51. **chunk الوحدة لا يُطلب حين العَلَم مطفأ.** · 52. كل الأرقام عبر `formatNumber`. · 53. RTL.

---

## 13. المراحل والبوابات

> لا تبدأ مرحلةً قبل خضرة بوابة سابقتها. سجّل نتيجة كل بوابة في `PROJECT_MAP.md`.

### M0 — الأساس المعياري
- `core/modules.py` + `core.TenantModule` + migration + منفذ السوبر أدمن.
- `core/hooks.py` (سجل حرّاس فارغ) + سطر L3.
- تطبيق `accountant_portal/` هيكلاً فارغاً في `INSTALLED_APPS` بـ`__init__.py`.
- **البوابة:** اختبارات 1–6 خضراء + **اختبار 3 يثبت صفر استعلام إضافي على لوحة الأعمال**
  + `makemigrations --check` نظيف.

### M1 — الهوية والارتباط والتفويض
- `AccountantProfile` + `AccountantEngagement` + `PortalSettings` + migration.
- L1 (الكتالوج + الدور + الفلترة بالوحدة) · L2 (حارس الارتباط النشط) · §6.4 الممنوعات.
- رموز التدقيق ≤20 محرفاً (§11).
- **البوابة:** اختبارات 7–15 خضراء = **zero leakage**، واختبار 47 **على MySQL**.

### M2 — التسجيل وموافقة الشركة
- مسار `/accountant/signup` + تحقق البريد + throttling + سياسة كلمة المرور.
- الدعوة/الطلب/الموافقة/التعليق/الاستئناف/الإلغاء + كتابة `MemberPermission` ذرّياً.
- **L4** (`_can_create_company`).
- شاشات 1–4.
- **البوابة:** 16–28 خضراء: التسجيل وحده صفر وصول · الإلغاء فوري · القبول المتزامن واحد ·
  المحاسب يُنشئ مكتبه.

### M3 — لوحة الشركات
- `/accountant/workspace/companies/` بتجميع خادمي + بحث + فلاتر + pagination.
- شاشة 5 + عَلَم الوحدة في `/api/permissions/me` + `lazyPage` مشروط.
- **البوابة:** اختبار 44 (200 شركة ≤4 استعلامات) + اختبار 51 (لا chunk حين الإطفاء).

### M4 — مساحة المراجعة المالية
- قراءة الفواتير والمراجيع والسندات والمصاريف والقيود والشجرة والتقارير ضمن نطاق الدور.
- `ReviewQuery` + دورتها + المرفقات.
- تصدير حزمة المراجعة (CSV + PDF-for-print).
- شاشات 6، 8، 10.
- **البوابة:** المحاسب يُنهي مراجعة كاملة، و**اختبار 14 (مصفوفة 403) أخضر بالكامل**.

### M5 — الجاهزية والاعتماد
- `TaxPeriodReview` + `readiness.py` (12 فحصاً) + الحالات + الاعتماد + القفل + L3 فعّالاً.
- شاشات 7، 9، 11.
- **البوابة:** 29–41 خضراء: لا اعتماد مع مانع · كل انتقال مدقَّق · الفحوص ≤6 استعلامات ·
  اللقطة لا تؤثر في التفويض.

### M6 — التكامل الرسمي (**لا يبدأ في هذا النطاق**)
شرط البدء المسبق، وكلها خارج قدرة المنفّذ: قرار ولاية نهائي + API حكومي موثَّق رسمياً +
**أهلية المنصة كـ«بيت برمجيات»** لدى الجهة المعنية. عند التنفيذ: `TaxAuthorityAdapter` بواجهة
واحدة · credentials لكل شركة مشفَّرة لا تُعرض للمحاسب ولا تدخل السجلات · OAuth2 حسب الوثائق ·
`idempotency_key = SHA256(tenant|invoice|scope)` **بقيد فريد** · حالات
`draft|submitting|allocated|rejected|held|retryable_failed` · حفظ مرجعَي الطلب والاستجابة بلا
أسرار · retry مع backoff للأخطاء القابلة للإعادة فقط · الفاتورة **ليست نهائية قبل استجابة
موثوقة** · سجل «مَن حضّر / مَن وافق / مَن أرسل» · **contract tests على mocks حصراً — ممنوع
الاتصال الحقيقي في الاختبارات**.

### M7 — التصليب والانحدار
- أمن (T1–T18) · أداء · وصولية · RTL · تنقية السجلات · تصحيح `AGENTS.md`/`CLAUDE.md`.
- **البوابة:** كل اختبارات Django والواجهة (القائمة والجديدة) خضراء عدا خط الأساس المعروف
  (8 اختبارات عروض) · `makemigrations --check` نظيف · **تشغيل على MySQL**.

---

## 14. Impact Map — الملفات

### تُعدَّل (بحدود L1–L4 وما يلزمها)
| الملف | التغيير | خطورة |
|---|---|---|
| [core/access.py](core/access.py) | +11 مفتاحاً بوسم الوحدة · +الدور · فلترة الكتالوج | **متوسطة** — `ROLE_ORDER` تقود شاشة الصلاحيات؛ أضف الدور **آخر** القائمة |
| [core/tenant_utils.py](core/tenant_utils.py:106) | حارس الارتباط النشط | **عالية** — كل طلب يمرّ هنا؛ الشرط مقيَّد بالدور الجديد فقط |
| [core/settings.py](core/settings.py:360) | `DEFAULT_THROTTLE_CLASSES` + `THROTTLE_RATES` + `ACCOUNTANT_VERIFICATION_MODE` | متوسطة |
| [core/urls.py](core/urls.py) | تضمين `accountant_portal.urls` مرة واحدة | منخفضة |
| [core/platform_admin_api.py](core/platform_admin_api.py) | منفذ تبديل الوحدات + تحقق المحاسبين | منخفضة |
| [accounting/services.py](accounting/services.py:509) | سطر `run_tax_period_guards` | **عالية** — نقطة اختناق كل قيد؛ لا بد أن تكون no-op عند الإطفاء |
| [tenants/models.py](tenants/models.py:277) | `ROLE_CHOICES` += قيمة | منخفضة |
| [tenants/views.py](tenants/views.py:229) | `_can_create_company` | **عالية — عيب مؤكَّد اليوم** |
| [hr/auth_api.py](hr/auth_api.py:190) | تحقق البريد + السياسة + throttling + منع التعداد | **عالية — يمسّ تسجيل التجار؛ خلف عَلَم (R5)** |
| [frontend_v2/App.tsx](frontend_v2/App.tsx) · `types/common.ts` · `Sidebar.tsx` · `utils/viewPermissions.ts` · `layout/Breadcrumb.tsx` · `e2e/parity-baseline.json` | مسارات وشاشات وأعلام | متوسطة |

### تُنشأ
`core/modules.py` · `core/hooks.py` · `accountant_portal/**` (12 ملفاً) ·
`frontend_v2/components/accountant/**` (11 شاشة) · `frontend_v2/services/accountantApi.ts` ·
`frontend_v2/utils/engagement.ts` (نقي وقابل للاختبار — نمط `utils/reservedStock.ts`) ·
4 migrations · مجلدا اختبارات.

### **لا تُلمس**
`inventory/*` · `logistics/*` · `partners/models.py` · `hr/*` عدا `auth_api.py` ·
**`sales/models.py`** (لا عمود جديد على `VatStatement` — الحالة في جدول الوحدة) ·
أي خدمة ترحيل قائمة عدا سطر L3.

---

## 15. مخاطر الهجرة والتوافق الخلفي وخطة الrollback

| # | الخطر | التخفيف | Rollback |
|---|---|---|---|
| R1 | حارس L2 يمسّ كل طلب | الشرط ينفَّذ **فقط** إذا `role=='legal_accountant'` ⇒ صفر أثر على الأدوار القائمة؛ قِس `assertNumQueries` قبل/بعد | حذف الشرط (الحماية الأساسية تبقى بحذف العضوية عند الإلغاء) |
| R2 | حارس L3 داخل نقطة اختناق القيود | أول سطر: بوليان مكيَّش؛ اختبار 3 يثبت صفر استعلام إضافي | حذف السطر — النظام يعود لسلوكه الحالي بالضبط |
| R3 | توسيع `ROLE_CHOICES` يكسر شاشة الأدوار | الدور **آخر** `ROLE_ORDER`، والواجهة تقرأ الكتالوج ديناميكياً | إزالة القيمة |
| R4 | تشديد التسجيل يكسر تسجيل التجار | تحقق البريد والسياسة **خلف عَلَم**، يُفعَّل لمسار المحاسب أولاً | إطفاء العَلَم |
| R5 | `_can_create_company` — توسيعها قد تفتح إنشاء الشركات | التغيير يتجاهل عضويات `legal_accountant` **فقط** | استعادة الدالة |
| R6 | فرق SQLite/MySQL يخفي عيوباً | بوابتا M1 وM7 تشترطان MySQL | — |
| R7 | Django 5.1 مقابل 6.0 محلياً | ممنوع استعمال ميزات 6.0 حصرية؛ التحقق النهائي على 5.1 | — |
| R8 | تراكم بيانات وحدة أُطفئت | الإطفاء **يخفي ولا يحذف**؛ الارتباطات النشطة **تُعلَّق لا تُلغى** (الإلغاء لا رجعة فيه) | إعادة التفعيل تستأنف الارتباطات المعلَّقة يدوياً |

**استراتيجية الطرح:** M0–M2 على شركة تجريبية واحدة عبر سجل الوحدات. التوسّع بعد خضرة بوابة M4.

---

## 16. خارج النطاق صراحةً — `Later / Explicitly Out of Scope`

لا تُحوَّل إلى مهام تنفيذ ولا تُقترح على المالك:
OCR · bank feeds · كشف شذوذ بالذكاء الاصطناعي · إدارة مكتب محاسبة وموظفيه ·
CRM · رواتب/حضور/مهام موظفي الشركات · إدارة مخزون ومستودعات ·
شحن واستيراد وتخليص · محادثة عامة (يكفي طلب توضيح مرتبط بمستند) ·
تخصيص صلاحيات غير محدود · `bulk reclassification` ·
**أي ربط حكومي** (SHAAM / المقاصة الإلكترونية / رقم التخصيص) ·
التحقق الآلي من رخصة المحاسب (لا سجل رسمي قابل للربط) ·
فوترة اشتراك مكتب المحاسب وتسعيره.

**مكتب المحاسب نفسه ليس استثناءً من هذا:** هو **شركة `Tenant`** هو مديرها، وفواتير أتعابه
وسنداتُ قبضه تستعمل `SalesInvoice` و`CustomerPayment` القائمَين بلا سطر كود جديد. إن طُلبت
له ميزة خاصة لاحقاً، فهي مهمة منفصلة لا امتداد لهذه.

---

## 17. مسرد القرارات المرجعية السريع

| السؤال | الجواب النهائي |
|---|---|
| هل يُنشئ المحاسب فواتير للشركة؟ | لا افتراضاً — يُمنح `sales.invoice.create` لكل ارتباط (ق12) |
| هل يرحّل أو يلغي ترحيلاً؟ | لا افتراضاً — حزمة `full_accounting` |
| هل يعتمد الفترة؟ | لا افتراضاً — `tax.period.approve` + إعادة مصادقة |
| هل يقدّم الإقرار؟ | لا — `tax.filing.submit` يُمنح فردياً، والتقديم **تسجيل يدوي** لا إرسال آلي |
| هل يرى التكاليف والأرباح؟ | لا (ق8) |
| هل يرى بنود الفاتورة؟ | **نعم** داخل عرض المستند — بلا شاشات المخزون ولا أوامره |
| هل يحذف مستنداً مرحّلاً؟ | **لا، مطلقاً**. التصحيح بعكس/إشعار دائن/قيد تصحيح (م53، م54) |
| هل يدير أعضاء الشركة أو إعداداتها؟ | لا، مطلقاً |
| ماذا يحدث عند الإلغاء؟ | حذف العضوية و`MemberPermission` فوراً؛ الوصول يسقط في الطلب التالي |
| ماذا لو لم تكن الوحدة في خطة الزبون؟ | **404 على كل مسار، صفر استعلام، صفر JS، صفر مفتاح صلاحية** |
