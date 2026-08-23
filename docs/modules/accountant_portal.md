# accountant_portal — بوابة المحاسب القانوني الخارجي: ارتباط بعدة شركات، مراجعة مالية، وفترات ضريبية

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

بوابة لمحاسب/مكتب خارجي يخدم عدة شركات في آنٍ واحد: يسجّل ملفاً مهنياً، يطلب الارتباط بشركة (أو
تدعوه هي)، وبعد تفعيل الارتباط يفتح ملف كل زبون **قراءةً** (فواتير، مصاريف، قائمة دخل، ميزانية،
منحنى أشهر) ويجهّز فتراته الضريبية ويرفع طلبات توضيح ويصدّر حزمة المراجعة. الوصول كله محكوم
بـ`AccountantEngagement` النشط: هو ما يخلق عضوية `legal_accountant` ويحدّد نطاق صلاحياتها،
وسحبه يحذفها. والوحدة مرخَّصة لكل شركة على حدة، وغير المرخّصة لا ترى المسار أصلاً.

وفوق ذلك **طبقة مكتب (practice)**: سجلّ زبائن المكتب نفسه — بمن فيهم زبونٌ **ليس شركةً على
المنصة** يُدخله المحاسب يدوياً — وبرامج المراجعة والمواعيد والمستندات وإعدادات المكتب.
الفارق الجوهري بين الطبقتين: **بيانات الطبقة الأولى تخصّ الشركة والمحاسب يقرؤها، وبيانات
طبقة المكتب تخصّ المحاسب نفسه وهو يكتبها.** ولذلك نطاق طبقة المكتب `accountant=` لا
`tenant=`، ولا جدول من جداولها يحمل مفتاحاً إلى `Tenant` إطلاقاً — فلا طريق منها إلى دفاتر
شركة، ولا إلى `post_journal` أو `record_stock_movement`. الرابط الوحيد بين الطبقتين حقلٌ
اختياري على `PracticeClient` يشير إلى `AccountantEngagement` **للمحاسب نفسه**، وهو مؤشّر
تنقّل لا قناة بيانات: فتح دفاتر الشركة يظلّ يمرّ بالارتباط النشط وحده.

## أهم الملفات

| الملف | الغرض | أسطر |
|---|---|---|
| `accountant_portal/services.py` | منطق الأعمال كله: الارتباطات، النطاق، المراجعة، الفترات، ملفات الزبون | 1368 |
| `accountant_portal/views.py` | كل الـviews (APIView يدوية لا ViewSets)، الحصص والحراسة | 1148 |
| `accountant_portal/practice.py` | خدمات طبقة المكتب: الزبائن والبرامج والمواعيد والمستندات والإعدادات و`practice_deadlines` | 661 |
| `accountant_portal/models.py` | الملف المهني، الارتباط، الإعدادات، مراجعة الفترة، طلب التوضيح، وجداول المكتب الخمسة | 523 |
| `accountant_portal/practice_views.py` | views طبقة المكتب — الحرّاس الثلاثة في `initial` واحدة، وكل فشل 404 | 273 |
| `accountant_portal/readiness.py` | 12 فحص جاهزية **مشتقّاً** للفترة الضريبية | 267 |
| `accountant_portal/permissions.py` | الصلاحيات المحرّمة + حجب المسارات التشغيلية | 82 |
| `accountant_portal/identity.py` | رموز تحقق البريد ورسائل الدعوة | 78 |
| `accountant_portal/guards.py` | حارس قفل الفترة المسجَّل في `core.hooks` | 52 |
| `accountant_portal/audit.py` | أكواد التدقيق المسموحة وكتابتها | 36 |

## الـModels

| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `AccountantProfile` | `professional_type`، `tax_registration_number` (فريد)، `verification_status` (unverified/pending_review/verified/rejected/barred)، `email_verified_at`، `barred_until` | `user` OneToOne؛ جدول `acct_portal_profiles` |
| `AccountantEngagement` | `status` (pending/active/suspended/revoked/declined/expired)، `initiated_by`، `invitation_token_hash` (SHA-256)، `invitation_expires_at`، `invitation_used_at`، `approved_scope_snapshot` (JSON) | `accountant` (PROTECT) + `tenant` (CASCADE)؛ `UniqueConstraint(accountant, tenant)` |
| `PortalSettings` | `require_reauth_for_sensitive`، `reauth_window_minutes`، `allow_grant_cost_view`، `invitation_expiry_days`، `max_active_engagements`، `lock_blocks_posting`، `default_grant_profile`، `filing_due_days`، `allow_accountant_reopen`، `export_formats` | `tenant` OneToOne |
| `TaxPeriodReview` | `period_from/to`، `status` (in_review/needs_company_action/ready/approved/submitted/locked)، `submission_reference`، `locked_at`، `reopen_count` | `tenant`، `vat_statement` OneToOne → `sales.VatStatement`؛ `UniqueConstraint(tenant, period_from, period_to)` |
| `ReviewQuery` | `entity_type`/`entity_id`، `severity` (blocker/warning/info)، `status` (open/answered/resolved/withdrawn)، `title`، `body`، `answer_body` | `tenant`، `engagement`، `period_review` (SET_NULL) |
| `PracticeClient` | `trade_name` (إلزامي)، بيانات الاتصال والعنوان، `sector`، `tax_number`، `status` (active/archived) | `accountant` (PROTECT)، `engagement` (SET_NULL — اختياري، ولمالكه وحده)؛ `UniqueConstraint(accountant, trade_name)`؛ **بلا `tenant`** |
| `PracticeProgram` | `service_type`، `frequency` (annual/monthly/once)، `team_note`، `due_date`، `status` (planned/in_progress/done) — و«متأخر» **مشتقّ من التاريخ لا حالة مخزَّنة** | `accountant`، `client` (CASCADE)؛ **بلا `tenant`** |
| `PracticeTask` | `title`، `due_at`، `kind` (appointment/deadline)، `status` (open/done) | `accountant`، `client` (اختياري)؛ **بلا `tenant`** |
| `PracticeDocument` | `name`، `url`، `uploaded_at` | `accountant`، `client`، `program` (اختياري)؛ **بلا `tenant`** |
| `PracticeSettings` | `default_program_due_days` (15)، `service_types` (JSON — أربعة أنواع عربية افتراضاً) | `profile` OneToOne → `AccountantProfile`؛ الصفّ كسول وغيابه = الافتراضات كاملةً |

## دوال الـservices العامة

```python
def get_portal_settings(tenant)   # إعدادات الشركة (get_or_create) — الغياب = الافتراضات
def require_reauth(*, request, tenant, user)  # إعادة كلمة المرور للفعل الحسّاس ضمن نافذة مخبّأة
def internal_membership(accountant, tenant)   # عضوية داخلية غير legal_accountant أو None
def default_engagement_scope(tenant, profile=None)  # نطاق الحزمة الافتراضية منقّىً من المحرّم
def validate_scope(tenant, scope)  # يرفض المحرّم والمجهول و inventory.cost.view إن مُنع
def sanitize_log_value(value, limit=200)  # يزيل CR/LF قبل أي كتابة في السجل
def request_company_engagement(*, accountant, tenant, note="")   # طلب المحاسب (pending)
def create_company_invitation(*, tenant, manager, accountant, scope, note="")  # → (engagement, token)
def accept_company_invitation(*, accountant, token)   # قبول الدعوة تحت select_for_update
def approve_accountant_request(*, engagement, manager, scope=None)  # موافقة الشركة وتفعيل
def suspend_engagement(*, engagement, actor, reason="")   # تعليق + سحب العضوية
def resume_engagement(*, engagement, actor)               # استئناف من اللقطة المحفوظة
def revoke_engagement(*, engagement, actor, reason="")    # إلغاء نهائي
def decline_engagement(*, engagement, actor, reason="")   # رفض طلب معلّق
def set_engagement_scope(*, engagement, actor, scope)     # تعديل نطاق ارتباط نشط
def active_engagement(*, user, tenant)                    # الارتباط النشط أو None
def create_review_query(*, tenant, user, data)   # طلب توضيح — يلزمه ارتباط نشط
def answer_review_query(*, query, user, body)
def close_review_query(*, query, user, outcome)  # resolved | withdrawn
def refresh_period_status(period)   # الحالة تُشتق من الموانع القائمة
def build_review_package(*, tenant, period_from, period_to)
def record_package_export(*, tenant, user, period_from, period_to, export_format, row_count)
def prepare_tax_period(*, tenant, user, period_from, period_to)  # مراجعة + كشف ض.ق.م
def period_readiness(period)   # يشغّل readiness.run_readiness_checks
def approve_tax_period(*, period, user, request)   # لا اعتماد مع موانع مفتوحة
def reopen_tax_period(*, period, user, reason)     # بسبب إلزامي، والمقفلة لا رجعة فيها
def submit_tax_period(*, period, user, request, reference, submitted_on=None)  # تسجيل ثم قفل
def client_invoice_rows(*, tenant, kind, date_from, date_to)
def client_expense_rows(*, tenant, date_from, date_to)
def client_financial_summary(*, tenant, date_from, date_to)
def client_statements(*, tenant, date_from, date_to)  # دخل للفترة + ميزانية تراكمية
def client_monthly_trend(*, tenant, months=6, today=None)
def practice_overview(*, accountant, today=None)   # لوحة المكتب لكل الزبائن
def portal_settings_payload(config)
def update_portal_settings(*, tenant, actor, data)  # لمدير الشركة وحده، مدقَّق
# EngagementConflict(code, detail, status_code=409) — استثناء الأخطاء الموحَّد، تحوّله الـviews
# إلى {"code","detail"} بحالته عبر `_conflict_response` في views.py.
```

