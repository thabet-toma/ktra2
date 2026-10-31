# accounting_office — موديول مكتب المحاسبة: زبون المكتب وبطاقته وجهاته وإعداداته وأدواره وخدماته وباقاته

> مبني على قراءة الكود مباشرةً بتاريخ 2026-10-31. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

مكتبُ المحاسبة كمنتجٍ مستقلّ على المنصّة (المواصفة #270، وتذكرة الأساس #271).
المكتب **شركةٌ** على المنصّة بقالب `accounting_office`، وتحت كل شركةٍ سجلٌّ خاصّ
بها: زبائنها (منشآت بملفٍ ضريبيٍّ واحد)، وبطاقاتها الضريبية، وجهاتُ الاتصال،
وسجلُّ إعداداتها، **وموظّفوها وأدوارهم ومسؤولُ كل زبون** (#272)، **وكتالوجُ خدماته وباقاتُه الجاهزة، وخدماتُ كل زبونٍ بدوريتها المؤرَّخة** (#273).

هذا الملفّ يوثّق **الطبقات الثلاث الأولى**: الزبون وبطاقته وجهاته وإعداداته،
**والأدوار والصلاحيات والموظف المسؤول**، **والخدمات والباقات وخدمات الزبون**.
الأتعابُ والالتزاماتُ والمواعيدُ والأوراقُ والتذكيراتُ تأتي في تذاكرها، والملفّ
يُحدَّث معها.

**مفتاح الترخيص:** `accounting_office` في `core/modules.py` (`MODULES`) — تسميتُه
«مكتب المحاسبة»، خططُه `Pro` و`Enterprise`، و`legacy_flag: None` (لا عَلَم قديم
يُيسِّره). كلُّ نقطةٍ تحت `/api/accounting-office/` تمرّ بـ`require_module` فتردّ
**404 لا 403** لشركةٍ غير مرخّصة.

**القالب:** `accounting_office` في `tenants/company_templates.py`
(`COMPANY_TEMPLATES`) — **بجانب** `accounting_firm` لا بديلاً عنه. يستعير شجرة
حسابات القديم وأنواعَ مستنداته بالإشارة (`ACCOUNTING_FIRM_COA`،
`ACCOUNTING_FIRM_DOCUMENT_TYPES`) وقناعَ مساراته نفسه
(`_GOODS_MOVEMENT_HIDDEN_PATHS`)، ولا يزرع خدمات (`services: None`).
و`tenants/services.py` (`create_company`) تُرخّص الوحدة عند إنشاء الشركة بهذا
القالب — نقطةُ الزرع واحدة، و`switch_company_template` لا يمنح تراخيص.

## أهم الملفات

| الملف | الغرض |
|---|---|
| `accounting_office/models.py` | النماذج الاثنا عشر، واختياراتُ البطاقة لكل نظامٍ ضريبيّ، و`is_tenant_member` (قاعدةُ العضويّة الواحدة)، وحارسُ عضويّة الموظف المسؤول في `save()` |
| `accounting_office/settings_registry.py` | سجلّ الإعدادات: المفتاح والنوع والمستويات والافتراضيِّ ومُتحقِّقُ القيمة |
| `accounting_office/services.py` | **المحلّل** ودوالّ الكتابة، ودورةُ حياة الزبون، والبطاقة، والجهات، ومستلِمو التذكيرات، و**`visible_clients`/`visible_contacts`/`can_see_amounts`/`mask_amounts`**، وكتالوجُ الخدمات وباقاتُها، وخدماتُ الزبون ودورياتُها المؤرَّخة، و**`suggest_frequency`** (#273) |
| `accounting_office/serializers.py` | شكل الـAPI وحده — لا قراءة إعداداتٍ فيه |
| `accounting_office/views.py` | كلُّ نقطةٍ خلف بوابة الترخيص، والعزل في كل استعلام، وحراسةُ كل كتابةٍ بمفتاحها، ونقاطُ الخدمات والباقات وخدمات الزبون (#273) |
| `accounting_office/apps.py` | `ready` تُسجّل حارسَ سجلّ نشاط «زبون المكتب» في `core.activity` (`register_document_history_guard`) — فتاريخُ زبونٍ لا تراه محجوبٌ 404 |
| `accounting_office/urls.py` | `SimpleRouter` (لا `DefaultRouter`: جذرُه فهرسٌ غير محروس) |
| `frontend_v2/services/accountingOfficeApi.ts` | عميل الواجهة فوق `restApi.ts` |
| `frontend_v2/utils/accountingOffice.ts` | الدوالّ الخالصة: تخصيصُ بطاقة الزبون، وحالةُ المخصَّص، وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه، وما يخفيه حجم «شخص واحد»، وقناعُ المبلغ المخفيّ («—»)، وأدوارُ قسم المكتب (بلا جدول تسميات). والشاشة تحفظ الحالة في العنوان عبر `useSearchParams` من react-router — لا `pushState`/`popstate` يدوياً، وأولُ الشهر ومنتقي الخدمات المتاحة وتسميةُ الدورية من اختيارات الخادم وملخّصُ الباقة (#273) |
| `frontend_v2/components/accounting-office/` | شاشات: القائمة (وتركّب ملفّ الزبون)، والإعدادات (وفيه قسم «الموظفون والأدوار»)، وخطوة أول تشغيل، و`OfficeUi.tsx` عناصرُ عرضٍ محليّةٌ على الوضع الداكن، وتبويبُ «الخدمات» ومجموعةُ «الخدمات والباقات» (#273) |

## الـModels

| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `OfficeClient` | `name`, `tax_file_number` (اختياري), `status` (`active`/`ended`), `ended_on`, `notes`, `responsible` (#272) | `tenant` FK. `responsible` FK إلى `auth.User` — `null=True`، `on_delete=SET_NULL`، `related_name="office_clients_responsible"`، ويجب أن يكون عضواً في شركة الزبون (حارسٌ في الخدمة والنموذج). **لا `Partner` ولا شركة على المنصّة.** قيدُ `CheckConstraint` يربط الحالة بتاريخها |
| `TaxCard` | `entity_type` (فرد/تضامن/مساهمة/غير ربحية), `vat_classification` (مشتغل مرخّص/معفى/غير مسجّل فلسطينيّاً · עוסק מורשה/עוסק פטור/מלכ"ר إسرائيلياً), `annual_sales` (Decimal، تُتحقَّق في الخدمة), `has_employees`, `employees_count`, `is_self_employed` | `OneToOne` مع `OfficeClient`، تُنشأ معه. **يوم الراحة وطريقة التقديم ليسا هنا** — إعدادان |
| `Contact` | `name`, `phone`, `language` (`ar`/`he`) | `tenant` FK. الشخص يملكه المكتب لا الزبون |
| `ClientContact` | `is_primary`, `primary_client_key` (عمود مُولَّد) | `(client, contact)` فريد. عمودٌ مُولَّد + فرادةٌ غير مشروطة = **جهة رئيسية واحدة على الأكثر** فعلياً في MySQL |
| `ClientReminderRecipient` | `reminder_type` (`documents`/`deadline`/`balance`/`appointment`) | `(client, reminder_type)` فريد ← `ClientContact`. غيابُ الصفّ = الرئيسية |
| `OfficeSettingValue` | `key`, `value` (JSON) | `(tenant, key)` فريد — قيمةُ المكتب |
| `ClientSettingOverride` | `key`, `value` (JSON) | `(tenant, client, key)` فريد — تخصيصُ الزبون |
| `OfficeService` | `code` (`SlugField`), `name`, `is_active`, `is_builtin`, `position` | `tenant` FK. **كتالوجُ المكتب**: فرادةٌ غير مشروطة على `(tenant, code)`، والخمسةُ الافتراضية أكوادُها ثابتة (`DEFAULT_SERVICES`) لأنّ الاقتراحَ يقرؤها، وتُزرع بـ`ensure_default_services` لا بهجرة بيانات. **لا حذفَ لخدمةٍ استُعملت** — `ClientService.service` على `PROTECT` والتعطيلُ هو الطريق |
| `ServicePackage` | `name`, `suggested_price` (`Decimal(14, 2)`, `null=True`) | `tenant` FK، و`services` M2M إلى `OfficeService`. **مبلغٌ يمرّ بالقناع**: `suggested_price` في `AMOUNT_KEYS`، وكتابتُه بلا `office.amounts.view` ⇒ 403. والحذفُ مباحٌ للباقة وحدها: قالبٌ لا تاريخَ زبونٍ فيه |
| `ClientService` | `starts_on`, `ends_on` (nullable = الإيقاف), `responsible_from`, `created_at` | `tenant` FK، و`client` FK، و`service` FK. **لا حذف**: الإيقافُ يكتب `ends_on` ويُبقي الصفَّ في التاريخ. ولا فترةَ متداخلةً لنفس `(زبون، خدمة)` — `overlapping_client_service` ترفضها في الخدمة، و`status_on(day)` وحدها تقول «نشطة أم موقوفة». و`responsible_from` يُخزَّن أولَ الشهر فقط: لا توليدَ فتراتٍ هنا (#274/#275) |
| `ClientServiceFrequency` | `frequency` (`monthly`/`bimonthly`/`quarterly`/`annual`/`on_demand`), `effective_from`, `suggested`, `created_by` | `client_service` FK، فرادةٌ على `(client_service, effective_from)`. **الدوريةُ بتاريخ سريان**: تغييرُها **يضيف صفّاً** ولا يعدّل ما قبله، والدوريةُ في يومٍ ما = الصفُّ ذو أكبر `effective_from <= اليوم` (`frequency_on`) |
| `TaxThreshold` | `tax_system`, `kind` (`vat_monthly_reporting`/`vat_exempt_dealer`), `year`, `amount`, `source_url` | **بلا `tenant` عمداً**: بياناتُ منصّةٍ مؤرَّخة واحدةٌ لكل المكاتب، فرادةٌ على `(tax_system, kind, year)`، وتُزرع بهجرة بياناتٍ من البحث. و`amount` **ليس مبلغَ زبون** فلا يُقنَّع — مُعفى في `test_amounts_guard.py` بسببٍ مكتوب |

## دوال الـservices العامة

```python
# ── الرؤية والمبالغ: مصدران وحيدان (#272) ──
visible_clients(tenant, user)                                 # الزبائن الذين يراهم هذا العضو — وحدها
visible_contacts(tenant, user)                                # جهاتُه: المربوطة بزبونٍ يراه أو غيرُ المربوطة
can_see_amounts(tenant, user)                                 # «يرى المبالغ»
mask_amounts(row, keys=AMOUNT_KEYS)                           # نسخةٌ بمفاتيح المبالغ None
user_display_name(user)                                       # اسمُ الموظف كما يُعرض ويُسجَّل
TAX_CARD_AMOUNT_KEYS / AMOUNT_KEYS                            # ثابتُ مفاتيح المبالغ
is_tenant_member(tenant_id, user_id)                          # في `models.py`: قاعدةُ العضويّة الواحدة
# ── المحلّل والإعدادات ──
resolve_setting(tenant, key, client=None, item=None)          # القيمة الفعلية وحدها
resolve_setting_with_source(tenant, key, client=None, item=None)  # (القيمة, المصدر)
resolve_setting_for_clients(tenant, key, clients)             # القائمة: استعلامان لا استعلامان لكل زبون
set_office_setting(tenant, key, value)                        # يتحقّق ثم يكتب
reset_office_setting(tenant, key)                             # «ارجع للافتراضي» = حذف (ويُرفض لمن لا افتراضي له)
set_client_setting(client, key, value)                        # تخصيصُ زبون
reset_client_setting(client, key)                             # «ارجع لإعداد المكتب»
clients_customized_for(tenant, key, *, user)                  # `user` مطلوب؛ تمرّ بـ`visible_clients`، و`user=None` صراحةً = داخليّ بلا طلب
clients_customized_payload(tenant, key, *, user)
first_run_status(tenant) / client_settings_payload(client)
office_settings_payload(tenant, *, user)                      # عدّادُ المخصِّصين على ما يراه العضو
office_setting_row(tenant, key, *, counts=None, user)
setting_value_label(definition, value) / tax_system_label(value)   # مصدر التسميات الوحيد
create_office_client(..., actor=, responsible=)               # المسؤول = المُنشئ افتراضاً إن كان عضواً (سوبر أدمن/دعم ⇒ بلا مسؤول)
update_office_client(...)                                     # الإنشاء مرفوضٌ قبل اكتمال أول تشغيل
assign_office_client(client, *, user, actor=, request=)       # يُقفل الصفّ ويُسجّل (من ← إلى)
end_office_client(..., actor=, request=) / reactivate_office_client(..., actor=, request=)
tax_card_payload(client, *, user)                             # user إلزامي؛ None الصريح وحده بلا قناع
update_tax_card(client, **fields)                             # المبيعات السنوية تُتحقَّق هنا
link_client_contact(...) / unlink_client_contact(...) / set_primary_client_contact(...)
delete_contact(contact)                                       # يُرفض إن كانت مربوطةً بزبون
set_reminder_recipient(...) / resolve_reminder_recipient(client, reminder_type) / reminder_recipients_payload(client)
# ── الخدمات والباقات وخدمات الزبون (#273) ──
ensure_default_services(tenant)                               # idempotent: الخمسةُ الافتراضية
services_catalog_payload(tenant) / office_service_row(service)
service_by_code(tenant, code) / create_office_service(tenant, *, name, position=None)
update_office_service(service, *, name=None, is_active=None, position=None)
packages_payload(tenant, *, user) / package_payload(package, *, user)
create_service_package(tenant, *, name, suggested_price=None, service_ids=None)
update_service_package(package, *, name=None, suggested_price=_UNSET, service_ids=None)
delete_service_package(package)                               # الباقةُ وحدها تُحذف
frequency_on(client_service, day, *, rows=None)               # القاعدةُ الوحيدة
frequency_label(value) / frequency_choices()
client_services_payload(client, *, user, today=None) / client_service_row(...)
add_client_service(*, client, service, starts_on=None, responsible_from=None, frequency=None, actor=None, today=None)
change_client_service_frequency(client_service, *, frequency, effective_from, actor=None)
stop_client_service(client_service, *, ends_on)
apply_package(client, package, *, actor=None, today=None)     # نسخٌ لا ربط
overlapping_client_service(client, service, starts_on)         # قاعدةُ التداخل الوحيدة
service_or_raise(tenant, pk) / package_or_raise(tenant, pk)    # حلُّ الكائن ورسالتُه واحدة
suggest_frequency(client, service_code, on_date=None)         # (frequency | None, reason)
suggestion_payload(client, service, *, on_date=None)
```

## أهم الـAPI endpoints

كلّها تحت `/api/accounting-office/`، وكلّها مصادَقةٌ بعضوية الشركة. بلا `AllowAny`.
**القراءةُ لكلّ عضو، والكتابةُ بمفاتيحها** (#272): كلُّ نقطة كتابةٍ تتطلّب
`office.clients.write` (`require_perm`)، وكتابةُ `settings/<key>/` و`services/` و`packages/` تتطلّب
`office.settings.manage`، و`assign/` تتطلّب `office.clients.assign`.

| Method | المسار | الـview |
|---|---|---|
| `GET/POST` | `clients/` | `OfficeClientViewSet` (`list`, `create`) |
| `GET/PUT/PATCH` | `clients/<pk>/` | `OfficeClientViewSet` (`retrieve`, `update`, `partial_update`) |
| `POST` | `clients/<pk>/end/` · `clients/<pk>/reactivate/` | `OfficeClientViewSet` (`end`, `reactivate`) |
| `POST` | `clients/<pk>/assign/` | `OfficeClientViewSet` (`assign`) — `{"user": <id>}` تحويلُ المسؤول، ويُسجَّل في `ActivityLog` |
| `GET/PATCH` | `clients/<pk>/tax-card/` | `OfficeClientViewSet` (`tax_card`) |
| `GET/POST` | `clients/<pk>/contacts/` | `OfficeClientViewSet` (`contacts`) |
| `DELETE` | `clients/<pk>/contacts/<contact_id>/` | `OfficeClientViewSet` (`unlink_contact`) |
| `POST` | `clients/<pk>/contacts/<contact_id>/primary/` | `OfficeClientViewSet` (`promote_contact`) |
| `GET/POST` | `clients/<pk>/reminders/` | `OfficeClientViewSet` (`reminders`) |
| `GET` | `clients/<pk>/settings/` | `OfficeClientViewSet` (`client_settings`) |
| `PUT/DELETE` | `clients/<pk>/settings/<key>/` | `OfficeClientViewSet` (`setting`) |
| `GET/POST` | `contacts/` | `OfficeContactViewSet` |
| `GET/PUT/PATCH/DELETE` | `contacts/<pk>/` | `OfficeContactViewSet` |
| `GET` | `settings/` | `OfficeSettingsViewSet` (`list`) |
| `PUT/DELETE` | `settings/<key>/` | `OfficeSettingsViewSet` (`setting`) |
| `GET` | `settings/<key>/clients/` | `OfficeSettingsViewSet` (`customized_clients`) |
| `GET/POST` | `services/` | `OfficeServiceViewSet` (`list`, `create`) — الكتالوجُ يُزرع عند أول قراءة |
| `GET/PUT/PATCH` | `services/<pk>/` | `OfficeServiceViewSet` (`retrieve`, `update`, `partial_update`) — **لا `DELETE`** (405) |
| `GET/POST` | `packages/` | `OfficePackageViewSet` (`list`, `create`) |
| `GET/PUT/PATCH/DELETE` | `packages/<pk>/` | `OfficePackageViewSet` — الحذفُ مباحٌ للباقة وحدها |
| `GET/POST` | `clients/<pk>/services/` | `OfficeClientViewSet` (`client_services`) — القائمةُ بالتاريخ والدورية الحالية وتاريخ الدوريات، والإضافة |
| `GET` | `clients/<pk>/services/suggest/?service=<code>&on=<date>` | `OfficeClientViewSet` (`client_service_suggest`) — الاقتراحُ وسببُه |
| `POST` | `clients/<pk>/services/<client_service_id>/frequency/` | `OfficeClientViewSet` (`client_service_frequency`) |
| `POST` | `clients/<pk>/services/<client_service_id>/stop/` | `OfficeClientViewSet` (`client_service_stop`) |
| `POST` | `clients/<pk>/apply-package/` | `OfficeClientViewSet` (`apply_package`) — يُرجع ما أُضيف وما تُخطّي |

**لا `DELETE` للزبون**: `destroy` ترفع `MethodNotAllowed` (405)، و«منتهٍ» حالةٌ
تُكتب بقيمتها الحقيقية لا صفٌّ يُطوى.

## الأدوار والصلاحيات (#272)

الأربعة على **الكتالوج القائم** (`core/access.py`) لا على محرّكٍ موازياً:
الترتيب `ROLE_DEFAULTS` ← تجاوز الدور للشركة (`RolePermission`) ← تجاوز العضو
(`MemberPermission`) — يحسبه `user_permissions` وحده.

| الدور في المكتب | الدور في الكتالوج | افتراضيّه |
|---|---|---|
| مالك | `manager` | `"*"` — كل شيء، **ولا يُقفل بتجاوز**. لا تغييرَ في سلوكه |
| مدير مكتب | `office_manager` (جديد) | `_VIEW_ONLY` + مفاتيح المكتب الخمسة. يختفي مع ترخيص وحدته (`ROLE_MODULES`) |
| محاسب | `accountant` | دوره القائم + `office.clients.write` وحده من مفاتيح المكتب |
| قارئ | `viewer` | `_VIEW_ONLY` — قراءةٌ بلا أيّ مفتاح كتابة. يُعرض في شاشة أدوار المكتب حين `office_size = large` وحده |

مفاتيح المكتب في `PERMISSIONS` بمجموعةٍ جديدة «مكتب المحاسبة» و`"module":
"accounting_office"` (لا تظهر لشركةٍ بلا ترخيص الوحدة):

| المفتاح | معناه |
|---|---|
| `office.clients.write` | يضيف ويعدّل الزبائن وبطاقاتهم وجهاتهم وتخصيصاتهم |
| `office.clients.all` | «يرى زبائن غيره» — **افتراضيّاً مطفأ للمحاسب والقارئ**، ويُمنح تجاوزاً لعضوٍ بعينه |
| `office.amounts.view` | «يرى المبالغ» — بدونه كلُّ مبلغٍ في الردّ `null` وكتابتُه 403 |
| `office.clients.assign` | يسند الزبون ويحوّله لموظّفٍ آخر |
| `office.settings.manage` | إعدادات المكتب (كتابةً) |

**«المفتاحان لكل عضو» هما تجاوزا العضو القائمان** على `office.clients.all`
و`office.amounts.view` — لا جدولَ جديد، ولا نقطةَ API جديدة: الشاشةُ تكتب عبر
`/api/permissions/member/` وتغيّر الدور عبر `tenants/companies/<id>/members/change-role/`.
**و`change-role` (وإضافةُ العضو) يرفض 400 أيّ دورٍ ليس في `visible_role_labels(tenant)`**
— فدورُ مكتبٍ لشركةٍ بلا ترخيص وحدته لا يُسند، ولا عضويّةَ بمفاتيح غائبة.

**وحجم المكتب لا يغيّر الخادم:** `office_size = solo` يُخفي في الواجهة عمود
«المسؤول» وزرّ «حوّل» وقسم الأدوار — والصلاحياتُ هي الحكم على كل حال. وخطوةُ
أول تشغيلٍ لا تعرض خياراتٍ على مَن لا يملك `office.settings.manage`: تقول إن
مالك المكتب أو مديره يكمله.

## الخدمات والباقات وخدمات الزبون (#273)

**ثلاثةُ مستوياتٍ لا مستويان**: «الخدمة» صفٌّ في **كتالوج المكتب** (`OfficeService`)
يفعّله ويضيف عليه ولا يحذف ما استُعمل، و**الباقة** (`ServicePackage`) قالبٌ يضمّ
خدماتٍ وسعراً مقترحاً اختيارياً، و**خدمةُ الزبون** (`ClientService`) ما اشتراه
زبونٌ بعينه بتاريخِ بدءٍ وانتهاءٍ و«من أيّ فترةٍ المكتب مسؤول». والتطبيقُ **نسخٌ
لا ربط**: تعديلُ الباقة بعدها لا يمسّ زبوناً، وتعديلُ خدمات الزبون لا يمسّ الباقة.

**«التغييرُ يسري من تاريخٍ ولقدّام» قاعدةٌ لا خيار.** الدوريةُ لا تُعدَّل في
مكانها: `ClientServiceFrequency` صفٌّ لكل تغيير بتاريخ سريانه، و
`frequency_on(client_service, day)` وحدها تجيب «ما دوريتُها في يومٍ ما؟» (الصفُّ ذو
أكبر `effective_from <= day`). فمن غيّرها من نيسان لا يمسّ آذار، ويُقرأ تاريخُ
الدوريات كاملاً في التبويب. وتاريخٌ مسجَّلٌ سابقاً يُرفض (400) إن وقع، ويُستبدل
صفُّه وحده إن كان مستقبلياً بعد اليوم — خطأُ إدخالٍ لم يقع بعد.

**الحالةُ نسبةً إلى اليوم، والفتراتُ لا تتداخل.** `ClientService.status_on(day)`
وحدها تجيب «نشطة أم موقوفة»: موقوفةٌ ⇔ `ends_on is not None and ends_on < day` —
فإيقافٌ بتاريخٍ مستقبليّ يبقى نشطاً اليوم ويُعرض «حتى <التاريخ>». و
`overlapping_client_service(client, service, starts_on)` قاعدةُ التداخل الوحيدة:
ترفض بدايةً جديدةً إن وُجد صفٌّ `ends_on is null OR ends_on >= starts_on` — وكان
`ends_on__isnull` وحده يسمح بفترةٍ متداخلةٍ مع إيقافٍ مستقبليّ (تقريران لشهرٍ
واحد). `add_client_service` يرفض بها، و`apply_package` يتخطّى بها بسببٍ مكتوب.
والإيقافُ **مرّةٌ واحدة** (صفٌّ له `ends_on` يُرفض بـ400)، ولا يسبق تاريخَ سريان
دوريةٍ مسجَّلة. و«من أيّ فترةٍ المكتب مسؤول» تُطبَّع أولَ الشهر دائماً
(`_first_of_month`): المكتبُ مسؤولٌ عن فترةٍ كاملة أو لا.

**الاقتراحُ من البطاقة لا من رقمٍ في الكود.** `suggest_frequency(client, code, day)`
تُرجع `(الدورية | None, السبب)` وتقرأ النظامَ بـ`resolve_setting(… "tax_system",
client=client)` — أي بطاقة الزبون لا إعداد المكتب:
- **إسرائيل، `vat`**: معفى (`exempt`) ⇒ سنوي؛ مرخّص/غير ربحيّ: المبيعاتُ السنوية
  فوق سقف `vat_monthly_reporting` لسنة `day` ⇒ شهري، وإلا كل شهرين.
- **إسرائيل، معفى فوق سقف `vat_exempt_dealer`**: يبقى سنوياً، ويُضاف إلى السبب
  «المبيعات تتجاوز سقف עוסק פטור لسنة <سنة> — راجع التصنيف» (ومعه «تقديري» إن
  كان السقفُ مستعاراً من سنةٍ سابقة) — بلا أرقام مبالغ.
- **صفرُ مبيعاتٍ إسرائيليّ**: الدوريةُ تبقى كل شهرين والسببُ يقول «لا مبيعات سنوية
  في البطاقة» بدل «المبيعات في حدوده».
- **فلسطين، `vat`**: المسجّل (مرخّص/معفى) ⇒ شهري، وغيرُ المسجّل ⇒ `None` (لا
  تقريرَ دوريّ) فيُطلب من الموظف اختيارٌ صريح بدل التخمين.
- `payroll` و`bookkeeping` ⇒ شهري · `annual_accounts` ⇒ سنوي · `consulting` وكلُّ
  خدمةٍ يضيفها المكتب ⇒ عند الطلب.
- **السقوفُ بياناتٌ مؤرَّخة** في `TaxThreshold` (بلا `tenant`) تُزرع بهجرة بياناتٍ
  من البحث بروابطها: IL `vat_monthly_reporting` 2026 = 1,775,000 و2027 =
  1,805,000، وIL `vat_exempt_dealer` 2026 = 122,833. سنةٌ بلا سقفٍ منشور تأخذ
  آخر سقفٍ سابق ويقول السبب «تقديري: سقف <سنة>»، وسنةٌ **قبل أقدم سقف** ⇒ `None`
  (لا استعارةَ من مستقبل).
- **السببُ نصٌّ بلا أرقام مبالغ**: النظامُ والتصنيفُ والسنةُ فقط، فلا يحتاج قناعاً.
  والاقتراحُ اقتراح: الموظف يؤكّده أو يغيّره، والمُسجَّل هو اختياره لا المقترح
  (`ClientServiceFrequency.suggested` يحفظ المقترحَ وقتها للسجلّ).

**الواجهة**: تبويبُ «الخدمات» في ملفّ الزبون يعرض النشطَ والموقوف (بتسمية
`status_label` من الخادم)، والدوريةَ الحالية و«من تاريخ»، و«غيّر الدورية من…»
(افتراضُ «سارية من» أولُ الشهر القادم، `firstOfNextMonth` — اليومُ قد يكون تاريخَ
سريانٍ مسجَّلاً فيرفضه الخادم)، و«أوقف بتاريخ…» (بتأكيد `useConfirm`، ويُخفى عن
صفٍّ له `ends_on`)، و«أضف خدمة» يسأل «من أيّ فترةٍ المكتب مسؤول؟» بحقل شهرٍ
(`input[type=month]` يُرسَل `<شهر>-01`) ويعرض المقترحَ وسببَه لتأكيده أو تغييره،
و«طبّق باقة» (ونتيجتُه بلا إضافةٍ تنبيهٌ معلوماتيّ لا خطأ). وردُّ اقتراحٍ قديم لا
يكتب فوق أحدث (عدّادُ طلبات). ومجموعةُ «الخدمات والباقات» في الإعدادات: الكتالوج
(تفعيل، إضافة، إعادة تسمية) والباقات (اسم، خدمات، سعر مقترح يُعرض «—» لمن لا يرى
المبالغ)، ومحرّرُ الباقة يعرض المفعّلةَ وحدها **وما اختِير سابقاً وهو معطَّل**
معلَّماً «معطّلة»، وحالتُها تحميلٌ وخطأٌ بزرّ «أعد المحاولة». والأزرارُ لمن يملك
المفتاح، والخادمُ هو الحكم.

## الاعتماديات

**يعتمد على:**
- `tenants` — `Tenant` (كل نموذجٍ يحمله)، و`UserCompanyMembership` (حارسُ عضويّة
  الموظف المسؤول)، والقالب في `tenants/company_templates.py` (`COMPANY_TEMPLATES`).
- `core` — `core/modules.py` (`require_module`) للترخيص، و`core/access.py`
  (`require_perm`، `user_has_perm`، ومفاتيح المكتب) للصلاحيات، و
  `core/api_defaults.py` (`ApiAuthAndUser`) للمصادقة والصلاحيات، و
  `core/activity.py` (`log_activity` لسجلّ إنهاء الزبون وإعادته وتحويل مسؤوله،
  و`register_document_history_guard` لحارس سجلّ نشاط الزبون — يُسجَّل من
  `accounting_office/apps.py` في `ready`، فالاتجاه `core` ← لا شيء).

**يعتمد عليه:** لا شيء بعد. لا استيرادَ من الموديول خارج شاشته ووثيقته — والوحدة معزولةٌ عمداً حتى تُبنى بقيةُ طبقاتها.

وكلُّ ما يأخذه من `core` **واجهةٌ عامّة** فيها (لا داخليات: لا `views` ولا
`serializers` ولا `urls`)، فلا سطرَ `ignore_imports` في `.importlinter` لهذا
الموديول.

## قواعد لا يجوز كسرها

- **المحلّل وحده يقرأ الإعدادات.** `resolve_setting` هو الترتيب
  (شغلة ← زبون ← مكتب ← افتراضي)، ولا كودَ يقرأ `OfficeSettingValue` أو
  `ClientSettingOverride` خاماً. يحرسه
  `accounting_office/tests/test_settings_guard.py` بمسح المصدر، ويثبت أنه يسقط
  على مخالفةٍ مصطنعة. نسخةٌ ثانية من الترتيب تفترق عن الأولى عند أول تعديل.
- **القائمة لا تنادي المحلّل لكل صف.** `resolve_setting_for_clients` تعطي نظامَ
  كل صفٍّ في **استعلامين** (قيمةُ المكتب + التخصيصات)، ومُسلسِلُ القائمة صفٌّ خفيفٌ
  بلا بطاقة. يحرسه اختبارُ عددِ استعلاماتٍ لا يكبر بين زبونين وعشرة.
- **كلُّ كتابة إعدادٍ تُتحقَّق قبلها** بـ`settings_registry.validate_value`: النوع،
  والاختيارات، والمستوى المسموح للمفتاح. و`ValidationError` من الخدمة تصل 400 لا
  500 (`OfficeModuleViewSet.handle_exception`).
- **تغييرُ النظام الضريبي يُفرّغ ما لا يصلح.** بعد ضبطه للزبون أو للمكتب (على
  زبائنَ لا تخصيصَ لهم) يُمرَّر كلُّ `entity_type`/`vat_classification` خارج
  اختيارات النظام الجديد إلى `""`، وتبقى المفاتيح المشتركة — في المعاملة نفسها.
- **لا زبونَ قبل اكتمال أول تشغيل.** `create_office_client` يرفض ما دام
  `first_run_status(tenant)["first_run_required"]`، والـAPI يردّ 400 بالسبب.
- **زبون المكتب ليس `Partner` ولا شركة على المنصّة ولا `PracticeClient`.** لا حقلَ
  ربطٍ بأيّها. أبو أحمد بمحلّين = **زبونان**، وجهةُ اتصالٍ واحدة تُربط بالاثنين.
- **لا حذف للزبون.** لا `DELETE` في الـAPI، و«منتهي» يبقى ببطاقته وجهاته
  وملاحظاته و`ended_on`، و«أعِد نشطاً» يمسح التاريخ ويعود. `destroy` مرفوضةٌ
  صراحةً (405). والحدثان يُكتبان في سجلّ النشاط (`log_activity`) بالفاعل.
- **جهةُ الاتصال ذاتُ الربط لا تُحذف من دفتر المكتب** — تُفكّ من الزبائن أولاً،
  والخدمة تردّ 400 بالسبب.
- **لا `UniqueConstraint(condition=…)`**: MySQL تتجاهل الفهارسَ الجزئية بصمت
  فتمرّ الهجرةُ ويغيب القيد في الإنتاج. الفرادةُ المشروطة تُترجم عموداً مُولَّداً
  (`ClientContact.primary_client_key`) ثم فرادةً غير مشروطة. يحرس الصنفَ كلَّه
  `core/tests/test_conditional_uniqueness.py`.
- **`tenant` على كل نموذج، والعزل في كل ViewSet.** `get_queryset` مقيَّدٌ بشركة
  الطلب، وكلُّ كائنٍ مرجعيّ في الجسم (زبون، جهة) يُتحقَّق أنه منها — و`Contact`
  من شركةٍ أخرى يُرفض قبل إنشاء أيّ رابط. والنماذجُ الابنة تملأ `tenant` من
  الزبون إن غاب، و**ترفض** (`ValueError`) شركةً مخالفة.
- **`visible_clients(tenant, user)` قاعدةٌ لا تُكسَر: مصدر الرؤية الوحيد.**
  كلُّ queryset أو نقطةٍ تُرجع زبوناً تمرّ بها: القائمة، والتفصيل وأفعاله
  المتداخلة (tax-card · contacts · reminders · settings · end/reactivate ·
  assign)، و`settings/<key>/clients/`، **وعدّادُ `client_customization_count`**
  (رقمٌ عن الزبائن فيُحسب على ما يراه العضو، وإلا خالف القائمةَ المفلترة تحته).
  بلا `office.clients.all` لا تُرجع إلا `responsible=user` — **فزبونُ غيرك 404 لا
  403**. ونسخةٌ ثانية من الشرط في نقطةٍ جديدة تفترق عن الأولى بصمت. وتذكرةُ
  الشغلات ستوسّع هذه الدالة وحدها بـ«المحوَّلة له شغلاتهم».
- **`visible_contacts(tenant, user)` قاعدةٌ لا تُكسَر: مصدر رؤية الجهات.** بلا
  `office.clients.all` تُرى الجهة **المربوطة بزبونٍ يراه** و**غيرُ المربوطة بأيّ
  زبون** (ليجدها المنتقي)، ويُحجب ما عداها **404** على القائمة والتفصيل والتعديل
  والحذف. حجبُ الزبون وحده كان يترك دفترَ الجهات كاملاً مفتوحاً على أسماء وهواتف.
- **سجلُّ نشاط «زبون المكتب» محروسٌ برؤيته.** `core.activity_views` يعامل
  `?entity_type=…&entity_id=…` «سجلَّ مستند» متاحاً لكل عضو؛ و`accounting_office/apps.py`
  (`ready`) يسجّل حارساً بـ`core.activity.register_document_history_guard` يستعمل
  `visible_clients`، فيأخذ مَن لا يرى الزبون **404** على تاريخه. والطبقةُ الدنيا
  لا تستورد الموديول (عقود `.importlinter`) — البوّابةُ تُسجَّل من المالك.
- **`can_see_amounts` و`mask_amounts` قاعدةٌ لا تُكسَر: مصدر المبالغ الوحيد.**
  كلُّ ردٍّ فيه مبلغ يمرّ بهما — `tax_card_payload` وتفصيلُ الزبون (البطاقة داخله)
  وPATCH البطاقة — والمبلغُ المخفيّ **`null`** في الردّ (الواجهة تعرض «—» ولا
  ترسله في الحفظ). وكتابةُ مبلغٍ بلا `office.amounts.view` ⇒ **403**، ولا يُمسّ
  المبلغ المخزَّن حين يحفظ العضو حقولاً أخرى. يحرس ذلك
  `accounting_office/tests/test_amounts_guard.py` بثلاثة مسوح: حقولُ
  `DecimalField` في **نماذج** الموديول (`get_models`)، وحقولُها المعلَنة في
  **المُسلسِلات**، ومفاتيحُ **الحمولات** العشرية — كلُّها مقابل `AMOUNT_KEYS`،
  ويسقط على نموذجٍ ونصٍّ مزروعين. **مفتاحُ مبلغٍ جديد يُضاف إلى `AMOUNT_KEYS`
  أولاً**، وإلا سقط الحارس.
- **الكتابةُ بمفاتيحها لا بالدور.** كلُّ نقطة كتابةٍ في `views.py` (زبائن، بطاقة،
  جهات، ربط، مستلِمون، تخصيص زبون) تتطلّب `office.clients.write`، وكتابةُ
  `settings/<key>/` تتطلّب `office.settings.manage` (ومعها الكتالوجُ والباقات، #273)، والتحويل
  `office.clients.assign`. **القارئ لا يكتب: 403**، والقراءةُ تبقى لكل عضو.
- **الموظف المسؤول عضوٌ في شركة الزبون.** قاعدةُ `is_tenant_member` في
  `accounting_office/models.py` وحدها يجيب عنها الخدمةُ (`ValidationError` ← 400)
  والنموذجُ (`ValueError` من `save()`) — فلا معنيان لـ«عضو» يفترقان. و`QuerySet.update()`
  لا يمرّ بالنموذج فلا يحرسه. والمسؤولُ عند الإنشاء هو المُنشئ **إن كان عضواً** (سوبر أدمن أو جلسة دعم يُنشئان زبوناً بلا مسؤول، و`responsible` الصريح لغير العضو يُرفض)، والتحويلُ فعلٌ
  مُسجَّل في `ActivityLog` (من ← إلى) داخل معاملةٍ يقرأ فيها الصفَّ **مقفولاً**
  (`select_for_update`) — و«من» هو المسؤول الفعليّ لحظةَ الكتابة لا نسخةً قديمة.
  وتكرارُ الإسناد لنفس الموظف لا يكتب حدثاً كاذباً.
- **الترخيص في `initial` بعد المصادقة والصلاحيات، و404 قبل 403**: طلبٌ مجهولٌ
  يأخذ 401، وعضوٌ في شركةٍ غير مرخّصة يأخذ 404 لا 403 (403 يُثبت وجود الوحدة).
  والجذر لا يُحلّ (`SimpleRouter`) كي لا يُكشَف وجودُ الوحدة لفهرسٍ غير محروس.
- **`TaxCard` لا يحمل `rest_days` ولا `filing_method`.** هما إعدادان يُخصَّصان
  للزبون فوق إعداد المكتب؛ حقلٌ هنا يصنع نسخةً ثانية تفترق عن المكتب بصمت.
- **`accounting_office` بنظامٍ ضريبيٍّ لم يُختَر**: خطوةُ أول تشغيل تمنع القائمة
  والإنشاء، و`first_run_status` مصدرُ الحقيقة — لا تخمينَ في الواجهة.
- **إعدادٌ بلا افتراضيٍّ لا يُمسح.** `reset_office_setting` يرفض `tax_system`
  و`office_size` كليهما (يعيدان المكتب إلى أول تشغيل)، والعلم `can_reset` هو ما
  تُخفيه الواجهة به. و`reset_client_setting` يفحص المستوى كما يفحصه
  `set_client_setting` — لا «حذف» لتخصيصٍ على مستوى لا يملكه المفتاح.
- **القراءةُ الجماعية محروسة**: `resolve_setting_for_clients` تمرّ بكل زبونٍ على
  `_assert_client_of_tenant`، ولا تقرأ إعداداً لزبونٍ من مكتبٍ آخر.
- **تعديلُ الزبون وبطاقته في معاملةٍ واحدة** (`update_office_client(..., tax_card=…)`):
  بطاقةٌ مرفوضة لا تُبقي الاسمَ الجديد محفوظاً خلف ردّ 400.
- **تعديلُ النظام الضريبي قراءةٌ ثابتة لا تكبر بالزبائن، ثم `UPDATE` لكل بطاقةٍ
  تغيّرت وحدها**: `_propagate_tax_system` تحسب الأنظمة بـ`resolve_setting_for_clients`
  وتجلب البطاقات مع زبونها (`select_related("client")`) باستعلامٍ واحد، فحفظُ
  البطاقة لا يقرأ زبونها من جديد. يحرسه اختبارٌ يزرع بطاقاتٍ تبطل بالتبديل ويقيس
  الفرق بين زبونين وعشرة: `UPDATE` واحدٌ لكل بطاقةٍ إضافية لا أكثر.
- **سقوفُ الحقول في الخدمة أيضاً**: المبيعات السنوية وعددُ الموظفين
  (`0..32767`) يُتحقَّقان في `_clean_tax_card_fields`، فمناداةُ الخدمة مباشرةً
  تعطي 400 لا `DataError` من القاعدة.
- **الروابط بين الكيانات محروسةٌ في النماذج**: `ClientContact` يرفض جهةً من مكتبٍ
  آخر، و`ClientReminderRecipient` يرفض رابطاً لزبونٍ آخر (مع ملء `tenant` من
  الزبون عند غيابه).
- **التسميات من الخادم**: `status_label` · `language_label` · `label` (نوع
  التذكير) · `value_label` (قيمة الإعداد) · `choices` (ومنها أيام الأسبوع) ·
  `client_label` (تسمية الإعداد من منظور الزبون: «أيام عطلة المكتب» ← «يوم راحة
  الزبون») · أسماءُ الأدوار من `/api/permissions/roles/`. تسمياتُ القيم المعروضة
  كلُّها من الخادم؛ والثوابت المحلّية ثلاثةٌ لا غير: خيارا لغة الجهة في
  `OfficeClientFile.tsx` («عربي/عبري»)، و**«مالك»** تسميةُ `manager` في شاشة
  أدوار المكتب وحدها (`OFFICE_OWNER_ROLE_LABEL`؛ تسميتُه في `ROLE_LABELS` «مدير»
  ولكلّ الشاشات، ولا تُبدَّل من أجله).

- **الدوريةُ بتاريخ سريانٍ لا في مكانها.** `ClientServiceFrequency` تُضاف ولا
  تُعدَّل، و`frequency_on` وحدها تقرأ «دوريةَ اليوم» — لا شرطٌ ثانٍ في نقطةٍ أو
  شاشة. تغييرُ الدورية بعد `ends_on` مرفوض، وقبل `starts_on` مرفوض، وتاريخٌ وقع
  لا يُعاد كتابته (400)؛ والمستقبليُّ يُستبدل صفُّه وحده.
- **الإيقافُ لا يمحو، والفتراتُ لا تتداخل.** `stop_client_service` يكتب `ends_on`
  ويُبقي الصفَّ، و`ClientService` لا `DELETE` لها في الـAPI: تقريرُ آذار المستحقُّ
  في نيسان يحتاج صفَّ آذار. والإيقافُ **مرّةٌ واحدة** (صفٌّ له `ends_on` يُرفض 400)،
  ولا يسبق تاريخَ سريان دوريةٍ مسجَّلة. و`overlapping_client_service` قاعدةُ
  التداخل الوحيدة (`ends_on is null OR ends_on >= starts_on`): الإيقافُ المستقبليّ
  **لا يفتح** فترةً متداخلة — كان `ends_on__isnull` يفتحها ويصنع تقريرين لشهرٍ واحد.
- **الحالةُ نسبةً إلى اليوم لا إلى وجود تاريخ.** `ClientService.status_on(day)`
  وحدها: موقوفةٌ ⇔ `ends_on < day`. «أوقف بتاريخ 31/12» يبقى نشطاً اليوم ويُعرض
  «حتى 31/12»، ولا `is_active` مشتقٌّ من `ends_on is None`.
- **«من أيّ فترةٍ المكتب مسؤول» فترةٌ كاملة.** تُطبَّع أولَ الشهر دائماً
  (`_first_of_month`): إرسالُ 17/5 يُخزَّن 1/5 — لا مكتبَ مسؤولٌ عن نصف فترة.
- **الباقةُ نسخٌ لا ربط.** `apply_package` يمرّ على كل خدمةٍ في الباقة: المعطَّلةُ
  في الكتالوج والمتداخلةُ مع فترةٍ قائمةٍ تُبلَّغ في `skipped` بسببهما (لا تختفي
  بصمت)، والباقي يُنسخ عبر `_insert_client_service` نفسها التي تستعملها الإضافة،
  والاقتراحُ يُحسب **مرّةً واحدة** (`on_demand` إن لا اقتراح). ولا حقلَ ربطٍ بين
  الباقة وخدمات الزبون — تعديلُ أحدهما لا يمسّ الآخر.
- **السقوفُ بياناتُ منصّةٍ مؤرَّخة لا رقمٌ في الكود.** `TaxThreshold` بلا `tenant`
  وتُقرأ بسنة اليوم (وآخر سقفٍ سابق عند الغياب، و«تقديري» معلَنةً)؛ رقمٌ في
  `services.py` كان يتعفّن مع كل نشرٍ رسميّ. وسقفُ `vat_exempt_dealer` **يُقرأ لا
  يُترك خاملاً**: تجاوزُ المعفى له يُضيف إلى السبب «راجع التصنيف» بلا أرقام مبالغ.
  و`amount` مُعفى من القناع بسببٍ مكتوب في `accounting_office/tests/test_amounts_guard.py`
  لأنه سقفٌ منشور لا مبلغُ زبون (والإعفاءُ مفتاحُه `TaxThreshold.amount` مؤهَّلاً،
  فلا يُعفى حقلٌ آخر بالاسم نفسه).
- **`suggested_price` مبلغ.** مُسجَّلٌ في `AMOUNT_KEYS` ويمرّ بـ`mask_amounts`
  في `package_payload`، وكتابتُه بلا `office.amounts.view` ⇒ 403؛ ومفتاحُ مبلغٍ
  جديد يمرّ بالثابت نفسه أو يسقط الحارس. وقرارُ القناع في `packages_payload`
  يُحسب **مرّةً للقائمة** لا لكل صفّ (كان `package.tenant` و`can_see_amounts`
  استعلاماتٍ لكل باقة).
- **كتالوجُ الخدمات والباقات بمفتاح الإعدادات.** إنشاءُ الخدمة وتعديلُها
  وتفعيلُها وكلُّ كتابةِ باقةٍ تتطلّب `office.settings.manage`، ونقاطُ خدمات
  الزبون `office.clients.write` مع `visible_clients` (زبونُ غيرك 404). والقارئُ
  403 على كل كتابة، **ويُحرَس المفتاحُ لا الدور**: `viewer` يمنعه
  `TenantRolePermission` قبل النقطة، فيُثبت الحارسُ بعضوٍ يكتب فعلاً (محاسب)
  لا يملك مفتاحَ الإعدادات.
- **لا حذفَ لخدمةٍ في الكتالوج.** لا `DELETE` على `services/` (405)،
  و`ClientService.service` على `PROTECT` — التعطيلُ (`is_active=False`) يُخفيها
  من الإضافة ويُبقي تاريخَ من اشتراها.

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `accounting_office/tests/test_module_gate.py` | 404 لكل مسارٍ مُسجَّل بلا ترخيص (حارسٌ معمَّم يقرأ المسارات من `urls.py`)، والقالب يرخّص عند الإنشاء و`general`/`accounting_firm` لا، والتبديل لا يرخّص |
| `accounting_office/tests/test_roles.py` | الزبائنُ المحجوبون 404 على كل فعلٍ متداخل (و403 على `assign/` حيث تسبق الصلاحيةُ `get_object`)، وتجاوزُ العضو يفتح الكل، وعدّادُ المخصِّصين على ما يراه العضو، ورؤيةُ دفتر الجهات (مرئيّة/مربوطة بغير المرئيّ/غير مربوطة)، وقناعُ المبالغ ورفضُ كتابتها، والمالك والمدير يريان الكل، والقارئ لا يكتب، والتحويل وسجلُّه وقفلُ صفّه ورفضُ غير العضو، وسجلُّ النشاط المحروس 404، واختفاءُ `office_manager` بلا ترخيص ورفضُ إسناده لشركةٍ بلا وحدة |
| `accounting_office/tests/test_amounts_guard.py` | لا `DecimalField` في نماذج الموديول ولا في مُسلسِلاته ولا مفتاحَ حمولةٍ عشريّ خارج `AMOUNT_KEYS`، والقناع يُفرّغها، والحارسُ يسقط على نموذجٍ ونصٍّ مزروعين |
| `accounting_office/tests/test_clients.py` | إنشاء الزبون وبطاقته معاً، رفضُ الإنشاء قبل أول تشغيل، عددُ استعلامات القائمة، البحث والفلترة، الإنهاء والإعادة وسجلُّهما، 405 للحذف، حارسُ `tenant` على النماذج الابنة، تحقّقُ المبيعات السنوية، اختياراتُ البطاقة لكل نظام، العزل بين مكتبين |
| `accounting_office/tests/test_contacts.py` | محلّان وجهةٌ واحدة، الرئيسيةُ في القاعدة والخدمة، فكُّ الربط، بحثُ الجهات، رفضُ حذف المربوطة، ومستلِمُ كل نوع تذكيرٍ والرجوع للرئيسية |
| `accounting_office/tests/test_settings.py` | المستويات والافتراضيُّ والتخصيصُ للشغلة، رفضُ مستوىً غير مسموحٍ وقيمةٍ غير صالحة، «ارجع للافتراضي» و«ارجع لإعداد المكتب» ورفضُ الأول لمن لا افتراضي له، تفريغُ البطاقة عند تبديل النظام، عدُّ المخصِّصين، وأول تشغيل |
| `accounting_office/tests/test_settings_guard.py` | لا ذِكرَ لنموذجَي التخزين خارج وحدة المحلّل |
| `frontend_v2/utils/accountingOffice.test.ts` | إخفاءُ `filing_method` لغير الإسرائيليّ، واشتقاقُ «مخصَّص»، وشارةُ الحالة، وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه، وإخفاءُ الإسناد في «شخص واحد»، وعرضُ «—» للمبلغ المخفيّ، وأدوارُ المكتب الأربعة |
| `accounting_office/tests/test_services.py` | الخمسةُ الافتراضية و`ensure_default_services` idempotent والكودُ المولَّد يتخطّى المأخوذ، وبياناتُ السقوف من هجرة `0003` نفسها (أرقامُها وروابطها حرفاً)، وتغييرُ الدورية من تاريخٍ لا يمسّ ما قبله، والإيقافُ يُبقي الصفَّ ويمنع تعديلَ الدورية بعده ويقع مرّةً واحدة ولا يسبق سريانَ دورية، والحالةُ نسبةً لليوم (إيقافٌ مستقبليّ = نشطة)، ومنعُ التداخل (قبل `ends_on` أو فيه ⇒ رفض، وبعده ⇒ قبول)، وتطبيعُ `responsible_from` أولَ الشهر، والباقةُ نسخٌ لا ربط (وإعادةُ إضافةِ الموقوفة، وتخطّي المعطَّلةِ والمتداخلةِ بسببهما، وفرعُ «لا اقتراح» فعلاً)، والاقتراحُ لنظامين ولسقفين في سنتين وبلا سقف («تقديري») وقبل أقدم سقف (`None` + 400)، وتحذيرُ تجاوز سقف עוסק פטור وصفرُ المبيعات، والسببُ بلا أرقام، وحارسا المفتاحين (محاسبٌ بلا `office.settings.manage`، وعضوٌ يرى الزبونَ بلا مفتاح الكتابة)، و404 لزبونٍ غيرك على كل نقطة، وقناعُ `suggested_price` ورفضُ كتابته بعضوٍ يملك مفتاحَ الإعدادات ولا يرى المبالغ، وعددُ استعلاماتِ قائمة الباقات لا يكبر بعددها |
