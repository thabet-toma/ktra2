# tenants — الشركة (Tenant) وعزلها: الهوية والأعضاء والأدوار والصلاحيات والفروع ودفاتر الترقيم

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
app صغير (3,309 سطر Python) لكنه **عابر للنظام كله**: يُعرّف `Tenant` — وحدة العزل التي يحمل مفتاحَها كل model في كل app آخر —
ومعها إعدادات الشركة، فروعها، دفاتر ترقيم مستنداتها، عضويات مستخدميها وأدوارهم، وتجاوزات الصلاحيات لكل دور ولكل عضو.
كما يملك `create_company` الذي يُقلع شركة جديدة كاملة (إعدادات + دفاتر أنواع مستنداتها + شجرة حسابات + فرع رئيسي + مستودع + عضوية مدير) — **على الخطة التجريبية بأربعة عشر يوماً** (`core/plans.py` — `trial_end_date`)، لا `Enterprise` بلا حدود ولا انتهاء.
`create_company` يقبل `template` (كلمة مفتاحية، افتراضه `general`) يحدّد أيّ بذرة حسابات وأيّ أنواع دفاتر تُزرع — السِجلّ في `tenants/company_templates.py` (`COMPANY_TEMPLATES`). `general` ينتج ما كان يُنتَج دائماً حرفياً (10 دفاتر لكل نوع من الخمسة عشر)، و`accounting_firm` يزرع شجرة أتعاب مهنية بلا مخزون ولا استيراد وسبعة أنواع دفاتر فقط، ومعها خمس خدمات جاهزة (`ACCOUNTING_FIRM_SERVICES`) كلٌّ مربوطٌ بحساب أتعابه (ISSUE #78) — بلا هذا الربط تبقى `4103`-`4106` حسابات ميتة. **`client_book` (ISSUE #81، القسم ١ من #77)** يزرع دفتر عميلٍ يُمسَك بالسندات وحدها — بلا مخزون ولا تكلفة بضاعة مباعة ولا فواتير بيع/شراء: نقدية وبنوك وذمم ومصاريف تشغيلية (13 بنداً تحت `52`)، وخمسة أنواع دفاتر فقط (سند قبض · سند صرف · سند مصروف · سند إيراد · قيد يومية). المشتريات مصروفٌ مباشر (`51`)، والجرد الدوري يُقفله المحاسب بقيدٍ يدوي واحد. **`tyres` (قالب الإطارات)** مطابقٌ اليوم لـ`general` حرفياً (`coa=None` و`document_types=None`) — الغاية **مفتاحٌ مستقل** تُعلَّق عليه تخصيصات قطاع الإطارات لاحقاً دون المساس بشركات `general` القائمة؛ فنقلُ شركةٍ `general` إليه يكتب حقلاً واحداً ولا يُنشئ صفّاً. `Tenant.template` يحفظ المفتاح المستعمَل. **ولكلِّ قالبٍ بابُه (بلاغ المالك):** `client_book` **يُرفض 400** على `companies/` و`set-template/` — ليس شركةً يملكها أحد بل دفترٌ يفتحه مكتبٌ لزبونه، ومن أنشأه مستقلاً حصل على دفترٍ بلا مكتب: بلا زرّ عودة، وخارج حصّة `office.managed_books`، وبلا ترخيص `accountant_portal` الذي تزرعه #87 — فشاشةُ بدايته تردّ 404. وعلى `managed-books/` انقلبت القاعدة: `client_book` **هو الافتراضي** حين لا يُذكر قالب (كان `general`)، وهو الوحيد المقبول — القالبان الآخران يفتحان نظاماً تجارياً كاملاً للزبون، نقيضَ ما بُني له هذا الباب. الفصل في `tenants/company_templates.py` (`BOOK_ONLY_TEMPLATES` + `assert_self_serve_template`/`assert_book_template`) ويفرضه `tenants/views.py` على النقاط الثلاث.
**تبديل القالب لشركة قائمة (ISSUE #64، القرار 4 — يرفع القناع ولا ينزع المزروع):** `TenantViewSet.set_template` (`companies/{id}/set-template/`، `admin.settings.manage`) يستدعي `tenants/services.py` (`switch_company_template`) — ذرّي بالكامل. يزرع الناقص من بذرة القالب الجديد (حسابات دليلٍ فوق الموجود بمطابقة الكود، وأنواع دفاتر لم يُزرع للشركة منها دفترٌ واحد بعد) **ولا يمسّ صفاً قائماً إطلاقاً**: لا حذف، لا `is_active=False`، لا إعادة تسمية حسابٍ يتشارك كوده بين القالبين (`4102` يبقى باسمه القديم لو أُنشئ بقالبٍ سابق). القناع الحيّ يتبدّل فوراً لأن الدالّة تستدعي `invalidate_tenant_cache()` — ضروري في النشر أحادي الشركة حيث يحمل `core.tenant_utils` مرجعاً بذاكرة العملية لكائن `Tenant` بمعزل عن صفقة القفل. يبقى `template` للقراءة فقط في `TenantSerializer` — نفس تعليل `store_slug` (كتابةٌ من نقطة خاصة تحمل تحقّقها، لا `PATCH` عام). يسجَّل التبديل في `AccountingAuditLog` (`action='TEMPLATE_SWITCH'`).
**تسمية القالب (ISSUE #82، القسم ٦ من #77):** اسم «فاتورة مبيعات»/«منتج» يتبدّل
بالقالب («فاتورة أتعاب»/«خدمة» لـ`accounting_firm` و`client_book`، محسومٌ في
#48) عبر معجمٍ مستقل — `core/terminology.py` (`term`, `terms_payload`) — لا
داخل `company_templates.py`؛ يصل على حمولة `/api/permissions/me` نفسها التي
تحمل `template`. التفصيل الكامل في `docs/modules/core.md`.

**القناع الحيّ (ISSUE #51، ووسّعته #81 لـ`client_book`):** `tenants/company_templates.py` (`TEMPLATE_HIDDEN_PATH_PREFIXES`) يخفي بادئات مسار API عن قالب `accounting_firm` (المخزون، ومسارات اللوجستيات والمشتريات مسمّاةً واحداً واحداً — و`supplier-payments` مستثنى عمداً لأن سند الصرف يبقى ولو كان مساره تحتها، وملف الاستيراد، والأجهزة الحساسة، وما بعد البيع، والمتجر) — طرحيّ لا إضافي، بخلاف `core/modules.py` (`MODULES`). `client_book` يرث هذه القائمة (`_GOODS_MOVEMENT_HIDDEN_PATHS`) كاملةً ويزيد عليها فواتير البيع وأوامر البيع وعروض الأسعار والإرساليات والمحجوزات (`/api/sales/invoices/`، `/quotations/`، `/orders/`، `/delivery-orders/`، `/reports/reserved-stock/`) — لا فاتورة بيع أصلاً في دفترٍ يُمسَك بالسندات؛ سند القبض (`/api/sales/payments/`) وسند الصرف يبقيان مفتوحين لنفس علّة `accounting_firm`. ينفّذه `core.permissions.TemplateSurfacePermission` (404 لا 403) عبر نقطتَي تركيب: `DEFAULT_PERMISSION_CLASSES` (`core/settings.py`) للـViewSets التي لا تُصرِّح صراحةً، و`core/api_defaults.py` (`ApiAuthAndUser`) لمن يُصرِّح. الحمولة `/api/permissions/me` تحمل `template` بجانب `modules` لتحرس به الواجهة (`frontend_v2/utils/viewPermissions.ts` — `TEMPLATE_HIDDEN_VIEWS`).
**القناع يفحص بادئة المسار لا معاملات الاستعلام (ISSUE #88):** `/api/inventory/products/?view=lookup` (عقد المنتقي الضيّق) محجوبٌ عن `accounting_firm`/`client_book` تماماً كباقي `/api/inventory/` — فمنتقي المستندات كان عاجزاً عن الوصول إلى خدمات #78 من شاشة الفاتورة. الحلّ نقطةٌ مستقلة خارج البادئة المقنَّعة (`GET /api/lookup/products/`، `ProductLookupViewSet` في `inventory/views.py`) لا رفعُ القناع عن `products/` — يحرس التفصيل `docs/modules/inventory.md`.
جدول `Currency` يعيش هنا أيضاً ويستورده `accounting` و`sales` و`logistics` منه.
**الدفتر المُدار (ISSUE #52):** `Tenant.managed_by` علمٌ من جنس `is_example`/`import_enabled`/`store_slug` — FK لشركة أخرى (مكتب محاسبة) تملك هذا الدفتر وتديره. `create_company` يقبله كلمةً مفتاحية (`managed_by`) فيمرّ الزرع نفسه لا مساراً موازياً. الدفتر المُدار **لا يُعَدّ في حصّة خطة أحد** كشركة (حدّه المستقل `office.managed_books` في `core/plans.py`)، ولا يظهر في `companies/my-companies/` (`tenants/views.py` — `my_companies` يستثني `tenant__managed_by__isnull=True`)، ويُفتح من `companies/{office_id}/managed-books/` (`TenantViewSet.managed_books`) بصلاحية `admin.members.manage` على المكتب المالك. العزل: `TenantViewSet.get_queryset` يمنح مدير المكتب رؤية كل دفاتره بلا عضويةٍ صريحة لكل واحد (قرار 7)، والموظف يُسند بعضوية `UserCompanyMembership` صريحة وإلا 404 لا 403 — ولا بُعد عزلٍ ثانٍ غير `tenant`. الرؤية وحدها لا تكفي: `core/tenant_utils.py` (`_validate_user_tenant_access`) تشترط صفّ عضويةٍ على الشركة المطلوبة، فاستُثني منها مديرُ المكتب على دفاتر مكتبه — وإلا رأى في القائمة دفتراً يردّه كل نداء عملٍ بـ`X-Tenant-Id`. **والدفتر المُدار لا يشترك**: خطتُه وتاريخُ انتهائه يُقرآن من مكتبه (`core/plans.py` — `_billing_tenant`)، وإلا ورث تجربة أربعة عشر يوماً من `create_company` فأقفل على مكتبٍ مشترِكٍ ودافع بعد أسبوعين.
**تسليم الدفاتر (ISSUE #54، نمط Xero لا QuickBooks):** `tenants.models.BookHandoverRequest` طلبٌ ينشئه مدير المكتب المالك (`tenants/services.py` — `create_handover_request`) على دفترٍ مُدار، يحمل صلاحيةً زمنية (`expires_at`، أسبوعان) ويستهدف مستخدماً مسجَّلاً مسبقاً (`invited_user`) — لا يمسّ `managed_by` عند الإنشاء. القبول (`accept_handover_request`) وحده — من العميل المدعوّ حصراً، والباقي «غير موجود» — يُسقط `managed_by` ذرّياً (`transaction.atomic` حول قفل الطلب والدفتر معاً)، ويمنح العميل عضوية `manager` على الدفتر؛ فحص الانتهاء يقع **خارج** تلك الصفقة الذرّية عمداً كي لا يتراجع تثبيت `expired` مع أي رفضٍ لاحق. **لا أثر محاسبي إطلاقاً**: لا `post_journal` ولا `record_stock_movement` في أي مسار من هذا الملف. حصّة `office.managed_books` تتحرّر تلقائياً لأنها عدٌّ حيّ على `managed_by` لا عدّاداً مخزَّناً. **إلغاء وصول المكتب بعد التسليم إجراءٌ منفصل صريح** عبر `TenantViewSet.remove_member` القائم أصلاً — لا يقع تلقائياً مع القبول، ويستدعيه العميل بصفته المدير الجديد. سطح الـAPI مستقل (`BookHandoverRequestViewSet` تحت `handover-requests/`) لأن العميل قبل القبول بلا عضوية على الدفتر فلا يصلح مسار `X-Tenant-Id` الاعتيادي — هويةٌ لا شركة، كسطح `accountant_portal`.

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
| `tenants/company_templates.py` | سِجلّ قوالب الشركة `COMPANY_TEMPLATES` (`general` · `accounting_firm` · `client_book` · `tyres`) — بذرة كل قالب وأنواع دفاتره، وتصنيفُ بابه (`BOOK_ONLY_TEMPLATES`/`SELF_SERVE_TEMPLATES` + `assert_self_serve_template`/`assert_book_template`) | 121 |
| `tenants/models.py` | 9 models (Tenant, Settings, Branch, Book, Membership, RolePermission, …) | 361 |
| `tenants/serializers.py` | تمثيل الشركة والإعدادات والدفاتر والعضوية | 92 |
| `tenants/urls.py` | router تحت `/api/tenants/` | 16 |
| `core/tenant_utils.py` | (خارج الـapp، لكنه مُنفِّذ العزل) حلّ الشركة + التحقق من العضوية | 227 |
| `core/access.py` | (خارج الـapp) كتالوج الصلاحيات + `ROLE_DEFAULTS` + `require_perm` | 418 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Tenant` (:18) | `TenantID` (PK), `CompanyName`, `Status` (Active/Suspended/Trial), `SubscriptionPlan` (Trial/Basic/Pro/Enterprise), `subscription_ends_at` (NULL = بلا انتهاء), `import_enabled`, `is_example`, `managed_by` (FK لذاته — دفترٌ مُدار)، `DomainName` (unique) | مُشار إليه بـ`tenant` FK من كل model في كل app |
| `Currency` (:4) | `CurrencyID`, `Code`, `Symbol`, `IsBaseCurrency` | **عام بلا tenant**؛ يستورده accounting/sales/logistics |
| `TenantSettings` (:54) | `default_vat_rate` (16.00), `fiscal_period_*`, `dashboard_month_start_day`, `font_scale`/`font_family`, `idle_timeout_minutes` (5..1440), `licensed_dealer_no` | `tenant` **OneToOne**, `currency`, `default_freight_credit_account`→Account |
| `Branch` (:141) | `name`, `code`, `is_main`, `is_active` | `tenant`, `unique_together (tenant, code)`؛ يشارك الشجرة والمنتجات والشركاء ويعزل الفواتير/المخزون/القيود |
| `TenantBook` (:203) | `document_type` (15 نوعاً), `book_number`, `last_used_number`, `is_active` | `tenant`, `branch` (NULL = دفتر شركة)، `unique_together (tenant, branch, document_type, book_number)` |
| `UserCompanyMembership` (:279) | `role` (7 أدوار), `is_default`, `can_access_import`, `is_example_access`, `ui_mode` (`simple`/`advanced`، افتراضي `advanced`) | `user`→auth.User, `tenant`, `unique_together (user, tenant)` |
| `RolePermission` (:312) | `role`, `permission_key`, `allowed` | `tenant`, `unique_together (tenant, role, permission_key)` |
| `MemberPermission` (:339) | `permission_key`, `allowed` | `membership`, `unique_together (membership, permission_key)` |
| `WhatsAppContact` (:170) | `phone_number` (unique), `is_active` | `tenant` — حارس العزل الوحيد على مسار واتساب |
| `BookHandoverRequest` (`models.py`) | `status` (pending/accepted/expired/cancelled), `expires_at`, `accepted_at` | `book`→Tenant، `office`→Tenant (لقطة وقت الإنشاء)، `invited_user`→auth.User (القابل الوحيد) |

## دوال الـservices العامة
```python
# tenants/services.py
def ensure_operational_accounts(tenant) -> list[str]:                  # يضمن (حسب بذرة قالب الشركة) 1107/1109/1110/2106-2109/2111 في شجرة قائمة (idempotent) — ISSUE #61
def ensure_operational_account(tenant, code: str):                     # يضمن حساباً واحداً ويعيده — ولو غاب أبوه المعياري
def ensure_base_currencies():                                          # يزرع ILS/USD ويعيد العملة الأساسية
def create_company(name: str, creator_user, *, template: str = 'general', managed_by: Tenant | None = None) -> Tenant:  # إقلاع شركة كاملة: إعدادات + دفاتر + COA حسب القالب + خدماته (ISSUE #78) + فرع + مستودع + عضوية مدير
def switch_company_template(tenant: Tenant, template: str, *, actor_user=None) -> dict:  # ISSUE #64 — يبدّل tenant.template ويزرع الناقص فقط؛ لا نزع إطلاقاً (القرار 4)
def set_example_company(tenant: Tenant | None) -> None:                # يعيّن شركة المثال الوحيدة ويزامن عضويات الوصول
def ensure_example_company_access(user) -> None:                       # يُلحق المستخدمين الجدد بشركة المثال عند أول تحميل
def member_payload(m: UserCompanyMembership) -> dict:                  # تمثيل عضوية موحّد (إدارة الشركة + لوحة المنصة)
def is_last_manager(tenant: Tenant, membership: UserCompanyMembership) -> bool:   # هل هذه آخر عضوية مدير؟
def create_branch(tenant: Tenant, name: str, code: str) -> Branch:     # إنشاء فرع تحت شركة أم
def create_handover_request(*, book: Tenant, requested_by, client_identifier: str) -> BookHandoverRequest:  # ISSUE #54 — يفتح طلب تسليم، بلا مساس بـmanaged_by
def accept_handover_request(*, request_id: int, accepting_user) -> BookHandoverRequest:                     # القبول وحده يُسقط managed_by ذرّياً — لا أثر محاسبي

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
| POST | `companies/{pk}/set-template/` | `TenantViewSet.set_template` (ISSUE #64) — يتطلب `admin.settings.manage`؛ body `{"template": "..."}`؛ يزرع الناقص من بذرة القالب الجديد ولا ينزع شيئاً |
| DELETE | `companies/{pk}/` | **محظور دائماً** — يرفع خطأ (views.py:280) |
| GET/POST | `companies/{pk}/members/` | `members` (views.py:290) — GET لأي عضو، POST يتطلب `admin.members.manage` |
| POST | `companies/{pk}/members/change-role/` · `members/remove/` | views.py:345 / 365 — مع حماية آخر مدير (views.py:339) |
| POST | `companies/{pk}/set-import-enabled/` | `set_import_enabled` (views.py:382) — سوبر أدمن |
| POST | `companies/{pk}/members/set-import-access/` | `set_member_import_access` (views.py:401) — مدير الشركة |
| GET | `companies/my-companies/` | `my_companies` (views.py:418) — يستثني الدفاتر المُدارة (`tenant__managed_by__isnull=True`) |
| GET/POST | `companies/{office_id}/managed-books/` | `TenantViewSet.managed_books` — مدير المكتب فقط؛ POST يفحص `office.managed_books` بـ`enforce_limits` قبل الإنشاء. **مستدعيها في الواجهة** (ISSUE #65): `frontend_v2/services/managedBooksApi.ts` وحده — لا `POST companies/` |
| GET/POST | `handover-requests/` | `BookHandoverRequestViewSet` (ISSUE #54) — مدير المكتب المالك ينشئ، والقائمة تُريه طلباته المُرسَلة والعميل طلباته الواردة |
| POST | `handover-requests/{id}/accept/` | `BookHandoverRequestViewSet.accept` — العميل المدعوّ حصراً؛ يُسقط `managed_by` ذرّياً ولا يمسّ وصول المكتب |
| POST | `companies/set-default/` | `set_default` (views.py:428) |
| POST | `companies/set-ui-mode/` | `set_ui_mode` — وضع عرض المستدعي في الشركة النشطة؛ بلا صلاحية إدارية، قيمة غير صالحة أو بلا عضوية ⇒ 400، و`viewer` ⇒ 403 من حارس المنصة |
| GET/POST | `branches/` | `BranchViewSet` (views.py:153) — الإنشاء يتطلب `admin.settings.manage` (views.py:175-177) |

## الاعتماديات
**يعتمد على:**
- `accounting` (models مباشرة) — `tenants/services.py` `from accounting.models import Account, Currency`؛ `create_company` يزرع شجرة الحسابات صفاً صفاً (`services.py:11-89`, `:245-258`).
- `inventory` (models مباشرة، استيراد مؤجَّل داخل الدالة) — `tenants/services.py` `from inventory.models import Warehouse` لإنشاء المستودع الافتراضي.
- `core` — `tenants/views.py` `from core.access import require_perm`؛ و`tenants/services.py` `from core.tenant_utils import invalidate_tenant_cache`، و`from core.models import TenantModule` + `from core.modules import invalidate_module_cache` (ISSUE #87 — ترخيص `accountant_portal` عند زرع `client_book`).
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
- **تبديل القالب لا ينزع شيئاً (ISSUE #64، القرار 4)**: `switch_company_template` تزرع الناقص من بذرة القالب الجديد فوق الموجود — لا حذف حساب أو دفتر، لا `is_active=False`، لا إعادة تسمية حسابٍ بكودٍ مشترك بين القالبين. القناع الحيّ (أعلاه) هو ما يُخفي الشاشات، لا محو الصفّ. استدعِ `invalidate_tenant_cache()` بعد أي تعديلٍ يدويّ مباشر على `tenant.template` خارج هذه الدالّة — وإلا بقي القناع يقرأ القيمة القديمة في النشر أحادي الشركة.
- **خدمات القالب تُزرع مع `create_company` وحدها (ISSUE #78)**: `ACCOUNTING_FIRM_SERVICES` (`tenants/company_templates.py`) — خمسة بنودٍ `is_service=True` كلٌّ مربوطٌ بحساب أتعابه عبر `Product.sale_account_override` — تُزرع فقط عند إنشاء شركةٍ جديدة بقالب `accounting_firm`. **لا تزرعها `switch_company_template`**: تبديل قالب شركةٍ قائمة إلى `accounting_firm` يزرع الحسابات وأنواع الدفاتر الناقصة (كالمعتاد، القرار 4) ولا يزرع خدمات — نطاق التذكرة نقطة زرعٍ واحدة صريحة. `general` بلا `services` (`None`) فلا بند يُزرع.
- **ترخيص `accountant_portal` يُزرع مع `create_company` وحدها لقالب `client_book` (ISSUE #87)**: شاشة بدايته («الوضع المالي») تستهلك `ClientSummaryView`/`ClientTrendView` تحت `guard_module_surface` (`core/modules.py`)، وبلا صفّ `TenantModule(enabled=True)` صريح تردّ 404 من أول يوم. `general` و`accounting_firm` لا يُلمَسان — الأخير لوحته (`practice/dashboard/`) هوياتيّة النطاق وتستدعى بلا `X-Tenant-Id` عمداً فلا تمرّ بهذا الحارس أصلاً. **لا تُزرع في `switch_company_template`**: نفس قاعدة ISSUE #78 أعلاه — نقطة زرعٍ واحدة صريحة، وتبديل قالب شركةٍ قائمة إلى `client_book` لا يمنحها ترخيصاً رجعياً.
- **السِجلّ مكرَّرٌ في موضعين ويجب أن يتطابقا**: `tenants/company_templates.py` و`frontend_v2/utils/companyTemplates.ts` (ومعه اتّحاد النوع `CompanyTemplateKey`). قالبٌ يُضاف في بايثون وحدها **لا يظهر للمستخدم أبداً** — الشاشتان (`FirstCompanyOnboarding` و`CompanyManagementModal`) تقرآن السِجلّ الأمامي. وأيقونتُه تُسجَّل في `TEMPLATE_ICONS` داخل الشاشتين وإلا سقطت إلى `Building2` فظهرت بطاقتان متجاورتان بأيقونةٍ واحدة. والعُرفان مختلفان عمداً: بايثون kebab-case (`building-2`) والواجهة PascalCase (`Building2`).
- **أمر السطر للنقل**: `python manage.py switch_company_template --tenant-id N --template KEY` — **معاينةٌ افتراضاً بلا كتابة**، و`--apply` ينادي `switch_company_template` نفسها بلا نسخ منطقها.
- **قالبٌ لكل باب، والحارس خادميّ**: لا تُضف `client_book` إلى قائمة قوالب إنشاء شركة في الواجهة — الخادم يردّها 400 عبر `assert_self_serve_template`، ولا تُسقط الحارس عن `managed-books/` لتسمح بدفترٍ `general`: القالبُ **هو** المنتج الذي بُني له ذلك الباب.
- **`TenantSettings.voucher_account_entry_mode` (بلاغ المالك)**: `free` (الافتراضي، سلوك #56/#80 حرفياً) أو `linked`. يقرأه `accounting.services._voucher_account_entry_is_linked` — نقطةُ قراءةٍ واحدة يستدعيها سندا المصروف والإيراد معاً — فيرفض `expense_account_name`/`revenue_account_name` حين يُلزم بالربط. غيابُ صفّ الإعدادات = `free`: القاعدة تفشل **مفتوحةً** عمداً كي لا تتوقّف شركةٌ قائمة عن إدخال مصاريفها.
- **`ensure_operational_accounts` تحترم بذرة القالب (ISSUE #61)**: الحسابات المضمونة (`1107`/`1109`/`1110`/`2106-2109`/`2111`) تُشتقّ من بذرة قالب الشركة (`tenant.template` ← `COMPANY_TEMPLATES[...]['coa']`) لا من `COA_DATA` مباشرة — وإلا أعاد `heal_company_seed` زرع ذمم شركاء اللوجستيات (`2106-2109`) في شجرة `accounting_firm` التي أسقطتها بذرتها عمداً (أبوها `21` موجودٌ فلا يمنعه غياب الأب). `general` (`coa=None`) يعني `COA_DATA` نفسها فبلا أي تغيير. `ensure_operational_account` **المفردة** (بلا `s`، تُستدعى من مسارات الترحيل: الشيكات والرواتب وعجز الصندوق) مستثناة عمداً — تُنشئ الحساب ولو غاب أبوه أو قالبه لا يحمله، كي لا يتوقّف ترحيل سندٍ.
- **الدفتر المُدار لا يُحذف ولا مسار موازياً لإنشائه**: `create_company` وحدها تزرعه (كلمة `managed_by`)، والحذف ممنوع أصلاً على كل الشركات. حصّته `office.managed_books` (`core/plans.py`) تُفحص **قبل** الإنشاء بـ`enforce_limits`، ولا بُعد عزلٍ ثانٍ غير `tenant`: الوصول عضويةٌ صريحة أو مديرُ المكتب المالك (`TenantViewSet.get_queryset`).
- **تسليم الدفاتر لا يمسّ صفاً محاسبياً واحداً**: `accept_handover_request` يقلب `managed_by` وحده — لا `post_journal`، لا `record_stock_movement`، لا قيدٌ يُعاد. الصفقة ذرّية (`transaction.atomic` حول قفل الطلب والدفتر)، وفحص الانتهاء يقع **خارجها** عمداً كي يبقى طلبٌ فات وقته `expired` ولو رُفض القبول لسببٍ آخر. لا تسليم بلا قبول العميل المدعوّ حصراً (`invited_user`) — شرط قبولٍ لا تفصيل واجهة. **إلغاء وصول المكتب بعد التسليم منفصلٌ صريح** (`members/remove` القائم)، لا يقع تلقائياً.

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
| `tests/test_client_book_template_api.py` (ISSUE #81، وISSUE #87 مراجعة) | `client_book`: البذرة (لا مخزون، 13 بند مصاريف تشغيلية) وخمسة دفاتر فقط، القناع يرث `accounting_firm` ويزيد فواتير البيع وأخواتها، سند القبض/الصرف يبقيان مفتوحين، سند إيراد وسند مصروف فعليان يُرحَّلان ويتوازنان، و`general`/`accounting_firm` بلا تغيير؛ `ClientBookAccountantPortalLicenseTest` — `accountant_portal` تُرخَّص تلقائياً لـ`client_book` وحده، نقطتا الملخّص/الاتجاه تردّان 200 لا 404، `general`/`accounting_firm` بلا ترخيص، وتبديل القالب لا يرخّص رجعياً |
| `tests/test_template_surface_rules.py` (بلاغ المالك) | قالبٌ لكل باب: `client_book` يُرفض 400 على `companies/` وعلى `set-template/` (والقالب القديم يبقى)، و`managed-books/` يفتح على `client_book` بلا تصريح ويرفض `general`/`accounting_firm` |
| `tests/test_company_template_switch_api.py` | تبديل القالب (ISSUE #64): صفر حذفٍ في الاتجاهين، حسابٌ مشترك الكود لا يُعاد تسميته، لا تعطيل حساب، الناقص يُزرع مرّةً واحدة (التكرار عديم الأثر)، غير المدير يُرفض، قالبٌ مجهول 400 عربي، سطر تدقيق، القناع يتبدّل فوراً بلا ترويسة، وأرصدة `JournalLine` مطابقة حرفياً بعد قيدٍ فعلي |
| `tests/test_managed_books_api.py` | الدفتر المُدار: مكتب Basic يفتح 3 وينكسر عند الرابع، غيابه عن `my-companies` رغم عضوية صريحة، مدير المكتب يرى كل دفاتره بلا عضوية لكل واحد، موظف غير مُسند ⇒ 404، مستخدم مكتب آخر لا يرى الدفتر إطلاقاً |
| `tests/test_book_handover_api.py` | تسليم الدفاتر (ISSUE #54): طلبٌ بلا قبول لا يغيّر شيئاً، انتهاء الصلاحية يمنع القبول، بعد القبول العميل مديرٌ والدفتر خارج `managed-books` والحصّة تتحرّر، وصول المكتب يبقى حتى `members/remove` الصريح، أرصدة دليل الحسابات (قبل/بعد قيدٍ فعلي) متطابقة حرفياً، عزل الإنشاء والقبول |
| `sales/tests/test_office_service_fee_accounts.py` (`sales`) | ISSUE #78: `accounting_firm` تُنشئ خمس خدمات مربوطة بحساباتها عند `create_company`، و`general` صفر خدمات |