وطبقة المكتب في `accountant_portal/practice.py` — كلها منطاقة بـ`accountant=` لا `tenant=`:

```python
# التوقيعات فقط — منسوخة حرفياً من accountant_portal/practice.py
def get_practice_settings(accountant)    # get_or_create كسول — الغياب = الافتراضات
def update_practice_settings(*, accountant, data)
def list_practice_clients(*, accountant, status=None, search=None)
def get_practice_client(*, accountant, client_id)   # صفّ محاسبٍ آخر ⇒ 404 «غير موجود»
def create_practice_client(*, accountant, data)     # trade_name إلزامي وفريد لكل محاسب
def update_practice_client(*, accountant, client_id, data)
def archive_practice_client(*, accountant, client_id)   # الحذف أرشفة دائماً
def restore_practice_client(*, accountant, client_id)
def list_practice_programs(*, accountant, client_id=None, status=None)
def create_practice_program(*, accountant, data, today=None)   # نوع الخدمة من PracticeSettings
def update_practice_program(*, accountant, program_id, data)
def delete_practice_program(*, accountant, program_id)
def list_practice_tasks(*, accountant, client_id=None, status=None)
def create_practice_task(*, accountant, data)
def update_practice_task(*, accountant, task_id, data)
def delete_practice_task(*, accountant, task_id)
def list_practice_documents(*, accountant, client_id=None, program_id=None)
def create_practice_document(*, accountant, data)
def delete_practice_document(*, accountant, document_id)
def practice_deadlines(*, accountant, today=None)   # برامج المكتب ومواعيده + مواعيد إقرارات الشركات المرتبطة
```

## أهم الـAPI endpoints

