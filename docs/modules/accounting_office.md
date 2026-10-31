# accounting_office — موديول مكتب المحاسبة: زبون المكتب وبطاقته الضريبية وجهاته وإعداداته

> مبني على قراءة الكود مباشرةً بتاريخ 2026-10-30. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

مكتبُ المحاسبة كمنتجٍ مستقلّ على المنصّة (المواصفة #270، وتذكرة الأساس #271).
المكتب **شركةٌ** على المنصّة بقالب `accounting_office`، وتحت كل شركةٍ سجلٌّ خاصّ
بها: زبائنها (منشآت بملفٍ ضريبيٍّ واحد)، وبطاقاتها الضريبية، وجهاتُ الاتصال،
وسجلُّ إعداداتها.

هذا الملفّ يوثّق **الطبقة الأولى (الأساس)**: الزبون، بطاقته، جهاته، والإعدادات.
الخدماتُ والأتعابُ والالتزاماتُ والمواعيدُ والأوراقُ والتذكيراتُ تأتي في تذاكرها،
والملفّ يُحدَّث معها.

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
| `accounting_office/models.py` | النماذج السبعة، واختياراتُ البطاقة لكل نظامٍ ضريبيّ |
| `accounting_office/settings_registry.py` | سجلّ الإعدادات: المفتاح والنوع والمستويات والافتراضيِّ ومُتحقِّقُ القيمة |
| `accounting_office/services.py` | **المحلّل** ودوالّ الكتابة، ودورةُ حياة الزبون، والبطاقة، والجهات، ومستلِمو التذكيرات |
| `accounting_office/serializers.py` | شكل الـAPI وحده — لا قراءة إعداداتٍ فيه |
| `accounting_office/views.py` | كلُّ نقطةٍ خلف بوابة الترخيص، والعزل في كل استعلام |
| `accounting_office/urls.py` | `SimpleRouter` (لا `DefaultRouter`: جذرُه فهرسٌ غير محروس) |
| `frontend_v2/services/accountingOfficeApi.ts` | عميل الواجهة فوق `restApi.ts` |
| `frontend_v2/utils/accountingOffice.ts` | الدوالّ الخالصة: تخصيصُ بطاقة الزبون، وحالةُ المخصَّص، وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه (بلا جدول تسميات). والشاشة تحفظ الحالة في العنوان عبر `useSearchParams` من react-router — لا `pushState`/`popstate` يدوياً |
| `frontend_v2/components/accounting-office/` | شاشات: القائمة (وتركّب ملفّ الزبون)، والإعدادات، وخطوة أول تشغيل، و`OfficeUi.tsx` عناصرُ عرضٍ محليّةٌ على الوضع الداكن |

## الـModels

| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `OfficeClient` | `name`, `tax_file_number` (اختياري), `status` (`active`/`ended`), `ended_on`, `notes` | `tenant` FK. **لا `Partner` ولا شركة على المنصّة.** قيدُ `CheckConstraint` يربط الحالة بتاريخها |
| `TaxCard` | `entity_type` (فرد/تضامن/مساهمة/غير ربحية), `vat_classification` (مشتغل مرخّص/معفى/غير مسجّل فلسطينيّاً · עוסק מורשה/עוסק פטור/מלכ"ר إسرائيلياً), `annual_sales` (Decimal، تُتحقَّق في الخدمة), `has_employees`, `employees_count`, `is_self_employed` | `OneToOne` مع `OfficeClient`، تُنشأ معه. **يوم الراحة وطريقة التقديم ليسا هنا** — إعدادان |
| `Contact` | `name`, `phone`, `language` (`ar`/`he`) | `tenant` FK. الشخص يملكه المكتب لا الزبون |
| `ClientContact` | `is_primary`, `primary_client_key` (عمود مُولَّد) | `(client, contact)` فريد. عمودٌ مُولَّد + فرادةٌ غير مشروطة = **جهة رئيسية واحدة على الأكثر** فعلياً في MySQL |
| `ClientReminderRecipient` | `reminder_type` (`documents`/`deadline`/`balance`/`appointment`) | `(client, reminder_type)` فريد ← `ClientContact`. غيابُ الصفّ = الرئيسية |
| `OfficeSettingValue` | `key`, `value` (JSON) | `(tenant, key)` فريد — قيمةُ المكتب |
| `ClientSettingOverride` | `key`, `value` (JSON) | `(tenant, client, key)` فريد — تخصيصُ الزبون |

## دوال الـservices العامة

```python
resolve_setting(tenant, key, client=None, item=None)          # القيمة الفعلية وحدها
resolve_setting_with_source(tenant, key, client=None, item=None)  # (القيمة, المصدر)
resolve_setting_for_clients(tenant, key, clients)             # القائمة: استعلامان لا استعلامان لكل زبون
set_office_setting(tenant, key, value)                        # يتحقّق ثم يكتب
reset_office_setting(tenant, key)                             # «ارجع للافتراضي» = حذف (ويُرفض لمن لا افتراضي له)
set_client_setting(client, key, value)                        # تخصيصُ زبون
reset_client_setting(client, key)                             # «ارجع لإعداد المكتب»
clients_customized_for(tenant, key) / clients_customized_payload(tenant, key)
first_run_status(tenant) / office_settings_payload(tenant) / client_settings_payload(client)
setting_value_label(definition, value) / tax_system_label(value)   # مصدر التسميات الوحيد
create_office_client(...) / update_office_client(...)         # الإنشاء مرفوضٌ قبل اكتمال أول تشغيل
end_office_client(..., actor=, request=) / reactivate_office_client(..., actor=, request=)
tax_card_payload(client) / update_tax_card(client, **fields)  # المبيعات السنوية تُتحقَّق هنا
link_client_contact(...) / unlink_client_contact(...) / set_primary_client_contact(...)
delete_contact(contact)                                       # يُرفض إن كانت مربوطةً بزبون
set_reminder_recipient(...) / resolve_reminder_recipient(client, reminder_type) / reminder_recipients_payload(client)
```

## أهم الـAPI endpoints

كلّها تحت `/api/accounting-office/`، وكلّها مصادَقةٌ بعضوية الشركة (الأدوار في #272). بلا `AllowAny`.

| Method | المسار | الـview |
|---|---|---|
| `GET/POST` | `clients/` | `OfficeClientViewSet` (`list`, `create`) |
| `GET/PUT/PATCH` | `clients/<pk>/` | `OfficeClientViewSet` (`retrieve`, `update`, `partial_update`) |
| `POST` | `clients/<pk>/end/` · `clients/<pk>/reactivate/` | `OfficeClientViewSet` (`end`, `reactivate`) |
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

**لا `DELETE` للزبون**: `destroy` ترفع `MethodNotAllowed` (405)، و«منتهٍ» حالةٌ
تُكتب بقيمتها الحقيقية لا صفٌّ يُطوى.

## الاعتماديات

**يعتمد على:**
- `tenants` — `Tenant` (كل نموذجٍ يحمله)، والقالب في `tenants/company_templates.py` (`COMPANY_TEMPLATES`).
- `core` — `core/modules.py` (`require_module`) للترخيص، و`core/api_defaults.py` (`ApiAuthAndUser`) للمصادقة والصلاحيات، و`core/activity.py` (`log_activity`) لسجلّ إنهاء الزبون وإعادته.

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
  الزبون»). تسمياتُ القيم المعروضة كلُّها من الخادم؛ وخيارا لغة الجهة في نموذج
  الإدخال («عربي/عبري» في `OfficeClientFile.tsx`) وحدهما ثابتان محلّيّان.

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `accounting_office/tests/test_module_gate.py` | 404 لكل مسارٍ مُسجَّل بلا ترخيص (حارسٌ معمَّم يقرأ المسارات من `urls.py`)، والقالب يرخّص عند الإنشاء و`general`/`accounting_firm` لا، والتبديل لا يرخّص |
| `accounting_office/tests/test_clients.py` | إنشاء الزبون وبطاقته معاً، رفضُ الإنشاء قبل أول تشغيل، عددُ استعلامات القائمة، البحث والفلترة، الإنهاء والإعادة وسجلُّهما، 405 للحذف، حارسُ `tenant` على النماذج الابنة، تحقّقُ المبيعات السنوية، اختياراتُ البطاقة لكل نظام، العزل بين مكتبين |
| `accounting_office/tests/test_contacts.py` | محلّان وجهةٌ واحدة، الرئيسيةُ في القاعدة والخدمة، فكُّ الربط، بحثُ الجهات، رفضُ حذف المربوطة، ومستلِمُ كل نوع تذكيرٍ والرجوع للرئيسية |
| `accounting_office/tests/test_settings.py` | المستويات والافتراضيُّ والتخصيصُ للشغلة، رفضُ مستوىً غير مسموحٍ وقيمةٍ غير صالحة، «ارجع للافتراضي» و«ارجع لإعداد المكتب» ورفضُ الأول لمن لا افتراضي له، تفريغُ البطاقة عند تبديل النظام، عدُّ المخصِّصين، وأول تشغيل |
| `accounting_office/tests/test_settings_guard.py` | لا ذِكرَ لنموذجَي التخزين خارج وحدة المحلّل |
| `frontend_v2/utils/accountingOffice.test.ts` | إخفاءُ `filing_method` لغير الإسرائيليّ، واشتقاقُ «مخصَّص»، وشارةُ الحالة، وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه |
