"""سجلّ إعدادات مكتب المحاسبة — تعريفٌ واحد لكل مفتاح، ومُتحقِّقٌ واحد.

**القاعدة (#254، وكل تذاكر الموديول):** كل ما يختلف من مكتبٍ لمكتب = إعداد، وما
يختلف من زبونٍ لزبون = تخصيصٌ فوقه. هذا الملفّ يقول **ما هو الإعداد**: نوعه،
ومستوياته المسموحة، وافتراضيّه (أو أنه «يُختار»). ولا يقول **ما قيمته** — ذلك
`accounting_office/services.py` (`resolve_setting`) وحده.

**القواعد المحسومة في #271:**
- `tax_system` و`office_size` **بلا افتراضي**: يُختاران. حتى يُختارا تبقى
  الواجهة على خطوة أول تشغيل.
- `rest_days` افتراضيّه الجمعة، وهو **أيام عطلة المكتب**. تخصيص الزبون هو **يوم
  راحة الزبون** — بالمحلّل نفسه، لا بحقلٍ ثانٍ في البطاقة.
- `filing_method` معناه في إسرائيل (19/23)، والبطاقة تُظهره للزبون الإسرائيليّ
  وحده — عرضٌ في الواجهة لا قاعدةٌ هنا.
- **الثوابت ليست هنا**: التاريخ لا يُمحى، والزبون لا يدخل البرنامج… إعداداتٌ لا
  قيَمٌ يملكها المكتب.
"""
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError

KIND_CHOICE = "choice"
KIND_BOOL = "bool"
KIND_INTEGER = "integer"
KIND_WEEKDAYS = "weekdays"
#: #277: قائمةُ مفاتيحَ من `choices` بلا تكرار — «أنواع الأحداث المفعّلة».
KIND_MULTI_CHOICE = "multi_choice"
#: #284: نصٌّ حرّ — أكوادُ حسابات الدفاتر اليوم، ولا يُقفل على قائمةٍ مخزَّنة هنا:
#: الحسابُ يُحلّ عند الترحيل من شجرة الشركة نفسها، وكودٌ يُكتب غلطاً يردّ 400
#: باسم مفتاحه بدل أن يُقبل ثم يسقط القيد.
KIND_TEXT = "text"

LEVEL_OFFICE = "office"
LEVEL_CLIENT = "client"
LEVEL_ITEM = "item"

SETTING_LEVELS: tuple[str, ...] = (LEVEL_OFFICE, LEVEL_CLIENT, LEVEL_ITEM)

#: مجموعات شاشة الإعدادات — ثابتٌ مستقلّ عن المستويات وإن تشارك `office` اسماً:
#: المستوى يقول «أين تُضبط القيمة»، والمجموعة تقول «أين تُعرض» — وقد تختلفان.
GROUP_OFFICE = "office"
#: #274: مجموعةُ الضريبة ولائحة المواعيد — الموعدُ الداخليّ ومدى التقويم.
GROUP_SCHEDULE = "schedule"
#: #276: مجموعةُ «التأخير والتنبيهات» — درجتا التأخير ومستلِمُ كلٍّ منهما.
GROUP_ALERTS = "alerts"
#: #280: مجموعةُ «التذكيرات والنصوص» — عددُ التذكيرات وإيقاعُها ونافذةُ الإرسال.
GROUP_REMINDERS = "reminders"
SETTING_GROUPS: tuple[tuple[str, str], ...] = (
    (GROUP_OFFICE, "المكتب"),
    (GROUP_SCHEDULE, "الضريبة ولائحة المواعيد"),
    (GROUP_ALERTS, "التأخير والتنبيهات"),
    (GROUP_REMINDERS, "التذكيرات والنصوص"),
)

#: مستلِمو التنبيه (#276) — مفاتيحُ الاختيار يقرؤها `services._alert_recipient_ids`.
#: «المسؤول» = `PeriodTask.effective_assignee`، و«صاحب المكتب» = عضوٌ نشطٌ بدور
#: `manager` في هذا المكتب (التعريفُ القائم، لا تعريفٌ ثانٍ).
ALERT_TO_ASSIGNEE = "assignee"
ALERT_TO_ASSIGNEE_OWNER = "assignee_owner"
ALERT_TO_OWNER = "owner"
ALERT_TO_CHOICES: tuple[str, ...] = (
    ALERT_TO_ASSIGNEE,
    ALERT_TO_ASSIGNEE_OWNER,
    ALERT_TO_OWNER,
)
ALERT_TO_LABELS: dict[str, str] = {
    ALERT_TO_ASSIGNEE: "المسؤول",
    ALERT_TO_ASSIGNEE_OWNER: "المسؤول وصاحب المكتب",
    ALERT_TO_OWNER: "صاحب المكتب",
}

#: نصّ القيمة الغائبة — ثابتٌ واحدٌ في الخادم، لا نسخةٌ في كل شاشة.
NOT_CHOSEN_LABEL = "غير مختار"

#: أنواعُ الأحداث التي تُسجَّل في ملفّ الزبون («صار حدث») — **قائمةٌ تُوسَّع صفّاً**،
#: ولكل نوعٍ سطرٌ في لائحة المنصة بـ`cadence="event"` و`event_kind` يطابقه. ونوعٌ
#: واحدٌ الآن: الاقتطاع. وإسرائيل بلا سطر حدثٍ حتى يوجد مصدرٌ بحثيّ له.
#:
#: **وهي هنا لا في النماذج** لأن إعداد `enabled_event_kinds` يقرأ مفاتيحها،
#: والسجلَّ لا يستورد النماذج (دَّورةُ استيراد)، والنماذجُ تستورد السجلّ.
EVENT_KIND_WITHHOLDING = "withholding"
EVENT_KIND_CHOICES: tuple[tuple[str, str], ...] = (
    (EVENT_KIND_WITHHOLDING, "اقتطاع ضريبة مصدر"),
)
EVENT_KIND_LABELS: dict[str, str] = dict(EVENT_KIND_CHOICES)

