# crm — نواةُ CRM كترا التسويقيّة (زبائنُ كترا المحتملون)

> مبني على قراءة الكود مباشرةً بتاريخ 2026-09-13. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

نواةُ CRM خلفيّةٌ لموظّفي عمليات كترا أنفسِهم (`platform_ops.PlatformEmployee`)
ومديرِ العمليات — لا علاقةَ لها بشركات الزبائن على المنصّة ولا بـ`partners`
ولا بـ`sales`: زبائنُ هذه الوحدة محلّاتٌ محتمَلة قبل أن تصير شركاتٍ على
المنصّة. المسارات تحت `/api/platform/crm/`، ومحروسةٌ بموظّف أو مدير عمليات
منصّة — **بالصلاحيّتين نفسِهما** لا بنسخةٍ منهما
(`platform_ops.permissions.IsPlatformOperationsStaff`/`IsPlatformOperationsManager`).

**app منفصل عن `platform_ops` عمداً (التذكرة 212-B):** `platform_ops` كبيرةٌ
جداً بالفعل (models.py وservices.py عشراتُ آلاف الأسطر)، و`.importlinter`
لا يحرسها إطلاقاً، بينما `crm` app جديد محروسٌ من يومه الأوّل.

## أهم الملفات

| الملف | الغرض |
|---|---|
| `crm/models.py` | `LeadImportBatch`، `Lead`، `LeadPhone` (مفتاحُ الفرادة)، `LeadActivity` (append-only)، `LeadTransfer` — **كلُّها بلا `tenant`** عمداً (زبائنُ كترا لا زبائن شركة)، محروسٌ بـ`crm/tests/test_crm_isolation_guard.py` |
| `crm/phone.py` | `normalize_phone` — تطبيعُ الهاتف إلى E.164، مفتاحُ فرادةٍ مخزَّنٌ في القاعدة فلا يُعدَّل بلا هجرةِ بيانات |
| `crm/services.py` | كلُّ الكتابة: `create_lead`/`suggest_lead`/`claim_lead`/`release_lead`/`log_activity`/`change_lead_status`/`transfer_lead`/`request_lead_transfer`/`decide_lead_transfer`/`approve_lead`/`reject_lead`/`import_leads`/`employee_lead_stats`/`manager_lead_overview`؛ والإحصاءان يجمعان المتابعات المتأخرة بلا استعلام لكل موظف، وحدُّ «اليوم» من `follow_up_day_bounds` وحدَها (المصدرُ الواحد لمعنى «متأخّر») |
| `crm/views.py` | `LeadViewSet` (ومن قائمته `follow_up=due|overdue|upcoming` بعد تضييق النطاق، بحدِّ **يومٍ** لا لحظةٍ فالثلاثةُ مجموعاتٌ متمايزةٌ و`overdue ⊂ due`)، `LeadTransferViewSet`، `MyLeadStatsView`، `ManagerLeadOverviewView`، `ColleagueDirectoryView` |
| `crm/urls.py` | مسارات `/api/platform/crm/` |
| `crm/tests/` | اختباراتُ الوحدة — راجع §الاختبارات (العددُ يتغيّر فلا يُكتب) |

## النماذج

| Model | الحقول المفتاحية | العلاقات |
|---|---|---|
| `Lead` | `store_name`·`status`(١٠ حالات)·`assigned_to`(`None`=مخزن متاح)·`approval_status`·`source` | `assigned_to`/`suggested_by` → `platform_ops.PlatformEmployee` (مرجعٌ نصّي)، `converted_tenant` → `tenants.Tenant`، `import_batch` → `LeadImportBatch` |
| `LeadPhone` | `e164` (**`unique=True` — مفتاحُ منع التكرار الوحيد في الوحدة**)، `kind` | `lead` → `Lead` (CASCADE)؛ قيد `UniqueConstraint(lead, kind)` غيرُ مشروط |
| `LeadActivity` | `kind`، `body`، `status_before/after` — **لا تعديل ولا حذف** | `lead` (PROTECT)، `employee`، `actor` |
| `LeadTransfer` | `status`(pending/approved/rejected)، `reason` إلزاميّ | `lead` (PROTECT)، `from_employee`، `to_employee` (PROTECT) |
| `LeadImportBatch` | عدّادات الدفعة و`duplicates` (JSON) | `leads` (`Lead.import_batch`) |

