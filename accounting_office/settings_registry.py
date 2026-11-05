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
SETTING_GROUPS: tuple[tuple[str, str], ...] = (
    (GROUP_OFFICE, "المكتب"),
    (GROUP_SCHEDULE, "الضريبة ولائحة المواعيد"),
    (GROUP_ALERTS, "التأخير والتنبيهات"),
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
        return value
    if definition.kind == KIND_WEEKDAYS:
        return _canonical_weekdays(value)
    if definition.kind == KIND_MULTI_CHOICE:
        return _canonical_multi_choice(definition, value)
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
}

#: ما تقرؤه خطوة «أول تشغيل» — بترتيبه كما يُعرَض في الواجهة.
FIRST_RUN_KEYS: tuple[str, ...] = ("tax_system", "office_size")
