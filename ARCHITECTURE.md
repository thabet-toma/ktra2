# ARCHITECTURE — K.T.R.A

> خريطة معمارية مضغوطة، مبنية على قراءة الكود مباشرةً بتاريخ 2026-08-11.
> **عند تعارض هذا الملف مع الكود، الكود هو المرجع.**
>
> **كيف تُستخدم:** اقرأ هذا الملف + `docs/modules/<الموديول المعني>.md` فقط.
> `docs/history/PROJECT_MAP.md` سجلّ تاريخي للمهام — لا يُقرأ افتراضياً.

## نظرة عامة

منصة ERP عربية متعددة الشركات (multi-tenant): محاسبة، مبيعات، مشتريات واستيراد، مخزون، رواتب، وبوابة محاسب خارجي.
Backend: Django 5.1.15 + DRF 3.16 على MySQL (إنتاج) / SQLite ذاكرة (اختبار).
Frontend: React 19 + TypeScript + Vite في `frontend_v2/` (بلا `src/`).
كل الـAPI تحت `/api/`، ومصادقة `TokenAuthentication` + `SessionAuthentication`.

## الـApps

الأسطر = Python بدون `migrations/`. «كود» = بدون ملفات الاختبار.
**الأرقام مقرَّبة للمئة ومولَّدة** (`python manage.py sync_docs`) — قيمتها ترتيبية
لا محاسبية. عمود «المسؤولية» مكتوب بيد ولا يمسّه التوليد.

<!-- AUTO:apps_table:START -->
| App | المسؤولية | كود | اختبار | مسار الـAPI |
|---|---|---:|---:|---|
| `logistics` | الاستيراد والمشتريات: صفقة ← شحنة ← تخليص ← نقل ← فاتورة دولية + التكلفة المستوردة | 17,400 | 8,300 | `/api/logistics/` |
| `core` | طبقة مشتركة: عزل الشركة، الصلاحيات، التقارير، الوحدات المرخّصة، الداشبورد، المساعد الذكي | 11,200 | 5,000 | `/api/` (متفرّق) |
| `sales` | دورة البيع (عرض ← طلبية ← فاتورة ← تسليم ← تحصيل) + سندات صرف المورّدين | 9,700 | 5,800 | `/api/sales/` |
| `accounting` | دفتر الأستاذ: شجرة الحسابات، القيود، الشيكات، البنوك، الفترات المالية، العملات، الضريبة | 9,600 | 2,800 | `/api/accounting/` |
| `inventory` | الأصناف والمستودعات و`StockMovement` (المصدر الوحيد للرصيد ومتوسط التكلفة) والأرقام التسلسلية | 4,400 | 2,500 | `/api/inventory/` |
| `accountant_portal` | بوابة محاسب قانوني خارجي يخدم عدة شركات: ارتباطات، مراجعة، فترات ضريبية | 3,400 | 2,900 | `/api/accountant/` |
| `hr` | الموظفون والرواتب والحضور والمهام | 2,200 | 900 | `/api/hr/` |
| `tenants` | تعريف الشركة وعزلها: الأعضاء، الأدوار، الفروع، دفاتر الترقيم، إقلاع شركة جديدة | 1,900 | 1,200 | `/api/tenants/` |
| `partners` | بطاقة الطرف الموحّدة (عميل/مورّد/…) وحساباتها البنكية وربطها بشجرة الحسابات | 1,000 | 700 | `/api/partners/` |
| `after_sales` | بطاقات الكفالة وأوامر الصيانة — **وحدة مرخّصة** | 1,000 | 500 | `/api/after-sales/` |
| `realestate` | العمارات والوحدات وعدادات الكهرباء | 600 | 0 | `/api/realestate/` |
| `bridge` | جسر مزامنة Firestore القديم (`FirestoreMirrorDoc`) | 600 | 400 | `/api/mapper/` |
| `device_registry` | سجل الأجهزة الحساسة — **وحدة مرخّصة، محايدة مالياً بالكامل** | 500 | 500 | `/api/devices/` |
<!-- AUTO:apps_table:END -->

