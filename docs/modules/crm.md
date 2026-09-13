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
| `crm/services.py` | كلُّ الكتابة: `create_lead`/`suggest_lead`/`claim_lead`/`release_lead`/`log_activity`/`change_lead_status`/`transfer_lead`/`request_lead_transfer`/`decide_lead_transfer`/`approve_lead`/`reject_lead`/`import_leads`/`employee_lead_stats`/`manager_lead_overview` |
| `crm/views.py` | `LeadViewSet`، `LeadTransferViewSet`، `MyLeadStatsView`، `ManagerLeadOverviewView` |
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

## الاختبارات

`crm/tests/`: تطبيعُ الهاتف (جدولٌ ذهبيّ ≥٢٠ حالة) · فرادة الهاتف (قيدُ قاعدة
حقيقيّ لا حارسَ بايثون) · قفلُ الملكية (403/409) · التحويل (مباشر/معلَّق) ·
الاقتراحات (pending حتى الاعتماد) · append-only للنشاط (405) · الاستيراد
(مكرَّرٌ لا يُسقِط الدفعة) · حارسُ المسارات (يعدّها من الـURLconf) · حارسُ
العزل (بلا tenant) · مطابقة `choices` لأعمدتها · **مطابقةُ سقوف الإدخال
لأعمدتها** (`test_input_widths_fit_columns.py`، ومنه دليلٌ سلوكيٌّ أنّ الرفضَ 400
لا خطأُ قاعدة، ودليلٌ أنّ الخدمة تحرس الطولَ بلا المُسلسِل) · رسمُ الهجرات
(اعتمادٌ على `tenants` و`platform_ops`) · ثباتُ عدد الاستعلامات في نظرة المدير
العامّة · **تعدادُ الملكيّة** لكلّ مسارات الوحدة (`test_lead_lock.py`).