## قرارٌ معماريّ: `crm` عضوٌ معلَنٌ في عنقود المنصّة

`crm` **يستورد `platform_ops` صراحةً** — الصلاحيّتان من
`platform_ops.permissions`، و`PlatformEmployee` من `platform_ops.models` في
أدوات الاختبار. وهذا مُعلَنٌ لا مُهرَّب: `PLATFORM_CLUSTER_APPS` في
`platform_ops/tests/test_isolation_guard.py` تضمّ `platform_ops` و`crm`، فيُعفى
كلٌّ منهما من حارس «لا يستوردني أحد».

**والسببُ أنّ الاعتمادَ قائمٌ في القاعدة أصلاً:** `Lead.assigned_to`/
`suggested_by` و`LeadTransfer.from_employee`/`to_employee` مفاتيحُ أجنبيّةٌ
حقيقيّةٌ إلى `platform_ops.PlatformEmployee`. فحجبُ سطر الاستيراد بمرجعٍ نصّي أو
بـ`apps.get_model()` لا يُلغي الاعتماد — يجعله **غيرَ معلَن** وحده، وهو أسوأ.
(المرجعُ النصّيُّ في النماذج يبقى كما هو، لكنّه أسلوبُ جانغو المعتاد في تعريف
المفاتيح لا تحايلٌ على الحارس.)

وثمنُ هذا الإعفاء شرطٌ واحدٌ محروسٌ في الاتّجاه المعاكس
(`crm/tests/test_crm_isolation_guard.py::CrmIsNotImportedByTheBusinessAppsTest`):
**لا تطبيقَ شركاتٍ يستورد `crm`** — فيبقى عنقودُ المنصّة كلُّه قابلاً للحذف دون
أن يتوقّف نظامُ الزبائن.

وملكيّةُ مسارات هذه الوحدة معدودةٌ في `crm/tests/test_lead_lock.py`
(`CrmOwnershipCensusTest`): كلُّ مسارٍ تحت `/api/platform/crm/` إمّا مُبرهَنٌ
عليه بصفِّ زميلٍ أو مُستثنًى بسببٍ مكتوب. ولزومُ هذا التعداد أنّ
`platform_ops/tests/test_staff_scope_guard.py` يمشي على `api/platform/ops/`
وحدَها فلا يرى هذه البادئةَ إطلاقاً.

## الصلاحيات

كلُّ نقطةٍ: `IsPlatformOperationsStaff | IsPlatformOperationsManager` (بعضُها
`IsPlatformOperationsManager` وحدها: `release`/`approve`/`reject`/الاستيراد/
`stats/overview/`). لا `AllowAny` ولا نقطةَ عامّة في هذه الوحدة إطلاقاً.

### `colleagues/` — ولماذا نقطةٌ ثانيةٌ لا توسيعُ الأولى

`GET /api/platform/crm/colleagues/` تُعيد `{id, name, job_title, is_me}` للموظّفين
`active` وحدَهم، وهي **مصدرُ منتقي «تحويل إلى»**. و`/api/platform/ops/employees/`
لا تصلح له: `PlatformEmployeeViewSet.get_queryset` تُضيَّق لغير المدير على صفّه هو
وحدَه — تضييقٌ مقصودٌ لأنّها تحمل التقييمَ والمستهدفاتِ والمحفظة. فتوسيعُها كان
سيُسلّم ذلك كلَّه لكلِّ زميل، والحلُّ نقطةٌ ضيّقةُ الحمولة. حمولتُها محروسةٌ
بقائمةٍ بيضاءَ صريحة في `crm/tests/test_colleague_directory.py` — فمن يستبدلها
غداً بالمُسلسِل الكامل «لتوفير كود» يسقط عنده الحارس.