## مخطط الاعتماديات

```
                    ┌──────────┐
                    │ tenants  │  ← بلا اعتماديات على apps أخرى
                    └────▲─────┘     (يصحّ استيراده من الجميع بلا دورة)
                         │ الكل
     ┌───────────────────┼───────────────────┐
     │                   │                   │
┌────┴─────┐      ┌──────┴──────┐     ┌──────┴──────┐
│ partners │◄─────│ accounting  │◄────│  inventory  │
└────▲─────┘      └──────▲──────┘     └──────▲──────┘
     │                   │  ▲                │
     │            ┌──────┴──┴────┐           │
     └────────────│    sales     │───────────┘
                  └──────▲───────┘
                         │  (SupplierPayment + ثابت serializer)
                  ┌──────┴───────┐
                  │  logistics   │──► accounting · inventory · partners
                  └──────────────┘

hr · accountant_portal · after_sales · core  ──►  accounting (+ غيره)
```

**`accounting` هو الـgod module**: مستورد مباشرةً من `sales`, `logistics`, `inventory`, `partners`, `hr`, `tenants`, `accountant_portal`, `core`.
`sales/models.py` و `logistics/models.py` يستوردان `Account/JournalHeader/TaxRate` كـFKs على مستوى الوحدة — أي تغيير سكيمة يموّج في migrations أربعة apps.

## قواعد عابرة للنظام

### 1. عزل الشركة (tenant) — لا middleware
1. **الحلّ:** `core/tenant_utils.py` `get_tenant(request)` — ترويسة `X-Tenant-Id`، ثم `user.tenant_id`، ثم auto-resolve لو كانت شركة واحدة فقط. الفشل = `None`، **لا سقوط عشوائي على شركة**.
2. **التحقق:** `_validate_user_tenant_access` (`core/tenant_utils.py`) يرفع `PermissionDenied` لغير عضو في `UserCompanyMembership`، ويرفض شركة `Status='suspended'`.
3. **الفلترة:** `TenantQuerySetMixin` (`core/mixins.py`) يطبّق `.filter(tenant=…)` ويرجع `.none()` بلا شركة. `BaseTenantViewSet` (`core/mixins.py`) ترثه ViewSets كل الـapps.
4. **الفرع:** `get_branch(request)` (`core/tenant_utils.py`) من `X-Branch-Id`، ويرفض فرعاً من شركة أخرى.

> **كل model يحمل `tenant` FK، وكل ViewSet يفلتر عليه. `get_queryset` بلا فلتر شركة = تسريب بيانات.**

### 2. الصلاحيات
`DEFAULT_PERMISSION_CLASSES = [IsAuthenticated, TenantRolePermission]` (`core/settings.py`).
الكتالوج ومصفوفة الأدوار في `core/access.py`؛ الإنفاذ خادمي عبر `require_perm` / `@requires_perm`.
سلسلة القرار: افتراضي الدور ← `tenants.RolePermission` (تجاوز لكل شركة) ← `MemberPermission` (لكل عضو).
دور `viewer` قراءة فقط. أعلام `/api/permissions/me/` **للعرض فقط** — إخفاء زر لا يحمي endpoint.

### 3. الترحيل المحاسبي
**كل قيد يمرّ عبر `accounting.services` (`post_journal`)** — هي وحدها تفرض الفترة المفتوحة والتوازن الدقيق والـidempotency وقفل `select_for_update`.
إلغاء الترحيل عبر `unpost_document`. القيد المرحّل لا يُعدَّل (`accounting/models.py` — حارس في `JournalHeader.save`) — الحل قيد عكسي.

المخالفات التاريخية (كتابة قيود مباشرة متجاوزةً `post_journal`) **عولجت في المرحلة 2** — كل الكتابة الخارجية الآن عبر `accounting/api.py`، ويحرسها عقد `no-direct-accounting-models` في `.importlinter`.

