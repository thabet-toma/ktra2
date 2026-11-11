# accounting_office — موديول مكتب المحاسبة: زبون المكتب وبطاقته وجهاته وإعداداته وأدواره وخدماته وباقاته والتزاماته وشغلاته وتنبيهاته ودفترِ زبونه

> مبني على قراءة الكود مباشرةً بتاريخ 2026-11-04. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

مكتبُ المحاسبة كمنتجٍ مستقلّ على المنصّة (المواصفة #270، وتذكرة الأساس #271).
المكتب **شركةٌ** على المنصّة بقالب `accounting_office`، وتحت كل شركةٍ سجلٌّ خاصّ
بها: زبائنها (منشآت بملفٍ ضريبيٍّ واحد)، وبطاقاتها الضريبية، وجهاتُ الاتصال،
وسجلُّ إعداداتها، **وموظّفوها وأدوارهم ومسؤولُ كل زبون** (#272)، **وكتالوجُ خدماته وباقاتُه الجاهزة، وخدماتُ كل زبونٍ بدوريتها المؤرَّخة** (#273)، **ولائحةُ مواعيد المنصّة والمحرّكُ النقيّ والتقويمُ المحسوب** (#274)، **والالتزاماتُ والشغلاتُ المحفوظة وشاشةُ «اليوم» ومحرّكُ «حدّث المكتب ليوم X»** (#275)، **ودرجتا التأخير والتنبيهاتُ الداخلية وجرسُها** (#276)، **وقائمةُ الأوراق الشهرية والسنوية وشبكةُ الأشهر وحالاتُها الأربع وملفاتُها بوصف נספח ז ومددُ الحفظ القانونية** (#278)، **ومتابعةُ استحقاق الرواتب: نسختا اللائحة v2/v3 ونصفُ السنويُّ وإعدادُ بنودها ودوريةُ خدمتها وبنودُ أوراقها** (#279).

هذا الملفّ يوثّق الطبقاتِ المبنية: الزبون وبطاقته وجهاته وإعداداته، والأدوار
والصلاحيات والموظف المسؤول، والخدمات والباقات وخدمات الزبون، ولائحةَ المواعيد
والتقويم، والالتزاماتِ والشغلات، والتنبيهاتِ الداخلية وجرسَها، **وتعديلَ المكتب
على اللائحة والتمديدَ والتزاماتِ المكتب والأحداث** (#277)، **وقائمةَ الأوراق
ووليدَها وشبكتَها** (#278)، **واستحقاقَ الرواتب ومواعيدَه** (#279)، **وأتعابَ
المكتب: الاشتراكَ والمسودّاتِ واعتمادَها** (#282، الجزء أ١)، **والدفعاتِ و«اللي
عليه» وكشفَ الحساب** (#283، الجزء أ — الخادم؛ وشاشاتُه ب). التذكيراتُ
وتصعيدُ التذكير و«جاهز للإرسال» (#280)، **وفاتورةُ الأتعاب الورقية وحقولُها
القانونية والترقيمُ والإشعارُ الدائن وشاشةُ «المسودّات»** (أ٢ من #282)، وإشعارُ
الدفع وتصنيفُ الدفاتر (#285) تأتي في تذاكرها، والملفّ يُحدَّث معها.

**ودفترُ الزبون (#286، الجزء أ — الخادم):** ثمانيةُ نماذجَ تبدأ من
`ClientBook`، وخدماتُها في `accounting_office/client_books.py`، ونقاطُها في
`OfficeClientBookViewSet`. **ليس دفترَ الشركة**: لا يمسّ محرّكَ القيود العام
(`accounting`)، والقرارُ وسببُ الاستثناء والبديلُ المرفوض في
`docs/decisions/client_books.md`. **وشاشاتُه (الجزء ب):** تبويبُ «الدفتر» في ملفّ
الزبون (`OfficeClientBook`) — وفيه **فتحُ الدفتر** لمن يملك `office.clients.write`
حين لا دفترَ للزبون — و«للإدخال» بطاقةً في شاشة «اليوم» وعدّادُها منها، ومحرّرُ
شجرة الزبون في إعدادات المكتب (`OfficeClientBooksTree`).

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
| `accounting_office/models.py` | النماذجُ السبعةُ والأربعون، واختياراتُ البطاقة لكل نظامٍ ضريبيّ، و`is_tenant_member` (قاعدةُ العضويّة الواحدة)، وحارسُ عضويّة الموظف المسؤول في `save()`، و**لائحةُ المواعيد** (`DeadlineSchedule`/`DeadlineRule`) وحارسُ مفاتيح شروطها، و**`OfficeAlert`** وأنواعُه القابلة للإضافة صفّاً (#276)، و**بنودُ الأوراق وصفوفُها وملفاتُها ومددُ الحفظ** (#278)، و**`CADENCE_SEMIANNUAL`** ودوريةُ نصف السنة و**`PlatformDocumentItem.default_status`** (#279)، و**`ReminderTemplate`/`ReminderLog`/`ReminderPostpone`/`OfficeHoliday` و`REMINDER_DEFAULT_TEXTS` وحقولُ إذن التذكير في `Contact`** (#280)، و**`ClientAppointment`** وتسمياتُ أنواع المواعيد وحالاتها (#281)، و**ثمانيةُ نماذج دفتر الزبون وشجرتاه** (#286)، و**نماذجُ الأتعاب الخمسة** (#282 — `FeeSubscription` و`ClientServicePrice` و`FeeExtraService` و`FeeDraft` و`FeeDraftLine`، ونوعُ التنبيه `fee_draft_pending`)، و**نماذجُ الدفعات الأربعة** (#283 — `FeePayment` و`FeeReceiptSequence` و`FeePaymentAllocation` و`FeeWriteOff`، ولا عمودَ لـ«المدفوع» ولا لـ«المتبقّي») |
| `accounting_office/settings_registry.py` | سجلّ الإعدادات: المفتاح والنوع والمستويات والافتراضيِّ ومُتحقِّقُ القيمة وحدُّها الأدنى والأعلى، ومجموعاتُ العرض (`GROUP_ALERTS` لـ#276 و`GROUP_REMINDERS` لـ#280)، و**قوائم `EVENT_KIND_CHOICES` و`PAYROLL_OBLIGATION_CHOICES` و`REMINDER_TYPE_CHOICES`** (#277 · #279 · #280 — تُوسَّعان صفّاً ولا تستوردان النماذج)، و**`book_entry_method` وقائمتا طريقتَي الإدخال** (#286 — طريقتان لا حقلٌ في الدفتر)، و**`fee_method` وقائمةُ طرق الأتعاب (وساعة `hourly` معروضةٌ مرفوضة) و`fee_auto_approve` المقفل** (#282) |
| `accounting_office/services.py` | **المحلّل** ودوالّ الكتابة، ودورةُ حياة الزبون، والبطاقة، والجهات، ومستلِمو التذكيرات، و**`visible_clients`/`visible_contacts`/`can_see_amounts`/`mask_amounts`**، وكتالوجُ الخدمات وباقاتُها، وخدماتُ الزبون ودورياتُها المؤرَّخة، و**`suggest_frequency`** (#273)، و**ربطُ اللائحة بالقاعدة: `schedule_for`/`rule_applies`/`client_deadlines`/`calendar_payload`** (#274)، و**الالتزاماتُ والشغلات: `_deadline_items` (المولّدُ الواحد) و`refresh_office`/`ensure_office_refreshed`/`obligation_row`/`today_payload`/`client_obligations_payload` وأفعالُ الحالة والمبلغ والإسناد** (#275)، و**`_generate_late_alerts`/`alerts_payload`/`mark_alert_seen`/`mark_all_alerts_seen` ومستلِمو التنبيه** (#276)، و**قائمةُ الأوراق: `_document_items_for` (الدالّةُ الواحدة) و`_generate_document_rows` (داخل `_refresh_client`) و`set_document_status`/`validate_document_upload`/`client_documents_payload`/`document_progress`** (#278)، و**`_assert_payroll_frequency` وإعدادُ `PAYROLL_OBLIGATIONS_KEY` في `rule_applies`** (#279)، و**التذكيرات: `set_contact_consent`/`render_reminder_body`/`validate_reminder_body`/`reminder_templates_payload`/`_reminder_candidates`/`ready_to_send_payload`/`mark_reminders_sent`/`dismiss_reminders`/`postpone_reminder`/`undo_reminder_log`/`_generate_reminder_alerts`** (#280)، و**جسرا الأتعاب: `_generate_fee_drafts` (الجسمُ في `fees.py`) و`_live_fee_draft_refs` (سقوطُ تنبيه المسودّة بالاعتماد)، و`client_service_periods` الواجهةُ العامةُ لفترات خدمة الزبون** (#282) |
| `accounting_office/deadlines.py` | **المحرّكُ النقيّ** (#274): `compute_deadline` (أربعةُ تواريخَ وثلاثُ علامات) و`periods_for` و`service_periods` و`period_label` و`add_months`/`month_start_after` — بلا استعلامٍ وبلا تاريخٍ قانونيّ في الكود |
| `accounting_office/appointments.py` | **المواعيدُ وتذكيرا الموعد والموعد الرسميّ** (#281): `create_appointment`/`reschedule_appointment`/`cancel_appointment`/`complete_appointment` (حالةٌ لا حذف)، و`send_appointment_confirmation` («ابعت تأكيد» صفُّ سجلٍّ + `confirmed_at`)، وقراءاتُ اليوم والتقويم وملفّ الزبون (`appointments_for_day`/`calendar_appointments`/`client_appointments_payload`)، و`client_owes` (نقيّة: هل على الزبون شيء؟)، و**المولّدان** `appointment_reminder_candidates` و`deadline_reminder_candidates` — نوافذُ من اليوم لا عدّادات، وبندٌ واحدٌ لكل (زبون، فترة) في الموعد الرسميّ بأقرب موعدٍ **قادمٍ عليه شيء** (وبندٌ لكل (زبون، يوم) في تذكير الموعد). يستورد `services` (و`services` يستورده **مؤجَّلاً** في `_appointments_module` فتُفكّ الدورة) |
| `accounting_office/client_books.py` | **خدماتُ دفتر الزبون** (#286): `bookkeeping_service_on`/`book_is_writable`/`assert_book_writable` (وجودُ الدفتر من `status_on` القائمة)، و`create_book`/`ensure_client_tree` (نسخُ الشجرة نسخةً واحدة)، و`add_account`، و`_next_number` (**القفلُ والترقيم** — `select_for_update` على `ClientBookSequence`)، و`create_entry`/`reverse_entry` (**يقفل الأصلَ** `select_for_update` قبل فحص «لها عكسٌ بالفعل»)، و`change_kind` (د7)، و`pending_entry_payload` («للإدخال» باستعلامٍ واحد)، و`choices_payload`/`entry_kind_choices`/`account_type_choices` (تسمياتُ الأنواع الثلاثة من النموذج — نقطةُ `client-books/choices/`). **لا استيرادَ من `accounting`** — يحرسه مسحُ `ast` في `accounting_office/tests/test_client_books.py` |
| `accounting_office/fees.py` | **خدماتُ الأتعاب** (#282، أ١): `subscription_on` (**السعرُ المؤرَّخ** — أكبر `starts_on` لا يتجاوز الشهر)، و`generate_fee_drafts` (**التوليدُ الشهريّ** ممّا يقرؤه `services.refresh_office` عبر `_generate_fee_drafts`)، و`_subscription_lines`/`_service_lines`/`_extra_lines` (المصادرُ الثلاثة)، و`_raise_pending_alerts` (**تنبيهُ الثلاثة أيام**)، و`can_approve_fee_drafts`/`approve_fee_draft`/`approve_all_fee_drafts`/`cancel_fee_draft` (**الدورُ لا المفتاح**، والصفوفُ تُقفل `select_for_update`، و**الاعتمادُ يستهلك الرصيدَ الدائن** عبر `payments.apply_open_credit` مؤجَّلاً)، و`create_subscription`/`create_extra_service`/`set_client_service_price`، و`_paused_month`/`_covered_before` (**حدودُ الفوترة**)، و`amounts_masked` و`subscription_row`/`draft_row`/`extra_row`/`service_price_row` (القناعُ قرارٌ يُحسب مرّةً، و`draft_row` تحمل `paid_amount`/`remaining`/`state` من `payments.invoice_summaries`)، و`draft_period_label` (**عامّةٌ** لأن كشفَ الحساب يقرؤها). **لا يكتب قيداً ولا فاتورة** — تلك #284 وأ٢ |
| `accounting_office/payments.py` | **الدفعاتُ و«اللي عليه» وكشف الحساب** (#283): `client_due` (**الصيغةُ الوحيدة**: `due = Σ remaining(المعتمدة) − credit`) و`client_due_map`/`client_dues_payload`، و`client_due_tax_note` (سطرُ العلم، خارجَ `due`)، و`invoice_summary`/`invoice_summaries` و`invoice_state` (`paid`/`partial`/`unpaid` مشتقّة)، و`with_invoice_totals`/`with_payment_credit` (**استعلامٌ فرعيٌّ لكل علاقة** — لا `SUM` على JOIN مزدوج يُضاعف الصفوف)، و`next_receipt_number` (**عدّادٌ مقفول**)، و`create_payment` (تخصيصٌ صريح أو أقدمُ أوّلَاً)، و`apply_open_credit` (الرصيدُ الدائن يُستهلك بتخصيصٍ جديدٍ عند الاعتماد)، و`write_off_fee_draft`/`can_write_off` (**صاحبُ المكتب وحده**)، و`visible_payments`/`filter_payments`/`payments_payload`/`payment_row`، و`ledger_payload` (**فلترةٌ وترقيمٌ في الاستعلام**). **لا يكتب قيداً ولا يعدّل مسودّة** |
| `accounting_office/serializers.py` | شكل الـAPI وحده — لا قراءة إعداداتٍ فيه |
| `accounting_office/views.py` | كلُّ نقطةٍ خلف بوابة الترخيص، والعزل في كل استعلام، وحراسةُ كل كتابةٍ بمفتاحها، ونقاطُ الخدمات والباقات وخدمات الزبون (#273)، ونقاطُ الجرس (#276 — كلُّ عضوٍ تنبيهاتُه هو)، ونقاطُ الأوراق: الحالةُ والملفاتُ وتنزيلُها وقوالبُ البنود (#278)، ونقاطُ التذكيرات: «جاهز للإرسال» وأفعالُها وسجلُّها ونصوصُها وأفعالُ مكتبه (#280)، ونقاطُ دفتر الزبون (#286 — قراءةً لكل من يرى الزبون وكتابةً بمفتاح الزبائن، **وسطرُ الدفتر يحمل `entry_kind_choices` و`account_type_choices`**: قائمتا تسمياتٍ تُبنيان في `client_books` كما في `frequency_choices`/`direction_choices`، و**`GET client-books/choices/`** تردّ `{book_kinds, entry_kinds, account_types}` لأن تسميات نوع الدفتر لا يحملها أيُّ ردٍّ آخر)، ونقاطُ المواعيد: قراءةٌ وثلاثةُ أشكالٍ للقائمة، وحجزٌ، وأفعالُ `confirm`/`reschedule`/`cancel`/`done` بلا حذفٍ ولا تعديلٍ جزئيّ (#281)، ونقاطُ الأتعاب (#282 — الاشتراكُ والإضافاتُ قراءةً وإضافة، والمسودّاتُ قراءةً واعتماداً وإلغاءً بلا حذف)، و**نقاطُ الدفعات وكشفِ الحساب** (#283 — `fees/payments/` قراءةً بفلاتر وإنشاءً بتخصيص، `fees/drafts/<pk>/write-off/` فعلٌ على المسودّة، `fees/ledger/` كشفٌ بفلترةٍ وترقيمٍ في الاستعلام، و`due` على صفّ الزبون) |
| `accounting_office/apps.py` | `ready` تُسجّل حارسَ سجلّ نشاط «زبون المكتب» في `core.activity` (`register_document_history_guard`) — فتاريخُ زبونٍ لا تراه محجوبٌ 404 |
| `accounting_office/urls.py` | `SimpleRouter` (لا `DefaultRouter`: جذرُه فهرسٌ غير محروس) |
| `frontend_v2/services/accountingOfficeApi.ts` | عميل الواجهة فوق `restApi.ts` — وفيه أنواعُ التذكيرات: `ReadyToSendPayload`/`ReminderLogRow`/`ReminderTemplateRow`/`ContactConsentPayload`/`OfficeHolidayRow` (#280)، ومنها `ReadyToSendItemKey` (الزبون والنوع **وطرفا الفترة** معاً — الخادم يطلب النهايةَ صريحة). **وحقولُ إذن التذكير على `ContactRow`** (#280/ب) مرآةُ `ContactSerializer`، فتقرؤها قائمةُ جهات الزبون بلا طلبٍ لكل جهة. **ودفترُ الزبون** (#286/ب): `listClientBooks`/`getClientBook` و`createClientBook` (فتحُ دفترٍ من التبويب) و`getClientBookChoices` (تسمياتُ الأنواع من `client-books/choices/`) و`listBookAccounts`/`addBookAccount` و`listBookEntries`/`createBookEntry` و`reverseBookEntry` و`changeClientBookKind` و`getPendingEntry`، بمفتاحٍ `CLIENT_BOOKS` ومسارُه معرّفُ الزبون لا الدفتر. **والقوائمُ تُقرأ بـ`apiGetObject` لا `apiGetList`**: كاشُ الأوفلاين على حركاتٍ تُكتب فيها يُظهر تاريخاً قديماً |
| `frontend_v2/utils/accountingOffice.ts` | الدوالّ الخالصة: تخصيصُ بطاقة الزبون، وحالةُ المخصَّص، وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه، وما يخفيه حجم «شخص واحد»، وقناعُ المبلغ المخفيّ («—»)، وأدوارُ قسم المكتب (بلا جدول تسميات). والشاشة تحفظ الحالة في العنوان عبر `useSearchParams` من react-router — لا `pushState`/`popstate` يدوياً، وأولُ الشهر ومنتقي الخدمات المتاحة وتسميةُ الدورية من اختيارات الخادم وملخّصُ الباقة (#273)، و**حسابُ التقويم** (#274): شبكةُ الشهر بالأحد أولاً، ومدى الأسبوع وأيامُه وإزاحتُه، وتجميعُ المواعيد على أيامها، وفلترُ الأنواع بلا تكرار، وتسميةُ الفترة احتياطاً — كلُّها نصوصُ ISO بلا `Date` منطقةٍ زمنية، والتاريخُ وأسماءُ الأيام من `utils/formatDate.ts` والتنقّلُ بين الشهور من `utils/monthKey.ts`، و**فلترُ «اليوم» وستُّ حالاتِه (بالفارغ «الكل»، والسادسةُ `missing_docs` #278) وأصنافُ الشارات الثلاث** (#276)، و**`alertTargetPath`** (ملفّ الزبون على `?tab=obligations&task=<id>`) و`clientTabFromSearch`/`taskIdFromSearch`/`officeTaskAnchorId`، و**رقمُ واتساب المكتب ورابطُه** (#280)؛ **و«جاهز للإرسال» وسجلُّ التذكيرات** (#280/ب): `readyToSendTypeChips` (الأنواعُ التي لها رسائلُ اليوم وحدها، بتسمية الخادم وعدِّ **رسائل** لا بنود)، و`filterReadyToSendMessages` (الرسالةُ كاملةً لأنها وحدةُ الإرسال)، و`readyToSendMessageKey` (مسوّدةُ النصّ بمفتاحٍ مشتقٍّ من محتوى الرسالة لا من فهرسها)، و`readyToSendItemKeys`، و`revertedReminderLogIds`/`canUndoReminderRow` («أُلغي» من `reverts_id`، والإبطالُ لـ`sent`/`manual` غيرِ المُبطَلين)، و`reminderLogKindClass`، و`nextDayIso` (أدنى تاريخٍ للتأجيل، بلا كائن `Date`)، و`isLockedOfficeSetting` (‏`reminder_auto_send` مقفلٌ عرضاً والخادمُ يردّ 400)، و`commonTaxSystem` (نظامُ الرسالة المشترك من بنودها، و`null` عند الاختلاف أو الغياب فلا مفتاحُ دولةٍ مخترَع)؛ **ودفترُ الزبون** (#286/ب): `bookKindOn` (نوعُ الدفتر **في تاريخ الحركة** — قاعدةُ `kind_on` نفسها، بها يُقرَّر وجوبُ التوازن) و`nextBookKind` (الانتقالُ الذي يسمح به الخادم؛ المزدوجُ ⇒ `null`) و`entryDateForMonth` (شهرُ اليوم ⇒ اليوم، وغيرُه ⇒ آخرُ يومٍ فيه، فلا تُكتب ورقةُ سنةٍ مضت في تسلسل السنة الجارية) و`clientBookPath`/`bookMonthFromSearch` (شهرُ الإدخال في العنوان) و`isLiveBookEntry`/`bookedDocumentIds` (الحيّةُ ما لم تُعكس ولم تكن عكساً) و`pendingMonthDocuments` («للإدخال» = خاناتُ `received` **وقائمةُ `annual`** ناقصَ روابط الحركات الحيّة — **اشتقاقٌ بلا نقطةٍ جديدة**) و`multipleDocumentsAllowed` (التعدّدُ في وضع «إدخال الشهر» وحده) و`bookDraftProblem` (بالسنتات: لا بندَ بلا حساب، ولا طرفين، ولا مبلغَ غيرَ رقميّ، والمزدوجُ وحدَه يُسأل عن التوازن) و`pendingEntryRowKey`/`pendingEntryClientCount`؛ و`'book'` **آخرَ** `CLIENT_TAB_KEYS` |
| `frontend_v2/components/accounting-office/` | شاشات: **«اليوم»** (`OfficeTodayScreen.tsx`، #275) والقائمة (وتركّب ملفّ الزبون)، والإعدادات (وفيه قسم «الموظفون والأدوار»، ومجموعتُها كلُّها من السجلّ)، وخطوة أول تشغيل، **والتقويم** (`OfficeCalendarScreen.tsx`، #274) — وفيه حجزُ الموعد #281 و**تأكيدُه من شريحته**، و`OfficeUi.tsx` عناصرُ عرضٍ محليّةٌ على الوضع الداكن، وتبويبُ «الخدمات» ومجموعةُ «الخدمات والباقات» (#273)، و**`OfficeAlertsBell.tsx`** جرسُ التنبيهات (#276)، و**`OfficeClientDocuments.tsx`** تبويبُ «الأوراق» و**`OfficeDocumentItemsSection.tsx`** قالبُ بنوده (#278)، و**«جاهز للإرسال»** (`OfficeReadyToSendScreen.tsx`، #280/ب) بأفعالها الأربعة، وتبويبُ «سجلّ التذكيرات» وموافقةُ الجهات (في `OfficeClientFile.tsx`)، و**`OfficeReminderTemplatesSection.tsx`** نصوصُ التذكير و**`OfficeHolidaysSection.tsx`** عطلُ المكتب (#280/ب)، و**`OfficeClientBook.tsx`** تبويبُ «الدفتر» في ملفّ الزبون (#286/ب — **فتحُ الدفتر** لمن يملك `office.clients.write` حين لا دفتر، ورأسٌ بالحالة وطريقةِ الإدخال، وجدولُ حركاتٍ بصفٍّ يُفتح على بنوده، ونموذجُ الإدخال بأوراق الشهر و«اختر الكل» في «إدخال الشهر»، و«اعكس» بتأكيدٍ على الحركة الحيّة وحدها)، وبطاقةُ «للإدخال» في **`OfficeTodayScreen.tsx`** (عدّادُها `total` من الخادم، وكبسةُ صفّها تفتح الدفتر على شهره)، و**`OfficeClientBooksTree.tsx`** محرّرُ شجرة الزبون في مجموعة «المكتب» بالإعدادات (يسرد ذوي الدفاتر، وإضافةٌ بـ`office.clients.write`)، و**`OfficeClientAppointments.tsx`** تبويبُ المواعيد و**`OfficeAppointmentCard.tsx`** بطاقةُ الموعد وأفعالُها الأربعة (#281) |

## الـModels

| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `OfficeClient` | `name`, `tax_file_number` (اختياري), `status` (`active`/`ended`), `ended_on`, `notes`, `responsible` (#272) | `tenant` FK. `responsible` FK إلى `auth.User` — `null=True`، `on_delete=SET_NULL`، `related_name="office_clients_responsible"`، ويجب أن يكون عضواً في شركة الزبون (حارسٌ في الخدمة والنموذج). **لا `Partner` ولا شركة على المنصّة.** قيدُ `CheckConstraint` يربط الحالة بتاريخها |
| `TaxCard` | `entity_type` (فرد/تضامن/مساهمة/غير ربحية), `vat_classification` (مشتغل مرخّص/معفى/غير مسجّل فلسطينيّاً · עוסק מורשה/עוסק פטור/מלכ"ר إسرائيلياً), `annual_sales` (Decimal، تُتحقَّق في الخدمة), `has_employees`, `employees_count` (تسميتُه المعروضة «عدد العاملين» #279), `is_self_employed` | `OneToOne` مع `OfficeClient`، تُنشأ معه. **يوم الراحة وطريقة التقديم ليسا هنا** — إعدادان |
| `Contact` | `name`, `phone`, `language` (`ar`/`he`), **`reminders_consent`, `consent_types`, `consent_on`, `consent_channel` (`talk`/`paper`/`whatsapp`), `consent_withdrawn_on`, `consent_withdrawn_by`** (#280) | `tenant` FK. الشخص يملكه المكتب لا الزبون. **والسحبُ لا يمحو الإذن** (تاريخُ الإذن يبقى بجانب تاريخ السحب)، و`allows_reminder(type)` هي السؤالُ الوحيد الذي تسأله القائمة |
| `ClientContact` | `is_primary`, `primary_client_key` (عمود مُولَّد) | `(client, contact)` فريد. عمودٌ مُولَّد + فرادةٌ غير مشروطة = **جهة رئيسية واحدة على الأكثر** فعلياً في MySQL |
| `ClientReminderRecipient` | `reminder_type` (`documents`/`deadline`/`balance`/`appointment`) | `(client, reminder_type)` فريد ← `ClientContact`. غيابُ الصفّ = الرئيسية |
| `OfficeSettingValue` | `key`, `value` (JSON) | `(tenant, key)` فريد — قيمةُ المكتب |
| `ClientSettingOverride` | `key`, `value` (JSON) | `(tenant, client, key)` فريد — تخصيصُ الزبون |
| `OfficeService` | `code` (`SlugField`), `name`, `is_active`, `is_builtin`, `position` | `tenant` FK. **كتالوجُ المكتب**: فرادةٌ غير مشروطة على `(tenant, code)`، والخمسةُ الافتراضية أكوادُها ثابتة (`DEFAULT_SERVICES`) لأنّ الاقتراحَ يقرؤها، وتُزرع بـ`ensure_default_services` لا بهجرة بيانات. **لا حذفَ لخدمةٍ استُعملت** — `ClientService.service` على `PROTECT` والتعطيلُ هو الطريق |
| `ServicePackage` | `name`, `suggested_price` (`Decimal(14, 2)`, `null=True`) | `tenant` FK، و`services` M2M إلى `OfficeService`. **مبلغٌ يمرّ بالقناع**: `suggested_price` في `AMOUNT_KEYS`، وكتابتُه بلا `office.amounts.view` ⇒ 403. والحذفُ مباحٌ للباقة وحدها: قالبٌ لا تاريخَ زبونٍ فيه |
| `ClientService` | `starts_on`, `ends_on` (nullable = الإيقاف), `responsible_from`, `created_at` | `tenant` FK، و`client` FK، و`service` FK. **لا حذف**: الإيقافُ يكتب `ends_on` ويُبقي الصفَّ في التاريخ. ولا فترةَ متداخلةً لنفس `(زبون، خدمة)` — `overlapping_client_service` ترفضها في الخدمة، و`status_on(day)` وحدها تقول «نشطة أم موقوفة». و`responsible_from` يُخزَّن أولَ الشهر فقط، و**`last_period_ours`** (#275) عمودٌ افتراضُه «علينا» يمنع توليدَ آخر فترةٍ عند الإيقاف |
| `ClientServiceFrequency` | `frequency` (`monthly`/`bimonthly`/`quarterly`/`annual`/`on_demand`), `effective_from`, `suggested`, `created_by` | `client_service` FK، فرادةٌ على `(client_service, effective_from)`. **الدوريةُ بتاريخ سريان**: تغييرُها **يضيف صفّاً** ولا يعدّل ما قبله، والدوريةُ في يومٍ ما = الصفُّ ذو أكبر `effective_from <= اليوم` (`frequency_on`) |
| `TaxThreshold` | `tax_system`, `kind` (`vat_monthly_reporting`/`vat_exempt_dealer`/`vat_detailed_reporting`), `year`, `amount`, `source_url` | **بلا `tenant` عمداً**: بياناتُ منصّةٍ مؤرَّخة واحدةٌ لكل المكاتب، فرادةٌ على `(tax_system, kind, year)`، وتُزرع بهجرة بياناتٍ من البحث. و`amount` **ليس مبلغَ زبون** فلا يُقنَّع — مُعفى في `test_amounts_guard.py` بسببٍ مكتوب |
| `DeadlineSchedule` | `tax_system`, `year`, `version`, `source_url`, `published_on`, `rest_day_policy` (`warn`/`postpone_client`), `authority_closed_days` (JSON)، `note` | **بلا `tenant`**: لائحةُ المنصّة واحدةٌ لكل المكاتب كالسقوف. فرادةٌ غير مشروطة على `(tax_system, year, version)`، و**النسخةُ السارية = أكبر `version`** ولا تُعدَّل نسخةٌ منشورة |
| `DeadlineRule` | `schedule`, `code`, `name`, `service_code` (من `DEFAULT_SERVICES`), `cadence` (`service`/`monthly`/`bimonthly`/`quarterly`/`semiannual`/`annual`/`event`), `rule_kind` (`day_of_next_month`/`end_of_period`/`month_day_next_year`/`days_after_event`), `rule_day`, `rule_month`, `event_kind` (#277)، `conditions` (JSON)، `is_generated`، `electronic_extension_days`، `period_overrides` (JSON)، `needs_review`، `source_url`، `position` | فرادةٌ على `(schedule, code)`. `conditions` مفاتيحها **`CONDITION_KEYS` وحدها** (`vat_classification_in` · `entity_type_in` · `has_employees` · `is_self_employed` · `annual_sales_above`)، ومفتاحٌ غيرها يرفعه `clean()`. و`period_overrides` بمفتاح شهر **نهاية** الفترة. وسطرُ `cadence="event"` لا يُولَّد دورياً أبداً: `event_kind` يطابق نوعَ حدثٍ مسجَّل. و`semiannual` (#279) دوريةُ **سطرٍ** — يناير–يونيو ثم يوليو–ديسمبر — ولا دوريةَ خدمة |

| `PeriodTask` | `period_start`, `period_end`, `internal_deadline` (أبكرُ مواعيد التزاماتها), `assignee` (nullable), `created_at` | `tenant` FK، و`client` و`client_service` على `PROTECT`. **فرادةٌ غير مشروطة** على `(client_service, period_start, period_end)` — شغلةٌ واحدة لكل خدمةٍ في فترة. `assignee=None` تعني **الوراثة** لا «بلا مسؤول»: `effective_assignee` تُعيد `assignee or client.responsible` |
| `Obligation` | `rule` (**nullable** #277)/`custom_rule`/`event`، `rule_code`/`name` (لقطةُ السطر), `origin` (`official`/`office`/`event`), `period_start`/`period_end`, `legal_date`/`official_date`/`actual_deadline`/`internal_deadline`, `platform_official_date` (nullable #277), `extended_to`/`extension_note`/`extended_by`/`extended_at` (#277), `estimated`, `postponed`, `warnings` (JSON), `status` (`pending`/`submitted`/`not_required`), `submitted_on`/`submitted_by`/`submission_number`, `prior_to_office`, `amount` (Decimal، nullable), `direction` (`due`/`refund`), `client_paid` | `tenant` FK، و`client`/`client_service`/`task`/`rule`/`custom_rule`/`event` على `PROTECT`. **فرادةٌ غير مشروطة** على `(client_service, rule_code, period_end)`، و**`CheckConstraint`** يضمن **مصدراً واحداً بالضبط**: `rule` أو `custom_rule`، لا كليهما ولا دونهما. و`due_date` خاصيّة = `extended_to or actual_deadline` — يقرؤها الأحمرُ والنافذةُ والترتيبُ وتوليدُ التنبيه. `amount` **مبلغٌ يُقنَّع**: في `OBLIGATION_AMOUNT_KEYS` و`AMOUNT_KEYS`، وكتابتُه بلا `office.amounts.view` ⇒ 403 |
| `OfficeRuleOverride` (#277) | `tax_system`, `rule_code`, `rule_day`/`rule_month`/`electronic_extension_days` (nullable = «كالمنصة»), `cleared`, `based_on` (JSON: لقطةُ قيم المنصة وقت التعديل + `schedule_id`), `note`, `created_by`, `created_at` | `tenant` FK. **سجلٌّ إلحاقيّ لا يُعدَّل ولا يُحذف**: الساري = أحدثُ صفٍّ لكل `(مكتب، نظام، كود)` بترتيب `-created_at, -id`، و`cleared=True` = «رجّع للمنصة». وفهرسٌ على `(tenant, tax_system, rule_code)`، والتعديلُ يسري على كل السنوات وكل زباين المكتب على نظامه الضريبي (`_recompute_for_code` يُقصر بـ`tax_system`) |
| `OfficeCustomRule` (#277) | `name`, `service` (FK `OfficeService`), `cadence` (بلا `event`), `rule_kind` (الثلاثة الدوريّة), `rule_day`, `rule_month`, `is_active`, `created_by`, `created_at`/`updated_at` | `tenant` FK، وكودُه المشتقّ `office-<pk>` هو `rule_code` في الالتزام — فتُصيبه الفرادةُ والفلترة. **يُعطَّل ولا يُحذف** (405)، والتعطيلُ يوقف الفترات الجديدة وحدها |
| `ClientEvent` (#277) | `kind` (من `EVENT_KIND_CHOICES`)، `occurred_on`, `note`, `created_by`, `created_at` | `tenant` FK، و`client` على `PROTECT`. **لا تعديلَ ولا حذف** («التاريخ لا يُمحى»)، ولكل حدثٍ التزاماتُه من أسطر `cadence="event"` |
| `ObligationDateChange` (#277) | `reason` (`office_override`/`platform_update`/`extension`/`extension_cleared`), `before` (JSON), `after` (JSON), `changed_by` (null للتلقائي), `created_at` | `tenant` FK، و`obligation` على `CASCADE`. **سجلٌّ إلحاقيّ**: كلُّ تغيّرِ تاريخٍ بسببه ومَن غيّره — والصفُّ لا يُعدَّل |
| `OfficeRefreshRun` | `day`, `ran_at`, `created_obligations` | `tenant` FK، **فرادةٌ غير مشروطة** على `(tenant, day)` — صفٌّ واحدٌ لكل (مكتب، يوم)، وهو ما يجعل `ensure_office_refreshed` لا تعمل مرّتين |
| `OfficeAlert` | `kind` (`task_late_internal`/`obligation_late`/`schedule_dates_changed`/`override_platform_changed`/`reminder_limit_reached`/`reminder_limit_reached_owner`)، `ref_key`، `message`، `day`، `seen_at`، `created_at` | `tenant` FK، و`recipient` FK إلى `auth.User` على `CASCADE` (المستلِمُ الوحيد)، و`client`/`task`/`obligation` **nullable على `CASCADE`** (مكانُ الفتح لا سندُ التنبيه). **فرادةٌ غير مشروطة** على `(tenant, recipient, kind, ref_key)` = «مرّةٌ واحدةٌ لكل مرجع»، وفهرسٌ `(tenant, recipient, seen_at)`. `ref_key` نصٌّ `"task:<id>"` أو `"obligation:<id>"` أو `"schedule:<id>"` أو `"override:<id>:schedule:<id>"` (#277) أو `"reminder:<زبون>:<نوع>:<بداية الفترة>:<نهايتها>"` (#280)، و`message` لقطةٌ **بلا أيّ مبلغ**. ونوعا اللائحة **بلا `client`**: وجهتُهما `OFFICE_ALERT_KIND_OPENS` ⇒ `deadline_rules`، ونوعا التذكير يفتحان `client_documents` |
| `ReminderTemplate` (#280) | `reminder_type`, `language` (`ar`/`he`), `body`, `updated_by`, `updated_at` | `tenant` FK، **فرادةٌ غير مشروطة** على `(tenant, reminder_type, language)`. **غيابُ الصفّ = نصُّ المنصّة** (`REMINDER_DEFAULT_TEXTS` في الكود)، و«ارجع للافتراضي» **حذفٌ** لا كتابةُ الافتراضيِّ مكانه — فتصحيحُ نصٍّ في الكود يصل مكتباً لم يخصّص |
| `ReminderLog` (#280) | `recipient_name`/`recipient_phone` (لقطة), `reminder_type`, `kind` (`sent`/`manual`/`dismissed`/`undo`), `channel` (`whatsapp`/`phone`/`in_person`/فارغ), `body`, `period_start`/`period_end` (nullable), `subject` (JSON: `document_item_codes`/`document_item_names`), `reason`, `reverts` (FK self), `created_by`, `batch` (UUID مفهرس: يُختم به كلُّ صفوف نداءٍ واحد), `created_at` | `tenant` FK، و`client` على **`PROTECT`** (تاريخٌ لا يُمحى)، و`contact` على `SET_NULL` (اللقطةُ تحفظ الاسم والهاتف). **إلحاقيٌّ لا يُعدَّل ولا يُحذف**: لا نقطةَ `PUT`/`PATCH`/`DELETE`، والتصحيحُ صفُّ `undo` يشير بـ`reverts` إلى ما يُبطله. وفهرسٌ `(tenant, client, reminder_type, period_start)` |
| `ReminderPostpone` (#280) | `reminder_type`, `until` (nullable = «امسح التأجيل»), `reason`, `created_by`, `created_at` | `tenant` FK، و`client` FK. **الساري = أحدثُ صفٍّ لكل (زبون، نوع)** بترتيب `-created_at, -id`: سجلٌّ لا حقل، فيبقى تاريخُ التأجيلات مكتوباً |
| `OfficeHoliday` (#280) | `date`, `name`, `created_at` | `tenant` FK، **فرادةٌ غير مشروطة** على `(tenant, date)`. **لا تقويمَ عطلٍ وطنيّ يُخترَع**: المكتبُ يعطّل يومَه، والتذكيرُ لا يُلغى بل يُحسَب في أوّل يومٍ مسموح بعده |
| `PlatformDocumentItem` (#278) | `tax_system`, `code`, `name`, `cadence` (`monthly`/`annual`), `service_codes` (JSON), `card_conditions` (JSON), `default_status` (#279), `sort_order` | **بلا `tenant`**: لائحةُ المنصّة واحدةٌ لكل المكاتب كاللائحة والسقوف. فرادةٌ **غير مشروطة** على `(tax_system, code)`. `service_codes` فارغةٌ = لكل زبون، و`card_conditions` مفاتيحُها حقولُ البطاقة وحدها (`entity_type`/`vat_classification`). **و`default_status` الحالةُ التي يبدأ بها الصفُّ المولَّد** — بندُ المنصّة وحده يحملها، وبندُ المكتب يبدأ «مطلوبة» دائماً. تُزرع بهجرة `0008`: **37 بنداً** (18 فلسطينيٌّ و19 إسرائيليّاً)، و**41** بعد `0009` بأربعة بنود رواتب (20 فلسطينيٌّ و21 إسرائيليّاً)، وعكسُ كلٍّ يحذف أكوادَه وحدها |
| `OfficeDocumentItem` (#278) | `tax_system`, `name`, `cadence`, `service_codes`, `card_conditions`, `is_active`, `created_by`, `created_at`/`updated_at` | `tenant` FK. كودُه المشتقّ `office_doc_<pk>` **مستقرٌّ** ويُخزَّن في الصفوف لقطةً. **يُعطَّل ولا يُحذف**: التعطيلُ يوقف التوليدَ وما وُلد يبقى |
| `OfficeDocumentItemChoice` (#278) | `item_code`, `included`, `updated_by`, `updated_at` | `tenant` FK، فرادةٌ على `(tenant, item_code)`. `included=False` يُخرج بندَ المنصّة من قالب المكتب، والغيابُ «ضمن القائمة» — صفٌّ يُقلب لا يُحذف. **ولبند المكتب مصدرٌ واحد**: `is_active`، فلا يُقلب من هنا |
| `ClientDocumentItemChoice` (#278) | `item_code`, `included`, `updated_by`, `updated_at` | `tenant` FK و`client` FK، فرادةٌ على `(client, item_code)`. **خيارُ الزبون يغلب الجميع**: `True` يفرض بنداً لا تنطبق شروطه ولا يريده القالب، و`False` يمحو بنداً انطبق |
| `DocumentChecklistItem` (#278) | `item_code`, `name`, `service_codes`, `cadence`, `period_start`/`period_end`, `status` (`required`/`partial`/`received`/`not_needed`), `received_on`/`received_by`/`channel`, `updated_by`, timestamps | `tenant` FK، و`client` على `PROTECT` (تاريخٌ لا يُمحى). **فرادةٌ غير مشروطة** على `(client, item_code, period_start)` = صفٌّ واحد لكل بندٍ في فترة، وفهرسٌ `(tenant, client, period_start)` لشبكة الأشهر وشارة الالتزام. والاسمُ والخدماتُ **لقطةُ وقت التوليد** |
| `DocumentFile` (#278) | `uid` (UUID فريد), `created_by`, `document_type`, `issuer_registration`, `document_date`, `document_number`, `captured_at`, `file_url`, `file_name`, `is_copy` | `tenant`/`client` FK، و`checklist_item` على `CASCADE`. **حقولُ נספח ז السبعة** (الأولى والثانية والسابعة تلقائية). `file_url` **لا يخرج في أيّ ردّ** — التقديمُ بايتاتٍ من `stream_stored_asset`. والحالةُ لا تتغيّر برفعٍ أو حذف |
| `DocumentRetentionRule` (#278) | `tax_system`, `code`, `name`, `years`, `alt_years` (nullable), `basis` (`year_end`/`later_of_year_end_or_filing`/`filing`), `source_url` | **بلا `tenant`**: مدةُ حفظٍ منشورةٌ لكل نظامٍ (فلسطين ٥ من نهاية السنة م79/1، إسرائيل ٧/٦ الأبعدُ منهما §25(ג) و٣ من التقديم §25(د))، فرادةٌ على `(tax_system, code)`. تُزرع بهجرة `0008`، ولا حسابَ تاريخٍ ولا حذفَ آليّ في v1 |
| `BookAccountTemplate` (#286) | `tax_system`, `book_kind` (`simple`/`double`), `code`, `name`, `parent_code`, `account_type` (أصول/خصوم/حقوق ملكية/إيرادات/مصاريف), `is_system` | **بلا `tenant` عمداً** كـ`TaxThreshold`: شجرةُ المنصّة واحدةٌ لكل المكاتب، وفرادةٌ **غير مشروطة** على `(tax_system, book_kind, code)`. تُزرع بهجرة `0011` لأربعة تركيباتٍ (نظامان × نوعا دفتر) بعكسٍ يحذف أكوادَها وحدها. `parent_code` **نصٌّ لا مفتاح** — الشجرةُ تُقرأ كوداً في الواجهة |
| `OfficeBookAccount` (#286) | نفسُ حقول القالب + `tenant`, `is_edited` | `tenant` FK، فرادةٌ على `(tenant, tax_system, book_kind, code)`. نسخةُ المكتب التي تُنسخ عنها دفاترُ زبائنه؛ `is_edited` تقول «عدّله المكتب» لا «هو من المنصّة» |
| `ClientBook` (#286) | `kind`, `opened_on`, `kind_changed_on` | `OneToOne` مع `OfficeClient` (دفترٌ واحد لكل زبون) و`tenant` FK يُملأ من الزبون. **لا يُحذف**، ووجودُه مشتقٌّ من خدمة مسك الدفاتر (`status_on`) لا من حقلٍ فيه. `kind_changed_on` يسجّل **من أيّ يوم** صار مزدوجاً |
| `ClientBookAccount` (#286) | `code`, `name`, `account_type`, `is_system`, `is_active` | `client` FK و`parent` **مفتاحٌ حقيقيّ** لنفسه (لا `parent_code` كالقالب: الشجرةُ صارت ملك الزبون). فرادةٌ على `(client, code)`. نسخةٌ واحدة عند إنشاء الدفتر: **لا مرجعَ حيّ** إلى القالب. `is_active` تعطيلٌ بدل حذف |
| `ClientBookSequence` (#286) | `year`, `last_number` | `client` FK، فرادةٌ على `(client, year)`. **أداةُ القفل والترقيم**: `select_for_update` ثم زيادةُ `last_number` داخل `transaction.atomic`، والرقمُ يُنسخ إلى `BookEntry.number`. **لا `MAX(number)+1` ولا `count()+1`** |
| `BookEntry` (#286) | `year`, `number`, `entry_date`, `kind` (`sales_invoice`/`purchase_invoice`/`expense`/`bank_movement`/`daily_report`), `memo`, `reverses`, `created_by`, `created_at` | `client_book` على **`PROTECT`** (دفترٌ فيه تاريخٌ لا يُطوى من تحت حركاته)، و`client` على `PROTECT`. فرادةٌ **غير مشروطة** على `(client, year, number)` — طبقةٌ ثانية تُساند القفل. **ولا عمودَ ورقةٍ فيه**: أوراقُه في `BookEntryDocument` لأن الحركةَ قد تُدخل أوراقَ شهرٍ كاملاً. و`reverses` يشير إلى الأصل، و`reversed_by` العكس — و`reverses` **`OneToOneField`**: عكسٌ واحد على الأكثر لكل حركة فرادةً في القاعدة، طبقةٌ ثانية تُساند قفلَ الأصل في `reverse_entry` |
| `BookEntryDocument` (#286) | — (رابط) | `entry` على `CASCADE` و`document` على `PROTECT`، فرادةٌ على `(entry, document)`، وفهرسٌ `(tenant, document)`. **ربطٌ يُقرأ لا عمودٌ يُكتب**: عكسُ الحركة يُعيد أوراقها إلى «للإدخال» وحدها. وقاعدةُ «حركةٌ حيّةٌ واحدة على الأكثر لكل ورقة» في `create_entry` داخل `atomic` وبقفل `select_for_update` على صفوف الأوراق |
| `FeeSubscription` (#282) | `amount` (Decimal، `AMOUNT_KEYS`), `currency` (FK `Currency` **nullable**، الافتراضُ عملةُ المنصّة), `cadence` (`monthly` وحدها اليوم), `starts_on`, `paused_from`/`paused_to` (إيقافُ فوترةٍ مؤقّت), `ended_on`, `created_at` | `tenant` FK و`client` FK. **السعرُ بتاريخ سريان**: فرادةٌ غير مشروطة على `(client, starts_on)` — تغييرُ السعر يضيف صفّاً ولا يعدّل ما قبله، وسعرُ شهرٍ = أكبرُ `starts_on` لا يتجاوز آخره (`fees.subscription_on`). وقيودُ `CheckConstraint` للمبلغ غير السالب ولترتيب طرفَي الإيقاف والإنهاء. **والشهرُ الذي يبدأ داخل الإيقاف لا مسودّةَ له** |
| `ClientServicePrice` (#282) | `amount` (Decimal، `AMOUNT_KEYS`) | `tenant`/`client` FK، و**`OneToOne` مع `ClientService`** (`related_name="price"`). سعرُ اتفاقِ هذا الزبون على هذه الخدمة لا سعرُ الكتالوج؛ والمسودّةُ السابقة لقطةٌ فلا يُعيد تغييرُه حسابَها |
| `FeeExtraService` (#282) | `service_name`, `amount` (Decimal، `AMOUNT_KEYS`), `performed_on`, `draft` (`next_month`/`standalone`), `billed_draft` (**nullable**، `PROTECT`، #282)، `created_at` | `tenant` FK و`client` FK، وفهرسٌ `(tenant, client, performed_on)`. **تُسجَّل عند التنفيذ**: `next_month` تدخل مسودّةَ الشهر التالي له، و`standalone` «فاتورة لحالها» لا تدخل مسودّةً. **وحقلان لا حقل**: `draft` اختيارُ وجهة، و`billed_draft` مفتاحُ الربط بالمسودّة التي فوترتها — يُكتب في معاملة التوليد نفسها، والإلغاءُ يُعيده `None` فتلحق الإضافةُ أوّلَ مسودّةٍ تالية، ولا تدخل مسودّتين |
| `FeeDraft` (#282) | `year`, `month`, `subtotal`/`total` (Decimal، `AMOUNT_KEYS`؛ متساويان في أ١ — لا ضريبةَ بعد), `status` (`draft`/`approved`/`cancelled`), `generated_at`, `approved_by`/`approved_at`/`approved_note` | `tenant` FK و`client` FK. **فرادةٌ غير مشروطة على `(client, year, month)`** = «مرّتان في اليوم نفسه مسودّةٌ واحدة»، و`CheckConstraint` للشهر (1..12) وللمبلغين غير السالبين. `generated_at` يُكتب من **يوم التوليد الصريح** (`fees._generated_at`) لا ساعةَ النظام، فتنبيهُ الثلاثة أيام يُقاس على تاريخه. **ولا حذف**: الحالتان فعلان وحدهما |
| `FeeDraftLine` (#282) | `label` (بلا مبلغٍ في نصّه), `amount` (Decimal، `AMOUNT_KEYS`), `source` (`subscription`/`service`/`extra`) | `tenant` FK، و`draft` على `CASCADE` (`related_name="lines"`). **المصدرُ مكتوبٌ لا مستنتَج** لتشرحه الواجهة، والمبلغُ لقطةُ وقت التوليد |
| `FeePayment` (#283) | `method` (`cash`/`cheque`/`transfer`/`card` — ثوابت `FEE_PAYMENT_METHOD_*` وتسمياتٌ عربية)، `amount` (Decimal، `AMOUNT_KEYS`)، `paid_at`، `note` (300، فارغةٌ افتراضاً)، `receipt_number` (30)، `created_by`، `created_at` | `tenant` FK و`client` FK. **ولا حقلَ عملة** كـ`FeeDraft` (الأتعابُ بعملة المكتب الواحدة). فرادةٌ على `(tenant, receipt_number)`، وقيدُ `amount > 0`. **لا تُعدَّل ولا تُحذف**: لا `PUT`/`PATCH`/`DELETE` |
| `FeeReceiptSequence` (#283) | `year`, `last_number` (default 0) | `tenant` FK، فرادةٌ على `(tenant, year)`. **أداةُ القفل والترقيم**: `select_for_update` ثم زيادةُ `last_number` داخل `transaction.atomic`، والرقمُ يُنسخ إلى `FeePayment.receipt_number` بصيغة `{year}-{n:05d}`. **لا `MAX+1` ولا `count+1`** |
| `FeePaymentAllocation` (#283) | `amount` (Decimal، `AMOUNT_KEYS`) | `tenant` FK، و`payment` على `CASCADE` (`related_name="allocations"`)، و`draft` على **`PROTECT`** (`related_name="allocations"`). فرادةٌ على `(payment, draft)` وقيدُ `amount > 0`. **وعليه تُبنى `remaining`** — لا عمودَ لها في المسودّة |
| `FeeWriteOff` (#283) | `amount` (Decimal، `AMOUNT_KEYS`)، `reason` (300، **إلزاميٌّ غيرُ فارغ** يفرضه `payments.write_off_fee_draft`)، `created_by`، `created_at` | `tenant` FK و`draft` على `PROTECT` (`related_name="write_offs"`)، وقيدُ `amount > 0`. **سطرٌ إلحاقيٌّ**: يخفّض `remaining` ولا يمحو دفعةً ولا مسودّة، وصلاحيتُه لصاحب المكتب وحده |
| `BookEntryLine` (#286) | `debit`, `credit`, `side_party` | `entry` على `CASCADE` و`account` على `PROTECT`، و`tenant` يُملأ من الحركة (`_fill_tenant_from_entry` — النموذجُ لا زبونَ له مباشرةً). `debit`/`credit` مسجَّلان في `AMOUNT_KEYS` (`BOOK_ENTRY_AMOUNT_KEYS`) ويُقنَّعان كسائر مبالغ الموديول |

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
resolve_settings_for_clients(tenant, keys, clients)           # مفاتيحُ مجموعةٍ لزبائنَ في استعلامين — بحارسي المحلّل
set_office_setting(tenant, key, value)                        # يتحقّق ثم يكتب
reset_office_setting(tenant, key)                             # «ارجع للافتراضي» = حذف (ويُرفض لمن لا افتراضي له، ولمسحٍ يقلب نافذة الإرسال)
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
stop_client_service(client_service, *, ends_on, last_period_ours=True)
apply_package(client, package, *, actor=None, today=None)     # نسخٌ لا ربط
overlapping_client_service(client, service, starts_on)         # قاعدةُ التداخل الوحيدة
service_or_raise(tenant, pk) / package_or_raise(tenant, pk)    # حلُّ الكائن ورسالتُه واحدة
suggest_frequency(client, service_code, on_date=None)         # (frequency | None, reason)
suggestion_payload(client, service, *, on_date=None)
# ── لائحة المواعيد والتقويم (#274) ──
schedule_for(tax_system, year)                                # (النسخة السارية | None, تقديريّ؟)
ThresholdContext(tax_system, day, cache=…)                    # سياقُ السقوف بمُذكِّرةٍ مشتركة
rule_applies(rule, card, thresholds_ctx, *, payroll_obligations=None)  # الشروطُ من اللائحة لا من الكود + إعدادُ بنود الرواتب (#279)
CalendarContext / calendar_context(tenant, clients)           # سياقُ الطلب: إعداداتٌ جماعية، نسخٌ، سقوف
client_deadlines(client, *, start, end, context=None)         # مواعيدُ زبونٍ محسوبةً لا محفوظة
client_services_of(client, context=None) / _periods_for_service(…)
calendar_row(item) / calendar_payload(tenant, *, user, start, end, …)
deadline_rules_payload(tax_system)                            # أسطرُ النسخة السارية لكل سنة
# ── الالتزامات والشغلات ومحرّك «حدّث المكتب» (#275) ──
_deadline_items(client, *, floor, end, context)               # المولّدُ الواحد: (الزبون، خدمة الزبون، السطر، النتيجة)
last_period_of_stream(periods, *, ends_on)                    # «آخرُ فترةٍ في سلسلة» — نقيّةٌ بلا قاعدة
refresh_office(tenant, *, day)                                # يحفظ ما حان وقته؛ يُرجع ما أنشأه هذا النداء
ensure_office_refreshed(tenant, *, day)                       # مرّةٌ في اليوم: لِيومٍ له سجلٌّ لا عمل
submit_obligation(obligation, *, actor, submitted_on=None, number="")   # انقدّم — نهائيٌّ
mark_obligation_not_required(obligation, *, actor) / reopen_obligation(obligation, *, actor)
set_obligation_amount(obligation, *, amount, direction)       # يُقفل عند «انقدّم»
set_obligation_client_paid(obligation, *, paid)               # في كلّ الحالات
close_prior_obligations(client, *, before, actor)             # «هدول انقدّموا قبل ما يجي علينا» → عدد
assign_task(task, *, assignee)                                # عضوٌ من المكتب، أو None للوراثة
obligation_row(obligation, *, day, masked=False) / task_row(task, *, obligations=None)
today_payload(tenant, *, user, day, filter="")                # صفوفٌ وعدّاداتٌ قبل الفلتر
client_obligations_payload(client, *, user, day)              # شغلاتُ الزبون بكلّ التزاماتها
obligation_direction_choices()                                # تسمياتُ «عليه/إله» من الخادم
# ── الدرجتان والتنبيهات والجرس (#276) ──
LATE_INTERNAL_ALERT_KEY / LATE_OFFICIAL_ALERT_KEY             # مفتاحا الإعدادين
MANAGER_ROLE                                                  # «صاحب المكتب» = `manager` — مستورَدٌ من `core/access.py`
_office_owner_ids(tenant)                                     # أعضاءُ المكتب النشطون بذلك الدور
_alert_recipient_ids(choice, *, assignee_id, owners)          # المستلِمون من الاختيار — بلا تكرار
_generate_late_alerts(tenant, *, day)                         # داخل `refresh_office`؛ يُرجع ما أنشأه النداء
alerts_payload(tenant, *, user, day=None, limit=50)            # {"unseen": n, "rows": [...]} — تنبيهاتُه وحده بلا المحسوم
alert_row(alert)                                              # سطرُ الجرس — بلا مبلغ، و`opens` وجهتُه
mark_alert_seen(alert, *, user) / mark_all_alerts_seen(tenant, *, user, day=None) -> int
# ── تعديل المكتب والتمديد والتزامات المكتب والأحداث (#277) ──
active_rule_overrides(tenant)                                 # الساري: أحدثُ صفٍّ لكل (نظام، كود) وغيرُ مُرجَع
custom_rules_payload(tenant)                                  # قائمةُ التزامات المكتب باختياراتها — قراءةٌ لا تزرع
_deadline_result(client, *, …, rule=, custom_rule=, override=)  # **مدخلاتُ المحرّك الوحيدة**: المولّد وإعادةُ الحساب
_recompute_obligations(obligations, *, context, reason, actor=None)   # دفعةٌ واحدة؛ يُرجع ما تغيّر
set_rule_override(tenant, *, tax_system, rule_code, rule_day=, rule_month=, electronic_extension_days=, note=, actor)
clear_rule_override(tenant, *, tax_system, rule_code, actor)  # «رجّع للمنصة»: صفٌّ cleared لا حذف
keep_rule_override(tenant, *, tax_system, rule_code, actor)   # «أُبقي تاريخي»: لقطةٌ من النسخة السارية
_apply_platform_updates(tenant, *, day, context)              # نسخةٌ أحدث ⇒ نقلُ غير المقدَّم وإعادةُ حسابه
_generate_schedule_alerts(tenant, *, day, context, schedule_changes=None)  # تنبيهُ اللائحة لأصحاب المكتب
extend_obligation(obligation, *, until, note, actor)          # pending وحده؛ وبعد الفعليّ؛ بملاحظة
clear_obligation_extension(obligation, *, actor)              # يرجع إلى الفعليّ بصفٍّ extension_cleared
create_custom_rule(tenant, *, name, service, cadence, rule_kind, rule_day=, rule_month=, is_active=True, actor, day=None)  # يولّد المستحقَّ لزبائن الخدمة فوراً
update_custom_rule(row, *, name=, service=, cadence=, rule_kind=, rule_day=, rule_month=, is_active=, actor, day=None)  # يولّد عند تبدّل الخدمة/الدورية/التفعيل
enabled_event_kinds(tenant)                                   # الأنواعُ المفعّلة بتسمياتها
record_client_event(client, *, kind, occurred_on, note="", actor)     # (الحدث, التزاماتُه)
client_events_payload(client, *, user) / client_event_row(event, *, client, user)
deadline_rules_payload(tax_system, *, tenant=None)            # + rule_code/platform/override/history/awaiting_decision
# ── قائمة الأوراق وشبكة الأشهر (#278) ──
DOCUMENT_STATUS_* / DOCUMENT_CHANNEL_*                        # ثوابتُ الحالات الأربع والقنوات الثلاث (و`*_LABELS` من الخادم)
document_status_label(status, cadence)                        # «مش لازمة هالشهر» أو «مش لازمة هالسنة»
document_status_choices() / document_channel_choices() / document_cadence_choices()
_document_items_for(client, *, cadence, period_start, period_end, context=None, skip=None)  # **الدالّةُ الواحدة** للبنود الفعّالة
_generate_document_rows(client, *, tenant, service_rows, end, context, skip)     # داخل `_refresh_client`
set_document_status(row, *, status, channel="", actor, day=None)   # القناةُ إلزامية لـ«وصلت»، والتراجعُ يمحوها
validate_document_size(*, size) / validate_document_upload(*, size, filename, content_type, head)  # الحجمُ قبل القراءة، والحكمُ للبايتات لا للاسم
create_document_file(row, *, file_url, file_name="", data=None, actor) / delete_document_file(file)
document_file_payload(file) / document_row_payload(row, *, files=None)
client_documents_payload(client, *, year)                     # months · items[].cells · annual · retention · choices
document_progress(tenant, obligations)                        # {pk: {received, required, missing}} — استعلامان مقيَّدان بمدى الالتزامات
document_retention_payload(client) / document_item_system(tenant, code)
document_items_payload(tenant, *, tax_system, client=None)    # قالبُ المكتب (+ `client_included` للزبون، وبنودُ المكتب الفعّالةُ وحدها معه)
set_office_document_choice(tenant, *, item_code, included, actor)
set_client_document_choice(client, *, item_code, included, actor)
create_office_document_item(...) / update_office_document_item(row, *, name=, cadence=, service_codes=, is_active=)
# ── الرواتب — متابعةُ الاستحقاق (#279) ──
PAYROLL_OBLIGATIONS_KEY / PAYROLL_FREQUENCY_ERROR / PAYROLL_FREQUENCIES   # مفتاحُ الإعداد، ورسالةُ الرفض، والمقبولتان
_assert_payroll_frequency(service_code, frequency)            # «شهرية أو كل شهرين» — النقطةُ الواحدة لمسارَي الكتابة
# ── التذكيرات والرسائل (#280) ──
REMINDER_DEFAULT_TEXTS / REMINDER_PLACEHOLDERS                # نصوصُ المنصّة (عربيٌّ وعبريٌّ لكل نوع) ورموزُها الستّة
REMINDER_TYPE_* / REMINDER_KIND_* / REMINDER_CHANNEL_*        # ثوابتُ الأنواع والأربعة الصادرة والقنوات (و`*_LABELS` من الخادم)
set_contact_consent(contact, *, consent, types=None, channel="", actor, day=None)   # الإذنُ والسحبُ بتاريخيهما
contact_consent_payload(contact) / create_contact(tenant, *, name, phone="", language="ar")
render_reminder_body(body, values)                           # استبدالٌ بـ`str.replace` لا `str.format` — نصُّ المستخدم لا يُسقِط الطلب
validate_reminder_body(body)                                  # رمزٌ مجهول ⇒ 400 يسمّيه
reminder_template_bodies(tenant, reminder_type)
reminder_templates_payload(tenant) / set_reminder_template(...) / reset_reminder_template(...)
_reminder_candidates(tenant, clients, *, day, settings_by_client, reminder_type=None)   # **الحسابُ الواحد**: المستحقُّ لكل (زبون، نوع، فترة)
ready_to_send_payload(tenant, *, user, day, reminder_type=None, assignee=None)   # رسالةٌ لكل شخصٍ في اليوم
mark_reminders_sent(...) / mark_reminders_manual(...) / dismiss_reminders(...)   # صفوفُ السجلّ الثلاثة
postpone_reminder(...) / undo_reminder_log(row, *, actor) / office_is_on_holiday(tenant, day)
visible_reminder_logs(tenant, user) / reminder_log_payload(...) / client_reminder_log_payload(client) / reminder_log_row(row)
reminder_postpone_row(row) / office_holiday_row(row) / day_key_blocked(day, rest_days)
_generate_reminder_alerts(tenant, *, day)                    # داخل `refresh_office`؛ التصعيدُ بعد الحدّ
# ── دفتر الزبون (#286) ──
bookkeeping_service_on(client, day)                           # وجودُ الدفتر من `status_on` القائمة — لا قاعدةَ ثانية
book_is_writable(book, day=None) / assert_book_writable(book, day=None)  # القراءةُ بعد الإيقاف تبقى، والكتابةُ 400
writable_client_ids(tenant, clients, day)                     # استعلامٌ واحد لقائمةِ دفاتر — لا نداءٌ لكل صفّ
books_payload(tenant, user, *, day=None) / book_row(book, *, writable, entry_method)
book_kind_choices() / entry_kind_choices() / account_type_choices() / choices_payload()   # تسمياتُ الأنواع الثلاثة — `client-books/choices/`
accounts_payload(client) / account_row(row)
add_account(client, *, code, name, parent_code="", account_type)   # حسابٌ يضيفه المكتب: `is_system=False`
create_book(tenant, client, *, kind, opened_on=None, day=None)
ensure_client_tree(client, kind)                              # نسخةُ الشجرة الواحدة — **لا مرجعَ حيّ**
entries_payload(book, *, year=None, user) / entry_row(entry, *, masked)   # **القناعُ قرارٌ جاهزٌ** يُحسب مرّةً في القائمة لا لكل صفّ
amounts_masked(tenant, user)                                  # قرارُ قناع المبالغ — **مرّةً واحدة** (N+1 سابقاً)
kind_on(book, day)                                            # نوعُ الدفتر **في تاريخ الحركة** لا نوع اليوم
sync_client_tree(client, kind)                                # يُكمل شجرة النوع الجديد عند الانتقال (يضيف ولا ينسخ)
_next_number(client, year)                                    # **القفلُ والترقيم**: لا `MAX+1` ولا `count+1`
create_entry(book, *, entry_date, kind, lines, memo="", documents=None, reverses=None, actor=None, day=None)   # `documents` قائمةُ أوراق
reverse_entry(entry, *, memo="", entry_date=None, actor=None, day=None)  # بنودٌ معكوسة، والأصلُ يبقى؛ يقفل الأصلَ قبل فحص «لها عكس»
change_kind(book, kind, *, day=None)                          # بسيط ← مزدوج من بداية سنة؛ والرجوعُ مرفوض
pending_entry_payload(tenant, user, *, day=None)              # «للإدخال»: `Exists` + `TruncMonth` باستعلامٍ واحد
```

**والأتعابُ في `fees.py`** (#282): المصدرُ الواحدُ لسعر الشهر وتناسبه واعتماده:

```python
# ── الأتعاب (#282، الجزء أ١ — في `accounting_office/fees.py`) ──
subscription_on(tenant, client, *, day)                       # أكبرُ `starts_on` لا يتجاوز آخرَ الشهر
generate_fee_drafts(tenant, *, day)                           # `{"created_drafts", "created_alerts"}` — يُنادَى من `refresh_office`
amounts_masked(tenant, user)                                  # قرارُ القناع مرّةً للطلب
subscription_row(row, *, masked) / draft_row(draft, *, masked) / extra_row(row, *, masked)   # القناعُ يطال البنود
subscriptions_payload(tenant, *, user) / drafts_payload(tenant, *, user) / extras_payload(tenant, *, user)
visible_subscriptions(tenant, user) / visible_extras(tenant, user) / visible_drafts(tenant, user)   # العزلُ من `visible_clients`
create_subscription(tenant, client, *, amount, starts_on, cadence=None, currency=None, paused_from=None, paused_to=None, ended_on=None)
create_extra_service(tenant, client, *, service_name, amount, performed_on, draft=None)
set_client_service_price(client_service, *, amount)           # «سعرٌ لكل خدمة» — تُعيد (الصف، أُنشئ؟) لنقطته `fees/service-prices/`
can_approve_fee_drafts(tenant, user)                          # `manager` و`office_manager` وحدهما
approve_fee_draft(draft, *, actor, note="") / approve_all_fee_drafts(tenant, *, actor, note="") / cancel_fee_draft(draft, *, actor)   # `select_for_update`
pending_drafts(tenant)                                        # «كم بقي» بعد «اعتمد الكل»
```

**والدفعاتُ و«اللي عليه» في `payments.py`** (#283): الصيغةُ الواحدةُ والترقيمُ والتخصيص:

```python
# ── الدفعات و«اللي عليه» وكشف الحساب (#283، الجزء أ — في `accounting_office/payments.py`) ──
client_due(tenant, client)                                    # **الدالّةُ الوحيدة**: {due, invoices_total, paid_total, credit, unpaid_count}
client_due_map(tenant, clients) / client_dues_payload(tenant, clients, *, user)   # استعلامان للصفحة، والقناعُ مرّةً
client_due_tax_note(tenant, client)                           # سطرُ العلم: مجموعُ الالتزامات غير المعلَّمة `client_paid` — **لا يدخل `due`**
client_due_payload(tenant, client, *, user)                   # الحمولةُ المفردة: `due` وسطرُ العلم معاً
invoice_summary(draft) / invoice_summaries(drafts)            # {paid_amount, written_amount, remaining, state, state_label}
invoice_state(total, remaining)                               # `paid` | `partial` | `unpaid` — من المتبقّي لا من عمود
with_invoice_totals(queryset) / with_payment_credit(queryset)  # تعليقُ `remaining`/`credit` باستعلامٍ فرعيٍّ لكل علاقة
next_receipt_number(tenant, *, year)                          # `{year}-{n:05d}` من عدّادٍ مقفول — لا `MAX+1`
create_payment(tenant, client, *, amount, method, paid_at, note="", actor=None, allocations=None)
apply_open_credit(tenant, clients)                            # يُنادَى عند الاعتماد: رصيدٌ دائن ⇒ تخصيصٌ جديد
write_off_fee_draft(draft, *, amount, reason, actor)           # صاحبُ المكتب وحده، وسببٌ مكتوب، وقفلٌ على المسودّة
can_write_off(tenant, user)                                   # `MANAGER_ROLE` وحده لا `OFFICE_MANAGER_ROLE`
visible_payments(tenant, user) / filter_payments(queryset, params)   # العزلُ من `visible_clients`، والفلاترُ في الاستعلام
payments_payload(tenant, *, user, queryset=None) / payment_row(payment, *, masked, due=None)
allocation_row(allocation, *, masked) / write_off_row(write_off, *, masked)
ledger_payload(tenant, *, user, params)                       # كشفُ الحساب: فلترةٌ وترقيمٌ في الاستعلام
amounts_masked(tenant, user)                                  # نفسُ `fees.amounts_masked` لا نسخةً ثانية
```

`deadlines.py` وحدها تقرأ حسابَ الأشهر: `add_months(day, months)` (مقيَّدةٌ بآخر
الشهر لأفق التقويم) و`month_start_after(day, months)` (أولُ الشهر)، و
`service_periods(frequency_of_month, start, end)` (ثلاثيات `(بداية, نهاية, دورية)`).
و`services` و`views` تستوردانها
ولا نسخةَ ثانية لها.

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
| `GET` | `calendar/?from=&to=&client=&member=&rule=` | `OfficeCalendarViewSet` (`list`) — **قراءةٌ خالصة، لا تحفظ سطراً** |
| `GET` | `deadline-rules/?system=PS\|IL` | `OfficeDeadlineRuleViewSet` (`list`) — أسطرُ اللائحة السارية، ولكل سطرٍ `rule_code` و`platform` و`override` و`history` و`awaiting_decision` (#277) |
| `POST` | `deadline-rules/override/` | `OfficeDeadlineRuleViewSet` (`override`) — **`office.settings.manage`**؛ `{system, code, rule_day?, rule_month?, electronic_extension_days?, note}` → `{override, changed_obligations}` |
| `POST` | `deadline-rules/clear-override/` · `keep-override/` | `OfficeDeadlineRuleViewSet` (`clear_override`, `keep_override`) — «تأخذ الجديد» / «أُبقي تاريخي»، وكلاهما صفٌّ جديد |
| `GET/POST` | `custom-rules/` | `OfficeCustomRuleViewSet` (`list`, `create`) — الالتزاماتُ الخاصة: **قراءةً وكتابةً بمفتاح `office.settings.manage`** |
| `PATCH` | `custom-rules/<id>/` | `OfficeCustomRuleViewSet` (`partial_update`) — الاسمُ والأيامُ والتفعيل. **لا `DELETE`** (405) |
| `GET` | `today/?filter=mine\|week\|late\|late_internal\|missing_docs` | `OfficeTodayViewSet` (`list`) — **يُشغّل التحديثَ اليوميّ أوّلاً** ثم يقرأ |
| `POST` | `obligations/<id>/submit/` | `OfficeObligationViewSet` (`submit`) — «انقدّم» بتاريخٍ ورقمٍ اختياريّين |
| `POST` | `obligations/<id>/not-required/` · `reopen/` | `OfficeObligationViewSet` (`not_required`, `reopen`) |
| `POST` | `obligations/<id>/amount/` | `OfficeObligationViewSet` (`amount`) — **مفتاحان**: الكتابة ورؤية المبالغ |
| `POST` | `obligations/<id>/client-paid/` | `OfficeObligationViewSet` (`client_paid`) — في كلّ الحالات |
| `POST` | `obligations/<id>/extend/` · `clear-extension/` | `OfficeObligationViewSet` (`extend`, `clear_extension`) — «مدّد» بتاريخٍ وملاحظة / «ألغِ التمديد» (#277) |
| `POST` | `tasks/<id>/assign/` | `OfficeTaskViewSet` (`assign`) — `{"assignee": <id> \| null}` |
| `GET` | `clients/<pk>/obligations/` | `OfficeClientViewSet` (`client_obligations`) — الشغلاتُ بكلّ التزاماتها |
| `POST` | `clients/<pk>/obligations/close-prior/` | `OfficeClientViewSet` (`close_prior`) — `{"before"?}` → `{"closed": n}` |
| `GET/POST` | `clients/<pk>/events/` | `OfficeClientViewSet` (`events`) — «صار حدث»: `GET` الأحداثُ والأنواعُ المفعّلة، و`POST` `{kind, occurred_on, note?}` ⇒ `{event, obligations}` (#277) |
| `GET` | `alerts/` | `OfficeAlertsViewSet` (`list`) — تنبيهاتُ العضو نفسه، المحسومُ مستبعَدٌ عند القراءة → `{"unseen": n, "rows": [...]}` |
| `POST` | `alerts/<id>/seen/` | `OfficeAlertsViewSet` (`seen`) — **تنبيهُ غيرك 404**، ويُرجع السطرَ المحدَّث |
| `POST` | `alerts/seen-all/` | `OfficeAlertsViewSet` (`seen_all`) — `{"seen": n}` |
| `GET` | `clients/<pk>/documents/?year=YYYY` | `OfficeClientViewSet` (`client_documents`) — **قراءةٌ خالصة**: أشهرٌ وبنودٌ وخاناتٌ (كلُّ صفٍّ بعدد الأشهر) والقائمةُ السنويةُ ومددُ الحفظ (#278) |
| `POST` | `clients/<pk>/document-choice/` | `OfficeClientViewSet` (`document_choice`) — `{item_code, included}` بمفتاح `office.clients.write`؛ يغلب قالبَ المكتب |
| `POST` | `documents/<row_id>/status/` | `OfficeDocumentViewSet` (`document_status`) — `{status, channel?}`؛ «وصلت» بلا قناة 400 |
| `GET/POST` | `documents/<row_id>/files/` | `OfficeDocumentViewSet` (`files`) — ملفاتُ الورقة، ورفعٌ multipart بحقول נספח ז |
| `GET` | `document-files/<id>/download/` | `OfficeDocumentFileViewSet` (`download`) — بايتاتٌ لا تحويل، ورابطُ التخزين لا يخرج |
| `DELETE` | `document-files/<id>/` | `OfficeDocumentFileViewSet` (`destroy`) — يحذف الصفَّ ثم الأصلَ من التخزين، **والحالةُ لا تتغيّر** |
| `GET` | `document-items/?system=PS\|IL&client=<id>?` | `OfficeDocumentItemViewSet` (`list`) — بنداتُ المنصّة وقائمةُ المكتب بـ`included` (و`client_included` مع زبون، و`id` فضاءُ بنود المكتب وحده — بندُ المنصّة `null`) |
| `POST` | `document-items/choice/` | `OfficeDocumentItemViewSet` (`choice`) — «ضمن القائمة» لبندِ منصّةٍ بمفتاح `office.settings.manage`؛ وبندُ المكتب `office_doc_*` **مرفوض** (يُفعَّل ويُعطَّل من قائمته) |
| `POST` | `document-items/` | `OfficeDocumentItemViewSet` (`create`) — بندٌ يضيفه المكتب (اسم، دورية، خدمات، تفعيل) |
| `PATCH` | `document-items/<id>/` | `OfficeDocumentItemViewSet` (`partial_update`) — **لا `DELETE`**: التعطيلُ (`is_active=false`) هو الفعل |
| `GET/POST` | `contacts/<id>/consent/` | `OfficeContactViewSet` (`consent`) — `{consent, types?, channel?}` بمفتاح `office.clients.write`؛ الرموزُ والقنواتُ تُتحقَّق في الخدمة (#280) |
| `GET` | `ready-to-send/?day=&reminder_type=&assignee=` | `OfficeReadyToSendViewSet` (`list`) — **قراءةٌ خالصة**: رسالةٌ لكل شخصٍ في اليوم، بنصٍّ بلغته (#280) |
| `POST` | `ready-to-send/sent/` · `manual/` · `dismiss/` · `postpone/` | `OfficeReadyToSendViewSet` — `{contact_id, body, channel?, items:[{client_id, reminder_type, period_start, period_end}]}` (**الطرفان معاً**: مفتاحُ الفترة تاريخان)؛ «كلّمناه» `phone`/`in_person` وحدهما، و«أجّل» `until` بعد اليوم |
| `GET` | `reminder-log/` | `OfficeReminderLogViewSet` (`list`) — الأحدثُ أوّلاً، **لا تعديلَ ولا حذف** (405) |
| `GET` | `reminder-log/<id>/` | `OfficeReminderLogViewSet` (`retrieve`) — **به يوجد مسارُ التفصيل**، وبه يأخذ `PUT`/`PATCH`/`DELETE` حكمَ 405 لا 404 |
| `POST` | `reminder-log/<id>/undo/` | `OfficeReminderLogViewSet` (`undo`) — صفُّ `undo` يشير إلى ما يُبطله؛ وإبطالُ `undo` 400 |
| `GET` | `clients/<pk>/reminder-log/` | `OfficeClientViewSet` (`reminder_log`) — سجلُّ الزبون لتبويب ملفّه (#280). **`clients/<pk>/reminders/` مسارٌ آخر**: مستلِمو الأنواع منذ #271 |
| `GET` | `reminder-templates/` | `OfficeReminderTemplateViewSet` (`list`) — كلُّ نوعٍ في لغتيه: الفعليُّ والافتراضيُّ وعلمُ التخصيص |
| `PUT/DELETE` | `reminder-templates/<type>/<lang>/` | `OfficeReminderTemplateViewSet` (`template`) — **`office.settings.manage`**؛ `DELETE` = «ارجع للافتراضي» |
| `GET/POST` | `office-holidays/` | `OfficeHolidayViewSet` (`list`, `create`) — القراءةُ لكل عضو والكتابةُ بمفتاح الإعدادات |
| `DELETE` | `office-holidays/<id>/` | `OfficeHolidayViewSet` (`destroy`) — بمفتاح الإعدادات |
| `GET/POST` | `client-books/` | `OfficeClientBookViewSet` (`list`, `create`) — الدفاترُ التي يراها العضو، وإنشاءُ دفترٍ لزبونٍ بلا دفتر (#286) |
| `GET` | `client-books/<client_id>/` | `OfficeClientBookViewSet` (`retrieve`) — **بمعرّف الزبون** كسائر مساراته؛ ووجودُه شرطُ 405 على `DELETE`/`PATCH` |
| `GET` | `client-books/choices/` | `OfficeClientBookViewSet` (`choices`) — `{book_kinds, entry_kinds, account_types}` بتسميات النموذج، قراءةً بلا مفتاح كتابة |
| `GET/POST` | `client-books/<client_id>/accounts/` | `OfficeClientBookViewSet` (`accounts`) — شجرةُ الحساب مسطّحةً بـ`parent_code`، وإضافةُ حسابٍ خاصّ بالزبون |
| `GET/POST` | `client-books/<client_id>/entries/?year=YYYY` | `OfficeClientBookViewSet` (`entries`) — الحركاتُ مرقَّمةً ببنودها، والإدخالُ (متوازنٌ في المزدوج) بحمولة `documents` قائمةً |
| `GET` | `client-books/<client_id>/entries/<id>/` | `OfficeClientBookViewSet` (`entry`) — حركةٌ واحدة، **قراءةً فقط**: `PUT`/`PATCH`/`DELETE` عليها 405 |
| `POST` | `client-books/<client_id>/entries/<id>/reverse/` | `OfficeClientBookViewSet` (`reverse`) — حركةٌ عكسية؛ عكسُ العكس وثاني عكسٍ 400 |
| `GET` | `client-books/pending-entry/` | `OfficeClientBookViewSet` (`pending_entry`) — «للإدخال»: أوراقٌ واصلةٌ بلا حركةٍ حيّة، بالزبون والشهر، **وللدفاتر القابلة للكتابة وحدها** |
| `POST` | `client-books/<client_id>/kind/` | `OfficeClientBookViewSet` (`kind`) — تغييرُ النوع (بسيط ← مزدوج من بداية سنة، د7) **ويُكمل الشجرة** |
| `GET/POST` | `fees/subscriptions/` | `OfficeFeeSubscriptionViewSet` (`list`, `create`) — الاشتراكاتُ التي يراها العضو؛ والإضافةُ سعرٌ **بتاريخ سريانه** (`office.clients.write` + `office.amounts.view`)، والتاريخُ المكرَّر 400 |
| `GET` | `fees/drafts/` | `OfficeFeeDraftViewSet` (`list`) — المسودّاتُ ببنودها ومصادرها، ومبالغُها `null` بلا `office.amounts.view`؛ **ولا `POST`** (التوليدُ في «حدّث المكتب») |
| `POST` | `fees/drafts/<id>/approve/` | `OfficeFeeDraftViewSet` (`approve`) — `manager`/`office_manager` وحدهما (403 لغيرهما)، وملاحظةٌ اختيارية؛ ومن حالةٍ غير «مسودّة» 400 |
| `POST` | `fees/drafts/approve-all/` | `OfficeFeeDraftViewSet` (`approve_all`) — كلُّ منتظرةٍ في المكتب، والردُّ `{approved, remaining, drafts}` |
| `POST` | `fees/drafts/<id>/cancel/` | `OfficeFeeDraftViewSet` (`cancel`) — قبل الاعتماد وحده؛ وبعده 400 (إبطالُ المعتمدة إجراءُ أ٢) |
| `GET/POST` | `fees/extras/` | `OfficeFeeExtraServiceViewSet` (`list`, `create`) — الخدماتُ الإضافيةُ ووجهتُها `next_month`/`standalone`، بسعرها وتاريخ تنفيذها، وبمعرّف المسودّة التي فوترتها (`billed_draft`) |
| `GET/POST` | `fees/service-prices/` | `OfficeFeeServicePriceViewSet` (`list`, `create`) — أسعارُ خدمات الزبائن لطريقة «سعرٌ لكل خدمة»: `POST` بمعرّف `client_service` أو بالخدمة والزبون، والمبلغُ بمفتاح `office.amounts.view` (403 لغيره)، والقناعُ على القراءة، وإعادةُ `POST` تُحدِّث الصفَّ الواحد |
| `GET/POST` | `fees/payments/?client=&method=&date_from=&date_to=` | `OfficeFeePaymentViewSet` (`list`, `create`) — الدفعاتُ بفلاترها في الاستعلام، والإنشاءُ يُخصّص **الأقدمَ أوّلَاً** أو بتخصيصٍ صريح `allocations: [{draft, amount}]`؛ ولا تعديلَ ولا حذف (405)، ولا مسارَ تفصيل (404) (#283) |
| `POST` | `fees/drafts/<id>/write-off/` | `OfficeFeeDraftViewSet` (`write_off`) — `{amount, reason}`؛ **صاحبُ المكتب وحده** (403 لمدير المكتب والمحاسب)، وسببٌ فارغٌ أو مبلغٌ فوق المتبقّي 400 (#283) |
| `GET` | `fees/ledger/?client=&state=&q=&page=&page_size=` | `OfficeFeeLedgerViewSet` (`list`) — كشفُ الحساب: `{invoices, payments, client_due}`، كلُّ مجموعةٍ `{count, page, page_size, results}`؛ الفواتيرُ المعتمدةُ بـ`paid_amount`/`remaining`/`state` (`paid\|partial\|unpaid`)، والفلترةُ والترقيمُ في الاستعلام (#283) |

**ولا `DELETE` في أيّ نقطةٍ من `fees/`** — `http_method_names` تُغلق الطريقة (405)،
كما لا `PUT`/`PATCH`: تغييرُ السعر صفٌّ جديد، وتغييرُ المسودّة اعتمادٌ أو إلغاء.

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
| `office.amounts.view` | «يرى المبالغ» — بدونه كلُّ مبلغٍ في الردّ `null` وكتابتُه 403، **عدا نصَّ رسالة التذكير** (و`body` في سجلّه) فيحمل مبلغَ الفترة: الرسالةُ موجَّهةٌ إلى الزبون نفسه عن مبلغٍ عليه (#281، انظر قسم المواعيد) |
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
صفٍّ له `ends_on`؛ وفي نموذجه خانةُ **«آخر فترة علينا»** مُعلَّمةً دائماً عند الفتح،
ورفعُ العلامة يُرسل `last_period_ours: false` ويُضيف جملةً إلى التأكيد، ويُظهر
كلُّ صفٍّ له `ends_on` و`last_period_ours` خاطئ «آخر فترة مش علينا» — ومنه إيقافٌ مستقبليّ حالتُه ما زالت «نشطة»)، و«أضف خدمة» يسأل «من أيّ فترةٍ المكتب مسؤول؟» بحقل شهرٍ
(`input[type=month]` يُرسَل `<شهر>-01`) ويعرض المقترحَ وسببَه لتأكيده أو تغييره،
و«طبّق باقة» (ونتيجتُه بلا إضافةٍ تنبيهٌ معلوماتيّ لا خطأ). وردُّ اقتراحٍ قديم لا
يكتب فوق أحدث (عدّادُ طلبات). ومجموعةُ «الخدمات والباقات» في الإعدادات: الكتالوج
(تفعيل، إضافة، إعادة تسمية) والباقات (اسم، خدمات، سعر مقترح يُعرض «—» لمن لا يرى
المبالغ)، ومحرّرُ الباقة يعرض المفعّلةَ وحدها **وما اختِير سابقاً وهو معطَّل**
معلَّماً «معطّلة»، وحالتُها تحميلٌ وخطأٌ بزرّ «أعد المحاولة». والأزرارُ لمن يملك
المفتاح، والخادمُ هو الحكم.

## لائحة المواعيد والمحرّك والتقويم (#274)

**اللائحةُ بياناتُ منصّةٍ بلا `tenant`** — كـ`TaxThreshold`: الموعدُ واحدٌ لكل
المكاتب، ونسخةٌ لكل شركة تعني موعدين لنفس القانون في منصّةٍ واحدة. ولكل نظامٍ
وسنةٍ **نسخةٌ مؤرَّخة** (`DeadlineSchedule`) بمصدرها (`source_url`) وتاريخ نشرها،
وفيها **سطرٌ لكل نوع التزام** (`DeadlineRule`): قاعدتُه، والخدمةُ التي يولّده،
وشروطُه على البطاقة، وعلامةُ «لا يُولَّد» (`is_generated=False` — الضمانُ
الاجتماعي الفلسطيني الموقوف بقرار 4/2019)، و`electronic_extension_days`،
و`period_overrides` لتأجيلات النشرة، و`needs_review` لقيمةٍ لم يُثبتها البحث.

**النسخةُ السارية لسنةٍ = أكبر `version`**، ولا تُعدَّل نسخةٌ نُشرت: التصحيحُ يُضاف
بنسخةٍ أعلى. وسنةٌ بلا نسخةٍ (2028 اليوم) تأخذ نسخةَ آخر سنةٍ سابقة وتُعلَن
**«تقديرية»**، **فتُتجاهل كلُّ تعديلاتها المنشورة** لأنها لسنةٍ أخرى. ولا نسخةَ
أصلاً ⇒ لا التزامات.

**المحرّكُ دالّةٌ نقيّة** في `accounting_office/deadlines.py`:
`compute_deadline(rule, *, period_start, period_end, estimated, client_rest_days,
office_rest_days, filing_method, internal_lead_days, schedule_policy,
authority_closed_days) -> DeadlineResult`. بلا استعلامٍ وبلا ساعة، وتأخذ كائناتٍ
جاهزة (أسطرٌ غيرُ محفوظة تكفي)، فتُختبَر بثوانٍ.

**الترتيبُ أربعة لا يُقدَّم أحدُها:**

1. **`legal_date` — التاريخُ بالقاعدة وحدها:** `day_of_next_month` = اليومُ
   `rule_day` من الشهر التالي لنهاية الفترة، و`end_of_period` = نهايةُ الفترة،
   و`month_day_next_year` = (`period_end.year + 1`, `rule_month`, `rule_day`).
2. **`official_date` — سياسةُ النسخة:** تعديلٌ منشورٌ في `period_overrides` ليس
   سببه يومَ الراحة وحده ⇒ يُؤخذ كما هو. وإلا فـ**`warn`** (فلسطين): التاريخُ
   يبقى بلا زحزحة، **وإن وقع في يوم إغلاق السلطة أُضيف تنبيه** «الموعد يوم
   <اليوم> — قدّم قبل» — لا نصَّ رسميّاً يؤجّله. و**`postpone_client`** (إسرائيل):
   يُقدَّم يوماً بيوم فوق أيام راحة **الزبون** وأيام إغلاق السلطة، و`postponed`
   صحيحٌ إن تحرّك. فالموعدُ المحسوبُ يعتمد على دين المكلَّف لا على إعداد المكتب.
3. **`actual_deadline` = `official_date` + `electronic_extension_days`** حين تكون
   طريقةُ التقديم إلكترونية، وإلا الرسميُّ نفسه — **ولا زحزحةَ بعده**: الأبكرُ
   أحوط، فالتأجيلُ الزائد يخالف «الموعد الأخير».
4. **`internal_deadline` = `actual_deadline` − أيام الإعداد**، ثم رجوعٌ يوماً
   بيوم ما دام اليومُ في **عطلة المكتب** — فالموعدُ الداخليُّ يومُ عملٍ دائماً.

**أيامُ الإعداد بحسب الدورية** إعداداتٌ في مجموعة **`GROUP_SCHEDULE`** («الضريبة
ولائحة المواعيد»): `internal_lead_days_monthly` (5، وتأخذها «كل شهرين» معها)،
و`internal_lead_days_quarterly` (7)، و`internal_lead_days_annual` (30) — بمستويات
مكتب ← زبون ← **شغلة** (المستوى الثالث للشغلة في #275 ولا يُستهلك اليوم)،
و`calendar_months_ahead` (12) للمكتب وحده. وكلُّها أعدادٌ غيرُ سالبة (حدٌّ أدنى في
تعريف الإعداد).

**الخدمةُ × البطاقة = الالتزامات.** `rule_applies(rule, card, thresholds_ctx)` تقرأ
الشروطَ من السطر: `vat_classification_in` و`entity_type_in` يُشترطان في قائمتهما،
و`has_employees`/`is_self_employed` تطابقاً، و`annual_sales_above` تجاوزاً لسقفٍ
منشور (`TaxThreshold` بنوعه، بقاعدة `_threshold_for` نفسها — سنةٌ بلا سقفٍ تأخذ
آخر سابقٍ مع «تقديري»). مثالُ المواصفة: **עוסק פטור مع خدمة ق.م يولّد التصريحَ
السنويّ وحده** ولا يولّد التقريرَ الدوري.

**الفتراتُ قسمان، ولا تخلطان:**

- **سطرٌ بدوريةٍ ثابتة** (`monthly`/`quarterly`/`annual`) يولّد فتراتِ **قاعدته**
  وحدها من `periods_for(cadence, floor, end)` — محاذاةً للتقويم: شهريٌّ كلَّ شهر،
  ورُبعيٌّ أرباعَ السنة، وسنويٌّ السنةَ الميلادية — **مستقلّةً عن دورية خدمة
  الزبون**. فخدمةُ رواتب شهرية لا تُولّد التقريرَ السنوي اثنتَي عشرة مرّةً،
  والرُّبعيُّ لا يصير شهرياً، وتصريحُ المعفى سنويٌّ ولو كانت خدمتُه شهرية.
- **سطرٌ بدورية `service`** (`ps_vat_periodic` و`il_vat_periodic`/`il_vat_detailed`)
  يتبع **دوريةَ خدمة الزبون المؤرَّخة** عبر `service_periods(frequency_of_month,
  start, end)` وتُرجع `(البداية, النهاية, الدورية)`: تُقرأ الدوريةُ عند **آخر يومٍ من
  كل شهر** (فبدايةٌ في 15/2 تُدرك شباط)، وتُوسَم الحزمةُ المحاذيةُ للتقويم التي تحوي
  الشهر. وأولُ فترةٍ تبدأ ببداية حزمتها وما بعدها بالمؤشّر، فالتغييرُ إلى «كل شهرين»
  من نيسان يعطي نيسانَ وحدَه فترةً ثم أيار–حزيران. **وتنتهي الفترةُ بنهاية حزمتها
  إلا إذا تغيّرت الدوريةُ (مقارنةَ النصّ لا الطول) في شهرٍ لاحقٍ داخلها: فتُقطع في
  آخر الشهر الذي قبل التغيير** — كل شهرين حتى آذار ثم شهرية من نيسان تعطي آذارَ وحدَه
  ثم نيسان، وسنويةٌ حتى كانون الثاني ثم شهرية من شباط تعطي كانون الثاني وحدَه ثم كلَّ
  شهر، وشهريةٌ ثم سنويةٌ من نيسان تعطي نيسان–كانون الأول. **بلا فجوةٍ ولا تداخل،
  والنتيجةُ لا تتغيّر ببداية المدى المعروض** لأن الحزم محاذاة.

و`on_demand` لا تولّد فتراتِ خدمة، ولا تُسقط سطراً قاعدتُه ثابتة.

**و`client_deadlines` تربطها بالقاعدة** بلا كتابة: لكل خدمةٍ عند الزبون ولكل
سطرٍ في نسخة **سنة الفترة** يخصّ خدمتها وبدوريتها نفسها، والفترةُ تخصّ المكتب إن
انتهت بعد بدايته وبعد `responsible_from`، ولم تنتهِ بعد `ends_on`. والإعداداتُ
**بالمحلّل وحده وبالزبون**: النظامُ ويومُ راحته وطريقةُ تقديمه وأيامُ إعداده بحسب
دورية الفترة (وهي **الدوريةُ التي قرأها المحرّكُ للفترة** حين تتبع الخدمة، لا
المستنتَجةُ من طولها: نيسان–كانون الأول بعد التحوّل إلى سنوية تأخذ أيامَ السنوية
لا الشهرية)، وأيامُ عطلة المكتب بلا زبون. وسطرٌ شرطُه `annual_sales_above` وسقفُه
مقروءٌ «تقديرياً» (سنةٌ بلا سقفٍ منشور) يحمل في `warnings` «تقديري: سقف <سنة>».
وسياقُ الطلب (`CalendarContext`) يحلّ إعدادَ زبونٍ خارج مجموعته بالمحلّل منفرداً
بدل إعادة `None`. وتُرجع ما
يقع `actual_deadline` له في المدى.

**التقويمُ محسوبٌ لا محفوظ.** `GET calendar/` قراءةٌ خالصة (لا استدعاءَ
لـ`ensure_default_services`: تلك تكتب): الزبائنُ من `visible_clients` وحدها، وفلترةٌ
على الموظف المسؤول، و`rule` على كود السطر. والمدى **≤ 62 يوماً** و`to` لا يتجاوز
`today + calendar_months_ahead` شهراً — وإلا **400** لا تقويمَ مقتطعاً بصمت. وكلُّ
سطرٍ يحمل التواريخَ الأربعة و`estimated` و`postponed` و`warnings` و`expected`
(صحيحٌ دائماً: كلُّ سطرٍ محسوب، وتمييزُ المحفوظ تذكرةٌ لاحقة) و`period_label` — **وبلا أيّ مبلغ**، فلا مسّ لحارس المبالغ.
وتغييرُ سطرٍ في اللائحة يظهر في الطلب التالي فوراً لأن لا شيءَ يُخزَّن.

**الواجهة:** `/accounting-office/calendar` — شهريٌّ (شبكةُ أسابيع تبدأ بالأحد)
وأسبوعيٌّ، وتنقّلٌ سابق/اليوم/تالي، وفلاترُ الموظف (تُخفى في «شخص واحد»
بـ`showsOfficeAssignment`) والزبون والنوع (من `deadline-rules/`). والسطرُ باهتٌ
بوسم «متوقَّع»، و«تقديري» بعلامة، والتنبيهُ بأيقونةٍ ونصّ الخادم، و«راجع» لسطر
`needs_review`، والضغطُ يفتح ملفّ الزبون. والمحتوى يُطلب لمدى العرض وحده، والطلبُ
يُلغى عند تغيّر المدى أو الفلتر، وحالاتُ التحميل والخطأ («أعد المحاولة») والفراغ
من `OfficeUi.tsx`.

## الالتزامات والشغلات ومحرّك «حدّث المكتب» (#275)

**الالتزامُ سطرُ لائحةٍ محفوظٌ لفترة** (`Obligation`)، و**الشغلةُ خدمةُ زبونٍ ×
فترة** (`PeriodTask`) يجمعها موعدُها الداخليُّ الأبكر ومسؤولُها. تُولَّد من
المحرّك نفسه الذي يقرأه التقويم، وتُحفظ مرّةً واحدةً لكل `(خدمة, سطر, نهاية
فترة)` بفرادةٍ غير مشروطة — فالتشغيلُ الثاني لا يضيف صفّاً.

**محرّكٌ واحد، لا نسختان.** `services._deadline_items(client, *, floor, end,
context)` هو المولّدُ الوحيد لكل بند `(الزبون, خدمةُ الزبون, السطر, DeadlineResult)`:

- **التقويم** (`client_deadlines`) يمرّره بأرضية `add_months(start, −24)` ويقصّه على
  `actual_deadline ∈ [start, end]` — سلوكُه كما كان حرفاً.
- **التحديثُ** (`refresh_office`) يمرّره بأرضية `max(starts_on, responsible_from)`
  **بلا سقف 24 شهراً** (فتشغيلٌ متأخّرٌ يلحق كلَّ ما فات، وزبونٌ جديدٌ بفترةٍ ماضيةٍ
  تُولَّد كلُّ فتراتها)، ويقصّه على `period_end < day`.

نسختان من توليد الفترات والقواعد كانتا تفترقان عند أوّل تصحيحٍ في اللائحة:
التقويمُ يرى الجديد والتحديثُ يحفظ القديم. و`CalendarContext` يبقى السياقَ الوحيد
للإعدادات والنسخ والسقوف، فلا N+1.

**«حدّث المكتب ليوم X» `refresh_office(tenant, *, day)`** — **idempotent وبلا
ساعة** (اليومُ يُمرَّر صريحاً دائماً):

- **ما حان وقتُه**: كلُّ التزامٍ `period_end < day` — **ق.م كانون الثاني تظهر في
  1 شباط ولا تظهر في 31 كانون الثاني**، والفترةُ التي تحتوي اليوم لم تنتهِ بعد.
- **والحدُّ الأدنى**: `max(starts_on, responsible_from)` للخدمة، و`_period_is_ours`
  (بدءٌ ومسؤوليةٌ وإيقاف)، و`ended_on` للزبون المنتهي (لا فترةَ تنتهي بعده)،
  و`last_period_ours=False` تُسقط آخر فترةٍ في كل سلسلة.
- **`get_or_create` للشغلة بـ`(client_service, period_start, period_end)` وللالتزام
  بـ`(client_service, rule_code, period_end)`، والصفُّ القائم لا يُحدَّث في التوليد**:
  تواريخُه ما رآه الموظف وأرسله. **والاستثناءُ المحسوم (#277)**: تحديثُ المنصة
  وتعديلُ المكتب يُعيدان حسابَ **غير المقدَّم** وحده (`_recompute_obligations`)،
  ويُسجَّل كلُّ تغيّرٍ في `ObligationDateChange` — و`submitted` لا يُمسّ أبداً.
  والموعدُ الداخليُّ للشغلة **ينخفض** إن انضمّ التزامٌ أبكر، ولا يتأخّر.
- **معاملةٌ لكل زبون**: مكتبٌ بألف زبون لا يُحبَس في معاملةٍ واحدة. والبندُ
  «التقديري» يُحفظ بـ`estimated=True`.
- **والكلفةُ لا تكبر بتاريخ الزبون**: `_refresh_client` يقرأ القائمَ استعلامين
  (شغلاتُ خدمات الزبون في قاموسٍ بمفتاح `(خدمة, بداية, نهاية)`، والتزاماتُها في
  مجموعة مفاتيح `(خدمة, كود السطر, نهاية الفترة)`)، والبندُ الغائب وحده يُنشأ
  بـ`get_or_create`. فمكتبٌ بسنتين تاريخ لا يدفع آلافَ الاستعلامات في خيط الطلب،
  ويحرسه اختبارُ `CaptureQueriesContext` بين مكتبين تاريخُهما 3 فترات و12.
- **ويُسجَّل `OfficeRefreshRun`** لكل (مكتب، يوم) بـ`get_or_create`؛ صفٌّه الواحد هو
  ما يجعل `ensure_office_refreshed` لا تعمل مرّتين. ويُرجع النداءُ **ما أنشأه هو**:
  صفراً في اليوم نفسه، والجديدَ في يومٍ لاحق (والسجلُّ يحمل عدّادَ أوّل تشغيل).
- **`ensure_office_refreshed(tenant, *, day)`** تُنادى عند أوّل فتحٍ لشاشة «اليوم»
  **ولـ`GET alerts/`** (الجرس): ليومٍ له صفٌّ **لا عمل**، وإلا `refresh_office`.
  فيعمل المكتبُ بلا cron، ولا يعتمد الجرسُ على أن يفتح أحدٌ «اليوم».
- **الأمر `refresh_accounting_offices [--day YYYY-MM-DD]`**: الافتراضُ
  `timezone.localdate()`، ويمرّ على الشركات التي `core.modules.module_enabled(tenant,
  "accounting_office")` وحدها، ويطبع سطرَ عدّاداتٍ لكل مكتب
  (**شغلات · التزامات · تنبيهات** — والثالثُ ما أنشأه النداء #276).
  تاريخٌ فاسدٌ ⇒ `CommandError`. **والـcron على الخادم خطوةُ نشرٍ لا كود — ولا
  مُجدوِل في المستودع.**

**الحالاتُ المخزّنة ثلاث، والمشتقّةُ تُقرأ ولا تُخزَّن:**

| المخزّن (`status`) | معناه |
|---|---|
| `pending` | لسا ما انقدّم |
| `submitted` | انقدّم — **نهائيٌّ لا يُتراجَع عنه** |
| `not_required` | مش لازم هالفترة — تُفتح بـ«رجّعها» |

و**المشتقّ** يُحسب من `day` عند القراءة (`services._badge_keys`) — ودرجتاه
وأولويّتُه في §«التأخير بدرجتين والتنبيهات والجرس» (#276). ولا عمودَ له، فعمودٌ
ينام بين تشغيلين يقول «متأخّر» عن يومٍ مضى.

**الأفعال (`services`) وكلُّ كتابةٍ خلف مفتاحها:**

- `submit_obligation(obligation, *, actor, submitted_on=None, number="")`: من
  المنتظِر إلى المُقدَّم، و`submitted_on` افتراضُه اليوم **ولا يكون في المستقبل**،
  ويُكتب `submitted_by` والرقم. **ولكلِّ انتقالٍ حالةٌ واحدةٌ يبدأ منها**:
  «انقدّم» من المنتظِر وحدها (و«مش لازم هالفترة» تُرجَّع أوّلاً)، و«رجّعها» من
  «مش لازم هالفترة» وحدها. وأيُّ انتقالٍ **من** `submitted` ⇒ `ValidationError`
  «انقدّم لا يُتراجَع عنه» (400 من الـAPI)، وغيرُه ⇒ 400 برسالةٍ تقول الطريق.
- `mark_obligation_not_required` / `reopen_obligation`: ذهابٌ وعودة، ولا مسّ
  بـ`submitted`.
- `set_obligation_amount(obligation, *, amount, direction)`: **مقيَّدٌ بالحالة** —
  ممنوعٌ بعد «انقدّم»، فالمبلغُ يُقفل عنده. `amount ≥ 0` أو `None` للمسح،
  و`direction` **مطلوبٌ مع المبلغ** («عليه»/«إله») ويُمسحان معاً. والحقلُ
  `amount` **مطلوبٌ في الجسم**: المسحُ بـ`null` صريحاً، و`{}` ⇒ 400.
- `set_obligation_client_paid(obligation, *, paid)`: في كلّ الحالات — الدفعُ خبرٌ عن
  الزبون لا عن التقديم.
- `close_prior_obligations(client, *, before, actor)`: كلُّ **منتظِرٍ** فترتُه
  تنتهي قبل `before` ⇒ `submitted` مع `prior_to_office=True` و`submitted_on=None`
  و`submitted_by=actor`. وما ليس منتظراً لا يُمسّ، ويُرجع العدد. وتاريخٌ في
  المستقبل يُرفض (قاعدةُ `submit_obligation` نفسها).
- `assign_task(task, *, assignee)`: العضوُ من **نفس المكتب** (`is_tenant_member`)
  وإلا 400، و`None` تعود إلى وراثة `client.responsible`.

**الإيقافُ و`last_period_ours`:** إيقافُ خدمةٍ في 31 آذار يُبقي التزامَ آذار
(المستحقَّ في نيسان) ولا يولّد نيسان — ويتبع ذلك من `_period_is_ours` وحدها.
و`stop_client_service(..., last_period_ours=False)` تكتب العلمَ على الصفّ فتمنع
`refresh_office` من توليد آخر فترةٍ في كل سلسلة، **وتُعلّم كلَّ التزامٍ منتظرٍ لها
«مش لازم هالفترة»** (لا حذف). و«آخرُ فترةٍ في سلسلة» دالّةٌ واحدة نقيّة:
`last_period_of_stream(periods, *, ends_on)` = الفترةُ التي `period_end ≤ ends_on`
وتنتهي التي تليها بعده. والزبونُ المنتهي: لا فترةَ تنتهي بعد `ended_on`.
ونموذجُ الإيقاف في الواجهة يرسل `last_period_ours` (خانةُ «آخر فترة علينا»،
الافتراضُ `true`)، و`client_service_row` تُعيده في كل سطر.

**المبلغُ مبلغ.** `Obligation.amount` في `OBLIGATION_AMOUNT_KEYS` و`AMOUNT_KEYS`،
وكلُّ صفٍّ يمرّ بـ`mask_amounts`: بلا `office.amounts.view` يصل `null` وتعرض الشاشة
«—»، وكتابتُه ⇒ **403** (كما سعر الباقة المقترح) — وهو **مبلغٌ لا مُعفًى**.

**نقاطُ «اليوم» والالتزامات:** كلُّ كائنٍ يُحلّ عبر `visible_clients`، فالتزامُ
غيرك أو شغلتُه أو زبونُه **404 لا 403** (والرؤيةُ قبل المفتاح في `tasks/<id>/assign/`
كذلك). والكتابةُ بمفاتيحها: الحالةُ و«الزبون دفع» و`close-prior` ⇒
`office.clients.write`، والمبلغُ معها `office.amounts.view`، والإسنادُ ⇒
`office.clients.assign`.

- **`today/?filter=mine|week|late|late_internal|missing_docs`**: يُشغّل `ensure_office_refreshed(day=localdate)`
  أوّلاً ثم `today_payload`. والصفوفُ **المنتظِرة** وحدها مرتَّبةً بـ**الموعد الساري**
  (`Coalesce("extended_to", "actual_deadline")` #277) ثم `internal_deadline` ثم اسم الزبون. و**العدّاداتُ الخمسة (`late`/`late_internal`/`week`/`missing_docs` «ناقصه أوراق» #278/`all`) تُحسب على
  كلِّ الميل المحفوظ قبل الفلتر** — فكبسةُ «متأخّر رسمي» لا تُصفّر «متأخّر داخلي». والفلترُ
  المجهول ⇒ 400. **وعددُ الاستعلامات لا يكبر بعدد الصفوف** (`select_related` للعلاقات
  كافّة، واختبارُ `CaptureQueriesContext` بين صفٍّ وخمسة).
- **`clients/<pk>/obligations/`**: شغلاتُ الزبون (الأحدثُ `period_end` أوّلاً) وكلُّ
  التزاماتها **في كلّ الحالات** بالشكل نفسه، والمبلغُ بالقناع. وكلُّ شغلةٍ تحمل
  `service {id, name}`: شغلتا «كانون الثاني» لق.م وللرواتب لا تُميَّزان بغيره.
- **وأفعالُ الالتزام** كلُّها تُرجع السطرَ المحدَّث بالشكل نفسه (فالخادمُ هو الحكم،
  والشاشةُ تعيد قراءة القائمة والعدّادات).

**الواجهة:** `/accounting-office/today` (`OfficeTodayScreen.tsx`) — الأوّلُ في بيان
الشريط («اليوم»، `nav.office_today`). عمودٌ واحدٌ على الجوال ويتّسع على `md:`؛
وعدّاداتٌ خمسةٌ (#276: «متأخّر رسمي» رقمُه أحمرُ · «متأخّر داخلي» رقمُه أصفرُ ·
«قريب هالأسبوع» · «الكل»؛ و#278: «ناقصه أوراق» رقمُه أصفرُ) **صفّاً أفقياً يتمرّر على الجوال** (كالنموذج) تُكبَس فتُفلتر،
ورقائقُ «شغلي/هالأسبوع/متأخّر رسمي/ناقصه أوراق» يُحفظ اختيارُها في العنوان (`?filter=` عبر
`useSearchParams`) فيبقى بعد التحديث والعودة. و«شغلي» واسمُ المحوَّل إليه يُخفيان
في «شخص واحد» (`showsOfficeAssignment`). وبطاقةٌ لكل التزام:
الزبون و«رسمي» والاسم — الفترة، وشارةُ (قريب/متأخّر رسمي/متأخّر داخلي) و«تقديري»، والمبلغُ
«عليه/إله ₪ X» أو «—»، و«داخلي dd/MM» و«رسمي dd/MM»؛ وأفعالُها «انقدّم» (نموذجٌ
مضمَّنٌ بالتاريخ ورقمٍ اختياريّ) و«مش لازم هالفترة» والمبلغُ و«الزبون دفع» و«افتح
الزبون». و**«الزبون دفع» في صفّ الأفعال لا داخل محرّر المبلغ**: يُكتب في كلّ
الحالات وبمفتاح الكتابة وحده (والخادمُ يقبله كذلك)، فيغيب عن مُقدَّمٍ أو عن عضوٍ
لا يرى المبالغ لو بقي في اللوحة. و`OfficeObligationRow.tsx` مكوّنٌ واحدٌ يرسم
سطرَ الالتزام (الأصلُ والشاراتُ والتواريخُ والمبلغُ والتحذيراتُ ثم الأفعال)
يستعمله هذا التبويبُ وبطاقةُ «اليوم»، و`OfficeObligationActions` (`OfficeObligationActions.tsx`) تحته. والحالاتُ من
`OfficeUi.tsx`، **وردُّ الطلب القديم يُتجاهَل** عند تغيّر الفلتر (علمُ `cancelled`)
فلا يكتب فوق أحدث منه. وتبويبُ
**«الالتزامات والشغلات»** في ملفّ الزبون يعرض الشغلاتِ بفترتها وموعدها الداخليّ
ومسؤولها (ومنتقي تحويلٍ لمن يملك `office.clients.assign` وخارج «شخص واحد»)،
والتزاماتِها بحالتها وأفعالها و«رجّعها»، وزرَّ «هدول انقدّموا قبل ما يجي علينا»
بتأكيدٍ يذكر عددَ ما أُغلق.

## التأخير بدرجتين والتنبيهات والجرس (#276)

**درجتان مشتقّتان عند القراءة، ولا يُخزَّن منهما شيء** (`services._badge_keys`):

| الشارة | معناها | الشرط |
|---|---|---|
| `late` — «متأخّر رسمي» **أحمر** | **الموعدُ الساري** (`due_date` = الممدَّد أو الفعليّ، والتمديدُ الإلكترونيّ داخله) تجاوز ولم يُقدَّم | `status = pending` و`due_date < day` |
| `late_internal` — «متأخّر داخلي» **أصفر** | الشغلةُ تجاوزت موعدَها الداخليَّ والرسميُّ لم يبلغ | `status = pending` و`task.internal_deadline < day` وليس أحمر |
| `near` — «قريب هالأسبوع» | نافذةُ `NEAR_WINDOW_DAYS = 6` كما في #275 | `0 ≤ (due_date − day).days ≤ 6`، ودون الأصفر |

**والأولوية: أحمر ← أصفر ← قريب ← لا شيء.** شارةٌ **واحدةٌ على الأكثر** لكل صفّ
(فشكلُ `badges` قائمةٌ بعنصرٍ واحد)، وتسمياتُها من `OBLIGATION_BADGE_LABELS`.
و**التمديد (#277) يحرّك الأحمرَ وحدَه**: `due_date` هو المقروء، و`internal_deadline`
لا يتغيّر بالتمديد — فالأصفرُ يبقى على الموعد الداخليّ.
فصفٌّ تجاوز داخليُّه لا يحمل شارةَ «قريب». و«انقدّم» و«مش لازم هالفترة» بلا شارة:
ما انتهى أمرُه لا يُنبَّه عليه.

**و«قريب» شارةٌ و`week` نافذة — يفترقان.** شارةُ `near` تخضع للأولوية (فلا تظهر
على صفٍّ أصفر)، أمّا **عدّادُ `week` وفلترُه فعلى الموعد الساري (`due_date`) وحدهما**:
`0 ≤ (due_date − day).days ≤ 6` مستقلاً عن الشارة — فصفٌّ صفرتُه «متأخّر
داخليّ» وموعدُه الساريُّ داخل النافذة **يُعدّ ويظهر تحت `week`**. لولا ذلك لصار
«قريب» مستحيلاً للربعيّ (7 أيامٍ داخليّة) والسنويّ (30)، ويومَين فقط للشهريّ.
فتُقرأ النافذةُ «ماذا يستحقّ هذا الأسبوع؟» والشارةُ «أين وقفتُ؟» — سؤالان.

**العدّاداتُ والفلاتر:** `today_payload.counters` = `{"late", "late_internal",
"week", "missing_docs", "all"}` — تُحسب على كلِّ الميل المحفوظ **قبل** الفلتر، و`week` نافذةُ
`due_date` أعلاه. و`TODAY_FILTERS` ستّةٌ (والفارغُ «الكل»، والسادسُ `missing_docs` #278)، والفلترُ `late`
هو الأحمرُ وحده و`late_internal` الأصفرُ وحده، والمجهولُ 400.

**`OfficeAlert` — تنبيهٌ داخليٌّ لمستلِمٍ واحد.** النوعُ `task_late_internal`
(«شغلة تجاوزت موعدها الداخلي») أو `obligation_late` («التزام تجاوز موعده الرسمي
ولم يُقدَّم»)، و**الأنواعُ تُضاف صفّاً في `OFFICE_ALERT_KIND_CHOICES`** لا فرعاً في
الكود (تصعيدُ التذكير والمسودّةُ غير المعتمدة تذاكرُها؛ **وتغيّرُ اللائحة نُفِّذ
في #277** — انظر §تعديل المكتب على اللائحة والتمديد والتزامات المكتب والأحداث)، و`ref_key`
`"task:<id>"` أو `"obligation:<id>"`. و`client`/`task`/`obligation` هي
**مكانُ الفتح** لا سندُ التنبيه، فحذفُها يحذف التنبيهَ (`CASCADE`) ولا يبقى صفٌّ
يشير إلى العدم. و`message` لقطةُ «اسم الزبون — اسم الالتزام/الفترة» وقت التوليد
**بلا أيّ مبلغ** — فلا يمسّ حارسَ المبالغ.

**«مرّةٌ واحدةٌ لكل مرجع»** هي فرادةٌ غير مشروطة على
`(tenant, recipient, kind, ref_key)`: تشغيلُ اليوم نفسه مرّتين لا يضيف صفّاً،
ويومٌ لاحقٌ لا يُكرّر التنبيهَ نفسه — الشارةُ تبقى تقول الحال، والتنبيهُ أثرُ
أوّلِ مرّةٍ بلغ فيها. والمرجعُ يُميّز الصفوفَ داخل النوع نفسه، فالتزامُ فترتين
تنبيهان، وشغلةٌ واحدةٌ تنبيهٌ واحد. **وهذا هو مفتاحُ التذاكر اللاحقة**: تصعيدُ
التذكير يرمّز دورتَه في `ref_key` (`"reminder:3:day:2"` مثلاً) أو يأخذ نوعاً لكل
درجة، فيبقى «مرّةً لكل مرجع» صادقاً بلا تعديل الفرادة.

**والدرجتان مشتقّتان من أيام الإعداد لا من رقمٍ هنا**: الأحمرُ من **`due_date`**
(`extended_to or actual_deadline`، وهو `official_date` + التمديد الإلكترونيّ حين
لا تمديدَ يدويّ — #277)، والأصفرُ من `task.internal_deadline`
= **أبكر مواعيد التزامات الشغلة**، وهو `actual_deadline` ناقصَ أيام الإعداد
(#274: 5 شهرياً، 7 ربعياً، 30 سنوياً — مستوى الشغلة ← الزبون ← المكتب). **وإعدادُ
#276 للمستلِمين وحده**، لا لعدد الأيام. **والأصفرُ وحده على الموعد الداخليّ**:
التمديدُ يحرّك الأحمرَ ولا يمسّ `task.internal_deadline`.

**التوليدُ داخل `refresh_office`** (`_generate_late_alerts`، بلا ساعة):
كلُّ التزامٍ `pending` بـ`due_date < day` ⇒ «الرسميّ» لمستلِمي
`late_official_alert_to`؛ وكلُّ شغلةٍ فيها التزامٌ منتظرٌ و`internal_deadline < day`
⇒ «الداخليّ» لمستلِمي `late_internal_alert_to` — **وشغلةٌ صار التزامُها أحمرَ تأخذ
الأحمرَ أيضاً** (مرجعان، والفرادةُ تمنع التكرار). **والكلفةُ لا تكبر بعدد
الالتزامات**: الإعدادُ يُقرأ مرّةً للمكتب، والمستلِمون استعلامٌ واحد، والمفاتيحُ
القائمة مجموعةٌ واحدة، ثم `bulk_create(..., ignore_conflicts=True)`. ويُرجع
`refresh_office` أيضاً `"created_alerts"` = **ما أنشأه هذا النداء**، و`OfficeRefreshRun`
لم يتغيّر، والأمرُ `refresh_accounting_offices` يطبع العددَ في سطره. و`ensure_office_refreshed`
لم تزل مرّةً في اليوم، فالمستحقُّ الجديد يأخذ تنبيهَه مرّةً يومياً.

**الإعدادان — «درجات التأخير ومستلِمُو التنبيه»**، في مجموعة `GROUP_ALERTS`
(«التأخير والتنبيهات») على **مستوى المكتب وحده** (المستلِمُ قرارُ المكتب لا قرارُ
زبون)، والاختياراتُ الثلاثةُ نفسها: `assignee` «المسؤول» · `assignee_owner`
«المسؤول وصاحب المكتب» · `owner` «صاحب المكتب». وافتراضُ الأصفر **`assignee`**
(شأنُ الموظف)، وافتراضُ الأحمر **`assignee_owner`** (الموعدُ الرسميُّ مسؤوليّةُ
المكتب كلّه). و**«المسؤول» = `effective_assignee`**، وإن كان `None` (زبونٌ بلا
مسؤول) ذهب لصاحب المكتب بدلاً منه. و**«صاحب المكتب» = كلُّ عضوٍ نشطٍ بدور
`manager`** (`_office_owner_ids` — التعريفُ القائم في `core/access.py`، لا تعريفٌ
ثانٍ)، ومستلِمٌ هو المسؤولُ وصاحبُ المكتب معاً يأخذ تنبيهاً واحداً (مجموعةٌ لا قائمة).

**القراءةُ تُسقط المحسوم وتتبع رؤية الزبون** (`alerts_payload`): تنبيهُ التزامٍ لم
يعد `pending`، وتنبيهُ شغلةٍ لم يبقَ فيها التزامٌ `pending` — بـ`Exists` بلا N+1؛
**وتنبيهُ زبونٍ لا يراه العضو لا يُعرض** (استعلامٌ فرعيٌّ على `visible_clients`،
مصدرُ الرؤية الوحيد، وتنبيهٌ بلا زبون يبقى لمستلِمه). **ولا يُحذف صفٌّ**: «انقدّم»
و«مش لازم هالفترة» يُسقطان التنبيهَ من الجرس، و«رجّعها» تُعيده لأن الحالَ وحدها
تغيّرت. والصفُّ: `id` · `kind` · `kind_label` · **`badge`** · `message` ·
`client {id, name}` أو `null` · `task_id` · `obligation_id` · `day` · `seen` ·
`created_at`؛ والحمولةُ `{"unseen": n, "rows": [...]}` و`unseen` عددُ غير المرئيّ
**وغير المحسوم** (يُعدّ على المجموعة كلّها لا على الصفحة المعروضة). و`badge` مفتاحُ
شارة النوع من `OFFICE_ALERT_KIND_BADGES` (أحمرُ للرسميّ وأصفرُ للداخليّ، ونوعٌ
لاحقٌ `""` محايد) — فتُلوَّن الشارةُ بلا معرفة أنواعٍ في الواجهة.

**«شفته»** (`mark_alert_seen` / `mark_all_alerts_seen`) تكتب `seen_at` لِما لم يُرَ،
فيُحسم العدّادُ. و**«شفتهم كلهم» على المعروض وحده** (يمرّ بـ`_visible_alerts`)،
فلا يُكتب على تنبيهٍ محسوم: «رجّعها» بعده تُعيد تنبيهاً **غيرَ مقروء** ويُعدّه
العدّاد. و**كلُّ عضوٍ يرى تنبيهاته هو فقط** (`recipient=user`): لا مفتاحَ إضافياً
ولا `?user=`، **وتنبيهُ غيرك 404** — والكائنُ يُحلّ بمستلِمِه في `OfficeAlertsViewSet`
قبل أيّ فعل. ثلاثُ نقاط: `GET alerts/` (تبدأ بـ`ensure_office_refreshed` كشاشة
«اليوم») · `POST alerts/<id>/seen/` (يُرجع السطرَ المحدَّث) · `POST alerts/seen-all/`
(`{"seen": n}`). و`mark_all_alerts_seen` **تقرأ المعرّفاتِ ثم تكتب** بـ`pk__in=ids`:
`UPDATE` بمجموعةٍ فرعيةٍ على الجدول نفسه يرفضه MySQL (1093) ويقبله SQLite، فلا يكشفه
الاختبار إلا بفحص شكل الاستعلام (`test_alerts.py`، `SeenScopeTest`).

**الجرسُ `OfficeAlertsBell.tsx`** في الشريط العلويّ بـ`AppLayout.tsx` **بجوار
`NotificationCenter`** (ذاك إشعاراتُ الموقع ولا يُمسّ): زرُّ جرسٍ بعدّادٍ أحمرَ صغير
(`bg-rose-600 text-white`، يختفي عند الصفر)، وقائمةٌ منسدلةٌ سطرٌ لكل تنبيه —
شارةُ النوع من `alert.badge` (`obligationBadgeClass`) والرسالةُ والتاريخُ القصيرُ
`dd/MM`، وغيرُ المرئيّ بخطٍّ أثقل — وزرُّ «شفتهم كلهم». **النقرُ يعلّمه «شفته» ثم
يفتح مكانَه**: ملفّ الزبون على تبويب «الالتزامات والشغلات» **وعلى الشغلة نفسها**
(`alertTargetPath` → `?client=<id>&tab=obligations&task=<task_id>`)،
و`OfficeClientFile` يقرأ `?tab=` و`?task=` عبر `useSearchParams` ويكتب التبويبَ عند
كل اختيارٍ فيبقى العنوانُ صادقاً؛ والشغلةُ المقصودة تُمرَّر إليها (`scrollIntoView`) **مرّةً لكل هدف**
(مرجعٌ يحفظ آخر معرّفٍ مُمرَّر إليه، فلا تقفز الصفحةُ بعد كل حفظٍ على أي شغلة)
وتُبرز بإطار (`ring-2 ring-amber-400`، Tailwind وحده) — فالتنبيهُ يحمل مكانَه لا
محتواه. ومعرّفُ العنصر ودالّةُ القراءة في `utils/accountingOffice.ts`
(`officeTaskAnchorId`/`taskIdFromSearch`، بـ`node --test`). والجلبُ عند التركيب
وكلَّ خمس دقائق وعند عودة التركيز للنافذة وبعد كل «شفته»، وردُّ طلبٍ قديمٍ لا يكتب
فوق أحدث منه (عدّادُ طلبات). وإغلاقٌ بالنقر خارجها وبـEsc، وحالاتُ تحميلٍ/خطأٍ بزرّ
«أعد المحاولة». **ولا يظهر إلا لمكتبِ محاسبةٍ مرخَّص** بالمصدر القائم نفسه
(`VIEW_MODULES`/`moduleAllowsView` مع `usePermissions().modules`) — لا شرطَ ترخيصٍ
جديد.

## تعديل المكتب على اللائحة، والتمديد، والتزامات المكتب، والأحداث (#277)

**اللائحةُ تبقى بياناتَ منصّةٍ لا تُعدَّل** (قرار #274) — والمكتبُ يعدّل عليها
**على مسؤوليته** بصفٍّ إلحاقيّ في `OfficeRuleOverride` يحمل قيمَه ولقطةَ المنصة
(`based_on`) ومَن عدّل ومتى. **والساري أحدثُ صفّ** لكل `(مكتب، نظام، كود)`
بترتيب `-created_at, -id`، و«رجّع للمنصة» صفٌّ `cleared=True` — **فالسجلُّ لا يُمحى**
(قرار #255)، وتاريخُ المنصة يبقى مقروءاً بجانبه في الشاشة.

**والحسابُ واحدٌ لا نسختان.** `services._deadline_result` هي مدخلاتُ المحرّك
الوحيدة: تقرأ النظامَ وإعدادات الزبون وعطلةَ المكتب وسياسة النسخة، ثم تنادي
`deadlines.compute_deadline`. يقرؤها **المولّد** (`_deadline_items`، للتقويم
والتحديث) و**إعادةُ الحساب** (`_recompute_obligations`) معاً — فأولُ تعديلٍ في
قاعدةٍ لا يفترق بينهما.

- **سطرٌ عليه تعديلُ مكتب**: يُحسب بكائنٍ نسخةٍ من السطر بقيم المكتب
  (`_rule_with_override`)، و`period_overrides` المنشورة **تُسقط** حين يُعدَّل السطر:
  قرارُ المكتب يغلب نشرةَ المنصة. وسياسةُ يوم الراحة للنسخة تبقى. ويُحسب موعدُ
  المنصة أيضاً؛ فإن اختلف `official_date` حُمِل في `platform_official_date`، وإلا
  بقي `None`.
- **التزامُ المكتب** (`OfficeCustomRule`): يُولَّد بالفترات نفسها (`periods_for` أو
  دورية الخدمة) وبلا **أيّ شرط بطاقة** — المكتبُ عرّفه لنفسه. كودُه `office-<pk>`
  فيسري عليه ما يسري على كودٍ رسميّ (الفرادةُ والفلترة)، و`origin="office"`.
  **ويُولَّد فور إنشائه** (`_generate_for_service`) لزبائن خدمته، وعند تبدّل خدمته
  أو دوريته أو عودته إلى التفعيل — بـ`_save_due_for_clients` نفسها التي يقرؤها
  `refresh_office`، فلا مسارَ ثانٍ، ولا ينتظر الالتزامُ الجديد الغدَ.
- **سطرُ الحدث** (`cadence="event"`) **لا يُولَّد دورياً أبداً** — يُتخطّى في
  `_deadline_items`، وتُولَّد فترتُه من الحدث وحده.

**تحديثُ المنصة = نسخةٌ أحدث** (`version` أكبر) لنفس `(tax_system, year)`،
و`schedule_for` يلتقطها. وقبل حفظ الجديد في `refresh_office`
(`_apply_platform_updates`): كلُّ التزامٍ **غيرِ مقدَّمٍ** (`pending`/`not_required`)
يشير إلى نسخةٍ لم تبقَ ساريةً ينتقل إلى سطر الكود نفسه في النسخة السارية ويُعاد
حسابه؛ وسطرٌ غاب من الجديد **لا يغيّر تاريخاً** ويُضاف «السطر لم يعد في لائحة
المنصة — راجع» إلى `warnings` (وتحفظه إعادةُ الحساب اللاحقة `_recomputed_warnings`،
ويسقط حين تنقله النسخةُ التي عاد فيها السطر). **والمقدَّمُ لا يُمسّ** ولا يُنقل سطرُه. والكلفةُ
ثابتة: الالتزاماتُ استعلامٌ واحد، وأسطرُ النسخ الجديدة استعلامٌ واحد، والكتابةُ
دفعةٌ واحدة.

وتنبيهان جديدان يستلمهما **أصحاب المكتب** (`MANAGER_ROLE` النشطون) بلا `client`:

| النوع | متى | `ref_key` | وجهتُه |
|---|---|---|---|
| `schedule_dates_changed` | تغيّر تاريخُ التزامٍ واحدٍ على الأقل بنسخةٍ جديدة — **«تغيّر موعد N التزامات»**، مرّةً لكل نسخة | `"schedule:<id>"` | `deadline_rules` |
| `override_platform_changed` | المنصة غيّرت سطراً عدّله المكتب (`based_on` لم يعد يطابق النسخة الجديدة) — **«تُبقي تاريخك أم تأخذ الجديد؟»** | `"override:<id>:schedule:<id>"` | `deadline_rules` |

ونوعاهما **خارج `RESOLVED_ALERT_KINDS`** فيبقيان حتى «شفته»، ويسقط الثاني وحده على
القراءة إن لم يعد ذلك التعديلُ سارياً (رُجّع أو أُكِّد) — بشرطٍ في `_visible_alerts`.
و**`alert_row` يحمل `opens`** من `OFFICE_ALERT_KIND_OPENS` (الافتراض `client`)،
فتعرف الواجهةُ الوجهةَ بلا معرفة أنواع. و«أُبقي تاريخي»
(`keep_rule_override`) صفٌّ بالقيم نفسها ولقطةٍ من النسخة السارية؛ و«تأخذ الجديد»
(`clear_rule_override`) صفُّ `cleared`.

**التمديد**: `Obligation.due_date` = `extended_to or actual_deadline` — وهو وحده ما
يقرؤه **الأحمر** في `_badge_keys`، ونافذةُ `week` في `_in_near_window`، ومرشّحا
`obligation_late` في `_generate_late_alerts` (في SQL: `Q(extended_to__isnull=True,
actual_deadline__lt=day) | Q(extended_to__lt=day)`)، وترتيبُ «اليوم»
(`Coalesce("extended_to", "actual_deadline")`). **والأصفرُ يبقى على
`task.internal_deadline`**: الموعدُ الداخليُّ قرارُ المكتب الداخليّ، والتمديدُ
للموعد الرسميّ. و`extend_obligation` للمنتظِر وحده، بتاريخٍ **بعد الفعليّ**
وبملاحظةٍ غير فارغة، وتكتب `extended_*` وصفّاً في `ObligationDateChange`
(`reason="extension"`) وأثراً في سجلّ الزبون. و`clear_obligation_extension` ترجع
إلى الفعليّ بصفٍّ `extension_cleared`. **وتنبيهُ `obligation_late` المولَّد سابقاً
يسقط من الجرس بعد التمديد** ما دام `due_date >= اليوم` — شرطٌ في `_visible_alerts`
يمرّ بـ`alerts_payload(..., day=)`، ولا صفَّ يُحذف.

**الأحداث («صار حدث»)**: `EVENT_KIND_CHOICES` في `settings_registry.py` (قائمةٌ
تُوسَّع صفّاً، ونوعٌ واحدٌ الآن: `withholding` = «اقتطاع ضريبة مصدر»)، وإعداد
`enabled_event_kinds` من نوع `KIND_MULTI_CHOICE` (مستوى المكتب، مجموعة `schedule`)،
و`record_client_event`:

1. النوعُ مفعَّلٌ وإلا رفض، والتاريخُ ليس في المستقبل.
2. سطرُ `cadence="event"` و`event_kind` المطابق في نسخة نظام الزبون لسنة وقوعه —
   وإلا «لا قاعدة لهذا الحدث في لائحة <النظام>».
3. خدمةُ السطر (`service_code`) **نشطةٌ** عند الزبون يومَ الحدث — وإلا رفضٌ باسمها.
4. ينشئ `ClientEvent`، ثم `PeriodTask` بفترةٍ هي يومُ الحدث نفسُه
   (`period_start=period_end`)، والتزاماً بـ`compute_deadline`: `legal_date` من
   `RULE_KIND_DAYS_AFTER_EVENT`
   (**اقتطاعٌ في X ⇒ الالتزام في X+30**)، والرسميُّ بسياسة يوم الراحة للنسخة،
   والداخليُّ بأيام الدورية الشهرية ولا يسبق يومَ الحدث (`max`).
5. حدثان في اليوم نفسه بنفس النوع ⇒ **التزامٌ واحد** (الفرادةُ القائمة)، والسجلُّ
   يحتفظ بالصفّين.

**وإسرائيل بلا سطر حدثٍ الآن** — لا مصدرَ بحثيّ له، فسطرُها يُضاف بنسخةٍ لاحقةٍ
حين يوجد مصدر.

**وهجرة `0007`** تنشئ **v2** لكل نسخة فلسطين قائمة (2026 و2027): تنسخ أسطرها حرفاً
(بما فيها `period_overrides` و`needs_review`) وتضيف سطر
`ps_withholding_event`، وتُبقي النسخَ القائمة كما هي. والالتزاماتُ الفلسطينية
القائمة تنتقل إلى v2 عند أول تحديث **بلا تغيّر تاريخٍ ولا تنبيه (N=0)**.

**وعكسُ الهجرة مشروطٌ بغياب بياناتٍ مولَّدة**: يحذف نسخ v2 التي أنشأتها وحدها
(بمفاتيحها الطبيعية، لا بأرقامها) — لكنه لا يمرّ بعد أن تُنشأ التزامات: أسطرُ v2
على `PROTECT` من `Obligation.rule`، فحذفُها يرفع `ProtectedError` ولا يمحو شيئاً
(والتاريخُ لا يُمحى — قرار #255). وهو صالحٌ في قاعدةٍ بعد الهجرة قبل التوليد
(اختبارٌ أو بيئةٌ جديدة). والتزامُ المكتب (`custom_rule`) والحدث (`event`) لا
يشيران إلى سطر لائحةٍ أصلاً — `rule` صار `null=True` — فليسا داخل هذا الحذف.

**الواجهة**: في `OfficeSettingsScreen` — مجموعة «الضريبة ولائحة المواعيد» — قسمُ
«لائحة المواعيد» (`OfficeDeadlineRulesSection`: وصفُ قاعدة المنصة من أرقامها،
وتعديلُ المكتب بارزاً وبجانبه «المنصة: …»، وزرّا «عدّل» و«رجّع للمنصة»، والسجلّ،
وشريطُ «تُبقي تاريخك أم تأخذ الجديد؟» بزرّيه) وقسمُ «التزامات المكتب»
(`OfficeCustomRulesSection`: إضافةٌ وتعديلٌ وتعطيل، **قراءةً وكتابةً بمفتاح
الإعدادات** — والدورُ في `list` أيضاً). والقسمان يُرسمان لمن يملك
`office.settings.manage` وحده، ومع نظامٍ غير مختارٍ يُعرض «اختر النظام الضريبي
أولاً» بدل افتراض `IL`. و`?group=schedule` تفتح الشاشة
على المجموعة (`settingsGroupFromSearch`، دالّةٌ خالصة)، وشريطُ «تُبقي تاريخك أم
تأخذ الجديد؟» يقرأ `awaiting_decision` من الخادم (لا مطابقةَ نصّ التنبيه)، ومفتاحُ
حالة التحرير والسجلّ `${rule_code}-${year}-${version}` لأن الكودَ يتكرّر لكل سنة. وملفُّ الزبون في تبويب
«الالتزامات والشغلات» فيه `OfficeClientEvents` («صار حدث») وأزرارُ «مدّد»/«ألغِ
التمديد» في `OfficeObligationActions`. و`OfficeObligationRow` و`OfficeCalendarScreen`
يحملان شارةَ «من المكتب»/«حدث» (بلونٍ محايد، والرسميُّ بلا شارة)، و«ممدَّد حتى …»
بملاحظتها، و«المنصة: …» (`obligationExtensionText` · `platformOfficialText` ·
`obligationOriginLabel` · `deadlineRuleDescription`، كلُّها خالصةٌ ومُختبَرة).
و`SettingControl` يرسم `multi_choice` مجموعةَ مربّعات (Tailwind فقط).

## قائمة الأوراق وشبكة الأشهر (#278)

**القائمةُ ثلاثُ طبقاتٍ لا طبقة** (قرار #278/D1): **بنداتُ المنصّة**
(`PlatformDocumentItem` بلا `tenant` كاللائحة والسقوف — قانونٌ واحدٌ لكل المكاتب)،
ثم **قالبُ المكتب**: بندٌ يضيفه (`OfficeDocumentItem`) أو بندُ منصّةٍ يُخرجه
(`OfficeDocumentItemChoice.included=False`)، ثم **خيارُ الزبون**
(`ClientDocumentItemChoice`) **الذي يغلب الجميع**: إدخالاً يفرض بنداً لا تنطبق
شروطه ولا يريده القالب، وإخراجاً يمحو بنداً انطبق.

**الانطباقُ** (`_document_item_applies`): `service_codes` فارغةٌ = لكل زبون، وإلا
فلا بدّ من تقاطعٍ مع خدمات الزبون **الفعّالة والمسؤول عنها المكتب في تلك الفترة**
(قاعدةُ `_period_is_ours` نفسها التي يحكم بها محرّك الالتزامات)، **وكلُّ** شرطٍ في
`card_conditions` يجب أن يطابق بطاقته — وقيمةٌ فارغةٌ في البطاقة **لا تطابق**
شرطاً أبداً. و`_document_items_for(client, *, cadence, period_start, period_end,
context=None, skip=None)` هي **الدالّةُ الواحدة** التي تجيب ذلك؛ يقرؤها التوليدُ
وحده، و`skip` يمرّ إلى `_document_service_codes` فتُسقط خدمةً رُفع عنها «آخر فترة
علينا» إن **حوت** فترتُها فترةَ المستندات (`_document_period_disclaimed`: احتواءٌ
لا تساوٍ — الخدمةُ قد تكون رُبعيةً أو سنويةً وقائمةُ المستندات شهرية).

**بندٌ واحدٌ لخدمتين**: «فاتورات المشتريات» `["bookkeeping", "vat"]` يُولَّد
**مرّةً واحدة** — لا بندان لخدمةٍ واحدة (معيار القبول ١).

**التوليدُ داخل «حدّث المكتب»** (`accounting_office/services.py` —
`_generate_document_rows`، مناداةً من `_refresh_client` في معاملة الزبون نفسها):
فترةٌ انتهت (`period_end <= day - 1`) صارت مستحقّة — الشهرُ M في أوّل M+1، والسنةُ
Y في 1 يناير Y+1 — لكل فترةٍ المكتب مسؤولٌ عنها، وللزبون المنتهي حتى `ended_on`،
و`skip` يسقط «آخر فترة علينا» **باحتواء فترتها** (في `_document_period_due`
و`_document_service_codes` معاً). و`get_or_create` على
`(client, item_code, period_start)` يجعله **idempotent**، والصفُّ القائم **لا
يُعاد كتابته**: الكتالوجُ وخياراتُه يؤثّران في التوليد القادم وحده، والصفُّ
لقطةٌ (`item_code`/`name`/`service_codes`). ويُضاف عدّادُ
`created_documents` إلى ردّ `refresh_office` بجانب عدّاداتها.

**الحالاتُ الأربع** (#278/D3): `required` «مطلوبة» · `partial` «وصلت ناقصة» ·
`received` «وصلت» · `not_needed` «مش لازمة هالشهر» — وتُعرض الأخيرة «مش لازمة
هالسنة» للصفّ السنوي (`document_status_label`). و`set_document_status`:
«وصلت»/«وصلت ناقصة» **تُلزمان قناةً** (`whatsapp`/`paper`/`email` — وإلا 400 على
`channel`) وتكتبان `received_on` (اليومَ المُمرَّر) و`received_by` (الفاعل)،
و«مطلوبة»/«مش لازمة» **تمحوان** الثلاثة. وحالةٌ مجهولة 400 على `status`.

**الملفُّ كيانٌ منفصلٌ اختياريّ** (#278/D4): `DocumentFile` بحقول **נספח ז**
السبعة (مُعرِّفٌ فريد `uid` · مَن أنشأ · نوعُ المستند — افتراضُه اسمُ الورقة ·
رقمُ تسجيل المُصدر · تاريخُ المستند · رقمُ المستند · تاريخُ الالتقاط)، و
`is_copy` افتراضُه «صورة» فيُعرض وسمُ «صورة — الأصل عند الزبون». **ورفعُه أو
حذفُه لا يغيّر الحالة** (معيار القبول ٤). والرفعُ يُفحص **حجمُه أوّلاً**
(`validate_document_size` من `upload.size`) **قبل أي قراءة** — فلا يدخل ملفٌّ فوق
١٠ ميجابايت الذاكرةَ — ثم يُقرأ رأسٌ بطول `DOCUMENT_MAGIC_BYTES` ويُعاد المؤشّر،
ويحكم `validate_document_upload` (PDF/JPEG/PNG/WEBP، **وبايتاتُ الملف هي الحَكَم**
لا امتدادُه)، ثم `upload_media_file`؛ وفشلُه (`MediaUploadError`) يحتفظ بحالته:
400 (الحجمُ أو سقفُ تخزين الخطّة) يُردّ بنصّه المكتوب لمستخدم الشركة، وأيُّ حالةٍ
أخرى (502/503) بجملةٍ عامّة والتفصيلُ للسجلّ (`logger.warning`) لأنه قد يحمل نصَّ
المزوّد. وإن فشل حفظُ الصفّ بعد نجاح الرفع يُمحى
الأصلُ (`destroy_cloudinary_asset`) فلا يتيمَ في التخزين. والتقديمُ بايتاتٍ من
`stream_stored_asset` (لا تحويل)، و`file_url` **لا يخرج في أيّ ردّ** — والحذفُ
يمحو الصفَّ أوّلاً ثم الأصلَ من التخزين بجهدٍ بذل (`destroy_cloudinary_asset`).

**«ناقصه أوراق» شارةٌ مشتقّةٌ تُحسب عند القراءة ولا تُخزَّن** (#278/D6): لالتزامٍ
منتظرٍ، الصفوفُ التي خدمتُه داخل `row.service_codes` وفترتُه محتواةٌ في فترته.
«وصلت ناقصة» تُبقيها، و«وصلت» و«مش لازمة» تُسقطانها، وصفٌّ بلا خدمةٍ لا يُشعلها.
وهي **إضافية**: تجتمع مع شارة التأخير الواحدة ولا تُزاحمها. ويُحسب معها
`docs: {"received": n, "required": m}` لكل صفّ (`m` بلا «مش لازمة»، `n` ما وصل،
و`null` إن لا صفوفَ محسوبة: لا صفّ، أو كلُّها «مش لازمة») — **باستعلامين ثابتين** لكل الصفحة (`document_progress`)،
والاستعلامُ الثاني **مقيَّدٌ بمدى الالتزامات المنتظِرة** (`period_start >= أدنى
بداية` و`period_end <= أقصى نهاية`) ثم مفهرَسٌ في الذاكرة على `(الزبون, كود
الخدمة)`، فكلُّ التزامٍ يمسح دلوه وحده ولا يُقرأ تاريخُ المكتب كلُّه لعدّ شهرٍ واحد.
ولها عدّادٌ `missing_docs` وفلترٌ في «اليوم».

**مددُ الحفظ بياناتُ منصّةٍ** (#278/D5) في `DocumentRetentionRule`: فلسطين ٥
سنواتٍ من نهاية السنة (م79/1)، وإسرائيل ٧ من نهاية السنة أو ٦ من التقديم
**الأبعدُ منهما** (§25(ג)) و٣ من التقديم لغير الإلزامية (§25(د))، بمصدرها
المنشور. تُزرع في هجرة `0008` مع لائحة البنود: **37 بنداً** (18 فلسطينيٌّ و19
إسرائيليّاً)، و**41** بعد `0009` (20 فلسطينيٌّ و21 إسرائيليّاً)، وعكسُها يحذف
أكوادَها وحدها. وv1 يعرضها في تذييل التبويب ولا يحسب
تاريخاً ولا يحذف شيئاً.

**الواجهة** (#278/D8): تبويبُ «الأوراق» في ملفّ الزبون
(`OfficeClientDocuments.tsx`) — دليلُ الألوان الأربعة، وشبكةُ الأشهر × البنود
(خانةٌ واحدةٌ لكل شهرٍ في كل صفّ، والفارغُ محايد)، وكبسةُ الخانة تفتح لوحَ
الحالة (أربعةُ أزرار، ثم «كيف وصلت؟» لـ«وصلت»)، وسطرُ تفاصيل الخانة وملفاتُها
(رفعٌ بحقول נספח ז، وفتحٌ من نقطة التنزيل، وحذفٌ بـ`useConfirm`)، والشريطُ
الكهرمانيّ «ناقص لشهر …»، والقائمةُ السنويةُ بطاقاتٍ، وتذييلُ مدد الحفظ، ولوحُ
«تخصيص القائمة» (يسرد من بنود المكتب الفعّالَ وحده، فالمعطَّلُ لا يولّد وخيارُ
الزبون عليه بلا أثر). وقالبُ المكتب قسمٌ في شاشة الإعدادات
(`OfficeDocumentItemsSection.tsx`) بمفتاح `office.settings.manage`. والمنطقُ
الخالصُ في `frontend_v2/utils/accountingOffice.ts`
(`documentGridRows` · `documentCellTone`/`documentCellClass`/`documentCellGlyph` ·
`documentDocsText` · `documentMissingBar` · `documentMonthLabel` …) بـ`node --test`،
والاتصالُ في `accountingOfficeApi.ts` (والرفعُ `apiPostFormData`).


## الرواتب — متابعة الاستحقاق (#279)

**النطاقُ مواعيدُ الاستحقاق وحدها — ولا حسابَ راتبٍ في أيّ سطر**: لا أجرَ ولا
شريحةَ ضريبةٍ ولا اقتطاع. السؤالُ الذي تجيبه التذكرة: **أيّ التزامٍ يستحقّ، ومتى،
ولمن؟** — والراتبُ نفسه رقمٌ يعرفه الزبون ويقدّمه ورقاً (تبويبُ «الأوراق»، #278).

**نصفُ سنويّ دوريةُ سطرٍ لا دوريةَ خدمة** (`CADENCE_SEMIANNUAL` في
`DEADLINE_CADENCE_CHOICES` و`CADENCE_SPAN_MONTHS = 6`): فترتاه **يناير–يونيو**
و**يوليو–ديسمبر**، ويأخذ أيامَ إعداده من **إعداد الربعيّ**
(`internal_lead_days_quarterly`) فلا إعدادَ سابعاً. **وليس في
`CLIENT_SERVICE_FREQUENCY_CHOICES`** ولا في دوريات التزام المكتب (#277): لا
زبونَ يشترك في خدمةٍ نصف سنوية، ولا مكتبَ يخترع سطراً بنصف سنة.

**نسخةُ إسرائيل v2** (هجرة `0009`): تُنسخ أسطرُ v1 حرفاً — بما فيها
`period_overrides` و`needs_review` — ويُزاد عليها:

- `il_withholding_102` و`il_bl_employees` تأخذان `cadence="service"`: **تتبعان
  دوريةَ خدمة الزبون** (#264 «دورية 102 حسب ملفه») — خدمةٌ شهرية تُولّد التزاماً
  كلَّ شهر، وخدمةٌ كلَّ شهرين تُولّد التزاماً واحداً لشهرين. وبقيّةُ حقولهما كما
  نُشرت.
- **`il_bl_126_semiannual`** «טופס 126 חציוני לביטוח לאומי»: `cadence="semiannual"`،
  وقاعدةُ `day_of_next_month` بـ`rule_day=18` ⇒ **18 يوليو** عن يناير–يونيو، و**18
  يناير** عن يوليو–ديسمبر (والتقريرُ المقدَّمُ في يناير يشمل السنةَ كلَّها)، بشرط `has_employees`، وبلا تمديدٍ إلكترونيّ، ومصدرُه صفحةُ
  ביטוח לאומי. والزحزحةُ بعد ذلك من سياسة النسخة (`postpone_client`) وحدها —
  فـ18/7/2026 يومُ سبتٍ فيُزحزَح، و**التاريخُ القانونيّ يبقى 18 تموز**.
- `il_annual_126_856` سطرٌ واحدٌ كما هو: 126 و856 على موعد §166 نفسه، و«856 إن
  وُجد» يدخل فيه.

**ونسخةُ فلسطين v3** (الهجرة نفسها، من v2 الحالية): تُنسخ الأسطرُ الستة حرفاً
ويُضاف **`ps_payroll_annual_statement`** «الكشف السنوي للرواتب» — سنويٌّ بـ30
نيسان وشرطِ `has_employees`، و**`needs_review=True`**: تعليمات 8/2012 تقول «في
نهاية كل فترة ضريبية» **بلا يومٍ منشور** (بحث `acct-tax-ps` §٤-ب)، فلا يُقدَّم
تاريخُه للناس مؤكَّداً، ويعدّله المكتب من شاشة اللائحة (#277). و`ps_social_security`
يبقى `is_generated=False` (موقوفٌ بقرار 4/2019).

**والنسخةُ السارية أكبرُ `version`** (`schedule_for`)، فالتصفّحُ والتحديثُ يقرآن
v2/v3 بلا سطرٍ جديد: والالتزاماتُ القائمة **غيرُ المقدَّمة** تنتقل إليهما في أوّل
«حدّث المكتب» بمسار #277 نفسه (`_apply_platform_updates`). وفترةٌ اختفى مجراها من
النسخة الجديدة (التزامٌ شهريّ لخدمةٍ صارت كلَّ شهرين) **لا يتغيّر تاريخُها** ولا
يُكتب فيها شيء — التاريخُ لا يُخترَع. و**المقدَّمُ لا يُمسّ** في كلّ الأحوال.

**دوريةُ خدمة الرواتب شهريةٌ أو كل شهرين** (#264): `_assert_payroll_frequency`
هي النقطةُ الواحدة، يقرؤها **مسارا الكتابة** — الإضافةُ (`_insert_client_service`)
وتغييرُ الدورية المؤرَّخة (`change_client_service_frequency`) — فيُرفض غيرهما
بـ`ValidationError({"frequency": "دوريةُ الرواتب شهريةٌ أو كل شهرين."})` (400 من
الـAPI) قبل أيّ كتابة. ولا حدَّ على خدمةٍ أخرى، و`suggest_frequency` تبقى تقترح
الشهريّ.

**إعدادُ «الالتزامات التي تولّدها خدمة الرواتب»** (`payroll_obligations`): من نوع
`KIND_MULTI_CHOICE` على **مستوى المكتب والزبون**، افتراضُه **كلُّ البنود**،
واختياراتُه **أكوادُ الرواتب غير الحدثية في أحدث نسخ اللائحة** بأسماء أسطرها تسمياتٍ
(`PAYROLL_OBLIGATION_CHOICES` في السجلّ — ولا يستورد النماذج كـ`EVENT_KIND_CHOICES`).
ويُطبَّق في **مكانٍ واحد**: `rule_applies` — سطرٌ `service_code="payroll"` خارج
الإعداد لا يُولَّد، فيقرأ **التوليدُ والتقويمُ** قراراً واحداً من الدالّة الواحدة.
**وأمّا «اليوم» فيقرأ الصفوف المحفوظة**: تقليصُ الإعداد لا يحذف التزاماً وُلد قبلُ
ولا يعيد كتابة تاريخه (#275)، فيبقى ظاهراً حتى يحسمه المكتب («مش لازم»).
**وسطرُ الحدث خارج الإعداد**: سطرُ الاقتطاع (`ps_withholding_event`) يحكمه
«أنواع الأحداث المفعّلة» (`enabled_event_kinds`) وحده — يُسجَّل الحدثُ فيُولَّد
التزامُه أو لا، ولا علاقةَ لهذا الإعداد به. ويُقرأ **من سياق الطلب**
(`CONTEXT_SETTING_KEYS` مع `PAYROLL_OBLIGATIONS_KEY`) فلا استعلامَ لكل سطر. وملفُّ
الزبون يرسمه `SettingControl` نفسه (يرسم `multi_choice` مجموعةَ مربّعات)، والخادمُ
هو الحكم. **وحارسُ الانحراف** اختبارٌ يقارن اختياراتِ السجلّ بأكواد الرواتب **غير
الحدثية** في النسخ السارية: بندٌ يُنشر بلا اختيارٍ يسقطه.

**وأوراقُ الرواتب بندان لكل نظام** (هجرة `0009`، شهريان بلا شرطِ بطاقة،
`service_codes=["payroll"]`): «كشف رواتب الشهر» `ps_payroll_sheet`/`il_payroll_sheet`
**مطلوب**، و«تغييرات الموظفين (تعيين، ترك، تغيير راتب)»
`ps_employee_changes`/`il_employee_changes` يبدأ **«مش لازمة»**. ولذلك حقلُ
**`PlatformDocumentItem.default_status`**: الحالةُ التي يبدأ بها الصفُّ المولَّد —
**بندُ المنصّة وحده يحملها، وبندُ المكتب يبدأ «مطلوبة» دائماً**. وصفٌّ «مش لازمة»
**لا يُعدّ ورقةً مطلوبة** في `document_progress` فلا يُشعل «ناقصه أوراق» (القاعدةُ
قائمةٌ من #278 ويحرسها اختبارٌ هنا). والتوليدُ `get_or_create` كما هو: الصفُّ
القائمُ لا يُعاد كتابةٌ فلا يُقلب ما رآه الموظف.

**وتسميةُ الحقل «عدد العاملين»** (#279): الحقلُ يبقى `employees_count` (لا هجرةَ
بيانات)، وتتغيّر تسميتُه المعروضة في النموذج (`verbose_name`) ورسالةِ التحقّق
وحقلِ ملفّ الزبون. ولا شيءَ آخرَ في البطاقة يتبدّل.

**وهجرة `0009_payroll_due_dates` إضافيّةٌ محضة**: `AddField` (الحالة الابتدائية)،
و`AlterField` (اختياراتُ الدورية وتسميةُ العدد — لا تبديلَ عمود)، و`RunPython`ان
بعكسٍ. **idempotent** بوسمها (`"v2: الرواتب (#279)"` و`"v3: الرواتب (#279)"`)
فلا تُنسخ سنةٌ مرّتين، وعكسُها يحذف **نسختَيها وبنداتِها الأربعة وحدها** —
والنسخُ الأقدم تبقى، و`Obligation.rule` على `PROTECT` يمنع سحبَ نسخةٍ حُسب عليها
التزامٌ محفوظ (قرار #255).

**والواجهة**: بنودُ الرواتب تظهر في تبويب «الأوراق» بلا عملٍ جديد (اللائحةُ بيانات)،
وإعدادُ الـ`payroll_obligations` في مجموعة «الضريبة ولائحة المواعيد» لمكتبه
ولزبونه، والأيامُ النصف سنوية على «18» تُعرض في شاشة اللائحة من أرقامها.

## التذكيرات والرسائل — «جاهز للإرسال» (#280)

**الفكرةُ سطرٌ واحد**: لا يُخزَّن «متى التذكير القادم» في أيّ عمود. `_reminder_candidates`
تحسب المستحقَّ **عند كل قراءة** من (أوراقٍ ناقصة × سجلِّ ما أُرسل × إعدادات الإيقاع)،
فسرعةُ إرسالٍ أو تغييرُ إعدادٍ أو عطلةٌ تُغيّر النتيجةَ فوراً بلا مهمةٍ تُحدّث صفوفاً.

**الإيقاع (D6)**: لكل (زبون × أوراق × فترة) — أوّلُ يومٍ = `period_end + start_days`
(افتراضُه 1)، واليومُ التالي = **آخرُ صفٍّ صادر** (إرسالٌ أو تنحية) + `interval_days`
(افتراضُه 3)، ولا تذكيرَ بعد `max` صفٍّ **عدّاً صافياً** (افتراضُه 3). والصفوفُ
**المُبطَلة بـ`undo` لا تُعدّ** (`Exists` داخل الاستعلام نفسه فلا استعلامَ لكل صفّ)،
و`dismissed` **يُعيد المؤقّت ولا يُعدّ**، و`manual` يُعدّ كالإرسال. والفواصلُ
**قابلةٌ للتخصيص لكل زبون**: مكتبٌ يلاحق زبوناً كبيراً بإيقاعٍ أسرع يخصّصه.

**الفترةُ بمفتاحٍ مركّب**: العدُّ والبنودُ مفتاحُها `(period_start, period_end)` لا
بدايةَ الفترة وحدها — القائمةُ السنوية تبدأ في 1 يناير كالشهرية، وبدايةٌ واحدةٌ
كانت تخلط أوراقَ السنة بأوراق كانون الثاني فتخطئ تاريخَ الاستحقاق. لذلك **يطلب
رمزُ الفعل الطرفين معاً**: `period_end` غائبةٌ ⇒ 400، ولا تُستنتَج من البداية.
ورسالةُ «جاهز للإرسال» تحمل المفتاحين في بندها، فالشاشةُ لا تخمّن.

**القائمةُ رسالةٌ لكل شخصٍ لا لكل زبون (D9)**: التجميعُ على جهة الاتصال المستلِمة
(تعيينُ النوع إن وُجد، وإلا الرئيسية — قاعدةُ `resolve_reminder_recipient` نفسها
مثبَّتةً في استعلامين). شخصٌ مستلِمٌ لزبونين يأخذ **رسالةً واحدة** فيهما، وبنودُها
مفصولةٌ بسطرٍ فارغ. و`reminder_merge_daily=False` يقلبها رسالةً لكل بند. والنصُّ
يُبنى بلغةِ **المستلِم** لا لغةِ المكتب. وجهةٌ بلا هاتفٍ تظهر أيضاً (`has_phone`)،
والشاشةُ تُقفل زرَّ الواتساب بنصّه («رقم غير صالح للواتساب») ولا تُخفي الصفّ.

**الحواجزُ تُطبَّق عند القراءة لا تُلغي التذكير (D5، D8)**: يومُ راحة الزبون
(`rest_days` المحلولة له)، وعطلةُ المكتب (`OfficeHoliday`)، وتأجيلُ الزوج
(`ReminderPostpone` — أحدثُ صفٍّ، و`until=None` يمسح)، ورفضُ الإذن
(`Contact.allows_reminder`) — كلُّها تُسقط البندَ **اليوم** فيظهر أوّلَ يومٍ مسموح
بعده من الحساب نفسه. **ولا تقويمَ عطلٍ وطنيّ يُخترَع**: المكتبُ يكتب عطلَه.

**الإذنُ على الجهة (D2)**: `reminders_consent` و`consent_types` و`consent_on`
و`consent_channel` — والسحبُ يكتب تاريخَه ومَن سحبه **ولا يمحو الإذن**: المكتبُ
يعرف كم أُرسل قبل أن يتغيّر الرأي. والجهةُ الجديدة تأخذ أنواعَ المكتب الافتراضية
(`reminder_default_consent_types`) **نسخةً** عند الإنشاء، فتغييرُ الإعداد بعدها لا
يعيد كتابة مَن أذن قبله. والكتابةُ بفعل `consent/` وحده فتسلك حارسَ الخدمة.

**النصوصُ (D3)**: `REMINDER_DEFAULT_TEXTS` في الكود — **عربيٌّ وعبريٌّ لكلٍّ من
الأنواع الأربعة** من بحث #256 §5، ومكتبٌ يغلبه بصفٍّ في `ReminderTemplate`.
والرموزُ ستةٌ بالضبط: `{client_name}` `{period}` `{due_date}` `{amount}`
`{missing_list}` `{office_name}` — ونصٌّ يحمل غيرها **يُرفَض عند الحفظ باسمه**،
و`render_reminder_body` يستبدل بـ`str.replace` وحده: `str.format` على نصٍّ يكتبه
المستخدم قوسٌ زائدٌ فيه يُسقِط الطلبَ 500. **ونصُّ (ب) في البحث ينادي
`{deadline_name}` وهو خارج الستّة**، فالمشحونُ يقول «موعد التقديم» — ومولّدُه
موجودٌ منذ #281 (`_reminder_render_values` يحمل قيمَه الستّ للأنواع كلها).
**و`{due_date}` يومٌ قادمٌ لا يومُ الاستحقاق المحسوب**: يُطبَع في النصّ
`day + interval_days` بصيغة `dd/MM/yyyy` — يومُ التذكير التالي — لأن `next_due`
هو اليومُ أو قبله بحكم شرط الظهور، وبعد عطلةٍ أو تأجيلٍ يصير ماضياً فيطلب النصُّ
ورقةً بتاريخٍ مضى. ويبقى `due_date` في بند الشاشة `ISO` بيومه المحسوب، فهو مفتاحُ
العدّ لا نصُّ رسالة.

**السجلُّ إلحاقيّ (D4)**: `ReminderLog` لا يعرف `PUT` ولا `PATCH` ولا `DELETE`
(405)، ولا يُكتب صفُّه إلا من `mark_reminders_sent`/`mark_reminders_manual`/
`dismiss_reminders` و`undo_reminder_log` — نقطةُ الكتابة واحدةٌ في الخدمة
(`_write_reminder_logs`)، وكلُّ بندٍ يحمل مستلِمَه فيها فتُنحّى بنودٌ كثيرةٌ
باستعلامِ بياناتٍ واحدٍ و`bulk_create` واحد. **وما تُرجعه الدالةُ يُعاد قراءتُه
بالحقل `batch`** (استعلامٌ واحد) لا ما أرجعه `bulk_create`: MySQL لا يُسنِد
المفاتيحَ بعده، فكان الجوابُ يخرج بـ`id: null` ولا تتراجع الشاشة. والقنواتُ معلَنةٌ في الشكل كذلك:
`sent` واتسابٌ وحدها (والفراغُ يعنيها) وأيُّ غيرها 400، و`manual` تلفونٌ أو
زيارة. و`recipient_name`/`recipient_phone` **لقطة**: تغييرُ
الهاتف بعدها لا يعيد كتابة التاريخ. و«ما انبعتت» صفٌّ جديدٌ يشير إلى ما يُبطله،
وإبطالُ `undo` يُرفَض 400 فلا يدور السجلُّ في حلقة. و`serializer_class` النقطةِ
سطرٌ للقراءة (`ReminderLogSerializer`) لا حمولةُ تأجيلٍ للكتابة.

**التصعيدُ بعد الحدّ (D11)**: داخل `refresh_office` كتنبيهات التأخير، و`ref_key`
هو `"reminder:<زبون>:<نوع>:<بداية الفترة>:<نهايتها>"` — **بطرفَي الفترة لا
ببدايتها وحدها**: الفترةُ السنوية تبدأ في 1 يناير كما يبدأ كانون الثاني، فمفتاحٌ
بالبداية يجعل تنبيهَ السنة وتنبيهَ الشهر صفّاً واحداً فيُسقط أحدهما الآخر من
الجرس بلا أن يُقرأ. وصلَ العدُّ `max` وحان يومُ التذكير
التالي ⇒ `reminder_limit_reached` للمسؤول (وإن غاب فصاحبُ المكتب، بقاعدة
`_alert_recipient_ids` نفسها)، وبعد `reminder_escalation_owner_days` (افتراضُه 2)
⇒ `reminder_limit_reached_owner` لأصحاب المكتب. الرسالةُ تسمّي الزبون والفترة
والعدد **بلا مبلغ**. **ويُسقطهما اكتمالُ الأوراق عند القراءة** كما يُسقط التقديمُ
تنبيهَ التأخير: `_live_reminder_alert_refs` تقرأ مراجعَ ما لم يكتمل **للزبائن
الذين لهم تنبيهُ تذكيرٍ قائمٌ وحدهم** — استعلامٌ فرعيٌّ واحد بـ`client_id__in`،
ففتحُ الجرس لا يمسح جدولَ الأوراق كلَّه — وتُطبَّق في
`_visible_alerts`، والصفُّ يبقى في القاعدة. والفرادةُ في القاعدة تحرس تكرارَ
اليوم نفسه.

**الكلفةُ ثابتة**: `_reminder_candidates` عددٌ ثابتٌ لا يكبر بعدد الزبائن
(الرؤية · إعداداتُ الزبائن · مستلِمو الأنواع · الرئيسية ·
صفوفُ الأوراق · السجلُّ · التأجيلات · العطلة · التنبيهاتُ القائمة)، ونصوصُ المكتب
تُقرأ مرّةً للنوع. **وإعداداتُ الزبائن تُقرأ مرّةً واحدةً للحمولة**:
`resolve_settings_for_clients` تجمع مفاتيحها في استعلامين — تخصيصاتُ الزبائن
وقيمُ المكتب — بالحارسين نفسيهما (`validate_level` و`_assert_client_of_tenant`)،
وتُمرَّر محلولةً إلى حساب الإيقاع وحجبِ يوم الراحة وبناءِ النصّ: لا محلّلٌ موازٍ
يُعيد ترتيبَ القراءة بلا حارسيها، ولا قراءةٌ ثانيةٌ تفترق عن الأولى. اختبارٌ يقارن
العدَّ لزبونٍ واحدٍ بخمسة، وآخرٌ يثبت أن النداءَ مرّة.
**وعدّادُ «جاهز للإرسال» في «اليوم» لم
يُضَف**: حسابُه يجرّ هذه الاستعلاماتِ إلى شاشةٍ تقرأ جدولَ الالتزامات وحده،
فلا يصحّ فيه شرطُ «بنفس الاستعلامات الثابتة» (قرارُ #280/D9 — يُذكر هنا ليُعرف أنه
مُتعمَّد لا منسيّ).

**والأنواعُ الأربعة في الإعدادات والقوالب فقط (D1)**: المُولَّدُ اليوم **أوراق ناقصة**
و**موعدٌ قريب** و**موعدٌ رسميٌّ قريب** (#281)، ويبقى **`balance`** بنصّه وإعداده
ومستلِميه وبلا مولّد حتى تذكرته (#285) — فطلبُ قائمته يُعيد فراغاً لا بنوداً بنصٍّ
لا يخصّها.

**وهجرة `0010_reminders_and_consent` إضافيّةٌ محضة**: ستةُ `AddField` على
`Contact`، وأربعةُ `CreateModel`، و`AlterField` على اختيارات `OfficeAlert.kind`
(لا تبديلَ عمود). بلا `RemoveField` ولا `DeleteModel` ولا `RunSQL`.

## المواعيد وتذكيرا الموعد والموعد الرسميّ (#281)

**الموعدُ حجزُ موظّفٍ لا حجزُ زبون** (`ClientAppointment`): `scheduled_at` لحظةٌ لا
تاريخ — موعدا العاشرة والثانية في اليوم نفسه يترتّبان بوقتهما لا بترتيب كتابتهما —
والأنواعُ أربعة (`visit`/`call`/`signature`/`papers`) وتسمياتُها وتسمياتُ الحالات
من الخادم، والحالاتُ ثلاث (`scheduled`/`done`/`cancelled`) **ولا حذف**: الإلغاءُ
يكتب حالةً وتاريخَها، و`confirmed_at` وقتُ تسجيل التأكيد. تُحجز من ملفّ الزبون
**ومن التقويم**، والقراءةُ من `visible_clients` وحدها (موعدُ زبونٍ لا يراه العضو
**404** لا 403)، والكتابةُ بمفتاح `office.clients.write`.

**«ابعت تأكيد» رسالةٌ بالسجلّ القائم (د4)**: `send_appointment_confirmation` تحلّ
المستلِم بقاعدة `resolve_reminder_recipient` نفسها وتكتب صفَّ `ReminderLog` بنوع
`appointment` (مفتاحُه يومُ الموعد بطرفيه) وتختم `confirmed_at` — لا جدولَ رسائلٍ
ثانٍ ولا نصَّ ثانٍ في الواجهة. **ومتاحٌ من التقويم كما هو من الملفّ**: شريحةُ الموعد
في `OfficeCalendarScreen.tsx` تحمل الزرَّ نفسه، ينادي `confirmAppointment` نفسَها،
ويستبدل السطرَ العائد (`confirmed_at` الجديد) في حالة الشاشة بلا إعادة تحميل،
ورفضُ الخادم (زبونٌ بلا جهةٍ بهاتف، **400** برسالةٍ تدلّ على ما يُضاف) يصل نصُّه
مفهوماً ولا يُكتب صفُّ `sent` إلى لا أحد.

**ولا محرّكاً موازياً للتذكير (د3)**: مولّدا `appointment_reminder_candidates`
و`deadline_reminder_candidates` في `accounting_office/appointments.py` يُرجعان
`services.ReminderCandidate` فتسري عليهما حواجزُ «جاهز للإرسال» كلُّها — الموافقةُ
ويومُ الراحة وعطلةُ المكتب والتأجيلُ والحدُّ الأقصى — **ونوعُهما يُمرَّر إليهما**:
طلبُ `ready-to-send/?reminder_type=documents` لا يعرض بندَ موعدٍ ولا موعداً رسمياً،
وكلُّ مولّدٍ يُعيد فراغاً لنوعٍ ليس نوعه.

**والنافذةُ لا العدّاد** (جولة التصليح الأولى): كلُّ مولّدٍ يفتح **نافذةً من اليوم**،
والبندُ مستحقٌّ إن لم يكن في السجلّ صفٌّ مؤقّت (`REMINDER_TIMER_KINDS`:
`sent`/`manual`/`dismissed`) **يومُه داخل النافذة السارية** — أما صفٌّ بعد اليوم
المحسوب فلا يُحسب، فالحسابُ «كما في ذلك اليوم».
- **الموعد**: `window_start = slot_day - appointment_reminder_days` (إعدادُ مكتبٍ
  يُخصَّص للزبون)، والبندُ بين `window_start` و`slot_day`، و`maximum` واحد.
- **الموعد الرسميّ**: موضعا `(7، 2)` نافذتان، والساريةُ هي **آخرُ إزاحةٍ بلغها
  اليوم** (`day >= due - 2` تلغي السبعة)، والبندُ بين بدايتها و`due`. و`step`/`max`
  من **موضع النافذة** (١ من ٢ ثم ٢ من ٢) لا من عدد الصفوف.
والعدُّ وحده كان **يُسقط «شيل»** (لا يُعدّ) فتعود التنحيةُ كلَّ يوم، **ويُكرِّر
الرسالةَ في اليوم نفسه** (إزاحةٌ أضيق بعد أوّل صفّ)، **ويستهلك تأكيدُ الموعد نافذةَ
تذكيره** فيمنع «قبله بيوم» أبداً. والتصحيحُ تمريرُ `by_pair` (الصفوفُ بأيامها
وأنواعها) لا `counted_by_pair`، فيحسب كلُّ مولّدٍ نافذته بنفسه.

**بندٌ واحدٌ لكل (زبون، فترة)** — مولّدُ الموعد الرسميّ: التزامان في الفترة نفسها
(ق.م + ضريبة دخل) كانا بندين بمفتاحٍ واحد `(client, reminder_type, period_start,
period_end)` ⇒ تحذيرُ مفاتيحَ مكرَّرة في React، وعدّادٌ مشتركٌ يُسقط «قبل ٢». فتُجمع
التزاماتُ الفترة في **بندٍ واحد**: **أقربُ موعدٍ لم يمضِ بعد** (`>= day`) بين
التزاماتها **التي عليها شيء** (`client_owes`) وحدها — `extended_to or
actual_deadline` — يفتح نافذته. **لا أبكرُ التزامٍ في الفترة** (جولة التصليح الثانية):
التزامٌ مدفوعٌ موعدُه 3 شباط وآخرُ عليه 620 موعدُه 10 شباط كان يعرض «موعد التقديم
03/02» ومن 4 شباط يُسقط `day <= due` الفترةَ كلَّها فلا يصل «قبل ٧» ولا «قبل ٢» عن
10 شباط أبداً؛ وكذلك التمديدُ حين يكون في الفترة التزامٌ منتظِرٌ مضى موعدُه. فمن لا
شيءَ عليه لا يُذكَّر بموعده، وما مضى موعدُه متأخّرٌ يخصّه التنبيهُ الأحمر
(`obligation_late`)، وإن لم يبقَ للفترة موعدٌ قادمٌ عليه شيء فلا بند. وأسماءُ الناقص
اتّحادُها (وهو `missing_by_period` المشترك أصلاً)، والمبلغُ مجموعُ المستحقّ غيرِ
المدفوع على التزاماتها. **ولا يُغيَّر `_reminder_item_payload` ولا مفتاحُ البند**:
التجميعُ في المولّد وحده. **ومثلُه تذكيرُ الموعد: بندٌ واحدٌ لكل (زبون، يوم)** —
موعدان للزبون في اليوم نفسه كانا بندين بالمفتاح `(client, appointment, slot_day,
slot_day)` نفسه (مفتاحُ React مكرَّر، وإرسالُ أحدهما يُسكت الآخر)، فيُجمعان في
بندٍ بوقتَيهما في `period_label` («10:00، 14:00»)، ورسالةٌ واحدة تُسكتهما.

**والمبلغُ في النصّ**: `ReminderCandidate.amount` (`Decimal | None`) يُملأ في مولّد
الموعد الرسميّ بالمجموع ويبقى `None` في مولّدي الأوراق والموعد، ويعرضه
`_reminder_render_values` بخانتين كما تعرضها مبالغُ الموديول (`620.00`). ونصُّ
`REMINDER_DEADLINE` المشحون أُعيدت صياغته عربيًّا وعبريًّا **سطراً لكل قيمة** («أوراق
ناقصة: …» و«مبلغ مستحقّ: …»)، والقيمةُ الغائبةُ تُنطق `REMINDER_ABSENT_TEXT` بلغة
المستلِم («ولا شي» / «אין») لا فراغاً: النصُّ مسطَّحٌ بلا شرطٍ لا يحذف عنوانه، فبدونها
يبقى العنوانُ معلَّقاً وتُقرأ الجملةُ القديمة «منك  قبل ما نقدّم» بفراغين. والرموزُ
تبقى ستّةً بلا رمزٍ جديد. **وعُرفُ الغياب واحدٌ** (`services.reminder_absent_text`):
نصُّ «ابعت تأكيد» (`_appointment_render_values`) يُنطق `{period}` و`{amount}` و
`{missing_list}` الغائبةَ بلغة جهته بالكلمة نفسها، لا فراغاً هناك و«ولا شي» هنا.

**المبلغُ في نصّ الرسالة استثناءٌ مقصودٌ من قناع `office.amounts.view`.** نصُّ «جاهز
للإرسال» (`ready_to_send_payload` ← `messages[].body`) ووصفُّ السجلّ المحفوظ
(`reminder_log_row` ← `body`) يحملان «مبلغ مستحقّ: 620.00» **ولو لعضوٍ بلا
`office.amounts.view`**: النصُّ رسالةٌ إلى **الزبون نفسه** عن مبلغٍ عليه، وقنعُه عن
الموظّف يُرسل «—» إلى الزبون بدل مبلغه. وما سوى النصّ يبقى مقنَّعاً: جذرُ `items` في
الحمولة بلا مفتاح مبلغٍ (لا `amount` في `_reminder_item_payload`). فالقاعدةُ «كلُّ
مبلغٍ يمرّ بالقناع» **لها هذا الاستثناءُ الواحد** — ويبني عليه #285 (رصيدُ الزبون في
نصّ تذكيره) قراراً لا افتراضاً، وأضاف **استثناءً ثانياً صريحاً**: أسطرُ «إشعار الدفع»
ومجموعُه في `items[].notice` مكشوفةٌ لأن الإشعارَ نفسَه هو المخرَجُ الموجَّه للزبون.
يثبّته `test_the_message_text_carries_the_amount_to_a_member_without_amounts_view`،
وللاستثناء الثاني اختبارٌ صريحٌ الآن:
`test_a_member_without_the_amounts_permission_still_reads_the_notice_amounts` في
`test_payment_notice.py` (دورُ `accountant` — لا يملك `office.amounts.view`) يؤكّد
`notice["total"] == "620.00"` ومبلغَ السطر ونصَّ الرسالة.

**التأجيلُ يمسح `confirmed_at`**: `reschedule_appointment` تكتب `confirmed_at = None`
— الموعدُ صار وقتاً آخر فتأكيدُه القديمُ لم يعد تأكيداً له، والتقويمُ يخفي زرَّ «ابعت
تأكيد» متى وُجد `confirmed_at`، فبلا المسح لا يُعاد التأكيدُ بعد «أجّل».

**والتقويمُ لا يقول «لا مواعيد» ومعه مواعيد**: `OfficeCalendarScreen.tsx` يعرض
حالةَ «لا مواعيد في هذا المدى» حين يخلو المدى من الالتزامات **والمواعيد معاً**
(زبونٌ جديدٌ بلا خدمات يُحجز له موعدٌ من التقويم نفسه فلا يختفي ومعه زرُّ تأكيده)،
وفشلُ التحميل يُفرِّغ `appointmentRows` مع `rows`.

**والشرطُ الحاسم**: لا تذكيرَ بموعدٍ رسميٍّ إلّا إذا **على الزبون شيء** —
`client_owes` نقيّةٌ ومفردة: «انقدّم»/«مش لازم» يُسقطانه، وأوراقٌ ناقصةٌ تكفي وحدها،
ومبلغٌ مدفوعٌ («الزبون دفع») أو مرتجعٌ («إلنا» لا «علينا») لا يُذكَّر به.

## إشعار الدفع — مركَّبٌ على «موعد رسمي قريب» (#285)

**إشعارٌ واحدٌ لكل (زبون، تاريخ استحقاق)** يجمع ما على الزبون في ذلك التاريخ، كلٌّ
بسطر، مع المجموع واتجاهه. **ولا نوعَ تذكيرٍ خامس (د1)**: `payment_notice_attachments`
(`accounting_office/appointments.py`) تُركَّب على بنود «موعد رسمي قريب» القائمة **بعد
حواجزها كلّها**، ويُرافق نصُّها `body` في `_reminder_message`، ويُوسَّع بندُ الحمولة
بحقل `notice`. **والرموزُ الستّةُ لا تُمَسّ** (`REMINDER_PLACEHOLDERS`): النصُّ يُبنى
في بايثون لا في قالبٍ يكتبه المكتب.

**والإشعارُ مفتاحُه (زبون، تاريخ) لا (زبون، بند).** البندُ يُفتح لكل (زبون، **فترة**)
— ربعيّةٌ وشهريّةٌ تستحقّان في 15 تعطيان بندين — والرسالةُ تُجمع للمستلِم. فركوبُ
الإشعار على كلّ بندٍ كان يُخرج العنوانَ والمجموعَ **مرّتين** في رسالةٍ واحدة
و`items[]` بإشعارين متطابقين. الحارسُ في `_with_payment_notices`: مجموعةُ مفاتيح
`(client.pk, render_due)`، والإشعارُ على **أوّل** بندٍ لكل مفتاحٍ وحده والباقي
`notice=None` (والبندُ نفسُه باقٍ بنصّه). يحرسه
`test_two_periods_owing_on_one_date_carry_one_notice_not_two`.

**التجميعُ على `due_date` لا على الفترة (د3)**: قد يوافق تاريخٌ واحد فترتين (ربعيّةً
وشهرية)، فمفتاحُ الإشعار (زبون، تاريخ). والإشارةُ من `direction` القائم — «عليه»
موجبٌ و«إله» سالبٌ — والمجموعُ مجموعُ الأسطر بإشارتها.

**وشرطُ السطر ثلاثةٌ لا اثنان:** `status=pending` · **`client_paid=False`** · مبلغٌ
غيرُ صفر. والمدفوعُ («الزبون دفع») خارجَ الأسطر كما في `_period_unpaid_total`
و`client_owes`: الإشعارُ يقول «مستحقّ»، وما دفعه الزبونُ ليس مستحقّاً. (نصُّ د3 في
الموجز ذكر الشرطين الأوّل والثالث، والثاني هو الصحيح ويُثبَّت هنا وفي docstring
`payment_notice`.) والالتزامُ المنتظِرُ بمبلغٍ صفرٍ سطراً لا يفتح.

**والكلفةُ ثابتة (#285/م٥).** مواعيدُ الضرائب تتجمّع في يومٍ واحد (15)، فبناءُ
الإشعار لكلّ بندٍ كان يدفع ثلاثةَ استعلاماتٍ لكلّ زبونٍ في كلّ فتح (التزاماتُ البند،
و`create_share` باستعلامَيها، ثم `INSERT`ين) — مكتبٌ بـ300 زبون ≈900 استعلام.
الآن: **استعلامُ `Obligation` واحد** لكلّ أزواج الحزب/التاريخ (`client_id__in` مع
`Q(extended_to__in=…) | Q(extended_to__isnull=True, actual_deadline__in=…)` والتجميعُ
على المفتاح الدقيق في بايثون — وشرطُ `IN` أعرضُ من الأزواج فالتجميعُ لازم)،
و**استعلامٌ واحدٌ للروابط الحيّة** بـ`doc_id__in` ثم `create_share` للناقص وحده، و`payment_notice`
المفردة تبقى غلافاً للصفحة العامة (`payment_notices` بأزواجه). وعلى المنوال نفسه
يُقرأ `can_share_payment_notice` **مرّةً واحدة** لا مرّةً لكلّ زوج. يحرسه
`PaymentNoticeCostTest` في `test_payment_notice.py` (زبونٌ مقابل خمسة **بعد** وجود
الروابط): العددُ نفسه.

**الألوانُ ثابتةٌ لا إعداد**: `payment_notice_tone(amount, threshold)` نقيّة —
موجبٌ `owed` (أحمر، «عليك»)، سالبٌ `refund` (أخضر، «إلك»)، و`|المبلغ| ≤ الحدّ`
`neutral` (رماديّ، شاملٌ ويغلب على الاثنين). ومرآتُها في الواجهة `paymentNoticeTone`
(`frontend_v2/utils/accountingOffice.ts`) تُختبر بـ`node --test`، فلا قاعدةَ لونٍ
ثانيةٍ في القالب. والتسميتان `owed`/`refund` هما مفردتا الاتجاه، و**`refund` لا `due`**
لأن `due` في هذا الموديول تعني «عليه». **والتأكيدُ على العنصر لا على الورقة**: `<style>`
يحمل `.pn-owed`/`.pn-refund`/`.pn-neutral` في كل صفحة، فـ`assertIn("pn-owed", html)`
كان ينجح ولو قُلب اللون؛ الأسطر الآن تُطابق `<span class="pn-owed">1,500 عليك</span>`
و`<td class="num pn-owed">1,200</td>` و`class="num pn-refund"` و`<span class="pn-neutral">`،
وأُثبت سقوطُ كلٍّ منها بقلب اللون قبل اعتمادها.

**ثلاثةُ إعداداتٍ في السجلّ** (مستوى المكتب والزبون، مجموعة «التذكيرات»):
`payment_notice_attach` (منطقيّ، افتراضُه نعم) · `payment_notice_format`
(`text`/`pdf`/`both`، افتراضُه `both`) · `payment_notice_gray_threshold` (عددٌ صحيح،
افتراضُه 10، والسالبُ مرفوض). وتُقرأ **لكل زبون** في مسحة الحساب نفسها
(`_REMINDER_CLIENT_KEYS`): إطفاءُ الإرفاق لزبونٍ يُخرج إشعارَه من رسالته وحدها
ويُبقي بندَ الموعد كما هو.

**والورقةُ نوعُ مستندٍ جديد في `docshare`** (`payment_notice`): جمهورُه الزبون
وصلاحيتُه `office.clients.write`، و`doc_id` **التزامٌ** لا زبون — `create_share`
و`resolve_share` تُمرّر `(tenant_id, doc_id)` وحدهما، ومن الالتزام يُشتقّ (الزبون،
تاريخُ الاستحقاق) فيُبنى الإشعار، **بلا حقلٍ إضافيّ في `DocumentShare`** وبلا هجرةٍ
إلا توسيعَ `choices` (`docshare/migrations/0007_payment_notice_doc_type.py`). و`page`
يُصيِّر أسطرَ الورقة ملوّنةً لأن قائمةَ `line_row` البيضاء لا تحمل حقلَ نبرة.
**والنوعُ مرخَّصُ الوحدة ونطاقُه في سطح الإدارة مضبوط** (`"module"` و`"scope"`،
ولا يُنشَأ من الباب العامّ) — التفصيلُ في `modules/docshare.md`.

**ولا قيدَ محاسبيّ ولا `post_journal` (د7)**: الإشعارُ عرضٌ ورسالة. والرابطُ يُنشَأ
أوّلَ مرّةٍ في مسار القراءة («جاهز للإرسال»)، لأن نصَّ الرسالة يجب أن يكون نهائياً
**قبل** الإرسال؛ والتكرارُ آمن (`dedupe` في `create_share` يعيد الرابطَ الحيّ).

**قيودٌ معروفة، مسجَّلةٌ لا مُصلَحة** (قرارُ منتج أو تذكرةٌ لاحقة، فلا يُعاد اكتشافُها):

- **رقمان في رسالةٍ واحدة**: «مبلغ مستحقّ» من #281 و«المجموع» من #285 قد يختلفان
  (الأوّل مجموعُ الفترة، والثاني مجموعُ التاريخ) — قرارُ منتجٍ مفتوح.
- **`total == 0`**: يُعرض «المجموع: 0.00» بلا كلمةٍ تفسّره.
- **القيمةُ الاحتياطية `.get(client_id, 0)`** في `payment_notice` تخالف افتراضَ
  السجلّ (10) حين يتعذّر حلُّ الإعداد — أثرُها لونٌ رماديّ لحدٍّ صفر.
- **مصدران لعائلة `PAYMENT_NOTICE_FORMAT_*`**: `settings_registry` و`services`.
- **`tax_file_number`** في حمولة الإشعار ولا يظهر على الورقة، والوثيقةُ تَعِد به.
- **الإشعارُ عربيٌّ دائماً** ولو كانت لغةُ الجهة عبريّة (النصُّ بلا جدول لغات).
- **ثمنُ التمديد (#277)**: رابطٌ أُنشئ ليوم 15/3 يعرض إشعار 15/4 بعد التمديد — مُعلَنٌ
  في `docshare/documents/accounting_docs.py`، والتاريخُ ظاهرٌ فلا خداع.
- **`notice` غيرُ مكتوبةٍ في أنواع TS ولا مستهلكَ لها اليوم** — المرآةُ تتبع الخادم
  حين تُبنى الشاشة.

## دفتر الزبون (#286 — الجزء أ: الخادم)

**الدفترُ دفترُ منشأةِ الزبون، لا دفترَ المكتب.** `accounting` هو دفترُ الشركة
المالكة للمستأجر (المكتبُ نفسه): قيودُه وميزانيتُه وإقرارُه. ودفترُ الزبون سجلُّ
منشأةٍ أخرى يمسك المكتبُ دفاترها خدمةً لها. فالقيدُ هنا **لا يمرّ بـ`post_journal`**
ولا يمسّ `JournalHeader`/`JournalLine` — **استثناءٌ صريح** من القاعدة الملزِمة،
وسببُه والبديلُ المرفوض في `docs/decisions/client_books.md`. ويحرسه
`accounting_office/tests/test_client_books.py`: مسحُ `ast` لملفّ الخدمات وملفّ
النماذج يسقط على أوّل استيرادٍ من `accounting`، واختبارٌ ثانٍ يثبت أن الحارسَ يسقط
على مخالفةٍ مصطنعة (فلا يصير المسحُ أعمى بلا إشعار).

**الترقيمُ بلا فجوات وتحت قفل.** `_next_number` يقرأ `ClientBookSequence`
بـ`select_for_update` داخل `transaction.atomic`، ويزيد `last_number`، وينسخه إلى
`BookEntry.number`. **لا `MAX(number)+1` ولا `count()+1`**: كلاهما يقرأ لقطةً قديمة
تحت التزامن فيُكرّر رقماً أو يُحدث فجوة. وفوق القفل قيدُ فرادةٍ
`(client, year, number)` — طبقةٌ ثانية تُسانده. والاختبارُ يُثبت **ترتيبَ الأحداث**
لا مجرّد انتظار: قراءةُ العدّاد وزيادتُه تسبقان إدراجَ الحركة، والرقمُ يُقرأ من
الصفّ المقفول لا من كائنٍ محفوظٍ في بايثون (تُدفع `last_number` إلى 41 فتأتي
الحركةُ التالية 42 لا 2). ويُعلن اختبارُ التزامن على اتصالين **تخطّيه** على SQLite
(لا `select_for_update` فيها) بدل أن يوهم بمرور.

**ولا حذف.** لا `DELETE` على دفترٍ ولا على حركة: `http_method_names` في
`OfficeClientBookViewSet` تسمح بالقراءة والإنشاء وحدهما، ومساراتُ التفصيل موجودةٌ
عمداً كي يردّ الحذفُ **405** لا 404. والتصحيحُ حركةٌ عكسية (`BookEntry.reverses`)
ببنودٍ مدينُها دائنُ الأصل والعكس، والأصلُ يبقى، و`BookEntry.client_book` على
`PROTECT` فلا يُطوى الدفترُ من تحت تاريخه. **وعكسٌ واحد لكل حركة:** `reverse_entry`
يقفل صفَّ الأصل بـ`select_for_update` داخل `transaction.atomic` **قبل** فحص «لها
عكسٌ بالفعل» — فحصٌ بلا قفلٍ يمرّ لطلبين متقاربين فتُكتب حركتان عكسيّتان ولا حذفَ
يُصلحهما — وفوق القفل `reverses` **`OneToOneField`** فرادةً في القاعدة. والاختبارُ
يُثبت ترتيبَ الأحداث (القفلُ قبل الفحص) وفرادةَ القاعدة، ويُعلن اختبارُ عكسين متزامنين
على اتصالين تخطّيه على SQLite.

**نوعُ الدفتر وانتقالُه (د7).** `simple`/`double` يُضبط عند الإنشاء. والانتقالُ من
البسيط إلى المزدوج **من بداية سنةٍ فقط**: يُرفض في سنة الفتح، ويُرفض إن وُجدت حركاتٌ
في السنة الجارية، ويُسجَّل `kind_changed_on` يومَ التغيير. والرجوعُ من المزدوج إلى
البسيط مرفوضٌ دائماً.

**النوعُ يُقرأ في تاريخ الحركة لا في تاريخ اليوم.** `kind_on(book, day)` يُعيد
البسيطَ لتاريخٍ يسبق `kind_changed_on`، والنوعَ الحاليَّ بعده — فحركةُ عهدٍ بسيطٍ
تُدخَل وتُعكس بقاعدة عهدها بعد الانتقال. والتوازنُ يُفحص بها على `entry_date`،
**والعكسُ يُقاس بنوع تاريخه، وبتاريخ الأصل افتراضاً** — لا إعفاء: عكسُ حركةِ طرفٍ
واحد مؤرَّخاً في سنة المزدوج 400، وإلا اختلّ ميزانُ تلك السنة. حُرِّر هذا بعد مراجعة:
بلا قراءةِ `kind_changed_on` كان عكسُ كل حركةٍ قديمة يردّ 400 «غير متوازنة»، وتُجبَر
ورقةٌ متأخّرةٌ لسنةٍ بسيطة على قيدٍ مزدوج متوازن.

**والانتقالُ يُكمل الشجرة.** `sync_client_tree` ينسخ **الأكوادَ الناقصة** من شجرة
النوع الجديد داخل المعاملة نفسها بتمريرتين (الآباءُ قد يأتون بعد الأبناء، وأبو
الحساب المضاف قد يكون قائماً) ولا يمسّ القائم. بلا هذا يبقى الدفترُ المحوَّل بلا
`2000`/`2100`/`2200`/`3000`/`5300`، فأوّلُ بندِ ضريبةٍ أو شراءٍ بالآجل يُرفض 400.

**الشجرةُ تُنسخ نسخةً واحدة (د6).** عند الإنشاء: من `OfficeBookAccount` للمكتب إن
وُجد، وإلا من `BookAccountTemplate` لـ`(النظام الضريبي، نوع الدفتر)` — والنظامُ من
المحلّل (`resolve_setting`) لا من حقلٍ ثانٍ في البطاقة. **لا مرجعَ حيّ**: تعديلُ
القالب لاحقاً لا يغيّر شجرةَ زبونٍ قائم.

**الدفترُ يوجد فقط مع مسك الدفاتر (د5).** وجودُه مشتقٌّ من خدمة
`SERVICE_CODE_BOOKKEEPING` بحالة `status_on` القائمة — لا حقلَ «هل له دفتر» يناقضها.
بلا الخدمة: الإنشاء 400. وبعد إيقافها: الدفترُ للقراءة، وكلُّ كتابةٍ عليه 400.

**والدفترُ يُفتح من تبويب «الدفتر».** `POST client-books/` كان لا يستدعيه إلا
الـviewset بلا شاشةٍ تنشئ دفتراً ولا دفترَ يُنشأ مع الخدمة — فكلُّ زبونٍ يرى «ما
في دفتر»، و«للإدخال» مقيَّدةٌ خادمياً بالدفاتر القائمة فتبقى صفراً. فحالةُ `noBook`
في `OfficeClientBook.tsx` تعرض لمن يملك `office.clients.write` منتقيَ النوع
وتاريخَ الفتح وزرَّ «افتح الدفتر» (`createClientBook`)، و`reload()` بعد 201،
ورسالةُ الخادم تُعرض كما هي (400 لزبونٍ بلا مسك دفاتر أو دفترٍ قائم).
**وتسمياتُ الأنواع من `client-books/choices/`**: `book_kinds` لا يحملها أيُّ ردٍّ
آخر (`kind_label` يسمّي النوعَ الحاليَّ وحده)، و`entry_kinds`/`account_types` مرآةُ
`BOOK_*_CHOICES`؛ ودالّتُها `choices_payload()` في `client_books.py` لا في
`views.py`، كـ`frequency_choices()`. وسطرُ الدفتر يحمل `entry_kind_choices` (لا
`kind_choices`: `kind` فيه نوعُ **الدفتر**) و`account_type_choices`، واختبارٌ في
`test_client_books.py` يقارن القائمتين بنموذجيهما حرفاً بحرف — سقوطُ الحقل صامتاً
لا يراه `tsc` (اختياريٌّ في الواجهة) فيصير منتقي نوع الحركة فارغاً وزرُّ «أدخل
الحركة» مقفلاً أبداً.

**«للإدخال» مشتقٌّ لا مخزَّن (د8/د9).** ورقةٌ بـ`DOCUMENT_STATUS_RECEIVED` **لا
حركةَ حيّةً لها** = «للإدخال»، مجمَّعةً بالزبون والشهر في `pending_entry_payload`
بـ`Exists` على `BookEntryDocument` في `WHERE` و`TruncMonth` على `period_start` —
**استعلامٌ واحد** لا حلقةَ N+1 (اختبارٌ يقارن العدَّ بزبونٍ واحدٍ بأربعة). ولا
عمودَ «انأدخلت»: بإدخال حركةٍ يُكتب رابطٌ للورقة، فتخرج من القائمة لأن الشرطَ صار
كاذباً. والشهرُ يختفي وحده حين لا تبقى فيه ورقةٌ واصلةٌ بلا إدخال.

**والورقةُ السنوية تُحسب مع الشهريّة.** `period_start` لها 1 يناير فتقع في صفّ
كانون الثاني، فنموذجُ الإدخال في الواجهة يقرأ `items` **و`annual`** معاً
(`pendingMonthDocuments`) ويُعرض السنويُّ في شهر بدء فترته وحده. قراءةُ `items`
وحدها كانت تُبقي صفَّ كانون الثاني عالقاً: يُفتح على «ما في أوراق بانتظار الإدخال»
ولا يُصفَّر أبداً. والبديلُ الأصحُّ على المدى الطويل اشتقاقٌ خادميٌّ بمعاملَي
`client` و`month` على `pending-entry/` نفسه (معاملٌ على المسار القائم لا مسارٌ
جديد)، ولم يُبنَ الآن لأن حمولةَ الخادم تجميعيّةٌ لا تُعيد معرّفاتِ الأوراق.

**أوراقُ الحركة رابطٌ لا عمود.** `BookEntryDocument` يقبل أوراقَ شهرٍ كاملة في
حركةٍ واحدة (طريقةُ «إدخال الشهر»)، وعكسُ الحركة **يُعيد أوراقها إلى «للإدخال»**
لأن الحركة المعكوسة ليست حيّة — بعمودٍ فريدٍ كانت الورقةُ تبقى «انأدخلت» أبداً ولا
يمكن ربطُها بالحركة الصحيحة. و«حركةٌ حيّةٌ واحدة على الأكثر لكل ورقة» تُفرض في
`create_entry` داخل `atomic` وبقفل `select_for_update` على صفوف الأوراق.

**ودفاترُ الخدمة الموقوفة لا تظهر في «للإدخال».** كلُّ إدخالٍ لها 400، فبقاؤها يعني
قائمةً لا تُصفَّر أبداً؛ ويُقيّدها `writable_client_ids` باستعلامٍ واحد ثابت.

**طريقةُ الإدخال إعداد (د10).** `book_entry_method` في
`accounting_office/settings_registry.py` بقيمتَي «ورقة ورقة» (`document`، وهو
الافتراض) و«إدخال الشهر» (`monthly`)، ويقبل تخصيصاً لكل زبون عبر المحلّل — لا حقلَ
في الدفتر يفترق عنه. وتُقاس لكل زبونٍ في حمولة الدفاتر بـ`resolve_setting_for_clients`
(استعلامان لا استعلامان لكل صفّ).

**العزل (د11).** كلُّ `get_queryset` يبدأ من `tenant` ويمرّ بـ`visible_clients`،
والدفترُ وحركاتُه تُطلب بمعرّف **الزبون** لا بمعرّف الدفتر. فزبونُ مكتبٍ آخر — أو
زبونُ زميلٍ لا يراه العضو — **404**، وحركةُ زبونٍ آخر في المكتب نفسه **404** كذلك.

**المبالغُ تمرّ بقناع `office.amounts.view`.** `debit`/`credit` مسجَّلان في
`AMOUNT_KEYS` (`BOOK_ENTRY_AMOUNT_KEYS`) — فتُقنَّع في القراءة **مع المجموعين
المشتقّين** `total_debit`/`total_credit` (قنعُ الحقلين وحدهما يترك الرقمَ في
المجموع)، ويُرفض إنشاءُ حركةٍ لمن لا يملك المفتاح **403** من
`_assert_can_write_amounts` (`PermissionDenied`، كعقد `reject_amount_writes`:
الحركةُ مبلغٌ بيد من يكتبها). و**القرارُ يُحسب مرّةً واحدة** في `amounts_masked`
وتُمرَّر نتيجتُه إلى `entry_row`: سؤالُ `can_see_amounts` لكل صفّ كان يكلّف أربعةَ
استعلاماتٍ إلى خمسة لكل حركة — خمسةُ آلافٍ لدفترٍ بألف حركة (وهو الخطأ نفسه الذي
أُصلح في `packages_payload`). و`user=None` الصريح وحده نداءٌ داخليٌّ بلا قناع —
كـ`services.tax_card_payload`، ومن نسي المستخدمَ يسقط.

**وأثرُ القناع التشغيليّ ومنحُه.** `office.amounts.view` يملكها `manager` و
`office_manager` وحدهما (`_OFFICE_MANAGER = _VIEW_ONLY | set(OFFICE_PERMISSION_KEYS)`،
ولا يملكها `accountant`). فمن يمسك الدفتر من غير هذين الدورين يُمنَح المفتاح من
**`RolePermission`** في قسم «الموظفون والأدوار» القائم — قرارُ المراجع: القناعُ
يمرّ، والمنحُ من هناك لا بمسارٍ جديد. (والقرارُ مسجَّلٌ في
`docs/decisions/client_books.md`.)

**وهجرة `0011_client_books` إضافيّةٌ محضة (د14):** ثمانيةُ `CreateModel` وثلاثةُ
فهارس وستةُ قيود، ثم `RunPython` لزرع شجرة المنصّة بعكسٍ يحذف أكوادَه وحدها. بلا
`RemoveField` ولا `DeleteModel` ولا `RunSQL`.

## الأتعاب — الاشتراك والمسودّات والاعتماد (#282، الجزء أ١: الخادم)

**الجزءُ أ١ يبني الحسابَ لا المستند**: مسودّةُ الشهر تُولَّد وتُعتمد هنا، وفاتورةُ
الأتعاب الورقية — الترقيمُ والحقولُ القانونية والإشعارُ الدائن ورابطُ PDF في
`docshare` وشاشةُ «المسودّات» — هي **أ٢**، والمعتمدةُ تُنتجها هناك. فلا
`FeeInvoice` في هذه الهجرة، ولا ترقيمَ، ولا قيدَ محاسبيّ (القيودُ #284)، ولا واجهة.

**طريقةُ الأتعاب إعدادٌ** (`fee_method`، مكتب ← زبون، الافتراضُ «اشتراك»):
`subscription` = الاشتراكُ الساري + إضافاتُ الشهر السابق، و`per_service` = مجموعُ
أسعار الخدمات التي استحقّت فتراتُها + الإضافات، و`hourly` **معروضةٌ مرفوضة**
(`services.FORBIDDEN_SETTING_VALUES` ⇒ 400 برسالتها على المستويين). و
`fee_auto_approve` مفتاحٌ **مقفلٌ مطفأٌ** مثل `reminder_auto_send` (400 على فتحه).

**ثلاثُ قواعدَ تحكم المسودّة:**
1. **السعرُ بتاريخ سريان** — `FeeSubscription` صفٌّ لكل تغيير، و`fees.subscription_on`
   تُعيد الصفَّ ذا أكبر `starts_on` لا يتجاوز **آخرَ الشهر**؛ فلا تعديلَ لصفٍّ سابق،
   ومسودّةُ شهرٍ مضى تبقى بسعرها.
2. **التناسبُ بعدد أيام الشهر الفعليّ — لا بثلاثين**: بدايةٌ في 16/نيسان (ثلاثون
   يوماً) = نصفُ الشهر تماماً، وفي 16/آذار (31) = 16/31. **والتناسبُ على حدود
   اشتراك الزبون لا حدود صفّ السعر**: صفٌّ يبدأ في منتصف الشهر يحكم الشهرَ كلَّه
   بسعره لأن صفَّ السعر السابق يغطّي أيامه الأولى (تغييرُ سعرٍ في 15/نيسان ⇒
   نيسان كاملة بسعرها الجديد، لا 400×16/30 وأياماً بلا فاتورة)، والتناسبُ من
   `starts_on` لأوّل صفٍّ أو لعودةٍ بعد إنهاءٍ وحدها (**والتغطيةُ يحكم بها الصفُّ
   الساري في اليوم السابق** لا أيُّ صفٍّ يغطّيه بحدّه: الإنهاءُ صفٌّ
   `starts_on = ended_on` ويبقى الأصلُ مفتوحاً، فعودةٌ بعده تُنسب من يومها). والانتهاءُ `ended_on`
   يُنسب في آخر الشهر بعدد أيامه ضمناً: صفٌّ `starts_on = ended_on = 20/5` ⇒ 20/31.
3. **التوليدُ مرّةً في الشهر** — `_generate_fee_drafts` داخل `refresh_office`:
   مسودّةٌ لكلّ زبونٍ **نشط**، تُولَّد لأوّل تشغيلٍ في الشهر (عمليّاً يوم 1)،
   وفرادةُ `(client, year, month)` تجعل التشغيلَ الثاني بلا أثر. **ولا مسودّة**
   لزبونٍ منتهٍ، ولا لشهرٍ يبدأ داخل إيقاف الفوترة، ولا لاشتراكٍ انتهى قبل الشهر،
   ولا لزبونٍ بلا سطرٍ واحد. **والإيقافُ يمنع المسودّةَ كلَّها لا سطرَ الاشتراك
   وحده** (في طريقة «اشتراك» وحدها، فالإيقافُ حقلٌ على صفّ الاشتراك): لا مسودّةَ
   فيها الإضافاتُ وحدها، وإضافاتُ الشهر الموقوف تنتظر أوّلَ مسودّةٍ بعد انتهاء
   الإيقاف. والكلفةُ **خطّيّةٌ** في عدد الزبائن النشطين: أصحابُ
   مسودّات الشهر يُقرؤون `client_id` مرّةً واحدةً ويُتخطّون قبل حساب السطور،
   فليس ثمّة استعلامٌ ولا `savepoint` لمن له مسودّة.

**والإضافاتُ (`FeeExtraService`)** تُسجَّل عند التنفيذ (`fees/extras/`): وجهتُها
«مسودّة الشهر القادم» (نُفِّذت في آذار ⇒ مسودّةُ نيسان) أو «فاتورة لحالها» فلا تدخل
مسودّةً. **ولكلٍّ `billed_draft`**: التوليدُ يقرأ ما نُفِّذ قبل الشهر ولم يُفوتر،
ويربطه بمسودّته **في المعاملة نفسها**، فإضافةٌ سُجِّلت بعد توليد مسودّة شهرها
تلحق أوّلَ مسودّةٍ تالية ولا تدخل مسودّتين. **وحارسُ التزامن** `billed_draft__isnull=True`
على تحديث الربط: إن سبقها تشغيلٌ متزامنٌ لشهرٍ آخر فلم تُربط كلُّ إضافات الزبون
تُتراجع مسودّتُه كلُّها (تلتقطها دورةٌ تالية) بدل أن تُحسب الإضافةُ مرّتين. وإلغاءُ المسودّة يُعيد `billed_draft`
`None` فتعود الإضافةُ إلى التوليد التالي. **والمسودّةُ لقطة** بعد ربطها: لا
يتغيّر مبلغُها بربطٍ أو سعرٍ لاحق.

**وأسعارُ خدمات الزبائن (`fees/service-prices/`)** هي مدخلُ طريقة
«سعرٌ لكل خدمة»: بلاها تُختار الطريقةُ ولا سعرَ لخدمةٍ فتُولَّد المسودّاتُ بلا
سطورٍ ويتوقّف المكتب بصمت. `POST` يُسعّر خدمةَ الزبون بمعرّفها (`client_service`)
أو بالخدمة والزبون معاً، وإعادةُ التسعير `POST` ثانٍ يُحدِّث الصفَّ الواحد
(`ClientServicePrice` `OneToOne` على الخدمة)؛ ولا `PUT`/`PATCH` ولا `DELETE`.

**والاعتمادُ دورٌ لا مفتاح**: `manager` و`office_manager` وحدهما
(`fees.FEE_APPROVER_ROLES`، والاسمُ من `core.access.OFFICE_MANAGER_ROLE`) —
`draft → approved` أو `draft → cancelled` قبل الاعتماد، **ولا حذف**. فاعتمادُ
محاسبٍ **403**، ومسودّةُ زبونٍ لا يراه العضو **404** (كالعزل في كل نقطة). والصفوفُ
تُقفل `select_for_update` قبل القراءة، فاعتمادان متزامنان لا يمرّان على المسودّة
نفسها. و«اعتمد الكل» (`fees/drafts/approve-all/`) يعتمد كلَّ منتظرةٍ **في المكتب**
(والملغاةُ لا تُعتمد) ويعيد `{approved, remaining, drafts}`، وبنودُ المسودّات
تُقرأ معها `prefetch_related` فلا استعلامَ لكل مسودّة.

**وتنبيهُ الثلاثة أيام**: مسودّةٌ منتظرةٌ مرّ عليها ثلاثةُ أيامٍ من **تاريخ
توليدها** ⇒ `OfficeAlert` بنوعٍ جديد `fee_draft_pending` ومرجعٍ واحد
`"fee_draft:<id>"` (`models.fee_draft_alert_ref`) لكل واحدٍ من المعتمِدين، ونصُّه
**بلا مبلغ**. ويسقط من الجرس باعتماد المسودّة **عند القراءة** (كأخبار الالتزامات):
الصفُّ يبقى أثراً، و`services._live_fee_draft_refs` تمنع عرضَه. و`generated_at`
يُكتب من **يوم التوليد الصريح** لا من ساعة النظام — وإلا كذب التنبيه على تشغيلٍ
ليومٍ ماضٍ.

**والقناعُ والمال**: مبالغُ الأتعاب في `FEE_AMOUNT_KEYS` (`amount` · `subtotal` ·
`total`) و`AMOUNT_KEYS`؛ والقراءةُ تحسب `fees.amounts_masked` **مرّةً للطلب**،
و`draft_row` تقنّع **البنودَ مع المجموع** (قنعُ الأعلى وحده يترك الرقمَ في السطر)،
وكتابةُ مبلغٍ بلا `office.amounts.view` **403** (`reject_amount_writes`).

**وهجرة `0012_fees`** إضافيّةٌ محضة: خمسةُ `CreateModel` (`FeeSubscription`،
`ClientServicePrice`، `FeeExtraService`، `FeeDraft`، `FeeDraftLine`)، وفهارسُها
وقيودُها (فرادةُ شهر المسودّة، وفرادةُ `(client, starts_on)`، والمبالغُ غيرُ
السالبة، وترتيبُ طرفَي الإيقاف والإنهاء)، و`AddField` لـ
`FeeExtraService.billed_draft` (ربطُ الإضافة بمسودّتها)، و`AlterField` لاختيارات
`OfficeAlert.kind` وحدها. **بلا `RunSQL` ولا `RemoveField` ولا `DeleteModel` ولا
`RunPython`** — لا بياناتَ أولية جديدة: القيمُ الافتراضية في السجلّ لا في صفوف.

**ولأ٢ صريحاً**: فاتورةُ الأتعاب بمستندها وحقولها القانونية، والترقيم، والإشعارُ
الدائن، ورابطُ PDF، وشاشةُ «المسودّات» (تعديلُ المسودّة/إعادةُ حسابها). و`FeeDraft`
المعتمدة تُنتج `FeeInvoice` في أ٢ — **مفهومان لا يُدمجان** (مسودّةٌ تُحسب ومستندٌ
يُرقَّم ويُطبع).

## الدفعات و«اللي عليه» وكشف الحساب (#283، الجزء أ: الخادم)

**الدفعةُ سندُ قبضٍ رقيق، والقيمةُ الكاملةُ مشتقّة**: `FeePayment` تحمل مبلغَها
وتاريخها وطريقتها ورقمَ إشعارها، و`FeePaymentAllocation` تقول على أيّ مسودّةٍ
ذهبت، و`FeeWriteOff` تقول ما تُنوزل عنه. **ولا عمودَ لـ«المدفوع» ولا لـ«المتبقّي»
ولا لـ«الرصيد الدائن»**: عمودٌ مخزَّنٌ ثانٍ يختلف عن الصفوف عند أوّل شطبٍ أو تخصيص،
ويُصلَح بالكذب.

**الصيغةُ الوحيدة** (`payments.client_due`، ومنها كلُّ سطحٍ يعرض «اللي عليه»):

```
remaining(مسودّة) = total − Σ allocations − Σ write_offs        (لا تسقط تحت الصفر)
credit(زبون)      = Σ(payment.amount − Σ allocations(payment))  (الجزءُ غيرُ المخصَّص)
due(زبون)         = Σ remaining(المعتمدة) − credit
```

- **`due` سالبٌ** حين يكون للزبون رصيدٌ دائن، **ولا يُقصّ إلى صفر**: الصفرُ يقول
  «لا شيء عليه» والسالِبُ يقول «له عندنا». دفعةُ 700 على 650 ⇒ `credit = 50` و
  `due = -50`.
- **`draft`/`cancelled` لا تدخلان الحساب**: لا دَينَ قبل الاعتماد، والملغاةُ لم تكن
  ديناً. ولا يُغيّر الجزئيُّ `FeeDraft.status` — «مدفوعة جزئياً» **حالةٌ مشتقّةٌ**
  (`paid|partial|unpaid`) تُقرأ من `remaining` في الحمولة.
- **والتخصيصُ الأقدمُ أوّلَاً** (`year, month, id`) على المعتمدة وحدها: دفعةُ
  الزبون تُسقِط أقدمَ فاتورةٍ عليه (عُرفُ كشف الحساب في دفترة وOdoo وQuickBooks —
  بغيرِه يتأخّر أقدمُ دينٍ أبداً فيصير التقادُم بلا معنى). ويُغيّره الموظف
  بـ`allocations: [{"draft": <id>, "amount": "..."}]`: مبالغُ موجبة، والمجموعُ
  لا يتجاوز الدفعة، ولكلّ مسودّةٍ لا يتجاوز متبقّيها، والمسودّةُ **معتمدةٌ وله
  وللمكتب نفسه** (وإلا 400 برسالةٍ واحدةٍ للغائبة ولغيرِه فلا تُثبت وجودَها).
- **والزيادةُ رصيدٌ دائنٌ مشتقّ** لا نموذجَ رصيدٍ منفصل، **ويُستهلك بتخصيصٍ جديد**:
  عند اعتماد فاتورةٍ جديدة يمرّ `apply_open_credit` على دفعات الزبون ذاتِ الرصيد
  فيخصّصها عليها — فيبقى الكشفُ سجلَّ صفوفٍ يُقرأ لا حساباً يُعاد في كل طلب.
  والقراءةُ تسبق الحلقة فحسابُ الأرصدة استعلامٌ واحدٌ ثابتُ الكلفة.
- **والجزءُ غيرُ المخصَّص من الدفعة رصيدٌ دائنٌ كذلك** (لا صفَّ له).

**ورقمُ الإشعار** `{year}-{n:05d}` من **عدّادٍ مقفول** (`FeeReceiptSequence`،
`select_for_update` ثم زيادةُ `last_number` داخل `transaction.atomic`) كـ
`ClientBookSequence` — **لا `MAX+1` ولا `count+1`**: كلاهما يقرأ لقطةً قديمة تحت
التزامن. والرقمُ فريدٌ لكل مكتب (`(tenant, receipt_number)`)، وسنتُه سنةُ `paid_at`
لا سنةُ الإدخال، **ولا يُعاد رقمُ إشعارٍ قائم أبداً**. وزيادةُ العدّاد والدفعةُ في
معاملةٍ واحدة: فشلُ الكتابة يُرجع العدّاد فلا فجوة.

**والشطبُ سطرٌ إلحاقيّ**: يخفّض `remaining` ولا يمحو الدفعةَ ولا المسودّةَ ولا
الشطبَ (لا `RemoveField` ولا `delete`)، ولا يتجاوز المتبقّي — شطبُ أكثرَ يمحو
الباقي بصمتٍ ويُظهر رصيداً دائناً لم يدفعه أحد. **وصلاحيتُه لصاحب المكتب وحده**
(`core.access.user_tenant_role(user, tenant) == MANAGER_ROLE`) لا لمدير المكتب ولا
للمحاسب — تنازلٌ عن مالٍ لا إدخالُ حركة (403 لغيرهما). وسببُه `reason` إلزاميٌّ
غيرُ فارغ، والمسودّةُ معتمدة.

**وسطرُ العلم الضريبيّ** (`client_due_tax_note`): مجموعُ `Obligation.amount` في
الالتزامات غير المعلَّمة `client_paid`، يُعرض **تحت** «اللي عليه» **ولا يدخل `due`**.
و`Obligation` **لا يحمل حقلاً خاصّاً بمبلغ ضريبة** — فلا حقلَ جديدٌ يُخترَع له؛
والمبلغُ مجموعُ ما وُجد من `amount` (وقد تكون فارغة).

**وكشفُ الحساب** (`fees/ledger/`): الفواتيرُ المعتمدةُ (بـ`paid_amount`/`remaining`/
`state`) والدفعات، في حمولةٍ واحدة: `{invoices, payments, client_due}` وكلُّ
مجموعةٍ `{count, page, page_size, results}`. **والفلترةُ والترقيمُ على الاستعلام**
(`client`، و`state` على تعليق `remaining` في SQL، و`q` بحثاً في اسم الزبون، و
`page`/`page_size` قصّاً في القاعدة) — **لا تصفيةً في بايثون**. والمجموعتان
مفصولتان لأن دمجَهما في قائمةٍ واحدة يتطلّب `UNION` على نوعي تاريخٍ مختلفين أو
تصفيةً في بايثون؛ والشاشةُ تصفّهما كما تشاء (#283/ب لاحقاً).

**والقناعُ والمال**: مفاتيحُ الدفعات في `services.PAYMENT_AMOUNT_KEYS` و`AMOUNT_KEYS`
(`amount` · `paid_amount` · `remaining` · `due` · `credit` · `invoices_total` ·
`paid_total` · `tax_note`). القراءةُ تحسب `amounts_masked` **مرّةً للطلب**،
والمفاتيحُ تبقى بقيمة `None` (نمطُ `mask_amounts` لا حذفَ مفتاح)، وكتابةُ مبلغٍ بلا
`office.amounts.view` **403** (`reject_amount_writes`).

**ولا تعديلَ ولا حذف**: `http_method_names = ["get", "post", "head", "options"]` على
`OfficeFeePaymentViewSet` و`OfficeFeeLedgerViewSet`، ولا مسارَ تفصيلٍ للدفعة أصلاً
(404 لسندٍ واحد، لا 405 فقط). والتصحيحُ دفعةٌ جديدة أو شطبٌ بسببٍ مكتوب.

**وهجرة `0014_fee_payments`** إضافيّةٌ محضة: أربعةُ `CreateModel` (`FeePayment` ·
`FeeReceiptSequence` · `FeePaymentAllocation` · `FeeWriteOff`) وفهارسُها وقيودُها
(فرادةُ رقم الإشعار للمكتب، وفرادةُ `(payment, draft)`، وفرادةُ `(tenant, year)`
للعدّاد، و`amount > 0` في الثلاثة) — **بلا `RunSQL` ولا `RemoveField` ولا
`DeleteModel` ولا `RunPython`**. وتابعةٌ لـ`0012_fees` — وهو **ورقةُ الهجرات** في
الشجرة بعد دمج #281/#282 (`0012_fees` يعتمد `0013_appointments`، فالرقمُ 0013
محجوزٌ و`0012` هو الورقة)، فلا سلسلةَ تُعاد ترقيمها.

## الشاشات — «جاهز للإرسال» وسجلُّ التذكيرات (#280، الجزء الثاني)

**الشاشةُ شاشةٌ كاملةٌ لا تبويبٌ في «اليوم»**: المعرّف `office-ready-to-send`
والمسار `/accounting-office/ready-to-send` (`OFFICE_READY_TO_SEND_PATH` في
`utils/accountingOffice.ts`)، ومجموعتُها في بيان الشريط **بعد «اليوم» مباشرةً**
بمصطلح `nav.office_ready_to_send` («جاهز للإرسال»)، ومسجَّلةٌ حيث «اليوم»:
`App.tsx` (استيرادٌ كسولٌ ومسارٌ وحالةُ توجيهٍ داخل `ModuleLicenseGuard`)،
و`types/common.ts`، و`Sidebar.tsx`، و`Breadcrumb.tsx`، و`utils/viewPermissions.ts`
(وحدةُ `accounting_office`)، و`core/shell_manifest.py`، و`core/terminology.py`.
**ولا عدّادَ لها في «اليوم»** (قرارُ #280/D9، الجزء الأول) — الشاشتان تُقرآن من
مصدرين مختلفين، فلا تُخلط كلفتُهما.

**البطاقةُ رسالةٌ واحدة** (وحدةُ الإرسال): اسمُ المستلِم وهاتفُه وشارةُ لغته،
وأسماءُ زبائنها بلا تكرار، وشاراتُ أنواع بنودها بتسمية الخادم ولونِ مفتاح
`badge` نفسه (`obligationBadgeClass`)، ونصُّ الفترة، ثم **معاينةُ النصّ** كما
سيخرج (`whitespace-pre-line`) و«عدّل» يحوّلها `textarea` — **والمعدَّلُ هو ما
يُرسَل ويُسجَّل** (`body` في الفعل)، والمسوّدةُ مفتاحُها `readyToSendMessageKey`
المشتقُّ من محتوى الرسالة لا من فهرسها (القائمةُ تُعاد قراءتُها بعد كل فعل).

**الأفعالُ أربعة، والخادمُ هو الحكم**: «ابعت على واتساب» يفتح
`officeWhatsappLink(phone, taxSystem, body)` في تبويبٍ جديد
(`window.open(..., '_blank', 'noopener')`) ثم يسأل «انبعتت؟» بـ«نعم» (`sent`)
و«لا» (يُغلق بلا كتابة)؛ و«ذكّرته بالتلفون» (`manual` بقناة `phone`) وبجانبه
«بالزيارة» (`in_person`)؛ و«أجّل» تاريخاً أدناه الغد (`min = nextDayIso(day)`)
ثم `postpone` **لكل زوج (زبون × نوع)** في البطاقة؛ و«شيل» بسببٍ اختياريّ ثم
`dismiss`. ورقائقُ الأنواع من رسائل اليوم وحدها (بتسمية الخادم وعدِّ **رسائل**
لا بنود)، وفلترُ الموظف لمن يرى زبائن غيره (`office.clients.all`) وفي مكتبٍ فيه
أكثر من شخص. والرجوعُ عند كل فشلٍ `humanizeThrown`، والحالاتُ الفارغةُ/التحميلُ
كالشاشات المجاورة، والنصُّ الفارغُ رسالةٌ لا زرّ (زرُّ الواتساب و«نعم» يُقفلان
عليه، فلا يُفتح `wa.me?text=` فارغٌ ولا يُسجَّل إرسالٌ بلا نصّ).

**ونظامُ الزبون الضريبيُّ في البند لا في المستلِم** (#280/ب): `_reminder_message`
تبني المستلِمَ بـ`contact_id`/`name`/`phone`/`has_phone`/`language`/`language_label`،
و**كلُّ بندٍ يحمل `tax_system` زبونه** — لأنه مصدرُ مفتاح الدولة الذي يبنيه
`officeWhatsappNumber` لرقمٍ أرضيّ، ورسالةُ شخصٍ واحدٍ قد تجمع زبونين بنظامين
مختلفين. والأرقامُ الثلاثة كلُّها تُقرأ في **مسحة الإعدادات الواحدة**
(`resolve_settings_for_clients` مع `_REMINDER_CLIENT_KEYS`)، فإضافةُ الحقل لا
تكلّف استعلاماً لكل بند. وتشترط الواجهةُ اتّفاقَ بنود الرسالة على نظامٍ واحد
(`commonTaxSystem`) — ومتى اختلفت أو غاب نظامُ بندٍ مرّرت `null` فلا تخمين:
الجوالُ الفلسطينيّ والإسرائيليّ والدوليُّ يُصاغون بلا مفتاح دولة، **والأرضيُّ
وحده** يعود `null` فيُقفل الزرُّ بنصّه («رقم غير صالح للواتساب»).

**تبويبُ «سجلّ التذكيرات» في ملفّ الزبون** بعد «الأوراق» (مفتاحُه
`reminder-log` في `CLIENT_TAB_KEYS`، و`?tab=` كأخواته): الأحدثُ أوّلاً من
`clients/<pk>/reminder-log/`، بكل سطرٍ تاريخُه ووقتُه، ونوعُ الصفّ بلونٍ
(`reminderLogKindClass`) وتسميته، ونوعُ التذكير، والقناة، والمستلِم وهاتفه،
والفترة، **وأسماءُ بنود الأوراق من لقطة الصفّ** (`subject.document_item_names`
التي حفظها الخادم وقت الإرسال — وهي المرجعُ الوحيد لبنود الزبون في صفَّي «شيل»
و«ما انبعتت» فليس فيهما نصّ)، ومَن كتبه، والنصُّ كما أُرسل (قابلٌ للفتح)،
والسبب. **و«أُلغي» تُشتقّ من `reverts_id`** (`revertedReminderLogIds`) لا من
علمٍ ثانٍ، و«ما انبعتت» على `sent`/`manual` **غيرِ مُبطَلٍ** وحده
(`canUndoReminderRow`، بمفتاح الكتابة وبتأكيدٍ أولاً) — والسجلُّ بلا تعديلٍ ولا
حذف كما لا تعرفه النقاط.

**والإذنُ يُدار من تبويب «جهات الاتصال»**: سطرُ الحالة تحت كل جهة («موافق يستلم
تذكيرات»/«ما وافق») وأنواعُها وتاريخُ إذنها وطريقُه وإن سُحب فسحبُه ومَن سحبه —
**كلُّه من حقول الجهة في القائمة نفسها** (`reminders_consent`/`consent_types`/
`consent_on`/`consent_channel_label`/`consent_withdrawn_*` على `ContactRow`،
وتسمياتُ الأنواع من `recipients[].label` المحمَّلة أصلاً)، فلا طلبَ شبكةٍ لكل
جهةٍ لعرض حالتها. و`contacts/<id>/consent/` تُطلب **عند فتح محرّر جهةٍ بعينها
وحدها** لأنها وحدها ترسل `type_choices`/`channel_choices` وتسمياتِ الأنواع،
وتُخزَّن بمفتاح المعرّف فلا تُقرأ مرّتين؛ وردُّ الحفظ أو السحب يحمل الحقولَ
كلَّها فيُطبَّق على `links` في السطر وفوراً. و«سجّل الموافقة» يفتح محرّراً
بالأنواع الحالية (ولا يُحفظ بلا نوعٍ واحد) و«سحب الموافقة» بتأكيدٍ يُبقي تاريخَ
الإذن. والكتابةُ بـ`office.clients.write` وحده.

**وفي الإعدادات**: مجموعةُ «التذكيرات والنصوص» تعرض إعداداتِها من السجلّ كما هي،
**و`reminder_auto_send` ضابطُه مقفلٌ** (`isLockedOfficeSetting`) لأن الخادم يردّ
400 على فتحه — وملاحظتُه من السجلّ تشرح القفل، فلا نصَّ محليّاً. وتحت السطور
قسمان: **نصوصُ التذكير** (`OfficeReminderTemplatesSection.tsx`) نصٌّ لكل
(نوع × لغة) بالفعليِّ من الخادم و`مخصَّص` وحفظٌ بـ`PUT` و«ارجع للافتراضي»
(`DELETE`) ورموزٌ تُدرَج بضغطة من `placeholders`؛ و**عطلُ المكتب**
(`OfficeHolidaysSection.tsx`) قائمةٌ بيومها واسمها، وإضافةٌ وحذفٌ بتأكيد. كِلاهما
يُقرأ لكل عضو ويُكتب بـ`office.settings.manage` (كلُّ قسمٍ يقرّر `canManage`
بنفسه كما في قالب بنود الأوراق).

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
- **ودفترُ الزبون لا يمرّ بمحرّك القيود العام — استثناءٌ موثَّق لا سهو.**
  `accounting_office/client_books.py` و`accounting_office/models.py` لا يستوردان
  `accounting.services` ولا `post_journal` ولا `JournalHeader`/`JournalLine`: دفترُ
  الزبون دفترُ منشأةٍ أخرى، وإدخالُه في محرّك المكتب يضع أرصدةَ منشآتٍ غريبة في
  ميزانيته وإقراره. القرارُ في `docs/decisions/client_books.md`، ويحرسه مسحُ `ast`
  في `accounting_office/tests/test_client_books.py`.
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
  assign · obligations · close-prior)، و`settings/<key>/clients/`، **وعدّادُ
  `client_customization_count`** (رقمٌ عن الزبائن فيُحسب على ما يراه العضو، وإلا
  خالف القائمةَ المفلترة تحته)، **ونقطتا «اليوم» والشغلات** (#275). بلا
  `office.clients.all` لا تُرجع إلا `responsible=user` **أو من حُوِّلت له شغلةٌ
  منها** (`PeriodTask.assignee=user`، بـ`.distinct()`) — **فزبونُ غيرك 404 لا
  403**. والتوسيعُ (#275) وقع **في هذه الدالة وحدها** كما وصفته النسخةُ السابقة:
  شرطٌ جديدٌ في نقطةٍ ثانية كان يفترق عن هذا بصمت.
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
- **الصفُّ المحفوظ لقطةٌ لا مرآة** (#278). `DocumentChecklistItem` ينسخ
  `item_code` و`name` و`service_codes` وقت التوليد، و`get_or_create` على
  `(client, item_code, period_start)` لا يكتب صفّاً ثانياً ولا يعيد كتابة قائم.
  فتعديلُ الكتالوج أو خياراتِه يؤثّر في التوليد **القادم** وحده، وما رآه الموظف
  يبقى بتاريخه.
- **`_document_items_for` هي الدالّةُ الواحدة لبنود الفترة** (#278) — يقرؤها
  التوليدُ وحده، والحمولاتُ تقرأ الصفوفَ المحفوظة. نسخةٌ ثانية من «هل ينطبق
  البند؟» تفترق عن الأولى عند أول شرطٍ يُضاف.
- **الملفُّ لا يغيّر الحالة، ورابطُ التخزين لا يخرج** (#278). رفعُ ملفٍّ أو حذفُه
  لا يمسّ `status` (معيار القبول ٤)، والتقديمُ بايتاتٍ من `stream_stored_asset`،
  و`document_file_payload` **بلا `file_url`** — وهي القاعدةُ التي تُبقي
  `file_url` خادمياً في كل ردّ، ويسقط عليها اختبارٌ يفتّش الردَّ عن رابط التخزين.
- **«ناقصه أوراق» تُحسب عند القراءة ولا تُخزَّن** (#278). لا عمودَ لها؛ ومعها
  `docs` لكل صفّ، والكلُّ عبر `document_progress` **باستعلامين ثابتين** لا يكبران
  بعدد الصفوف (يحرسه اختبارُ `CaptureQueriesContext` في «اليوم»).
- **مددُ الحفظ بياناتُ منصّةٍ لا ثوابتُ كود** (#278). سنةُ الحفظ وأساسُها في
  `DocumentRetentionRule` بمصدرها المنشور، وv1 لا يحسب تاريخاً ولا يحذف.
- **اعتمادُ مسودّات الأتعاب دورٌ لا مفتاح** (#282): `manager` و`office_manager`
  وحدهما (`fees.can_approve_fee_drafts` عبر `user_tenant_role`)، والصفوفُ تُقفل
  `select_for_update` قبل القراءة فقرارُ الاعتماد يُبنى على الحال الآنية.
  و`draft → approved`/`cancelled` فعلان لا غير: **لا حذفَ ولا تعديلَ لمسودّة**،
  والمعتمدةُ سندُ فاتورةٍ في أ٢. ومسودّةُ زبونٍ لا يراه العضو **404** قبل سؤال الدور
  (403 يُثبت وجودها).
- **السعرُ المؤرَّخ والمبلغُ لقطة** (#282): تغييرُ سعر الاشتراك **يضيف صفّاً**
  (`FeeSubscription`، فرادةُ `(client, starts_on)`) ولا يعدّل ما قبله، وسطورُ
  المسودّة ومجموعاها لقطاتُ وقت التوليد — فما وُلد لا يتغيّر بسعرٍ أو خدمةٍ تُضاف
  بعدها. **وما لم يُفوتر لا يضيع**: إضافةٌ سُجِّلت بعد توليد مسودّة شهرها تنتظر
  أوّلَ مسودّةٍ تالية (`FeeExtraService.billed_draft`)، فلا تدخل مسودّةً مرّتين
  ولا تُسقَط. والتناسبُ بعدد أيام الشهر الفعليّ لا بثلاثين، **وعلى حدود اشتراك
  الزبون لا حدود صفّ السعر**: صفٌّ يبدأ في منتصف الشهر يحكمه بسعره كاملاً.
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
  `set_client_setting` — لا «حذف» لتخصيصٍ على مستوى لا يملكه المفتاح. وطرفا
  نافذة الإرسال يحرسهما `_assert_send_window` في الكتابة **وفي المسح** (يرجع
  المسحُ بالطرف إلى افتراضيّه، فنهاية 23 وبداية 20 ثم مسحُ النهاية ⇒ 400).
- **القراءةُ الجماعية محروسة**: `resolve_settings_for_clients` (ومعها
  `resolve_setting_for_clients` التي تُفوّضها) تمرّ بكل زبونٍ على
  `_assert_client_of_tenant`، وتفحص `validate_level` لكل مفتاحٍ قبل أيّ قراءة —
  فلا يُقرأ إعدادٌ لزبونٍ من مكتبٍ آخر ولا إعدادٌ مكتبيٌّ لمجموعة زبائن. ونسخةٌ
  ثانية من الترتيب تفترق عن الأولى عند أول تعديل، فيحرسها مسحُ المصدر أعلاه.
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
- **لا تاريخَ قانونيّاً في الكود.** كلُّ يومٍ وكلُّ شهرٍ في
  `accounting_office/deadlines.py` يُقرأ من سطرٍ في اللائحة؛ ولا رقمَ في المحرّك
  إلا `0` و`1` و`12` (أعدادُ التقويم). يحرسه مسحُ `ast` في
  `accounting_office/tests/test_deadlines.py`، ويسقط على `15` مزروعٍ — فالرقمُ
  المحفور يتعفّن مع كل نشرةٍ رسمية.
- **اللائحةُ بياناتُ منصّةٍ بلا `tenant`، ونسختُها لا تُعدَّل.** تصحيحُها يُضاف
  بـ`version` أعلى، والساريةُ أكبرُ `version`. وسنةٌ بلا نسخةٍ ⇒ «تقديري» **بلا
  تعديلاتها المنشورة** لأنها لسنةٍ أخرى. شروطُ السطر مفاتيحُها في `CONDITION_KEYS`
  وحدها، ومفتاحٌ غيرها `ValidationError` من `clean()`.
  **وتعديلُ المكتب (#277) لا يمسّها**: صفٌّ إلحاقيّ في `OfficeRuleOverride` مِلكُ
  المكتب يحمل لقطةَ المنصة، و«رجّع للمنصة» صفٌّ `cleared` — **لا `UPDATE` ولا
  `DELETE` على سطر لائحة أبداً**، ولا على صفّ تعديل.
- **`submitted` لا يُمسّ** (#277): لا تحديثُ لائحةٍ ولا تعديلُ مكتبٍ ولا تمديدٌ
  يغيّر تاريخَ ما قُدِّم — والاختبارُ يثبته في كل مسار.
- **التمديدُ على الموعد الساري وحده**: `due_date = extended_to or actual_deadline`،
  والأصفرُ يبقى على `task.internal_deadline`. من يقرأ `actual_deadline` للتحذير
  بعد #277 يخالف القرار.
- **التقويمُ تقريرٌ لا سجلّ.** `GET calendar/` لا يكتب سطراً (يحرسه اختبارُ عدّ
  صفوفِ كل نماذج الموديول قبل الطلب وبعده)، ولا ينادي `ensure_default_services`.
  ولا مبلغَ فيه، فلا حارسَ مبالغ يتأثّر.
- **سياسةُ يوم الراحة لكل نظام لا لكل مكتب.** `rest_day_policy` على نسخة اللائحة:
  فلسطين `warn` (تنبيهٌ بلا زحزحة — لا نصَّ رسميّاً يؤجّل)، وإسرائيل
  `postpone_client` (تأجيلٌ بعد يوم راحة الزبون وأيام إغلاق السلطة). وسطرٌ منشورٌ
  سببه يومُ الراحة وحده (`rest_day_only`) يُعاد حسابه لزبونٍ راحتُه غيرها.
- **محرّكٌ واحد للفترات والقواعد.** التقويمُ والتحديثُ يقرآن `_deadline_items`
  نفسَه؛ نسخةٌ ثانية تفترق عند أول تصحيحٍ في اللائحة. والقاعدةُ نفسها للأسطر:
  السطرُ يولّد فتراتِ مصدره وحده (`rule.cadence != source` ⇒ لا بند).
- **«حدّث المكتب ليوم X» idempotent وبلا ساعة.** اليومُ يُمرَّر صريحاً، والصفُّ القائم
  لا يُحدَّث في التوليد (`get_or_create` بفرادةٍ غير مشروطة)، ومعاملةٌ لكل زبون،
  و`OfficeRefreshRun` صفٌّ واحدٌ لكل (مكتب، يوم). ولا `date.today()` في كود
  الإنتاج — `timezone.localdate()` وحده عند حدود الطلبات. **والاستثناءُ المحسوم
  (#277)**: تحديثُ المنصة يُعيد حسابَ غير المقدَّم قبل حفظ الجديد، بكتابةٍ دفعيّةٍ
  واحدة (`bulk_update`) لا بنداً بنداً.
- **ما حان وقتُه = `period_end < day`.** لا `actual_deadline`: ق.م كانون الثاني
  تظهر في 1 شباط. والدرجاتُ تُحسب عند القراءة: **الأحمرُ من `due_date`
  (`extended_to or actual_deadline`)، والأصفرُ من `task.internal_deadline`** (أبكر مواعيد التزامات الشغلة)،
  **و«قريب» شارةٌ بالأولوية** بينما **عدّادُ/فلترُ `week` نافذةٌ على `due_date`**
  مستقلةٌ عن الشارة (#276) — فصفٌّ أصفرُ داخل النافذة يُعدّ ويظهر تحت `week`.
- **المبلغُ يُقفل عند «انقدّم»، و«انقدّم» لا يُتراجَع عنه.** أيُّ انتقالٍ من
  `submitted` ⇒ `ValidationError` «انقدّم لا يُتراجَع عنه»، و`client_paid` وحدها
  تُكتب في كلّ الحالات.
- **`last_period_ours=False` تُسقط آخر فترةٍ ولا تحذف صفّاً.** `refresh_office`
  لا يولّدها، والمنتظِرُ منها يصير «مش لازم هالفترة» — والتاريخُ يبقى.
- **لا مُجدوِل في المستودع.** `refresh_accounting_offices` أمرٌ يدويٌّ يُشغّله cron
  الخادم (خطوةُ نشر)، و`ensure_office_refreshed` تغطّي أوّل فتحٍ في اليوم.
- **الدرجتان مشتقّتان ولا تُخزَّنان** (#276). لا عمودَ «متأخّر داخلي»، وشارةٌ
  **واحدةٌ على الأكثر** لكل صفّ بالترتيب **أحمر ← أصفر ← قريب ← لا شيء**؛
  و`week` عدّاداً وفلتراً **نافذةُ `due_date` وحدها** (`extended_to or
  actual_deadline`) لا الشارة — فصفٌّ أصفرُ داخل النافذة يُعدّ. والأحمرُ و`week`
  على `due_date`، والأصفرُ وحده على `task.internal_deadline`. أيُّ قراءةٍ تُخزّن الحالةَ تفترق عن اليوم الذي يراه
  الموظف. يحرسه اختبارُ `ResolvedBadgeTest` على `client_obligations_payload`
  (كلُّ الحالات) لأن `today_payload` يقرأ المنتظِرَ وحده.
- **التنبيهُ مرّةٌ واحدةٌ لكل (مستلِم، نوع، مرجع)**. الفرادةُ غير المشروطة في
  القاعدة (`uniq_office_alert_ref`) لا في الكود، فالنداءُ الثاني لا يضيف صفّاً.
  ونوعٌ جديد يُضاف **صفّاً في `OFFICE_ALERT_KIND_CHOICES`** لا فرعاً في الكود.
- **المحسومُ يُستبعد عند القراءة ولا يُحذف** (`Exists` بلا N+1): «انقدّم» و«مش
  لازم هالفترة» يُسقطان التنبيهَ من الجرس، و«رجّعها» تُعيده، والصفُّ أثرٌ يبقى.
- **«صاحب المكتب» تعريفٌ واحد، و«المسؤول» قيمةٌ واحدة.** `_office_owner_ids`
  تقرأ دورَ `MANAGER_ROLE` (المعرَّفُ في `core/access.py` ويقرؤه هذا الموديول
  منه — لا إعلانَ ثانٍ)، و«المسؤول» هو `task.effective_assignee`، وإن غاب فصاحب
  المكتب — ولا تعريفَ ثانٍ في نقطةٍ أو شاشة. والمستلِمُ الواحد لا يُكرَّر ولو
  جمعه الدوران (مجموعةٌ لا قائمة).
- **القراءةُ والكتابة على المعروض، والرؤيةُ تتبع الزبون.** `_visible_alerts`
  تُسقط المحسوم **وتُسقط تنبيهَ زبونٍ لا يراه العضو** (استعلامٌ فرعيٌّ على
  `visible_clients`)، و`mark_all_alerts_seen` يكتب على `_visible_alerts` وحدها
  فلا يُقنّع تنبيهاً محسوماً يعود لاحقاً. حرسهما اختبارا العزل بمستلِمٍ واحدٍ في
  مكتبين (بلا فلتر `tenant` يسقطان) واختبارُ «شفتهم كلهم» ثم «رجّعها».
- **التنبيهُ بلا مبلغ.** `message` لقطةُ نصٍّ بلا رقم مال، وحمولةُ السطر بلا
  مفتاحِ مبلغ، و`OfficeAlert` بلا `DecimalField` — فلا مسّ لحارس المبالغ.
- **الجرسُ لمكتبٍ مرخَّصٍ وحده، وكلُّ عضوٍ تنبيهاتُه هو.** الظهورُ من
  `VIEW_MODULES`/`moduleAllowsView` (المصدرُ القائم)، والقراءةُ والكتابةُ
  بـ`recipient=request.user` — ولا مفتاحَ إضافياً هنا، **وتنبيهُ غيرك 404**.
- **الواجهةُ لا تعرف أنواعَ التنبيه.** الخادمُ يُرسل `kind_label` و`badge` و`opens`،
  والجرسُ يُلوّن بـ`obligationBadgeClass(alert.badge)` ويُوجّه بـ`alertTargetPath`
  من `opens`؛ نوعٌ لاحقٌ يصل `""` فيأخذ المحايد بلا حزمةٍ جديدة. ومفتاحُ الشارة
  يُضاف صفّاً في `OFFICE_ALERT_KIND_BADGES`، والوجهةُ في `OFFICE_ALERT_KIND_OPENS`.
- **إعادةُ الحساب دفعةٌ واحدة ولها مصدرٌ واحد.** `_recompute_obligations` وحدها
  تُعيد حسابَ التزامٍ محفوظ (تعديلُ مكتبٍ أو تحديثُ منصة)، وبدالّة المحرّك نفسها —
  ولا نسخةَ ثانية من الحساب في خدمةٍ أو شاشة. وممنوعٌ
  `UPDATE … WHERE id IN (SELECT … من الجدول نفسه)` (MySQL 1093): تُقرأ المعرّفات
  أولاً، ثم يُكتب (كما في `mark_all_alerts_seen`).
- **دوريةُ خدمة الرواتب شهريةٌ أو كل شهرين — والنقطةُ واحدة** (#279).
  `_assert_payroll_frequency` هي الحكم، ويقرؤها **مسارا كتابة الدورية**
  (الإضافةُ وتغييرُ الدورية المؤرَّخة): شرطٌ في أحدهما وحده يترك البابَ الآخر
  مفتوحاً لـ«رُبعية» فلا تُتبع #264. والرفضُ **قبل أيّ كتابة**.
- **إعدادُ «الالتزامات التي تولّدها خدمة الرواتب» يُطبَّق في `rule_applies` وحدها**
  (#279): التوليدُ والتقويمُ يقرآن القرارَ الواحد من الدالّة الواحدة، فنسخةٌ ثانية
  من الشرط في نقطةٍ أو شاشة تفترق عن الأولى عند أول بندٍ يُضاف. **و«اليوم» يقرأ
  المحفوظ**: التقليصُ يوقف الجديد ولا يمسح صفّاً وُلد قبلُ — يبقى حتى يُحسم. ويُقرأ
  من `CalendarContext` (`CONTEXT_SETTING_KEYS`) فلا استعلامَ لكل سطر.
- **نصفُ سنويٍّ دوريةُ سطرٍ لا دوريةَ خدمة** (#279). `semiannual` في
  `DEADLINE_CADENCE_CHOICES` و`CADENCE_SPAN_MONTHS` وحدها — لا في
  `CLIENT_SERVICE_FREQUENCY_CHOICES` ولا في دوريات التزام المكتب، وأيامُ إعداده
  من مفتاح الربعيّ. إضافتُها إلى `FREQUENCY_*` تُدخل «خدمةً نصف سنوية» لا
  معنى لها في قانون.
- **`default_status` لبند المنصّة وحده، وبندُ المكتب يبدأ «مطلوبة»** (#279).
  القانونُ يقول أيُّ ورقةٍ لا تُطلب شهرياً؛ ورقةٌ أضافها المكتب لا تُولَد ملغاةً
  بلا قراره. وصفٌّ «مش لازمة» **لا يُعدّ مطلوباً** في `document_progress` فلا
  يُشعل «ناقصه أوراق» — ولو كان موجوداً في الفترة.
- **التذكيرُ يُحسب عند القراءة ولا يُخزَّن** (#280). لا عمودَ «متى القادم» ولا
  مهمةَ تُحدّثه: `_reminder_candidates` وحدها تجيب المستحقَّ من (الأوراق الناقصة ×
  السجلّ × الإعداد)، فتغييرُ إعدادٍ أو عطلةٌ أو إرسالٌ يسري فوراً. تخزينُ الموعد
  كان يحتاج تحديثاً يومياً ويترك المواعيدَ القديمة على حالها بعد تصحيح إعداد.
- **`ReminderLog` إلحاقيٌّ لا يُعدَّل ولا يُحذف** (#280). لا نقطةَ `PUT`/`PATCH`/
  `DELETE` (405)، والصفُّ لا يُكتب إلا من `_write_reminder_logs`، والتصحيحُ صفُّ
  `undo` يشير بـ`reverts` إلى ما يُبطله، وإبطالُ `undo` 400 فلا حلقة. والعدُّ
  الصافي يستثني المُبطَل (`Exists` في الاستعلام نفسه)، و`dismissed` يُعيد المؤقّت
  ولا يُعدّ، و`manual` يُعدّ كالإرسال. واللقطة (`recipient_name`/`recipient_phone`)
  لا تُعاد كتابتها بتغيير الجهة بعدها.
- **الإذنُ شرطُ الظهور، والسحبُ لا يمحو الإذن** (#280). `Contact.allows_reminder`
  هي السؤالُ الوحيد، وتاريخُ السحب يُكتب مع مَن سحب بجانب تاريخ الإذن. وجهةٌ بلا
  إذنٍ (أو نوعُها ليس في `consent_types`) لا تدخل «جاهز للإرسال» أبداً. والجهةُ
  الجديدة تأخذ `reminder_default_consent_types` **نسخةً** عند الإنشاء.
- **نصُّ التذكير لا يمرّ بـ`str.format`** (#280). `render_reminder_body` يستبدل
  الستّةَ المعتمدة بـ`str.replace` ويترك ما سواها حرفياً، و`validate_reminder_body`
  يرفض الرمزَ المجهول باسمه عند الحفظ. `str.format` على نصٍّ يكتبه المكتب يُسقِط
  الطلب 500 على قوسٍ واحدٍ زائد.
- **الإرسالُ التلقائيُّ مقفلٌ مطفأً** (#280). `reminder_auto_send` قيمةُ `False`
  وحدها، وأيُّ `True` ⇒ 400 برسالته (`LOCKED_SETTING_MESSAGES` في الخدمة). فتحُه
  حذفُ المفتاح من الخريطة في تذكرة المرحلة الثانية — لا مسارٌ ثانٍ في الـview.
- **التذكيرُ لا يُلغى بحاجز** (#280). يومُ راحة الزبون وعطلةُ المكتب وتأجيلُ الزوج
  تُسقط البندَ **اليوم** فقط، ويظهر أوّلَ يومٍ مسموح بعده — لأن الحسابَ من السجلّ.
  ولا تقويمَ عطلٍ وطنيّ في الكود: المكتبُ يكتب عطلَه في `OfficeHoliday`.
- **القائمةُ لكل شخصٍ لا لكل زبون** (#280). التجميعُ على جهة الاتصال المستلِمة،
  فشخصٌ مستلِمٌ لزبونين يأخذ رسالةً واحدة؛ والنصُّ بلغة المستلِم. والكلفةُ ثابتة:
  عدُّ الاستعلامات لا يكبر بعدد الزبائن (اختبارٌ يقارن زبوناً بخمسة).

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `accounting_office/tests/test_module_gate.py` | 404 لكل مسارٍ مُسجَّل بلا ترخيص (حارسٌ معمَّم يقرأ المسارات من `urls.py`)، والقالب يرخّص عند الإنشاء و`general`/`accounting_firm` لا، والتبديل لا يرخّص |
| `accounting_office/tests/test_roles.py` | الزبائنُ المحجوبون 404 على كل فعلٍ متداخل (و403 على `assign/` حيث تسبق الصلاحيةُ `get_object`)، وتجاوزُ العضو يفتح الكل، وعدّادُ المخصِّصين على ما يراه العضو، ورؤيةُ دفتر الجهات (مرئيّة/مربوطة بغير المرئيّ/غير مربوطة)، وقناعُ المبالغ ورفضُ كتابتها، والمالك والمدير يريان الكل، والقارئ لا يكتب، والتحويل وسجلُّه وقفلُ صفّه ورفضُ غير العضو، وسجلُّ النشاط المحروس 404، واختفاءُ `office_manager` بلا ترخيص ورفضُ إسناده لشركةٍ بلا وحدة |
| `accounting_office/tests/test_amounts_guard.py` | لا `DecimalField` في نماذج الموديول ولا في مُسلسِلاته ولا مفتاحَ حمولةٍ عشريّ خارج `AMOUNT_KEYS`، والقناع يُفرّغها، والحارسُ يسقط على نموذجٍ ونصٍّ مزروعين |
| `accounting_office/tests/test_clients.py` | إنشاء الزبون وبطاقته معاً، رفضُ الإنشاء قبل أول تشغيل، عددُ استعلامات القائمة، البحث والفلترة، الإنهاء والإعادة وسجلُّهما، 405 للحذف، حارسُ `tenant` على النماذج الابنة، تحقّقُ المبيعات السنوية، اختياراتُ البطاقة لكل نظام، العزل بين مكتبين |
| `accounting_office/tests/test_contacts.py` | محلّان وجهةٌ واحدة، الرئيسيةُ في القاعدة والخدمة، فكُّ الربط، بحثُ الجهات، رفضُ حذف المربوطة، ومستلِمُ كل نوع تذكيرٍ والرجوع للرئيسية |
| `accounting_office/tests/test_settings.py` | المستويات والافتراضيُّ والتخصيصُ للشغلة، رفضُ مستوىً غير مسموحٍ وقيمةٍ غير صالحة، «ارجع للافتراضي» و«ارجع لإعداد المكتب» ورفضُ الأول لمن لا افتراضي له، تفريغُ البطاقة عند تبديل النظام، عدُّ المخصِّصين، وأول تشغيل، و**إعداداتُ #274** (المجموعة الجديدة، ومستوى الشغلة لأيام الموعد الداخلي وحدها) |
| `accounting_office/tests/test_settings_guard.py` | لا ذِكرَ لنموذجَي التخزين خارج وحدة المحلّل |
| `accounting_office/tests/test_alerts.py` | **التأخيرُ بدرجتين والتنبيهاتُ #276**: الأصفرُ بعد الموعد الداخليّ ولا شيءَ معه، والأحمرُ يغلب ويأتي وحده، والأصفرُ يغلب «قريب»، و«قريب» لا يبقى بعد الداخليّ، **والمحسومُ بلا شارة في `client_obligations_payload`** (كلُّ الحالات؛ يسقط لو حُذف شرطُ الحالة)، **والتمديدُ الإلكترونيّ ليس تأخيراً** (`official_date < day ≤ actual_deadline` ⇒ لا أحمرَ ولا تنبيه، و`day == actual` كذلك)؛ والتنبيهُ الداخليُّ للمسؤول وحده افتراضاً والرسميُّ له ولصاحبَي المكتب، وإعدادا المستلِمين (`owner` يُبعد الأحمرَ عن المسؤول و`assignee` يُبعده عن المالك)، وزبونٌ بلا مسؤول ⇒ صاحبُ المكتب، ومستلِمٌ جامعٌ للدورين ⇒ صفٌّ واحد، والرسالةُ بلا مبلغ، و`badge` يُرسله الخادم من خريطة الأنواع (ونوعٌ مجهول ⇒ `""`)؛ ولا تكرارَ في اليوم نفسه ولا في يومٍ لاحق مع `created_alerts`، والجديدُ يأخذ تنبيهَه؛ والمحسومُ («انقدّم»/«مش لازم»/«رجّعها») يُسقط عند القراءة ولا يُحذف، وشغلةٌ فيها التزامٌ منتظرٌ يبقى تنبيهُها؛ **والتنبيهُ يتبع رؤية الزبون** (زبونٌ حُوِّل لغيره ⇒ لا يظهر)، **و«شفتهم كلهم» لا يكتب على محسوم** (رجيعُه يعود غيرَ مقروء ويُعدّ)؛ و«شفته» يُنقص العدّاد و«شفتهم كلهم» يُصفّره لكل مستلِمٍ على حِدة؛ **والعدّاداتُ الخمسة (ومعها `missing_docs` #278) قبل الفلتر و`week` نافذةٌ مستقلّةٌ عن الشارة** (صفٌّ أصفرُ داخل النافذة يُعدّ ويظهر تحتها) وفلترا الأحمر والأصفر منفصلان والمجهولُ مرفوض؛ وكلفةُ التوليد ثابتةٌ بين التزامٍ وخمسة (`CaptureQueriesContext`)؛ والأمرُ يطبع «تنبيهات n»؛ **وعزلُ المكتبين بمستلِمٍ واحدٍ فيهما** (تنبيهٌ بلا زبون لا يفصله إلا `tenant` — يسقط لو حُذف)؛ ولا `DecimalField` ولا مفتاحَ مبلغ |
| `accounting_office/tests/test_alerts_api.py` | **نقاطُ الجرس #276**: شكلُ `{"unseen", "rows"}` ومفاتيحُ السطر (ومنها `badge`)، وكلُّ عضوٍ تنبيهاتُه وحدها، وطلبٌ مجهولٌ 401 ووحدةٌ غير مرخَّصة 404، وعددُ استعلامات `GET alerts/` لا يكبر بعدد الصفوف، و`seen/` يُنقص العدّاد (ومرّتان لا تغيّران)، و`seen-all/` يُرجِع العددَ ويُصفّر، **وتنبيهُ غيرك 404** (ولا يُكتب فيه)، **وتنبيهُ مكتبٍ آخر 404 ولا يظهر** (للمستخدم نفسِه وبلا زبون، فلا يفصله إلا `tenant`)، وتنبيهُ التزامٍ انقدّم يخرج من الجرس مع بقاء صفّه |
| `frontend_v2/utils/accountingOffice.test.ts` | إخفاءُ `filing_method` لغير الإسرائيليّ، واشتقاقُ «مخصَّص»، وشارةُ الحالة، وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه، وإخفاءُ الإسناد في «شخص واحد»، وعرضُ «—» للمبلغ المخفيّ، وأدوارُ المكتب الأربعة، و**تقويمُ #274**: شبكةُ الشهر بالأحد أولاً، ومدى الأسبوع، وتنقّلُ الشهور عبر السنة، والتجميعُ على يوم الموعد، وتسميةُ الفترة، ووسمُ «متوقَّع»، و**«اليوم» (#275)**: تسمياتُ الحالة/الاتجاه/الشارة من الخادم وحدها (والقيمةُ الخام احتياطاً)، ونصُّ المبلغ بالاتجاه والقناع («—»)، وقراءةُ الفلتر من العنوان وكتابتُه، والتاريخُ القصير `dd/MM` بلا `Date`، و**#276**: `late_internal` فلترٌ مقروءٌ ومكتوب، وأصنافُ الشارات الثلاث (أحمر/أصفر/محايد)، وشارةُ التنبيه من `badge` وحده (ونوعٌ مجهولٌ محايد)، و`alertTargetPath` بـ`task=`، و`clientTabFromSearch`، و`taskIdFromSearch`/`officeTaskAnchorId`، و**#277**: وصفُ قاعدة السطر من أرقامها (والنوعُ المجهول يعيد تسميةَ الخادم)، و`settingsGroupFromSearch`، و`alertTargetPath` بـ`opens=deadline_rules`، ونصُّ التمديد وشارةُ الأصل و«المنصة: …»، وتاريخُ التمديد المقترح بعد ثلاثين يوماً، و**#278**: صفوفُ الشبكة خانةٌ لكل شهرٍ (والفارغُ محايدة)، وألوانُ الحالات الخمس ورموزُها، و`documentDocsText` («وصل 3/5» و«0/0» فارغ)، و`documentMissingBar` (آخرُ شهرٍ وأسماءُ النواقص وغيابُه)، وتسميةُ «مش لازمة هالسنة»، ووسمُ الملف، والسنواتُ المتاحة، وفلترُ `missing_docs` قراءةً وكتابةً، و**#280**: رقمُ واتساب المكتب من جوالٍ فلسطينيّ (059/056 ⇒ 970) وإسرائيليّ (05 غيرُهما ⇒ 972) وأرضيٍّ بمفتاح نظامه، والدوليُّ `+`/`00` يمرّ بلا إعادة بناء، والقمامةُ والقصيرُ يُعيدان `null`، ورابطُ `wa.me` يرمّز النصّ، و**#280/ب**: مفاتيحُ الفعل أربعةٌ (الزبون والنوع **وطرفا الفترة**)، ورقائقُ الأنواع ما له رسائلُ اليوم وحدها بتسمية الخادم وعدِّ **رسائل** لا بنود، وترشيحُ النوع يُبقي الرسالةَ كاملةً، ومفتاحُ المسوّدة يميّز رسالتَي شخصٍ واحدٍ ولا يتغيّر بترتيب البنود، و`reverts_id` يُعلّم «أُلغي» و«ما انبعتت» على `sent`/`manual` غيرِ المُبطَلين وحدهم، وألوانُ أنواع الصفّ الأربعة (والمجهولُ محايد)، و`nextDayIso` يعبر الشهرَ والسنة ولا يخترع تاريخاً من فاسد، و`isLockedOfficeSetting`، و`commonTaxSystem` (اتّفاقُ البنود على نظامٍ واحد، والاختلافُ والغيابُ `null`)، و`?tab=reminder-log` مقروءٌ من العنوان |
| `accounting_office/tests/test_services.py` | الخمسةُ الافتراضية و`ensure_default_services` idempotent والكودُ المولَّد يتخطّى المأخوذ، وبياناتُ السقوف من هجرة `0003` نفسها (أرقامُها وروابطها حرفاً)، وتغييرُ الدورية من تاريخٍ لا يمسّ ما قبله، والإيقافُ يُبقي الصفَّ ويمنع تعديلَ الدورية بعده ويقع مرّةً واحدة ولا يسبق سريانَ دورية، والحالةُ نسبةً لليوم (إيقافٌ مستقبليّ = نشطة)، ومنعُ التداخل (قبل `ends_on` أو فيه ⇒ رفض، وبعده ⇒ قبول)، وتطبيعُ `responsible_from` أولَ الشهر، والباقةُ نسخٌ لا ربط (وإعادةُ إضافةِ الموقوفة، وتخطّي المعطَّلةِ والمتداخلةِ بسببهما، وفرعُ «لا اقتراح» فعلاً)، والاقتراحُ لنظامين ولسقفين في سنتين وبلا سقف («تقديري») وقبل أقدم سقف (`None` + 400)، وتحذيرُ تجاوز سقف עוסק פטור وصفرُ المبيعات، والسببُ بلا أرقام، وحارسا المفتاحين (محاسبٌ بلا `office.settings.manage`، وعضوٌ يرى الزبونَ بلا مفتاح الكتابة)، و404 لزبونٍ غيرك على كل نقطة، وقناعُ `suggested_price` ورفضُ كتابته بعضوٍ يملك مفتاحَ الإعدادات ولا يرى المبالغ، وعددُ استعلاماتِ قائمة الباقات لا يكبر بعددها |
| `accounting_office/tests/test_deadlines.py` | **محرّكُ #274**: ق.م فلسطينيُّ كانون الثاني = 15 شباط، والجمعةُ تبقى مع التنبيه؛ والتأجيلُ الإسرائيليُّ بعد يوم راحة مسلم/يهودي/مسيحي؛ و`rest_day_only` يُعاد حسابه وغيره يُؤخذ؛ والتمديدُ الإلكترونيّ والموعدُ الداخليّ (والرجوعُ من الجمعة) وأيامُه 5/7/30 بتخصيص الزبون؛ و`periods_for`/`service_periods` محاذاةً بلا فجوة (والتقصيرُ يقطع الحزمة قبل التغيير، ودوريةُ الفترة المقطوعة تحدّد أيامَ إعدادها)؛ وسياقُ الطلب لا يُسقط زبوناً خارج مجموعته، وتنبيهُ «تقديري: سقف» على سطر السقف، وزبونٌ بلا بطاقة بلا 500، والفلترةُ بالزبون/الموظف تجلب خدماتِ المفلتَرين وحدهم؛ وسطرُ الدورية الثابتة يُولَّد مرّةً في السنة (و`on_demand` لا تُسقطه)؛ وشهرٌ بدأ في منتصفه يُدرَك؛ والربعُ نفسُه في مديين مختلفين؛ وبياناتُ هجرة `0004` حرفاً (عدُّ الأسطر لكل نسخة، وآذار 2026 = 27.4 وشباط 2026 = 26.3 وأيلول 2027 = 28.10)؛ و«עוסק פטור» لا يولّد الدوري؛ والسقفُ المفصّل؛ وسنةٌ بلا لائحة «تقديري» (بتعديلٍ يُزرع على شهرها فيُثبت تجاهلَه)؛ والخدمةُ الموقوفة؛ وحارسُ «لا تاريخَ قانونيّاً» بمسح `ast` وإسقاطِه على `15` و`-15`؛ والتقويمُ لا يحفظ سطراً ولا يكبر عددُ استعلاماته بعدد الزبائن؛ وتغييرُ السطر يظهر فوراً؛ والفلترةُ والمدى والأفقُ وتاريخٌ فاسدُ اليوم ⇒ 400 |
| `accounting_office/tests/test_obligations.py` | **التزاماتُ وشغلاتُ #275**: التشغيلُ مرّتين ليومٍ واحدٍ = مرّة (لا صفَّ مكرّرٌ ولا سجلَّان)، و`ensure` لا تعمل ليومٍ مسجَّل، وق.م كانون الثاني غائبةٌ في 31/1 وحاضرةٌ في 1/2، والتشغيلُ المتأخّرُ يلحق الفترات كلَّها، ورواتبُ إسرائيل الشهرية بموظّفين ⇒ شغلةٌ واحدةٌ والتزامان (`il_withholding_102` + `il_bl_employees`) وموعدُها الداخليُّ أبكرُهما، والتقريرُ السنويُّ 126/856 (شغلةٌ لعام 2026 تُحفظ من 1/1/2027)، وسنةٌ تقديرية (2028) تُحفظ بعلامتها، والصفُّ القائمُ لا تتغيّر تواريخُه بتعديل اللائحة، والتقويمُ ما زال يحسب ولا يحفظ، والشاراتُ تُحسب من اليوم بلا كتابةٍ في القاعدة، والمبلغُ يُقفل عند «انقدّم» و«انقدّم» لا يُتراجَع عنه و«مش لازم» تُفتح، وتاريخُ تقديمٍ مستقبليٌّ يُرفض، والاتجاهُ مطلوبٌ مع المبلغ، و«هدول انقدّموا قبل…» تُغلق المنتظِرَ قبل تاريخها وحده، وإيقافُ 31/3 يُبقي آذار ويُسقط نيسان، و`last_period_ours=False` لا تُولَّد وتُسكِتُ المنتظِر، والزبونُ المنتهي لا فترةَ بعد `ended_on`، ودالّةُ «آخر فترةٍ في سلسلة» نقيّةً، وتحويلُ الشغلة (عضوُ مكتبٍ آخر يُرفض، والمحوَّلُ إليه يرى الزبونَ بلا `office.clients.all`، و`None` يعيد الوراثة)، والأمرُ (المرخَّص وحده، و`--day` كما ورد، وتاريخٌ فاسدٌ `CommandError`)، وشكلُ السطر المحسوم، والقناعُ على المبلغ، والعدّاداتُ قبل الفلتر **ونافذةُ `week` على `actual_deadline` مستقلةً عن الشارة** (صفٌّ أصفرُ داخل النافذة يظهر تحت `week` و`late_internal` معاً) والفلاترُ الخمسة (والسادسُ `missing_docs` في `test_documents_api.py`) والمجهولُ 400 |
| `accounting_office/tests/test_obligations_api.py` | **نقاطُ #275**: المحاسبُ يرى زبائنه وحدهم في `today/`، والمبلغُ `null` بلا `office.amounts.view` وكتابتُه 403، والكتابةُ لمن يراه، و«انقدّم/مش لازم/رجّعها» عبر الـAPI (والانتقالُ من «انقدّم» 400)، و`client_paid` في كلّ الحالات، والعدّاداتُ قبل الفلتر والفلترُ المجهولُ 400، والتزامُ غيرك وشغلتُه وزبونُه 404، وعزلُ مكتبٍ آخر 404، وطلبان في يومٍ واحدٍ ⇒ سجلُّ تحديثٍ واحد، وعددُ استعلامات `today/` لا يكبر بين صفٍّ وخمسة (`CaptureQueriesContext`)، وشغلاتُ الزبون الأحدثَ أوّلاً بكلّ الحالات وبشكلها المحسوم، و«أغلق السابق» على زبونه وحده، والإسنادُ بمفتاحه (403 بدونه، و400 لعضوٍ من خارج المكتب) |
| `accounting_office/tests/test_schedule_overrides.py` | **تعديلُ المكتب والتمديد والتزامات المكتب والأحداث #277**: التعديلُ يُحرّك المنتظِرَ و«مش لازم» ولا يمسّ المقدَّم (وعددُ `ObligationDateChange` بعدد ما تغيّر)، و`platform_official_date` يُملأ ثم يُمسح بالرجوع للمنصة، ونشرةُ المنصة تُتجاهل حين يُعدَّل السطر، والسجلُّ إلحاقيٌّ والساري آخرُ صفّ، ورفضُ كودٍ مجهولٍ وقيمةٍ خارج حدّيها، **وكلفةُ الإعادة لا تكبر بعدد الالتزامات**؛ وتحديثُ المنصة: غيرُ المعدَّل يتبع النسخة الجديدة (و«مش لازم» معه) والمقدَّمُ لا، وتنبيهُ `schedule_dates_changed` بعددِه الصحيحِ ومرّةً واحدة، وسطرٌ سقط من الجديدة يُنبِّه في `warnings` ولا يغيّر تاريخاً؛ والمعدَّلُ يبقى مع تنبيه «تُبقي أم تأخذ الجديد؟» ثم «أُبقي تاريخي» يُسقطه و«آخذ الجديد» يُطبّق المنصة؛ **والتمديد**: يحرّك الأحمرَ وحده ويُبقي الأصفرَ على الموعد الداخليّ، ونافذةُ `week` تتبعه، ويُرفض للمقدَّم ولتاريخٍ ليس بعد الفعليّ وللملاحظة الفارغة، ويُسقط تنبيهَ `obligation_late` من الجرس بلا حذف صفّه، وإلغاؤه يكتب `extension_cleared`؛ **والتزامُ المكتب**: يظهر في «اليوم» والتقويم بعلامة «من المكتب» ويُحفظ بالتحديث، وتعطيلُه يوقف الجديد فقط، وتعديلُه يُعيد حسابَ غير المقدَّم وحده؛ **والحدث**: اقتطاعٌ في X ⇒ `X+30` و`origin=event`، ونوعٌ غيرُ مفعَّلٍ يُرفض، وزبونٌ بلا خدمة الرواتب يُرفض، وحدثٌ مكرّرٌ ⇒ التزامٌ واحد، وإسرائيل «لا قاعدة»، وسطرُ الحدث لا يُولَّد دورياً؛ **والهجرة**: فلسطين v2 بستة أسطرٍ (5 منسوخة + الحدث) وتاريخُ نشرها، والتزاماتُ فلسطين القائمة تنتقل إليها بلا تغيّرٍ ولا تنبيه، وعكسُها يحذف ما أنشأته وحدَه |
| `accounting_office/tests/test_schedule_overrides_api.py` | **نقاطُ #277**: `GET deadline-rules/` يحمل مفاتيحَه القديمة ويضيف `platform`/`override`/`history`؛ و`override/` بلا `office.settings.manage` ⇒ 403 وبالمفتاح ⇒ 200 والعدّادُ صادق، و`keep-override/` و`clear-override/`، ورمزٌ مجهول ⇒ 400؛ والتمديد عبر API (`extend/` و`clear-extension/`) بالمفتاح، وملاحظةٌ فارغة ⇒ 400، والتزامُ غيرك ⇒ 404؛ و`custom-rules/` إنشاءٌ وتعديلٌ و`DELETE` ⇒ 405، وقراءةٌ لكل عضو وكتابةٌ بالإعدادات، وعزلُ مكتبٍ آخر، ونوعُ قاعدةٍ مجهول ⇒ 400، **ودوريةُ نصفٍ سنويّ في التزام المكتب ⇒ 400 بلا صفّ (ورسالةُ الحدث تبقى لـ`event`)**؛ والأحداث (`clients/<pk>/events/`) تسجيلٌ يُرجع الحدثَ والتزامَه، وزبونٌ لا تراه 404 أو زبونُ مكتبٍ آخر 404، وبلا مفتاح الكتابة 403، ونوعٌ معطَّل ⇒ 400؛ و`opens` في سطر الجرس (`deadline_rules` لنوعَي اللائحة و`client` لغيرهما) |
| `accounting_office/tests/test_documents.py` | **قائمةُ الأوراق #278 (خدمياً)**: «فواتير المشتريات» بندٌ **واحد** لزبونٍ عنده مسك دفاتر وقيمة مضافة (معيار القبول ١)، والشهرُ يُحفظ في أوّل التالي والسنةُ في 1 يناير، والتشغيلُ مرّتين لا يكتب صفّاً، وخدمةٌ تبدأ في آذار لا تُطلب في كانون الثاني؛ وطبقاتُ القائمة: إخراجُ المكتب يُسقط، وخيارُ الزبون يفرض بنداً رفضته شروطه ويُسقط بنداً انطبق، و«تقرير مدقق» غائبٌ عن الفرد وحاضرٌ للشركة، وبطاقةٌ ناقصةُ التصنيف لا تطابق شرطاً؛ والحالات: «وصلت» تحفظ الفاعل والتاريخ والقناة، والقناةُ الغائبةُ 400، والحالةُ المجهولةُ 400، والتراجعُ يمحو الثلاثة، وتسميةُ السنوي «مش لازمة هالسنة»؛ و«ناقصه أوراق»: مطلوبةٌ تُشعلها وناقصةٌ تُبقيها ووصلت/مش لازمة تُسقطانها، وصفٌّ خارج الفترة أو بلا خدمةٍ لا يُشعلها، والمقدَّمُ لا يُقاس؛ وعدّادُ `وصل/مطلوب`؛ والبذرةُ (**٤١ بنداً: 12+8 فلسطين و13+8 إسرائيل** — ومنها بندا الرواتب الأربعة بكودهما وخدمتهما وحالتِهما الابتدائية #279) وعكسُها يحذف أكوادَها وحدها؛ ومددُ الحفظ الثلاث بمصادرها ونصُّها؛ وبندُ مكتبٍ بكوده المشتقّ؛ وجولةُ الإصلاح الأولى: خدمةٌ رُفع عنها «آخر فترة علينا» تسقط بنودَها في الشهر الذي **تحويه** فترتُها وتبقى بنودُ الخدمة الأخرى، واستعلامُ التقدّم مقيَّدٌ بمدى الالتزامات المنتظِرة |
| `accounting_office/tests/test_documents_api.py` | **نقاطُ #278**: كلُّ صفٍّ في الشبكة بعدد الأشهر وخانةٌ `null` لبندٍ بلا صفّ (معيار القبول ٥)، وحمولةُ التسميات ومددِ الحفظ والسنوات، والقائمةُ السنوية؛ وتسجيلُ الحالة (والمالك يُحفظ فاعلاً)، والقناةُ الغائبة 400 والمجهولةُ 400، وزبونُ الزميل 404 وصفُّ مكتبٍ آخر 404؛ والملفُّ: رفعٌ يُرجع 201 بلا `file_url` ولا رابطِ تخزينٍ في أيّ ردّ، والحالةُ لا تتغيّر، وتنزيلٌ بايتاتٍ من `stream_stored_asset`، وحذفٌ يمحو الصفَّ ويستدعي `destroy_cloudinary_asset` بالرابط، وملفٌّ فارغٌ أو نوعٌ ممنوعٌ 400؛ وقالبُ البنود: قراءةٌ لكل عضو و`system` خاطئٌ 400، و«ضمن القائمة» بلا `office.settings.manage` ⇒ 403، وإنشاءُ بندٍ وتعديلُه بالمفتاح و`DELETE` غيرُ مسموح، وخيارُ الزبون يغلب القالبَ ويظهر في التوليد؛ و«اليوم»: عدّادُ `missing_docs` وفلترُه و`docs` لكل صفّ، والمحسومُ يُسقطه، وعددُ الاستعلامات لا يكبر باثنَي عشرَ صفّاً إضافياً؛ وجولةُ الإصلاح الأولى: رفعٌ فوق السقف 400 بلا قراءةٍ كاملة، وفشلُ حفظ صفّ الملف يمحو الأصلَ المرفوع، وبندُ المنصّة بلا `id`، وبندُ المكتب لا يُقلب من `choice/`؛ وجولةُ الإصلاح الثانية: فشلُ الرفع يُبقي حالتَه (سقفُ الخطّة 400 بنصّه للمستخدم، وخطأُ المزوّد 502 بجملةٍ عامّةٍ ونصُّه في السجلّ لا في الردّ)، ولوحةُ الزبون تعرض بنودَ المكتب **المفعَّلة** وحدها وقائمةُ الإعدادات تعرض المعطَّلَ معها |
| `accounting_office/tests/test_payroll.py` | **الرواتب — متابعةُ الاستحقاق #279**: نصفُ سنويّ فترتاه يناير–يونيو ويوليو–ديسمبر ودوريةُ سطرٍ لا خدمة وأيامُه من مفتاح الربعيّ؛ **102 والـביטוח يتبعان دوريةَ الخدمة** (شهريةٌ ⇒ التزامٌ لكل شهر، وكلُّ شهرين ⇒ التزامٌ لشهرين) من **v2**؛ و`טופס 126 חציוני` **التاريخُ القانونيّ 18 تموز 2026 و18 كانون الثاني 2027 قبل الزحزحة**؛ وفلسطين: الاقتطاعُ في 15 من التالي، و**الكشفُ السنوي 30 نيسان 2027 بـ`needs_review`**، والضمانُ الاجتماعي لا يُولَّد؛ **وإعدادُ الالتزامات**: بندٌ أُخرج لزبونٍ يسقط له وحده ويبقى لغيره، **والتقويمُ يقرأ القرار نفسه**؛ و**دوريةُ الرواتب**: «رُبعية» مرفوضةٌ برسالتها في **المسارَين** (الإضافة وتغيير الدورية) وشهريةٌ وكلُّ شهرين مقبولتان وخدمةٌ أخرى تحفظ ربعيتها؛ **وأوراقُ الرواتب**: الكشفُ لزبون الخدمة وحده وحالتُه «مطلوبة»، و«تغييرات الموظفين» «مش لازمة» ولا تُشعل «ناقصه أوراق» (المطلوبُ واحدٌ ويصل ⇒ لا شارة)، وبندُ المكتب يبدأ «مطلوبة»؛ **والهجرة**: إسرائيل v2 (كلُّ حقلٍ منسوخٌ حرفاً + سطرُ 126 النصف سنوي) وفلسطين v3 (سبعةُ أسطر + الكشفُ السنوي) وبنداتُها الأربعة، وعكسُها يحذف ما أنشأته وحدها ولا يمسّ v1/v2 ويُعاد بالزرع ثانيةً؛ **وحارسُ انحراف** اختياراتِ السجلّ مقابل أكواد الرواتب غير الحدثية في النسخ السارية وتسمياتِها |
| `accounting_office/tests/test_appointments.py` | **المواعيدُ والتذكيران #281**: الحجزُ بتاريخه ووقته، ورفضُ نوعٍ رابع، وإلغاءٌ يكتب حالةً لا يحذف، ومرفوضُ الأفعال على الملغى/المنتهي، وتأكيدٌ يكتب صفَّ سجلٍّ ويختم `confirmed_at` (وبلا جهةٍ 400 ولا صفّ)، والقائمةُ بمنتقي الأنواع؛ **و`client_owes`** بحالاته الأربع بلا قاعدة بيانات؛ **ومولّد الموعد الرسميّ**: سبعةُ أيامٍ قبل الموعد لا قبله بيوم، والثاني عند يومين، والتمديدُ يُحرّك الموعدَين ويُطبَع الممدَّدُ في النصّ، والمقدَّمُ/المدفوعُ/بلا شيءٍ لا بندَ له، والنوعُ المطفأُ يختفي؛ **ومولّد الموعد**: قبله بيوم، وإعدادُ المكتب وتخصيصُ الزبون، والملغى والمنتهي بلا تذكير؛ **وجولةُ التصليح الأولى**: تأكيدُ الحجز لا يستهلك نافذةَ «قبله بيوم» (والتأكيدُ داخل النافذة يُسكتها)، والتزامان في فترةٍ واحدةٍ **بندٌ واحد** بأقرب موعدٍ واتّحاد الناقص ومجموع المستحقّ (500.00 في النصّ)، و«شيل» يُسكت النافذةَ حتّى التالية، والإرسالُ لا يتكرّر في اليوم نفسه، والنافذةُ الثانيةُ تُفتح مرّةً، ونصُّ الموعد الرسميّ يُقرأ في الحالات الثلاث بلا فراغٍ مزدوجٍ ولا عنوانٍ معلَّق (عربيًّا وعبريًّا)، وفلترُ `reminder_type` لا يعرض إلا نوعَه؛ **وجولةُ التصليح الثانية**: الأبكرُ الذي لا شيءَ عليه لا يفتح نافذةَ الموعد الرسميّ، والمدفوعُ الأبكرُ لا يُسقط تذكيرَ الموعد الحقيقيّ، والماضي المنتظِرُ لا يُخفي الممدَّدَ اللاحق، وفترةٌ مضت مواعيدُها كلُّها بلا بند، وموعدان في اليوم نفسه بندٌ واحد بوقتَيهما، و«أجّل» يمسح `confirmed_at`، وقيمةُ الغياب في نصّ التأكيد بلغة الجهة، ومبلغُ نصّ الرسالة لعضوٍ بلا `office.amounts.view` استثناءٌ مثبَّت؛ **و«اليوم» والتقويم**: عدّادُ المواعيد وترتيبُها بوقتها، والملغى خارج العدّ، والتقويمُ يحمل مواعيدَ مداه وفلترَ زبونه؛ **والـAPI**: العزلُ 404 والكتابةُ بمفتاحها، وأفعالُ الموعد الأربعة، والقائمةُ بيومها وبرؤية العضو |
| `accounting_office/tests/test_reminders.py` | **التذكيرات — «جاهز للإرسال» #280 (خدمياً)**: الإذنُ يُمنح ويُسحب بتاريخيهما ومَن سحبه، ونوعٌ أو قناةٌ مجهولة 400، ورافضُ الإذن أو نوعُه ليس في `consent_types` لا يظهر، والجهةُ الجديدة تأخذ افتراضيَّ المكتب؛ **والقوالب**: نصٌّ عربيٌّ وعبريٌّ لكلٍّ من الأنواع الأربعة، والبديلُ يغلب والافتراضيُّ لا يُكتب مكانه، والرمزُ المجهول 400 يسمّيه، ونصٌّ فارغٌ 400، و`render_reminder_body` يترك ما ليس من الستّة ولا يسقط على قوس؛ **والإيقاع**: أوّلُ تذكيرٍ بعد انتهاء الفترة بيوم، والثاني بعد ثلاثةٍ من الإرسال، ولا رابعَ بعد الثالث، و«وصلت» تخرج و«وصلت ناقصة» تبقى، والتنحيةُ تُعيد المؤقّت ولا تُعدّ، و«كلّمناه» يُعدّ، والـ`undo` يُنقص عدّاً ولا يُبطَل مرّتين؛ **والقائمة**: شخصٌ لزبونين = رسالةٌ واحدة، وتعيينُ النوع يغلب الرئيسية، ونصُّ المستلِم بلغته، وبديلُ المكتب يظهر في الرسالة، وبلا هاتفٍ تظهر (`has_phone=false`)، وبلا تجميعٍ رسالةٌ لكل بند، والمنتهي لا يُعرض، وفلترُ المسؤول، وزبونُ مكتبٍ آخر لا يُعرض، والنوعُ بلا مولّدٍ يُعيد فراغاً؛ **والحواجز**: يومُ راحة الزبون وعطلةُ المكتب يؤجّلان الظهور لا يُلغيانه، والتأجيلُ يحجب حتى تاريخه و`until=None` يمسحه وتاريخُ اليوم مرفوض؛ **والتصعيد**: تنبيهُ المسؤول يومَ الاستحقاق التالي بلا مبلغ، وصاحبُ المكتب بعد يومين، ولا شيءَ قبل الفاصل، مرّةً واحدةً في اليوم، ويُسقطه اكتمالُ الأوراق عند القراءة، ويفتح تبويبَ الأوراق؛ **والكلفة**: عددُ الاستعلامات نفسُه لزبونٍ وخمسة؛ وشكلُ اللقطة في السجلّ، والسجلُّ الأحدثَ أوّلاً، وجهةٌ أو زبونٌ خارج الرؤية يُرفض. **وجولةُ الإصلاح الأولى**: شهرٌ وسنةٌ يبدآن في اليوم نفسه ⇒ تنبيهان لا واحد، و`{due_date}` في النصّ يومُ التذكير القادم بـ`dd/MM/yyyy` بعد يوم راحة، و`sent` واتسابٌ وحدها والفراغُ يعنيها، وتنحيةُ ثلاثة بنودٍ استعلامُ بياناتٍ واحد و`bulk_create` واحد، ولا مسحَ لأوراق زبونٍ بلا تنبيهٍ قائم، وحارسا `resolve_settings_for_clients` وقراءتُه مرّةً للحمولة، وتنبيهُ التذكير مُثبَتٌ قبل اكتمال الأوراق |
| `accounting_office/tests/test_reminders_api.py` | **نقاطُ #280**: حقولُ الإذن على الجهة، و`contacts/<id>/consent/` يُمنح ويُسحب ويعيد مَن سحب، ونوعٌ/قناةٌ/قيمةٌ غير منطقية 400، والكتابةُ بلا مفتاحها 403؛ و`reminder-templates/` تُقرأ لكل عضوٍ (ثمانيةُ أسطر)، والبديلُ `PUT` و«ارجع للافتراضي» `DELETE`، والرمزُ المجهول 400 يسمّيه، وبلا `office.settings.manage` 403، ونوعٌ أو لغةٌ مجهولة 400؛ و`ready-to-send/` تجمع اليومَ رسائلَ، و`sent/` صفٌّ لكل بندٍ بلقطة الهاتف، و`manual/` تلفونٌ أو زيارة فقط، و`dismiss/` بسببٍ وبلا نصّ، و`postpone/` بتاريخٍ بعد اليوم (واليوم 400)، وزبونُ غيرك لا يظهر ولا يُرسَل له، والأفعالُ الأربعة بلا مفتاح الكتابة 403، ونوعٌ مجهول 400، والفلترُ بنوعٍ بلا مولّدٍ فراغ؛ و`reminder-log/` تُقرأ و`PUT`/`PATCH`/`DELETE` 405 والصفُّ باقٍ، والـ`undo` يشير إلى ما يُبطله وإبطالُه 400، وسجلُّ الزبون على `clients/<pk>/reminder-log/`، وزبونُ الزميل 404 على السجلّ وعلى الإبطال؛ و`office-holidays/` تُقرأ لكل عضوٍ وتُكتب بالمفتاح، والتكرار 400 والحذف 204؛ و`reminder_auto_send` مقفلٌ برسالته، والنافذةُ تُرفض خارج 0–23 وبترتيبٍ مقلوب، ومجموعةُ «التذكيرات والنصوص» تُخدَم بقيمها الافتراضية. **وجولةُ الإصلاح الأولى**: النافذةُ تُرفض ببدايةٍ متأخّرةٍ عن النهاية كذلك، و`sent/` قناةٌ غيرُ الواتساب 400، و`serializer_class` السجلّ سطرُ قراءةٍ لا حمولةُ تأجيل (وحقولُه هي حقولُ الردّ)، ويومُ النقاط أربعاءُ ثابتةٌ فلا قائمةَ فارغةً كلَّ جمعة. **وجولةُ التصحيح الثانية**: `consent_withdrawn_by` كائنٌ `{id, name}` على قائمة جهات الزبون وتفصيلها وردّ `promote` (و`None` لجهةٍ لم يُسحب إذنها)، وعددُ الاستعلامات ثابت مهما بلغ عدد الجهات المسحوبة، و`sent/` بنصٍّ فارغٍ أو مسافات 400 ولا صفَّ يُكتب |
| `accounting_office/tests/test_fees.py` | **الأتعاب ١ #282**: طريقةُ الأتعاب إعدادٌ مكتب ← زبون وافتراضُها «اشتراك»، و`hourly` مرفوضةٌ برسالتها على المستويين، و`fee_auto_approve` مقفلٌ (400 على `true`)؛ **والتوليدُ**: أوّلُ تشغيلٍ في الشهر مسودّةٌ واحدة ومرّتان لا تضيفان، ويومٌ لاحقٌ في الشهر لا يولّد ثانية، والتغييرُ يضيف صفَّ سعرٍ ومسودّةُ نيسان تأخذ الجديد، والتناسبُ نصفٌ تماماً في شهرٍ من ثلاثين و16/31 في شهرٍ من أحدٍ وثلاثين، ولا مسودّةَ لزبونٍ منتهٍ ولا لاشتراكٍ انتهى قبل الشهر ولا لشهرٍ داخل إيقاف الفوترة؛ **و«سعرٌ لكل خدمة»**: مجموعُ الخدمات المستحقّة في الشهر + إضافاتِ الشهر السابق، و«فاتورة لحالها» لا تدخل مسودّة؛ **والاعتماد**: صاحبُ المكتب ومديرُ المكتب يعتمدان والمحاسبُ 403 (والمسودّةُ باقية)، و«اعتمد الكل» يعتمد كلَّ منتظرة، والإلغاءُ قبل الاعتماد وحده، والمعتمدةُ لا يُعاد توليدها ولا تتغيّر، و`can_approve_fee_drafts` ترفض المحاسب؛ **والتنبيه**: لا شيء قبل ثلاثة أيام، ثم صفٌّ لكل معتمِدٍ بمرجعٍ واحد ونصٍّ بلا مبلغ، ولا تكرارَ في اليوم الرابع، ويسقط من الجرس باعتماد المسودّة؛ **والـAPI**: الإضافةُ والقراءةُ للاشتراك والإضافة، والتاريخُ المكرَّر 400، والقناعُ `null` للمحاسب في المسودّة وبنودها والاشتراكات، وكتابةُ مبلغٍ بلا المفتاح 403، و`DELETE` على الجموع والأفعال 405 ولا صفَّ يُحذف من مسار التفصيل، وزبونُ مكتبٍ آخر 404 ومسودّةُ مكتبٍ آخر لا تُقرأ ولا تُعتمد؛ **وجولةُ التصليح الأولى**: تغييرُ سعرٍ في منتصف الشهر يحكمه بسعره كاملاً، وصفٌّ `starts_on = ended_on = 20/5` يُنسب 20/31، وشهرٌ موقوفٌ لا مسودّةَ له وإضافاتُه تنتظر ما بعد الإيقاف، وإضافةٌ سُجِّلت بعد توليد مسودّة شهرها تظهر في التالية مرّةً واحدة وإلغاؤها يُعيدها، وفرادةُ `(زبون، سنة، شهر)` تُسقط تكراراً في القاعدة، و«اعتمد الكل» لا يعتمد الملغاة ويرفض المحاسب 403، ومحاسبٌ يرى زبونَه وحده في القوائم الثلاث و404 على كتابة زبون زميل، وفبراير 14/28 وأوّلُ الشهر كاملاً وإيقافٌ مفتوح وحدُّه، وكلفةُ التوليد و«اعتمد الكل» لا تكبر بعدد المسودّات؛ **ونقطةُ `fees/service-prices/`**: 201 بالمعرّف أو بالخدمة والزبون، وإعادةُ `POST` 200 تحديثاً لا صفّاً ثانياً، و403 بلا مفتاح الكتابة، و404 لخدمة مكتبٍ آخر، والقناعُ للمحاسب و403 على كتابة مبلغه، و405 على `DELETE`، وتوليدُ مسودّةٍ من سعرٍ مُدخَلٍ عبر الـAPI |
| `accounting_office/tests/test_payments.py` | **الدفعات و«اللي عليه» وكشف الحساب #283**: دفعةُ 500 على 300 و350 ⇒ الأقدمُ تُسدَّد بالكامل والثانيةُ `partial` بباقٍ 150 و`due = 150`؛ وزيادةُ 700 على 650 ⇒ `credit = 50` و`due = -50`؛ **والرصيدُ الدائنُ يُستهلك بتخصيصٍ جديد** عند اعتماد الفاتورة القادمة و`due` يبقى صحيحاً؛ و`draft`/`cancelled` لا تدخلان الحساب ولا الكشف؛ والتخصيصُ الصريحُ يُلغي «الأقدم» ويُرفض بأكثرَ من الدفعة أو من المتبقّي أو بصفرٍ أو على غير المعتمدة؛ والشطبُ يخفّض `remaining` ولا يمحو صفّاً (عدُّ الصفوف والمبالغ قبل/بعد)، وسببٌ فارغٌ أو مبلغٌ فوق المتبقّي 400، ومديرُ المكتب والمحاسبُ 403؛ **ورقمُ الإشعار** متسلسلٌ `{year}-{n:05d}` وفريدٌ للعام والشركة، و**عدّادٌ لا `MAX+1`** (رقمٌ عالٍ مزروعٌ لا يُغيّر التالي)؛ وفلاترُ `client`/`method`/`date_from`/`date_to`، و405 على الجمع و404 لسندٍ واحد (لا مسارَ تفصيل)؛ والقناعُ `null` في `amount`/`due`/`credit`/`remaining`/`total` على الدفعات والمسودّات والزبائن والكشف؛ والعزلُ: دفعةُ مكتبٍ آخر لا تُنشأ ولا تُقرأ، وتخصيصٌ على مسودّة غيره 400 بلا صفّ؛ وكشفُ الحساب: فلترُ الحالة في الاستعلام، وبحثُ الاسم، وترقيمُ الصفحتين، و`client_due` للزبون المفلتر و404 لغيره؛ وسطرُ العلم الضريبيّ مجموعُ الالتزامات غير المدفوعة **خارجَ `due`** |
