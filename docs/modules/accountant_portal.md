# accountant_portal — بوابة المحاسب القانوني الخارجي: ارتباط بعدة شركات، مراجعة مالية، وفترات ضريبية

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

بوابة لمحاسب/مكتب خارجي يخدم عدة شركات في آنٍ واحد: يسجّل ملفاً مهنياً، يطلب الارتباط بشركة (أو
تدعوه هي)، وبعد تفعيل الارتباط يفتح ملف كل زبون **قراءةً** (فواتير، مصاريف، قائمة دخل، ميزانية،
منحنى أشهر) ويجهّز فتراته الضريبية ويرفع طلبات توضيح ويصدّر حزمة المراجعة. الوصول كله محكوم
بـ`AccountantEngagement` النشط: هو ما يخلق عضوية `legal_accountant` ويحدّد نطاق صلاحياتها،
وسحبه يحذفها. والوحدة مرخَّصة لكل شركة على حدة، وغير المرخّصة لا ترى المسار أصلاً.

## أهم الملفات

| الملف | الغرض | أسطر |
|---|---|---|
| `accountant_portal/services.py` | منطق الأعمال كله: الارتباطات، النطاق، المراجعة، الفترات، ملفات الزبون | 1368 |
| `accountant_portal/views.py` | كل الـviews (APIView يدوية لا ViewSets)، الحصص والحراسة | 1148 |
| `accountant_portal/models.py` | الملف المهني، الارتباط، الإعدادات، مراجعة الفترة، طلب التوضيح | 347 |
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
# إلى {"code","detail"} بحالته عبر _conflict_response (views.py:127-128).
```

## أهم الـAPI endpoints

مركّبة تحت `api/accountant/` (`core/urls.py:87`).

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
| GET | `/api/accountant/client/documents\|statements\|trend\|summary/` | `ClientDocumentsView` … |
| POST/GET | `/api/accountant/tax/periods/prepare/` · `{id}/approve\|reopen\|mark-submitted/` · `{id}/readiness/` | `TaxPeriodPrepareView` · `TaxPeriodActionView` · `TaxPeriodReadinessView` |
| GET/POST | `/api/accountant/review/queries/` (+ `{id}/answer\|resolve\|withdraw/`) | `ReviewQueryListCreateView` · `ReviewQueryActionView` |
| POST/GET | `/api/accountant/review/export/` · `/api/accountant/activity/` | `ReviewPackageExportView` · `AccountantActivityView` |

**حصص الطلبات** (`core/settings.py:381-389`): `accountant_signup` 5/hour · `accountant_verify`
10/hour · `accountant_invite` 20/hour · `accountant_engagement_request` 10/hour (عبر
`SuccessOnlyScopedThrottle` — تُحسب على النجاح وحده، `views.py:105-120`) ·
`accountant_company_lookup` 60/hour (حصة مستقلة عمداً، `views.py:456-459`).

## كيف يُمنَح المحاسب وصولاً لشركة

1. **ملف مهني** شرط دائم؛ تحقق البريد اختياري خلف `ACCOUNTANT_REQUIRE_EMAIL_VERIFICATION` (افتراضه false — `core/settings.py:398`، `services.py:83-90`).
2. **ارتباط** بطلب المحاسب أو بدعوة الشركة (الرمز يُخزَّن مجزّأً SHA-256 فقط، `services.py:296`).
3. **التفعيل** حصراً بـ`_activate_locked` (`services.py:306-333`): ترخيص الوحدة، الحالة `pending`، الدعوة غير منتهية، المحاسب غير ممنوع، حدّ الارتباطات النشطة، ثم النطاق والتدقيق.
4. **العضوية**: `_replace_membership_scope` (`services.py:207-231`) ينشئ `UserCompanyMembership` بدور `legal_accountant` + `MemberPermission` لكل مفتاح مرئي غير محرّم؛ ومن له عضوية داخلية في الشركة نفسها لا يُمَسّ دورها ولا تخصيصاتها (`services.py:101-116`).
5. **الفحص عند كل طلب**: `core/tenant_utils.py:144-163` يرفع `EngagementInactive` لعضو `legal_accountant` بلا ارتباط نشط أو بلا ترخيص وحدة — هذا مصدر الحقيقة لا اللقطة.
6. **السحب**: التعليق/الإلغاء يحذف عضوية `legal_accountant` وحدها (`services.py:119-128`).

## الاعتماديات

**يعتمد على:** `core` — `permission_keys`/`require_perm`/`user_tenant_role` (`services.py:21`، `views.py:78`)، `guard_module_surface`/`require_module`/`module_enabled` (`views.py:79`)، `log_activity` (`services.py:22`)، `core.hooks.register_tax_period_guard` (`guards.py:50`) · `tenants` — نماذج `MemberPermission`/`UserCompanyMembership` مباشرةً (`services.py:24`) · `accounting` — `AccountingAuditLog` (`audit.py:27`) و`JournalLine` قراءةً (`services.py:867`، `905`، `1036`) · `sales` — `build_vat_statement` (`services.py:707`) و`SalesInvoice` قراءةً (`services.py:602`، `827`).

**يعتمد عليه:** `core/tenant_utils.py:144-163` (فحص الارتباط النشط)، `core/permissions.py:26` و`core/access.py:379` و`core/permissions_api.py:122,220,248` (تنقية الصلاحيات المحرّمة)، `core/platform_admin_api.py`، و`hr/views.py:22` + `hr/payroll_api.py:20` + `hr/auth_api.py:26`.

## قواعد لا يجوز كسرها

- **العزل بين الشركات هو المخاطرة الأولى هنا**: المحاسب الواحد يحمل عضويات في عدة شركات، فأي مسار يقرأ بيانات دون `get_tenant` + `require_module` + `require_perm` (`TenantScopedView.tenant_for`، `views.py:701-711`) هو تسريب بين شركات. كل استعلام في `services.py` يبدأ بـ`tenant=` — لا استثناء، ولا فلترة بمعرّف قادم من العميل وحده.
- **ربط كيان بطلب توضيح يُتحقق من ملكيته للشركة** (`services.py:452-465`) وبنفس رسالة «غير موجود» لمنع التعداد (T2/IDOR).
- **البحث عن شركة بالمطابقة التامة فقط ولا يعيد قائمة** (`views.py:447-474`) — منعاً لتعداد شركات المنصة (T8).
- **الصلاحيات المحرّمة** (`permissions.py:12-33`، منها `hr.*` و`admin.*` و`import.*`) لا تُمنح بأي طريق: `validate_scope` (`services.py:189`)، `default_engagement_scope` (`services.py:180`)، `_replace_membership_scope` (`services.py:228`)، وتصفية `core/access.py:378-381`.
- **`/api/inventory/` و`/api/hr/` و`/api/logistics/` محجوبة** عن المحاسب (`permissions.py:47-57`)، وكل كتابة له خارج `/api/accountant/` مرفوضة (`core/permissions.py:74-81`).
- **رمز الدعوة لا يُخزَّن خاماً** — sha256 فقط، ويُستهلك مرة واحدة تحت `select_for_update` (`services.py:337-349`).
- **ملف الزبون قراءة فقط** — لا مسار كتابة على مستنداته في هذه الوحدة (`views.py:801-802`).
- **الفترة المقدَّمة مقفلة نهائياً**: `submit_tax_period` يضع `locked`، وإعادة الفتح ترفض `submitted`/`locked` (`services.py:760-761`)، وحارس `tax_period_lock_guard` يمنع أي ترحيل بتاريخ داخلها ما لم تُطفئ الشركة `lock_blocks_posting` (`guards.py:32-46`).
- **لا اعتماد مع موانع مفتوحة** (`services.py:745-746`)، ولا تقديم قبل الاعتماد (`services.py:787-788`)، وسبب إعادة الفتح إلزامي (`services.py:765-766`).
- **الأفعال الحسّاسة تلزمها إعادة كلمة المرور**: الاعتماد والتقديم وتعديل النطاق (`services.py:743`، `789`، `views.py:675`)، ولا تُسجَّل كلمة المرور ولا طولها (`services.py:58`).
- **كل فعل حسّاس يكتب صفّ تدقيق بكود من `AUDIT_ACTION_CODES`** والمجهول يرفع `ValueError` (`audit.py:24-25`)؛ وكل قيمة مستخدم تدخل السجل تُنقّى من CR/LF (`services.py:234-236`).
- **إعدادات البوابة لمدير الشركة وحده** (`admin.settings.manage`، `views.py:1126`) — والمحاسب لا يملك هذا المفتاح أبداً لأنه محرّم عليه.
- **الشركة غير المرخّصة لا ترى المسار** — `guard_module_surface` في `PortalAPIView` (`views.py:100-102`).

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
| `tests/test_mysql_m2_concurrency.py` (72) · `test_mysql_audit.py` (41) | استهلاك الدعوة مرة واحدة تحت تزامن حقيقي، وثبات صفوف التدقيق (MySQL) |
| `tests/test_demo_workspace.py` (134) · `test_platform_modules.py` (42) | فتح واجهة المحاسب وتبديل ترخيص الوحدة من لوحة المنصة (سوبر أدمن) |