## الواجهة — أين تُستهلَك هذه النقاط

شاشاتُ الوحدة تحت `frontend_v2/components/platform/staff/crm/`، وتبويبُ
«العملاء» ثانيَ الشريط في `frontend_v2/utils/staffNav.ts` (`crm`):

| الملف | الغرض |
|---|---|
| `CrmPanel.tsx` | الحاوية: النطاقُ والترشيحُ والاستلامُ والبحثُ بالرقم، ومنها نطاق «متابعاتي» الذي يطلب المستحقّ والمتأخر من عملائي — **وتبويبُه خلف وجودِ دفترٍ شخصيّ** (`hasPersonalDesk`) لأنّ `scope=mine` بلا صفِّ موظّفٍ صفرٌ بحكم البناء، ويحرسه `test_the_follow_ups_tab_is_hidden_from_a_desk_that_cannot_have_rows`، ولوحُ المدير للمدير وحدَه |
| `CrmLeadList.tsx` | القائمةُ وبطاقةُ «بحثِ الرقم قبل الاتصال» بحالاتها الثلاث (مقفولٌ · في المخزن فيظهر «استلام» · غيرُ مسجَّل)، وموعد المتابعة القادم مع تمييز المتأخر |
| `CrmLeadProfile.tsx` | ملفُّ العميل: خطّ مراحل الحالة، وسجلُّ التواصل الذي يبيّن انتقال الحالة، وتسجيلُ اتّصالٍ ورابطُ `wa.me` وطلبُ التحويل والإعادةُ للمخزن |
| `CrmTransferInbox.tsx` | صندوقُ طلبات التحويل والبتُّ فيها — **بلا هذه اللوحة يصير زرُّ «طلب تحويل العميل» باباً مسدوداً** |
| `CrmMyStats.tsx` | عدّاداتُ الموظّف من `stats/me/` — مجموعةٌ في الخادم لا محسوبةٌ في الواجهة |
| `CrmManagerPanel.tsx` | رفعُ الأرقام بنتيجةِ دفعةٍ كاملة (مُنشأ/مكرَّر/غيرُ صالح + مَن لديه كلُّ مكرَّر)، واعتمادُ الاقتراحات ورفضُها، وعلى بطاقةِ كلِّ موظّفٍ شارةُ «متأخرة» **حقلاً يُعرَض لا نصّاً يُلحَم في اسمه** |

وعقدُها محروسٌ ساكناً في `platform_ops/tests/test_crm_ui_contract.py`:
**تعدادُ استهلاكٍ يَعدُّ النداءَ في مكوّنٍ لا التصديرَ في عميل الـAPI.** الصيغةُ
الأولى منه سألت «هل المسارُ مستهلَكٌ في `platformCrmApi.ts`؟» فكان الجواب نعم
لكلِّ مسار، وخمسُ دوالَّ لا يستدعيها مكوّنٌ واحد — ومنها صندوقُ التحويل كلُّه:
الطلبُ يُرسَل ولا يراه أحد، والحارسُ أخضر.

## قواعد لا يجوز كسرها

1. **كلُّ كتابةٍ عبر `crm/services.py`** — لا كتابة من الـview مباشرةً.
2. **`LeadPhone.e164` هو مفتاحُ منع التكرار الوحيد** — لا أعمدة هاتف على `Lead`.
   القيد `UniqueConstraint(lead, kind)` **غيرُ مشروط عمداً** (MySQL تتجاهل
   الشرطي بصمت)، وفرادةُ `e164` نفسِها عمودٌ `unique=True` عاديّ (يعمل بلا
   شرط أصلاً).
3. **`LeadActivity` بلا مسار تعديلٍ أو حذف** — `PUT`/`PATCH`/`DELETE` على
   `leads/<pk>/activities/` تردّ 405 بنصٍّ عربيّ صريح (`crm/views.py`).