#: #279: بنودُ خدمة الرواتب في **أحدث نسخ اللائحة** — أكوادٌ وتسمياتُ أسطرها
#: (أسماءُ الأسطر في اللائحة نفسها، فلا اسمَ ثانٍ يفترق عنها). وهي هنا لا في
#: النماذج: إعدادُ `payroll_obligations` يقرأ مفاتيحها، والسجلَّ لا يستورد النماذج.
#: **وسطرُ الحدث خارجها**: سطرُ الاقتطاع يحكمه «أنواع الأحداث المفعّلة»
#: (`enabled_event_kinds`) وحده، لا هذا الإعداد — فإدراجُه هنا يُوهم أنه يُتحكَّم به.
#: **وحارسُ الانحراف** اختبارٌ يقارن هذه القائمة بأكواد `service_code="payroll"`
#: **غير الحدثية** في النسخ السارية — بندٌ يُضاف إلى اللائحة بلا اختيارٍ هنا يسقطه الاختبار.
PAYROLL_OBLIGATION_CHOICES: tuple[tuple[str, str], ...] = (
    ("ps_payroll_withholding", "اقتطاع ضريبة الرواتب"),
    ("ps_social_security", "اشتراكات الضمان الاجتماعي"),
    ("ps_payroll_annual_statement", "الكشف السنوي للرواتب"),
    ("il_withholding_102", "ניכויים — טופס 102"),
    ("il_bl_employees", "ביטוח לאומי לעובדים — 102"),
    ("il_bl_126_semiannual", "טופס 126 חציוני לביטוח לאומי"),
    ("il_annual_126_856", "דוח שנתי 126/856"),
)
PAYROLL_OBLIGATION_LABELS: dict[str, str] = dict(PAYROLL_OBLIGATION_CHOICES)

#: #280: أنواعُ التذكير الأربعة — **تُعرَّف هنا لا في النماذج** لأن إعدادَي
#: `reminder_types_enabled` و`reminder_default_consent_types` يقرآن مفاتيحها،
#: والسجلَّ لا يستورد النماذج (دَّورةُ استيراد). والنماذجُ تعيد تصديرها كما في
#: أنواع الأحداث (#277) — فلا نسختان تفترقان عند أوّل نوعٍ يُضاف.
REMINDER_DOCUMENTS = "documents"
REMINDER_DEADLINE = "deadline"
REMINDER_BALANCE = "balance"
REMINDER_APPOINTMENT = "appointment"
#: #283/ب: إشعارُ القبض — بندٌ لكل دفعةٍ دخلت اليوم يُعلم بها الزبون. وليس
#: تذكيراً بدَينٍ (`balance`) بل إثباتَ استلامٍ: اتجاهُه «وصلنا» لا «عليك».
REMINDER_FEE_RECEIPT = "fee_receipt"
REMINDER_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    (REMINDER_DOCUMENTS, "أوراق ناقصة"),
    (REMINDER_DEADLINE, "موعد رسمي قريب"),
    (REMINDER_BALANCE, "اللي عليه"),
    (REMINDER_APPOINTMENT, "تذكير موعد"),
    (REMINDER_FEE_RECEIPT, "إشعار قبض"),
)
REMINDER_TYPES: tuple[str, ...] = tuple(key for key, _label in REMINDER_TYPE_CHOICES)
REMINDER_TYPE_LABELS: dict[str, str] = dict(REMINDER_TYPE_CHOICES)

#: #286: طريقتا إدخال دفتر الزبون — تُعرَّفان هنا لا في النماذج: إعداد
#: `book_entry_method` يقرأ مفاتيحهما، والسجلَّ لا يستورد النماذج (دَّورةُ استيراد).
#: والتسميةُ عربيةٌ في الطرفين لأن الإعدادَ يُعرَض في اختيارٍ واحد لا في شاشتين.
BOOK_ENTRY_METHOD_DOCUMENT = "document"
BOOK_ENTRY_METHOD_MONTHLY = "monthly"
BOOK_ENTRY_METHOD_CHOICES: tuple[tuple[str, str], ...] = (
    (BOOK_ENTRY_METHOD_DOCUMENT, "ورقة ورقة"),
    (BOOK_ENTRY_METHOD_MONTHLY, "إدخال الشهر"),
)
BOOK_ENTRY_METHODS: tuple[str, ...] = tuple(
    key for key, _label in BOOK_ENTRY_METHOD_CHOICES
)
BOOK_ENTRY_METHOD_LABELS: dict[str, str] = dict(BOOK_ENTRY_METHOD_CHOICES)

