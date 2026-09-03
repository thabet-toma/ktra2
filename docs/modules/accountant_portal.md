# accountant_portal — بوابة المحاسب القانوني الخارجي: ارتباط بعدة شركات، مراجعة مالية، وفترات ضريبية

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

بوابة لمحاسب/مكتب خارجي يخدم عدة شركات في آنٍ واحد: يسجّل ملفاً مهنياً، يطلب الارتباط بشركة (أو
تدعوه هي)، وبعد تفعيل الارتباط يفتح ملف كل زبون **قراءةً** (فواتير، مصاريف، قائمة دخل، ميزانية،
منحنى أشهر) ويجهّز فتراته الضريبية ويرفع طلبات توضيح ويصدّر حزمة المراجعة. الوصول كله محكوم
بـ`AccountantEngagement` النشط: هو ما يخلق عضوية `legal_accountant` ويحدّد نطاق صلاحياتها،
وسحبه يحذفها. والوحدة مرخَّصة لكل شركة على حدة، وغير المرخّصة لا ترى المسار أصلاً.

**ISSUE #55:** كل محاسبٍ كان مسجَّلاً قبلها صار مديرَ مكتبٍ (`accounting_firm`) عبر أمر
ترحيلٍ مرّةً واحدة (تحت)، و`PracticeClient` القديمة بقيت كما هي بلا `engagement`/`managed_tenant`،
وكل `AccountantEngagement` نشط صار زبون مكتبٍ من نوع `engaged`. الباب المنفصل الذي كان
يسجّل محاسباً من صفحة الدخول (`/accountant/signup` في `frontend_v2`) أُغلق — الزر والمسار
والاستدعاء حُذفوا من الواجهة، لكن نقطة `/api/accountant/signup/` بقيت حيّةً على الخادم.