4. **حارسُ الملكية في الخدمة لا في الـview**: `log_activity`/`change_lead_status`/
   `transfer_lead` كلُّها ترفض (`LeadLockedError`، 403) إن لم يكن الفاعلُ صاحبَ
   العميل ولا مديراً — وتُختبر مباشرةً بتجاوز المُسلسِل (`test_lead_transfer.py`)
   لا عبر الـHTTP وحده.
5. **`normalize_phone` (`crm/phone.py`) مفتاحُ فرادةٍ مخزَّن** — تغييرُ سلوكها
   يستلزم هجرةَ بياناتٍ تعيد تطبيعَ الصفوف القديمة.
6. **لا `tenant` على أيّ نموذج هنا** — محروسٌ بقائمةٍ بيضاءَ صريحة
   (`crm/tests/test_crm_isolation_guard.py`).
7. **لا نسخةَ ثانيةً من قاعدة صلاحيّة** — الصلاحيّتان تُستورَدان من
   `platform_ops.permissions` لا تُستنسَخان؛ ونسخُهما محلّياً يخلق تبايناً
   مستقبليّاً في قاعدةِ أمن (راجع القرار المعماريّ أعلاه).
8. **لا يستورد `crm` أيُّ تطبيقِ شركات** — الشرطُ الذي يُبقي عنقودَ المنصّة
   قابلاً للحذف، محروسٌ في `crm/tests/test_crm_isolation_guard.py`.
9. **كلُّ حقلِ إدخالٍ نصّيٍّ مسقوفٌ بعرض عموده** — `CharField()` بلا `max_length`
   يمرّ من التحقّق ثمّ تقتطعه MySQL بصمتاً، وSQLite لا تُظهر الفرق. يُقرأ العرضُ
   من النموذج لا يُكتب رقماً، ويحرسه
   `crm/tests/test_input_widths_fit_columns.py`. وحدُّ الدفعة
   `MAX_IMPORT_ROWS = 5000` لأنّ `import_leads` معاملةٌ ذرّيّةٌ واحدة.
10. **كلُّ نقطةٍ في الـURLconf تصل شاشةً، أو لها عذرٌ مكتوب** — العذرُ سطرٌ في
    `UNUSED_BY_DESIGN` داخل `platform_ops/tests/test_crm_ui_contract.py` يقول
    **لماذا**. نقطةٌ موصولةٌ بعميل الـAPI ولا تستدعيها شاشةٌ = فعلٌ يُرسَل ولا
    مَن يراه.
11. **صاحبُ العميل يُحوّل ولا يَطلُب** — `request_lead_transfer` ترفض طلباً من
    صاحب العميل نفسِه (400، `owner_transfers_directly`). بلا هذا يُنشَأ طلبٌ
    معلَّقٌ منه إليه، ثمّ يسدّ `transfer_already_pending` **بابَه هو** حتى يبتَّ
    أحدٌ في طلبٍ لا معنى له. والملكيّةُ في الواجهة تُقارَن بمعرّف الموظّف من
    **ملفّه** لا بـ`is_me` في `colleagues/` — فذاك الدليلُ يعيد `active` وحدَهم،
    فموظّفٌ في إجازةٍ يسقط من دليل نفسِه.
