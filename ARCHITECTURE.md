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

| App | المسؤولية | كود | اختبار | مسار الـAPI |
|---|---|---:|---:|---|
| `logistics` | الاستيراد والمشتريات: صفقة ← شحنة ← تخليص ← نقل ← فاتورة دولية + التكلفة المستوردة | 15,004 | 7,860 | `/api/logistics/` |
| `sales` | دورة البيع (عرض ← طلبية ← فاتورة ← تسليم ← تحصيل) + سندات صرف المورّدين | 9,075 | 5,770 | `/api/sales/` |
| `core` | طبقة مشتركة: عزل الشركة، الصلاحيات، التقارير، الوحدات المرخّصة، الداشبورد، المساعد الذكي | 10,015 | 4,104 | `/api/` (متفرّق) |
| `accounting` | دفتر الأستاذ: شجرة الحسابات، القيود، الشيكات، البنوك، الفترات المالية، العملات، الضريبة | 8,896 | 2,275 | `/api/accounting/` |
| `inventory` | الأصناف والمستودعات و`StockMovement` (المصدر الوحيد للرصيد ومتوسط التكلفة) والأرقام التسلسلية | 4,277 | 2,437 | `/api/inventory/` |
| `accountant_portal` | بوابة محاسب قانوني خارجي يخدم عدة شركات: ارتباطات، مراجعة، فترات ضريبية | 3,440 | 2,913 | `/api/accountant/` |
| `hr` | الموظفون والرواتب والحضور والمهام | 2,132 | 743 | `/api/hr/` |
| `tenants` | تعريف الشركة وعزلها: الأعضاء، الأدوار، الفروع، دفاتر الترقيم، إقلاع شركة جديدة | 1,419 | 1,249 | `/api/tenants/` |
| `partners` | بطاقة الطرف الموحّدة (عميل/مورّد/…) وحساباتها البنكية وربطها بشجرة الحسابات | 1,212 | 686 | `/api/partners/` |
| `after_sales` | بطاقات الكفالة وأوامر الصيانة — **وحدة مرخّصة** | 954 | 535 | `/api/after-sales/` |
| `device_registry` | سجل الأجهزة الحساسة — **وحدة مرخّصة، محايدة مالياً بالكامل** | 543 | 483 | `/api/devices/` |
| `bridge` | جسر مزامنة Firestore القديم (`FirestoreMirrorDoc`) | 543 | 149 | `/api/mapper/` |
| `realestate` | العمارات والوحدات وعدادات الكهرباء | 548 | 0 | `/api/realestate/` |

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
`sales/models.py:5` و `logistics/models.py:6` يستوردان `Account/JournalHeader/TaxRate` كـFKs على مستوى الوحدة — أي تغيير سكيمة يموّج في migrations أربعة apps.

## قواعد عابرة للنظام

### 1. عزل الشركة (tenant) — لا middleware
1. **الحلّ:** `core/tenant_utils.py:25` `get_tenant(request)` — ترويسة `X-Tenant-Id`، ثم `user.tenant_id`، ثم auto-resolve لو كانت شركة واحدة فقط. الفشل = `None`، **لا سقوط عشوائي على شركة**.
2. **التحقق:** `_validate_user_tenant_access` (`core/tenant_utils.py:118`) يرفع `PermissionDenied` لغير عضو في `UserCompanyMembership`، ويرفض شركة `Status='suspended'`.
3. **الفلترة:** `TenantQuerySetMixin` (`core/mixins.py:7`) يطبّق `.filter(tenant=…)` ويرجع `.none()` بلا شركة. `BaseTenantViewSet` (`core/mixins.py:36`) ترثه ViewSets كل الـapps.
4. **الفرع:** `get_branch(request)` (`core/tenant_utils.py:189`) من `X-Branch-Id`، ويرفض فرعاً من شركة أخرى.

> **كل model يحمل `tenant` FK، وكل ViewSet يفلتر عليه. `get_queryset` بلا فلتر شركة = تسريب بيانات.**

### 2. الصلاحيات
`DEFAULT_PERMISSION_CLASSES = [IsAuthenticated, TenantRolePermission]` (`core/settings.py`).
الكتالوج ومصفوفة الأدوار في `core/access.py`؛ الإنفاذ خادمي عبر `require_perm` / `@requires_perm`.
سلسلة القرار: افتراضي الدور ← `tenants.RolePermission` (تجاوز لكل شركة) ← `MemberPermission` (لكل عضو).
دور `viewer` قراءة فقط. أعلام `/api/permissions/me/` **للعرض فقط** — إخفاء زر لا يحمي endpoint.