#: #285: كيف يُرفَق «إشعار الدفع» برسالة «موعد رسمي قريب» — **نصّاً أو رابطاً أو
#: الاثنين**. تُعرَّف هنا لا في النماذج: إعدادُ `payment_notice_format` يقرأ
#: مفاتيحها، والسجلَّ لا يستورد النماذج (دَّورةُ استيراد).
PAYMENT_NOTICE_FORMAT_TEXT = "text"
PAYMENT_NOTICE_FORMAT_PDF = "pdf"
PAYMENT_NOTICE_FORMAT_BOTH = "both"
PAYMENT_NOTICE_FORMAT_CHOICES: tuple[tuple[str, str], ...] = (
    (PAYMENT_NOTICE_FORMAT_TEXT, "نصّاً"),
    (PAYMENT_NOTICE_FORMAT_PDF, "رابط PDF"),
    (PAYMENT_NOTICE_FORMAT_BOTH, "نصّاً ورابطاً"),
)
PAYMENT_NOTICE_FORMATS: tuple[str, ...] = tuple(
    key for key, _label in PAYMENT_NOTICE_FORMAT_CHOICES
)
PAYMENT_NOTICE_FORMAT_LABELS: dict[str, str] = dict(PAYMENT_NOTICE_FORMAT_CHOICES)
#: #282: طرقُ الأتعاب — تُعرَّف هنا لا في النماذج: إعداد `fee_method` يقرأ
#: مفاتيحها، والسجلَّ لا يستورد النماذج (دَّورةُ استيراد). و«بالساعة» **معروضةٌ
#: ومرفوضة**: قيمتُها محسومة لدى المكتب ويجب أن يراها فيرى أنّها ليست متاحةً
#: بعد، لا أن يظنّ الطريقةَ الوحيدةَ هي الاشتراك. والحارسُ في
#: `accounting_office/services.py` (`_assert_choice_available`) يردّ 400 برسالتها.
FEE_METHOD_SUBSCRIPTION = "subscription"
FEE_METHOD_PER_SERVICE = "per_service"
FEE_METHOD_HOURLY = "hourly"
FEE_METHOD_CHOICES: tuple[tuple[str, str], ...] = (
    (FEE_METHOD_SUBSCRIPTION, "اشتراك شهري + إضافات"),
    (FEE_METHOD_PER_SERVICE, "سعرٌ لكل خدمة"),
    (FEE_METHOD_HOURLY, "بالساعة"),
)
FEE_METHODS: tuple[str, ...] = tuple(key for key, _label in FEE_METHOD_CHOICES)
FEE_METHOD_LABELS: dict[str, str] = dict(FEE_METHOD_CHOICES)

#: نافذةُ الإرسال (§#280/D7): ساعةُ بدايةٍ وساعةُ نهايةٍ تُخزَّنان للمرحلة الثانية
#: ولا تقرؤهما هذه المرحلة. والحدُّ 23 لأن الساعةَ 24 تعني «المنتصف» في لغاتٍ
#: وتُلبس على من يقرأ، فالوضوحُ أولى.
SEND_HOUR_MIN = 0
SEND_HOUR_MAX = 23