### 4. المخزون
`quantity_on_hand` و `avg_cost` لا يتغيّران إلا عبر `inventory.services.record_stock_movement` (`inventory/services.py`) — الدالة الوحيدة التي تقفل الصنف بـ`select_for_update` وتحفظ لقطات before/after.
الصادر لا يغيّر `avg_cost` إطلاقاً؛ الوارد وحده يطبّق معادلة المتوسط المرجّح.

### 5. ترقيم المستندات
عبر `tenants.TenantBook.get_next_number` وحده (`tenants/models.py`, `select_for_update` داخل `atomic`) — أو غلافه `accounting.services.next_document_number`.

### 6. الوحدات المرخّصة
`core/modules.py` يحكم أي وحدة مفعّلة لأي شركة حسب الخطة. الوحدات المرخّصة (`import`, `accountant_portal`, `after_sales`, `sensitive_devices`) **ترد 404 لشركة غير مرخّصة** — لا 403.

### 7. الترقيم (pagination)
صنفان في `core/pagination.py`:
- `EnforcedPageNumberPagination` — **إلزامي**، يُرقّم دائماً ولو لم يمرَّر `?page=`. مفروض على نقاط «الفئة أ» (حركات المخزون، القيود، فواتير البيع والشراء، الصفقات، المدفوعات) بعد P0-5.
- `OptionalPageNumberPagination` — **opt-in** (الافتراضي العام): بلا `?page=` يُرجع كل الصفوف. يبقى مقصوداً للقوائم المنسدلة والـautocomplete.

## أين أبدأ؟

| المهمة | اقرأ | ابدأ من |
|---|---|---|
| فاتورة بيع: إنشاء/ترحيل/إلغاء ترحيل | `modules/sales.md` + `modules/accounting.md` | `sales/services/` (`post_sales_invoice`), `sales/views.py` |
| قيد محاسبي أو شجرة حسابات | `modules/accounting.md` | `accounting/services.py` (`post_journal`) |
| شيكات / بنوك / مطابقة | `modules/accounting.md` | `accounting/services.py`, `accounting/models.py` (`Cheque.VALID_TRANSITIONS`) |
| حركة مخزون أو تكلفة | `modules/inventory.md` | `inventory/services.py` (`record_stock_movement`) |
| أرقام تسلسلية | `modules/inventory.md` | `inventory/serials.py` |
| رحلة استيراد / مرحلة صفقة | `modules/logistics.md` | `logistics/domain/stages.py` (`advance_deal_stage`) |
| التكلفة المستوردة (landed cost) | `modules/logistics.md` | `logistics/landed_cost.py` |
| عميل/مورّد وربطه بالحسابات | `modules/partners.md` | `partners/views.py`, `partners/signals.py` |
| رواتب | `modules/hr.md` | `hr/payroll.py` |
| شركة جديدة / أعضاء / أدوار | `modules/tenants.md` | `tenants/services.py` (`create_company`) |
| صلاحيات | `modules/tenants.md` | `core/access.py` |
| محاسب خارجي / ارتباطات | `modules/accountant_portal.md` | `accountant_portal/services.py` |
| تقارير | `modules/core.md` | `core/reports/` (`run_report`), `core/reports_api.py` |
| عزل الشركة / حلّ الـtenant | `modules/core.md` + هذا الملف §1 | `core/tenant_utils.py` (`get_tenant`) |
| صلاحيات / وحدات مرخّصة / كاش | `modules/core.md` | `core/access.py`, `core/modules.py` |
| أي شاشة أو خدمة في الواجهة | `modules/frontend.md` | `frontend_v2/services/restApi.ts` |
| **أين نقطة الـAPI؟** | — | `docs/API_INDEX.md` (مولَّد — كل النقاط ← الـView ← الملف) |

## الاختبارات

```bash
python -m pytest <app>/tests -q      # الحلقة الداخلية أثناء التعديل
python -m pytest -q -n auto          # البوابة قبل أي commit (‎~80ث؛ ‎~114 تسلسلياً)
```
> العدد لا يُكتب في الوثائق — يتغيّر مع كل اختبار يُضاف، ومكانه خرج الأمر نفسه.