**ISSUE #60:** أُغلقت نقطة الخادم أيضاً — `AccountantSignupView` والمسار
`/api/accountant/signup/` حُذفا (كانا يقبلان POST بلا مصادقة، فالباب كان مغلقاً
بالضغط ومفتوحاً بـ`curl`، عيبٌ من فئة #51)، ومعها حصّة `accountant_signup` ودالّة
`identity.py` (`send_existing_account_email`) التي لم تكن تخدم غير التسجيل. من
يريد مكتب محاسبة يُنشئ شركةً بقالب `accounting_firm` — لا باب تسجيل خارجي منفصل.
المحاسبون القائمون و`AccountantEngagement` النشطة لم يُمسّا؛ لا هجرة قاعدة بيانات.

وفوق ذلك **طبقة مكتب (practice)**: سجلّ زبائن المكتب نفسه — بمن فيهم زبونٌ **ليس شركةً على
المنصة** يُدخله المحاسب يدوياً — وبرامج المراجعة والمواعيد والمستندات وإعدادات المكتب.
الفارق الجوهري بين الطبقتين: **بيانات الطبقة الأولى تخصّ الشركة والمحاسب يقرؤها، وبيانات
طبقة المكتب تخصّ المحاسب نفسه وهو يكتبها.** ولذلك نطاق طبقة المكتب `accountant=` لا
`tenant=`، ولا جدول من جداولها يحمل مفتاحاً إلى `Tenant` — فلا طريق منها إلى دفاتر
شركة، ولا إلى `post_journal` أو `record_stock_movement` — باستثناء واحد موثَّق (ISSUE #52):
`PracticeClient.managed_tenant`، رابطٌ لدفتر مُدار يملكه مكتب هذا المحاسب نفسه
(`Tenant.managed_by`)، والعزل عنده لا يعتمد على غياب الحقل بل على
`TenantViewSet.get_queryset` (`tenants/views.py`) — دفتر مكتبٍ آخر «غير موجود» له
مهما أشار إليه `PracticeClient`. الرابط الثاني على `PracticeClient` حقلٌ اختياري يشير
إلى `AccountantEngagement` **للمحاسب نفسه**، وهو مؤشّر تنقّل لا قناة بيانات: فتح دفاتر
الشركة يظلّ يمرّ بالارتباط النشط وحده. **النوع مشتقّ من الحقلين معاً** — خاصية
`PracticeClient.client_type` (`managed` / `engaged` / `hybrid` / `unlinked`) — لا حقل
حالة ثالث يمكن أن يناقضهما (مرآته في الواجهة: `frontend_v2/utils/officeClientType.ts`).

**ISSUE #57:** مسارات `tax/periods/...` (تحت) لا تفترض دفتر المكتب — تعمل على أي
دفترٍ يصله المستخدم بـ`X-Tenant-Id`، فيصلح لدفتر عميلٍ مُدار أو مربوطٍ بالضبط
كما يصلح لدفتر شركة عادية؛ لا تغيير في `guards.py`/`readiness.py`/`services.py`.
الواجهة تستدعيها من **بطاقة العميل** نفسها (`frontend_v2/components/accountant/office/OfficeClientTaxPeriods.tsx`،
مُضافة كتبويب في `OfficeExternalClientPage.tsx`) لا من بوابةٍ منفصلة — أيّ دفترٍ
يُستعمل يحسمه `frontend_v2/utils/clientBookAccess.ts` (المُدار يفوز عند التعارض).

**ISSUE #86 — «مكانٌ واحد»:** `PracticeClient` **مجمَّدٌ للكتابة**. زبون المكتب صار
`partners.Partner` نفسه داخل شركة مكتب المحاسب (`office_tenant_id`) — لا سجلّ
منفصل، وفاتورة أتعابه فاتورة بيع عادية بمحاسبتها الكاملة (#46/#11). `Partner`
اكتسب `sector`/`mobile` (الحقلان البنيويّان الوحيدان اللذان كان `PracticeClient`
يحملهما ولا يحملهما) و`engagement`/`managed_tenant` (مراجع نصّية — لا استيراد
فعلي من `partners` إلى `accountant_portal`) مع `client_type` مشتقّاً بنفس منطق
ISSUE #52 (القرار 9 في #46). `PracticeProgram`/`PracticeTask`/`PracticeDocument`
بقيت نماذجها كما هي، مضافاً إليها `partner` (الحقل الحيّ) بجانب `client` (مجمَّدٌ
للكتابة — صفٌّ تاريخي يبقى مقروءاً في مسار السقوط تحت). أمر
`migrate_practice_clients_to_partners` (idempotent، `--dry-run`، لا حذف) ينقل
زبائن كل محاسبٍ له مكتب (نتيجة ISSUE #55) إلى أطراف شركته، بعلامتَي `CustomerNote`
منفصلتَين: `MIGRATION_MARKER_TARGET_TYPE` (`'practice_client_migration'`، تمنع
التكرار وتحفظ نصّاً تاريخياً — جهة الاتصال والحالة والملاحظات) و
`PROFILE_NOTE_TARGET_TYPE` (`'practice_client_profile'`، JSON حيٌّ يقرؤه
ويكتبه `practice.py` كأي زبونٍ عادي). موعد حذف `PracticeClient` نفسه موثَّقٌ في
`docs/decisions/practice_client_retirement.md` — لا حذف قبل دورة ضريبية كاملة
من نجاح الأمر على الإنتاج.

**مراجعة 2 (نفس اليوم) — قراءةٌ انتقالية بلا فقد شاشة:** المراجعة الأولى جعلت
محاسباً لم يُرحَّل بعد (أو تعثّر ترحيله، أو أضاف له `migrate_accountant_offices`
زبوناً جديداً بعد ترحيله) يفتح «زبائني» خاويةً رغم بياناتٍ سليمة في القاعدة —
خرقٌ لقيدٍ منصوص: «محاسبٌ تعثّر ترحيله يبقى على سطحه القديم». `list_office_partners`
الآن **تدمج** أطراف شركة المكتب مع كل `PracticeClient` لم يُرحَّل بعد
(`_unmigrated_practice_clients` — علامة `MIGRATION_MARKER_TARGET_TYPE` وحدها
تقرّر، لا «هل القائمة فارغة»)، بمعرّفٍ **سالبٍ** عمداً (`_legacy_client_payload`)
لا يتقاطع أبداً مع معرّف `Partner` الموجب — فكتابةٌ عليه (`get_office_partner`
الصارمة، ومسارات PATCH كلها) تُخفق بأمان 404 بدل أن تصيب صفّاً خطأً أو تكتب على
`PracticeClient`. `get_office_client_view` وحدها تفهم المعرّف السالب للقراءة
(`GET .../clients/{id}/`)؛ الكتابة تبقى صارمةً موجبة الطرف حصراً. `PracticeProgram`/
`Task`/`Document` تعرض `partner_id`/`partner_name` بنفس القاعدة (`_client_ref`) —
صفٌّ قديمٌ لم يُرحَّل يعرض اسم زبونه من `client.trade_name` لا فراغاً، وتصفيته
بمعرّفه السالب تعمل (`_filter_by_client_ref`). عناوين `<int:client_id>` تحوّلت
`<str:client_id>` في `urls.py` (محوّل `int` القياسي يرفض إشارة السالب).

**مراجعة 2 أيضاً — الأرشفة وجهة الاتصال عادتا:** المراجعة الأولى حذفت أرشفة
زبون المكتب و`contact_first`/`contact_last`/`notes` بلا إذنٍ من التذكرة.
الأرشفة صارت `PracticeClientArchive` (جدولٌ صغير `(accountant, partner)` — حالة
**طبقة المكتب** لا الطرف، فـ`Partner` نفسه يبقى فاعلاً في كل مكانٍ آخر يستعمله).
جهة الاتصال والملاحظات تعيش في `CustomerNote` بـ`target_type=PROFILE_NOTE_TARGET_TYPE`
(JSON محدَّثٌ في مكانه، لا حقل بنيويّ جديد على `Partner`) — `_load_profile_notes`/
`_save_profile_note`، باستعلامٍ مجمَّعٍ واحد لكل قائمة لا استعلامٍ لكل صفّ.
`PracticeClientListView`/`DetailView` صارا يقرآن/يكتبان `Partner` (عبر
`list_office_partners`/`get_office_client_view`/`create_office_partner`/
`update_office_partner`)، والربط بارتباطٍ على المنصة أو بدفترٍ مُدار في
`PracticeClientLinkView` وحدها (`PATCH .../clients/{id}/link/`) — فعلٌ حسّاس
مستقلّ عن تعديل بيانات الاتصال. `PracticeClientDetailView.delete`/
`PracticeClientRestoreView` عادتا (`archive_office_partner`/`restore_office_partner`).

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
| `accountant_portal/management/commands/migrate_accountant_offices.py` | ISSUE #55 — ترحيل idempotent: مكتب `accounting_firm` لكل محاسبٍ بلا مكتب، وربط كل `AccountantEngagement` نشط بزبون `PracticeClient` («مربوطٌ بإذنه») | 158 |
| `accountant_portal/management/commands/migrate_practice_clients_to_partners.py` | ISSUE #86 — ترحيل idempotent ثانٍ (بعد #55): كل `PracticeClient` تابعٍ لمحاسبٍ له مكتب ينتقل إلى `partners.Partner` داخل شركته، وتُربط برامجه/مواعيده/مستنداته بالطرف الجديد؛ لا حذف، لا كتابة على `PracticeClient` | 190 |

## الـModels

| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `AccountantProfile` | `professional_type`، `tax_registration_number` (فريد)، `verification_status` (unverified/pending_review/verified/rejected/barred)، `email_verified_at`، `barred_until` | `user` OneToOne؛ جدول `acct_portal_profiles` |
| `AccountantEngagement` | `status` (pending/active/suspended/revoked/declined/expired)، `initiated_by`، `invitation_token_hash` (SHA-256)، `invitation_expires_at`، `invitation_used_at`، `approved_scope_snapshot` (JSON) | `accountant` (PROTECT) + `tenant` (CASCADE)؛ `UniqueConstraint(accountant, tenant)` |
| `PortalSettings` | `require_reauth_for_sensitive`، `reauth_window_minutes`، `allow_grant_cost_view`، `invitation_expiry_days`، `max_active_engagements`، `lock_blocks_posting`، `default_grant_profile`، `filing_due_days`، `allow_accountant_reopen`، `export_formats` | `tenant` OneToOne |
| `TaxPeriodReview` | `period_from/to`، `status` (in_review/needs_company_action/ready/approved/submitted/locked)، `submission_reference`، `locked_at`، `reopen_count` | `tenant`، `vat_statement` OneToOne → `sales.VatStatement`؛ `UniqueConstraint(tenant, period_from, period_to)` |
| `ReviewQuery` | `entity_type`/`entity_id`، `severity` (blocker/warning/info)، `status` (open/answered/resolved/withdrawn)، `title`، `body`، `answer_body` | `tenant`، `engagement`، `period_review` (SET_NULL) |
| `PracticeClient` **(مجمَّدٌ للكتابة — ISSUE #86)** | `trade_name` (إلزامي)، بيانات الاتصال والعنوان، `sector`، `tax_number`، `status` (active/archived)، `client_type` (property مشتقّة: managed/engaged/hybrid/unlinked) | `accountant` (PROTECT)، `engagement` (SET_NULL)، `managed_tenant` (SET_NULL)؛ `UniqueConstraint(accountant, trade_name)` — **قراءةٌ فقط** عبر مسار السقوط (`_unmigrated_practice_clients`) لكل صفٍّ بلا علامة نقل، وبلا كتابةٍ جديدة أبداً؛ انظر `docs/decisions/practice_client_retirement.md` |
| `PracticeClientArchive` **(جديد — مراجعة 2 من ISSUE #86)** | `archived_at` | `accountant` (CASCADE)، `partner` (CASCADE)؛ `UniqueConstraint(accountant, partner)` — وجود الصفّ = مؤرشف؛ حالة **طبقة المكتب** لا الطرف |
| `PracticeProgram` | `service_type`، `frequency` (annual/monthly/once)، `team_note`، `due_date`، `status` (planned/in_progress/done) — و«متأخر» **مشتقّ من التاريخ لا حالة مخزَّنة** | `accountant`، `partner` (CASCADE، اختياري — الحقل الحيّ)، `client` (CASCADE، اختياري، مجمَّد)؛ **بلا `tenant`** |
| `PracticeTask` | `title`، `due_at`، `kind` (appointment/deadline)، `status` (open/done) | `accountant`، `partner` (SET_NULL، اختياري — الحقل الحيّ)، `client` (SET_NULL، اختياري، مجمَّد)؛ **بلا `tenant`** |
| `PracticeDocument` | `name`، `url`، `uploaded_at` | `accountant`، `partner` (CASCADE، اختياري — الحقل الحيّ)، `client` (CASCADE، اختياري، مجمَّد)، `program` (اختياري)؛ **بلا `tenant`** |
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
def office_tenant_id(accountant)   # شركة مكتب هذا المحاسب أو None — لم يُرحَّل بعد (ISSUE #55)
def list_office_partners(*, accountant, search=None, status=None)   # ISSUE #86 — أطراف مُرحَّلة + PracticeClient لم يُرحَّل بعد (سقوط قراءة)
def get_office_partner(*, accountant, partner_id)   # صارمة: Partner فقط، معرّفٌ موجبٌ فقط — تُستعمل في كل كتابة
def get_office_client_view(*, accountant, client_id)   # عرضٌ للقراءة وحدها — يفهم المعرّف السالب (زبونٌ لم يُرحَّل)
def create_office_partner(*, accountant, data)     # trade_name إلزامي؛ 409 بلا شركة مكتب؛ يعيد حمولة جاهزة
def update_office_partner(*, accountant, partner_id, data)   # صارمة كـget_office_partner
def link_office_partner(*, accountant, partner_id, data)   # engagement_id/managed_tenant_id وحدهما — فعلٌ حسّاس مستقلّ
def archive_office_partner(*, accountant, partner_id)   # PracticeClientArchive — حالة طبقة المكتب لا الطرف
def restore_office_partner(*, accountant, partner_id)
def list_practice_programs(*, accountant, partner_id=None, status=None)
def create_practice_program(*, accountant, data, today=None)   # نوع الخدمة من PracticeSettings
def update_practice_program(*, accountant, program_id, data)
def delete_practice_program(*, accountant, program_id)
def list_practice_tasks(*, accountant, partner_id=None, status=None)
def create_practice_task(*, accountant, data)
def update_practice_task(*, accountant, task_id, data)
def delete_practice_task(*, accountant, task_id)
def list_practice_documents(*, accountant, partner_id=None, program_id=None)
def create_practice_document(*, accountant, data)
def delete_practice_document(*, accountant, document_id)
def practice_deadlines(*, accountant, today=None)   # برامج المكتب ومواعيده + مواعيد إقرارات الشركات المرتبطة
def practice_dashboard(*, accountant, today=None)   # ISSUE #58 — لوحة المكتب لصاحب المكتب: عملاء + استحقاقات + أتعاب غير محصّلة، بعدد استعلامات ثابت
def staff_practice_dashboard(*, staff, today=None)  # ISSUE #58 (القرار 7) — لوحة موظفٍ بلا ملف محاسب: عملاؤه المُسنَدون فقط عبر عضويته على دفترهم المُدار؛ استحقاقات وأتعاب فارغتان دوماً
```

## أهم الـAPI endpoints

مركّبة تحت `api/accountant/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
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
| GET/POST | `/api/accountant/practice/clients/` · GET/PATCH/DELETE `clients/{id}/` · POST `clients/{id}/restore/` · PATCH `clients/{id}/link/` | `practice_views.PracticeClient*` — ISSUE #86: الزبون `partners.Partner` داخل شركة المكتب؛ الحذف **أرشفة** (`PracticeClientArchive`) لا إزالة؛ `link/` وحدها تعدّل `engagement_id`/`managed_tenant_id` (فعلٌ حسّاس)؛ `GET clients/{id}/` يفهم معرّفاً سالباً (زبونٌ لم يُرحَّل بعد، قراءةٌ فقط)؛ المسار `<str:client_id>` لا `<int:>` لأجل ذلك |
| GET/POST | `practice/programs/` · PATCH/DELETE `programs/{id}/` | `practice_views.PracticeProgram*` |
| GET/POST | `practice/tasks/` · PATCH/DELETE `tasks/{id}/` | `practice_views.PracticeTask*` |
| GET | `practice/documents/` · POST `documents/upload/` (multipart) · DELETE `documents/{id}/` | `practice_views.PracticeDocument*` — الرفع عبر `core.media_views.upload_media_file` المشتركة وبحصّة `media_upload` نفسها |
| GET/PATCH | `practice/settings/` | `practice_views.PracticeSettingsView` |
| GET | `practice/deadlines/` | `practice_views.PracticeDeadlinesView` — برامج المكتب ومواعيده **ومواعيد إقرارات الشركات المرتبطة** في قائمة واحدة |
| GET | `practice/dashboard/` | `practice_views.PracticeDashboardView` (ISSUE #58) — **البوابة الوحيدة المخفَّفة** في سطح المكتب: صاحب ملفٍ مهني يرى `practice_dashboard` (عملاؤه، `practice_deadlines`، والأتعاب غير المحصّلة من دفتره هو وحده)؛ مستخدمٌ بلا `AccountantProfile` (موظف مكتب، القرار 7) يرى `staff_practice_dashboard` — عملاء الدفاتر المُدارة التي هو عضوٌ فيها (`UserCompanyMembership` على `PracticeClient.managed_tenant`، لا حقل إسنادٍ ثالث) فقط، فارغة إن لم يُسنَد له شيء — 200 لا 404. كل مسار آخر في `practice_views.py` يبقى خلف `PracticeView` (يتطلّب ملفاً مهنياً) بلا تخفيف |
| GET | `/api/accountant/client/documents\|statements\|trend\|summary/` | `ClientDocumentsView` … |
| POST/GET | `/api/accountant/tax/periods/prepare/` · `{id}/approve\|reopen\|mark-submitted/` · `{id}/readiness/` | `TaxPeriodPrepareView` · `TaxPeriodActionView` · `TaxPeriodReadinessView` |
| GET/POST | `/api/accountant/review/queries/` (+ `{id}/answer\|resolve\|withdraw/`) | `ReviewQueryListCreateView` · `ReviewQueryActionView` |
| POST/GET | `/api/accountant/review/export/` · `/api/accountant/activity/` | `ReviewPackageExportView` · `AccountantActivityView` |

**حصص الطلبات** (`core/settings.py` (`DEFAULT_THROTTLE_RATES`)): `accountant_verify`
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

**يعتمد على:** `core` — `permission_keys`/`require_perm`/`user_tenant_role` (`services.py`، `views.py`)، `guard_module_surface`/`require_module`/`module_enabled` (`views.py`)، `log_activity` (`services.py`)، `core.hooks.register_tax_period_guard` (`guards.py`) · `tenants` — نماذج `MemberPermission`/`UserCompanyMembership` مباشرةً (`services.py`) · `accounting` — `AccountingAuditLog` (`audit.py`)، `JournalLine` قراءةً، و`vat_period_totals` (issue #79: مصدر أرقام الضريبة الوحيد في `client_financial_summary`، `services.py`) · `sales` — `build_vat_statement` (`services.py`) و`SalesInvoice` قراءةً (`services.py`) و`SalesInvoice` قراءةً في `practice.py` (`_unpaid_fee_invoices`، ISSUE #58) · `partners` — **models** فقط (`Partner`، `CustomerNote` — ISSUE #86، `practice.py`): زبون المكتب صار طرفاً، فقراءته وكتابته تمرّان بنموذج `Partner` مباشرةً؛ لا استيراد لـ`partners.serializers`/`views` (محرَّمةٌ عبر `.importlinter`).
طبقة المكتب لا تعتمد على `accounting` ولا `inventory` إطلاقاً — `practice.py` لا يستورد منهما شيئاً؛ اعتمادها الوحيد خارج `core`/`tenants` هو `partners.models` (زبونها، ISSUE #86) و`sales.models.SalesInvoice` (الأتعاب غير المحصّلة، ISSUE #58).

**يعتمد عليه:** `core/tenant_utils.py` (فحص الارتباط النشط)، `core/permissions.py` و`core/access.py` و`core/permissions_api.py` (تنقية الصلاحيات المحرّمة)، `core/platform_admin_api.py`، و`hr/views.py` + `hr/payroll_api.py` + `hr/auth_api.py`.

## قواعد لا يجوز كسرها

- **العزل بين الشركات هو المخاطرة الأولى هنا**: المحاسب الواحد يحمل عضويات في عدة شركات، فأي مسار يقرأ بيانات دون `get_tenant` + `require_module` + `require_perm` (`views.py` (`TenantScopedView`)) هو تسريب بين شركات. كل استعلام في `services.py` يبدأ بـ`tenant=` — لا استثناء، ولا فلترة بمعرّف قادم من العميل وحده.
- **ربط كيان بطلب توضيح يُتحقق من ملكيته للشركة** (`services.py` (`create_review_query`)) وبنفس رسالة «غير موجود» لمنع التعداد (T2/IDOR).
- **البحث عن شركة بالمطابقة التامة فقط ولا يعيد قائمة** (`views.py` (`CompanyLookupView`)) — منعاً لتعداد شركات المنصة (T8).
- **الصلاحيات المحرّمة** (`permissions.py` (`LEGAL_ACCOUNTANT_FORBIDDEN`)، منها `hr.*` و`admin.*` و`import.*`) لا تُمنح بأي طريق: `validate_scope` (`services.py`)، `default_engagement_scope` (`services.py`)، `_replace_membership_scope` (`services.py`)، وتصفية `core/access.py`.
- **`/api/inventory/` و`/api/hr/` و`/api/logistics/` محجوبة** عن المحاسب (`permissions.py` (`_RESTRICTED_ROUTE_PREFIXES`))، وكل كتابة له خارج `/api/accountant/` مرفوضة (`core/permissions.py`).
- **حارس انتهاء الاشتراك يُستدعى يدوياً هنا**: مسارات الوحدة تعلن `permission_classes = [IsAuthenticated]` فلا يمرّ بها `TenantRolePermission` — ومعه يغيب منعُ الكتابة على شركةٍ انتهى اشتراكها. تُستدعى `core/permissions.py` (`require_active_subscription`) في `views.py` (`TenantScopedView.tenant_for`) و(`CompanyPortalSettingsView._tenant`). أي مسار جديد يحلّ شركةً بنفسه دونهما يفتح الباب الخلفي من جديد.
- **رمز الدعوة لا يُخزَّن خاماً** — sha256 فقط، ويُستهلك مرة واحدة تحت `select_for_update` (`services.py` (`accept_company_invitation`)).
- **دفاتر الزبون قراءة فقط** — لا مسار كتابة على مستندات الشركة في هذه الوحدة (`views.py` — `ClientDocumentsView` وأخواتها). وطبقة المكتب **لا تنقض هذه القاعدة**: ما يكتبه المحاسب هناك بياناتُ مكتبه هو (زبائنه وبرامجه ومواعيده ومستنداته)، لا بيانات الشركة. `PracticeProgram`/`PracticeTask`/`PracticeDocument`/`PracticeSettings` بلا `tenant`؛ زبون المكتب وحده (`Partner`، ISSUE #86) يحمله عمداً — هو **داخل شركة المكتب نفسها**، لا شركة زبونٍ حقيقي.
- **نطاق طبقة المكتب `accountant=` لا `tenant=`** — كل استعلام على `PracticeProgram`/`PracticeTask`/`PracticeDocument`/`PracticeSettings` في `practice.py` يبدأ به، وصفُّ مكتبٍ آخر يعود **404 «غير موجود»** لا 403 (`practice.py`): ردُّ «ممنوع» يُقرّ بوجود ما يخفيه. ومسارات المكتب هوياتية فلا تحتاج `X-Tenant-Id`. **الزبون وحده استثناء (ISSUE #86)**: `Partner` يحمل `tenant=` (شركة المكتب)، والعزل عنده `tenant=office_tenant_id(accountant)` بدل `accountant=` مباشرةً — نفس فلسفة «غير موجود» لا «ممنوع»، ونفس غياب `X-Tenant-Id` من الطلب (الخادم يحسم شركة المكتب من هوية المحاسب لا من ترويسة العميل).
- **القراءة الانتقالية تسقط، والكتابة لا** (مراجعة 2 من ISSUE #86): زبونٌ لم يُرحَّل بعد (`_unmigrated_practice_clients`) يظهر في `list_office_partners`/`get_office_client_view` بمعرّفٍ **سالبٍ**، فكل مسار كتابة (`get_office_partner`، `update_office_partner`، `link_office_partner`، إنشاء برنامج/موعد/مستند بـ`partner_id`) يرفضه 404 بأمان — معرّف Partner لا يكون سالباً أبداً. لا سطرٌ يكتب على `PracticeClient` من أي دالةٍ في هذا المسار. المسارات `<str:client_id>` لا `<int:>` في `urls.py` لهذا السبب وحده.
- **`settings.ACCOUNTANT_PRACTICE_ENABLED` مُطفأً يجعل كل مسار مكتب 404** — الحارس في `initial` واحدة قبل المصادقة وقبل وجود `AccountantProfile` (`practice_views.py`).
- **البوابة الهوياتية (`AccountantProfile` إلزامي) مُخفَّفة على `practice/dashboard/` وحده** (ISSUE #58، القرار 7): `PracticeDashboardView` لا يرث `PracticeView`، بل يعيد تطبيق فحص العَلَم وحده ثم يفرّق داخل `get()` — موظفٌ بلا ملف مهني يرى `staff_practice_dashboard` (`practice.py`) بدل 404. الإسناد بعضوية `UserCompanyMembership` على `PracticeClient.managed_tenant` نفسه — **لا حقل تعيين ثالث** — وزبونٌ بلا دفتر مُدار لا سبيل لإسناده هكذا فيبقى لصاحب المكتب وحده. أي مسار جديد تحت `practice_views.py` يجب أن يرث `PracticeView` كسائر السطح لا هذا الاستثناء.
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
| `tests/test_m2_identity.py` (224) | تحقق البريد (الرمز أحاديّ الاستعمال)، بوابة `me/` تحت `ACCOUNTANT_REQUIRE_EMAIL_VERIFICATION`، وISSUE #60 — `/api/accountant/signup/` يردّ 404 |
| `tests/test_m3_workspace.py` (154) | لوحة شركات المحاسب: `accessible`، الفترة الأخيرة، عدّاد الموانع |
| `tests/test_m4_review.py` (225) | طلبات التوضيح وأثرها على حالة الفترة، حزمة التصدير والتدقيق |
| `tests/test_m5_periods.py` (505) | دورة الفترة الضريبية، فحوص الجاهزية، حارس القفل، تفاعل الفترة مع الطلبات |
| `tests/test_m7_hardening.py` (188) | حجب الأسرار عن السجلات، حقن الأسطر، منع التعديل عبر مسار بديل، تدقيق كل فعل حسّاس |
| `tests/test_office_client_files.py` (263) | ملف الزبون قراءةً فقط: فواتير، مصاريف، ملخص، بيانات مالية، لوحة المكتب |
| `tests/test_practice_clients.py` | طبقة المكتب على مستوى الخدمات: زبون المكتب (`Partner`) عزلاً بـ`tenant=office_tenant_id`، 409 بلا شركة مكتب، رفض ربط ارتباط ليس للمحاسب، كسل `PracticeSettings`؛ `PracticeClientArchiveTest` (الأرشفة/الاسترجاع بلا مسّ الطرف)، `PracticeClientProfileFieldsTest` (جهة الاتصال والملاحظات رحلة ذهاب وعود)، `LegacyClientFallbackTest` (مراجعة 2: محاسبٌ غير مُرحَّل يرى زبائنه القدامى بمعرّفٍ سالب، الكتابة عليهم تُرفض، ولا كتابة على `PracticeClient` أبداً) |
| `tests/test_practice_api.py` | الطبقة نفسها فوق HTTP: الدورة الكاملة لكل كيان (زبون=`Partner`، برامج/مواعيد/مستندات بـ`partner_id`)، أرشفة/استرجاع، جهة الاتصال عبر الشبكة، و**404** لمحاسبٍ على صفّ غيره في كل فعل، مسار `clients/{id}/link/` المنفصل، والرفع مموّهاً، والعَلَم مُطفأً ⇒ 404 على كل المسارات؛ `PracticeLegacyClientFallbackApiTest` (الزبون القديم يظهر بمعرّفٍ سالب فوق HTTP ويُفتح للقراءة وحدها، ولا يظهر لمكتبٍ آخر) |
| `tests/test_migrate_practice_clients_to_partners.py` | ISSUE #86 — أمر النقل: زبونٌ عاديٌّ ومربوطٌ يُنقلان إلى `Partner` داخل شركة المكتب بعلامتَي `CustomerNote` (تاريخية + ملفّ تعريف حيّ)، البرامج/المواعيد/المستندات تُربط بالطرف الجديد بلا مسّ `client`، محاسبٌ بلا مكتب يُتخطّى لا يُكسَر، الحقول الأضيق تُقصّ لا تسقط، `--dry-run` لا يكتب، وإعادة التشغيل idempotent (تُكمل ربط صفوفٍ أضيفت لاحقاً)، وجهة الاتصال/الملاحظات تُقرأ حيّةً بعد النقل لا نصّاً تاريخياً وحده |
| `tests/test_mysql_m2_concurrency.py` (72) · `test_mysql_audit.py` (41) | استهلاك الدعوة مرة واحدة تحت تزامن حقيقي، وثبات صفوف التدقيق (MySQL) |
| `tests/test_demo_workspace.py` (134) · `test_platform_modules.py` (42) | فتح واجهة المحاسب وتبديل ترخيص الوحدة من لوحة المنصة (سوبر أدمن) |
| `tests/test_client_book_tax_periods.py` | ISSUE #57 — تجهيز/جاهزية/قفل الفترة عبر `X-Tenant-Id` على دفتر عميل مُدار؛ القفل لا يمسّ دفتر المكتب ولا دفتر عميلٍ آخر |
| `tests/test_practice_dashboard.py` | ISSUE #58 — لوحة المكتب: عدد الاستعلامات ثابتٌ من 3 إلى 60 عميلاً (`CaptureQueriesContext`)، عزل مكتبٍ عن آخر، الأتعاب من دفتر المكتب لا دفتر عميله المُدار؛ والقرار 7 — موظفٌ مُسنَد يرى عملاءه المُسنَدين فقط (لا 404، لا الكل)، وموظفٌ غير مُسنَد يرى صفراً، وموظف مكتبٍ آخر لا يرى شيئاً منه |
| `tests/test_migrate_accountant_offices.py` | ISSUE #55 — أمر الترحيل عبر `call_command` وأثره فوق HTTP: مكتب `accounting_firm` يُنشأ لمحاسبٍ بلا مكتب ولا يُكرَّر لمن له مكتب فعلاً، زبونٌ يدويٌّ قديم يبقى بلا `engagement`/`managed_tenant`، ارتباطٌ نشط يصير زبون `engaged` (أو يُربط بزبونٍ يدويٍّ قائمٍ بنفس الاسم لا يُكرَّر)، ارتباطٌ غير نشط لا يصير زبوناً، وإعادة التشغيل idempotent |