12. **«متأخّر» وَحدتُه يومٌ لا لحظة، وتعريفُها واحدٌ في ثلاثةِ مواضع** —
    المرشِّحُ (`_apply_lead_filters`) وعدّادُ الموظّف (`employee_lead_stats`)
    ولوحةُ المدير (`manager_lead_overview`) كلُّها تقرأ
    `crm/services.py` (`follow_up_day_bounds`)، وشارةُ البطاقة في
    `CrmLeadList.tsx` تقيس منتصفَ الليلة المحلّيّة نظيراً لها. والسببُ أنّ
    الشاشةَ تكتب **تاريخاً** يختاره الموظّف وتُلحق به `T09:00:00` اعتباطاً: فبقياس
    اللحظة يغيب موعدُ اليومِ عن «متابعاتي» صباحاً ثمّ يصير «متأخّراً» في التاسعة
    وواحدة، ويصير `due` (`__lte=now`) و`overdue` (`__lt=now`) **مجموعتَين
    متطابقتَين عمليّاً** — ثلاثةُ أسماءٍ لسلوكَين. ولا `__date` هنا أبداً: جانغو
    تترجمها `DATE(CONVERT_TZ(...))` وجداولُ `mysql.time_zone` فارغةٌ على خادمنا
    فتعيد `NULL` أي صفرَ صفوفٍ بلا خطأ — الحدودُ من `core/date_ranges.py`
    (`local_day_start`). يحرسه `crm/tests/test_lead_follow_up_filters.py`
    (`OverdueMeansOneThingEverywhereTest`) و
    `platform_ops/tests/test_crm_ui_contract.py`
    (`test_the_overdue_badge_measures_a_day_not_an_instant`).
13. **لا `window.prompt`/`confirm`/`alert` في شاشات المنصّة** — حوارُ المتصفّح لا
    يُنسَّق ولا يحمل اتّجاه RTL وتحجبه بعضُ المتصفّحات صامتاً فيبدو الزرُّ
    معطوباً؛ والسببُ يُكتَب في حقلٍ داخل الصفحة (نمطُ `ToastProvider`/
    `ConfirmProvider` القائم).

## الاختبارات

`crm/tests/`: تطبيعُ الهاتف (جدولٌ ذهبيّ ≥٢٠ حالة) · فرادة الهاتف (قيدُ قاعدة
حقيقيّ لا حارسَ بايثون) · قفلُ الملكية (403/409) · التحويل (مباشر/معلَّق) ·
الاقتراحات (pending حتى الاعتماد) · append-only للنشاط (405) · الاستيراد
(مكرَّرٌ لا يُسقِط الدفعة) · **مديرٌ بلا صفِّ `PlatformEmployee`** (`test_manager_without_employee_row.py`: `scope=mine` له صفرٌ **بحكم البناء** بينما `all` تعيد الصفَّين، والمخزنُ ليس بديلاً، و`stats/me/` ترفع 403 — وهي الحقيقةُ التي يُبنى عليها هبوطُ لوحة الواجهة) · حارسُ المسارات (يعدّها من الـURLconf) · حارسُ
العزل (بلا tenant) · مطابقة `choices` لأعمدتها · **مطابقةُ سقوف الإدخال
لأعمدتها** (`test_input_widths_fit_columns.py`، ومنه دليلٌ سلوكيٌّ أنّ الرفضَ 400
لا خطأُ قاعدة، ودليلٌ أنّ الخدمة تحرس الطولَ بلا المُسلسِل) · رسمُ الهجرات
(اعتمادٌ على `tenants` و`platform_ops`) · ثباتُ عدد الاستعلامات في نظرة المدير
العامّة · **تعدادُ الملكيّة** لكلّ مسارات الوحدة (`test_lead_lock.py`) · **دليلُ الزملاء** بقائمةٍ بيضاءَ على الحمولة وباستثناء غيرِ النشط (`test_colleague_directory.py`) · **صاحبُ العميل لا يَطلُب تحويلاً** — عبر الـHTTP وفي الخدمة مباشرةً (`test_lead_transfer.py`) · **مرشِّحُ المتابعات بحدِّ يومٍ** (`test_lead_follow_up_filters.py`: موعدُ اليومِ مستحقٌّ وليس متأخّراً ولا قادماً، والثلاثةُ مجموعاتٌ متمايزةٌ فعلاً، و`NULL` ليس في أيٍّ منها، و`OverdueMeansOneThingEverywhereTest` يسأل المرشِّحَ والعدّادَين عن صفٍّ موعدُه منتصفُ ليلةِ اليوم فيلزمهم جواباً واحداً).