### 3. الترحيل المحاسبي
**كل قيد يمرّ عبر `accounting.services.post_journal`** (`accounting/services.py:479`) — هي وحدها تفرض الفترة المفتوحة والتوازن الدقيق والـidempotency وقفل `select_for_update`.
إلغاء الترحيل عبر `unpost_document`. القيد المرحّل لا يُعدَّل (`accounting/models.py:110`) — الحل قيد عكسي.

⚠️ **مخالفات معروفة** (انظر «الديون» أدناه): `logistics/views.py:1223` و `partners/signals.py:202` يكتبان قيوداً مباشرةً متجاوزَين `post_journal`.

### 4. المخزون
`quantity_on_hand` و `avg_cost` لا يتغيّران إلا عبر `inventory.services.record_stock_movement` (`inventory/services.py:154`) — الدالة الوحيدة التي تقفل الصنف بـ`select_for_update` وتحفظ لقطات before/after.
الصادر لا يغيّر `avg_cost` إطلاقاً؛ الوارد وحده يطبّق معادلة المتوسط المرجّح.

### 5. ترقيم المستندات
عبر `tenants.TenantBook.get_next_number` وحده (`tenants/models.py:244`, `select_for_update` داخل `atomic`) — أو غلافه `accounting.services.next_document_number`.

### 6. الوحدات المرخّصة
`core/modules.py` يحكم أي وحدة مفعّلة لأي شركة حسب الخطة. الوحدات المرخّصة (`import`, `accountant_portal`, `after_sales`, `sensitive_devices`) **ترد 404 لشركة غير مرخّصة** — لا 403.

### 7. الترقيم (pagination)
`core/pagination.py` `OptionalPageNumberPagination` — **opt-in**: يعمل فقط عند تمرير `?page=`. بدونه يرجع الـendpoint كل الصفوف. (دين أداء معروف — انظر `docs/REFACTOR_PROMPTS.md`.)

## أين أبدأ؟

| المهمة | اقرأ | ابدأ من |
|---|---|---|
| فاتورة بيع: إنشاء/ترحيل/إلغاء ترحيل | `modules/sales.md` + `modules/accounting.md` | `sales/services.py`, `sales/views.py` |
| قيد محاسبي أو شجرة حسابات | `modules/accounting.md` | `accounting/services.py:479` (`post_journal`) |
| شيكات / بنوك / مطابقة | `modules/accounting.md` | `accounting/services.py`, `accounting/models.py` (`Cheque.VALID_TRANSITIONS`) |
| حركة مخزون أو تكلفة | `modules/inventory.md` | `inventory/services.py:154` (`record_stock_movement`) |
| أرقام تسلسلية | `modules/inventory.md` | `inventory/serials.py` |
| رحلة استيراد / مرحلة صفقة | `modules/logistics.md` | `logistics/domain/stages.py:74` (`advance_deal_stage`) |
| التكلفة المستوردة (landed cost) | `modules/logistics.md` | `logistics/landed_cost.py` |
| عميل/مورّد وربطه بالحسابات | `modules/partners.md` | `partners/views.py`, `partners/signals.py` |
| رواتب | `modules/hr.md` | `hr/payroll.py` |
| شركة جديدة / أعضاء / أدوار | `modules/tenants.md` | `tenants/services.py` (`create_company`) |
| صلاحيات | `modules/tenants.md` | `core/access.py` |
| محاسب خارجي / ارتباطات | `modules/accountant_portal.md` | `accountant_portal/services.py` |
| تقارير | — | `core/reports.py`, `core/reports_api.py` |
| عزل الشركة / حلّ الـtenant | هذا الملف §1 | `core/tenant_utils.py` |

## الاختبارات

```bash
python manage.py test --settings=core.test_settings   # 1,025 اختباراً — يجب أن تبقى خضراء
```
- `core/test_settings.py`: SQLite في الذاكرة، `DummyCache`، والهجرات معطّلة (`run_syncdb`) للسرعة.
- `pytest.ini` موجود لكن `testpaths` فيه **لا يشمل** `accountant_portal` و `after_sales` و `device_registry`. استخدم `manage.py test` للتغطية الكاملة.

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