class _NoDefault:
    """غيابُ افتراضي: «يُختار» — لا قيمةَ تخمينيةً يحملها البرنامج عن المكتب."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NO_DEFAULT"

    def __bool__(self) -> bool:
        return False


NO_DEFAULT = _NoDefault()

#: أيام الأسبوع بترتيبها القانونيّ — التخزين بمفاتيحها، والترتيب يُطبَّع هنا.
WEEKDAYS: tuple[tuple[str, str], ...] = (
    ("sun", "الأحد"),
    ("mon", "الاثنين"),
    ("tue", "الثلاثاء"),
    ("wed", "الأربعاء"),
    ("thu", "الخميس"),
    ("fri", "الجمعة"),
    ("sat", "السبت"),
)
WEEKDAY_KEYS: tuple[str, ...] = tuple(key for key, _label in WEEKDAYS)
WEEKDAY_LABELS: dict[str, str] = dict(WEEKDAYS)


@dataclass(frozen=True)
class SettingDefinition:
    """تعريف إعدادٍ واحد — لا يحمل قيمة، بل يصف كيف تُقرأ وتُتحقَّق."""

    key: str
    label: str
    kind: str
    levels: tuple[str, ...]
    choices: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    default: Any = NO_DEFAULT
    group: str = GROUP_OFFICE
    note: str = ""
    #: حدٌّ أدنى للأنواع العددية — والسالبُ لا معنى له في «أيامٍ قبل الموعد» ولا
    #: في «مدىً بالأشهر». `None` تعني «لا حدَّ زائداً على النوع».
    min_value: int | None = None
    #: حدٌّ أعلى للأنواع العددية — «ساعةُ الإرسال» تنتهي عند 23 ولا تعرف `None`.
    max_value: int | None = None
    #: تسميةُ الإعداد من منظور الزبون حين تختلف عن تسمية المكتب — «أيام عطلة
    #: المكتب» للمكتب، و«يوم راحة الزبون» تخصيصاً فوقه. القيمةُ والتسميةُ من
    #: السجلّ نفسه، فلا تصنع الواجهة اسماً ثانياً يفترق عنه.
    client_label: str = ""

    def label_for(self, level: str = LEVEL_OFFICE) -> str:
        if level == LEVEL_CLIENT and self.client_label:
            return self.client_label
        return self.label

    @property
    def has_no_default(self) -> bool:
        return self.default is NO_DEFAULT

    @property
    def allows_client_level(self) -> bool:
        return LEVEL_CLIENT in self.levels

    @property
    def allows_item_level(self) -> bool:
        return LEVEL_ITEM in self.levels

    def choice_options(self) -> list[dict[str, str]]:
        """اختيارات الإعداد بتسمياتها — للواجهة، وللاختيارات المشتقّة (أيام الأسبوع)."""
        if self.kind == KIND_WEEKDAYS:
            return [{"value": key, "label": label} for key, label in WEEKDAYS]
        return [
            {"value": value, "label": self.labels.get(value, value)}
            for value in self.choices
        ]


def _canonical_weekdays(value) -> list[str]:
    """قائمة أيامٍ مفاتيحَ، بترتيب الأسبوع، بلا تكرار — أو رفض."""
    if not isinstance(value, (list, tuple)):
        raise ValidationError({"value": "أيام الأسبوع تُرسَل قائمةً."})
    keys = list(value)
    if any(not isinstance(key, str) or key not in WEEKDAY_KEYS for key in keys):
        raise ValidationError({"value": "يومٌ غير معروف في قائمة أيام الأسبوع."})
    if len(set(keys)) != len(keys):
        raise ValidationError({"value": "يومٌ مكرَّر في قائمة أيام الأسبوع."})
    return [key for key in WEEKDAY_KEYS if key in set(keys)]


def _canonical_multi_choice(definition, value) -> list[str]:
    """قائمةٌ فرعيةٌ من اختيارات الإعداد، بترتيب الإعداد، بلا تكرار — أو رفض."""
    if not isinstance(value, (list, tuple)):
        raise ValidationError({"value": f"«{definition.label}» تُرسَل قائمةً."})
    keys = list(value)
    if any(
        not isinstance(key, str) or key not in definition.choices for key in keys
    ):
        raise ValidationError({
            "value": f"قيمةٌ غير معروفة في «{definition.label}».",
        })
    if len(set(keys)) != len(keys):
        raise ValidationError({"value": f"قيمةٌ مكرَّرة في «{definition.label}»."})
    return [key for key in definition.choices if key in set(keys)]


def validate_value(definition: SettingDefinition, value):
    """يُعيد القيمة مُطبَّعةً، أو يرفع `ValidationError` — نقطة التحقّق الوحيدة."""
    if definition.kind == KIND_CHOICE:
        if not isinstance(value, str) or value not in definition.choices:
            raise ValidationError({
                "value": f"قيمة «{value}» غير مقبولة لـ«{definition.label}».",
            })
        return value
    if definition.kind == KIND_BOOL:
        if not isinstance(value, bool):
            raise ValidationError({"value": f"«{definition.label}» مفتاحٌ نعم/لا."})
        return value
    if definition.kind == KIND_INTEGER:
        # `bool` نوعٌ فرعيٌّ من `int` في بايثون — يُستثنى صراحةً وإلا مرّ True = 1.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError({"value": f"«{definition.label}» عددٌ صحيح."})
        if definition.min_value is not None and value < definition.min_value:
            raise ValidationError({
                "value": (
                    f"«{definition.label}» لا يقلّ عن {definition.min_value}."
                ),
            })
        if definition.max_value is not None and value > definition.max_value:
            raise ValidationError({
                "value": (
                    f"«{definition.label}» لا يزيد على {definition.max_value}."
                ),
            })
        return value
    if definition.kind == KIND_WEEKDAYS:
        return _canonical_weekdays(value)
    if definition.kind == KIND_MULTI_CHOICE:
        return _canonical_multi_choice(definition, value)
    if definition.kind == KIND_TEXT:
        if not isinstance(value, str):
            raise ValidationError({"value": f"«{definition.label}» نصّ."})
        return value.strip()
    raise ValidationError({"value": f"نوع إعداد غير معروف: {definition.kind}."})


def validate_level(definition: SettingDefinition, level: str) -> None:
    if level not in SETTING_LEVELS:
        raise ValidationError({"level": f"مستوى غير معروف: {level}."})
    if level not in definition.levels:
        raise ValidationError({
            "level": f"«{definition.label}» لا يُضبط على مستوى «{level}».",
        })


def get_definition(key: str) -> SettingDefinition:
    definition = SETTINGS_REGISTRY.get(key)
    if definition is None:
        raise ValidationError({"key": f"إعداد غير معروف: {key}."})
    return definition


#: #284: كودُ «شيكات برسم التحصيل» — من الحسابات التشغيلية المبذورة
#: (`tenants/services.py`، `OPERATIONAL_ACCOUNT_CODES` وسطرُه في `COA_DATA`).
#: ثابتٌ هنا لا باستيراد `tenants.services`: السجلَّ لا يستورد نماذجَ ولا خدمات
#: (دَّورةُ استيراد)، والرقمَ يحرسه اختبارٌ يقارنه بالمصدر.
CHEQUE_UNDER_COLLECTION_CODE = "1107"

#: #284: كودُ حساب مصروف الديون المعدومة — **لا وجودَ له في بذرة الشجرة** (لا في
#: `COA_DATA` ولا في `ACCOUNTING_FIRM_COA`)، فالافتراضُ يشير إلى حسابٍ يُنشئه
#: `accounting_office/office_journal.py` (`ensure_writeoff_account`) تحت «52»
#: عند أوّل شطب. واختيارُ كودٍ خارج سلسلة البذرة (5201–5206 · 53xx) عمداً: لا
#: يصطدم بحسابٍ قائمٍ في شجرةٍ قديمة. واسمُه وأبوه عند الإنشاء لا هنا.
WRITEOFF_ACCOUNT_CODE = "5290"

#: أول إعدادات الموديول — أربعةٌ لا غير في #271. الباقي يأتي مع تذاكره.
SETTINGS_REGISTRY: dict[str, SettingDefinition] = {
    "tax_system": SettingDefinition(
        key="tax_system",
        label="النظام الضريبي",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=("PS", "IL"),
        labels={"PS": "فلسطيني", "IL": "إسرائيلي"},
        # بلا افتراضي: نظام المكتب اختيارٌ لا تخمين، والزبون يرثه ما لم يُخصَّص.
        default=NO_DEFAULT,
        note="نظام الزبون = نظام المكتب افتراضاً، وقابلٌ للتخصيص لكل زبون.",
    ),
    "office_size": SettingDefinition(
        key="office_size",
        label="حجم المكتب",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE,),
        choices=("solo", "small", "large"),
        labels={"solo": "شخص واحد", "small": "صغير", "large": "كبير"},
        default=NO_DEFAULT,
        note="مكتبٌ فقط — لا معنى لحجم المكتب في زبونٍ بعينه.",
    ),
    "rest_days": SettingDefinition(
        key="rest_days",
        label="أيام عطلة المكتب",
        client_label="يوم راحة الزبون",
        kind=KIND_WEEKDAYS,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=["fri"],
        note="قيمة المكتب = أيام عطلة المكتب، وتخصيص الزبون = يوم راحة الزبون.",
    ),
    "filing_method": SettingDefinition(
        key="filing_method",
        label="طريقة التقديم",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=("electronic", "manual"),
        labels={"electronic": "إلكتروني", "manual": "يدوي"},
        default="electronic",
        note="معناه في إسرائيل (19/23)؛ تُظهره البطاقة للزبون الإسرائيلي وحده.",
    ),
    # ── الضريبة ولائحة المواعيد (#274) ──
    #
    # أيامُ الموعد الداخلي لكل دورية، ومدى التقويم قدّاماً. والقيمُ الافتراضية من
    # المواصفة (#270): شهريٌّ وكلُّ شهرين خمسةُ أيام، ورُبعيٌّ سبعة، وسنويٌّ ثلاثون.
    #
    # **و`item` هنا للشغلة في #275 ولا يُستهلك اليوم**: المستوى مسموحٌ فيصل إعدادُ
    # الشغلة الواحدة بلا تغيير المحرّك، وإضافتُه لاحقاً كانت تكسر توقيعاً.
    "internal_lead_days_monthly": SettingDefinition(
        key="internal_lead_days_monthly",
        label="أيام الموعد الداخلي — شهري وكل شهرين",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT, LEVEL_ITEM),
        default=5,
        min_value=0,
        group=GROUP_SCHEDULE,
        note="كم يوماً قبل آخر موعد فعليّ يقف الموعد الداخليّ للفترات الشهرية.",
    ),
    "internal_lead_days_quarterly": SettingDefinition(
        key="internal_lead_days_quarterly",
        label="أيام الموعد الداخلي — ربع سنوي",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT, LEVEL_ITEM),
        default=7,
        min_value=0,
        group=GROUP_SCHEDULE,
        note="كم يوماً قبل آخر موعد فعليّ للفترات الربعية.",
    ),
    "internal_lead_days_annual": SettingDefinition(
        key="internal_lead_days_annual",
        label="أيام الموعد الداخلي — سنوي",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT, LEVEL_ITEM),
        default=30,
        min_value=0,
        group=GROUP_SCHEDULE,
        note="كم يوماً قبل آخر موعد فعليّ للفترات السنوية.",
    ),
    "calendar_months_ahead": SettingDefinition(
        key="calendar_months_ahead",
        label="مدى التقويم للأمام (بالأشهر)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE,),
        default=12,
        # صفرٌ مباحٌ ومعناه «لا تقويمَ مستقبليّ» — والسالبُ لا معنى له.
        min_value=0,
        group=GROUP_SCHEDULE,
        note="إلى أيّ مدىً يُحسب التقويم قدّاماً.",
    ),
    #: #277: «صار حدث» يولّد التزامه من سطر اللائحة — والأنواعُ المفعّلة تحدّ ما
    #: يُسجَّل. الافتراضُ كلُّ الأنواع: المكتبُ يقلّص لا يبدأ بقائمةٍ فارغة.
    "enabled_event_kinds": SettingDefinition(
        key="enabled_event_kinds",
        label="أنواع الأحداث المفعّلة",
        kind=KIND_MULTI_CHOICE,
        levels=(LEVEL_OFFICE,),
        choices=tuple(key for key, _label in EVENT_KIND_CHOICES),
        labels=EVENT_KIND_LABELS,
        default=[key for key, _label in EVENT_KIND_CHOICES],
        group=GROUP_SCHEDULE,
        note="«صار حدث» في ملفّ الزبون يولّد التزامه لِما يُفعَّل هنا وحده.",
    ),
    #: #279: «أيّ التزاماتٍ تولّدها خدمة الرواتب؟» — قرارُ المكتب يُخصَّص لزبون
    #: (مكتبٌ لا يتولّى الـביטוח לאומי لزبونٍ بعينه يُخرجه له وحده). الافتراضُ
    #: **كلُّ البنود**: المكتب يقلّص لا يبدأ بقائمةٍ فارغة. ويُطبَّق في
    #: `services.rule_applies` وحدها، فيقرأ التوليدُ والتقويمُ قراراً واحداً —
    #: وأما «اليوم» فيقرأ الصفوف المحفوظة، وما وُلد قبل التقليص يبقى حتى يُحسم.
    "payroll_obligations": SettingDefinition(
        key="payroll_obligations",
        label="الالتزامات التي تولّدها خدمة الرواتب",
        kind=KIND_MULTI_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=tuple(key for key, _label in PAYROLL_OBLIGATION_CHOICES),
        labels=PAYROLL_OBLIGATION_LABELS,
        default=[key for key, _label in PAYROLL_OBLIGATION_CHOICES],
        group=GROUP_SCHEDULE,
        note="بندٌ يُخرَج هنا لا يُولَّد بعد الآن ولا يظهر في التقويم؛ وما وُلد قبلُ يبقى حتى يُحسم.",
    ),
    # ── التأخير والتنبيهات (#276) ──
    #
    # إعدادان لا واحد: الأصفرُ («متأخّر داخلي») شأنُ الموظف المسؤول وحده افتراضاً،
    # والأحمرُ («متأخّر رسمي») يبلغ المسؤولَ **وصاحبَ المكتب** لأن الموعدَ الرسميَّ
    # مسؤوليّةُ المكتب كلّه. ومستوى المكتب وحده: المستلِمُ قرارُ المكتب لا قرارُ زبون.
    "late_internal_alert_to": SettingDefinition(
        key="late_internal_alert_to",
        label="مستلِمو تنبيه «متأخّر داخلي»",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE,),
        choices=ALERT_TO_CHOICES,
        labels=ALERT_TO_LABELS,
        default=ALERT_TO_ASSIGNEE,
        group=GROUP_ALERTS,
        note="شغلةٌ تجاوزت موعدها الداخلي — الافتراضُ المسؤول وحده.",
    ),
    "late_official_alert_to": SettingDefinition(
        key="late_official_alert_to",
        label="مستلِمو تنبيه «متأخّر رسمي»",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE,),
        choices=ALERT_TO_CHOICES,
        labels=ALERT_TO_LABELS,
        default=ALERT_TO_ASSIGNEE_OWNER,
        group=GROUP_ALERTS,
        note="التزامٌ تجاوز موعده الرسمي ولم يُقدَّم — الافتراضُ المسؤول وصاحب المكتب.",
    ),
    # ── التذكيرات والنصوص (#280) ──
    #
    # **ما يُرسَل ومتى وبكم**: الأنواعُ المفعّلة، وإيقاعُ «الأوراق الناقصة»
    # (أوّلُ تذكيرٍ بعد انتهاء الفترة بيوم، ثم كلَّ ثلاثةٍ، وبثلاثةٍ كحدٍّ أقصى).
    # والأرقامُ الثلاثة **قابلةٌ للتخصيص لكل زبون**: مكتبٌ يلاحق زبوناً كبيراً
    # بإيقاعٍ أسرع يخصّصه، والافتراضُ يبقى واحداً للباقين.
    #
    # **والإرسالُ التلقائيُّ مقفلٌ مطفأً**: الحقلُ `False` افتراضاً، وأيُّ `True`
    # يُرفَض 400 برسالته (الحارسُ في `services.set_office_setting`) — فالمرحلةُ
    # الأولى **مراجعةُ موظّفٍ قبل كل إرسال**، وإعدادٌ يفتح البابَ قبل أوانه
    # يكسر هذا القرار بصمت.
    "reminder_types_enabled": SettingDefinition(
        key="reminder_types_enabled",
        label="أنواع التذكيرات المفعّلة",
        kind=KIND_MULTI_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=REMINDER_TYPES,
        labels=REMINDER_TYPE_LABELS,
        default=list(REMINDER_TYPES),
        group=GROUP_REMINDERS,
        note="نوعٌ يُطفأ هنا لا يظهر في «جاهز للإرسال» ولا يستهلك تذكيراتٍ.",
    ),
    "reminder_auto_send": SettingDefinition(
        key="reminder_auto_send",
        label="الإرسال التلقائي",
        kind=KIND_BOOL,
        levels=(LEVEL_OFFICE,),
        default=False,
        group=GROUP_REMINDERS,
        note="مقفلٌ مطفأً في المرحلة الأولى — كلُّ رسالةٍ يراها موظّفٌ قبل إرسالها.",
    ),
    "reminder_merge_daily": SettingDefinition(
        key="reminder_merge_daily",
        label="رسالةٌ واحدة لكل شخصٍ في اليوم",
        kind=KIND_BOOL,
        levels=(LEVEL_OFFICE,),
        default=True,
        group=GROUP_REMINDERS,
        note="مفعّلةً تُجمَع بنودُ الشخص الواحد في رسالة؛ مطفأةً تُرسَل رسالةٌ لكل بند.",
    ),
    "documents_reminder_start_days": SettingDefinition(
        key="documents_reminder_start_days",
        label="أوّل تذكيرٍ للأوراق بعد انتهاء الفترة (أيام)",
        client_label="أوّل تذكيرٍ لأوراقي بعد انتهاء الفترة (أيام)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=1,
        min_value=0,
        group=GROUP_REMINDERS,
        note="يومٌ واحدٌ افتراضاً: التذكيرُ يبدأ في أوّل يومٍ بعد انتهاء الشهر.",
    ),
    "documents_reminder_interval_days": SettingDefinition(
        key="documents_reminder_interval_days",
        label="بين التذكير والتذكير (أيام)",
        client_label="بين تذكيري وتذكيري (أيام)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=3,
        min_value=1,
        group=GROUP_REMINDERS,
        note="صفرٌ مرفوض: تذكيرٌ كلَّ يومٍ إلحاحٌ لا متابعة.",
    ),
    "documents_reminder_max": SettingDefinition(
        key="documents_reminder_max",
        label="أقصى عددِ تذكيراتٍ للأوراق",
        client_label="أقصى عددِ تذكيراتٍ لأوراقي",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=3,
        min_value=1,
        group=GROUP_REMINDERS,
        note="بعد الحدّ يتوقّف التذكيرُ ويصعد تنبيهٌ داخليّ للمسؤول ثم لصاحب المكتب.",
    ),
    "reminder_send_hour_start": SettingDefinition(
        key="reminder_send_hour_start",
        label="بداية نافذة الإرسال (ساعة)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE,),
        default=9,
        min_value=SEND_HOUR_MIN,
        max_value=SEND_HOUR_MAX,
        group=GROUP_REMINDERS,
        note="تُخزَّن للمرحلة الثانية؛ المرحلةُ الأولى تُرسِل بيد الموظف في أيّ ساعة.",
    ),
    "reminder_send_hour_end": SettingDefinition(
        key="reminder_send_hour_end",
        label="نهاية نافذة الإرسال (ساعة)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE,),
        default=19,
        min_value=SEND_HOUR_MIN,
        max_value=SEND_HOUR_MAX,
        group=GROUP_REMINDERS,
        note="لا تكون قبل بدايتها — الحارسُ في `services.set_office_setting`.",
    ),
    "reminder_escalation_owner_days": SettingDefinition(
        key="reminder_escalation_owner_days",
        label="بعد كم يومٍ يُصعَّد لصاحب المكتب",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE,),
        default=2,
        min_value=0,
        group=GROUP_REMINDERS,
        note="تنبيهُ المسؤول يسبقه؛ ويبقى صاحبُ المكتب آخرَ من يعلم.",
    ),
    #: #281: تذكيرُ الموعد قبل كم يوم — القيمةُ بالمستوى نفسه لكل نوعٍ آخر
    #: (إعدادُ المكتب، ويُخصَّص للزبون): مكتبٌ يذكّر قبل يومٍ وآخر قبل ثلاثة.
    "appointment_reminder_days": SettingDefinition(
        key="appointment_reminder_days",
        label="تذكير الموعد قبل (أيام)",
        client_label="تذكير موعدي قبل (أيام)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=1,
        min_value=0,
        group=GROUP_REMINDERS,
        note="قبل الموعد بهذا العدد من الأيام يظهر «تذكير موعد» في «جاهز للإرسال».",
    ),
    "reminder_default_consent_types": SettingDefinition(
        key="reminder_default_consent_types",
        label="أنواع التذكير التي يوافق عليها الشخص الجديد",
        kind=KIND_MULTI_CHOICE,
        levels=(LEVEL_OFFICE,),
        choices=REMINDER_TYPES,
        labels=REMINDER_TYPE_LABELS,
        default=list(REMINDER_TYPES),
        group=GROUP_REMINDERS,
        note="تُنسَخ على جهة الاتصال عند إنشائها، وتُعدَّل بعدها لكل شخصٍ وحده.",
    ),
    # ── إشعار الدفع (#285) ──
    #
    # **لا إعدادَ للألوان**: «عليك» أحمر و«إلك» أخضر ثابتان لا يُضبطان، والقريبُ
    # من الصفر رماديٌّ بحدٍّ **واحد** هو هذا — فالألوانُ قرارُ منتجٍ لا ذوقُ مكتب.
    # والحدُّ يُخصَّص لكل زبون: مبلغُ 7 شيكل حدٌّ محسوبٌ في منشأةٍ صغيرة، وصفرٌ
    # فعليّ في منشأةٍ كبيرة يريد كلَّ قرشٍ أحمر.
    "payment_notice_attach": SettingDefinition(
        key="payment_notice_attach",
        label="إرفاق إشعار الدفع بتذكير الموعد",
        client_label="إرفاق إشعار الدفع بتذكير موعدي",
        kind=KIND_BOOL,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=True,
        group=GROUP_REMINDERS,
        note="إطفاؤه لزبونٍ يُخرج الإشعارَ من رسالته وحدها، ويبقى بندُ الموعد كما هو.",
    ),
    "payment_notice_format": SettingDefinition(
        key="payment_notice_format",
        label="صيغة إشعار الدفع",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=PAYMENT_NOTICE_FORMATS,
        labels=PAYMENT_NOTICE_FORMAT_LABELS,
        default=PAYMENT_NOTICE_FORMAT_BOTH,
        group=GROUP_REMINDERS,
        note="النصُّ سطورٌ في الرسالة، والرابطُ ورقةٌ تُفتح — والمرسل يختار.",
    ),
    #: «مبلغ» بلا منازل: الرماديُّ قرارُ عرضٍ («قريبٌ من الصفر»)، والدرهمُ الواحد
    #: لا يغيّر القرار. والسالبُ مرفوض — «حدٌّ سالب» يجعل كلَّ مبلغٍ رماديّاً.
    "payment_notice_gray_threshold": SettingDefinition(
        key="payment_notice_gray_threshold",
        label="حدّ الرمادي في إشعار الدفع (المبلغ)",
        kind=KIND_INTEGER,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        default=10,
        min_value=0,
        group=GROUP_REMINDERS,
        note="مبلغٌ قيمتُه المطلقة تساويه أو تقلّ يُعرَض رماديّاً لا أحمر ولا أخضر.",
    ),
    # ── دفتر الزبون (#286) ──
    #
    # **طريقةُ الإدخال إعدادٌ لا حقل** (د10): مكتبٌ يُدخل ورقةً ورقةً وآخر يُدخل
    # الشهر كاملاً. والافتراضُ «ورقة ورقة» لأنه الأضيق: لا تُجمَع أوراقٌ في حركةٍ
    # واحدة قبل أن يُطلب ذلك. ويُخصَّص لكل زبون، فمنشأةٌ كبيرةٌ تُدخل شهرياً
    # تخصيصُها وحدها ولا يجرّ معها بقية الزبائن.
    "book_entry_method": SettingDefinition(
        key="book_entry_method",
        label="طريقة إدخال دفتر الزبون",
        client_label="طريقة إدخال دفتري",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=BOOK_ENTRY_METHODS,
        labels=BOOK_ENTRY_METHOD_LABELS,
        default=BOOK_ENTRY_METHOD_DOCUMENT,
        group=GROUP_OFFICE,
        note=(
            "«ورقة ورقة» حركةٌ لكل ورقةٍ واردة، و«إدخال الشهر» أوراقُ الشهر في حركة."
        ),
    ),
    # ── الأتعاب (#282) ──
    #
    # **الطريقةُ إعدادٌ مكتب ← زبون** لا عمودٌ في الاشتراك: مكتبٌ يفوتر منشأةً
    # صغيرةً بالاشتراك وأخرى بالخدمات، والافتراضُ الاشتراكُ لأنه أبسطُ شكلٍ
    # يتّفق عليه الطرفان. و«بالساعة» قيمةٌ معروضةٌ مرفوضةٌ حتى تُحسم صيغتُها.
    #
    # **والاعتمادُ التلقائي مقفلٌ مطفأً** كـ`reminder_auto_send`: المسودّةُ يراها
    # صاحبُ المكتب قبل اعتمادها، وإعدادٌ يفتح البابَ قبل أوانه يكسر القرار بصمت.
    "fee_method": SettingDefinition(
        key="fee_method",
        label="طريقة الأتعاب",
        client_label="طريقة أتعابي",
        kind=KIND_CHOICE,
        levels=(LEVEL_OFFICE, LEVEL_CLIENT),
        choices=FEE_METHODS,
        labels=FEE_METHOD_LABELS,
        default=FEE_METHOD_SUBSCRIPTION,
        group=GROUP_OFFICE,
        note=(
            "«الاشتراك» مسودّةٌ شهرية من الاشتراك والإضافات، و«سعرٌ لكل خدمة» "
            "مجموعُ الخدمات المستحقّة في الشهر؛ و«بالساعة» غير متاحةٍ بعد."
        ),
    ),
    "fee_auto_approve": SettingDefinition(
        key="fee_auto_approve",
        label="الاعتماد التلقائي لمسودّات الأتعاب",
        kind=KIND_BOOL,
        levels=(LEVEL_OFFICE,),
        default=False,
        group=GROUP_OFFICE,
        note="مقفلٌ مطفأً في هذه المرحلة — المسودّةُ يُراها صاحبُ المكتب قبل اعتمادها.",
    ),
    # ── القيدُ التلقائيُّ في دفاتر المكتب (#284) ──
    #
    # **لا آليةَ «حدث ← حساب» في المستودع**، فأقربُ مكافئٍ هو ما تعرفه المنتجاتُ
    # المهنية: حسابٌ افتراضيٌّ لكل مسارِ مالٍ في إعدادات الشركة (Odoo: حسابٌ لكل
    # طريقة دفعٍ في اليومية؛ QuickBooks: حسابُ الصندوق/البنك في الإعدادات). فلا
    # يُنشئ المكتبُ حساباً ولا يخترع كوداً: يقرأ ما في شجرته ويكتب كودَه هنا.
    #
    # **والأكوادُ نصٌّ لا قائمةُ اختياراتٍ مخزَّنة**: الشجرةُ ملكُ الشركة وتتغيّر
    # بحفظها، وقائمةٌ في السجلّ تتجمّد عند لحظة كتابتها. الحلُّ عند الترحيل
    # (`accounting_office/office_journal.py`) بـ`get_account_by_code`، وكودٌ
    # غائبٌ أو معطَّل ⇒ 400 يُسمّي المفتاحَ والكود.
    #
    # **والإطفاءُ يمنع القيدَ والشيكَ معاً**: مكتبٌ يُمسك دفاتره خارج المنصّة
    # يُسجّل ما دُفع عليه بلا أن تُكتب له دفاترُ لا يقرؤها أحد.
    "office_journal_enabled": SettingDefinition(
        key="office_journal_enabled",
        label="ترحيل الدفعات والشطب إلى دفاتر المكتب",
        kind=KIND_BOOL,
        levels=(LEVEL_OFFICE,),
        default=True,
        group=GROUP_OFFICE,
        note=(
            "مطفأً: لا يُرحَّل قيدٌ ولا يُسجَّل شيك — والدفعةُ والشطبُ يُسجَّلان عاديًّا."
        ),
    ),
    "office_journal_cash_account": SettingDefinition(
        key="office_journal_cash_account",
        label="حساب النقد للدفعات النقدية",
        kind=KIND_TEXT,
        levels=(LEVEL_OFFICE,),
        default="1101",
        group=GROUP_OFFICE,
        note="يُدين به قيدُ دفعةٍ نقدية — كودُ الحساب في شجرة المكتب.",
    ),
    "office_journal_bank_account": SettingDefinition(
        key="office_journal_bank_account",
        label="حساب البنك للتحويلات والبطاقات",
        kind=KIND_TEXT,
        levels=(LEVEL_OFFICE,),
        default="1102",
        group=GROUP_OFFICE,
        note="يُدين به قيدُ دفعةِ تحويلٍ أو بطاقة — كودُ الحساب في شجرة المكتب.",
    ),
    "office_journal_cheque_account": SettingDefinition(
        key="office_journal_cheque_account",
        label="حساب الشيكات تحت التحصيل",
        kind=KIND_TEXT,
        levels=(LEVEL_OFFICE,),
        default=CHEQUE_UNDER_COLLECTION_CODE,
        group=GROUP_OFFICE,
        note=(
            "يُدين به قيدُ دفعةٍ بشيك — «شيكات برسم التحصيل» من الشجرة التشغيلية."
        ),
    ),
    "office_journal_receivable_account": SettingDefinition(
        key="office_journal_receivable_account",
        label="حساب ذمم زبائن المكتب",
        kind=KIND_TEXT,
        levels=(LEVEL_OFFICE,),
        default="1103",
        group=GROUP_OFFICE,
        note="يُدائن به قيدُ الدفعة والشطب، وعليه وسمُ الطرف وحده.",
    ),
    "office_journal_revenue_account": SettingDefinition(
        key="office_journal_revenue_account",
        label="حساب إيراد الأتعاب",
        kind=KIND_TEXT,
        levels=(LEVEL_OFFICE,),
        default="4102",
        group=GROUP_OFFICE,
        # **للجزء أ٢، لا يقرؤه شيءٌ اليوم**: قيدُ الفاتورة الورقية هو من يقرؤه،
        # والقيمةُ مسجَّلةٌ من الآن كي لا يصل اعتمادُها بسؤالٍ عن كودٍ لم يُقرأ.
        note=(
            "يُدائن به قيدُ فاتورة الأتعاب — للجزء أ٢، لا يقرؤه شيءٌ اليوم."
        ),
    ),
    "office_journal_writeoff_account": SettingDefinition(
        key="office_journal_writeoff_account",
        label="حساب مصروف الديون المعدومة",
        kind=KIND_TEXT,
        levels=(LEVEL_OFFICE,),
        # **الحسابُ يُنشأ عند الحاجة**: لا بذرةَ تحمله، فافتراضُ كودٍ غيرِ موجودٍ
        # كان يجعل الشطبَ يردّ 400 في كل مكتب — وهو بندٌ من التذكرة نفسها.
        # `office_journal.ensure_writeoff_account` ينشئه تحت «52» قبل أوّل قيد،
        # ولا يُنشئ حساباً لكودٍ صريحٍ كتبه المكتب (الكودُ الغريب 400 كما هو).
        default=WRITEOFF_ACCOUNT_CODE,
        group=GROUP_OFFICE,
        note=(
            "يُدين به قيدُ الشطب — يُنشأ تلقائياً تحت «52» إن غاب من الشجرة."
        ),
    ),
}

#: ما تقرؤه خطوة «أول تشغيل» — بترتيبه كما يُعرَض في الواجهة.
FIRST_RUN_KEYS: tuple[str, ...] = ("tax_system", "office_size")
