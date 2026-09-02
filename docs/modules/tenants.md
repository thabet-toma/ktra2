# tenants — الشركة (Tenant) وعزلها: الهوية والأعضاء والأدوار والصلاحيات والفروع ودفاتر الترقيم

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
app صغير (3,309 سطر Python) لكنه **عابر للنظام كله**: يُعرّف `Tenant` — وحدة العزل التي يحمل مفتاحَها كل model في كل app آخر —
ومعها إعدادات الشركة، فروعها، دفاتر ترقيم مستنداتها، عضويات مستخدميها وأدوارهم، وتجاوزات الصلاحيات لكل دور ولكل عضو.
كما يملك `create_company` الذي يُقلع شركة جديدة كاملة (إعدادات + دفاتر أنواع مستنداتها + شجرة حسابات + فرع رئيسي + مستودع + عضوية مدير) — **على الخطة التجريبية بأربعة عشر يوماً** (`core/plans.py` — `trial_end_date`)، لا `Enterprise` بلا حدود ولا انتهاء.
`create_company` يقبل `template` (كلمة مفتاحية، افتراضه `general`) يحدّد أيّ بذرة حسابات وأيّ أنواع دفاتر تُزرع — السِجلّ في `tenants/company_templates.py` (`COMPANY_TEMPLATES`). `general` ينتج ما كان يُنتَج دائماً حرفياً (10 دفاتر لكل نوع من الخمسة عشر)، و`accounting_firm` يزرع شجرة أتعاب مهنية بلا مخزون ولا استيراد وسبعة أنواع دفاتر فقط. `Tenant.template` يحفظ المفتاح المستعمَل؛ تبديله لاحقاً غير مبنيّ بعد.
**القناع الحيّ (ISSUE #51):** `tenants/company_templates.py` (`TEMPLATE_HIDDEN_PATH_PREFIXES`) يخفي بادئات مسار API عن قالب `accounting_firm` (المخزون، ومسارات اللوجستيات والمشتريات مسمّاةً واحداً واحداً — و`supplier-payments` مستثنى عمداً لأن سند الصرف يبقى ولو كان مساره تحتها، وملف الاستيراد، والأجهزة الحساسة، وما بعد البيع، والمتجر) — طرحيّ لا إضافي، بخلاف `core/modules.py` (`MODULES`). ينفّذه `core.permissions.TemplateSurfacePermission` (404 لا 403) عبر نقطتَي تركيب: `DEFAULT_PERMISSION_CLASSES` (`core/settings.py`) للـViewSets التي لا تُصرِّح صراحةً، و`core/api_defaults.py` (`ApiAuthAndUser`) لمن يُصرِّح. الحمولة `/api/permissions/me` تحمل `template` بجانب `modules` لتحرس به الواجهة (`frontend_v2/utils/viewPermissions.ts` — `TEMPLATE_HIDDEN_VIEWS`).
جدول `Currency` يعيش هنا أيضاً ويستورده `accounting` و`sales` و`logistics` منه.

## آلية عزل الشركات (القاعدة العابرة للنظام)
**لا يوجد middleware للشركة** (`core/settings.py:113-125`). العزل ثلاثي الطبقات، وكلّه على مستوى الطلب:

1. **الحل (Resolution)** — `core/tenant_utils.py` `get_tenant(request)`: يقرأ ترويسة **`X-Tenant-Id`** أولاً؛ ثم `user.tenant_id`؛
   ثم auto-resolve إن كانت في القاعدة شركة واحدة فقط. **لا سقوط عشوائي إلى شركة**؛ الفشل يُرجِع `None` (أو `PermissionDenied` مع `raise_on_missing=True`).
2. **التحقق من العضوية** — `core/tenant_utils.py` `_validate_user_tenant_access`: يبحث عن `UserCompanyMembership(user, tenant)`؛
   غيابها ⇒ `PermissionDenied` مع تسجيل `SECURITY ALERT` (`:136-143`). السوبر يُوزر يتجاوز. شركة `Status='suspended'` تُرفض لغير السوبر أدمن (`:167-177`).
   الدور المُكتشَف يُخزَّن على الطلب في `request._tenant_membership_role` (`:165`) لتستعمله طبقة الصلاحيات بلا استعلام ثانٍ.
3. **فلترة الـqueryset** — `core/mixins.py:7-20` `TenantQuerySetMixin.get_queryset` يُطبّق `qs.filter(tenant=tenant)`، **ويُرجع `.none()` إن لم تُحَل الشركة**؛
   و`TenantCreateMixin.perform_create` (`core/mixins.py:22-33`) يحقن الشركة عند الإنشاء ويرفع 400 بدل السقوط إلى `tenant_id=1`.
   `BaseTenantViewSet` (`core/mixins.py`) يجمع الاثنين وترثه ViewSets كل الـapps.

فوق ذلك، `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated, TenantRolePermission, TemplateSurfacePermission]` (`core/settings.py`) —
و`TenantRolePermission` (`core/permissions.py`) يمنع أي كتابة من دور `viewer` ويقيّد `legal_accountant` بمسارات `/api/accountant/` فقط، و`TemplateSurfacePermission` (`core/permissions.py`) يخفي مسارات القناع الحيّ (أعلاه) بـ404.

**الأدوار والصلاحيات** — `UserCompanyMembership.role` من سبعة: manager / accountant / legal_accountant / sales / procurement / staff / viewer (`tenants/models.py:280-288`).
الترتيب النهائي للصلاحية (`core/access.py:352-383`): **افتراضي الدور** (`ROLE_DEFAULTS`, `core/access.py`) ← **تجاوز الدور** (`RolePermission`) ← **تجاوز العضو** (`MemberPermission`, الأعلى).
المدير مستثنى من كل تجاوز فلا يُقفَل خارج نظامه (`core/access.py:359-361`). الإنفاذ خادمي عبر `require_perm` / `@requires_perm` (`core/access.py`, `:408`)؛
`/api/permissions/me` للعرض فقط. وحدة الاستيراد طبقة ثانية مستقلة: `Tenant.import_enabled` (سوبر أدمن) × `UserCompanyMembership.can_access_import` (مدير الشركة) — `core/import_access.py`.

**وضع عرض الواجهة (`ui_mode`) — تفضيل شخصي لا صلاحية.** يسكن العضوية نفسها لأنها أصلاً صفٌّ لكل
(مستخدم × شركة): الشخص نفسه قد يكون «سهلاً» في شركته و«متقدماً» في شركة يحاسب لها. الافتراضي
`advanced` بلا backfill — لا تُبدَّل تجربة عضو قائم صامتاً. يُقرأ بـ`core/access.py` (`user_ui_mode`)
ويُنشر في حمولة `/api/permissions/me/`، ويُكتب بـ`tenants/views.py` (`set_ui_mode`) على عضوية
**المستدعي وحده** في الشركة المحلولة من سياق الطلب. لم يُخزَّن في `TenantSettings` عمداً: الكتابة
هناك تشترط `admin.settings.manage` فما كان غير المدير ليحفظ وضعه أصلاً.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `tenants/views.py` | ViewSets: الإعدادات، الدفاتر، العملات، الشركات والأعضاء، الفروع | 445 |
| `tenants/services.py` | `create_company` + شجرة الحسابات `COA_DATA` + شركة المثال + الفروع | 383 |
| `tenants/company_templates.py` | سِجلّ قوالب الشركة `COMPANY_TEMPLATES` (`general` · `accounting_firm`) — بذرة كل قالب وأنواع دفاتره | 121 |
| `tenants/models.py` | 9 models (Tenant, Settings, Branch, Book, Membership, RolePermission, …) | 361 |
| `tenants/serializers.py` | تمثيل الشركة والإعدادات والدفاتر والعضوية | 92 |
| `tenants/urls.py` | router تحت `/api/tenants/` | 16 |
| `core/tenant_utils.py` | (خارج الـapp، لكنه مُنفِّذ العزل) حلّ الشركة + التحقق من العضوية | 227 |
| `core/access.py` | (خارج الـapp) كتالوج الصلاحيات + `ROLE_DEFAULTS` + `require_perm` | 418 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Tenant` (:18) | `TenantID` (PK), `CompanyName`, `Status` (Active/Suspended/Trial), `SubscriptionPlan` (Trial/Basic/Pro/Enterprise), `subscription_ends_at` (NULL = بلا انتهاء), `import_enabled`, `is_example`, `DomainName` (unique) | مُشار إليه بـ`tenant` FK من كل model في كل app |
| `Currency` (:4) | `CurrencyID`, `Code`, `Symbol`, `IsBaseCurrency` | **عام بلا tenant**؛ يستورده accounting/sales/logistics |
| `TenantSettings` (:54) | `default_vat_rate` (16.00), `fiscal_period_*`, `dashboard_month_start_day`, `font_scale`/`font_family`, `idle_timeout_minutes` (5..1440), `licensed_dealer_no` | `tenant` **OneToOne**, `currency`, `default_freight_credit_account`→Account |
| `Branch` (:141) | `name`, `code`, `is_main`, `is_active` | `tenant`, `unique_together (tenant, code)`؛ يشارك الشجرة والمنتجات والشركاء ويعزل الفواتير/المخزون/القيود |
| `TenantBook` (:203) | `document_type` (15 نوعاً), `book_number`, `last_used_number`, `is_active` | `tenant`, `branch` (NULL = دفتر شركة)، `unique_together (tenant, branch, document_type, book_number)` |
| `UserCompanyMembership` (:279) | `role` (7 أدوار), `is_default`, `can_access_import`, `is_example_access`, `ui_mode` (`simple`/`advanced`، افتراضي `advanced`) | `user`→auth.User, `tenant`, `unique_together (user, tenant)` |
| `RolePermission` (:312) | `role`, `permission_key`, `allowed` | `tenant`, `unique_together (tenant, role, permission_key)` |
| `MemberPermission` (:339) | `permission_key`, `allowed` | `membership`, `unique_together (membership, permission_key)` |
| `WhatsAppContact` (:170) | `phone_number` (unique), `is_active` | `tenant` — حارس العزل الوحيد على مسار واتساب |

## دوال الـservices العامة
```python
# tenants/services.py
def ensure_operational_accounts(tenant) -> list[str]:                  # يضمن 1107/1110/2106-2109/2111 في شجرة قائمة (idempotent)
def ensure_operational_account(tenant, code: str):                     # يضمن حساباً واحداً ويعيده — ولو غاب أبوه المعياري
def ensure_base_currencies():                                          # يزرع ILS/USD ويعيد العملة الأساسية
def create_company(name: str, creator_user, *, template: str = 'general') -> Tenant:  # إقلاع شركة كاملة: إعدادات + دفاتر + COA حسب القالب + فرع + مستودع + عضوية مدير
def set_example_company(tenant: Tenant | None) -> None:                # يعيّن شركة المثال الوحيدة ويزامن عضويات الوصول
def ensure_example_company_access(user) -> None:                       # يُلحق المستخدمين الجدد بشركة المثال عند أول تحميل
def member_payload(m: UserCompanyMembership) -> dict:                  # تمثيل عضوية موحّد (إدارة الشركة + لوحة المنصة)
def is_last_manager(tenant: Tenant, membership: UserCompanyMembership) -> bool:   # هل هذه آخر عضوية مدير؟
def create_branch(tenant: Tenant, name: str, code: str) -> Branch:     # إنشاء فرع تحت شركة أم

# tenants/models.py — ترقيم المستندات (يستهلكه كل الـapps)
@classmethod
def get_next_number(cls, tenant_id: int, document_type: str,
                    book_number: int = 0, branch_id: int | None = None) -> int:   # ذرّي عبر select_for_update
```

## أهم الـAPI endpoints
كل ما يلي تحت `/api/tenants/` (`core/urls.py`) — الـrouter في `tenants/urls.py:7-13`.

| Method | المسار | الـview |
|---|---|---|
| GET/PUT/PATCH | `settings/current/` | `TenantSettingsViewSet.current` (views.py:57) — الكتابة تتطلب `admin.settings.manage` (:73) |
| GET/POST | `books/` · `books/seed/` | `TenantBookViewSet` (views.py:89) · `seed` (views.py:118) |
| GET | `currencies/` | `CurrencyViewSet` (views.py:22) — قراءة فقط |
| GET/POST | `companies/` | `TenantViewSet` (views.py:216) — القائمة مقصورة على شركات عضويات المستخدم (views.py:224-230)؛ الإنشاء manager-only (views.py:232-248) |
| PUT/PATCH | `companies/{pk}/` | يتطلب `admin.settings.manage` (views.py:271-278) |
| DELETE | `companies/{pk}/` | **محظور دائماً** — يرفع خطأ (views.py:280) |
| GET/POST | `companies/{pk}/members/` | `members` (views.py:290) — GET لأي عضو، POST يتطلب `admin.members.manage` |
| POST | `companies/{pk}/members/change-role/` · `members/remove/` | views.py:345 / 365 — مع حماية آخر مدير (views.py:339) |
| POST | `companies/{pk}/set-import-enabled/` | `set_import_enabled` (views.py:382) — سوبر أدمن |
| POST | `companies/{pk}/members/set-import-access/` | `set_member_import_access` (views.py:401) — مدير الشركة |
| GET | `companies/my-companies/` | `my_companies` (views.py:418) |
| POST | `companies/set-default/` | `set_default` (views.py:428) |
| POST | `companies/set-ui-mode/` | `set_ui_mode` — وضع عرض المستدعي في الشركة النشطة؛ بلا صلاحية إدارية، قيمة غير صالحة أو بلا عضوية ⇒ 400، و`viewer` ⇒ 403 من حارس المنصة |
| GET/POST | `branches/` | `BranchViewSet` (views.py:153) — الإنشاء يتطلب `admin.settings.manage` (views.py:175-177) |

## الاعتماديات
**يعتمد على:**
- `accounting` (models مباشرة) — `tenants/services.py` `from accounting.models import Account, Currency`؛ `create_company` يزرع شجرة الحسابات صفاً صفاً (`services.py:11-89`, `:245-258`).
- `inventory` (models مباشرة، استيراد مؤجَّل داخل الدالة) — `tenants/services.py` `from inventory.models import Warehouse` لإنشاء المستودع الافتراضي.
- `core` — `tenants/views.py` `from core.access import require_perm`؛ و`tenants/services.py` `from core.tenant_utils import invalidate_tenant_cache`.
- `accountant_portal` (استيراد مؤجَّل من `core/tenant_utils.py`) لفحص ارتباط المحاسب القانوني.
- `tenants/models.py` نفسه بلا اعتماديات على apps أخرى (Django فقط) — لذا يصحّ استيراده من الجميع بلا دورة.

**يعتمد عليه:** فعلياً **كل app**: `sales`, `logistics`, `accounting`, `inventory`, `partners`, `hr`, `realestate`, `after_sales`, `bridge`, `device_registry`, `accountant_portal`, `core`.
أمثلة: `logistics/models.py` · `accounting/models.py` (يستورد `Tenant, Currency` ويعيد تصديرهما فعلياً) · `hr/models.py` · `realestate/models.py` · `sales/models.py`.

## قواعد لا يجوز كسرها
- **كل model يحمل `tenant` FK، وكل ViewSet يفلتر عليه.** استخدم `BaseTenantViewSet` (`core/mixins.py`) ولا تكتب `get_queryset` بلا فلتر شركة.
- **لا سقوط افتراضي إلى شركة**: `get_tenant` يُرجع `None` لا شركةً عشوائية (`core/tenant_utils.py:104-114`)، و`TenantQuerySetMixin` يُرجع `.none()` عندها (`core/mixins.py`) — لا `tenant_id=1` (`core/mixins.py:28-31`).
- **العضوية شرط الوصول**: `_validate_user_tenant_access` يرفع `PermissionDenied` لغير العضو (`core/tenant_utils.py`)، والسوبر يوزر وحده يتجاوز (`:126-127`).
- **الصلاحية تُفحص خادمياً** بـ`require_perm`/`@requires_perm` (`core/access.py`, `:408`) — إخفاء زر في الواجهة ليس حماية (موثَّق في `core/access.py:17-18`).
- **المدير لا يُجرَّد بصلاحية**: `user_permissions` يعود مبكراً للمدير قبل تطبيق أي تجاوز (`core/access.py:359-361`).
- **لا يُترك تينانت بلا مدير**: `is_last_manager` (`services.py`) + `_assert_not_last_manager` (`views.py`).
- **حذف الشركة ممنوع من الـAPI** نهائياً (`tenants/views.py:280-282`).
- **ترقيم المستندات عبر `TenantBook.get_next_number` فقط** — قفل صف `select_for_update` داخل `transaction.atomic` (`models.py:244-273`)؛ لا تحسب `last_used_number + 1` يدوياً.
- **الفرع يشارك الشجرة/المنتجات/الشركاء ويعزل الفواتير والمخزون والقيود** عبر بُعد `branch` (`models.py:141-149`, `services.py:374-380`) — لا تنسخ شجرة حسابات لفرع.
- **`viewer` قراءة فقط** على مستوى المنصة (`core/permissions.py`)، و`legal_accountant` يكتب من `/api/accountant/` فقط (`core/permissions.py:74-81`).
- **الشركة الجديدة تبدأ تجريبية**: `create_company` يضبط `SubscriptionPlan='Trial'` و`Status='Trial'` و`subscription_ends_at` بعد `TRIAL_PERIOD_DAYS` — الترقية أو التمديد من لوحة المنصة، والحدود تتبع الخطة تلقائياً.
- **انتهاء الاشتراك يمنع الكتابة وحدها**: مضيُّ `subscription_ends_at` يجعل الشركة للقراءة والطباعة والتصدير، والكتابة ترد 403 (`core/permissions.py` — `TenantRolePermission`). التاريخ **شامل** (يوم الانتهاء يوم عمل)، والسؤال عنه يمرّ بـ`core/plans.py` (`subscription_expiry`) وحده — لا تعيد حساب «هل انتهى» في نقطة ثانية. تعديل التاريخ من لوحة المنصة فقط: `subscription_ends_at` للقراءة في `TenantSerializer` عمداً. ومسارٌ يستبدل `permission_classes` (بوابة المحاسب) لا يرث الحارس — يستدعي `require_active_subscription` صراحةً.
- **`ui_mode` تفضيل عرض لا صلاحية**: لا يمنح وصولاً ولا يحجب مساراً ولا يُستشار في أي قرار خادمي. كتابته ذاتية على عضوية المستدعي وحدها (`tenants/views.py` — `set_ui_mode`)، ولم يُثقَب لأجله حارس `viewer`: رفضه 403 مقبول ومعالَج في الواجهة (`docs/modules/frontend.md`).
- **القناع الحيّ طرحيّ لا إضافي**: لا تُدرَج شاشة جوهرية (مخزون/لوجستيات/متجر) في `core/modules.py` (`MODULES`) لإخفائها عن قالب — أضِف بادئة مسارها إلى `TEMPLATE_HIDDEN_PATH_PREFIXES` (`tenants/company_templates.py`) بدل ذلك. ومسارٌ يُصرِّح بـ`permission_classes` صراحةً (بوابة المحاسب، أو أي `ApiAuthAndUser` مباشر) لا يرث `DEFAULT_PERMISSION_CLASSES` — يلزمه `TemplateSurfacePermission` صراحةً في قائمته.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `tests/test_company_isolation.py` (299) | رفض شركة بلا عضوية، تبديل الشركة، شجرة حسابات معزولة، تسلسل فواتير مستقل، من يملك إنشاء شركة |
| `tests/test_read_isolation.py` (87) | endpoints القوائم الفعلية (منتجات/شركاء/فئات/حركات/قيود) تُرجع فارغاً لشركة جديدة ولو امتلأت أخرى |
| `tests/test_branch_isolation.py` (96) | الفرع يشارك الشجرة ويعزل الفواتير والترقيم؛ رفض فرع شركة أخرى؛ الإنشاء manager-only |
| `tests/test_import_access.py` (181) | نموذج الاستيراد من مستويين + إخفاء شجرة 53* عمّن لا يملك الصلاحية |
| `tests/test_company_admin.py` (178) | تعديل الشركة manager-only، منع الحذف، إدارة الأعضاء وحماية آخر مدير |
| `tests/test_company_seeding.py` (79) | `create_company`: COA + دفاتر + بداية فارغة + عضوية مدير + عدم المساس بشركات قائمة |
| `tests/test_tenant_book_concurrent.py` (61) | ذرّية `get_next_number` تحت التزامن |
| `tests/test_operational_accounts.py` (124) | شركة جديدة جاهزة تشغيلياً بلا حساب يدوي (1107/1110/2106-2109/2111) |
| `tests/test_session_settings.py` (79) · `test_appearance_settings.py` (65) | مهلة الخمول والمظهر: محفوظة خادمياً، معزولة لكل شركة، ضمن نطاق صالح |
| `tests/test_ui_mode.py` | وضع العرض: الافتراضي `advanced`، الكتابة تمسّ عضوية المستدعي في الشركة النشطة وحدها، وضعان لنفس الشخص في شركتين، قيمة غير صالحة/بلا عضوية ⇒ 400، `viewer` ما زال ممنوعاً من الكتابة، والحمولة `/permissions/me` تعكس المحفوظ (وسوبر أدمن بلا عضوية ⇒ `advanced`) |
| `tests/test_company_template_api.py` | القالب عند الإنشاء: `general` مطابق حرفياً لما يُنتَج اليوم، `accounting_firm` يزرع شجرته ويُسقط الحسابات التجارية، مفتاح مجهول يُرفض 400 |
| `tests/test_company_template_mask_api.py` | القناع الحيّ: `accounting_firm` يردّ 404 على المخزون/اللوجستيات/المشتريات/المتجر ويُبقي `supplier-payments` مفتوحاً، والقناع يصمد بلا ترويسة `X-Tenant-Id`، و`general` صفر تغيير |
