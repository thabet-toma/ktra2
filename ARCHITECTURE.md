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
| `logistics` | الاستيراد والمشتريات: صفقة ← شحنة ← تخليص ← نقل ← فاتورة دولية + التكلفة المستوردة | 19,800 | 12,300 | `/api/logistics/` |
| `core` | طبقة مشتركة: عزل الشركة، الصلاحيات، التقارير، الوحدات المرخّصة، الداشبورد، المساعد الذكي | 17,300 | 10,300 | `/api/` (متفرّق) |
| `accounting` | دفتر الأستاذ: شجرة الحسابات، القيود، الشيكات، البنوك، الفترات المالية، العملات، الضريبة | 14,900 | 8,300 | `/api/accounting/` |
| `sales` | دورة البيع (عرض ← طلبية ← فاتورة ← تسليم ← تحصيل) + سندات صرف المورّدين | 11,800 | 9,800 | `/api/sales/` |
| `hr` | الموظفون والرواتب والحضور الجغرافي والورديات والعقود والطلبات والسلف والخدمة الذاتية | 7,100 | 3,900 | `/api/hr/` |
| `inventory` | المنتجات والمستودعات و`StockMovement` (المصدر الوحيد للرصيد ومتوسط التكلفة) والأرقام التسلسلية وحالة المخزون وحدود التجديد | 7,000 | 5,900 | `/api/inventory/` |
| `accountant_portal` | بوابة محاسب قانوني خارجي يخدم عدة شركات: ارتباطات، مراجعة، فترات ضريبية — وفوقها **طبقة مكتب** بنطاق `accountant=` لا `tenant=`: زبائن المكتب (ولو لم يكونوا شركات على المنصة) وبرامجه ومواعيده ومستنداته | 5,500 | 4,900 | `/api/accountant/` |
| `docshare` | مشاركة المستند برابط عام: صفحة **بلا مصادقة** يفتحها الزبون **أو المورّد** (‏HTML خادمي بوسوم Open Graph لمعاينة واتساب) + قبول/رفض عرض السعر منها. أربعة عشر نوعاً بجمهورين ومفتاحَي صلاحية | 3,300 | 2,200 | `/s/` · `/api/share/` · `/api/document-shares/` |
| `tenants` | تعريف الشركة وعزلها: الأعضاء، الأدوار، الفروع، دفاتر الترقيم، إقلاع شركة جديدة | 3,000 | 2,800 | `/api/tenants/` |
| `after_sales` | بطاقات الكفالة وأوامر الصيانة — **وحدة مرخّصة** | 2,200 | 2,000 | `/api/after-sales/` |
| `store` | المتجر العام: خمس نقاط قراءة **بلا مصادقة** مُقيَّدة بـ`Tenant.store_slug`، ولوحة إدارته المصادَق عليها (مظهر · صور · حملات · منتجات متجر) | 1,400 | 1,800 | `/api/store/` |
| `partners` | بطاقة الطرف الموحّدة (عميل/مورّد/…) وحساباتها البنكية وربطها بشجرة الحسابات | 1,200 | 800 | `/api/partners/` |
| `import_file` | ملف الاستيراد: قائمة تحقّق مستندات ومهامّ لكل صفقة، ترسو على الصفقة أو على شحنتها — **وحدة مرخّصة، محايدة مالياً بالكامل** | 800 | 1,000 | `/api/import-file/` |
| `realestate` | العمارات والوحدات وعدادات الكهرباء | 600 | 0 | `/api/realestate/` |
| `device_registry` | سجل الأجهزة الحساسة — **وحدة مرخّصة، محايدة مالياً بالكامل** | 600 | 500 | `/api/devices/` |
| `bridge` | جسر مزامنة Firestore القديم (`FirestoreMirrorDoc`) | 600 | 400 | `/api/mapper/` |
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

**ISSUE #86:** `accountant_portal` صار يستورد `partners.models.Partner` مباشرةً
(`accountant_portal/practice.py`) — زبون مكتب المحاسبة صار طرفاً لا سجلّاً
منفصلاً. الاتجاه يبقى وحيداً: `partners` لا يستورد `accountant_portal` بكود
حقيقي أبداً — حقلا `Partner.engagement`/`Partner.managed_tenant` مراجع نصّية
(`'accountant_portal.AccountantEngagement'`) يحلّها جانغو عبر سجلّ الـapps لا
استيراداً فعلياً، فلا دورة اعتماديات.

## قواعد عابرة للنظام