- **pytest هو المُشغّل لا `manage.py test`.** الأخير يكتشف أصناف `TestCase` وحدها، و253
  اختباراً هنا مكتوبة دوالَّ على مستوى الوحدة فلا يراها (‎18% من المجموعة تبدو خضراء وهي لم
  تعمل). قِيس أن pytest مجموعةٌ فائقة تماماً — بفرق صفر بمقارنة معرِّفات الاختبارات.
- **البوابة لا تُقسَّم بحسب الموديول.** `accounting` مستوردة من ثماني apps، وتعديلٌ في app
  يُسقط اختبارات غيرها روتينياً هنا — جلسةٌ واحدة أعطت مثالين: تعديل نموذج في `logistics`
  أسقط اختباراً في `core`، وكنسةٌ في `accounting/services.py` أسقطت ثمانية اختبارات شيكات.
  «شغّل موديولك فقط» كان سيمرّر الاثنين. التقسيم للحلقة الداخلية السريعة وحدها.
- `core/test_settings.py`: SQLite في الذاكرة، `DummyCache`، هجرات معطّلة (`run_syncdb`)،
  وتهشير MD5 — كلّها سرعةٌ بلا تنازل عن الصحة. الإنتاج يبقى على PBKDF2.
- `pytest.ini` يجمع كل `<app>/tests`؛ يحرس اكتمالَ قائمته `core/tests/test_docs_freshness.py`
  بعد أن سقطت منها ثلاث apps فغابت عن CI بصمت. CI تشغّل pytest تسلسلياً تحت `coverage`
  (‎`-n auto` يحتاج تركيب تغطية موزَّعة، ولا يستحقّه زمنٌ صار مقبولاً بعد المُجزِّئ السريع).
- **الإنفاذ آلي لا طوعي:** CI تعمل على `main` و`newktra` (كانت على `main` وحده وهو متوقف
  منذ 2026-07-19)، وبوابة `deploy.ps1` قبل النشر تشغّل pytest الكامل. وCI تثبّت
  `requirements.txt` أي Django 5.1.15 — فهي التي تغطّي فارق نسخة التطوير المحلية (6.0.3).

## اصطلاحات

- الـmodels/views/serializers/services في **جذر كل app** (`sales/views.py`) — لا مجلد `api/`.
- ملفات الاختبار في `<app>/tests/`.
- الوثائق: هذا الملف + `docs/modules/` (حالي) · `docs/decisions/` (قرارات) · `docs/history/` (تاريخي).
- Frontend: `frontend_v2/` مباشرةً (`components/`, `services/`, `utils/`) — بلا `src/`. الـbase client هو `services/restApi.ts`. Tailwind فقط، لا inline styles.

## الديون المعمارية المعروفة

| الدين | الموقع | المرجع |
|---|---|---|
| ~~قيود تُكتب يدوياً متجاوزةً `post_journal`~~ ✅ عولج (المرحلة 2) | كل الكتابة عبر `accounting.api`/`post_journal` | `docs/REFACTOR_PROMPTS.md` مرحلة 2 |
| `logistics` يستورد داخليات `sales.serializers` | `logistics/serializers/_helpers.py` (`CHEQUE_DUE_DATE_REQUIRED`) | `docs/REFACTOR_PROMPTS.md` (دين مؤجل) |
| 5 نماذج دفع منفصلة | `logistics/`, `sales/`, `accounting/` | `docs/decisions/payment_model_unification.md` |
| مرفقات كحقول URL متفرّقة بلا نموذج موحّد | `logistics/models.py` | `docs/decisions/attachments_model.md` |
| ~~ملفات عملاقة~~ ✅ عولج (المرحلة 3) — الأربعة الكبرى صارت حزماً | `logistics/views/`, `sales/services/`, `logistics/serializers/`, `core/reports/` | `docs/REFACTOR_PROMPTS.md` مرحلة 3 |
| اختناقات التوسّع (كاش ملفّي، ترقيم opt-in، فهارس ناقصة) | `core/settings.py` | `docs/REFACTOR_PROMPTS.md` مراحل 4-6 |
