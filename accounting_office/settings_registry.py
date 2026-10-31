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

LEVEL_OFFICE = "office"
LEVEL_CLIENT = "client"
LEVEL_ITEM = "item"

SETTING_LEVELS: tuple[str, ...] = (LEVEL_OFFICE, LEVEL_CLIENT, LEVEL_ITEM)

#: مجموعات شاشة الإعدادات — ثابتٌ مستقلّ عن المستويات وإن تشارك `office` اسماً:
#: المستوى يقول «أين تُضبط القيمة»، والمجموعة تقول «أين تُعرض» — وقد تختلفان.
GROUP_OFFICE = "office"
SETTING_GROUPS: tuple[tuple[str, str], ...] = ((GROUP_OFFICE, "المكتب"),)

#: نصّ القيمة الغائبة — ثابتٌ واحدٌ في الخادم، لا نسخةٌ في كل شاشة.
NOT_CHOSEN_LABEL = "غير مختار"


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
        return value
    if definition.kind == KIND_WEEKDAYS:
        return _canonical_weekdays(value)
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
}

#: ما تقرؤه خطوة «أول تشغيل» — بترتيبه كما يُعرَض في الواجهة.
FIRST_RUN_KEYS: tuple[str, ...] = ("tax_system", "office_size")