### 1. عزل الشركة (tenant) — لا middleware
1. **الحلّ:** `core/tenant_utils.py` `get_tenant(request)` — ترويسة `X-Tenant-Id`، ثم `user.tenant_id`، ثم auto-resolve لو كانت شركة واحدة فقط. الفشل = `None`، **لا سقوط عشوائي على شركة**.
2. **التحقق:** `_validate_user_tenant_access` (`core/tenant_utils.py`) يرفع `PermissionDenied` لغير عضو في `UserCompanyMembership`، ويرفض شركة `Status='suspended'`.
3. **الفلترة:** `TenantQuerySetMixin` (`core/mixins.py`) يطبّق `.filter(tenant=…)` ويرجع `.none()` بلا شركة. `BaseTenantViewSet` (`core/mixins.py`) ترثه ViewSets كل الـapps.
4. **الفرع:** `get_branch(request)` (`core/tenant_utils.py`) من `X-Branch-Id`، ويرفض فرعاً من شركة أخرى.

> **كل model يحمل `tenant` FK، وكل ViewSet يفلتر عليه. `get_queryset` بلا فلتر شركة = تسريب بيانات.**

### 2. الصلاحيات
`DEFAULT_PERMISSION_CLASSES = [IsAuthenticated, TenantRolePermission, TemplateSurfacePermission]` (`core/settings.py`).
الكتالوج ومصفوفة الأدوار في `core/access.py`؛ الإنفاذ خادمي عبر `require_perm` / `@requires_perm`.
سلسلة القرار: افتراضي الدور ← `tenants.RolePermission` (تجاوز لكل شركة) ← `MemberPermission` (لكل عضو).
دور `viewer` قراءة فقط. أعلام `/api/permissions/me/` **للعرض فقط** — إخفاء زر لا يحمي endpoint.