مركّبة تحت `api/accountant/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
| POST | `/api/accountant/signup/` | `AccountantSignupView` (AllowAny · `accountant_signup`) |
| POST | `/api/accountant/verify-email/` · `resend-verification/` | `VerifyEmailView` · `ResendVerificationView` (`accountant_verify`) |
| GET/PATCH | `/api/accountant/me/` | `AccountantMeView` |
| GET | `/api/accountant/workspace/companies/` | `WorkspaceCompaniesView` |
| GET | `/api/accountant/companies/lookup/?q=` | `CompanyLookupView` (`accountant_company_lookup`) |
| POST | `/api/accountant/engagements/request/` · `accept-invite/` | `RequestEngagementView` (`accountant_engagement_request`) · `AcceptInvitationView` |
| POST | `/api/accountant/engagements/{id}/withdraw/` · `resign/` | `WithdrawEngagementView` · `ResignEngagementView` |
| POST | `/api/accountant/company/engagements/invite/` | `CompanyInviteView` (`accountant_invite`) |
| POST | `/api/accountant/company/engagements/{id}/approve\|decline\|suspend\|resume\|revoke/` | `CompanyEngagementActionView` |
| PATCH | `/api/accountant/company/engagements/{id}/scope/` | `CompanyScopeView` |
| GET/PATCH | `/api/accountant/company/settings/` | `CompanyPortalSettingsView` |
| GET | `/api/accountant/practice/overview/` | `PracticeOverviewView` |
| GET/POST | `/api/accountant/practice/clients/` · GET/PATCH/DELETE `clients/{id}/` · POST `clients/{id}/restore/` | `practice_views.PracticeClient*` — الحذف **أرشفة** لا إزالة |
| GET/POST | `practice/programs/` · PATCH/DELETE `programs/{id}/` | `practice_views.PracticeProgram*` |
| GET/POST | `practice/tasks/` · PATCH/DELETE `tasks/{id}/` | `practice_views.PracticeTask*` |
| GET | `practice/documents/` · POST `documents/upload/` (multipart) · DELETE `documents/{id}/` | `practice_views.PracticeDocument*` — الرفع عبر `core.media_views.upload_media_file` المشتركة وبحصّة `media_upload` نفسها |
| GET/PATCH | `practice/settings/` | `practice_views.PracticeSettingsView` |
| GET | `practice/deadlines/` | `practice_views.PracticeDeadlinesView` — برامج المكتب ومواعيده **ومواعيد إقرارات الشركات المرتبطة** في قائمة واحدة |
| GET | `/api/accountant/client/documents\|statements\|trend\|summary/` | `ClientDocumentsView` … |
| POST/GET | `/api/accountant/tax/periods/prepare/` · `{id}/approve\|reopen\|mark-submitted/` · `{id}/readiness/` | `TaxPeriodPrepareView` · `TaxPeriodActionView` · `TaxPeriodReadinessView` |
| GET/POST | `/api/accountant/review/queries/` (+ `{id}/answer\|resolve\|withdraw/`) | `ReviewQueryListCreateView` · `ReviewQueryActionView` |
| POST/GET | `/api/accountant/review/export/` · `/api/accountant/activity/` | `ReviewPackageExportView` · `AccountantActivityView` |

**حصص الطلبات** (`core/settings.py` (`DEFAULT_THROTTLE_RATES`)): `accountant_signup` 5/hour · `accountant_verify`
10/hour · `accountant_invite` 20/hour · `accountant_engagement_request` 10/hour (عبر
`views.py` (`SuccessOnlyScopedThrottle`) — تُحسب على النجاح وحده) ·
`accountant_company_lookup` 60/hour (حصة مستقلة عمداً، `views.py` (`CompanyLookupView`)).

## كيف يُمنَح المحاسب وصولاً لشركة

1. **ملف مهني** شرط دائم؛ تحقق البريد اختياري خلف `ACCOUNTANT_REQUIRE_EMAIL_VERIFICATION` (افتراضه false — `core/settings.py`، و`services.py` (`_require_verified_profile`)).
2. **ارتباط** بطلب المحاسب أو بدعوة الشركة (الرمز يُخزَّن مجزّأً SHA-256 فقط، `services.py`).
3. **التفعيل** حصراً بـ`services.py` (`_activate_locked`): ترخيص الوحدة، الحالة `pending`، الدعوة غير منتهية، المحاسب غير ممنوع، حدّ الارتباطات النشطة، ثم النطاق والتدقيق.
4. **العضوية**: `services.py` (`_replace_membership_scope`) ينشئ `UserCompanyMembership` بدور `legal_accountant` + `MemberPermission` لكل مفتاح مرئي غير محرّم؛ ومن له عضوية داخلية في الشركة نفسها لا يُمَسّ دورها ولا تخصيصاتها (`services.py` (`internal_membership`)).
5. **الفحص عند كل طلب**: `core/tenant_utils.py` (`EngagementInactive`) يُرفع لعضو `legal_accountant` بلا ارتباط نشط أو بلا ترخيص وحدة — هذا مصدر الحقيقة لا اللقطة.
6. **السحب**: التعليق/الإلغاء يحذف عضوية `legal_accountant` وحدها (`services.py` (`suspend_engagement`)).

## الاعتماديات

**يعتمد على:** `core` — `permission_keys`/`require_perm`/`user_tenant_role` (`services.py`، `views.py`)، `guard_module_surface`/`require_module`/`module_enabled` (`views.py`)، `log_activity` (`services.py`)، `core.hooks.register_tax_period_guard` (`guards.py`) · `tenants` — نماذج `MemberPermission`/`UserCompanyMembership` مباشرةً (`services.py`) · `accounting` — `AccountingAuditLog` (`audit.py`) و`JournalLine` قراءةً (`services.py`) · `sales` — `build_vat_statement` (`services.py`) و`SalesInvoice` قراءةً (`services.py`).
طبقة المكتب لا تعتمد على `accounting` ولا `inventory` إطلاقاً — `practice.py` لا يستورد منهما شيئاً.

**يعتمد عليه:** `core/tenant_utils.py` (فحص الارتباط النشط)، `core/permissions.py` و`core/access.py` و`core/permissions_api.py` (تنقية الصلاحيات المحرّمة)، `core/platform_admin_api.py`، و`hr/views.py` + `hr/payroll_api.py` + `hr/auth_api.py`.

## قواعد لا يجوز كسرها

- **العزل بين الشركات هو المخاطرة الأولى هنا**: المحاسب الواحد يحمل عضويات في عدة شركات، فأي مسار يقرأ بيانات دون `get_tenant` + `require_module` + `require_perm` (`views.py` (`TenantScopedView`)) هو تسريب بين شركات. كل استعلام في `services.py` يبدأ بـ`tenant=` — لا استثناء، ولا فلترة بمعرّف قادم من العميل وحده.
- **ربط كيان بطلب توضيح يُتحقق من ملكيته للشركة** (`services.py` (`create_review_query`)) وبنفس رسالة «غير موجود» لمنع التعداد (T2/IDOR).
- **البحث عن شركة بالمطابقة التامة فقط ولا يعيد قائمة** (`views.py` (`CompanyLookupView`)) — منعاً لتعداد شركات المنصة (T8).
- **الصلاحيات المحرّمة** (`permissions.py` (`LEGAL_ACCOUNTANT_FORBIDDEN`)، منها `hr.*` و`admin.*` و`import.*`) لا تُمنح بأي طريق: `validate_scope` (`services.py`)، `default_engagement_scope` (`services.py`)، `_replace_membership_scope` (`services.py`)، وتصفية `core/access.py`.
- **`/api/inventory/` و`/api/hr/` و`/api/logistics/` محجوبة** عن المحاسب (`permissions.py` (`_RESTRICTED_ROUTE_PREFIXES`))، وكل كتابة له خارج `/api/accountant/` مرفوضة (`core/permissions.py`).
- **حارس انتهاء الاشتراك يُستدعى يدوياً هنا**: مسارات الوحدة تعلن `permission_classes = [IsAuthenticated]` فلا يمرّ بها `TenantRolePermission` — ومعه يغيب منعُ الكتابة على شركةٍ انتهى اشتراكها. تُستدعى `core/permissions.py` (`require_active_subscription`) في `views.py` (`TenantScopedView.tenant_for`) و(`CompanyPortalSettingsView._tenant`). أي مسار جديد يحلّ شركةً بنفسه دونهما يفتح الباب الخلفي من جديد.
- **رمز الدعوة لا يُخزَّن خاماً** — sha256 فقط، ويُستهلك مرة واحدة تحت `select_for_update` (`services.py` (`accept_company_invitation`)).
- **دفاتر الزبون قراءة فقط** — لا مسار كتابة على مستندات الشركة في هذه الوحدة (`views.py` — `ClientDocumentsView` وأخواتها). وطبقة المكتب **لا تنقض هذه القاعدة**: ما يكتبه المحاسب هناك بياناتُ مكتبه هو (زبائنه وبرامجه ومواعيده ومستنداته)، لا بيانات الشركة — ولا جدول من جداول المكتب يحمل مفتاحاً إلى `Tenant`.
- **نطاق طبقة المكتب `accountant=` لا `tenant=`** — كل استعلام في `practice.py` يبدأ به، وصفُّ مكتبٍ آخر يعود **404 «غير موجود»** لا 403 (`practice.py`): ردُّ «ممنوع» يُقرّ بوجود ما يخفيه. ومسارات المكتب هوياتية فلا تحتاج `X-Tenant-Id`.
- **`settings.ACCOUNTANT_PRACTICE_ENABLED` مُطفأً يجعل كل مسار مكتب 404** — الحارس في `initial` واحدة قبل المصادقة وقبل وجود `AccountantProfile` (`practice_views.py`).
- **الفترة المقدَّمة مقفلة نهائياً**: `submit_tax_period` يضع `locked`، وإعادة الفتح ترفض `submitted`/`locked` (`services.py` (`reopen_tax_period`))، وحارس `guards.py` (`tax_period_lock_guard`) يمنع أي ترحيل بتاريخ داخلها ما لم تُطفئ الشركة `lock_blocks_posting`.
- **لا اعتماد مع موانع مفتوحة** (`services.py` (`approve_tax_period`))، ولا تقديم قبل الاعتماد (`services.py` (`submit_tax_period`))، وسبب إعادة الفتح إلزامي (`services.py` (`reopen_tax_period`)).
- **الأفعال الحسّاسة تلزمها إعادة كلمة المرور**: الاعتماد والتقديم وتعديل النطاق (`services.py` (`require_reauth`)، `views.py`)، ولا تُسجَّل كلمة المرور ولا طولها (`services.py`).
- **كل فعل حسّاس يكتب صفّ تدقيق بكود من `AUDIT_ACTION_CODES`** والمجهول يرفع `ValueError` (`audit.py` (`AUDIT_ACTION_CODES`))؛ وكل قيمة مستخدم تدخل السجل تُنقّى من CR/LF (`services.py` (`sanitize_log_value`)).
- **إعدادات البوابة لمدير الشركة وحده** (`admin.settings.manage`، `views.py`) — والمحاسب لا يملك هذا المفتاح أبداً لأنه محرّم عليه.
- **الشركة غير المرخّصة لا ترى المسار** — `guard_module_surface` في `views.py` (`PortalAPIView`).

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `tests/test_m1_foundation.py` (408) | النماذج والقيود الفريدة، مصفوفة الوصول والدور، رفض المفاتيح المحرّمة عبر API، أكواد التدقيق |
| `tests/test_m2_engagements.py` (656) | دورة حياة الارتباط كاملةً، النطاق الافتراضي والحزم الثلاث، حصة طلب الارتباط |
| `tests/test_m2_identity.py` (224) | التسجيل وتحقق البريد (وسلوكه حين لا يُشترط)، حصة التسجيل |
| `tests/test_m3_workspace.py` (154) | لوحة شركات المحاسب: `accessible`، الفترة الأخيرة، عدّاد الموانع |
| `tests/test_m4_review.py` (225) | طلبات التوضيح وأثرها على حالة الفترة، حزمة التصدير والتدقيق |
| `tests/test_m5_periods.py` (505) | دورة الفترة الضريبية، فحوص الجاهزية، حارس القفل، تفاعل الفترة مع الطلبات |
| `tests/test_m7_hardening.py` (188) | حجب الأسرار عن السجلات، حقن الأسطر، منع التعديل عبر مسار بديل، تدقيق كل فعل حسّاس |
| `tests/test_office_client_files.py` (263) | ملف الزبون قراءةً فقط: فواتير، مصاريف، ملخص، بيانات مالية، لوحة المكتب |
| `tests/test_practice_clients.py` (435) | طبقة المكتب على مستوى الخدمات: عزل المحاسبين، رفض ربط ارتباط ليس للمحاسب، الأرشفة بدل الحذف، كسل `PracticeSettings` |
| `tests/test_practice_api.py` (394) | الطبقة نفسها فوق HTTP: الدورة الكاملة لكل كيان، و**404** لمحاسبٍ على صفّ غيره في كل فعل، والرفع مموّهاً، والعَلَم مُطفأً ⇒ 404 على كل المسارات |
| `tests/test_mysql_m2_concurrency.py` (72) · `test_mysql_audit.py` (41) | استهلاك الدعوة مرة واحدة تحت تزامن حقيقي، وثبات صفوف التدقيق (MySQL) |
| `tests/test_demo_workspace.py` (134) · `test_platform_modules.py` (42) | فتح واجهة المحاسب وتبديل ترخيص الوحدة من لوحة المنصة (سوبر أدمن) |