**القناع الحيّ (ISSUE #51):** `TemplateSurfacePermission` (`core/permissions.py`) يخفي بادئات مسار
API كاملة (404) لقالب شركة بعينه — طرحيّ لا إضافي (بخلاف `core/modules.py` (`MODULES`) الإضافي:
وحدة تُشترى فتظهر). السِجلّ `TEMPLATE_HIDDEN_PATH_PREFIXES` في `tenants/company_templates.py`،
ومرآته الواجهية `TEMPLATE_HIDDEN_VIEWS` في `frontend_v2/utils/viewPermissions.ts` (سِجلٌّ مستقل
بمفاتيح شاشات لا مسارات). ViewSet يُصرِّح بـ`permission_classes` صراحةً (بدل الاعتماد على
`DEFAULT_PERMISSION_CLASSES`) يلزمه ضمّ `TemplateSurfacePermission` يدوياً — `core/api_defaults.py`
(`ApiAuthAndUser`) يفعل ذلك للمسارات المشتركة.

**والقالب ليس قائمةً واحدة تُعرض في كل باب:** `client_book` دفترٌ يفتحه مكتبُ
محاسبةٍ لزبونه لا شركةٌ يملكها أحد — شاشةُ بدايته وحصّته ووحدته المرخَّصة كلّها
مبنيّة على وجود مكتبٍ فوقه. يفصل البابين `tenants/company_templates.py`
(`BOOK_ONLY_TEMPLATES` + `assert_self_serve_template`/`assert_book_template`)،
ويفرضهما `tenants/views.py` على النقاط الثلاث (`companies/`،
`companies/{id}/set-template/`، `companies/{id}/managed-books/`). مرآته الواجهية
`SELF_SERVE_COMPANY_TEMPLATES`/`CLIENT_BOOK_TEMPLATES`
(`frontend_v2/utils/companyTemplates.ts`) — عرضٌ للقاعدة لا مصدرُها.

**وضع العرض ليس صلاحية.** تحمل الحمولة نفسها حقل `ui_mode` (`core/access.py` — `user_ui_mode`)
المخزَّن على العضوية لكل (مستخدم × شركة). آليتان تعملان فوق قائمة واحدة ولا تتنازعان:
**الصلاحية تحجب، والوضع يُرتّب** — الوضع لا يمنح ما منعته الصلاحية ولا يحجب مساراً، والرابط
المباشر لشاشةٍ خارج «الوضع السهل» يبقى يعمل. والقناع **قناعان**: قائمةُ الشاشات، ثم العناصر
**داخل** كل شاشة (الاستحقاق، الضريبة، خصم السطر، أعمدة الجداول، التبويبات المتقدّمة) — سِجلٌّ
واحد لهما في `frontend_v2/utils/uiMode.ts` وغلافٌ تفاعليّ واحد `hooks/useSimpleUi.ts`. وفوقهما
**قاعدة السقوط للظهور**: عنصرٌ يحمل قيمةً فعلية (ضريبةٌ محسوبة، استحقاقٌ مُدخَل، رصيدٌ محجوز)
يظهر رغم الوضع — الإخفاء يقلّم الصفر ولا يُخفي رقماً يغيّر مالاً. تفصيله في
`docs/modules/frontend.md`.

### 3. الترحيل المحاسبي
**كل قيد يمرّ عبر `accounting.services` (`post_journal`)** — هي وحدها تفرض الفترة المفتوحة والتوازن الدقيق والـidempotency وقفل `select_for_update`.
إلغاء الترحيل عبر `unpost_document` — ويمرّ بحرّاس الفترة نفسها (`validate_fiscal_period` + `run_tax_period_guards`) بتاريخ المستند قبل أن يعكس شيئاً: الحذف من شهر مُقفَل تعديلٌ عليه كالإضافة. القيد المرحّل لا يُعدَّل (`accounting/models.py` — حارس في `JournalHeader.save`) — الحل قيد عكسي.
الفترات المالية تُنشأ شهرية افتراضياً (`create_fiscal_year`)، **لا تتقاطع** (`assert_no_period_overlap`)، وإعادة فتح فترة مغلقة تشترط سبباً يُحفظ في `AccountingAuditLog` — هي الاستثناء المُعلَن الوحيد من القفل.

المخالفات التاريخية (كتابة قيود مباشرة متجاوزةً `post_journal`) **عولجت في المرحلة 2** — كل الكتابة الخارجية الآن عبر `accounting/api.py`، ويحرسها عقد `no-direct-accounting-models` في `.importlinter`.

### 4. المخزون
`quantity_on_hand` و `avg_cost` لا يتغيّران إلا عبر `inventory.services.record_stock_movement` (`inventory/services.py`) — الدالة الوحيدة التي تقفل المنتج بـ`select_for_update` وتحفظ لقطات before/after.
الصادر لا يغيّر `avg_cost` إطلاقاً؛ الوارد وحده يطبّق معادلة المتوسط المرجّح.

### 5. ترقيم المستندات
عبر `tenants.TenantBook.get_next_number` وحده (`tenants/models.py`, `select_for_update` داخل `atomic`) — أو غلافه `accounting.services.next_document_number`.

### 6. الوحدات المرخّصة
`core/modules.py` يحكم أي وحدة مفعّلة لأي شركة حسب الخطة. الوحدات المرخّصة (`import`, `import_file`, `accountant_portal`, `after_sales`, `sensitive_devices`, `hr_suite`) **ترد 404 لشركة غير مرخّصة** — لا 403.

**و`hr_suite` وحدها بابان في تطبيق واحد**: الحضور والورديات والعقود والطلبات والخدمة الذاتية مرخّصة، وسطحُ الرواتب القديم (`employees`، `payslips`، `work-logs`…) **مفتوحٌ بلا ترخيص ولا يصير مرخّصاً** — حجبُه كان سيُطفئ رواتب شركاتٍ تشتغل عليه. كل ViewSet جديد يرث `hr/suite.py` (`HrSuiteViewSetBase`) ويُسجَّل على `suite_router`، وحارسٌ في `hr/tests/test_hr_suite_org.py` يمشي على الراوتر نفسه فيسقط إن أفلت واحدٌ من الوراثة.

### 7. الترقيم (pagination)
منتجان في `core/pagination.py`:
- `EnforcedPageNumberPagination` — **إلزامي**، يُرقّم دائماً ولو لم يمرَّر `?page=`. مفروض على نقاط «الفئة أ» (حركات المخزون، القيود، فواتير البيع والشراء، الصفقات، المدفوعات) بعد P0-5، وعلى قائمة المتجر العام (`store/views.py`) لأنها كتالوج ينمو بلا حدّ خلف نقطة **مجهولة**.
- `OptionalPageNumberPagination` — **opt-in** (الافتراضي العام): بلا `?page=` يُرجع كل الصفوف. يبقى مقصوداً للقوائم المنسدلة والـautocomplete.

### 8. فلترة التاريخ على أعمدة الوقت — لا `__date` أبداً
`created_at__date=X` تُترجَم في MySQL إلى `DATE(CONVERT_TZ(created_at,'UTC','Asia/Hebron'))`، و`CONVERT_TZ` بمنطقةٍ مُسمّاة تحتاج جداول `mysql.time_zone` مُحمَّلة — **وهي فارغة على خادم الإنتاج**، فتُعيد `NULL` ⇒ الشرط لا يطابق صفاً واحداً ⇒ الشاشة فارغة بلا خطأ ولا أثرٍ في اللوج. هكذا اختفى سجلّ النشاط بالكامل (١٣٤٤ صفاً في الجدول وصفرٌ على الشاشة)، ومعه عدّاد حدود الخطط الذي كان يرجع صفراً فلا يُنفَّذ حدّ.

المصدر الوحيد: `core/date_ranges.py` — `filter_local_date_range(qs, 'created_at', date_from=…, date_to=…)` يحسب حدود اليوم المحلي في بايثون ويقارن بها مباشرةً (`>= بداية اليوم` و`< بداية الغد`). لا اعتماد على إعداد الخادم، **والفهرس على العمود يبقى مستعملاً** بينما `DATE(CONVERT_TZ(...))` يُلغيه. ومعه `resolve_preset` لأسماء المدى الجاهزة (`today`/`yesterday`/`week`/`month`/`quarter`/`year`/`all`) — **والأسبوع يبدأ السبت**.

على `DateField` (مثل `movement_date` و`transaction_date`) لا مسألة: `TruncMonth`/`TruncWeek` عليها لا تمرّ بـ`CONVERT_TZ`. والحارس ساكن بالضرورة — `core/tests/test_date_ranges.py` يمسح كود المشروع بحثاً عن `__date` على عمود `DateTimeField`، لأن المجموعة تعمل على SQLite حيث `__date` تعمل تماماً فلا اختبارَ ديناميكيّ يكشف الانهيار.

## أين أبدأ؟

| المهمة | اقرأ | ابدأ من |
|---|---|---|
| فاتورة بيع: إنشاء/ترحيل/إلغاء ترحيل | `modules/sales.md` + `modules/accounting.md` | `sales/services/` (`post_sales_invoice`), `sales/views.py` |
| قيد محاسبي أو شجرة حسابات | `modules/accounting.md` | `accounting/services.py` (`post_journal`) |
| شيكات / بنوك / مطابقة | `modules/accounting.md` | `accounting/services.py` (`transfer_cheque`), `accounting/services.py` (`INCOMING_TRANSITIONS`) |
| صندوق نقدي: إنشاء/كشف/تحويل/جرد | `modules/accounting.md` §الخزينة | `accounting/services.py` (`create_cash_box`, `cash_box_statement`), `frontend_v2/components/finance/CashBoxList.tsx` |
| «من أي صندوق يُدفع؟» | `modules/accounting.md` §الخزينة | `accounting/services.py` (`resolve_cash_account`), `frontend_v2/utils/cashBox.ts` |
| حركة مخزون أو تكلفة | `modules/inventory.md` | `inventory/services.py` (`record_stock_movement`) |
| أرقام تسلسلية | `modules/inventory.md` | `inventory/serials.py` |
| «ما هذا الرقم؟» — مسح باركود/سيريال/IMEI | `modules/core.md` + `modules/frontend.md` | `core/scan.py` (`resolve_scan`), `frontend_v2/components/shared/ScanLookupPanel.tsx` |
| رحلة استيراد / مرحلة صفقة | `modules/logistics.md` | `logistics/domain/stages.py` (`advance_deal_stage`) |
| التكلفة المستوردة (landed cost) | `modules/logistics.md` | `logistics/landed_cost.py` |
| عميل/مورّد وربطه بالحسابات | `modules/partners.md` | `partners/views.py`, `partners/signals.py` |
| رواتب ومسير وسلف | `modules/hr.md` | `hr/payroll.py` (`compute_payslip`), `hr/contracts.py` (`effective_terms`) |
| حضور وانصراف وورديات | `modules/hr.md` | `hr/attendance.py` (`recompute_attendance_day`, `evaluate_punch`) |
| إجازات وطلبات واعتمادها | `modules/hr.md` | `hr/leave.py` (`leave_balance`), `hr/requests.py` (`approve`) |
| شركة جديدة / أعضاء / أدوار | `modules/tenants.md` | `tenants/services.py` (`create_company`), `tenants/company_templates.py` (`COMPANY_TEMPLATES`) |
| صلاحيات | `modules/tenants.md` | `core/access.py` |
| محاسب خارجي / ارتباطات | `modules/accountant_portal.md` | `accountant_portal/services.py` |
| مكتب المحاسب: زبائنه وبرامجه ومواعيده | `modules/accountant_portal.md` | `accountant_portal/practice.py` (`list_office_partners`) |
| تقارير | `modules/core.md` | `core/reports/` (`run_report`), `core/reports_api.py` |
| عزل الشركة / حلّ الـtenant | `modules/core.md` + هذا الملف §1 | `core/tenant_utils.py` (`get_tenant`) |
| صلاحيات / وحدات مرخّصة / كاش | `modules/core.md` | `core/access.py`, `core/modules.py` |
| مشاركة مستند برابط عام / معاينة واتساب | `modules/docshare.md` | `docshare/services.py` (`create_share`), `docshare/documents/` (`DOC_TYPES`) |
| أي شاشة أو خدمة في الواجهة | `modules/frontend.md` | `frontend_v2/services/restApi.ts` |
| «الوضع السهل» — قناع الواجهة المبسّطة | `modules/frontend.md` + `modules/tenants.md` | `frontend_v2/utils/uiMode.ts`, `core/access.py` (`user_ui_mode`) |
| نافذة عائمة (سحب/تحجيم) أو موضع شريط الإجراءات | `modules/frontend.md` §T-WIN | `frontend_v2/utils/windowGeometry.ts`, `frontend_v2/components/kit/KitFloatWindow.tsx`, `frontend_v2/components/layout/ActionBarRail.tsx` |
| مسودّة مستند محلية (ما كُتب لا يضيع) | `modules/frontend.md` §مسودّات المستندات | `frontend_v2/utils/documentDraft.ts`, `frontend_v2/hooks/useDocumentDraft.ts` |
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
  منذ 2026-07-19). وهي تثبّت `requirements.txt` أي Django 5.1.15 — فتغطّي فارق نسخة
  التطوير المحلية (6.0.3). **CI هي البوابة الآلية الوحيدة الآن** بعد حذف سكربت النشر
  (2026-08-12): لم يعد في المستودع أي مسار نشر آلي إلى الإنتاج (`ktra-pro.tech`).

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
| ~~اختناقات التوسّع (كاش ملفّي، ترقيم opt-in، فهارس ناقصة)~~ ✅ عولجت (المرحلة 5) — و**قِيست** في المرحلة 6: الاختناق المتبقي **واحد فقط وهو سعة الـworkers لا الكود** | `core/settings.py` | `docs/LOAD_TEST_RESULTS.md` |
| ~~القاعدة لا تُبنى من الهجرات~~ ✅ عولج 2026-08-12 — انظر الملاحظة أسفل الجدول | `core/models.py` (`SystemAttachment`) | `docs/SCALABILITY_AUDIT.md` (P0-14) |
| `accountant_portal.PracticeClient` مجمَّدٌ بموعد حذف — زبون المكتب صار `partners.Partner` (ISSUE #86) | `accountant_portal/models.py`، `accountant_portal/management/commands/migrate_practice_clients_to_partners.py` | `docs/decisions/practice_client_retirement.md` |

> ### ✅ البناء من صفر يعمل — وكان مكسوراً حتى 2026-08-12
> `SystemAttachment` (`core/models.py`) كان معرَّفاً بـ**`managed = False`** —
> النموذج الوحيد كذلك في المشروع. جانغو يسجّل `core/migrations/0001_initial.py`
> مطبَّقةً `[X]` **بلا أن يُنشئ جدول `system_attachments` إطلاقاً**، والإنتاج نجا
> لأن جدوله أُنشئ يدوياً خارج جانغو.
>
> **والأخطر أن مُكتشِف الهجرات يتجاهل حقول النماذج غير المُدارة**، فحقل `tenant`
> عاش في النموذج ولم يدخل الهجرة قطّ — أي أن قلب `managed` وحده كان سيُنشئ
> جدولاً بلا عمود `TenantID`. أُصلح الأمران معاً، وتُحقّق بـ`migrate` كامل على
> قاعدة MySQL فارغة: الجدول يُبنى بأعمدته السبعة ومفتاحه الأجنبي إلى `tenants`.
>
> القلب آمن على الإنتاج لأن الهجرة مسجَّلة في `django_migrations` فلا تُنفَّذ
> ثانيةً — نفس النمط المطبَّق سلفاً على `partners` و`tenants`.
