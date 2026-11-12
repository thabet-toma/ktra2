"""خدمات مكتب المحاسبة — المحلّل الواحد، ودورة حياة الزبون، والجهات.

**المحلّل هو القانون:** `resolve_setting` يقرأ بالترتيب
**تخصيص الشغلة ← تخصيص الزبون ← قيمة المكتب ← الافتراضي**، ويرفض مستوىً غير
مسموحٍ للمفتاح. ولا كود خارج هذا الملفّ يقرأ `OfficeSettingValue` أو
`ClientSettingOverride` — النسخةُ الثانية من الترتيب تفترق عن الأولى بصمت.

**والكتابة تُتحقَّق قبلها**: كل ضبطٍ يمرّ بـ`settings_registry.validate_value`
(نوعُ الإعداد ومُتحقِّقه)، فيستحيل أن يدخل الجدولَ ما لا يعرفه السجلّ.
"""
import copy
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.db.models.functions import Coalesce, ExtractYear
from django.utils import timezone

from accounting_office import deadlines, settings_registry
from accounting_office.models import (
    CADENCE_EVENT,
    CADENCE_SEMIANNUAL,
    CADENCE_SERVICE,
    CLIENT_SERVICE_FREQUENCY_CHOICES,
    CLIENT_SERVICE_STATUS_ACTIVE,
    CLIENT_SERVICE_STATUS_LABELS,
    CONDITION_ANNUAL_SALES_ABOVE,
    CONDITION_ENTITY_TYPE_IN,
    CONDITION_HAS_EMPLOYEES,
    CONDITION_IS_SELF_EMPLOYED,
    CONDITION_VAT_CLASSIFICATION_IN,
    CONSENT_CHANNEL_LABELS,
    DEADLINE_CADENCE_CHOICES,
    DEFAULT_SERVICES,
    DOCUMENT_CADENCE_ANNUAL,
    DOCUMENT_CADENCE_CHOICES,
    DOCUMENT_CADENCE_LABELS,
    DOCUMENT_CADENCE_MONTHLY,
    DOCUMENT_CARD_CONDITION_FIELDS,
    DOCUMENT_CHANNEL_CHOICES,
    DOCUMENT_CHANNEL_LABELS,
    DOCUMENT_FILE_COPY_TAG,
    DOCUMENT_STATUS_CHOICES,
    DOCUMENT_STATUS_LABELS,
    DOCUMENT_STATUS_NOT_NEEDED,
    DOCUMENT_STATUS_NOT_NEEDED_ANNUAL_LABEL,
    DOCUMENT_STATUS_PARTIAL,
    DOCUMENT_STATUS_RECEIVED,
    DOCUMENT_STATUS_REQUIRED,
    EVENT_KIND_CHOICES,
    EVENT_KIND_LABELS,
    FEE_DRAFT_STATUS_APPROVED,
    FEE_DRAFT_STATUS_CANCELLED,
    FEE_DRAFT_STATUS_DRAFT,
    FEE_DRAFT_STATUS_LABELS,
    FREQUENCY_ANNUAL,
    FREQUENCY_BIMONTHLY,
    FREQUENCY_KEYS,
    FREQUENCY_LABELS,
    FREQUENCY_MONTHLY,
    FREQUENCY_ON_DEMAND,
    FREQUENCY_QUARTERLY,
    OBLIGATION_BADGE_LABELS,
    OBLIGATION_BADGE_LATE,
    OBLIGATION_BADGE_LATE_INTERNAL,
    OBLIGATION_BADGE_MISSING_DOCS,
    OBLIGATION_BADGE_NEAR,
    OBLIGATION_CHANGE_EXTENSION,
    OBLIGATION_CHANGE_EXTENSION_CLEARED,
    OBLIGATION_CHANGE_OFFICE_OVERRIDE,
    OBLIGATION_CHANGE_PLATFORM_UPDATE,
    OBLIGATION_DIRECTION_CHOICES,
    OBLIGATION_DIRECTION_DUE,
    OBLIGATION_DIRECTION_LABELS,
    OBLIGATION_DIRECTION_REFUND,
    OBLIGATION_ORIGIN_EVENT,
    OBLIGATION_ORIGIN_LABELS,
    OBLIGATION_ORIGIN_OFFICE,
    OBLIGATION_ORIGIN_OFFICIAL,
    OBLIGATION_STATUS_LABELS,
    OBLIGATION_STATUS_NOT_REQUIRED,
    OBLIGATION_STATUS_PENDING,
    OBLIGATION_STATUS_SUBMITTED,
    OFFICE_ALERT_DEFAULT_OPENS,
    OFFICE_ALERT_KIND_BADGES,
    #: #290: تذكيرُ نسخة البيانات الشهرية — نوعُ التنبيه ومفتاحُ شهره.
    OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
    OFFICE_ALERT_KIND_FEE_DRAFT_PENDING,
    OFFICE_ALERT_KIND_LABELS,
    OFFICE_ALERT_KIND_OBLIGATION_LATE,
    OFFICE_ALERT_KIND_OPENS,
    OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED,
    OFFICE_ALERT_KIND_REMINDER_LIMIT,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
    OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
    OFFICE_ALERT_KIND_TASK_LATE_INTERNAL,
    OFFICE_CUSTOM_RULE_CADENCE_CHOICES,
    OFFICE_CUSTOM_RULE_KIND_CHOICES,
    OFFICE_RULE_OVERRIDE_FIELDS,
    REMINDER_ALERT_KINDS,
    REMINDER_APPOINTMENT,
    REMINDER_BALANCE,
    REMINDER_CHANNEL_LABELS,
    REMINDER_CHANNEL_WHATSAPP,
    REMINDER_COUNTED_KINDS,
    REMINDER_DEADLINE,
    REMINDER_DEFAULT_TEXTS,
    REMINDER_DOCUMENTS,
    #: #283/ب: نوعُ إشعار القبض — مولّدُه في `payments` ويُنادى من هنا.
    REMINDER_FEE_RECEIPT,
    REMINDER_KIND_DISMISSED,
    REMINDER_KIND_LABELS,
    REMINDER_KIND_MANUAL,
    REMINDER_KIND_SENT,
    REMINDER_KIND_UNDO,
    REMINDER_LANGUAGE_CHOICES,
    REMINDER_LANGUAGES,
    REMINDER_MANUAL_CHANNELS,
    REMINDER_PLACEHOLDERS,
    REMINDER_TIMER_KINDS,
    REMINDER_TYPE_CHOICES,
    REMINDER_TYPE_LABELS,
    REMINDER_TYPES,
    RETENTION_BASIS_LABELS,
    RETENTION_BASIS_LATER_OF_YEAR_END_OR_FILING,
    RULE_KIND_CHOICES,
    RULE_KIND_DAYS_AFTER_EVENT,
    RULE_KIND_DAY_OF_NEXT_MONTH,
    RULE_KIND_END_OF_PERIOD,
    RULE_KIND_MONTH_DAY_NEXT_YEAR,
    SERVICE_CODE_ANNUAL_ACCOUNTS,
    SERVICE_CODE_BOOKKEEPING,
    SERVICE_CODE_CONSULTING,
    SERVICE_CODE_PAYROLL,
    SERVICE_CODE_VAT,
    TAX_SYSTEM_CHOICES,
    THRESHOLD_KIND_VAT_EXEMPT_DEALER,
    THRESHOLD_KIND_VAT_MONTHLY_REPORTING,
    ClientContact,
    ClientDocumentItemChoice,
    ClientEvent,
    ClientReminderRecipient,
    ClientService,
    ClientServiceFrequency,
    ClientServicePrice,
    ClientSettingOverride,
    Contact,
    DeadlineRule,
    DeadlineSchedule,
    DocumentChecklistItem,
    DocumentFile,
    DocumentRetentionRule,
    FeeDraft,
    FeeDraftLine,
    FeeExtraService,
    FeeSubscription,
    Obligation,
    ObligationDateChange,
    OfficeAlert,
    OfficeClient,
    OfficeCustomRule,
    OfficeDocumentItem,
    OfficeDocumentItemChoice,
    OfficeHoliday,
    OfficeRefreshRun,
    OfficeRuleOverride,
    OfficeService,
    OfficeSettingValue,
    PeriodTask,
    PlatformDocumentItem,
    ReminderLog,
    ReminderPostpone,
    ReminderTemplate,
    ServicePackage,
    TaxCard,
    TaxThreshold,
    fee_draft_alert_ref,
    is_tenant_member,
    tax_card_choices,
)
from core.access import (
    MANAGER_ROLE,
    OFFICE_AMOUNTS_VIEW_KEY,
    OFFICE_CLIENTS_ALL_KEY,
    OFFICE_CLIENTS_WRITE_KEY,
    OFFICE_MANAGER_ROLE,
    office_role_keys,
    user_has_perm,
    user_tenant_role,
)
from core.activity import log_activity
from tenants.models import UserCompanyMembership

MODULE_KEY = "accounting_office"

#: الإعداد الذي يحكم اختيارات كل بطاقة — يُذكر مرةً واحدةً هنا لأن له مساراً
#: جانبيّاً: تغييره يُفرّغ ما لم يعد صالحاً في البطاقة.
TAX_SYSTEM_KEY = "tax_system"

#: أكبر مبيَعاتٍ سنوية يقبلها `DecimalField(max_digits=14, decimal_places=2)`:
#: 12 خانةً صحيحةً وخانتان عشريتان.
MAX_ANNUAL_SALES = Decimal("999999999999.99")

#: سقفُ `PositiveSmallIntegerField` — حدودُ الحقل نفسها، مكرَّرةً حيث تُنادَى
#: الخدمة مباشرةً بلا serializer.
MAX_EMPLOYEES_COUNT = 32767

#: مصادر القيمة الفعلية — تُسلَّم للواجهة كي تعرف من أين جاءت.
SOURCE_ITEM = settings_registry.LEVEL_ITEM
SOURCE_CLIENT = settings_registry.LEVEL_CLIENT
SOURCE_OFFICE = settings_registry.LEVEL_OFFICE
SOURCE_DEFAULT = "default"

#: «لا قيمة» — ثابتٌ واحدٌ في الخادم، والواجهة تقرؤه في `value_label` بدل نسخه.
NOT_CHOSEN_LABEL = settings_registry.NOT_CHOSEN_LABEL

#: قائمةُ أيامٍ فارغة مقصودة: «بلا أيام عطلة» — ليست «غير مختار».
NO_REST_DAYS_LABEL = "بلا أيام عطلة"


# ── الرؤية والمبالغ: مصدرٌ واحد لكلٍّ منهما (#272) ─────────────────────────
#
# **لا يُكتب شرطُ «زبائن هذا العضو» في نقطةٍ ثانية.** كلُّ قائمةٍ أو نقطةٍ تُرجع
# زبوناً تمرّ بـ`visible_clients`، وكلُّ مبلغٍ يمرّ بـ`can_see_amounts` و
# `mask_amounts`. نسخةٌ ثانيةٌ من الشرط تفترق عن الأولى عند أوّل تعديلٍ بصمت —
# وهي بعينها الطريقة التي تُسرَّب بها بيانات مكتبٍ إلى غيره.
#
# **استثناءٌ واحدٌ مقصود (#281): نصُّ الرسالة.** `{amount}` في نصّ «جاهز للإرسال»
# (`ready_to_send_payload` ← `messages[].body`) وفي وصفِّ سجلّ التذكير المحفوظ
# (`reminder_log_row` ← `body`) يحمل مبلغَ الفترة **ولو لعضوٍ بلا `office.amounts.view`**:
# النصُّ رسالةٌ إلى **الزبون نفسه** عن مبلغٍ عليه، وقنعُه عن الموظّف كان يُرسل «—»
# إلى الزبون بدل مبلغه. وما سوى النصّ يبقى مقنَّعاً: بنودُ `items` المهيكلة بلا
# مبلغٍ أصلاً. مبلغٌ جديدٌ في نصّ رسالةٍ يُقرَّر هنا قراراً لا يمرّ بالصمت.

#: مفاتيح المبالغ في حمولة البطاقة الضريبية. مبلغٌ جديدٌ يُضاف هنا **أولاً**،
#: وإلا سقط حارسُ `accounting_office/tests/test_amounts_guard.py`.
TAX_CARD_AMOUNT_KEYS: tuple[str, ...] = ("annual_sales",)

#: مفاتيح مبالغ الباقات — الباقة تُقترح بسعرٍ اختياريّ، وهو مبلغُ تسويقٍ لا مبلغُ
#: زبون، لكنه يُعرض لعضوٍ قد لا يملك رؤية المبالغ فيمرّ بالقناع كغيره.
PACKAGE_AMOUNT_KEYS: tuple[str, ...] = ("suggested_price",)

#: مبلغُ الالتزام (#275): ما على الزبون أو له في فترةٍ — **يُقفل عند «انقدّم»**.
#: و`computed_amount` (#287/٤) المبلغُ المحسوبُ من الدفتر: محفوظٌ إلى جانب
#: المعدَّل لا مكانه، فالسؤال «كم قال الدفتر وكم قُدّم؟» يبقى مقروءاً.
OBLIGATION_AMOUNT_KEYS: tuple[str, ...] = ("amount", "computed_amount")

#: مبالغُ بنود دفتر الزبون (#286): مدينُ البند ودائنه، **والأساسُ الخاضعُ للضريبة
#: وقيمتُها** (#288/ب-٢). تُقنَّع كسائر مبالغ الموديول — من لا يملك «يرى المبالغ»
#: لا يقرأ أرقامَ دفترٍ ولا يكتبها، والقاعدةُ نفسُها في القراءة
#: (`client_books.entry_row`) والكتابة (`create_entry`).
BOOK_ENTRY_AMOUNT_KEYS: tuple[str, ...] = (
    "debit", "credit", "tax_base", "tax_amount",
)

#: مبالغُ الأتعاب (#282): مبلغُ الاشتراك وسعرُ خدمة الزبون وسطرُ الإضافة وسطرُ
#: المسودّة ومجموعاها، **وقيمةُ ضريبة فاتورة الأتعاب** (أ٢). `total` و`subtotal`
#: مفتاحان لا واحد: المسودّةُ تحمل مجموعهما ظاهراً في القائمة، ومن لا يرى المبالغ
#: يقرأ `null` فيهما وفي كل سطرٍ تحته — والفاتورةُ كذلك في `total` و`tax_total`.
FEE_AMOUNT_KEYS: tuple[str, ...] = ("amount", "subtotal", "total", "tax_total")

#: مبالغُ الدفعات و«اللي عليه» (#283): مبلغُ الدفعة وتخصيصُها، والمتبقّي على
#: المسودّة، والمدفوعُ عليها والمشطوبُ منها، و`due`/`credit`، ومجموعا الكشف،
#: وسطرُ العلم الضريبيّ. **كلُّها مشتقّةٌ لا مخزَّنة** ومع ذلك مبالغ: تُقنَّع في
#: الحمولات كسائر مبالغ الموديول، ومفتاحٌ جديدٌ فيها يُضاف هنا **أولاً**.
PAYMENT_AMOUNT_KEYS: tuple[str, ...] = (
    "amount",
    "paid_amount",
    "written_amount",
    "remaining",
    "due",
    "credit",
    "invoices_total",
    "paid_total",
    "tax_note",
    # #283/ب: كشفُ الحساب — الرصيدُ الافتتاحيُّ والختاميُّ والجارِي، ومجموعُ
    # الحركة الصافية. أربعةُ مفاتيحِ مبلغٍ تُقنَّع كما تُقنَّع بقيّةُ المبالغ:
    # كشفٌ يقنّع صفوفَه ويُظهر رصيدَه الختامي لا يقنّع شيئاً.
    "opening_balance",
    "closing_balance",
    "balance",
    "movements",
    # #289: مجموعُ «اللي عليه» في لوحة صاحب المكتب — مجموعُ `due` نفسه لا مبلغٌ
    # ثانٍ، لكنه **مفتاحُ مبلغٍ في حمولة** فيُقنَّع كسائرها.
    "due_total",
)

#: كلُّ مفاتيح المبالغ في الموديول — يقارنها الحارس بحقول `DecimalField`
#: المعلَنة في مُسلسِلات الموديول وبمفاتيح حمولاته العشرية، فتضطرّ كلُّ تذكرةٍ
#: لاحقة فيها مبلغٌ أن تمرّ بالقناع.
AMOUNT_KEYS: frozenset[str] = frozenset(
    TAX_CARD_AMOUNT_KEYS
    + PACKAGE_AMOUNT_KEYS
    + OBLIGATION_AMOUNT_KEYS
    + BOOK_ENTRY_AMOUNT_KEYS
    + FEE_AMOUNT_KEYS
    + PAYMENT_AMOUNT_KEYS,
)


# ── الأتعاب: مفاتيحُ الإعداد وحارسا الاختيار (#282) ──────────────────────────
#
# **الطريقةُ إعدادٌ والاعتمادُ إعدادٌ مقفل** — والمفاتيحُ هنا قبل قسم التذكيرات
# لأن `LOCKED_SETTING_MESSAGES` يُبنى عند الاستيراد، فيحتاج مفتاحَه معرَّفاً.
FEE_METHOD_KEY = "fee_method"
FEE_AUTO_APPROVE_KEY = "fee_auto_approve"

# ── التشغيل والنسخ (#290): مفاتيحُ مجموعةٍ ثابتةٍ هنا لا نصوصاً في الكود ──────
#
# المفتاحان الأوّلان **مقفلان مطفأين** (`settings_registry.LOCKED_SETTING_NOTE`)
# وتذكيرُ النسخة مفتوحٌ شهريٌّ افتراضاً. وثوابتُها هنا لا في `office_exports`:
# حارسُ القفل يُبنى عند الاستيراد فيحتاج مفاتيحَه معرَّفةً قبله (كـ`fee_method`).
OPERATIONS_OFFICIAL_INVOICING_KEY = "official_invoicing"
OPERATIONS_AUTO_SEND_KEY = "auto_send"
DATA_EXPORT_REMINDER_KEY = "data_export_reminder"

#: «بالساعة» معروضةٌ في الاختيار ومرفوضةٌ برسالتها: يراها المكتب فيعرف أنها
#: ليست متاحةً بعد، ولا يظنّ الطريقةَ الوحيدةَ هي الاشتراك.
FEE_HOURLY_LOCKED = "الأتعاب بالساعة غير متاحة قبل المرحلة الثانية"
FEE_AUTO_APPROVE_LOCKED = (
    "الاعتماد التلقائي لمسودّات الأتعاب غير متاح قبل المرحلة الثانية"
)

#: قيمُ اختيارٍ معروضةٌ مرفوضةٌ بقرار — مفتاحُ الإعداد ← (القيمة, رسالتُها).
#: البابُ الواحدُ لفتحها في المرحلة الثانية هو حذفُ الصفّ من هنا؛ لا فرعٌ في
#: الـview ولا استثناءٌ لمستوى الزبون.
FORBIDDEN_SETTING_VALUES: dict[str, tuple[str, str]] = {
    FEE_METHOD_KEY: (settings_registry.FEE_METHOD_HOURLY, FEE_HOURLY_LOCKED),
}


def _assert_choice_available(key, value) -> None:
    """قيمةُ اختيارٍ مرفوضةٌ بقرار (لا بنوعها) — تُرفض برسالتها المعلَنة."""
    forbidden = FORBIDDEN_SETTING_VALUES.get(key)
    if forbidden is None:
        return
    locked_value, message = forbidden
    if value == locked_value:
        raise ValidationError({"value": message})


def visible_clients(tenant, user):
    """**مصدر الرؤية الوحيد**: كلُّ قائمةٍ أو نقطةٍ تُرجع زبوناً تمرّ من هنا.

    بلا `office.clients.all` («يرى زبائن غيره») لا تُرجع إلا زبائنَ هذا العضو
    (`responsible=user`) **والزبائن الذين حُوِّلت له شغلةٌ منهم** (`PeriodTask`
    بـ`assignee=user`)، ومعها كلُّ زبائن المكتب. والتفصيلُ المحجوب يُترجم في
    الـview إلى **404 لا 403**: 403 يثبت وجودَ الزبون، و404 لا يثبت شيئاً.

    **التوسيعُ (#275) في هذا الموضع وحده** — هو الموضعُ الذي وصفته النسخةُ
    السابقة: شغلةٌ تُحوَّل إلى موظّفٍ تُريهِ زبونَها ولو لم يكن مسؤولَه. شرطٌ
    جديدٌ في نقطةٍ ثانية كان يفترق عن هذا بصمت. و`.distinct()` لأن الزبون قد
    يطابق الشرطين معاً (مسؤولٌ عنه وله عنده شغلات) فيأتي مرّتين.
    """
    queryset = OfficeClient.objects.filter(tenant=tenant)
    if user_has_perm(user, tenant, OFFICE_CLIENTS_ALL_KEY):
        return queryset
    if user is None or not getattr(user, "is_authenticated", False):
        return queryset.none()
    assigned = PeriodTask.objects.filter(
        tenant=tenant, assignee=user,
    ).values("client_id")
    return queryset.filter(Q(responsible=user) | Q(pk__in=assigned)).distinct()


def visible_contacts(tenant, user):
    """**مصدر رؤية الجهات الوحيد**: ما يراه العضو من دفتر جهات المكتب.

    بلا `office.clients.all` تبقى له جهتان: **مربوطةٌ بزبونٍ يراه** (فهو يعمل
    عليه)، و**غيرُ مربوطةٍ بأيّ زبون** (وإلا لم يجد المنتقي جهةً جديدة فأنشأها
    مكرَّرة). وأمّا جهةٌ مربوطةٌ بزبونٍ لا يراه فاسمُها وهاتفُها ليسا له — حجبُ
    الزبون وحده كان يترك دفترَ الجهات كاملاً مفتوحاً على أسماء وهواتف.
    """
    queryset = Contact.objects.filter(tenant=tenant)
    if user_has_perm(user, tenant, OFFICE_CLIENTS_ALL_KEY):
        return queryset
    if user is None or not getattr(user, "is_authenticated", False):
        return queryset.none()
    linked_to_visible = ClientContact.objects.filter(
        client__in=visible_clients(tenant, user).values("pk"),
    ).values("contact_id")
    linked_at_all = ClientContact.objects.filter(tenant=tenant).values("contact_id")
    return queryset.filter(Q(pk__in=linked_to_visible) | ~Q(pk__in=linked_at_all))


def can_see_amounts(tenant, user) -> bool:
    """هل يملك هذا العضو «يرى المبالغ»؟ كلُّ قراءةِ مبلغٍ وكتابتِه تمرّ من هنا."""
    return user_has_perm(user, tenant, OFFICE_AMOUNTS_VIEW_KEY)


def mask_amounts(row: dict, keys=AMOUNT_KEYS) -> dict:
    """نسخةٌ من الصفّ بمفاتيح المبالغ `None` — لا حذفَ للمفتاح.

    الشكلُ يبقى ثابتاً بين من يرى ومن لا يرى: الواجهةُ تعرض «—» على `null`،
    وغيابُ المفتاح كان يجعلها تخمّن.
    """
    masked = dict(row)
    for key in keys:
        if key in masked:
            masked[key] = None
    return masked


def user_display_name(user) -> str:
    """اسمُ الموظف كما يُعرض ويُسجَّل: الاسمُ الكامل، وإلا اسم المستخدم."""
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


# ── المحلّل: القراءة الوحيدة للإعدادات ─────────────────────────────────────
def assert_client_of_tenant(tenant, client) -> None:
    """زبونٌ من شركةٍ أخرى لا يُمرَّر للمحلّل — وإلا قرأ إعداداً عابراً للشركات."""
    if tenant is None or client is None:
        raise ValidationError({"client": "الزبون والمكتب مطلوبان معاً."})
    if client.tenant_id != tenant.pk:
        raise ValidationError({"client": "هذا الزبون ليس من زبائن هذا المكتب."})


def resolve_setting_with_source(tenant, key, client=None, item=None):
    """القيمة الفعلية ومصدرها — `(None, None)` حين لا افتراضيَّ ولا قيمة.

    رفضُ المستوى **قبل** أيّ قراءة: تمرير زبون لإعدادٍ مكتبيٍّ فقط خطأُ مناداةٍ
    لا حالةٌ فارغة تُسكت عنه.
    """
    definition = settings_registry.get_definition(key)

    if item is not None:
        settings_registry.validate_level(definition, settings_registry.LEVEL_ITEM)
    if client is not None:
        assert_client_of_tenant(tenant, client)
        settings_registry.validate_level(definition, settings_registry.LEVEL_CLIENT)

    if item is not None:
        overrides = getattr(item, "setting_overrides", None) or {}
        if key in overrides:
            return settings_registry.validate_value(definition, overrides[key]), SOURCE_ITEM

    if client is not None:
        row = ClientSettingOverride.objects.filter(
            tenant=tenant, client=client, key=key,
        ).first()
        if row is not None:
            return row.value, SOURCE_CLIENT

    row = OfficeSettingValue.objects.filter(tenant=tenant, key=key).first()
    if row is not None:
        return row.value, SOURCE_OFFICE

    if definition.has_no_default:
        return None, None
    # نسخةٌ لا مرجعٌ إلى السجلّ: قاموسٌ/قائمةٌ مشتركة تُعدَّل عرضاً فتفسد كل طلب.
    return copy.deepcopy(definition.default), SOURCE_DEFAULT


def resolve_setting(tenant, key, client=None, item=None):
    """القيمة الفعلية وحدها — الواجهةُ التي يستهلكها كلُّ شيء."""
    return resolve_setting_with_source(tenant, key, client=client, item=item)[0]


def resolve_settings_for_clients(tenant, keys, clients) -> dict[int, dict]:
    """قيمُ مجموعة مفاتيح لمجموعة زبائن في **استعلامين** — لا استعلامين لكل مفتاح.

    نفسُ ترتيب المحلّل (تخصيصُ الزبون ← قيمةُ المكتب ← الافتراضي) **وبحارسين
    نفسيهما**: `validate_level` لكل مفتاح قبل أيّ قراءة (فتمريرُ إعدادٍ مكتبيٍّ
    لمجموعة زبائن خطأُ مناداةٍ لا قيمةٌ تُقرأ)، و`assert_client_of_tenant` لكل
    زبون (فمجموعةٌ فيها زبونُ مكتبٍ آخر تقرأ إعداداً عابراً). ولا مستوى الشغلة:
    الشغلةُ كائنٌ واحد يُمرَّر، لا مجموعة.

    **والقيمُ تُنسخ لكل زبون**: قائمةُ أيام العطلة الافتراضية مشتركةٌ في السجلّ،
    وقيمُ المكتب تُخزَّن JSON — فقراءةٌ بلا نسخةٍ تُعدَّل عرضاً فتفسد غيرها.
    """
    keys = list(dict.fromkeys(keys))
    definitions = {}
    for key in keys:
        definition = settings_registry.get_definition(key)
        settings_registry.validate_level(definition, settings_registry.LEVEL_CLIENT)
        definitions[key] = definition

    clients = list(clients)
    for client in clients:
        assert_client_of_tenant(tenant, client)

    client_ids = [client.pk for client in clients]
    overrides = {
        (client_id, key): copy.deepcopy(value)
        for client_id, key, value in (
            ClientSettingOverride.objects
            .filter(tenant=tenant, key__in=keys, client_id__in=client_ids)
            .values_list("client_id", "key", "value")
        )
    }
    office_values = dict(
        OfficeSettingValue.objects
        .filter(tenant=tenant, key__in=keys)
        .values_list("key", "value"),
    )
    resolved: dict[int, dict] = {}
    for client_id in client_ids:
        row = {}
        for key in keys:
            if (client_id, key) in overrides:
                row[key] = overrides[(client_id, key)]
                continue
            definition = definitions[key]
            if key in office_values:
                row[key] = copy.deepcopy(office_values[key])
            elif definition.has_no_default:
                row[key] = None
            else:
                row[key] = copy.deepcopy(definition.default)
        resolved[client_id] = row
    return resolved


def resolve_setting_for_clients(tenant, key, clients) -> dict[int, object]:
    """القيمة الفعلية لمجموعة زبائن في **استعلامين** — لا استعلامين لكل زبون.

    تُستعمل في القوائم: صفُّ القائمة يقرأ من هنا بدل نداء `resolve_setting`
    مرّتين أو ثلاثاً لكل زبون. والحارسُ والمستوياتُ في
    `resolve_settings_for_clients` التي تُقرأ لها هذه — نسخةٌ واحدة من القاعدة
    لا نسختان تفترقان عند أوّل تعديل.
    """
    return {
        client_id: row[key]
        for client_id, row in resolve_settings_for_clients(
            tenant, [key], clients,
        ).items()
    }


# ── الكتابة: تُتحقَّق بالنوع والمستوى قبل أن تلمس الجدول ────────────────────
def set_office_setting(tenant, key, value):
    definition = settings_registry.get_definition(key)
    settings_registry.validate_level(definition, settings_registry.LEVEL_OFFICE)
    clean = settings_registry.validate_value(definition, value)
    # حارسا القرار لا النوع: إعدادٌ مقفلٌ مطفأ، ونافذةُ إرسالٍ زوجٌ مرتَّب.
    _assert_locked_setting(key, clean)
    _assert_choice_available(key, clean)
    _assert_send_window(tenant, key, clean)
    with transaction.atomic():
        row, _created = OfficeSettingValue.objects.update_or_create(
            tenant=tenant, key=key, defaults={"value": clean},
        )
        _propagate_tax_system(tenant, key, _clients_without_override(tenant, key))
    return row.value


def reset_office_setting(tenant, key) -> None:
    """«ارجع للافتراضي» — حذفُ قيمة المكتب لا كتابةُ الافتراضيِّ مكانها.

    الكتابةُ مكانها تُجمِّد الافتراضيَّ عند قيمته اليوم، فمتى تغيّر في السجلّ لم
    يصل المكتب. والحذف يُعيده إلى التتبّع.

    **إعدادٌ بلا افتراضيٍّ لا يُرجَع إلى شيء**: حذفُ `tax_system` يُعيد المكتب إلى
    أول تشغيلٍ ويُبطل اختيارات كل بطاقة — فيُرفض، ويُختار غيره بدلاً منه.

    **وطرفا نافذة الإرسال** يرجع أحدهما إلى افتراضيّه فتنقلب النافذة (نهاية 23
    وبداية 20، ثم مسحُ النهاية ⇒ 20→19): يُرفض بحارس الكتابة نفسه.
    """
    definition = settings_registry.get_definition(key)
    settings_registry.validate_level(definition, settings_registry.LEVEL_OFFICE)
    if definition.has_no_default:
        raise ValidationError({
            "value": (
                f"«{definition.label}» بلا افتراضيٍّ يُرجَع إليه — "
                "اختر له قيمةً بدلاً من مسحها."
            ),
        })
    # الحذفُ يحرّك الطرف إلى افتراضيّه، فالنافذةُ الناتجة تُفحص كما تُفحص الكتابة.
    _assert_send_window(tenant, key, definition.default)
    with transaction.atomic():
        OfficeSettingValue.objects.filter(tenant=tenant, key=key).delete()
        _propagate_tax_system(tenant, key, _clients_without_override(tenant, key))


def set_client_setting(client, key, value, *, tenant=None):
    tenant = tenant if tenant is not None else client.tenant
    assert_client_of_tenant(tenant, client)
    definition = settings_registry.get_definition(key)
    settings_registry.validate_level(definition, settings_registry.LEVEL_CLIENT)
    clean = settings_registry.validate_value(definition, value)
    # و«بالساعة» مرفوضةٌ على المستويين: تخصيصُ زبونٍ لا يفتح طريقةً مقفلة.
    _assert_choice_available(key, clean)
    with transaction.atomic():
        row, _created = ClientSettingOverride.objects.update_or_create(
            tenant=tenant, client=client, key=key, defaults={"value": clean},
        )
        _propagate_tax_system(tenant, key, [client])
    return row.value


def reset_client_setting(client, key, *, tenant=None) -> None:
    """«ارجع لإعداد المكتب» — حذفُ التخصيص فيرتفع الترتيب إلى قيمة المكتب."""
    tenant = tenant if tenant is not None else client.tenant
    assert_client_of_tenant(tenant, client)
    definition = settings_registry.get_definition(key)
    # المستوى يُفحص هنا كما في `set_client_setting`: حذفُ تخصيصٍ مكتبيٍّ كذبٌ —
    # لا تخصيصَ له أصلاً، والردُّ 400 أنفع من «نجاح» لا أثر له.
    settings_registry.validate_level(definition, settings_registry.LEVEL_CLIENT)
    with transaction.atomic():
        ClientSettingOverride.objects.filter(tenant=tenant, client=client, key=key).delete()
        _propagate_tax_system(tenant, key, [client])


def clients_customized_for(tenant, key, *, user):
    """«مخصَّص عند N زبون» — القائمة نفسها، لا عدّاً منفصلاً يفترق عنها.

    تمرّ بـ`visible_clients` حين يُمرَّر عضو: قائمةُ المخصِّصين تُرجع زبائن،
    ومن لا يرى زبائنَ غيره لا يقرأ أسماءهم من هنا. و`user` **مطلوبٌ بلا افتراضي**:
    افتراضُ `None` كان يُرجع التصفية الكاملة لمن ينسى تمريره. و`user=None` صراحةً
    نداءٌ داخليٌّ بلا طلب (كل زبائن المكتب).
    """
    settings_registry.get_definition(key)
    base = (
        OfficeClient.objects.filter(tenant=tenant) if user is None
        else visible_clients(tenant, user)
    )
    return (
        base.filter(setting_overrides__key=key)
        .distinct()
        .order_by("name", "id")
    )


def clients_customized_payload(tenant, key, *, user) -> list[dict]:
    """صفوفُ قائمة المخصِّصين — تُبنى هنا لا في الـview (مصدرٌ واحد للشكل)."""
    return [
        {
            "id": client.pk,
            "name": client.name,
            "status": client.status,
            "status_label": client.get_status_display(),
        }
        for client in clients_customized_for(tenant, key, user=user)
    ]


def _customization_counts(tenant, *, user) -> dict[str, int]:
    """عددُ الزبائن المخصِّصين لكل مفتاح — **فوق الزبائن الذين يراهم العضو**.

    الرقمُ يقول شيئاً عن الزبائن، فيمرّ بالقاعدة نفسها التي تمرّ بها قائمةُ
    `settings/<key>/clients/`: عدٌّ على كل المكتب كان يخبر عضوٌ بلا
    `office.clients.all` كم زبوناً لغير يخصَّص، ويخالف القائمةَ المفلترة تحته.
    """
    queryset = ClientSettingOverride.objects.filter(tenant=tenant)
    if user is not None:
        queryset = queryset.filter(
            client__in=visible_clients(tenant, user).values("pk"),
        )
    rows = queryset.values("key").annotate(total=Count("id"))
    return {row["key"]: row["total"] for row in rows}


# ── تغييرُ النظام الضريبي يُفرّغ ما لا يصلح في البطاقة ──────────────────────
def _clients_without_override(tenant, key):
    """زبائنٌ لا تخصيصَ لهم على هذا المفتاح — يتأثّرون بقيمة المكتب وحدها."""
    return OfficeClient.objects.filter(tenant=tenant).exclude(setting_overrides__key=key)


def _clear_stale_tax_card_fields(card, tax_system) -> list[str]:
    """يُفرّغ من البطاقة ما لم يعد ضمن اختيارات النظام الجديد — ويُبقي المشترك."""
    allowed_entity = {value for value, _label in tax_card_choices(tax_system, "entity_type")}
    allowed_vat = {
        value for value, _label in tax_card_choices(tax_system, "vat_classification")
    }
    cleared = []
    if card.entity_type and card.entity_type not in allowed_entity:
        card.entity_type = ""
        cleared.append("entity_type")
    if card.vat_classification and card.vat_classification not in allowed_vat:
        card.vat_classification = ""
        cleared.append("vat_classification")
    return cleared


def _propagate_tax_system(tenant, key, clients) -> int:
    """بعد أيّ تغييرٍ لـ`tax_system`: طابِق البطاقات بنظامها الفعليّ الجديد.

    **قراءةٌ ثابتة لا تكبر بالزبائن، ثم `UPDATE` لكل بطاقةٍ تغيّرت وحدها**: نظامُ
    المجموعة من المحلّل الجماعيّ (استعلامان)، والبطاقات باستعلامٍ واحد مع زبونها
    (`select_related`) — فحفظُ البطاقة لا يقرأ زبونها من جديد في
    `_fill_tenant_from_client`. وبطاقةٌ لم يتغيّر فيها شيء لا تُكتب.
    """
    if key != TAX_SYSTEM_KEY:
        return 0
    clients = list(clients)
    if not clients:
        return 0

    systems = resolve_setting_for_clients(tenant, TAX_SYSTEM_KEY, clients)
    cards = TaxCard.objects.filter(
        client_id__in=[client.pk for client in clients],
    ).select_related("client")
    cleared = 0
    for card in cards:
        fields = _clear_stale_tax_card_fields(card, systems.get(card.client_id))
        if not fields:
            continue
        card.save(update_fields=[*fields, "updated_at"])
        cleared += 1
    return cleared


# ── حمولات الشاشات ────────────────────────────────────────────────────────
def setting_choice_label(definition, value) -> str:
    """تسميةُ قيمةِ اختيار — ومنها تسمية النظام الضريبي."""
    if value is None or value == "":
        return NOT_CHOSEN_LABEL
    return definition.labels.get(value, value)


def setting_value_label(definition, value) -> str:
    """نصُّ القيمة كما يُعرض — **مصدرٌ واحد**، والواجهة ترسمه بلا نسخةٍ منه.

    أيامُ الأسبوع من تسميات السجلّ نفسها، والنصُّ الفارغ ثابتٌ واحد
    (`NOT_CHOSEN_LABEL`)، فلو غيّر المكتبُ مصطلحاً لم يبق في الشاشات نصٌّ قديم.
    """
    if value is None or value == "":
        return NOT_CHOSEN_LABEL
    if definition.kind == settings_registry.KIND_WEEKDAYS:
        days = value if isinstance(value, (list, tuple)) else []
        labels = dict(settings_registry.WEEKDAYS)
        return "، ".join(labels.get(day, day) for day in days) or NO_REST_DAYS_LABEL
    if definition.kind == settings_registry.KIND_BOOL:
        return "نعم" if value else "لا"
    if definition.kind == settings_registry.KIND_CHOICE:
        return setting_choice_label(definition, value)
    if definition.kind == settings_registry.KIND_MULTI_CHOICE:
        keys = value if isinstance(value, (list, tuple)) else []
        labels = definition.labels
        return "، ".join(labels.get(key, key) for key in keys) or NOT_CHOSEN_LABEL
    return str(value)


def tax_system_label(value) -> str:
    """تسميةُ النظام الضريبي — من السجلّ نفسه، لا نسخةٌ في الـserializer."""
    return setting_choice_label(settings_registry.SETTINGS_REGISTRY[TAX_SYSTEM_KEY], value)


def _setting_row(definition, *, level=settings_registry.LEVEL_OFFICE) -> dict:
    return {
        "key": definition.key,
        "label": definition.label_for(level),
        "client_label": definition.client_label,
        "kind": definition.kind,
        "levels": list(definition.levels),
        "group": definition.group,
        "note": definition.note,
        "choices": definition.choice_options(),
        "has_default": not definition.has_no_default,
        "default": None if definition.has_no_default else copy.deepcopy(definition.default),
        # حدُّ الطول للنصوص (`KIND_TEXT`) — العمودُ يحكم، والضابطُ يمنع التجاوز
        # قبل الطلب، فلا يقتطع MySQL النصَّ بصمتٍ ولا يردّ الخادمُ 400 بعد كتابة.
        "max_length": definition.max_length,
        # #290: القفلُ من السجلّ لا قائمةً في الواجهة — الضابطُ يُطفأ به،
        # والحكمُ في `set_office_setting` وحده.
        "locked": definition.locked,
    }


def first_run_status(tenant) -> dict:
    """أول تشغيل: ما دام النظام أو الحجم غير مختارٍ تبقى الخطوة أمام القائمة."""
    missing = [
        key for key in settings_registry.FIRST_RUN_KEYS
        if resolve_setting(tenant, key) is None
    ]
    return {
        "first_run_required": bool(missing),
        "missing_settings": missing,
    }


def office_settings_payload(tenant, *, user) -> dict:
    """سجلّ الإعدادات بقيمة المكتب الفعليّة والافتراضيِّ وعدد المخصِّصين.

    و`user` يُمرَّر من الـview بلا افتراضي: عدّادُ المخصِّصين يُحسب على ما يراه
    العضو وحده (`_customization_counts`)، فمَن لا يرى زبائن غيره لا يقرأ عددهم.
    """
    counts = _customization_counts(tenant, user=user)
    return {
        **first_run_status(tenant),
        "groups": [
            {"id": group_id, "label": label}
            for group_id, label in settings_registry.SETTING_GROUPS
        ],
        "settings": [
            office_setting_row(tenant, key, counts=counts, user=user)
            for key in settings_registry.SETTINGS_REGISTRY
        ],
    }


def office_setting_row(tenant, key, *, counts=None, user) -> dict:
    """سطرُ إعدادٍ واحدٍ على مستوى المكتب — يستعمله العرض وردُّ الضبط والمسح."""
    definition = settings_registry.get_definition(key)
    stored = OfficeSettingValue.objects.filter(tenant=tenant, key=key).first()
    has_office_value = stored is not None
    value = (
        copy.deepcopy(stored.value) if has_office_value
        else (None if definition.has_no_default else copy.deepcopy(definition.default))
    )
    default = None if definition.has_no_default else copy.deepcopy(definition.default)
    counts = counts if counts is not None else _customization_counts(tenant, user=user)
    return {
        **_setting_row(definition),
        "value": value,
        "value_label": setting_value_label(definition, value),
        "office_value": copy.deepcopy(stored.value) if has_office_value else None,
        "has_office_value": has_office_value,
        "differs_from_default": has_office_value and value != default,
        # «ارجع للافتراضي» لمن له افتراضيٌّ فعلاً — وإلا كان الزرُّ يُعيد المكتب
        # إلى أول تشغيل. الواجهة تُخفيه بهذا العلم، والخادم يرفضه 400.
        "can_reset": has_office_value and not definition.has_no_default,
        "client_customization_count": counts.get(key, 0),
    }


def client_setting_row(client, key) -> dict:
    """سطرُ إعدادٍ واحدٍ من منظور زبون: قيمته الفعليّة، ومصدرها، وهل هي تخصيص."""
    definition = settings_registry.get_definition(key)
    value, source = resolve_setting_with_source(
        client.tenant, definition.key, client=client,
    )
    return {
        **_setting_row(definition, level=settings_registry.LEVEL_CLIENT),
        "value": value,
        "value_label": setting_value_label(definition, value),
        "source": source,
        "is_customized": source == SOURCE_CLIENT,
    }


def client_settings_payload(client) -> dict:
    """قيم الزبون الفعلية، ومن أين جاءت، وهل هي تخصيصٌ عنه.

    تُعرض الإعدادات التي **تقبل مستوى الزبون** وحدها: `office_size` إعدادٌ مكتبيٌّ
    لا معنى له في ملفّ زبون، وعرضُه بقيمةٍ موروثة يُغرِق الشاشة بما لا يُخصَّص.
    """
    return {
        "client": client.pk,
        "settings": [
            client_setting_row(client, key)
            for key, definition in settings_registry.SETTINGS_REGISTRY.items()
            if definition.allows_client_level
        ],
    }


def tax_card_payload(client, *, user) -> dict:
    """البطاقة بتسميات نظام الزبون — لا بتسميات نظامٍ آخر.

    **وتمرّ بقناع المبالغ**: عضوٌ بلا `office.amounts.view` يصله `annual_sales`
    = `None` (والواجهة تعرض «—»)، ولا يصل القناعُ إلى تسميات النظام ولا إلى
    الاختيارات. و`user` إلزاميٌّ بلا افتراضيّ: `user=None` **الصريح** وحده نداءٌ
    داخليٌّ بلا ردٍّ — لا يُقنَّع؛ ومن نسي المستخدم يسقط لا يأخذ حمولةً كاملة.
    """
    card = client.tax_card
    system = resolve_setting(client.tenant, TAX_SYSTEM_KEY, client=client)
    entity_labels = dict(tax_card_choices(system, "entity_type"))
    vat_labels = dict(tax_card_choices(system, "vat_classification"))
    payload = {
        "id": card.pk,
        "entity_type": card.entity_type,
        "entity_type_label": entity_labels.get(card.entity_type, ""),
        "vat_classification": card.vat_classification,
        "vat_classification_label": vat_labels.get(card.vat_classification, ""),
        "annual_sales": card.annual_sales,
        "has_employees": card.has_employees,
        "employees_count": card.employees_count,
        "is_self_employed": card.is_self_employed,
        "tax_system": system,
        "entity_type_choices": [
            {"value": value, "label": label}
            for value, label in tax_card_choices(system, "entity_type")
        ],
        "vat_classification_choices": [
            {"value": value, "label": label}
            for value, label in tax_card_choices(system, "vat_classification")
        ],
        "updated_at": card.updated_at,
    }
    if user is not None and not can_see_amounts(client.tenant, user):
        return mask_amounts(payload, TAX_CARD_AMOUNT_KEYS)
    return payload


# ── دورة حياة الزبون ──────────────────────────────────────────────────────
def _assert_member_of_tenant(tenant, user) -> None:
    """الموظف المسؤول عضوٌ في شركة الزبون — وإلا كان الزبون صفّاً لا يراه أحد.

    حارسُ الخدمة (400 بالسبب) وحارسُ النموذج (`OfficeClient.save`) كلاهما قائم:
    الأوّل يُخبر الـAPI، والثاني يُغلق مسار `save()`.
    """
    if not is_tenant_member(getattr(tenant, "pk", tenant), getattr(user, "pk", None)):
        raise ValidationError({"user": "هذا المستخدم ليس عضواً في شركة الزبون."})


def create_office_client(
    *, tenant, name, tax_file_number="", notes="", tax_card=None,
    actor=None, responsible=None,
) -> OfficeClient:
    """الزبون وبطاقته في كتابةٍ واحدة — بطاقةٌ بلا زبون أو زبونٌ بلا بطاقة عطل.

    **وقبل ذلك: المكتب جاهز؟** زبونٌ يُنشأ قبل اختيار النظام الضريبي وحجم المكتب
    يولد ببطاقةٍ لا اختياراتِ لها، ثم يُفتح ملفُّه على أول تشغيلٍ ناقص. فيُرفض
    الإنشاء حتى يكتمل — والقاعدة نفسها تحرس شاشة القائمة (`first_run_status`).

    **والمسؤولُ = المُنشئ افتراضاً حين يكون عضواً** (#272): زبونٌ بلا مسؤولٍ لا يراه
    عضوٌ لا يملك «يرى زبائن غيره» — يُنشئه ثم يختفي من قائمته. أمّا المُنشئ غيرُ
    العضو (سوبر أدمن، جلسة دعم) فيمرّ `require_write` ولا يُسنَد إليه شيء: يبقى
    الزبون بلا مسؤول. و`responsible` الممرَّر صراحةً يُرفض لغير العضو.
    """
    if first_run_status(tenant)["first_run_required"]:
        raise ValidationError({
            "detail": "اختر نظام مكتبك الضريبي وحجمه أولاً — من إعدادات المكتب.",
        })
    if not (name or "").strip():
        raise ValidationError({"name": "اسم الزبون مطلوب."})
    if responsible is not None:
        _assert_member_of_tenant(tenant, responsible)
        assigned = responsible
    elif actor is not None and is_tenant_member(tenant.pk, actor.pk):
        assigned = actor
    else:
        assigned = None
    card_fields = _clean_tax_card_fields(tenant, None, tax_card or {})
    with transaction.atomic():
        client = OfficeClient.objects.create(
            tenant=tenant,
            name=name.strip(),
            tax_file_number=(tax_file_number or "").strip(),
            notes=notes or "",
            responsible=assigned,
        )
        TaxCard.objects.create(client=client, **card_fields)
    return client


def assert_office_assignee(tenant, user) -> None:
    """الموظفُ الجديد في التحويل: **عضوٌ في الشركة وله دورُ مكتب**.

    العضويّةُ وحدها لا تكفي (#289): زبونٌ يُحوَّل إلى موظّفٍ لا يفتح الموديول
    يصير صفّاً لا يراه أحد — ولا يظهر في جدول اللوحة، فيُنسى بلا أثر. و«دورُ
    مكتب» يُشتقّ من `core.access` (`office_role_keys`) لا قائمةً ثانيةً هنا.

    والرسالةُ بمفتاح `responsible` — اسمُ الحقل الذي يُرسله الـAPI.
    """
    _assert_member_of_tenant(tenant, user)
    if user_tenant_role(user, tenant) not in office_role_keys():
        raise ValidationError({
            "responsible": (
                "هذا المستخدم ليس عضواً بدور مكتبٍ في الشركة — "
                "لا يُحوَّل إليه زبونٌ لا يراه."
            ),
        })


def assign_office_client(client, *, user, actor=None, request=None) -> OfficeClient:
    """تحويلُ الزبون لموظّفٍ آخر — **فعلٌ يُسجَّل** (من ← إلى) لا كتابةٌ صامتة.

    ويُسجَّل الحدثُ في المعاملة نفسها: مسؤولٌ تبدّل بلا أثرٍ في السجلّ يجعل «من
    كان مسؤولاً عنه في آذار؟» سؤالاً بلا جواب.

    **والصفُّ يُقرأ تحت قفلٍ داخل المعاملة**: تحويلان متزامنان على نسخةٍ قديمة
    كانا يُسجّلان «من» مسؤولاً لم يعد مسؤولاً — والسجلُّ يكذب. فالمقروءُ هو ما
    سُيَكتب فوقه فعلاً.
    """
    _assert_member_of_tenant(client.tenant, user)
    with transaction.atomic():
        locked = OfficeClient.objects.select_for_update().get(pk=client.pk)
        previous = locked.responsible
        if previous is not None and previous.pk == user.pk:
            return locked
        locked.responsible = user
        locked.save(update_fields=["responsible", "updated_at"])
        log_activity(
            action="update",
            entity_type="office_client",
            entity_id=locked.pk,
            entity_label=locked.name,
            description=(
                f"تحويل زبون المكتب «{locked.name}» من «{user_display_name(previous)}» "
                f"إلى «{user_display_name(user)}»"
            ),
            metadata={
                "from": None if previous is None else previous.pk,
                "to": user.pk,
                "from_label": user_display_name(previous),
                "to_label": user_display_name(user),
            },
            request=request,
            tenant=locked.tenant,
            user=actor,
        )
    return locked


def update_office_client(
    client, *, name=None, tax_file_number=None, notes=None, tax_card=None,
) -> OfficeClient:
    """تعديلُ الزبون وبطاقته في **معاملةٍ واحدة**: لا اسمٌ يُحفظ واختيارٌ مرفوض.

    كان الـview يحفظ الاسم أوّلاً ثم يكتب البطاقة؛ فبطاقةٌ بتصنيفٍ غير صالحٍ تُبقي
    الاسمَ الجديد محفوظاً رغم ردّ 400 — نصفُ تعديلٍ يُخالف ما قاله الخادم.
    """
    changed = []
    if name is not None:
        if not name.strip():
            raise ValidationError({"name": "اسم الزبون مطلوب."})
        client.name = name.strip()
        changed.append("name")
    if tax_file_number is not None:
        client.tax_file_number = tax_file_number.strip()
        changed.append("tax_file_number")
    if notes is not None:
        client.notes = notes
        changed.append("notes")

    with transaction.atomic():
        if changed:
            client.save(update_fields=[*changed, "updated_at"])
        if tax_card:
            update_tax_card(client, **tax_card)
    return client


def _log_client_status(client, *, description, metadata, actor, request) -> None:
    """الإنهاء والإعادة حدثان في السجلّ — لا حالةٌ تتبدّل بلا أثر.

    `ended_on` يُمسح من الصفّ عند الإعادة، والتاريخُ يبقى هنا: السجلُّ لا يُمحى،
    وسطرُ النشاط يقول «متى توقّف» ولو صار نشطاً.
    """
    log_activity(
        action="update",
        entity_type="office_client",
        entity_id=client.pk,
        entity_label=client.name,
        description=description,
        metadata=metadata,
        request=request,
        tenant=client.tenant,
        user=actor,
    )


def end_office_client(client, *, on=None, actor=None, request=None) -> OfficeClient:
    """«أنهِ» — كلُّ شيءٍ يبقى: البطاقة والجهات والملاحظات، ويُضاف تاريخ الوقوع."""
    if client.status == OfficeClient.STATUS_ENDED and client.ended_on is not None:
        return client
    client.status = OfficeClient.STATUS_ENDED
    client.ended_on = on or timezone.localdate()
    with transaction.atomic():
        client.save(update_fields=["status", "ended_on", "updated_at"])
        _log_client_status(
            client,
            description="إنهاء زبون مكتب",
            metadata={"ended_on": client.ended_on.isoformat()},
            actor=actor,
            request=request,
        )
    return client


def reactivate_office_client(client, *, actor=None, request=None) -> OfficeClient:
    """«أعِد نشطاً» — يمسح تاريخ الإنهاء ويُبقي كل ما عداه، والحدثُ في السجلّ."""
    previous_end = client.ended_on
    client.status = OfficeClient.STATUS_ACTIVE
    client.ended_on = None
    with transaction.atomic():
        client.save(update_fields=["status", "ended_on", "updated_at"])
        _log_client_status(
            client,
            description="إعادة زبون مكتب نشطاً",
            metadata={"ended_on": previous_end.isoformat() if previous_end else None},
            actor=actor,
            request=request,
        )
    return client


def mark_client_delivered(
    client, *, on=None, actor=None, request=None,
) -> OfficeClient:
    """«تم التسليم» — تاريخٌ يُكتب بفعلٍ صريح، وإعدادُ الحجب يمنعه ما دام رصيد.

    **والحارسُ هنا لا في الـview**: كلُّ نداءٍ برمجيّ يمرّ به، والـview يترجمه
    400 مسمّى. والرفضُ **لا يكتب تاريخاً**: صفٌّ يبقى `delivered_on = None`، ويُرفع
    الحجبُ بالدفع الكامل لأن شرطَه `client_due.due > 0` من الدالّة الواحدة.

    **والتسليمُ حدثٌ في السجلّ**: `delivered_on` يقول متى، وسطرُ النشاط يقول مَن
    (كما الإنهاءُ والإعادة) — فلا حالةَ تتبدّل بلا أثر.
    """
    if client.delivered_on is not None:
        return client
    day = on or timezone.localdate()
    if resolve_setting(client.tenant, DELIVERY_HOLD_UNPAID_KEY):
        due = _payments_module().client_due(client.tenant, client)
        if due.due > 0:
            raise ValidationError({"delivered": DELIVERY_HOLD_MESSAGE})
    with transaction.atomic():
        client.delivered_on = day
        client.save(update_fields=["delivered_on", "updated_at"])
        _log_client_status(
            client,
            description="تعليم زبون مكتب «تم التسليم»",
            metadata={"delivered_on": client.delivered_on.isoformat()},
            actor=actor,
            request=request,
        )
    return client


# ── البطاقة الضريبية ─────────────────────────────────────────────────────
_TAX_CARD_FIELDS = (
    "entity_type", "vat_classification", "annual_sales",
    "has_employees", "employees_count", "is_self_employed",
)


def _clean_annual_sales(value) -> Decimal:
    """مبلغٌ صالحٌ لحقل `DecimalField(max_digits=14, decimal_places=2)` أو رفض.

    الفحصُ هنا لا في الـserializer وحده: الخدمة تُنادَى مباشرةً من الاختبارات ومن
    مساراتٍ أخرى، وسكربتٌ يُمرّر نصّاً أو سالباً أو كسراً بخاناتٍ ثلاث يجب أن
    يأخذ 400 واضحاً لا `InvalidOperation` من قاعدة البيانات (500).
    """
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"annual_sales": "المبيعات السنوية يجب أن تكون رقماً."}) from None
    if not amount.is_finite():
        raise ValidationError({"annual_sales": "المبيعات السنوية يجب أن تكون رقماً."})
    if amount < 0:
        raise ValidationError({"annual_sales": "المبيعات السنوية لا تكون سالبة."})
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError({
            "annual_sales": "المبيعات السنوية بخانتين عشريتين على الأكثر.",
        })
    if amount > MAX_ANNUAL_SALES:
        raise ValidationError({
            "annual_sales": "المبيعات السنوية تتجاوز 12 خانةً صحيحة.",
        })
    return amount


def _clean_tax_card_fields(tenant, client, payload) -> dict:
    """يتحقّق من اختيارات البطاقة على **نظام الزبون** لا على الاتّحاد كلّه."""
    if not payload:
        return {}
    system = (
        resolve_setting(tenant, TAX_SYSTEM_KEY, client=client) if client is not None
        else resolve_setting(tenant, TAX_SYSTEM_KEY)
    )
    unknown = set(payload) - set(_TAX_CARD_FIELDS)
    if unknown:
        raise ValidationError({"tax_card": f"حقول غير معروفة: {sorted(unknown)}"})

    clean = {}
    for field in ("entity_type", "vat_classification"):
        if field not in payload:
            continue
        value = payload[field]
        allowed = {key for key, _label in tax_card_choices(system, field)}
        if value not in ("", None) and value not in allowed:
            raise ValidationError({
                field: f"«{value}» ليس من اختيارات النظام الضريبي الحاليّ.",
            })
        clean[field] = value or ""
    if "annual_sales" in payload:
        clean["annual_sales"] = _clean_annual_sales(payload["annual_sales"])
    if "has_employees" in payload:
        clean["has_employees"] = bool(payload["has_employees"])
    if "employees_count" in payload:
        count = payload["employees_count"]
        # السقفُ من الحقل نفسه (`PositiveSmallIntegerField` = 0..32767): خدمةٌ
        # تُنادَى مباشرةً لا تمرّ بـ`serializer`، فتجاوزُه كان `DataError` من
        # القاعدة (500) بدل 400.
        if (
            not isinstance(count, int) or isinstance(count, bool)
            or count < 0 or count > MAX_EMPLOYEES_COUNT
        ):
            raise ValidationError({
                "employees_count": (
                    f"عدد العاملين عددٌ صحيح بين 0 و{MAX_EMPLOYEES_COUNT}."
                ),
            })
        clean["employees_count"] = count
    if "is_self_employed" in payload:
        clean["is_self_employed"] = bool(payload["is_self_employed"])
    return clean


def update_tax_card(client, **payload) -> TaxCard:
    clean = _clean_tax_card_fields(client.tenant, client, payload)
    card = client.tax_card
    for field, value in clean.items():
        setattr(card, field, value)
    if clean:
        card.save(update_fields=[*clean, "updated_at"])
    return card


# ── الجهات وربطها ─────────────────────────────────────────────────────────
def _contact_of_tenant(tenant, contact) -> Contact:
    if contact.tenant_id != tenant.pk:
        raise ValidationError({"contact": "هذه الجهة ليست من جهات هذا المكتب."})
    return contact


def _link_of(client, contact) -> ClientContact | None:
    return ClientContact.objects.filter(client=client, contact=contact).first()


def link_client_contact(*, client, contact, is_primary=False) -> ClientContact:
    """ربطٌ — و«رئيسية» تُنزّل الرئيسيةَ السابقة في المعاملة نفسها."""
    _contact_of_tenant(client.tenant, contact)
    if _link_of(client, contact) is not None:
        raise ValidationError({"contact": "هذه الجهة مربوطةٌ بهذا الزبون أصلاً."})
    with transaction.atomic():
        if is_primary:
            ClientContact.objects.filter(client=client, is_primary=True).update(
                is_primary=False,
            )
        return ClientContact.objects.create(
            tenant=client.tenant, client=client, contact=contact, is_primary=is_primary,
        )


def unlink_client_contact(*, client, contact) -> None:
    ClientContact.objects.filter(client=client, contact=contact).delete()


def set_primary_client_contact(*, client, contact) -> ClientContact:
    link = _link_of(client, contact)
    if link is None:
        raise ValidationError({"contact": "هذه الجهة غير مربوطةٍ بهذا الزبون."})
    with transaction.atomic():
        ClientContact.objects.filter(client=client, is_primary=True).exclude(
            pk=link.pk,
        ).update(is_primary=False)
        if not link.is_primary:
            link.is_primary = True
            link.save(update_fields=["is_primary"])
    return link


def delete_contact(contact) -> None:
    """حذفُ شخصٍ من دفتر المكتب — لا يُحذف وهو مربوطٌ بزبون.

    الرابطُ يحمل `is_primary` ومستلِمَ التذكيرات؛ حذفُه تحت الزبون يقطع صامتاً
    «من نكلّمه». فيُطلب فكُّ الربط أولاً صراحةً، والقاعدة هنا لا في الشاشة.
    """
    if ClientContact.objects.filter(contact=contact).exists():
        raise ValidationError({
            "detail": "هذه الجهة مربوطةٌ بزبون — افكّ ربطها من الزبائن أولاً.",
        })
    contact.delete()


# ── مستلِم كل نوع تذكير ───────────────────────────────────────────────────
def set_reminder_recipient(*, client, reminder_type, contact):
    """تعيينُ مستلِم نوعٍ — و`contact=None` يُعيده إلى الرئيسية."""
    if reminder_type not in ClientReminderRecipient.REMINDER_TYPES:
        raise ValidationError({"reminder_type": "نوع تذكير غير معروف."})
    if contact is None:
        ClientReminderRecipient.objects.filter(
            client=client, reminder_type=reminder_type,
        ).delete()
        return None

    _contact_of_tenant(client.tenant, contact)
    link = _link_of(client, contact)
    if link is None:
        raise ValidationError({"contact": "لا يُعيَّن مستلِماً إلا جهةٌ مربوطةٌ بالزبون."})
    row, _created = ClientReminderRecipient.objects.update_or_create(
        client=client, reminder_type=reminder_type,
        defaults={"client_contact": link, "tenant": client.tenant},
    )
    return row


def resolve_reminder_recipient(client, reminder_type) -> ClientContact | None:
    """**الدالة الوحيدة** التي تعطي المستلِم الفعلي: التعيين، وإلا الرئيسية."""
    if reminder_type not in ClientReminderRecipient.REMINDER_TYPES:
        raise ValidationError({"reminder_type": "نوع تذكير غير معروف."})
    assigned = (
        ClientReminderRecipient.objects
        .filter(client=client, reminder_type=reminder_type)
        .select_related("client_contact__contact")
        .first()
    )
    if assigned is not None:
        return assigned.client_contact
    return (
        ClientContact.objects
        .filter(client=client, is_primary=True)
        .select_related("contact")
        .first()
    )


def reminder_recipients_payload(client) -> list[dict]:
    """الأنواع الأربعة ومستلِموها في **استعلامين**: تعييناتٌ ثم رئيسية واحدة.

    كان استعلامين لكل نوع (ثمانيةٌ لأربعة أنواع) في قائمةٍ تُفتح مع كل ملفّ زبون.
    """
    assigned = {
        row.reminder_type: row.client_contact
        for row in (
            ClientReminderRecipient.objects
            .filter(client=client)
            .select_related("client_contact__contact")
        )
    }
    primary = (
        ClientContact.objects
        .filter(client=client, is_primary=True)
        .select_related("contact")
        .first()
    )

    rows = []
    for reminder_type, label in ClientReminderRecipient.REMINDER_TYPE_CHOICES:
        link = assigned.get(reminder_type) or primary
        rows.append({
            "reminder_type": reminder_type,
            "label": label,
            "is_fallback": reminder_type not in assigned,
            "recipient": (
                None if link is None else {
                    "contact_id": link.contact_id,
                    "name": link.contact.name,
                    "phone": link.contact.phone,
                    "language": link.contact.language,
                }
            ),
        })
    return rows


# ── كتالوج خدمات المكتب (#273) ───────────────────────────────────────────────
#
# الخمسةُ الافتراضية تُزرع بدالّةٍ لا بهجرة بياناتٍ لكل شركة: الهجرةُ تُنشئ صفوفاً
# للمكاتب الموجودة، وكلُّ مكتبٍ يُنشأ بعدها يحتاج زرعاً — فالدالّةُ وحدها تكفي
# الاثنين، لأنها idempotent بفرادة `(tenant, code)`.
def ensure_default_services(tenant) -> list[OfficeService]:
    """يزرع الخدمات الخمس الافتراضية للمكتب — **idempotent** (مرّتان = خمسٌ).

    تُنادى من قائمة الكتالوج ومن كل قراءةٍ تحتاج كود خدمة، فلا يبدأ مكتبٌ جديدٌ
    بكتالوجٍ فارغ، ولا يضاعف الصفوفَ نداءٌ ثانٍ. ولا يمسّ المكتبُ ما زرعه: يغيّر
    الاسمَ ويعطّل — والكودُ يبقى.
    """
    existing = set(
        OfficeService.objects.filter(tenant=tenant).values_list("code", flat=True),
    )
    with transaction.atomic():
        for position, (code, name) in enumerate(DEFAULT_SERVICES):
            if code in existing:
                continue
            OfficeService.objects.get_or_create(
                tenant=tenant,
                code=code,
                defaults={"name": name, "is_builtin": True, "position": position},
            )
    return list(OfficeService.objects.filter(tenant=tenant))


def office_service_row(service) -> dict:
    """سطرُ خدمةٍ كما يراه المنتقي والشاشة — الكودُ فيه لأنه عقدُ الاقتراح."""
    return {
        "id": service.pk,
        "code": service.code,
        "name": service.name,
        "is_active": service.is_active,
        "is_builtin": service.is_builtin,
        "position": service.position,
    }


def services_catalog_payload(tenant) -> list[dict]:
    """كتالوج المكتب — الخمسةُ الافتراضية تُزرع عند أول قراءةٍ لهذه الشاشة."""
    return [
        office_service_row(row) for row in ensure_default_services(tenant)
    ]


#: رسائلُ «ليس من كتالوج المكتب» و«باقةٌ غير موجودة» — **موضعٌ واحد** لكلٍّ منهما،
#: تناديه الخدمةُ والـviews معاً، فلا تفترق صياغتان لنفس الرفض.
SERVICE_NOT_IN_CATALOG = "خدمةٌ ليست من كتالوج هذا المكتب."
_PACKAGE_NOT_FOUND = "باقةٌ غير موجودةٍ في هذا المكتب."


def service_by_code(tenant, code) -> OfficeService:
    """خدمةٌ بكودها — والزرعُ أوّلاً كي يعمل الاقتراحُ على مكتبٍ جديد."""
    ensure_default_services(tenant)
    service = OfficeService.objects.filter(
        tenant=tenant, code=(code or "").strip(),
    ).first()
    if service is None:
        raise ValidationError({"service": "خدمةٌ غير معروفةٍ في كتالوج هذا المكتب."})
    return service


def service_or_raise(tenant, pk) -> OfficeService:
    """خدمةُ كتالوج المكتب بمعرّفها — والـviews تناديها بدل استعلامٍ ثانٍ برسالته."""
    service = OfficeService.objects.filter(tenant=tenant, pk=pk).first()
    if service is None:
        raise ValidationError({"service": SERVICE_NOT_IN_CATALOG})
    return service


def package_or_raise(tenant, pk) -> ServicePackage:
    """باقةُ المكتب بمعرّفها — ورسالةُ الرفض في `_PACKAGE_NOT_FOUND` وحدها."""
    package = ServicePackage.objects.filter(tenant=tenant, pk=pk).first()
    if package is None:
        raise ValidationError({"package": _PACKAGE_NOT_FOUND})
    return package


def _assert_service_of_tenant(tenant, service) -> None:
    if service is None or service.tenant_id != getattr(tenant, "pk", tenant):
        raise ValidationError({"service": SERVICE_NOT_IN_CATALOG})


def _generated_service_code(tenant) -> str:
    """كودٌ مولَّدٌ لخدمةٍ أضافها المكتب — `custom-<8 hex>`، والفرادةُ للقاعدة."""
    for _attempt in range(5):
        code = f"custom-{uuid4().hex[:8]}"
        if not OfficeService.objects.filter(tenant=tenant, code=code).exists():
            return code
    raise ValidationError({"name": "تعذّر توليد كودٍ للخدمة — أعد المحاولة."})


def create_office_service(tenant, *, name, position=None) -> OfficeService:
    """خدمةٌ يضيفها المكتب: `is_builtin=False` وكودٌ مولَّد لا يُكتب باليد."""
    clean = (name or "").strip()
    if not clean:
        raise ValidationError({"name": "اسم الخدمة مطلوب."})
    ensure_default_services(tenant)
    with transaction.atomic():
        if position is None:
            top = OfficeService.objects.filter(tenant=tenant).aggregate(
                top=Max("position"),
            )["top"]
            position = (top or 0) + 1
        return OfficeService.objects.create(
            tenant=tenant,
            code=_generated_service_code(tenant),
            name=clean,
            is_builtin=False,
            position=position,
        )


def update_office_service(service, *, name=None, is_active=None, position=None) -> OfficeService:
    """تعديلُ تسمية الخدمة وتفعيلها وترتيبها — **لا كودَ ولا `is_builtin`**.

    الكودُ عقدٌ يقرؤه الاقتراح، وتغييرُه كان يقلب خدمةً مضافةً إلى «مسك دفاتر»
    أو العكس بكتابةِ كلمةٍ في الشاشة.
    """
    changed = []
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValidationError({"name": "اسم الخدمة مطلوب."})
        service.name = clean
        changed.append("name")
    if is_active is not None:
        service.is_active = bool(is_active)
        changed.append("is_active")
    if position is not None:
        service.position = position
        changed.append("position")
    if changed:
        service.save(update_fields=[*changed, "updated_at"])
    return service


# ── الباقات الجاهزة (#273) ──────────────────────────────────────────────────
#: «لم يُرسَل» — تُميَّز به الكتابةُ الفارغةُ عن `None` الذي يمسح السعر المقترح.
_UNSET = object()


def _clean_suggested_price(value):
    """سعرُ الباقة: فارغٌ ⇒ `None` (لا سعرَ مقترحاً)، وسالبٌ ⇒ رفض."""
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"suggested_price": "سعرٌ غير صالح."}) from None
    if amount < 0:
        raise ValidationError({"suggested_price": "السعر المقترح لا يكون سالباً."})
    return amount


def _services_of_ids(tenant, service_ids) -> list[OfficeService]:
    """خدماتُ باقةٍ من معرّفاتها — **كلُّ معرّفٍ يُتحقَّق أنه من كتالوج المكتب**."""
    ids = list(dict.fromkeys(service_ids or []))
    services = list(OfficeService.objects.filter(tenant=tenant, pk__in=ids))
    if len(services) != len(ids):
        raise ValidationError({"services": SERVICE_NOT_IN_CATALOG})
    return services


def _package_row(package, *, masked: bool) -> dict:
    """سطرُ باقةٍ وقرارُ القناع **مُمرَّرٌ جاهزاً** — لا يُحسب لكل صفّ.

    `package.tenant` لا يُلمس هنا: قراءتُه كانت استعلاماً لكل باقة، و
    `can_see_amounts` ثلاثةَ استعلاماتٍ لكل صفّ. القرارُ يُحسب مرّةً في
    `packages_payload`.
    """
    price = None if package.suggested_price is None else f"{package.suggested_price:.2f}"
    row = {
        "id": package.pk,
        "name": package.name,
        "suggested_price": price,
        "services": [office_service_row(item) for item in package.services.all()],
        "created_at": package.created_at,
        "updated_at": package.updated_at,
    }
    return mask_amounts(row, PACKAGE_AMOUNT_KEYS) if masked else row


def package_payload(package, *, user) -> dict:
    """سطرُ باقة — **بتمرير القناع**: `suggested_price` مبلغٌ ولو لم يكن مبلغَ زبون.

    والمبلغُ يُرسَل **نصّاً** كـ`annual_sales` (ردّ الـserializer العشريّ): واجهةٌ
    تقرأ `'1750.00'` لا `1750.0` العائم.
    """
    masked = user is not None and not can_see_amounts(package.tenant, user)
    return _package_row(package, masked=masked)


def packages_payload(tenant, *, user) -> list[dict]:
    """قائمةُ الباقات — **قرارُ القناع مرّةً واحدة**، لا `can_see_amounts` لكل صفّ.

    وكانت `package_payload` تُنادى لكل باقة فتحسب `package.tenant` و
    `can_see_amounts` (استعلاماتِ صلاحياتٍ ثلاثة) لكل صفّ: صفحةٌ بعشر باقات =
    ثلاثون استعلاماً لا واحد.
    """
    masked = user is not None and not can_see_amounts(tenant, user)
    rows = ServicePackage.objects.filter(tenant=tenant).prefetch_related("services")
    return [_package_row(row, masked=masked) for row in rows]


def create_service_package(tenant, *, name, suggested_price=None, service_ids=None) -> ServicePackage:
    clean = (name or "").strip()
    if not clean:
        raise ValidationError({"name": "اسم الباقة مطلوب."})
    services = _services_of_ids(tenant, service_ids)
    with transaction.atomic():
        package = ServicePackage.objects.create(
            tenant=tenant,
            name=clean,
            suggested_price=_clean_suggested_price(suggested_price),
        )
        package.services.set(services)
    return package


def update_service_package(
    package, *, name=None, suggested_price=_UNSET, service_ids=None,
) -> ServicePackage:
    """تعديلُ الباقة — **لا يمسّ خدمةَ زبونٍ واحد**: التطبيقُ نسخٌ لا ربط."""
    changed = []
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValidationError({"name": "اسم الباقة مطلوب."})
        package.name = clean
        changed.append("name")
    if suggested_price is not _UNSET:
        package.suggested_price = _clean_suggested_price(suggested_price)
        changed.append("suggested_price")
    services = None if service_ids is None else _services_of_ids(package.tenant, service_ids)
    with transaction.atomic():
        if changed:
            package.save(update_fields=[*changed, "updated_at"])
        if services is not None:
            package.services.set(services)
    return package


def delete_service_package(package) -> None:
    """الحذفُ مباحٌ **للباقة وحدها**: قالبٌ لا تاريخَ لزبونٍ فيه."""
    package.delete()


# ── خدمات الزبون: الإضافة والدورية والإيقاف (#273) ─────────────────────────
#: #279/D4: دوريةُ خدمة الرواتب **شهريةٌ أو كل شهرين** — «دورية 102 حسب ملفه»
#: (#264): ملفٌّ شهريٌّ يُقدّم شهرياً، وملفٌّ كلَّ شهرين يُقدّمهما معاً.
PAYROLL_FREQUENCY_ERROR = "دوريةُ الرواتب شهريةٌ أو كل شهرين."
PAYROLL_FREQUENCIES: frozenset[str] = frozenset({FREQUENCY_MONTHLY, FREQUENCY_BIMONTHLY})


def _assert_payroll_frequency(service_code, frequency) -> None:
    """**النقطةُ الوحيدة** التي تحكم دوريةَ الرواتب — يقرؤها مسارا الكتابة.

    الإضافةُ (`_insert_client_service`) وتغييرُ الدورية المؤرَّخة
    (`change_client_service_frequency`) يكتبان صفوفَ الدورية، فلو كُتب الشرطُ في
    أحدهما وحده لمرّت «رُبعيةٌ» من الباب الآخر. ولا حدَّ على خدمةٍ غير الرواتب.
    """
    if service_code == SERVICE_CODE_PAYROLL and frequency not in PAYROLL_FREQUENCIES:
        raise ValidationError({"frequency": PAYROLL_FREQUENCY_ERROR})


def frequency_on(client_service, day, *, rows=None):
    """**القاعدةُ الوحيدة**: الدوريةُ في يومٍ ما = الصفُّ ذو أكبر `effective_from <= day`.

    `rows` تُمرَّر حين تكون الدورياتُ محمَّلةً سلفاً (قائمةُ خدمات الزبون) فلا
    استعلامَ لكل خدمة — والقاعدةُ هي هي، لا نسخةٌ ثانية لها في القائمة.
    """
    if rows is None:
        return (
            client_service.frequencies
            .filter(effective_from__lte=day)
            .order_by("-effective_from", "-id")
            .first()
        )
    eligible = [row for row in rows if row.effective_from <= day]
    return max(eligible, key=lambda row: (row.effective_from, row.pk), default=None)


def frequency_label(value) -> str:
    """تسميةُ الدورية من ثابت النموذج — الواجهة ترسمها ولا تعرف جدولاً محلياً."""
    return FREQUENCY_LABELS.get(value or "", "")


def frequency_choices() -> list[dict]:
    return [
        {"value": value, "label": label}
        for value, label in CLIENT_SERVICE_FREQUENCY_CHOICES
    ]


def _first_of_month(day):
    return day.replace(day=1)


def _frequency_row_payload(item) -> dict:
    return {
        "id": item.pk,
        "frequency": item.frequency,
        "frequency_label": frequency_label(item.frequency),
        "effective_from": item.effective_from.isoformat(),
        "suggested": item.suggested or None,
        "created_by_name": user_display_name(item.created_by),
        "created_at": item.created_at,
    }


def client_service_row(row, *, today, frequencies) -> dict:
    """سطرُ خدمة زبون: تواريخُها وحالتُها ودوريتُها **اليوم** وتاريخُ دورياتها.

    الحالةُ `status_on(today)` لا «هل لها `ends_on`»: إيقافٌ بتاريخٍ مستقبليّ
    يبقى نشطاً اليوم، و`is_active` في الحمولة تتبع الحالةَ لا وجودَ التاريخ.
    """
    current = frequency_on(row, today, rows=frequencies)
    status = row.status_on(today)
    return {
        "id": row.pk,
        "service": office_service_row(row.service),
        "starts_on": row.starts_on.isoformat(),
        "ends_on": None if row.ends_on is None else row.ends_on.isoformat(),
        "responsible_from": row.responsible_from.isoformat(),
        "last_period_ours": row.last_period_ours,
        "is_active": status == CLIENT_SERVICE_STATUS_ACTIVE,
        "status": status,
        "status_label": CLIENT_SERVICE_STATUS_LABELS[status],
        "frequency": None if current is None else current.frequency,
        "frequency_label": frequency_label(None if current is None else current.frequency),
        "frequency_from": None if current is None else current.effective_from.isoformat(),
        "frequencies": [_frequency_row_payload(item) for item in frequencies],
    }


def client_services_payload(client, *, user, today=None) -> dict:
    """تبويب «الخدمات»: النشطُ والموقوف، والدوريةُ الحالية وتاريخُ الدوريات.

    `user` **مفتاحيٌّ إلزامي** كسائر دوالّ الحمولة (#272) ولو لم تكن فيها مبالغُ
    اليوم — فنسخةٌ ثانية من التوقيع تفترق عند أول مبلغٍ يُضاف إليها. والمبالغُ
    تبقى في البطاقة والباقات.
    """
    today = today or timezone.localdate()
    rows = (
        client.services
        .select_related("service")
        .prefetch_related("frequencies__created_by")
        .order_by("starts_on", "id")
    )
    return {
        "client": client.pk,
        "today": today.isoformat(),
        "services": [
            client_service_row(
                row, today=today, frequencies=list(row.frequencies.all()),
            )
            for row in rows
        ],
        "frequency_choices": frequency_choices(),
    }


def overlapping_client_service(client, service, starts_on):
    """**قاعدةُ التداخل الوحيدة**: الصفُّ الذي يمنع بدايةً جديدةً لـ(زبون، خدمة).

    يمنع إن كان الصفُّ بلا نهاية (`ends_on is null`) أو امتدّ إلى البداية الجديدة
    أو بعدها (`ends_on >= starts_on`). فالإيقافُ بتاريخٍ مستقبليّ **لا يفتح** الباب
    لفترةٍ متداخلة — كان `ends_on__isnull=True` يفعلها ويصنع تقريرين لشهرٍ واحد.

    ترجع الصفّ المتداخل أو `None`؛ و`add_client_service` يرفض به و
    `apply_package` يتخطّى به بسببٍ مكتوب — قاعدةٌ واحدة لا نسختان.
    """
    return (
        client.services
        .filter(service=service)
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=starts_on))
        .order_by("starts_on", "id")
        .first()
    )


def _insert_client_service(
    *, client, service, starts_on, responsible_from, frequency, suggestion, actor,
) -> ClientService:
    """صفُّ خدمةٍ وأولُ صفّ دوريةٍ له في المعاملة نفسها — **موضعُ الإنشاء الوحيد**.

    الدوريةُ والمقترحُ يصلان جاهزين: المنادي (إضافةً أو تطبيقَ باقة) يحسب
    الاقتراح مرّةً واحدة، فلا يُحسب مرّتين ولا يُقرأ السقفُ مرّتين. وشركةُ الخدمة
    تُفحص هنا أيضاً (دفاعٌ في العمق): باقةٌ رُبطت برمجياً بخدمةٍ من كتالوج مكتبٍ
    آخر لا تُنسخ إلى هذا الزبون.
    """
    _assert_service_of_tenant(client.tenant, service)
    # #279: قبل أيّ كتابةٍ — لا صفَّ خدمةٍ يُنشأ ثم يُرفض.
    _assert_payroll_frequency(service.code, frequency)
    with transaction.atomic():
        row = ClientService.objects.create(
            tenant=client.tenant,
            client=client,
            service=service,
            starts_on=starts_on,
            responsible_from=responsible_from,
        )
        ClientServiceFrequency.objects.create(
            client_service=row,
            frequency=frequency,
            effective_from=starts_on,
            suggested=suggestion or "",
            created_by=actor if getattr(actor, "pk", None) else None,
        )
    return row


def add_client_service(
    *, client, service, starts_on=None, responsible_from=None,
    frequency=None, actor=None, today=None,
) -> ClientService:
    """إضافةُ خدمةٍ لزبون — و**أولُ صفّ دوريةٍ** بتاريخ بدئها في المعاملة نفسها.

    الدورية: الممرَّرة، وإلا المقترحة من البطاقة والسقف المؤرَّخ. وإن لم تكن هناك
    مقترحة (غيرُ مسجّلٍ في فلسطين مثلاً) فالطلبُ **يُرفض 400** بطلب اختيارٍ صريح —
    لا تخمينَ نيابةً عن الموظف. و«من أيّ فترةٍ المكتب مسؤول» تُطبَّع أولَ الشهر
    دائماً: المكتبُ مسؤولٌ عن فترةٍ كاملة أو لا.
    """
    today = today or timezone.localdate()
    _assert_service_of_tenant(client.tenant, service)
    if not service.is_active:
        raise ValidationError({"service": "هذه الخدمة معطَّلة في كتالوج المكتب."})
    starts_on = starts_on or today
    responsible_from = _first_of_month(responsible_from or today)
    if overlapping_client_service(client, service, starts_on) is not None:
        raise ValidationError({
            "service": (
                "فترةٌ متداخلةٌ مع صفٍّ قائمٍ لهذه الخدمة — حدّد تاريخاً بعد انتهائه."
            ),
        })

    suggestion, reason = suggest_frequency(client, service.code, starts_on)
    chosen = frequency or suggestion
    if chosen not in FREQUENCY_KEYS:
        if frequency:
            raise ValidationError({"frequency": "دورية غير معروفة."})
        raise ValidationError({"frequency": reason or "اختر دورية الخدمة."})

    return _insert_client_service(
        client=client,
        service=service,
        starts_on=starts_on,
        responsible_from=responsible_from,
        frequency=chosen,
        suggestion=suggestion,
        actor=actor,
    )


def change_client_service_frequency(
    client_service, *, frequency, effective_from, actor=None, today=None,
):
    """**التغييرُ يسري من تاريخٍ ولقدّام**: صفٌّ جديد، ولا يُعدَّل ما قبله أبداً.

    وتاريخٌ مسجَّلٌ سابقاً: يُستبدل صفُّه **فقط** إن كان مستقبلياً بعد اليوم (خطأُ
    إدخالٍ لم يقع بعد)، وإلا فهو تاريخٌ وقع — يُرفض ولا يُعاد كتابته.
    """
    today = today or timezone.localdate()
    if frequency not in FREQUENCY_KEYS:
        raise ValidationError({"frequency": "دورية غير معروفة."})
    # #279: البابُ الثاني لكتابة الدورية — الدوريةُ المؤرَّخة تحكمها القاعدةُ نفسها.
    _assert_payroll_frequency(client_service.service.code, frequency)
    if effective_from is None:
        raise ValidationError({"effective_from": "تاريخ السريان مطلوب."})
    if effective_from < client_service.starts_on:
        raise ValidationError({
            "effective_from": "التغيير لا يسبق بدء الخدمة.",
        })
    if client_service.ends_on is not None and effective_from > client_service.ends_on:
        raise ValidationError({
            "effective_from": "الخدمة موقوفة — لا دوريةَ بعد تاريخ الإيقاف.",
        })
    suggestion, _reason = suggest_frequency(
        client_service.client, client_service.service.code, effective_from,
    )
    created_by = actor if getattr(actor, "pk", None) else None
    with transaction.atomic():
        existing = client_service.frequencies.filter(
            effective_from=effective_from,
        ).first()
        if existing is not None:
            if effective_from <= today:
                raise ValidationError({
                    "effective_from": (
                        "دوريةٌ مسجَّلةٌ في هذا التاريخ — التغيير يسري من تاريخٍ لاحق."
                    ),
                })
            existing.frequency = frequency
            existing.suggested = suggestion or ""
            existing.created_by = created_by
            existing.save(update_fields=["frequency", "suggested", "created_by"])
            return existing
        return ClientServiceFrequency.objects.create(
            client_service=client_service,
            frequency=frequency,
            effective_from=effective_from,
            suggested=suggestion or "",
            created_by=created_by,
        )


def stop_client_service(client_service, *, ends_on, last_period_ours=True) -> ClientService:
    """الإيقافُ يكتب `ends_on` ويُبقي الصفّ — **ولا حذف**: التاريخُ سؤالٌ له جواب.

    وثلاثةُ رفوضٍ قبله: تاريخٌ مطلوب، وصفٌّ موقوفٌ سابقاً (الإيقافُ مرّةٌ واحدة —
    كتابةُ تاريخٍ ثانٍ كانت تمحو الأول بلا أثر)، و`ends_on` يسبق تاريخَ سريان
    دوريةٍ مسجَّلة (فلا دوريةَ تُسجَّل بعد انتهاء الخدمة). والتحقّقُ والكتابةُ في
    معاملةٍ واحدة كالإضافة وتغيير الدورية.

    **و«آخرُ فترةٍ علينا؟» (#275)**: `last_period_ours=False` تعني أن المكتب لا
    يتحمّل آخر فترةٍ في كل سلسلةٍ — فتُكتب على الصفّ (فلا يولّدها «حدّث المكتب»
    أبداً)، **وكلُّ التزامٍ منتظرٍ لها يُعلَّم «مش لازم هالفترة»** بدل أن يبقى
    في الشاشة أبداً. والمنقضي قبلها يبقى: تقريرُ آذار المستحقُّ في نيسان له صفّ.
    """
    if ends_on is None:
        raise ValidationError({"ends_on": "تاريخ الإيقاف مطلوب."})
    if client_service.ends_on is not None:
        raise ValidationError({
            "ends_on": (
                f"الخدمة موقوفةٌ بتاريخ {client_service.ends_on.isoformat()} — "
                "لا إيقافَ ثانٍ."
            ),
        })
    if ends_on < client_service.starts_on:
        raise ValidationError({"ends_on": "الإيقاف لا يسبق بدء الخدمة."})
    latest = client_service.frequencies.order_by("-effective_from").first()
    if latest is not None and ends_on < latest.effective_from:
        raise ValidationError({
            "ends_on": (
                "الإيقاف يسبق تاريخ سريان دوريةٍ مسجَّلة — "
                f"أقربُ سريانٍ {latest.effective_from.isoformat()}."
            ),
        })
    with transaction.atomic():
        client_service.ends_on = ends_on
        client_service.last_period_ours = bool(last_period_ours)
        client_service.save(update_fields=["ends_on", "last_period_ours"])
        if not client_service.last_period_ours:
            _close_pending_last_periods(client_service)
    return client_service


def apply_package(client, package, *, actor=None, today=None) -> dict:
    """تطبيقُ باقةٍ على زبون: **نسخٌ لا ربط** — ويُرجع ما أُضيف وما تُخطّي.

    كلُّ خدمةٍ في الباقة تُفحص: المعطَّلةُ في الكتالوج تُبلَّغ بسببها، والمتداخلةُ
    مع فترةٍ قائمةٍ تُبلَّغ بذلك، والباقي يُنسخ بالدورية المقترحة (`on_demand` إن
    لا اقتراح). والاقتراحُ يُحسب هنا **مرّةً واحدة** ويُسلَّم لـ
    `_insert_client_service` جاهزاً. وتعديلُ الباقة بعدها لا يمسّ الزبون، وتعديلُ
    خدمات الزبون لا يمسّ الباقة — لا حقلَ ربطٍ بينهما.
    """
    if package is None or package.tenant_id != client.tenant_id:
        raise ValidationError({"package": _PACKAGE_NOT_FOUND})
    today = today or timezone.localdate()
    added: list[dict] = []
    skipped: list[dict] = []
    with transaction.atomic():
        for service in package.services.order_by("position", "name", "id"):
            if not service.is_active:
                skipped.append({
                    "service_id": service.pk,
                    "service_name": service.name,
                    "reason": "معطَّلة في كتالوج المكتب",
                })
                continue
            if overlapping_client_service(client, service, today) is not None:
                skipped.append({
                    "service_id": service.pk,
                    "service_name": service.name,
                    "reason": "فترةٌ متداخلةٌ عند الزبون — لم تُمسّ دوريتُها",
                })
                continue
            suggestion, _reason = suggest_frequency(client, service.code, today)
            chosen = suggestion or FREQUENCY_ON_DEMAND
            row = _insert_client_service(
                client=client,
                service=service,
                starts_on=today,
                responsible_from=_first_of_month(today),
                frequency=chosen,
                suggestion=suggestion,
                actor=actor,
            )
            added.append({
                "service_id": service.pk,
                "service_name": service.name,
                "client_service_id": row.pk,
                "frequency": chosen,
            })
    return {"added": added, "skipped": skipped}


# ── اقتراحُ الدورية من البطاقة والسقف المؤرَّخ (#273) ───────────────────────
def _vat_classification(client) -> str:
    card = getattr(client, "tax_card", None)
    return (card.vat_classification if card is not None else "") or ""


def _vat_label(tax_system, value) -> str:
    """تسميةُ تصنيف ق.م **من اختيارات البطاقة** لا من نصٍّ مكتوبٍ هنا."""
    labels = dict(tax_card_choices(tax_system, "vat_classification"))
    return labels.get(value, value or "")


def _threshold_for(tax_system, kind, day):
    """`(الصفّ, تقديريّ؟)` — سنةٌ بلا سقفٍ منشورٍ تأخذ آخر سقفٍ سابق وتُعلَن تقديرية."""
    row = TaxThreshold.objects.filter(
        tax_system=tax_system, kind=kind, year=day.year,
    ).first()
    if row is not None:
        return row, False
    fallback = (
        TaxThreshold.objects
        .filter(tax_system=tax_system, kind=kind, year__lt=day.year)
        .order_by("-year")
        .first()
    )
    if fallback is None:
        return None, False
    return fallback, True


def _suggest_palestinian_vat(client):
    """فلسطين: المسجّل (مرخّص أو معفى) يقدّم دورياً، وغيرُ المسجّل لا تقريرَ له."""
    classification = _vat_classification(client)
    if not classification:
        return None, "البطاقة بلا تصنيف ق.م — أكملها لتُقترح الدورية"
    label = _vat_label("PS", classification)
    if classification in ("licensed", "exempt"):
        return FREQUENCY_MONTHLY, f"فلسطيني · {label} — تقرير ق.م شهريّ"
    return None, f"فلسطيني · {label} — لا تقرير دوري"


def _suggest_israeli_vat(client, on_date):
    """إسرائيل: منشورٌ من المبيعات السنوية مقابل سقف السنة — والسقفُ بياناتٌ مؤرَّخة."""
    classification = _vat_classification(client)
    if not classification:
        return None, "البطاقة بلا تصنيف ق.م — أكملها لتُقترح الدورية"
    label = _vat_label("IL", classification)
    card = getattr(client, "tax_card", None)
    annual_sales = card.annual_sales if card is not None else Decimal("0")
    if classification == "exempt":
        # المعفى يبقى سنوياً، لكن سقفَ עוסק פטור **يُقرأ لا يُترك خاملاً**: تجاوزُه
        # يعني أن التصنيفَ صار موضعَ مراجعة — والسببُ نصٌّ بلا أرقام مبالغ.
        reason = f"إسرائيلي · {label} — הצהרת עוסק פטור سنوية"
        threshold, estimated = _threshold_for(
            "IL", THRESHOLD_KIND_VAT_EXEMPT_DEALER, on_date,
        )
        if threshold is not None and annual_sales > threshold.amount:
            basis = (
                f"تقديري: سقف עוסק פטור لسنة {threshold.year}" if estimated
                else f"سقف עוסק פטור لسنة {threshold.year}"
            )
            reason += f"؛ المبيعات تتجاوز {basis} — راجع التصنيف"
        return FREQUENCY_ANNUAL, reason
    if classification not in ("authorized", "nonprofit"):
        return None, f"إسرائيلي · {label} — تصنيفٌ لا تقريرَ دوري له"

    threshold, estimated = _threshold_for(
        "IL", THRESHOLD_KIND_VAT_MONTHLY_REPORTING, on_date,
    )
    if threshold is None:
        return None, f"إسرائيلي · {label} — لا سقفَ منشوراً لهذه السنة"
    # السببُ **بلا أرقام مبالغ**: السنةُ ونظامُها وتصنيفُها فقط — فلا يحتاج قناعاً.
    basis = f"تقديري: سقف {threshold.year}" if estimated else f"سقف {threshold.year}"
    if annual_sales == 0:
        return (
            FREQUENCY_BIMONTHLY,
            f"إسرائيلي · {label} — {basis}: لا مبيعات سنوية في البطاقة",
        )
    if annual_sales > threshold.amount:
        return (
            FREQUENCY_MONTHLY,
            f"إسرائيلي · {label} — {basis}: المبيعات تتجاوزه ⇒ تقرير شهريّ",
        )
    return (
        FREQUENCY_BIMONTHLY,
        f"إسرائيلي · {label} — {basis}: المبيعات في حدوده ⇒ تقرير كل شهرين",
    )


def suggest_frequency(client, service_code, on_date=None):
    """الدوريةُ المقترحةُ لخدمةٍ عند تاريخ — `(frequency | None, reason: str)`.

    النظامُ من `resolve_setting(... "tax_system", client=client)` — بطاقةُ الزبون لا
    إعدادُ المكتب. والاقتراحُ **اقتراح**: الموظف يؤكّده أو يغيّره، والباقي يُخزَّن
    بتاريخ سريانه.
    """
    on_date = on_date or timezone.localdate()
    code = (service_code or "").strip()
    if code == SERVICE_CODE_PAYROLL:
        return FREQUENCY_MONTHLY, "رواتب — تقريرٌ شهريّ"
    if code == SERVICE_CODE_BOOKKEEPING:
        return FREQUENCY_MONTHLY, "مسك دفاتر — عملٌ شهريّ"
    if code == SERVICE_CODE_ANNUAL_ACCOUNTS:
        return FREQUENCY_ANNUAL, "ميزانية وتدقيق — عملٌ سنويّ"
    if code == SERVICE_CODE_CONSULTING:
        return FREQUENCY_ON_DEMAND, "استشارات ومعاملات — عند الطلب"
    if code != SERVICE_CODE_VAT:
        return FREQUENCY_ON_DEMAND, "خدمةٌ يضيفها المكتب — عند الطلب"

    system = resolve_setting(client.tenant, TAX_SYSTEM_KEY, client=client)
    if system == "PS":
        return _suggest_palestinian_vat(client)
    if system == "IL":
        return _suggest_israeli_vat(client, on_date)
    return None, "لم يُختَر النظام الضريبي بعد — اختره من إعدادات المكتب"


def suggestion_payload(client, service, *, on_date=None) -> dict:
    """حمولةُ نقطة الاقتراح: المقترحُ وسببه واختياراتُ الدوريات — كلها من الخادم."""
    day = on_date or timezone.localdate()
    suggestion, reason = suggest_frequency(client, service.code, day)
    return {
        "service": service.code,
        "service_id": service.pk,
        "service_name": service.name,
        "on": day.isoformat(),
        "frequency": suggestion,
        "frequency_label": frequency_label(suggestion),
        "reason": reason,
        "frequency_choices": frequency_choices(),
    }


# ── لائحة المواعيد والتقويم (#274) ──────────────────────────────────────────
#
# **المحرّكُ نقيٌّ في `accounting_office/deadlines.py`، وهذا الموضع يربطه بالقاعدة
# والإعدادات:** يقرأ النسخةَ السارية، ويحلّ إعدادات الزبون **بالمحلّل وحده**،
# ويولّد الفترات من دورية الخدمة المؤرَّخة، ثم ينادي `compute_deadline`.
#
# **ولا يُحفظ شيء**: التقويمُ يُحسب عند كل قراءة، فتغييرُ سطرٍ في اللائحة يظهر في
# الطلب التالي بلا إعادة توليدٍ ولا وظيفةٍ خلفية.

#: أقصى ما يفصل الموعدَ عن نهاية فترته: قاعدتان تُلقيه في السنة التالية
#: (`month_day_next_year`)، فالفترةُ السنوية التي انتهت في 2025 قد يكون موعدُها في
#: 2026. فتُقرأ السلاسل من سنتين قبل بداية المدى كي لا تسقط فترةٌ موعدُها داخله.
DEADLINE_LOOKBACK_MONTHS = 12 * 2

#: أطولُ مدىً يطلبه التقويم — **شهران**: شبكةُ الشهر تصل 42 يوماً، والرُّبع (92)
#: يُرفض. ولا يصير الطلبُ مسحاً لسنوات.
CALENDAR_MAX_SPAN_DAYS = 62

#: إعدادُ أيام الموعد الداخلي بحسب الدورية — «كل شهرين» تأخذ حصّةَ الشهريّ،
#: و«نصف سنوي» (#279) حصّةَ الربعيّ: قاعدتُها أقربُ إلى الربعيّ في المدى ولا
#: إعدادَ سابعاً لها (#279/D1).
INTERNAL_LEAD_SETTING_BY_CADENCE: dict[str, str] = {
    FREQUENCY_MONTHLY: "internal_lead_days_monthly",
    FREQUENCY_BIMONTHLY: "internal_lead_days_monthly",
    FREQUENCY_QUARTERLY: "internal_lead_days_quarterly",
    CADENCE_SEMIANNUAL: "internal_lead_days_quarterly",
    FREQUENCY_ANNUAL: "internal_lead_days_annual",
}

#: إعدادُ «الالتزامات التي تولّدها خدمة الرواتب» (#279) — يقرؤه `rule_applies`.
PAYROLL_OBLIGATIONS_KEY = "payroll_obligations"

#: الإعداداتُ التي تُقرأ **جماعياً** لزبائن التقويم: كلُّها تقبل التخصيص لكل زبون،
#: فتُحلّ مرّةً لكل مفتاح في الطلب (`resolve_setting_for_clients`) لا مرّتين لكل
#: زبون. وأيامُ عطلة المكتب تُقرأ بلا زبونٍ مرّةً واحدة.
CONTEXT_SETTING_KEYS: tuple[str, ...] = (
    TAX_SYSTEM_KEY,
    "rest_days",
    "filing_method",
    PAYROLL_OBLIGATIONS_KEY,
    *INTERNAL_LEAD_SETTING_BY_CADENCE.values(),
)


@dataclass
class ThresholdContext:
    """سياقُ قراءة السقوف لسطرٍ في سنةٍ ما — بمُذكِّرة، فلا يُقرأ السقفُ مرّتين.

    `cache` يُشارَك مع سياق التقويم كلِّه (`CalendarContext.thresholds`)، فسقفُ
    (نظام، نوع، سنة) يُقرأ **مرّةً في الطلب** لا مرّةً لكل فترةٍ لكل زبون.
    """

    tax_system: str
    day: date
    cache: dict = field(default_factory=dict, repr=False)

    def get(self, kind: str):
        """`(صفُّ السقف | None, تقديريّ؟)` — بقاعدة `_threshold_for` وحدها."""
        key = (self.tax_system, kind, self.day.year)
        if key not in self.cache:
            self.cache[key] = _threshold_for(self.tax_system, kind, self.day)
        return self.cache[key]


def schedule_for(tax_system, year) -> tuple[DeadlineSchedule | None, bool]:
    """النسخةُ السارية لسنةٍ — أو آخر سنةٍ سابقة معها، وتُعلَن **تقديرية**.

    «السارية» = أكبر `version` لتلك السنة، فلا تُعدَّل نسخةٌ منشورة. وسنةٌ بلا
    نسخةٍ (2028 اليوم) تأخذ نسخةَ 2027 وتُعلَن تقديرية، فتتجاهل تعديلاتها
    المنشورة لأنها لسنةٍ أخرى. ولا نسخةَ أصلاً ⇒ `(None, False)`.
    """
    current = (
        DeadlineSchedule.objects
        .filter(tax_system=tax_system, year=year)
        .order_by("-version")
        .first()
    )
    if current is not None:
        return current, False
    previous = (
        DeadlineSchedule.objects
        .filter(tax_system=tax_system, year__lt=year)
        .order_by("-year", "-version")
        .first()
    )
    if previous is None:
        return None, False
    return previous, True


def rule_applies(
    rule, card, thresholds_ctx: ThresholdContext, *, payroll_obligations=None,
) -> bool:
    """هل يُولّد هذا السطرُ التزاماً لهذه البطاقة؟ — **الشروطُ من اللائحة**.

    `is_generated=False` («لا يُولَّد») يسقط أوّلاً. ثم كلُّ شرطٍ في
    `rule.conditions`: التصنيفُ ونوعُ الكيان يُشترطان في قائمتهما، والموظفون
    والتعاملُ الذاتيّ تطابقاً، والسقفُ تجاوزاً (`annual_sales > السقف المنشور`).
    وسقفٌ غير منشورٍ لسنةٍ ولا لسابقةٍ لها ⇒ لا يُثبت التجاوز ⇒ لا يُولَّد.

    **وإعدادُ «الالتزامات التي تولّدها خدمة الرواتب» (#279) يُطبَّق هنا وحده**:
    سطرُ خدمة الرواتب الذي أُخرِج من الإعداد لا يُولَّد لصاحبه — فالتوليدُ والتقويمُ
    يقرآن قراراً واحداً من هذه الدالّة. **وأما «اليوم» فيقرأ الصفوف المحفوظة**:
    تقليصُ الإعداد لا يحذف التزاماً وُلد قبلُ ولا يعيد كتابة تاريخه (#275)، فيبقى
    ظاهراً حتى يحسمه المكتب («مش لازم»). و`None` (نداءٌ بلا سياق) تعني «كلُّ
    البنود مفعّلة» — وهي **الافتراضُ في السجلّ**، فلا يفترق المنادي القديم عن
    القرار.
    """
    if not rule.is_generated:
        return False
    if (
        rule.service_code == SERVICE_CODE_PAYROLL
        and payroll_obligations is not None
        and rule.code not in payroll_obligations
    ):
        return False
    conditions = rule.conditions or {}

    for key, field_name in (
        (CONDITION_VAT_CLASSIFICATION_IN, "vat_classification"),
        (CONDITION_ENTITY_TYPE_IN, "entity_type"),
    ):
        allowed = conditions.get(key)
        if allowed is None:
            continue
        if (getattr(card, field_name, "") or "") not in allowed:
            return False

    for key, field_name in (
        (CONDITION_HAS_EMPLOYEES, "has_employees"),
        (CONDITION_IS_SELF_EMPLOYED, "is_self_employed"),
    ):
        expected = conditions.get(key)
        if expected is None:
            continue
        if bool(getattr(card, field_name, False)) != bool(expected):
            return False

    kind = conditions.get(CONDITION_ANNUAL_SALES_ABOVE)
    if kind:
        threshold, _estimated = thresholds_ctx.get(kind)
        if threshold is None or card is None:
            return False
        return card.annual_sales > threshold.amount
    return True


def _service_periods(client_service, *, floor, end, frequencies):
    """فتراتُ خدمةٍ دوريتُها مؤرَّخة — `(البداية, النهاية, الدورية)`.

    الحسابُ في `deadlines.service_periods` (حزمٌ محاذاةٌ للتقويم، والشهرُ تحكمه
    دوريتُه في آخره)، وهذا الربطُ وحده هنا: خدمةُ الزبون ودورياتُها المؤرَّخة.

    والدوريةُ في الثلاثية هي التي **قرأها** المحرّكُ للفترة، لا المستنتَجةُ من
    طولها: فترةٌ قُطعت بتغيير الدورية (نيسان–كانون الأول بعد التحوّل إلى سنوية)
    تبقى بدوريتها.

    والمؤشّرُ الأول أولُ شهرٍ في `max(floor, starts_on, responsible_from)` — أرضيةُ
    المدى يأتي بها المنادي (التقويمُ بسقف 24 شهراً، والتحديثُ بلا سقف)، والحزمُ
    محاذاة، فلا تتغيّر النتيجة ببداية الطلب.
    """
    def frequency_of_month(month):
        return _frequency_at_month_end(client_service, month, frequencies)

    floor = max(floor, client_service.starts_on, client_service.responsible_from)
    return deadlines.service_periods(frequency_of_month, floor, end)


def client_service_periods(client_service, *, floor, end, frequencies=None):
    """**الواجهةُ العامة** لفترات خدمةٍ مؤرَّخة — يقرؤها جرّافُ الأتعاب (#282).

    الربطُ بين خدمة الزبون ودورياتها المؤرَّخة في `_service_periods` وحدها؛ نسخةٌ
    ثانية منه في `accounting_office/fees.py` تفترق عن قاعدة «الدورية في آخر
    الشهر» عند أول تعديلٍ بصمت. و`frequencies` تُمرَّر محمَّلةً سلفاً حين تكون
    القائمةُ تُبنى لزبائن كثيرين، فلا استعلامُ دورياتٍ لكل خدمة.
    """
    if frequencies is None:
        frequencies = list(client_service.frequencies.all())
    return _service_periods(
        client_service, floor=floor, end=end, frequencies=frequencies,
    )


def _frequency_at_month_end(client_service, month, frequencies):
    """الدوريةُ السارية في **آخر** يومٍ من الشهر — بدايةٌ في 15/2 تُدرك شباط.

    `frequency_on` تقارن `effective_from` باليوم، و`effective_from` يساوي
    `starts_on` بلا تطبيعٍ لأول الشهر؛ فقراءةُ أول الشهر تُسقط شهراً بدأ في منتصفه
    (أولُ صفّ دوريةٍ سريانُه 15/2 لا يطابق 1/2). وقراءةُ آخره تُدركه.
    """
    month_end = deadlines.month_start_after(month, 1) - timedelta(days=1)
    current = frequency_on(client_service, month_end, rows=frequencies)
    return current.frequency if current else None


def _period_is_ours(client_service, period_end) -> bool:
    """الفترةُ تخصّ المكتب: انتهت بعد بدئه وبعد مسؤوليته، وقبل إيقاف الخدمة."""
    if period_end < client_service.starts_on:
        return False
    if period_end < client_service.responsible_from:
        return False
    if client_service.ends_on is not None and period_end > client_service.ends_on:
        return False
    return True


def _rules_by_service(schedule) -> dict[str, list]:
    """أسطرُ النسخة مجمَّعةً بكود الخدمة — دورةٌ واحدة لكل نسخة، لا سطرٍ بسطر."""
    grouped: dict[str, list] = {}
    for rule in schedule.rules.all():
        grouped.setdefault(rule.service_code, []).append(rule)
    return grouped


@dataclass
class CalendarContext:
    """سياقُ طلبٍ واحدٍ للتقويم — يمنع N+1 ويُبقي `client_deadlines` صالحةً وحدها.

    يُبنى مرّةً قبل حلقة الزبائن: مُذكِّرةُ النسخ والأسطر، وأيامُ عطلة المكتب،
    والإعداداتُ القابلة للتخصيص مُحلَّلةً **جماعياً** لزبائن الطلب
    (`resolve_setting_for_clients` مفتاحاً مفتاحاً). وخدماتُ الزبائن تُجلب بـ
    `prefetch_related` على استعلام الزبائن الأب.

    **ويحمل تعديلات المكتب وقواعده (#277) قِراءةً واحدة**: الساري لكل
    `(نظام, كود)` وقواعدُ المكتب المفعّلة مجمَّعةً بكود الخدمة — فلا استعلامَ لكل
    سطرٍ ولا لكل زبون.

    و`client_deadlines(client, …)` بلا سياقٍ تبني سياقَها لزبونٍ واحد، فتبقى
    صالحةً منفردةً (اختبارٌ أو نداءٌ داخليّ) بلا كلفةٍ إضافية.
    """

    tenant: Any
    settings: dict[str, dict[int, Any]] = field(default_factory=dict, repr=False)
    office_rest_days: list = field(default_factory=list)
    #: بمفتاح `(النظام, السنة)`: مكتبٌ يضمّ نظامين لا يقرأ نسخةَ أحدِهما للآخر.
    schedules: dict[tuple[str, int], tuple] = field(default_factory=dict, repr=False)
    #: سقوفُ (نظام، نوع، سنة) — مشتركةٌ بين كل فترات الطلب.
    thresholds: dict[tuple[str, str, int], tuple] = field(
        default_factory=dict, repr=False,
    )
    #: #277: الساري من تعديلات المكتب، بمفتاح `(النظام, كود السطر)`.
    overrides: dict[tuple[str, str], Any] = field(default_factory=dict, repr=False)
    #: #277: قواعدُ المكتب المفعّلة، مجمَّعةً بكود خدمة الزبون.
    custom_rules: dict[str, list] = field(default_factory=dict, repr=False)
    #: #278: بنداتُ الأوراق لكل `(النظام, الدورية)` — قراءةٌ واحدة لكل نظامٍ في الطلب.
    document_items: dict[tuple[str, str], list] = field(
        default_factory=dict, repr=False,
    )
    #: #278: خيارُ المكتب على البنود، وخيارُ كل زبونٍ — تُقرأ عند أول حاجةٍ مرّة.
    document_choices: dict[str, bool] | None = field(default=None, repr=False)
    document_client_choices: dict[int, dict[str, bool]] = field(
        default_factory=dict, repr=False,
    )

    def setting(self, client, key):
        """قيمةُ إعدادٍ لزبون — من المجموعة إن حُلّت، وإلا بالمحلّل."""
        resolved = self.settings.get(key)
        if resolved is None or client.pk not in resolved:
            return resolve_setting(self.tenant, key, client=client)
        return resolved[client.pk]

    def lead_days(self, client, setting_key) -> int:
        if not setting_key:
            return 0
        return self.setting(client, setting_key) or 0

    def schedule(self, tax_system, year) -> tuple:
        return _schedule_bundle(self.schedules, tax_system, year)


#: أقصى ما يُعرض من سجلّ تعديلاتٍ لسطرٍ واحد في شاشة اللائحة.
OVERRIDE_HISTORY_LIMIT = 20


def _override_index(tenant):
    """`(الساري, السجلّ)` في مرورٍ واحد — بمفتاح `(النظام, كود السطر)`.

    الصفوفُ مرتَّبةً `-created_at, -id`، فأوّلُ صفٍّ لكل مفتاح هو **الساري**، وما
    بعده تاريخٌ يُعرض ولا يحكم. و«رجّع للمنصة» صفٌّ `cleared` يُسقط المفتاح من
    الساري ولا يُحذف من السجلّ.
    """
    active: dict[tuple[str, str], OfficeRuleOverride] = {}
    history: dict[tuple[str, str], list[dict]] = {}
    for row in (
        OfficeRuleOverride.objects
        .filter(tenant=tenant)
        .select_related("created_by")
        .order_by("-created_at", "-id")
    ):
        key = (row.tax_system, row.rule_code)
        active.setdefault(key, row)
        entries = history.setdefault(key, [])
        if len(entries) < OVERRIDE_HISTORY_LIMIT:
            entries.append(_override_row(row))
    return {key: row for key, row in active.items() if not row.cleared}, history


def active_rule_overrides(tenant) -> dict[tuple[str, str], OfficeRuleOverride]:
    """**الساري** من تعديلات المكتب: أحدثُ صفٍّ لكل (نظام، كود) وغيرُ مُرجَع."""
    return _override_index(tenant)[0]


def _active_custom_rules(tenant) -> dict[str, list]:
    """قواعدُ المكتب المفعّلة مجمَّعةً بكود خدمتها — استعلامٌ واحد."""
    grouped: dict[str, list] = {}
    for row in (
        OfficeCustomRule.objects
        .filter(tenant=tenant, is_active=True)
        .select_related("service")
        .order_by("name", "id")
    ):
        grouped.setdefault(row.service.code, []).append(row)
    return grouped


def calendar_context(tenant, clients) -> CalendarContext:
    """سياقُ الطلب: الإعداداتُ القابلة للتخصيص جماعياً + عطلةُ المكتب مرّةً.

    ومعها تعديلاتُ المكتب وقواعدُه (#277): قراءتان ثابتتان مهما كثر الزبائن.
    """
    clients = list(clients)
    resolved: dict[str, dict[int, Any]] = {}
    if clients:
        for key in dict.fromkeys(CONTEXT_SETTING_KEYS):
            resolved[key] = resolve_setting_for_clients(tenant, key, clients)
    return CalendarContext(
        tenant=tenant,
        settings=resolved,
        office_rest_days=resolve_setting(tenant, "rest_days") or [],
        overrides=active_rule_overrides(tenant),
        custom_rules=_active_custom_rules(tenant),
    )


@dataclass(frozen=True)
class RuleSpec:
    """لقطةُ سطرٍ بالشكل الذي يقرؤه المحرّك — لا نموذجَ ثانٍ للقاعدة.

    `compute_deadline` يقرأ `code`/`rule_kind`/`rule_day`/`rule_month`/
    `electronic_extension_days`/`period_overrides` وحدها، فتكفي هذه اللقطة بدل
    الكائن المحفوظ. وهي لقطةُ قاعدة مكتبٍ كما هي لقطةُ سطر منصةٍ بقيم المكتب —
    **ولقطةٌ لا نسخةٌ من الصفّ**: `copy.copy` على صفّ `DeadlineRule` يتشارك
    `_state`، فأيّ `save()` عليه يكتب قيم المكتب فوق لائحة المنصة.
    """

    code: str
    rule_kind: str
    rule_day: int | None = None
    rule_month: int | None = None
    electronic_extension_days: int = 0
    period_overrides: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DeadlineItem:
    """بندُ موعدٍ واحد كما يُخرجه المولّد الوحيد — للتقويم والتحديث معاً.

    يحمل أصلَه (`official`/`office`) ومصدرَه: سطرُ منصةٍ (`rule`) أو قاعدةُ
    مكتبٍ (`custom_rule`). و`code`/`name` يُقرآن من المصدر صراحةً فلا فرعان في
    كل مستهلك.
    """

    client: Any
    client_service: Any
    result: deadlines.DeadlineResult
    rule: Any = None
    custom_rule: Any = None
    origin: str = OBLIGATION_ORIGIN_OFFICIAL

    @property
    def code(self) -> str:
        return self.rule.code if self.rule is not None else self.custom_rule.code

    @property
    def name(self) -> str:
        return self.rule.name if self.rule is not None else self.custom_rule.name

    @property
    def needs_review(self) -> bool:
        return bool(getattr(self.rule, "needs_review", False))


def custom_rule_spec(custom_rule) -> RuleSpec:
    """لقطةُ قاعدة مكتبٍ للمحرّك — بلا تمديدٍ إلكترونيّ ولا نشرةٍ منشورة."""
    return RuleSpec(
        code=custom_rule.code,
        rule_kind=custom_rule.rule_kind,
        rule_day=custom_rule.rule_day,
        rule_month=custom_rule.rule_month,
    )


def _rule_with_override(rule, override) -> RuleSpec:
    """سطرُ المنصة بقيم المكتب — **لقطةٌ** لا تُحفظ ولا تمسّ الصفّ المحفوظ.

    و`None` في التعديل تعني «كالمنصة». و`period_overrides` المنشورة **تُسقط**
    حين يُعدَّل السطر: قرارُ المكتب يغلب نشرةَ المنصة (#277). وسياسةُ يوم الراحة
    للنسخة تبقى سارية: المكتبُ عدّل التاريخ لا القاعدة.
    """
    return RuleSpec(
        code=rule.code,
        rule_kind=rule.rule_kind,
        rule_day=rule.rule_day if override.rule_day is None else override.rule_day,
        rule_month=(
            rule.rule_month if override.rule_month is None else override.rule_month
        ),
        electronic_extension_days=(
            rule.electronic_extension_days
            if override.electronic_extension_days is None
            else override.electronic_extension_days
        ),
        period_overrides={},
    )


def _deadline_result(
    client, *, period_start, period_end, cadence, context, system,
    rule=None, custom_rule=None, override=None,
):
    """**مدخلاتُ المحرّك الوحيدة** لموعدٍ واحد — يقرؤها المولّد وإعادةُ الحساب.

    تقرأ كلَّ إعدادٍ بالمحلّل والسياق، وتستدعي `deadlines.compute_deadline` بنفس
    الترتيب، ثم تُلحق تحذيرَ السقف التقديري **هنا** لا في مستهلكٍ دون آخر: من
    يُعيد حساب التزامٍ محفوظٍ يأخذ التحذيرَ نفسَه الذي أخذه المولّد، فلا تمحوه
    الإعادة (#277).

    وإذا كان للسطر تعديلُ مكتبٍ حُسب موعدُ المنصة أيضاً، فإن اختلف `official_date`
    حُمِل في `platform_official_date` — وإلا بقي `None` (لا نسخةً ثانية من القيمة
    بلا سبب).

    تُرجع `None` لسنةٍ بلا أيّ نسخةِ لائحة: لا موعدَ بلا قانون.
    """
    schedule, estimated, _grouped = context.schedule(system, period_end.year)
    if schedule is None:
        return None
    inputs = {
        "period_start": period_start,
        "period_end": period_end,
        "estimated": estimated,
        "client_rest_days": context.setting(client, "rest_days") or [],
        "office_rest_days": context.office_rest_days,
        "filing_method": context.setting(client, "filing_method"),
        "internal_lead_days": context.lead_days(
            client, INTERNAL_LEAD_SETTING_BY_CADENCE.get(cadence),
        ),
        "schedule_policy": schedule.rest_day_policy,
        "authority_closed_days": schedule.authority_closed_days or [],
    }
    if custom_rule is not None:
        result = deadlines.compute_deadline(custom_rule_spec(custom_rule), **inputs)
    elif override is not None:
        result = deadlines.compute_deadline(
            _rule_with_override(rule, override), **inputs,
        )
        platform = deadlines.compute_deadline(rule, **inputs)
        if platform.official_date != result.official_date:
            result = replace(result, platform_official_date=platform.official_date)
    else:
        result = deadlines.compute_deadline(rule, **inputs)
    if rule is None:
        return result
    return _with_estimated_threshold_warning(
        result, rule,
        ThresholdContext(tax_system=system, day=period_end, cache=context.thresholds),
    )


def _deadline_items(client, *, floor, end, context):
    """**المولّدُ الوحيد**: بندُ موعدٍ لكل `(الزبون, خدمةُ الزبون, السطر, الفترة)`.

    لكل خدمةٍ عند الزبون، ولكل سطرٍ في **نسخة نظامه** يخصّ خدمتها، فتراتٌ فقاعدته:

    - **`cadence == "service"`**: الفتراتُ من دورية الخدمة المؤرَّخة
      (`deadlines.service_periods`) — حزمٌ محاذاةٌ للتقويم تتبع تغييرَها.
    - **دوريةٌ ثابتة** (`monthly`/`quarterly`/`annual`): الفتراتُ من
      `deadlines.periods_for` على `rule.cadence`، **مستقلّةً عن دورية الخدمة** —
      وإلا وُلّد التقريرُ السنوي اثنتَي عشرة مرّةً لخدمةٍ شهرية، والرُّبعيُّ شهرياً.
    - **`cadence == "event"`** (#277): لا تُولَّد دورياً أبداً — سطرُ الحدث يُولَّد
      من حدثٍ مسجَّلٍ وحده (`record_client_event`).

    ثم تُصفّى بالفترة التي تخصّ المكتب (`_period_is_ours`) — بلا شرطٍ على
    `actual_deadline`: **التقويمُ** يقصّ على المدى، و**التحديثُ** يقصّ على
    `period_end < يومه`. ونسختان من توليد الفترات والقواعد كانتا تفترقان عند
    أول تصحيحٍ في اللائحة: التقويمُ يرى الجديد والتحديثُ يحفظ القديم.

    **وسطرٌ عليه تعديلُ مكتبٍ يُحسب بقيم المكتب** ويُحمل موعدُ المنصة بجانبه إن
    اختلف. و**قواعدُ المكتب الخاصة** تُولَّد بالفترات نفسها وبلا شروط بطاقة —
    المكتبُ عرّفها لنفسه، واللائحةُ لم تشترطها.
    """
    system = context.setting(client, TAX_SYSTEM_KEY)
    if not system:
        return

    # بطاقةٌ غائبةٌ (صفٌّ شُطب يدوياً) لا تُسقِط تقويمَ المكتب: الشروطُ المشروطة
    # بالبطاقة لا تنطبق عليها، فيبقى ما لا شرطَ له (دفترٌ بلا بطاقةٍ لا مواعيدَ له).
    card = getattr(client, "tax_card", None)
    # #279: إعدادُ بنود الرواتب يُقرأ مرّةً للزبون من سياق الطلب (لا استعلامَ لكل
    # سطر)، ويُمرَّر إلى `rule_applies` وحدها — فقرارٌ واحدٌ للتوليد والتقويم.
    payroll_obligations = context.setting(client, PAYROLL_OBLIGATIONS_KEY)

    for client_service in client_services_of(client, context):
        frequencies = list(client_service.frequencies.all())
        service_code = client_service.service.code
        custom_rules = context.custom_rules.get(service_code, [])
        for period_start, period_end, source, cadence in _periods_for_service(
            client_service, service_code, frequencies,
            system=system, floor=floor, end=end, context=context,
        ):
            if not _period_is_ours(client_service, period_end):
                continue
            schedule, _estimated, grouped = context.schedule(system, period_end.year)
            if schedule is None:
                continue
            thresholds = ThresholdContext(
                tax_system=system, day=period_end, cache=context.thresholds,
            )
            for rule in grouped.get(service_code, []):
                # السطرُ يولّد فتراتِ مصدره وحده: سطرٌ سنويّ لا يُولَّد لكل شهر،
                # وسطرُ «service» يولّد فترات دورية الخدمة وحدها. وسطرُ الحدث لا
                # يُولَّد دورياً بحال.
                if rule.cadence == CADENCE_EVENT or rule.cadence != source:
                    continue
                if not rule_applies(
                    rule, card, thresholds, payroll_obligations=payroll_obligations,
                ):
                    continue
                result = _deadline_result(
                    client,
                    rule=rule,
                    override=context.overrides.get((system, rule.code)),
                    period_start=period_start,
                    period_end=period_end,
                    cadence=cadence,
                    context=context,
                    system=system,
                )
                if result is None:
                    continue
                yield DeadlineItem(
                    client=client,
                    client_service=client_service,
                    rule=rule,
                    result=result,
                )
            for custom_rule in custom_rules:
                if custom_rule.cadence != source:
                    continue
                result = _deadline_result(
                    client,
                    custom_rule=custom_rule,
                    period_start=period_start,
                    period_end=period_end,
                    cadence=cadence,
                    context=context,
                    system=system,
                )
                if result is None:
                    continue
                yield DeadlineItem(
                    client=client,
                    client_service=client_service,
                    custom_rule=custom_rule,
                    result=result,
                    origin=OBLIGATION_ORIGIN_OFFICE,
                )


def client_deadlines(client, *, start, end, context=None) -> list[dict]:
    """مواعيدُ زبونٍ في مدى — محسوبةٌ عند القراءة ولا محفوظة.

    تُبنى من المولّد الوحيد (`_deadline_items`) بأرضية **سنتين قبل المدى**:
    قاعدتان تُلقيهما في السنة التالية (`month_day_next_year`)، ففترةٌ انتهت في
    2025 قد يكون موعدُها داخل المدى. ثم تُقصّ على `actual_deadline ∈ [start, end]`.

    **والتحديثُ اليوميّ يقرأ المولّد نفسه** بأرضية خدمة الزبون بلا سقف وبقصٍّ على
    `period_end` — فلا نسختان تفترقان.
    """
    context = context or calendar_context(client.tenant, [client])
    rows: list[dict] = []
    for item in _deadline_items(
        client,
        floor=deadlines.add_months(start, -DEADLINE_LOOKBACK_MONTHS),
        end=end,
        context=context,
    ):
        if not start <= item.result.actual_deadline <= end:
            continue
        rows.append({
            "client": client,
            "service": item.client_service.service,
            "rule": item.rule,
            "custom_rule": item.custom_rule,
            "code": item.code,
            "name": item.name,
            "needs_review": item.needs_review,
            "origin": item.origin,
            "result": item.result,
        })
    return rows


def _with_estimated_threshold_warning(result, rule, thresholds_ctx):
    """يُلحق «تقديري: سقف …» حين يُقرأ سقفُ شرط السطر من سنةٍ سابقة.

    `rule_applies` تبقى منطقيةً والمحرّكُ نقيّاً: العلامةُ تُقرأ من مُذكِّرة
    `ThresholdContext` نفسها (لا استعلامَ ثانياً)، وصيغتُها صيغةُ #273
    (`suggest_frequency`).
    """
    kind = (rule.conditions or {}).get(CONDITION_ANNUAL_SALES_ABOVE)
    if not kind:
        return result
    threshold, estimated = thresholds_ctx.get(kind)
    if threshold is None or not estimated:
        return result
    return replace(
        result, warnings=[*result.warnings, f"تقديري: سقف {threshold.year}"],
    )


def client_services_of(client, context=None):
    """خدماتُ الزبون — من ذاكرة `prefetch_related` حين يكون السياق محمَّلاً.

    ولا `order_by` بعدها: طلبُ ترتيبٍ على مديرٍ مُحمَّلٍ مسبقاً يستعلم من جديد،
    و`ClientService.Meta.ordering` هو الترتيبُ أصلاً.
    """
    if context is not None:
        return list(client.services.all())
    return list(
        client.services.select_related("service").prefetch_related("frequencies"),
    )


def _streams_for_service(
    client_service, service_code, frequencies, *, system, floor, end, context,
) -> dict[str, list[tuple]]:
    """فتراتُ الخدمة **مسقوفةً بمصدرها**: سلسلةٌ لكلِّ سطرٍ ثابتٍ + سلسلةُ الخدمة.

    المفتاحُ هو `source` نفسه (قيمةُ `rule.cadence`)، والقيمةُ ثلاثياتُ
    `(البداية, النهاية, دوريةُ الإعداد)`. وتُستعمل مرّتين بلا نسختين من الحساب:
    يُسطَّحها `_periods_for_service` للمولّد، ويقرأ منها `_last_periods_of_service`
    «آخرَ فترةٍ في كل سلسلة» عند الإيقاف.
    """
    cadences = _cadences_for_service(context, system, service_code, floor, end)
    streams: dict[str, list[tuple]] = {}
    if CADENCE_SERVICE in cadences:
        streams[CADENCE_SERVICE] = [
            (period_start, period_end, cadence)
            for period_start, period_end, cadence in _service_periods(
                client_service, floor=floor, end=end, frequencies=frequencies,
            )
        ]
    for cadence in cadences - {CADENCE_SERVICE}:
        streams[cadence] = [
            (period_start, period_end, cadence)
            for period_start, period_end in deadlines.periods_for(cadence, floor, end)
        ]
    return streams


def _periods_for_service(
    client_service, service_code, frequencies, *, system, floor, end, context,
) -> list[tuple]:
    """فتراتُ الخدمة كلُّها — `(البداية, النهاية, مصدرُ الفترة, دوريةُ الإعداد)`.

    تُسطَّح من `_streams_for_service`: سطرٌ ثابتُ الدورية يولّد فتراتِ قاعدته
    وحدها (`deadlines.periods_for`) مستقلّةً عن دورية الخدمة، وسطرُ `service`
    يولّد فترات دورية الخدمة المؤرَّخة، ودوريةُ الإعداد للفترة المقطوعة هي
    الدوريةُ التي قرأها المحرّكُ لها لا المستنتَجةُ من طولها.
    """
    return [
        (period_start, period_end, source, cadence)
        for source, periods in _streams_for_service(
            client_service, service_code, frequencies,
            system=system, floor=floor, end=end, context=context,
        ).items()
        for period_start, period_end, cadence in periods
    ]


def _cadences_for_service(context, tax_system, service_code, floor, end) -> set:
    """دورياتُ أسطر خدمةٍ في نسخ السنوات التي يمسّها المدى.

    ومعها دورياتُ قواعد المكتب المفعّلة (#277) — تُولَّد بالفترات نفسها، فلا
    نسخةً ثانية من حساب الفترات لهذا المصدر.
    """
    cadences: set[str] = set()
    for schedule, _estimated, grouped in _schedules_for_range(
        context, tax_system, floor, end,
    ):
        if schedule is None:
            continue
        cadences.update(
            rule.cadence
            for rule in grouped.get(service_code, [])
            if rule.is_generated and rule.cadence != CADENCE_EVENT
        )
    cadences.update(
        custom.cadence for custom in context.custom_rules.get(service_code, ())
    )
    return cadences


def _schedules_for_range(context, tax_system, floor, end) -> list[tuple]:
    """نسخُ سنوات المدى من مُذكِّرة السياق — لا استعلامَ جديداً بعد أوّل سنة."""
    return [
        context.schedule(tax_system, year)
        for year in range(floor.year, end.year + 1)
    ]


def _schedule_bundle(cache, tax_system, year) -> tuple:
    """`(النسخة, تقديريّ؟, الأسطرُ مجمَّعةً)` — بمُذكِّرةٍ داخل النداء الواحد.

    والمفتاحُ `(النظام, السنة)` لا السنةَ وحدها: مكتبٌ فيه زبونٌ فلسطينيّ وآخرُ
    إسرائيليّ كان يقرأ نسخةَ أحدِهما للآخر، فتُسقَط سطورُ الخدمة كلُّها.
    """
    key = (tax_system, year)
    if key not in cache:
        schedule, estimated = schedule_for(tax_system, year)
        cache[key] = (
            schedule,
            estimated,
            _rules_by_service(schedule) if schedule is not None else {},
        )
    return cache[key]


def calendar_row(item) -> dict:
    """سطرُ التقويم كما يُعرض — **بلا أيّ مبلغ** فلا حارسَ مبالغ يتأثّر.

    `expected` صحيحٌ دائماً: كلُّ سطرٍ في التقويم محسوبٌ لا محفوظ، والتقويمُ لا
    يحفظ شيئاً ولا يميّز المحفوظ — تمييزُه تذكرةٌ لاحقة.
    """
    result = item["result"]
    return {
        "client": {"id": item["client"].pk, "name": item["client"].name},
        "service": {
            "code": item["service"].code,
            "name": item["service"].name,
        },
        "rule": {
            "code": item["code"],
            "name": item["name"],
            "needs_review": item["needs_review"],
        },
        "origin": item["origin"],
        "origin_label": OBLIGATION_ORIGIN_LABELS.get(item["origin"], ""),
        "period_start": result.period_start.isoformat(),
        "period_end": result.period_end.isoformat(),
        "period_label": deadlines.period_label(result.period_start, result.period_end),
        "legal_date": result.legal_date.isoformat(),
        "official_date": result.official_date.isoformat(),
        "actual_deadline": result.actual_deadline.isoformat(),
        "internal_deadline": result.internal_deadline.isoformat(),
        # #277: تاريخُ المنصة حين يختلف عن موعد المكتب المعدَّل، وإلا `None`.
        "platform_official_date": (
            None if result.platform_official_date is None
            else result.platform_official_date.isoformat()
        ),
        "estimated": result.estimated,
        "postponed": result.postponed,
        "warnings": list(result.warnings),
        "expected": True,
    }


def calendar_payload(
    tenant, *, user, start, end, client=None, member=None, rule_code="", today=None,
) -> dict:
    """تقويمُ المدة — **قراءةٌ خالصة** على ما يراه هذا العضو من زبائن.

    الزبائنُ من `visible_clients` وحدها (فزبونُ غيرك لا يظهر)، و`member` يفلتر
    على المسؤول. والفلترةُ على المدى في `client_deadlines` قبل أيّ تشكيل، فلا
    يُبنى صفٌّ ليُرمى.

    **وسياقٌ واحدٌ قبل الحلقة** (`calendar_context`): الإعداداتُ القابلة للتخصيص
    تُحلّ جماعياً، والنسخُ والأسطرُ بمُذكِّرة، وخدماتُ الزبائن بـ
    `prefetch_related` على هذا الاستعلام — فكلفةُ الطلب لا تكبر بعدد الزبائن.
    """
    today = today or timezone.localdate()
    visible = visible_clients(tenant, user)
    # الفلترةُ في الاستعلام قبل أن يُقيَّم: `prefetch_related` يجلب خدماتِ ما تبقّى
    # وحده، لا خدماتِ كلِّ زبائن المكتب ثم يُرمى أغلبُها.
    if client is not None:
        visible = visible.filter(pk=client)
    if member is not None:
        visible = visible.filter(responsible_id=member)
    clients = list(
        visible
        .select_related("tax_card")
        .prefetch_related("services__service", "services__frequencies")
        .order_by("name", "id"),
    )

    context = calendar_context(tenant, clients)
    rows = []
    for office_client in clients:
        for item in client_deadlines(
            office_client, start=start, end=end, context=context,
        ):
            if rule_code and item["code"] != rule_code:
                continue
            rows.append(calendar_row(item))
    rows.sort(key=lambda row: (
        row["actual_deadline"], row["client"]["name"], row["rule"]["code"],
    ))
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "today": today.isoformat(),
        "rows": rows,
        # #281: مواعيدُ المدى مع التزاماته — التقويمُ يقرأ يومَه كاملاً: ما يجب
        # عمله وما حُجز فيه، ولا شاشةَ مواعيدَ ثانيةً تنافسه. **وبفلترَي التقويم
        # نفسيهما** (الزبون والموظّف) وإلا عرض تقويمٌ مُرشَّحٌ صفوفَ غيره.
        # و`kind_choices`: التقويمُ يحجز أيضاً (الموظّفُ يسجّل الموعد من هنا)،
        # فلا يبني جدولَ أنواعٍ ثانياً في الواجهة.
        "appointments": _appointments_module().calendar_appointments(
            tenant, user, start=start, end=end, client=client, member=member,
        ),
        "kind_choices": _appointments_module().kind_choices(),
    }


def deadline_rules_payload(tax_system, *, tenant=None) -> dict:
    """أسطرُ النسخة السارية لكل سنةٍ متاحةٍ في نظام — للفلتر ولعرض اللائحة.

    **استعلامان لا استعلامان لكل سنة**: النسخُ كلُّها بـ`prefetch_related("rules")`
    مرّةً، والأخذُ من أوّلها لكل سنة (المرتَّبةُ `-version` ⇒ السارية = أكبر نسخة).

    **ومفاتيحُ المكتب (#277) تُضاف بلا حذف مفتاح**: `rule_code` صريحاً (الكودُ
    يتكرّر لكل سنة، فلا مفتاحَ به)، و`platform` قيمُ المنصة، و`override` تعديلُ
    المكتب الساري أو `null`، و`history` آخرُ 20 صفّ تعديل، و`awaiting_decision`
    True حين تكون نسخةُ السطر أحدثَ من نسخة اللقطة وقيمُها تخالفها — **بالمسند
    نفسه** الذي يبني عليه التنبيه (`_based_on_matches`)، فلا تُنسخ القاعدة ولا
    تُقرأ من نصّ التنبيه.

    وتُقرأ مرّةً واحدةً للطلب (لا استعلامَ لكل سطر) — ولا تُقرأ أصلاً حين لا
    يُمرَّر `tenant`، فتبقى قراءةُ التقويم استعلامين كما كانت.
    """
    schedules = (
        DeadlineSchedule.objects
        .filter(tax_system=tax_system)
        .prefetch_related("rules")
        .order_by("year", "-version")
    )
    overrides: dict[tuple[str, str], Any] = {}
    history: dict[tuple[str, str], list[dict]] = {}
    snapshot_versions: dict[int, int] = {}
    if tenant is not None:
        overrides, history = _override_index(tenant)
        snapshot_ids = {
            (override.based_on or {}).get("schedule_id")
            for override in overrides.values()
        } - {None}
        if snapshot_ids:
            snapshot_versions = dict(
                DeadlineSchedule.objects
                .filter(pk__in=snapshot_ids)
                .values_list("pk", "version"),
            )
    kinds = dict(RULE_KIND_CHOICES)
    rows = []
    seen_years: set[int] = set()
    for schedule in schedules:
        if schedule.year in seen_years:
            continue
        seen_years.add(schedule.year)
        for rule in schedule.rules.all():
            key = (tax_system, rule.code)
            override = overrides.get(key)
            awaiting = False
            if override is not None:
                snapshot = override.based_on or {}
                awaiting = (
                    schedule.version > snapshot_versions.get(
                        snapshot.get("schedule_id"), 0,
                    )
                    and not _based_on_matches(snapshot, rule)
                )
            rows.append({
                "code": rule.code,
                "rule_code": rule.code,
                "name": rule.name,
                "service_code": rule.service_code,
                "is_generated": rule.is_generated,
                "needs_review": rule.needs_review,
                "year": schedule.year,
                "version": schedule.version,
                "source_url": rule.source_url,
                "platform": {
                    "rule_kind": rule.rule_kind,
                    "rule_kind_label": kinds.get(rule.rule_kind, ""),
                    "rule_day": rule.rule_day,
                    "rule_month": rule.rule_month,
                    "electronic_extension_days": rule.electronic_extension_days,
                },
                "override": None if override is None else _override_row(override),
                "history": history.get(key, []),
                "awaiting_decision": awaiting,
            })
    return {"system": tax_system, "rules": rows}


# ── الالتزامات والشغلات ومحرّك «حدّث المكتب ليوم X» (#275) ──────────────────
#
# **المحرّكُ واحد**: `_deadline_items` هو المولّدُ الوحيد للفترات والقواعد
# والنتائج. التقويمُ يقصّه على `actual_deadline`، والتحديثُ يقصّه على
# `period_end < today` — فلا نسختان تفترقان عند أول تصحيحٍ في اللائحة.
#
# **والمشتقُّ لا يُخزَّن**: شارةٌ واحدةٌ لكل صفّ — أحمرُ `late` (`due_date < day`) ثم أصفرُ
# `late_internal` (`task.internal_deadline < day`) ثم `near`؛ و`week` نافذةُ `due_date` مستقلّة (`_in_near_window`).
# والموعدُ الساري `due_date` = `extended_to or actual_deadline`: الأحمرُ ونافذةُ `week` عليه،
# والأصفرُ وحده على `task.internal_deadline`.

#: نافذةُ «قريب هالأسبوع»: من اليوم إلى ستة أيامٍ بعده (اليومُ السابع يومُ عملٍ آخر).
NEAR_WINDOW_DAYS = 6

#: فلاترُ شاشة «اليوم» — الفارغ «الكل»، والبقيةُ تُقصّ الصفوفَ بعد العدّ.
#: `late` الأحمرُ وحده، و`late_internal` الأصفرُ وحده (#276)، و`missing_docs`
#: «ناقصه أوراق» (#278).
TODAY_FILTERS: tuple[str, ...] = (
    "", "mine", "week", "late", "late_internal", "missing_docs",
)
TODAY_FILTER_HINT = (
    "فلترٌ غير معروف — mine أو week أو late أو late_internal أو missing_docs."
)

#: نصُّ رفض التراجع عن «انقدّم» — واحدٌ في الخدمة والاختبار.
SUBMITTED_LOCKED = "انقدّم لا يُتراجَع عنه"


def last_period_of_stream(periods, *, ends_on):
    """**آخرُ فترةٍ في سلسلة**: `(البداية, النهاية)` أو `None` — دالّةٌ نقيّة.

    التعريف: الفترةُ التي `period_end <= ends_on` **وتنتهي التي تليها بعد**
    `ends_on`. فالسلسلةُ الشهرية المقطوعة في 31 آذار آخرُها آذار، والمقطوعة في
    15 شباط آخرُها كانون الثاني — الفترةُ التي تحتوي تاريخَ الإيقاف ليست
    «منتهية» فلا تُحسب. والسلسلةُ متّصلةٌ ومحاذاة (`deadlines.periods_for`
    و`service_periods`)، فغيابُ التالي في قائمةٍ مقطوعةٍ يعني أنها الأخيرة.
    """
    last = None
    for index, (start, end) in enumerate(periods):
        if end > ends_on:
            break
        following = periods[index + 1] if index + 1 < len(periods) else None
        if following is None or following[1] > ends_on:
            last = (start, end)
    return last


def _last_periods_of_service(client_service, *, client=None, context=None) -> set[tuple]:
    """آخرُ فترةٍ في **كل سلسلة** (دورية الخدمة، ولكلِّ سطرٍ ثابت) للخدمة.

    تُقرأ من `_streams_for_service` نفسها التي يقرؤها المحرّك — فلا نسخةً ثانية
    من توليد الفترات. وتُرجع مجموعةً من `(البداية, النهاية)` لأن المقارنةَ
    بالفترة لا بمصدرها: سطران بدوريةٍ واحدةٍ فترتُهما واحدة.
    """
    ends_on = client_service.ends_on
    if ends_on is None:
        return set()
    client = client_service.client if client is None else client
    # سياقُ الطلب يُمرَّر من `refresh_office` (زبائنُه كلُّهم) وإلا بُني لزبونٍ واحد.
    context = context or calendar_context(client.tenant, [client])
    system = context.setting(client, TAX_SYSTEM_KEY)
    if not system:
        return set()
    streams = _streams_for_service(
        client_service,
        client_service.service.code,
        list(client_service.frequencies.all()),
        system=system,
        floor=max(client_service.starts_on, client_service.responsible_from),
        end=ends_on,
        context=context,
    )
    lasts: set[tuple] = set()
    for periods in streams.values():
        last = last_period_of_stream(
            [(start, end) for start, end, _cadence in periods], ends_on=ends_on,
        )
        if last is not None:
            lasts.add(last)
    return lasts


def _close_pending_last_periods(client_service) -> int:
    """كلُّ التزامٍ منتظرٍ لآخر فترةٍ ⇒ «مش لازم هالفترة» — **لا حذف**.

    الصفُّ يبقى بتاريخه ومن حُوِّل إليه، والحالةُ وحدها تتغيّر — فسؤالُ «لماذا لم
    نقدّم آذار؟» له جوابٌ في الشاشة بدل أن يختفي الصفُّ بصمت.
    """
    periods = _last_periods_of_service(client_service)
    if not periods:
        return 0
    condition = Q()
    for period_start, period_end in periods:
        condition |= Q(period_start=period_start, period_end=period_end)
    return client_service.obligations.filter(
        condition, status=OBLIGATION_STATUS_PENDING,
    ).update(
        status=OBLIGATION_STATUS_NOT_REQUIRED, updated_at=timezone.now(),
    )


def _obligation_defaults(
    tenant, client, *, task, result, origin, name, rule=None, custom_rule=None,
    event=None,
) -> dict:
    """حقولُ `Obligation` المشتقّة من نتيجة المحرّك — **موضعُها الوحيد**.

    يقرؤها التوليدُ الدوريّ والحدثُ معاً، فلا نسختان تفترقان عند أول حقلٍ يُضاف
    إلى الالتزام. و`tenant` يُمرَّر صريحاً: الزبونُ يُحمَّل بلا `tenant` في مسح
    التحديث، وقراءتُه من الصفّ استعلامٌ لكل زبون.
    """
    return {
        "tenant": tenant,
        "client": client,
        "task": task,
        "rule": rule,
        "custom_rule": custom_rule,
        "event": event,
        "origin": origin,
        "name": name,
        "period_start": result.period_start,
        "legal_date": result.legal_date,
        "official_date": result.official_date,
        "actual_deadline": result.actual_deadline,
        "internal_deadline": result.internal_deadline,
        "platform_official_date": result.platform_official_date,
        "estimated": result.estimated,
        "postponed": result.postponed,
        "warnings": list(result.warnings),
    }


def _refresh_client(client, *, tenant, day, end, context, skip):
    """زبونٌ واحد: يحفظ شغلاته والتزاماتِه وقائمةَ أوراقه — الثلاثةَ جديدةً.

    **القائمُ يُقرأ استعلامين لا بنداً بنداً**: شغلاتُ خدمات الزبون في قاموسٍ
    بمفتاح `(client_service, period_start, period_end)`، والتزاماتُها في مجموعة
    مفاتيح `(client_service, rule_code, period_end)`. فالكلفةُ لا تكبر بتاريخ
    الزبون: مكتبٌ بسنتين تاريخ لا يدفع آلافَ الاستعلامات في خيط الطلب. والبندُ
    الغائب وحده يُنشأ بـ`get_or_create` (حمايةً من تشغيلين متزامنين) ثم يُضاف إلى
    القاموس/المجموعة فوراً فلا يُقرأ مرّتين في المسحة نفسها.

    **وأوراقُ الفترة (#278) تُولَّد في المعاملة نفسها** بعد الالتزامات
    (`_generate_document_rows`): القائمةُ نتيجةُ الحفظ نفسِه، فلا مسارَ ثانٍ لها.

    معاملةُ النداء في `refresh_office` (واحدةٌ لكل زبون). و`skip` فتراتُ
    الخدمات التي رُفع عنها «آخر فترة علينا».
    """
    service_rows = client_services_of(client, context)
    if not service_rows:
        return 0, 0, 0
    floor = min(
        min(row.starts_on for row in service_rows),
        min(row.responsible_from for row in service_rows),
    )
    service_ids = [row.pk for row in service_rows]
    known_tasks = {
        (row.client_service_id, row.period_start, row.period_end): row
        for row in PeriodTask.objects.filter(client_service_id__in=service_ids)
    }
    known_obligations = set(
        Obligation.objects
        .filter(client_service_id__in=service_ids)
        .values_list("client_service_id", "rule_code", "period_end"),
    )
    created_tasks = 0
    created_obligations = 0
    for item in _deadline_items(client, floor=floor, end=end, context=context):
        result = item.result
        client_service = item.client_service
        # **ما حان وقتُه = فترةٌ انتهت قبل اليوم**: تقريرُ كانون الثاني يظهر في
        # 1 شباط لا في 31 كانون الثاني، والفترةُ التي تحتوي اليوم لم تنتهِ بعد.
        if result.period_end >= day:
            continue
        # زبونٌ منتهٍ: لا فترةَ تنتهي بعد تاريخ إنهائه — ما انقضى قبلها يبقى.
        if client.ended_on is not None and result.period_end > client.ended_on:
            continue
        if (result.period_start, result.period_end) in skip.get(client_service.pk, ()):
            continue
        task_key = (client_service.pk, result.period_start, result.period_end)
        task = known_tasks.get(task_key)
        if task is None:
            task, task_created = PeriodTask.objects.get_or_create(
                client_service=client_service,
                period_start=result.period_start,
                period_end=result.period_end,
                defaults={
                    "tenant": tenant,
                    "client": client,
                    "internal_deadline": result.internal_deadline,
                },
            )
            known_tasks[task_key] = task
            if task_created:
                created_tasks += 1
        obligation_key = (client_service.pk, item.code, result.period_end)
        if obligation_key in known_obligations:
            # **صفٌّ قائمٌ لا يُحدَّث**: تواريخُه ما رآه الموظف، وتصحيحُها تذكرة.
            continue
        _obligation, obligation_created = Obligation.objects.get_or_create(
            client_service=client_service,
            rule_code=item.code,
            period_end=result.period_end,
            defaults=_obligation_defaults(
                tenant, client,
                task=task,
                result=result,
                origin=item.origin,
                name=item.name,
                # الالتزامُ يشير إلى **نسخة اللائحة الفعلية** التي حُسب عليها،
                # فلا يصير يتيماً حين تُنشر نسخةُ سنةٍ أعلى. والتزامُ المكتب
                # يشير إلى قاعدته هو (`custom_rule`) ويبقى `rule` فارغاً.
                rule=item.rule,
                custom_rule=item.custom_rule,
            ),
        )
        known_obligations.add(obligation_key)
        if not obligation_created:
            continue
        created_obligations += 1
        # الموعدُ الداخليُّ للشغلة **أبكرُ** التزاماتها: ينخفض إن انضمّ أبكر،
        # ولا يتأخّر أبداً بعد أن رآه الموظف.
        if result.internal_deadline < task.internal_deadline:
            task.internal_deadline = result.internal_deadline
            task.save(update_fields=["internal_deadline"])
    created_documents = _generate_document_rows(
        client, tenant=tenant, service_rows=service_rows, end=end,
        context=context, skip=skip,
    )
    return created_tasks, created_obligations, created_documents


# ── التنبيهات الداخلية (#276) ───────────────────────────────────────────────
#
# **التنبيهُ يُولَّد داخل «حدّث المكتب» لا بساعة**: `ensure_office_refreshed` تعمل
# مرّةً في اليوم، فالمستحقُّ الجديد يأخذ تنبيهَه مرّةً، والمرجعُ الذي نُبِّه عليه
# سابقاً لا يتكرّر — الفرادةُ في القاعدة تحرس ذلك ولو نُودِي التوليد مرّتين.

#: إعدادا المستلِمين — مستوى المكتب وحده، ويُقرآن مرّةً لكل توليد.
LATE_INTERNAL_ALERT_KEY = "late_internal_alert_to"
LATE_OFFICIAL_ALERT_KEY = "late_official_alert_to"


def _office_owner_ids(tenant) -> set[int]:
    """أعضاءُ المكتب النشطون بدور «صاحب المكتب» — التعريفُ القائم نفسه."""
    return set(
        UserCompanyMembership.objects
        .filter(tenant=tenant, role=MANAGER_ROLE, user__is_active=True)
        .values_list("user_id", flat=True),
    )


def _alert_recipient_ids(choice, *, assignee_id, owners) -> set[int]:
    """مستلِمو تنبيهٍ واحد من قيمة الإعداد — **مجموعةٌ فلا تكرار**.

    «المسؤول» = `effective_assignee`، وإن غاب (زبونٌ بلا مسؤول) ذهب لصاحب المكتب
    بدلاً منه: تنبيهٌ لا يبلغ أحداً أسوأ من تنبيهٍ يبلغ رئيسَ المكتب. ومستلِمٌ هو
    المسؤولُ وصاحبُ المكتب معاً يأخذ تنبيهاً واحداً.
    """
    owner_ids = set(owners)
    responsible = {assignee_id} if assignee_id else set(owner_ids)
    if choice == settings_registry.ALERT_TO_OWNER:
        return owner_ids
    if choice == settings_registry.ALERT_TO_ASSIGNEE_OWNER:
        return responsible | owner_ids
    return responsible


def _new_alert_rows(
    *, tenant, kind, ref_key, recipients, message, day,
    client, task, obligation, existing,
) -> list[OfficeAlert]:
    """صفوفُ التنبيه غير الموجودة — والمفاتيحُ القائمة تُمرَّر مجموعةً واحدةً.

    `existing` مجموعةُ `(recipient_id, kind, ref_key)` المقروءة باستعلامٍ واحد
    لمراجع المرشّحين وحدها (`ref_key__in`) لا لتنبيهات المكتب كلّها، ويُضاف إليها
    المرشّحُ فور قبوله فلا يُكرَّر داخل النداء نفسه.
    """
    rows = []
    for recipient_id in sorted(recipients):
        key = (recipient_id, kind, ref_key)
        if key in existing:
            continue
        existing.add(key)
        rows.append(OfficeAlert(
            tenant=tenant,
            recipient_id=recipient_id,
            kind=kind,
            ref_key=ref_key,
            client=client,
            task=task,
            obligation=obligation,
            message=message,
            day=day,
        ))
    return rows


def _generate_late_alerts(tenant, *, day) -> int:
    """يولّد تنبيهات التأخير ليومٍ صريح ويُرجع **ما أنشأه هذا النداء**.

    - كلُّ التزامٍ `pending` و`due_date < day` ⇒ «التزام تجاوز موعده الرسمي ولم
      يُقدَّم» لمستلِمي `late_official_alert_to`. و`due_date` هو
      `extended_to or actual_deadline` (#277): التمديدُ يُسكِت الأحمرَ إلى موعده.
    - كلُّ شغلةٍ فيها التزامٌ منتظرٌ و`internal_deadline < day` ⇒ «شغلة تجاوزت
      موعدها الداخلي» لمستلِمي `late_internal_alert_to` — وشغلةٌ صار التزامُها
      أحمرَ تأخذ الأحمرَ أيضاً (مرجعان مختلفان، والفرادةُ تمنع التكرار).

    **والكلفةُ ثابتة**: الإعدادُ يُقرأ مرّةً للمكتب، والمستلِمون استعلامٌ واحد،
    والمفاتيحُ القائمة استعلامٌ واحدٌ محصورٌ بمراجع المرشّحين (`ref_key__in`) لا
    بتاريخ المكتب كلِّه، ثم `bulk_create(ignore_conflicts=True)` دفعةً — فلا
    استعلامَ لكل التزام. والإعداداتُ تُقرأ **بلا زبونٍ ولا شغلة** (مستوى المكتب
    وحده)، والمسؤولُ من `effective_assignee` وحدها.
    """
    internal_to = resolve_setting(tenant, LATE_INTERNAL_ALERT_KEY)
    official_to = resolve_setting(tenant, LATE_OFFICIAL_ALERT_KEY)
    owners = _office_owner_ids(tenant)
    candidates = list(
        Obligation.objects
        .filter(tenant=tenant, status=OBLIGATION_STATUS_PENDING)
        # المتأخّرُ وحده يُحمَّل: الرسميُّ (أو الممدَّد) أو شغلتُه الداخليّ — والقصُّ
        # في SQL لا في بايثون، فمكتبٌ بآلاف الالتزامات المنتظِرة لا يُحمَّل كلُّها
        # كلَّ يوم. والتعبيرُ هو `due_date` نفسُه: الممدَّدُ يُقارَن بتمدیده.
        .filter(
            Q(extended_to__isnull=True, actual_deadline__lt=day)
            | Q(extended_to__lt=day)
            | Q(task__internal_deadline__lt=day),
        )
        .select_related(
            "client",
            "client__responsible",
            "task",
            "task__assignee",
            "task__client__responsible",
            "task__client_service__service",
        )
    )
    # المفاتيحُ القائمة لهذه المراجع وحدها — لا تاريخُ المكتب كلِّه: المراجعُ
    # التي سيُحاول النداءُ كتابتها (المنتظِرةُ المتأخّرة وشغلاتُها المتأخّرة داخلياً)،
    # والقراءةُ استعلامٌ واحد.
    ref_keys = {
        f"obligation:{obligation.pk}"
        for obligation in candidates
        if obligation.due_date < day
    }
    ref_keys |= {
        f"task:{obligation.task_id}"
        for obligation in candidates
        if obligation.task.internal_deadline < day
    }
    existing = set(
        OfficeAlert.objects
        .filter(tenant=tenant, ref_key__in=ref_keys)
        .values_list("recipient_id", "kind", "ref_key"),
    ) if ref_keys else set()
    rows: list[OfficeAlert] = []
    counted_tasks: set[int] = set()
    for obligation in candidates:
        task = obligation.task
        client = obligation.client
        assignee = task.effective_assignee
        assignee_id = getattr(assignee, "pk", None)
        if obligation.due_date < day:
            rows.extend(_new_alert_rows(
                tenant=tenant,
                kind=OFFICE_ALERT_KIND_OBLIGATION_LATE,
                ref_key=f"obligation:{obligation.pk}",
                recipients=_alert_recipient_ids(
                    official_to, assignee_id=assignee_id, owners=owners,
                ),
                message=(
                    f"{client.name} — {obligation.name} "
                    f"({deadlines.period_label(obligation.period_start, obligation.period_end)})"
                ),
                day=day,
                client=client,
                task=task,
                obligation=obligation,
                existing=existing,
            ))
        if task.internal_deadline >= day or task.pk in counted_tasks:
            continue
        counted_tasks.add(task.pk)
        rows.extend(_new_alert_rows(
            tenant=tenant,
            kind=OFFICE_ALERT_KIND_TASK_LATE_INTERNAL,
            ref_key=f"task:{task.pk}",
            recipients=_alert_recipient_ids(
                internal_to, assignee_id=assignee_id, owners=owners,
            ),
            message=(
                f"{client.name} — {task.client_service.service.name} "
                f"({deadlines.period_label(task.period_start, task.period_end)})"
            ),
            day=day,
            client=client,
            task=task,
            obligation=None,
            existing=existing,
        ))
    if not rows:
        return 0
    OfficeAlert.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def _save_due_for_clients(tenant, clients, *, day, context) -> tuple[int, int, int]:
    """يحفظ المستحقَّ لكل زبونٍ في معاملته — `(شغلات, التزامات, أوراق)` جديدة.

    **موضعُ الحفظ الوحيد**: يقرؤه `refresh_office` لكل زبائن المكتب، ويقرؤه
    إنشاءُ قاعدة المكتب لزبائن خدمتها وحدهم (#277) — فلا مسارَ ثانٍ للتوليد.
    """
    end = day - timedelta(days=1)
    created_tasks = 0
    created_obligations = 0
    created_documents = 0
    for client in clients:
        skip = {
            row.pk: _last_periods_of_service(row, client=client, context=context)
            for row in client_services_of(client, context)
            if not row.last_period_ours and row.ends_on is not None
        }
        with transaction.atomic():
            tasks, obligations, documents = _refresh_client(
                client, tenant=tenant, day=day, end=end, context=context, skip=skip,
            )
        created_tasks += tasks
        created_obligations += obligations
        created_documents += documents
    return created_tasks, created_obligations, created_documents


def refresh_office(tenant, *, day) -> dict:
    """«حدّث المكتب ليوم X» — يحفظ ما حان وقته، **idempotent وبلا ساعة**.

    **ما حان وقتُه**: كلُّ التزامٍ انتهت فترتُه قبل `day` (`period_end < day`) —
    فق.م كانون الثاني تظهر في 1 شباط ولا تظهر في 31 كانون الثاني.

    **والأرضيةُ `max(starts_on, responsible_from)` بلا سقف 24 شهراً**: تشغيلٌ
    متأخّرٌ يلحق كلَّ ما فات، وزبونٌ جديدٌ بفترةٍ ماضيةٍ تُولَّد كلُّ فتراتها.
    والتقويمُ يقرأ المولّدَ نفسه بسقفه — **محرّكٌ واحد**.

    **والصفُّ القائم لا يُحدَّث**: `get_or_create` للشغلة بـ`(client_service,
    period_start, period_end)` وللالتزام بـ`(client_service, rule_code,
    period_end)`. فتشغيلُ اليوم نفسه مرّتين لا يكتب صفّاً، وتشغيلُ يومٍ لاحقٍ
    يضيف الجديد فقط. **ومعاملةٌ لكل زبون**: مكتبٌ بألف زبون لا يُحبَس في واحدة.

    **وقبل حفظ الجديد** يُطبَّق تحديثُ المنصة (#277): كلُّ التزامٍ غيرِ مقدَّمٍ
    يشير إلى نسخةِ لائحةٍ لم تبقَ ساريةً ينتقل إلى سطر الكود نفسه في النسخة
    السارية ويُعاد حسابه بالدالّة الواحدة — والمقدَّمُ لا يُمسّ، وسطرٌ غاب من
    الجديد يُضاف إلى `warnings` وحده.

    ويُسجَّل `OfficeRefreshRun` لليوم (`get_or_create`)، فالسجلُّ صفٌّ واحدٌ لكل
    (مكتب، يوم) وعدّادُه ما أنشأه أوّلُ تشغيل. ويُرجع ما أنشأه **هذا** النداء:
    صفراً في اليوم نفسه، والجديدَ في يومٍ لاحق.

    **ومعه — لا في مسارٍ ثانٍ (#290)** — يُزامَن التزامُ المكتب نفسه من لائحته
    الثابتة (`self_obligations.sync_self_obligations`)، ويُولَّد تذكيرُ نسخة
    البيانات الشهريُّ إن كان إعدادُه مفعّلاً. كلاهما مفتاحُه الطبيعيُّ يمنع
    التكرار، فلا يخرج هذا النداء عن كونه idempotent.
    """
    clients = list(
        OfficeClient.objects
        .filter(tenant=tenant)
        .select_related("tax_card", "responsible")
        .prefetch_related("services__service", "services__frequencies")
        .order_by("id"),
    )
    context = calendar_context(tenant, clients)
    # **قبل حفظ الجديد**: الالتزامُ غيرُ المقدَّم يلحق نسخةَ المنصة السارية (#277)،
    # فلا يبقى صفٌّ محفوظٌ على نسخةٍ سُحبت. وما تغيّر تاريخُه يُبنى عليه تنبيهُ
    # «تغيّر موعد N التزامات».
    with transaction.atomic():
        schedule_changes = _apply_platform_updates(tenant, day=day, context=context)
    created_tasks, created_obligations, created_documents = _save_due_for_clients(
        tenant, clients, day=day, context=context,
    )

    OfficeRefreshRun.objects.get_or_create(
        tenant=tenant, day=day, defaults={"created_obligations": created_obligations},
    )
    # التنبيهاتُ بعد حفظ الالتزامات: تقرأ ما صار محفوظاً في هذا النداء أيضاً.
    created_alerts = _generate_late_alerts(tenant, day=day)
    created_alerts += _generate_schedule_alerts(
        tenant, day=day, context=context, schedule_changes=schedule_changes,
    )
    # #280: تصعيدُ التذكير بعد الحدّ — يُقرأ من السجلّ المحفوظ، فيأتي بعد التنبيهات.
    created_alerts += _generate_reminder_alerts(tenant, day=day)
    # #282: مسودّاتُ الأتعاب لدورة الشهر نفسه — فرادةُ `(زبون، سنة، شهر)` تجعلها
    # مسودّةً واحدةً مهما تكرّر التشغيل، وتنبيهُ «مرّ عليها ثلاثة أيام» يُولَّد
    # هنا لأن لا ساعةَ في الموديول.
    fee_drafts = _generate_fee_drafts(tenant, day=day)
    created_alerts += fee_drafts["created_alerts"]
    # #290: **التزامُ المكتب نفسه** — لائحتُه في الكود، والتوليدُ `get_or_create`
    # على (مكتب، قاعدة، فترة). ولا يمسّ التزامات الزبائن ولا عدّاداتها بشيء.
    created_self_obligations = _sync_self_obligations(tenant, day=day)
    # #290: تذكيرُ نسخة البيانات — تنبيهٌ واحدٌ في الشهر لأصحاب المكتب، تقرؤه
    # الشاشةُ من هذا النوع وتُسكِته نقطةُ التصدير الكامل.
    created_alerts += _generate_data_export_reminders(tenant, day=day)
    return {
        "day": day.isoformat(),
        "created_tasks": created_tasks,
        "created_obligations": created_obligations,
        # #278: أوراقُ الفترات التي صارت مستحقّة — عدّادٌ بجانب عدّاداتها.
        "created_documents": created_documents,
        "created_alerts": created_alerts,
        # #282: عددُ المسودّات التي أنشأها هذا النداء (لا تحديثَ لمعتمدةٍ ولا ملغاة).
        "created_fee_drafts": fee_drafts["created_drafts"],
        # #290: بنودُ التزام المكتب نفسِه التي أُنشئت الآن (واحدٌ في السنة عادةً).
        "created_self_obligations": created_self_obligations,
    }


def ensure_office_refreshed(tenant, *, day):
    """مرّةٌ في اليوم: ليومٍ له سجلٌّ **لا عمل** (تُرجع `None`)، وإلا `refresh_office`.

    تُرجع `None` ليومٍ مسجَّلٍ سابقاً (لا تشغيلَ ولا عدّادات)، وعدّاداتِ
    `refresh_office` (`created_tasks`/`created_obligations`/`created_documents`/
    `created_alerts`/`created_fee_drafts`) ليومٍ جديد — فالمُنادي إن أراد الأرقام
    فليقرأها من قيمتها المُعادة لا من `None`.

    تُنادى عند أول فتحٍ لشاشة «اليوم» **ولجرس التنبيهات** (`GET alerts/`)، فيصير
    أولُ فتحٍ لأيٍّ منهما تشغيلاً يومياً بلا مُجدوِلٍ في المستودع (الـcron على
    الخادم خطوةُ نشر) — والجرسُ لا يعتمد على أن يفتح أحدٌ «اليوم».
    """
    if OfficeRefreshRun.objects.filter(tenant=tenant, day=day).exists():
        return None
    return refresh_office(tenant, day=day)


def _clean_obligation_amount(value):
    """مبلغُ الالتزام: فارغٌ ⇒ `None` (مسح)، وسالبٌ أو أكثر من خانتين ⇒ رفض."""
    if value is None or value == "":
        return None
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"amount": "مبلغٌ غير صالح."}) from None
    if not amount.is_finite() or amount < 0:
        raise ValidationError({"amount": "المبلغ لا يكون سالباً."})
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError({"amount": "المبلغ بخانتين عشريتين على الأكثر."})
    return amount


def _assert_not_submitted(obligation, field="status"):
    """«انقدّم» نهائيٌّ: أيُّ انتقالٍ منه مرفوض — والمبلغُ معه."""
    if obligation.status == OBLIGATION_STATUS_SUBMITTED:
        raise ValidationError({field: SUBMITTED_LOCKED})


def _assert_transition(obligation, allowed, message) -> None:
    """الانتقالُ من حالةٍ واحدةٍ مسموحة: الخروجُ من «انقدّم» برسالته، وغيرُه برسالةٍ تقول الطريق."""
    if obligation.status == OBLIGATION_STATUS_SUBMITTED:
        raise ValidationError({"status": SUBMITTED_LOCKED})
    if obligation.status not in allowed:
        raise ValidationError({"status": message})


def submit_obligation(obligation, *, actor, submitted_on=None, number="") -> Obligation:
    """«انقدّم»: من المنتظِر إلى المُقدَّم، بتاريخ التقديم ومَن قدّمه ورقمه.

    `submitted_on` افتراضُه اليوم، **ولا يكون في المستقبل** — تقديمٌ بتاريخٍ لم
    يأتِ بعد يكذب على السجلّ. والانتقالُ من **المنتظِر وحده**: «مش لازم هالفترة»
    تُرجَّع أوّلاً، و«انقدّم» نهائيٌّ (`SUBMITTED_LOCKED`).
    """
    _assert_transition(
        obligation,
        {OBLIGATION_STATUS_PENDING},
        "«مش لازم هالفترة» — رجّعها أوّلاً ثم قدّم.",
    )
    today = timezone.localdate()
    day = submitted_on or today
    if day > today:
        raise ValidationError({"submitted_on": "تاريخ التقديم لا يكون في المستقبل."})
    obligation.status = OBLIGATION_STATUS_SUBMITTED
    obligation.submitted_on = day
    obligation.submitted_by = actor if getattr(actor, "pk", None) else None
    obligation.submission_number = (number or "").strip()
    obligation.save(update_fields=[
        "status", "submitted_on", "submitted_by", "submission_number", "updated_at",
    ])
    # #287/٥: «انقدّم» يقفل فترةَ الدفتر — إن كان الإعدادُ مفعّلاً وثمّة دفتر.
    # استيرادٌ كسول: `client_books` يستورد هذه الوحدة، فالاستيرادُ أعلى الملفّ دورة.
    from accounting_office import client_books

    client_books.close_period_on_submit(obligation, actor=actor, day=day)
    return obligation


def mark_obligation_not_required(obligation, *, actor) -> Obligation:
    """«مش لازم هالفترة» — من المنتظِر وحده، وتُفتح بـ`reopen_obligation`.

    `actor` في التوقيع توحيداً مع `submit_obligation`: هذان الانتقالان لا يكتبان
    عموداً لمن فعلهما في هذه الشريحة (الحالةُ والتاريخُ يكفيان). والانتقالُ من
    **المنتظِر وحده**: ما عُلِّم سابقاً لا يُعلَّم ثانيةً، و«انقدّم» مرفوض.
    """
    _assert_transition(
        obligation,
        {OBLIGATION_STATUS_PENDING},
        "الالتزامُ معلَّمٌ «مش لازم هالفترة» — «رجّعها» تُعيده منتظراً.",
    )
    obligation.status = OBLIGATION_STATUS_NOT_REQUIRED
    obligation.submitted_on = None
    obligation.submitted_by = None
    obligation.submission_number = ""
    obligation.save(update_fields=[
        "status", "submitted_on", "submitted_by", "submission_number", "updated_at",
    ])
    return obligation


def reopen_obligation(obligation, *, actor) -> Obligation:
    """«رجّعها»: من «مش لازم هالفترة» وحدها إلى المنتظِر — **لا من «انقدّم»**."""
    _assert_transition(
        obligation,
        {OBLIGATION_STATUS_NOT_REQUIRED},
        "«رجّعها» لـ«مش لازم هالفترة» وحدها — والالتزام منتظرٌ أصلاً.",
    )
    obligation.status = OBLIGATION_STATUS_PENDING
    obligation.save(update_fields=["status", "updated_at"])
    return obligation


def set_obligation_amount(obligation, *, amount, direction) -> Obligation:
    """مبلغُ الالتزام واتجاهه — **يُقفل عند «انقدّم»**: ما قُدّم لا يُعاد تسعيره.

    `amount=None` (أو سلسلةٌ فارغة) يمسح المبلغَ والاتجاه معاً، وإلا فالاتجاه
    **مطلوب**: «عليه» أم «إله» — رقمٌ بلا اتجاهٍ لا يُقرأ في كشف.
    """
    _assert_not_submitted(obligation, field="amount")
    clean = _clean_obligation_amount(amount)
    if clean is None:
        obligation.amount = None
        obligation.direction = ""
    else:
        if direction not in dict(OBLIGATION_DIRECTION_CHOICES):
            raise ValidationError({
                "direction": "اتجاه المبلغ مطلوب: «عليه» أو «إله».",
            })
        obligation.amount = clean
        obligation.direction = direction
    obligation.save(update_fields=["amount", "direction", "updated_at"])
    return obligation


def set_obligation_client_paid(obligation, *, paid) -> Obligation:
    """«الزبون دفع» — **في كلّ الحالات**: الدفعُ خبرٌ عن الزبون لا عن التقديم."""
    obligation.client_paid = bool(paid)
    obligation.save(update_fields=["client_paid", "updated_at"])
    return obligation


#: #287/٤: إعدادُ «حساب المبلغ من الدفتر» — فعّالاً يُتاح الحساب، وكلُّ حسابٍ يُخزَّن.
OBLIGATION_FROM_BOOK_KEY = "obligation_amount_from_book"


def _client_book_for(obligation):
    """دفترُ زبون الالتزام — أو 400 برسالته: لا دفترَ فلا حسابَ من لا شيء."""
    from accounting_office.models import ClientBook

    book = ClientBook.objects.filter(client=obligation.client).first()
    if book is None:
        raise ValidationError({
            "client": "لا دفترَ لهذا الزبون — لا مبلغَ يُحسب من دفترٍ غير موجود.",
        })
    return book


def compute_obligation_amount(obligation, *, actor=None, day=None):
    """**المبلغُ المحسوبُ من الدفتر**: ض.ق.م = مبيعات − مدخلاتٍ معترفاً بها.

    ثلاثةُ شروطٍ قبله: الإعدادُ مفعّلٌ للزبون، وله دفتر، والالتزام لم يُقدَّم
    («انقدّم» نهائيٌّ كما في المبلغ اليدويّ). والنتيجةُ تُحفظ في `computed_amount`
    **ولا تلمس `amount`**: التأكيدُ فعلٌ ثانٍ صريح (`confirm_obligation_amount`)،
    فالفرقُ بين ما قاله الدفترُ وما قُدِّم فعلاً يبقى مقروءاً.

    وتُعيد `(الالتزام، تفصيلَ الحساب)` — التفصيلُ يراه الموظف فيؤكّد أو يعدّل:
    تأكيدُ رقمٍ لم يُقرأ تفصيلُه ليس تأكيداً.

    و`المدخلاتُ المعترف بها` تُقرأ من `book_reports.vat_from_book` — لا حسابٌ
    ثانٍ هنا: تقريرُ ض.ق.م ومبلغُ الالتزام يجب أن يقولا الرقمَ نفسه.
    """
    from accounting_office import book_reports

    if not resolve_setting(
        obligation.tenant, OBLIGATION_FROM_BOOK_KEY, client=obligation.client,
    ):
        raise ValidationError({
            "amount": (
                "«حساب مبلغ الالتزام من الدفتر» غير مفعّل لهذا الزبون — "
                "فعّله من إعدادات المكتب، أو اكتب المبلغ يدوياً."
            ),
        })
    _assert_not_submitted(obligation, field="amount")
    book = _client_book_for(obligation)
    computed = book_reports.vat_from_book(
        book,
        period_start=obligation.period_start,
        period_end=obligation.period_end,
    )
    obligation.computed_amount = Decimal(computed["vat_due"])
    obligation.save(update_fields=["computed_amount", "updated_at"])
    return obligation, computed


def confirm_obligation_amount(obligation, *, actor=None) -> Obligation:
    """**تأكيدُ الموظف**: المحسوبُ يصير المبلغَ المعدَّل — والاثنان يبقيان.

    الاتجاهُ من إشارة المحسوب: موجبٌ «عليه» وسالبٌ «إله» (كإشعار الدفع)، والصفرُ
    يُقبل مبلغاً صفرياً بلا اتجاه — التزامٌ صفريٌّ نتيجةٌ صحيحة، لا فراغ.
    """
    _assert_not_submitted(obligation, field="amount")
    if obligation.computed_amount is None:
        raise ValidationError({
            "amount": "لا مبلغَ محسوباً بعد — احسبه من الدفتر أوّلاً.",
        })
    amount = obligation.computed_amount
    obligation.amount = abs(amount)
    if amount > 0:
        obligation.direction = OBLIGATION_DIRECTION_DUE
    elif amount < 0:
        obligation.direction = OBLIGATION_DIRECTION_REFUND
    else:
        obligation.direction = ""
    obligation.save(update_fields=["amount", "direction", "updated_at"])
    return obligation


def close_prior_obligations(client, *, before, actor) -> int:
    """«هدول انقدّموا قبل ما يجي علينا» — تُسكِت المنتظِرَ الذي سبق تاريخاً.

    كلُّ التزامٍ **منتظر** فترتُه تنتهي قبل `before` يصير مُقدَّماً مع
    `prior_to_office=True`، **بلا تاريخ تقديمٍ ولا رقم**: لم يُقدَّم من المكتب
    بل وجدناه مقدَّماً. وما ليس منتظراً (أُرسل أو «مش لازم») لا يُمسّ.
    """
    if before is None:
        raise ValidationError({"before": "تاريخ الحدّ مطلوب."})
    # قاعدةُ `submit_obligation` نفسها: تاريخٌ لم يأتِ بعد لا يُغلق شيئاً.
    if before > timezone.localdate():
        raise ValidationError({"before": "تاريخ «قبل» لا يكون في المستقبل."})
    return client.obligations.filter(
        status=OBLIGATION_STATUS_PENDING, period_end__lt=before,
    ).update(
        status=OBLIGATION_STATUS_SUBMITTED,
        prior_to_office=True,
        submitted_on=None,
        submitted_by=actor if getattr(actor, "pk", None) else None,
        updated_at=timezone.now(),
    )


def assign_task(task, *, assignee) -> PeriodTask:
    """تحويلُ شغلةٍ لعضوٍ آخر — أو `None` للعودة إلى وراثة مسؤول الزبون.

    `assignee` عضوٌ في **نفس المكتب** (`is_tenant_member`)، وإلا كانت الشغلةُ
    تُحال إلى موظّفٍ لا يراه أحد. والوراثةُ لا تحتاج كتابةً، فالـ`None` يمسح
    التحويل ويُعيد القاعدة.
    """
    if assignee is not None and not is_tenant_member(
        task.tenant_id, getattr(assignee, "pk", None),
    ):
        raise ValidationError({
            "assignee": "الموظف المحوَّل إليه الشغلة ليس عضواً في هذا المكتب.",
        })
    task.assignee = assignee
    task.save(update_fields=["assignee"])
    return task


def obligation_direction_choices() -> list[dict]:
    """اتجاهُ المبلغ — **تسمياتُه من الخادم وحده**، فلا جدولَ في الشاشة."""
    return [
        {"value": value, "label": label}
        for value, label in OBLIGATION_DIRECTION_CHOICES
    ]


def _badge_keys(obligation, day, *, task=None) -> list[str]:
    """مفتاحُ الشارة الواحدة المشتقّة — **من الحالة واليوم، ولا عمودَ لها**.

    **درجتان لا واحدة (#276)، والأولوية محسومة:**

    - **أحمر `late`**: منتظرٌ و`due_date < day` — الموعدُ الساري (مع التمديد
      الإلكترونيّ، ومع التمديد اليدويّ إن وُجد #277) تجاوز ولم يُقدَّم.
    - **أصفر `late_internal`**: منتظرٌ و`internal_deadline` لشغلتِه قبل اليوم،
      وليس أحمر — الموعدُ الداخليُّ هو ما يراه الموظف قبل الرسميّ.
    - **`near`**: منتظرٌ وموعدُه الساريّ من اليوم إلى ستة أيامٍ بعده، ودونهما.

    وشارةٌ **واحدةٌ على الأكثر** لكل صفّ: الأحمرُ يسبق الأصفر، والأصفرُ يسبق
    «قريب» — فصفٌّ تجاوز داخليُّه لا يقول «قريب هالأسبوع» أيضاً. والمُقدَّمُ
    والمُستثنى بلا شارة: ما انتهى أمرُه لا يُنبَّه عليه.
    """
    if obligation.status != OBLIGATION_STATUS_PENDING:
        return []
    due = obligation.due_date
    if due < day:
        return [OBLIGATION_BADGE_LATE]
    task = obligation.task if task is None else task
    if task.internal_deadline < day:
        return [OBLIGATION_BADGE_LATE_INTERNAL]
    if 0 <= (due - day).days <= NEAR_WINDOW_DAYS:
        return [OBLIGATION_BADGE_NEAR]
    return []


def _badge_payloads(obligation, day, *, keys=None, task=None) -> list[dict]:
    """شاراتُ السطر — و`keys` يُمرَّر حين حُسبت مرّةً في الحمولة (لا تُعاد)."""
    return [
        {"key": key, "label": OBLIGATION_BADGE_LABELS[key]}
        for key in (_badge_keys(obligation, day, task=task) if keys is None else keys)
    ]


def _assignee_payload(assignee):
    if assignee is None:
        return None
    return {"id": assignee.pk, "name": user_display_name(assignee)}


def _obligation_row(
    obligation, *, day, client, task, masked, badge_keys=None, docs=None,
) -> dict:
    """سطرُ التزامٍ — **الزبونُ والشغلةُ يُمرَّران محمَّلين** (لا استعلامَ لكل صفّ).

    **و«ناقصه أوراق» (#278) شارةٌ إضافية**: تُضاف إلى مفاتيح التأخير المحسوبة ولا
    تُزاحمها — `docs` يمرّرها المنادي محسوبةً لصفوف الطلب كلها (استعلامان)،
    ونداءُ الصفّ الواحد يحسبها لنفسه (`obligation_row`). و`badge_keys` مفاتيحُ
    التأخير التي حسبها المنادي مرّةً في مسحته فلا تُعاد للصفّ.
    """
    amount = None if obligation.amount is None else f"{obligation.amount:.2f}"
    # #287/٤: المحسوبُ من الدفتر يُعرض إلى جانب المعدَّل — مفتاحُ مبلغٍ مسجَّل
    # فيمرّ بالقناع، وصفرُه `"0.00"` لا `None`: «حُسب فكان صفراً» خبرٌ آخر عن
    # «لم يُحسب بعد».
    computed = (
        None if obligation.computed_amount is None
        else f"{obligation.computed_amount:.2f}"
    )
    keys = list(
        _badge_keys(obligation, day, task=task) if badge_keys is None else badge_keys,
    )
    if (docs or {}).get("missing") and OBLIGATION_BADGE_MISSING_DOCS not in keys:
        keys.append(OBLIGATION_BADGE_MISSING_DOCS)
    # الشكلُ المنشور `{"received", "required"}` وحده — و`missing` قرارُ شارةٍ
    # داخليّ لا يُرسَل، فالواجهةُ تقرأ العدّاد ولا تعيد الحكم.
    docs_payload = (
        None if docs is None
        else {
            "received": docs.get("received", 0),
            "required": docs.get("required", 0),
        }
    )
    row = {
        "id": obligation.pk,
        "client": {"id": client.pk, "name": client.name},
        "task": {
            "id": task.pk,
            "internal_deadline": task.internal_deadline.isoformat(),
            "assignee": _assignee_payload(task.effective_assignee),
        },
        "name": obligation.name,
        "rule_code": obligation.rule_code,
        "origin": obligation.origin,
        "origin_label": OBLIGATION_ORIGIN_LABELS.get(obligation.origin, ""),
        "period_label": deadlines.period_label(
            obligation.period_start, obligation.period_end,
        ),
        "official_date": obligation.official_date.isoformat(),
        "actual_deadline": obligation.actual_deadline.isoformat(),
        "internal_deadline": obligation.internal_deadline.isoformat(),
        # #277: الموعدُ الساري (الممدَّد أو الفعليّ) وتاريخُ المنصة حين اختلف.
        "due_date": obligation.due_date.isoformat(),
        "extended_to": (
            None if obligation.extended_to is None
            else obligation.extended_to.isoformat()
        ),
        "extension_note": obligation.extension_note,
        "platform_official_date": (
            None if obligation.platform_official_date is None
            else obligation.platform_official_date.isoformat()
        ),
        "estimated": obligation.estimated,
        "warnings": list(obligation.warnings or []),
        "badges": _badge_payloads(obligation, day, keys=keys, task=task),
        # #278: `وصل n / م` — `null` حين لا صفَّ ورقةٍ محسوباً لهذا الالتزام.
        "docs": docs_payload,
        "amount": amount,
        "computed_amount": computed,
        "direction": obligation.direction,
        "direction_label": OBLIGATION_DIRECTION_LABELS.get(obligation.direction, ""),
        "client_paid": obligation.client_paid,
        "status": obligation.status,
        "status_label": OBLIGATION_STATUS_LABELS.get(obligation.status, ""),
    }
    return mask_amounts(row, OBLIGATION_AMOUNT_KEYS) if masked else row


def obligation_row(obligation, *, day, masked=False) -> dict:
    """سطرُ التزامٍ واحد — بردٍّ من فعلٍ بعد حفظه، أو لنداءٍ داخليّ.

    **والمبلغُ يمرّ بالقناع**: `amount` مفتاحُ مبلغٍ مسجَّل، ومن لا يملك رؤية
    المبالغ يصله `None` وتعرض الشاشة «—». وتقدّمُ الأوراق يُحسب لهذا الصفّ وحده.
    """
    return _obligation_row(
        obligation,
        day=day,
        client=obligation.client,
        task=obligation.task,
        masked=masked,
        docs=document_progress(obligation.tenant, [obligation]).get(obligation.pk),
    )


def task_row(task, *, obligations=None) -> dict:
    """سطرُ شغلةٍ — باسِم خدمتها (شغلتا «كانون الثاني» لق.م وللرواتب لا تُميَّزان
    بغيره) وموعدها الداخليّ ومسؤولها الفعليّ. والعلاقةُ تُحمَّل في الاستعلام."""
    row = {
        "id": task.pk,
        "service": {
            "id": task.client_service.service_id,
            "name": task.client_service.service.name,
        },
        "period_start": task.period_start.isoformat(),
        "period_end": task.period_end.isoformat(),
        "period_label": deadlines.period_label(task.period_start, task.period_end),
        "internal_deadline": task.internal_deadline.isoformat(),
        "assignee": _assignee_payload(task.effective_assignee),
    }
    if obligations is not None:
        row["obligations"] = obligations
    return row


def _visible_pending_obligations(tenant, user):
    """الميلُ المنتظِرُ الذي يراه العضو — **قراءةٌ واحدة لا تكبر بعدد الصفوف**.

    الزبائنُ من `visible_clients` وحدها، والعلاقاتُ المطلوبة للصفّ كلِّه
    select_related: الزبونُ ومسؤولُه (للمسؤول الفعليّ)، والشغلةُ ومن حُوِّلت له.
    """
    return (
        Obligation.objects
        .filter(
            client__in=visible_clients(tenant, user).values("pk"),
            status=OBLIGATION_STATUS_PENDING,
        )
        .select_related(
            "client__responsible",
            "task",
            "task__assignee",
            "task__client__responsible",
        )
        .order_by(
            # #277: الترتيبُ بالموعد الساري — الممدَّدُ إلى أيار لا يتصدّر صفَّ
            # اليوم على أنه متأخّر.
            Coalesce("extended_to", "actual_deadline"),
            "internal_deadline",
            "client__name",
        )
    )


def _in_near_window(obligation, day) -> bool:
    """هل يقع الموعدُ الساري في نافذة «قريب هالأسبوع»؟ — **مستقلٌّ عن الشارة**.

    عدّادُ `week` وفلترُه يُحسبان بهذا الشرط وحده: صفٌّ صفرتُه «متأخّر داخليّ»
    وموعدُه الفعليُّ داخل النافذة يُعدّ ويظهر تحت `week` — فالشارةُ واحدةٌ
    بالأولوية، والنافذةُ سؤالٌ آخر («ماذا يستحقّ هذا الأسبوع؟»). ولولا ذلك لصار
    «قريب» مستحيلاً للربعيّ (7 أيامٍ داخليّة) والسنويّ (30).

    والموعدُ الساري (`due_date`) هو المقصود: تمديدٌ إلى ما بعد الأسبوع يُخرج
    الصفَّ من النافذة (#277).
    """
    return 0 <= (obligation.due_date - day).days <= NEAR_WINDOW_DAYS


def today_payload(tenant, *, user, day, filter="") -> dict:
    """شاشةُ «اليوم»: صفوفُ المنتظِر مرتَّبةً بالميل، وعدّاداتُه الستّة قبل الفلتر.

    **العدّاداتُ (`late` · `late_internal` · `week` · `missing_docs` ·
    `appointments` · `all`) على كل الميل المحفوظ** ثم يقصّ الفلترُ الصفوفَ وحدها —
    فكبسةُ «متأخّر رسمي» لا تُصفّر «متأخّر داخليّ». و`appointments` (#281) عدّةُ
    مواعيدِ اليوم المحجوزة، وقائمتُها في `appointments` **لا يقصّها الفلتر**: الفلترُ
    للالتزامات، والموعدُ ليس التزاماً. والفلاترُ ستةٌ: `mine` (المسؤولُ الفعليُّ هو
    العضو) · `week` (نافذةُ `due_date` = `extended_to or actual_deadline` مستقلّةً
    عن الشارة) · `late` (الأحمرُ وحده) · `late_internal` (الأصفرُ وحده) ·
    `missing_docs` («ناقصه أوراق» #278)، والفارغُ «الكل»؛ وغيرُها **400**.

    **و`docs` لكل صفّ** (`{"received": n, "required": m}` أو `null`) يُحسب
    لالتزامات الطلب كلّها باستعلامين ثابتين (`document_progress`) — لا صفّاً صفّاً.

    و`day` يُمرَّر صريحاً ولا يُقرأ من الساعة: الشاراتُ تُحسب عنه، فالصفُّ نفسُه
    «قريب» في يومٍ وليس في آخر بلا أن يتغيّر في القاعدة.
    """
    if filter not in TODAY_FILTERS:
        raise ValidationError({"filter": TODAY_FILTER_HINT})
    masked = user is not None and not can_see_amounts(tenant, user)
    tagged = [
        (obligation, _badge_keys(obligation, day, task=obligation.task))
        for obligation in _visible_pending_obligations(tenant, user)
    ]
    # #278: «ناقصه أوراق» — استعلامان لكل الصفحة، تمرّ بهما عدّاداتُها وصفوفُها.
    progress = document_progress(tenant, [row for row, _keys in tagged])
    # #281: «مواعيد اليوم» قرارُ المكتب لا قرارُ فلتر الالتزامات — تُقرأ كاملةً
    # قبل الفلتر كسائر العدّادات، ولا يقصّها `filter` الذي يخصّ صفوفَ الالتزامات.
    appointments_today = _appointments_module().appointments_for_day(tenant, user, day)
    counters = {
        "late": sum(1 for _row, keys in tagged if OBLIGATION_BADGE_LATE in keys),
        "late_internal": sum(
            1 for _row, keys in tagged if OBLIGATION_BADGE_LATE_INTERNAL in keys
        ),
        "week": sum(1 for row, _keys in tagged if _in_near_window(row, day)),
        "missing_docs": sum(
            1 for row, _keys in tagged
            if progress.get(row.pk, {}).get("missing")
        ),
        "appointments": len(appointments_today),
        "all": len(tagged),
    }
    user_id = getattr(user, "pk", None)
    rows = []
    for obligation, keys in tagged:
        docs = progress.get(obligation.pk)
        if filter == "mine" and _effective_assignee_id(obligation) != user_id:
            continue
        if filter == "week" and not _in_near_window(obligation, day):
            continue
        if filter == "late" and OBLIGATION_BADGE_LATE not in keys:
            continue
        if filter == "late_internal" and OBLIGATION_BADGE_LATE_INTERNAL not in keys:
            continue
        if filter == "missing_docs" and not (docs or {}).get("missing"):
            continue
        rows.append(_obligation_row(
            obligation,
            day=day,
            client=obligation.client,
            task=obligation.task,
            masked=masked,
            # المفاتيحُ حُسبت في المسحة أعلاه (عدّاداتاً وفلترةً) فلا تُعاد للصفّ.
            badge_keys=keys,
            docs=docs,
        ))
    return {
        "day": day.isoformat(),
        "filter": filter,
        "counters": counters,
        "rows": rows,
        "appointments": appointments_today,
        "direction_choices": obligation_direction_choices(),
    }


def _effective_assignee_id(obligation):
    """معرّفُ المسؤول الفعليّ للصفّ — بلا استعلامٍ إضافيّ (المسؤولُ محمَّل)."""
    assignee = obligation.task.assignee or obligation.client.responsible
    return getattr(assignee, "pk", None)


#: أنواعُ التنبيه التي **تُسقطها القراءةُ** إذا انحلّ سببُها. نوعٌ جديد لا يُضاف
#: هنا: يُضاف صفّاً في `OFFICE_ALERT_KIND_CHOICES` ويُعرض كما هو (`~Q(kind__in=…)`).
RESOLVED_ALERT_KINDS: tuple[str, ...] = (
    OFFICE_ALERT_KIND_OBLIGATION_LATE,
    OFFICE_ALERT_KIND_TASK_LATE_INTERNAL,
)


def _live_override_alerts_q(tenant):
    """شرطُ بقاء تنبيه «تُبقي تاريخك أم تأخذ الجديد؟» — تعديلٌ ما زال سارياً.

    النوعُ خارج `RESOLVED_ALERT_KINDS` فلا يسقط بالحالة، لكنه يسقط على القراءة إن
    رُجّع التعديلُ أو أُكِّد: `ref_key` يبدأ بـ`"override:<id>:"`، والمُقارَنةُ
    بمجموعة تعديلاتٍ ساريةٍ **مقروءةٍ مرّة** (لا استعلامَ لكل صفّ).
    """
    alive = [
        Q(ref_key__startswith=f"override:{override.pk}:")
        for override in active_rule_overrides(tenant).values()
    ]
    if not alive:
        return Q(pk__in=[])
    condition = alive[0]
    for clause in alive[1:]:
        condition |= clause
    return Q(kind=OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED) & condition


def visible_alerts(tenant, user, day=None):
    """تنبيهاتُ هذا المستخدم وحدها، **المعروضُ له وحده وبلا المحسوم**.

    **والرؤيةُ تتبع الزبون**: تنبيهُ زبونٍ لا يراه العضو لا يُعرض — وإلا بقي
    تنبيهُ زبونٍ حُوِّل لغيره في جرسه بعد أن حُرِم زبونَه. والشرطُ استعلامٌ
    فرعيٌّ واحد على `visible_clients` (مصدرُ الرؤية الوحيد)، فلا N+1؛ وتنبيهٌ بلا
    زبون يبقى ظاهراً لمستلِمه — ونوعا اللائحة (#277) بلا زبونٍ أصلاً.

    وتنبيهُ التزامٍ لا يُعرض إن لم يبقَ الالتزامُ منتظراً **أو صار موعدُه الساريّ
    بعد اليوم** (مُدَّد)، وتنبيهُ شغلةٍ لا يُعرض إن لم يبقَ فيها التزامٌ منتظرٌ —
    بـ`Exists` كذلك. و`day` يُمرَّر صريحاً من الـview (لا ساعةً في الخدمة).

    **وتنبيهُ التذكير (#280)** يُسقطه اكتمالُ أوراق الفترة عند القراءة: يُقرأ
    مراجعُ ما لم يكتمل مجموعةً واحدة، فيسقط الصفُّ بلا كتابةٍ ولا حذف —
    كتنبيه الالتزام الذي يُسقطه التقديم.

    **وتنبيهُ مسودّة الأتعاب (#282)** يُسقطه اعتمادُها أو إلغاؤها بالقراءة نفسها:
    مسودّةٌ اعتُمدت لا تنبيهَ لها، والصفُّ يبقى أثراً لا يُمحى.
    """
    day = day or timezone.localdate()
    pending_obligation = Obligation.objects.filter(
        pk=OuterRef("obligation_id"), status=OBLIGATION_STATUS_PENDING,
    ).filter(Q(extended_to__isnull=True, actual_deadline__lt=day) | Q(extended_to__lt=day))
    pending_task = Obligation.objects.filter(
        task_id=OuterRef("task_id"), status=OBLIGATION_STATUS_PENDING,
    )
    live_reminders = _live_reminder_alert_refs(tenant)
    live_fee_drafts = _live_fee_draft_refs(tenant)
    return (
        OfficeAlert.objects
        .filter(tenant=tenant, recipient=user)
        .filter(
            Q(client__isnull=True)
            | Q(client__in=visible_clients(tenant, user).values("pk")),
        )
        .annotate(
            obligation_pending=Exists(pending_obligation),
            task_pending=Exists(pending_task),
        )
        .filter(
            Q(kind=OFFICE_ALERT_KIND_OBLIGATION_LATE, obligation_pending=True)
            | Q(kind=OFFICE_ALERT_KIND_TASK_LATE_INTERNAL, task_pending=True)
            # نوعُ اللائحة المعدَّلة يُحكم بشرطه وحده — لا بشرط «كل ما لم يُحسَم».
            | _live_override_alerts_q(tenant)
            # ونوعا التذكير ببقاء الأوراق ناقصةٍ في فترتها وحدها.
            | Q(kind__in=REMINDER_ALERT_KINDS, ref_key__in=live_reminders)
            # ومسودّةُ الأتعاب ببقائها غيرَ معتمدةٍ وحدها.
            | Q(
                kind=OFFICE_ALERT_KIND_FEE_DRAFT_PENDING,
                ref_key__in=live_fee_drafts,
            )
            | (
                ~Q(kind__in=RESOLVED_ALERT_KINDS)
                & ~Q(kind=OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED)
                & ~Q(kind__in=REMINDER_ALERT_KINDS)
                & ~Q(kind=OFFICE_ALERT_KIND_FEE_DRAFT_PENDING)
            )
        )
    )


def alert_row(alert) -> dict:
    """سطرُ الجرس — **بلا مبلغ**، و`client` مكانُ الفتح لا سندُ التنبيه.

    و`badge` **مفتاحُ شارة النوع من الخادم** (`OFFICE_ALERT_KIND_BADGES`)، فتُلوَّن
    الشارةُ في الواجهة بلا معرفة أنواعٍ فيها: نوعٌ لاحقٌ يُضاف صفّاً في الخريطة
    ويأخذ محايداً (`""`) حتى يُلوَّن. و`opens` (#277) خريطةُ الوجهة من الخادم
    كذلك: `"client"` أو `"deadline_rules"` أو `"client_documents"` (#280).
    """
    return {
        "id": alert.pk,
        "kind": alert.kind,
        "kind_label": OFFICE_ALERT_KIND_LABELS.get(alert.kind, ""),
        "badge": OFFICE_ALERT_KIND_BADGES.get(alert.kind, ""),
        "opens": OFFICE_ALERT_KIND_OPENS.get(alert.kind, OFFICE_ALERT_DEFAULT_OPENS),
        "message": alert.message,
        "client": (
            None if alert.client is None
            else {"id": alert.client_id, "name": alert.client.name}
        ),
        "task_id": alert.task_id,
        "obligation_id": alert.obligation_id,
        "day": alert.day.isoformat(),
        "seen": alert.seen_at is not None,
        "created_at": alert.created_at.isoformat(),
    }


def alerts_payload(tenant, *, user, day=None, limit=50) -> dict:
    """حمولةُ الجرس: `{"unseen": عددُ غير المرئيّ وغير المحسوم, "rows": [...]}`.

    **تنبيهاتُ هذا المستخدم وحده** (`recipient=user`) الأحدثُ أوّلاً، والمحسومُ
    مستبعَدٌ عند القراءة (`visible_alerts`). و`unseen` يُعدّ على المجموعة كلّها
    لا على الصفحة المعروضة، فالسقفُ لا يكذب على العدّاد. و`day` يومُ القياس
    (يُمرَّر من الـview) فتمديدُ التزامٍ يُسقط تنبيهَه بلا كتابة.
    """
    queryset = visible_alerts(tenant, user, day=day)
    unseen = queryset.filter(seen_at__isnull=True).count()
    rows = [
        alert_row(alert)
        for alert in queryset.select_related("client")[:limit]
    ]
    return {"unseen": unseen, "rows": rows}


def mark_alert_seen(alert, *, user):
    """«شفته» — يُكتب `seen_at` مرّةً، والقراءةُ التالية تُنقص العدّاد.

    تنبيهُ غيرك يُرفض هنا احتياطاً؛ والـAPI يُحلّ الكائن بمستلِمِه فيردّ **404**
    قبل أن يبلغ هذه الدالّة.
    """
    if alert.recipient_id != getattr(user, "pk", None):
        raise ValidationError({"alert": "التنبيهُ ليس لهذا المستخدم."})
    if alert.seen_at is None:
        alert.seen_at = timezone.now()
        alert.save(update_fields=["seen_at"])
    return alert


def mark_all_alerts_seen(tenant, *, user, day=None) -> int:
    """«شفتهم كلهم» — **المعروضُ وحده**: عددُ ما كُتب له `seen_at`.

    يمرّ بـ`visible_alerts` نفسها، فلا يُكتب على تنبيهٍ محسوم: «رجّعها» بعدها
    تُعيد تنبيهاً **غيرَ مقروء** ويُعدّه العدّاد. ولو كُتب على المحسوم لضحك
    العدّادُ على الحال: صفٌّ رجع إلى الجرس وهو «مقروء» بلا أن يراه أحد.
    """
    # المعرّفاتُ تُقرأ أولاً ثم تُكتب: `UPDATE … WHERE id IN (SELECT … FROM` الجدولِ
    # نفسِه يرفضه MySQL (خطأ 1093) ويقبله SQLite — فيمرّ الاختبارُ ويسقط الإنتاج.
    ids = list(
        visible_alerts(tenant, user, day=day)
        .filter(seen_at__isnull=True)
        .values_list("pk", flat=True),
    )
    if not ids:
        return 0
    return OfficeAlert.objects.filter(pk__in=ids).update(seen_at=timezone.now())


def client_obligations_payload(client, *, user, day) -> dict:
    """تبويبُ «الالتزامات والشغلات»: شغلاتُ الزبون **الأحدثَ فترةً أولاً**.

    كلُّ شغلةٍ بموعدها الداخليّ ومسؤولها الفعليّ وبكلِّ التزاماتها **في كلّ
    الحالات** (لا المنتظِرة وحدها: الملفُّ يعرض ما انقدّم وما استُثني أيضاً).
    والمبلغُ يمرّ بالقناع مرّةً واحدةً للحمولة، وتقدّمُ الأوراق يُحسب للزبون
    باستعلامين (#278).
    """
    masked = user is not None and not can_see_amounts(client.tenant, user)
    tasks = list(
        client.tasks
        .select_related("assignee", "client__responsible", "client_service__service")
        .prefetch_related("obligations"),
    )
    obligations = [row for task in tasks for row in task.obligations.all()]
    progress = document_progress(client.tenant, obligations)
    return {
        "client": {"id": client.pk, "name": client.name},
        "day": day.isoformat(),
        "tasks": [
            task_row(task, obligations=[
                _obligation_row(
                    obligation, day=day, client=client, task=task, masked=masked,
                    docs=progress.get(obligation.pk),
                )
                for obligation in task.obligations.all()
            ])
            for task in tasks
        ],
        "direction_choices": obligation_direction_choices(),
    }


# ── تعديل المكتب على اللائحة، والتمديد، والتزامات المكتب، والأحداث (#277) ────
#
# **اللائحةُ بياناتُ منصّةٍ لا تُعدَّل**، وتعديلُ المكتب عليها **صفٌّ إلحاقيّ** في
# `OfficeRuleOverride`: الساري = أحدثُ صفٍّ لكل (مكتب، نظام، كود)، و«رجّع للمنصة»
# صفٌّ `cleared` لا حذف — فالسجلُّ لا يُمحى.
#
# **والحسابُ واحد**: `_deadline_result` هي مدخلاتُ المحرّك الوحيدة، يقرؤها المولّد
# (`_deadline_items`) **وإعادةُ الحساب** (`_recompute_obligations`) معاً — فلا
# نسختان تفترقان عند أول تعديل. وما قُدِّم (`submitted`) لا يدخل إعادةَ الحساب
# أصلاً: «ما قُدِّم لا يغيّره تحديث اللائحة».

#: الحقولُ التي تُعاد كتابتها في الالتزام المحفوظ — ولا `status` ولا مبلغَ ولا لقطةَ
#: اسم. و`rule` معها: تحديثُ المنصة ينقل الصفَّ إلى السطر الجديد فيُكتب معه.
RECOMPUTED_OBLIGATION_FIELDS: tuple[str, ...] = (
    "rule",
    "legal_date",
    "official_date",
    "actual_deadline",
    "internal_deadline",
    "postponed",
    "warnings",
    "platform_official_date",
    "updated_at",
)

#: نصُّ سطرٍ سُحب من النسخة الجديدة — يُضاف إلى `warnings` ولا يغيّر تاريخاً.
PLATFORM_MISSING_LINE_WARNING = "السطر لم يعد في لائحة المنصة — راجع"

#: حدُّ التمديد الإلكترونيّ الذي يقبله تعديلُ المكتب (يوماً).
MAX_OVERRIDE_EXTENSION_DAYS = 60

#: سقفُ أيام سطر الحدث («بعد N يوماً من الحدث») — مدىً لا يومَ شهر. وحدُّه
#: معقوليّةٌ لا تاريخُ قانون: القانونُ في `rule_day` الأصليّ في اللائحة.
MAX_OVERRIDE_EVENT_DAYS = 180


def _override_row(override) -> dict:
    """سطرُ تعديلٍ كما يُعرض ويُسجَّل — و`based_on` لقطةُ المنصة وقت التعديل."""
    return {
        "id": override.pk,
        "tax_system": override.tax_system,
        "rule_code": override.rule_code,
        "rule_day": override.rule_day,
        "rule_month": override.rule_month,
        "electronic_extension_days": override.electronic_extension_days,
        "cleared": override.cleared,
        "note": override.note,
        "based_on": dict(override.based_on or {}),
        "created_by_name": user_display_name(override.created_by),
        "created_at": (
            None if override.created_at is None else override.created_at.isoformat()
        ),
    }


def _latest_platform_rule(tax_system, rule_code):
    """سطرُ الكود في **أحدث نسخةٍ نُشرت** لنظام — مصدرُ اللقطة والتحقّق.

    الترتيبُ بتاريخ النشر لا بالسنة: «النسخة الجديدة» هي آخرُ ما نشرته المنصة لهذا
    السطر، وتصحيحُ 2026 يُنشر بعد لائحة 2027 فيكون هو الأحدث. والسنةُ والنسخةُ
    يكسران التعادل.
    """
    return (
        DeadlineRule.objects
        .filter(schedule__tax_system=tax_system, code=rule_code)
        .select_related("schedule")
        .order_by(
            "-schedule__published_on", "-schedule__year", "-schedule__version",
        )
        .first()
    )


def _override_based_on(rule) -> dict:
    """لقطةُ قيم المنصة وقت التعديل — بها يُقال «المنصة غيّرت موعداً أنت معدّله»."""
    return {
        "rule_kind": rule.rule_kind,
        "rule_day": rule.rule_day,
        "rule_month": rule.rule_month,
        "electronic_extension_days": rule.electronic_extension_days,
        "schedule_id": rule.schedule_id,
    }


def _based_on_matches(based_on, rule) -> bool:
    """هل لقطةُ التعديل تطابق السطرَ الساري؟ — القيمُ التي يعدّلها المكتب وحدها."""
    snapshot = based_on or {}
    return all(
        snapshot.get(field) == getattr(rule, field)
        for field in ("rule_kind", *OFFICE_RULE_OVERRIDE_FIELDS)
    )


def _clean_override_number(value, field, *, minimum, maximum):
    """عددٌ صحيحٌ في حدّيه، أو `None` («كالمنصة») — وإلا رفضٌ بالحقل."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError({field: "عددٌ صحيحٌ مطلوب."})
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "عددٌ صحيحٌ مطلوب."}) from None
    if not minimum <= number <= maximum:
        raise ValidationError({field: f"القيمةُ بين {minimum} و{maximum}."})
    return number


def _dates_snapshot(obligation) -> dict:
    """التواريخُ التي تُكتب في سجلّ التغيّر — نصوصاً ISO فلا تنسيقَ JSON يفترق."""
    snapshot = {
        "legal_date": obligation.legal_date.isoformat(),
        "official_date": obligation.official_date.isoformat(),
        "actual_deadline": obligation.actual_deadline.isoformat(),
        "internal_deadline": obligation.internal_deadline.isoformat(),
        "postponed": obligation.postponed,
        "platform_official_date": (
            None if obligation.platform_official_date is None
            else obligation.platform_official_date.isoformat()
        ),
    }
    if obligation.extended_to is not None:
        snapshot["extended_to"] = obligation.extended_to.isoformat()
    return snapshot


def _stream_obligation_result(
    obligation, *, client_service, context, system, bounds, streams,
):
    """نتيجةُ التزامٍ **دوريّ**: فترتُه من مجاري خدمته، ثم `_deadline_result`.

    مجاري كل خدمةٍ تُحسب مرّةً في النداء (`streams`) بمداها الكامل (`bounds`) —
    فلا استعلامَ لكل التزام. وفترةٌ لم تعد في المجاري (دوريةٌ تبدّلت أو سطرٌ
    سُحب) تُرجع `None`: لا تاريخَ يُخترَع.
    """
    periods = streams.get(client_service.pk)
    if periods is None:
        floor, end = bounds[client_service.pk]
        periods = {
            (start, finish): cadence
            for start, finish, _source, cadence in _periods_for_service(
                client_service,
                client_service.service.code,
                list(client_service.frequencies.all()),
                system=system,
                floor=min(
                    client_service.starts_on, client_service.responsible_from, floor,
                ),
                end=end,
                context=context,
            )
        }
        streams[client_service.pk] = periods
    cadence = periods.get((obligation.period_start, obligation.period_end))
    if cadence is None:
        return None
    return _deadline_result(
        obligation.client,
        rule=obligation.rule,
        custom_rule=obligation.custom_rule,
        override=(
            None if obligation.rule_id is None
            else context.overrides.get((system, obligation.rule_code))
        ),
        period_start=obligation.period_start,
        period_end=obligation.period_end,
        cadence=cadence,
        context=context,
        system=system,
    )


def _recomputed_warnings(obligation, result) -> list:
    """تحذيراتُ الإعادة: ما يحسبه المحرّك، ومعه «السطر لم يعد في اللائحة» إن كان مكتوباً.

    ذلك التحذيرُ يكتبه تحديثُ المنصة لا المحرّك، فالإعادةُ التي تستبدل `warnings`
    بنتيجة المحرّك وحدها كانت تمحوه. وحين ينقل التحديثُ الالتزامَ إلى نسخةٍ فيها
    السطرُ يُسقطه قبل الإعادة (`_apply_platform_updates`) فلا يبقى كاذباً.
    """
    warnings = list(result.warnings)
    if (
        PLATFORM_MISSING_LINE_WARNING in (obligation.warnings or [])
        and PLATFORM_MISSING_LINE_WARNING not in warnings
    ):
        warnings.append(PLATFORM_MISSING_LINE_WARNING)
    return warnings


def _recompute_obligations(obligations, *, context, reason, actor=None):
    """يُعيد حسابَ مواعيد التزاماتٍ محفوظة **بدالّة المحرّك نفسها** — بلا نسخةٍ ثانية.

    كلُّ التزامٍ يُطابَق بفترته في مجاري خدمته (`_periods_for_service`) فتُعرف
    دوريةُ الفترة (وهي ما يحكم أيامَ الإعداد)، ثم يُنادى `_deadline_result` بمدخلات
    المولّد نفسها. وما تغيّر فعلاً يُسجَّل في `ObligationDateChange`، ويُرجع النداءُ
    قائمةَ ما تغيّر وحدها.

    **ودفعةٌ واحدة**: مجاري كل خدمةٍ تُحسب مرّةً، والكتابةُ `bulk_update` واحدة،
    وأبكرُ داخليٍّ لكل شغلةٍ استعلامٌ واحد ثم `bulk_update` ثانٍ — فالكلفةُ لا تكبر
    بعدد الالتزامات. و`submitted` لا يدخل هنا أصلاً.
    """
    processed: list = []
    changed: list = []
    befores: dict[int, dict] = {}
    streams: dict[int, dict[tuple, str]] = {}
    # مدى كل خدمةٍ **من كل التزاماتها** لا من أوّلها: مكتبةٌ تُقرأ بترتيبٍ عشوائيّ
    # كانت تُسقط فتراتٍ لاحقة فتخرج الإعادةُ ناقصة.
    bounds: dict[int, tuple] = {}
    for obligation in obligations:
        service_id = obligation.client_service_id
        floor, end = bounds.get(
            service_id, (obligation.period_start, obligation.period_end),
        )
        bounds[service_id] = (
            min(floor, obligation.period_start),
            max(end, obligation.period_end),
        )
    for obligation in obligations:
        client = obligation.client
        system = context.setting(client, TAX_SYSTEM_KEY)
        if not system:
            continue
        if obligation.origin == OBLIGATION_ORIGIN_EVENT and obligation.event_id:
            # **فترةُ الحدث ليست في أيّ مجرى لائحة**، فتُحسب بالدالّة التي يقرؤها
            # التوليدُ نفسُه — وإلا سقطت الإعادةُ عليها بصمت (#277).
            result = _event_obligation_result(
                client, rule=obligation.rule,
                occurred_on=obligation.period_end,
                context=context, system=system,
            )
        else:
            result = _stream_obligation_result(
                obligation,
                client_service=obligation.client_service,
                context=context,
                system=system,
                bounds=bounds,
                streams=streams,
            )
        if result is None:
            continue
        before = _dates_snapshot(obligation)
        obligation.legal_date = result.legal_date
        obligation.official_date = result.official_date
        obligation.actual_deadline = result.actual_deadline
        obligation.internal_deadline = result.internal_deadline
        obligation.postponed = result.postponed
        obligation.warnings = _recomputed_warnings(obligation, result)
        obligation.platform_official_date = result.platform_official_date
        obligation.updated_at = timezone.now()
        processed.append(obligation)
        if _dates_snapshot(obligation) != before:
            befores[obligation.pk] = before
            changed.append(obligation)
    if processed:
        Obligation.objects.bulk_update(
            list(processed), list(RECOMPUTED_OBLIGATION_FIELDS),
        )
    if changed:
        actor_row = actor if getattr(actor, "pk", None) else None
        ObligationDateChange.objects.bulk_create([
            ObligationDateChange(
                tenant_id=obligation.tenant_id,
                obligation=obligation,
                reason=reason,
                before=befores[obligation.pk],
                after=_dates_snapshot(obligation),
                changed_by=actor_row,
            )
            for obligation in changed
        ])
        _reset_task_internal_deadlines({row.task_id for row in changed})
    return changed


def _reset_task_internal_deadlines(task_ids) -> None:
    """أبكرُ موعدٍ داخليٍّ لالتزامات كل شغلةٍ متغيّرة — استعلامٌ واحد وكتابةٌ واحدة."""
    if not task_ids:
        return
    earliest: dict[int, Any] = {}
    for task_id, internal in (
        Obligation.objects
        .filter(task_id__in=task_ids)
        .values_list("task_id", "internal_deadline")
    ):
        if task_id not in earliest or internal < earliest[task_id]:
            earliest[task_id] = internal
    touched = []
    for task in PeriodTask.objects.filter(pk__in=task_ids):
        earliest_day = earliest.get(task.pk)
        if earliest_day is None or earliest_day == task.internal_deadline:
            continue
        task.internal_deadline = earliest_day
        touched.append(task)
    if touched:
        PeriodTask.objects.bulk_update(touched, ["internal_deadline"])


def _recompute_for_code(tenant, rule_code, *, reason, actor=None, tax_system=None):
    """إعادةُ حساب كل التزامات المكتب **غير المقدَّمة** لكود سطرٍ — لا المقدَّم.

    و`tax_system` يقصرها على التزامات أسطر ذلك النظام: تعديلُ المكتب مفتاحُه
    `(النظام، الكود)`، فلا يمسّ التزاماً بالكود نفسه في النظام الآخر. والتزامُ
    المكتب الخاص (`rule=None`) يُنادى بلا نظام فيبقى داخلاً.
    """
    obligations = Obligation.objects.filter(
        tenant=tenant,
        rule_code=rule_code,
        status__in=(OBLIGATION_STATUS_PENDING, OBLIGATION_STATUS_NOT_REQUIRED),
    )
    if tax_system is not None:
        obligations = obligations.filter(rule__schedule__tax_system=tax_system)
    obligations = list(
        obligations
        .select_related(
            "client",
            "client_service__service",
            "task",
            "rule",
            "custom_rule",
        )
        .prefetch_related("client_service__frequencies")
    )
    if not obligations:
        return []
    context = calendar_context(tenant, [row.client for row in obligations])
    return _recompute_obligations(
        obligations, context=context, reason=reason, actor=actor,
    )


def _assert_tax_system(tax_system) -> str:
    """نظامٌ ضريبيّ معروف — تحقّقٌ واحدٌ لثلاثة أفعالٍ على اللائحة."""
    if tax_system not in dict(TAX_SYSTEM_CHOICES):
        raise ValidationError({"system": "النظام الضريبي غير معروف."})
    return tax_system


def set_rule_override(
    tenant, *, tax_system, rule_code, rule_day=None, rule_month=None,
    electronic_extension_days=None, note="", actor,
) -> dict:
    """**يعدّل المكتب سطرَ اللائحة** على مسؤوليته: صفٌّ جديد، ثم إعادةُ حساب غير المقدَّم.

    المكتبُ يعدّل الأيامَ وحدها: `rule_day`/`rule_month`/`electronic_extension_days`،
    و`None` تعني «كالمنصة». ونوعُ القاعدة (`rule_kind`) يبقى من اللقطة — تغييرُه
    تغييرُ قانونٍ لا تأخيرُ موعد.

    **والملاحظةُ إلزامية**: التعديلُ قرارٌ على مسؤوليّة المكتب، وقرارٌ بلا سببٍ
    مكتوبٍ لا يُفسَّر بعد شهرين — والواجهةُ تطلبه، والخادمُ يرفض غيابه.

    وتحقّقان قبل الكتابة: الكودُ موجودٌ في نسخة المنصة (وإلا كان تعديلاً على لا
    شيء)، والقيمُ في حدودها.

    ويُرجع `{"override": …، "changed_obligations": N}` — و`N` عدّادُ ما تغيّر
    تاريخُه فعلاً، لا كلَّ ما مُسّ.
    """
    _assert_tax_system(tax_system)
    rule = _latest_platform_rule(tax_system, rule_code)
    if rule is None:
        raise ValidationError({
            "code": (
                f"السطر «{rule_code}» غير موجود في لائحة "
                f"{tax_system_label(tax_system)}."
            ),
        })
    if rule.rule_kind == RULE_KIND_DAYS_AFTER_EVENT:
        # سطرُ الحدث: `rule_day` **مدىً بالأيام بعد الحدث** لا يومَ شهر.
        clean_day = _clean_override_number(
            rule_day, "rule_day", minimum=0, maximum=MAX_OVERRIDE_EVENT_DAYS,
        )
    else:
        clean_day = _clean_override_number(
            rule_day, "rule_day", minimum=1, maximum=31,
        )
    if clean_day is not None and rule.rule_kind == RULE_KIND_END_OF_PERIOD:
        # المحرّكُ يُرجع نهايةَ الفترة لهذا النوع ولا يقرأ اليوم — فقبولُه كتابةٌ بلا أثر.
        raise ValidationError({
            "rule_day": "هذا الموعد آخرُ يومٍ في الفترة — لا يومَ يُعدَّل فيه.",
        })
    clean_month = _clean_override_number(rule_month, "rule_month", minimum=1, maximum=12)
    if clean_month is not None and rule.rule_kind != RULE_KIND_MONTH_DAY_NEXT_YEAR:
        raise ValidationError({
            "rule_month": (
                "شهرُ القاعدة لسطر «يوم في السنة التالية» وحده — غيره يومٌ في شهر."
            ),
        })
    clean_extension = _clean_override_number(
        electronic_extension_days, "electronic_extension_days",
        minimum=0, maximum=MAX_OVERRIDE_EXTENSION_DAYS,
    )
    clean_note = (note or "").strip()
    if not clean_note:
        raise ValidationError({"note": "ملاحظة التعديل مطلوبة — القرارُ يُفسَّر بها."})
    with transaction.atomic():
        override = OfficeRuleOverride.objects.create(
            tenant=tenant,
            tax_system=tax_system,
            rule_code=rule_code,
            rule_day=clean_day,
            rule_month=clean_month,
            electronic_extension_days=clean_extension,
            based_on=_override_based_on(rule),
            note=clean_note,
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        changed = _recompute_for_code(
            tenant, rule_code, reason=OBLIGATION_CHANGE_OFFICE_OVERRIDE, actor=actor,
            tax_system=tax_system,
        )
    return {"override": _override_row(override), "changed_obligations": len(changed)}


def clear_rule_override(tenant, *, tax_system, rule_code, actor) -> dict:
    """**«رجّع لتاريخ المنصة»** — صفٌّ `cleared=True` ثم الإعادةُ نفسها. لا حذف."""
    _assert_tax_system(tax_system)
    rule = _latest_platform_rule(tax_system, rule_code)
    if rule is None:
        raise ValidationError({
            "code": f"السطر «{rule_code}» غير موجود في لائحة المنصة.",
        })
    with transaction.atomic():
        override = OfficeRuleOverride.objects.create(
            tenant=tenant,
            tax_system=tax_system,
            rule_code=rule_code,
            cleared=True,
            based_on=_override_based_on(rule),
            note="رجّع للمنصة",
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        changed = _recompute_for_code(
            tenant, rule_code, reason=OBLIGATION_CHANGE_OFFICE_OVERRIDE, actor=actor,
            tax_system=tax_system,
        )
    return {"override": _override_row(override), "changed_obligations": len(changed)}


def keep_rule_override(tenant, *, tax_system, rule_code, actor) -> dict:
    """**«أُبقي تاريخي»** — صفٌّ بالقيم نفسها ولقطةٍ من النسخة السارية.

    فيصير الساري الجديد ويسقط تنبيهُ «تُبقي تاريخك أم تأخذ الجديد؟» بلا أن يتغيّر
    تاريخُ التزامٍ واحد. ولا تعديلَ ساري ⇒ رفضٌ بالطريق الصحيح: «تأخذ الجديد» هو
    `clear_rule_override`.
    """
    _assert_tax_system(tax_system)
    current = active_rule_overrides(tenant).get((tax_system, rule_code))
    if current is None:
        raise ValidationError({
            "code": (
                "لا تعديلَ سارياً لهذا السطر — و«تأخذ الجديد» هو «رجّع للمنصة»."
            ),
        })
    rule = _latest_platform_rule(tax_system, rule_code)
    with transaction.atomic():
        override = OfficeRuleOverride.objects.create(
            tenant=tenant,
            tax_system=tax_system,
            rule_code=rule_code,
            rule_day=current.rule_day,
            rule_month=current.rule_month,
            electronic_extension_days=current.electronic_extension_days,
            based_on=(
                _override_based_on(rule) if rule is not None else dict(current.based_on)
            ),
            note=current.note,
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        changed = _recompute_for_code(
            tenant, rule_code, reason=OBLIGATION_CHANGE_OFFICE_OVERRIDE, actor=actor,
            tax_system=tax_system,
        )
    return {"override": _override_row(override), "changed_obligations": len(changed)}


def _append_warnings(obligations, warning) -> int:
    """يُضيف تنبيهاً **مرّةً**: تشغيلٌ ثانٍ لا يكرّره، ولا يمحو تنبيهات المحرّك."""
    touched = []
    for obligation in obligations:
        warnings = list(obligation.warnings or [])
        if warning in warnings:
            continue
        obligation.warnings = [*warnings, warning]
        obligation.updated_at = timezone.now()
        touched.append(obligation)
    if touched:
        Obligation.objects.bulk_update(touched, ["warnings", "updated_at"])
    return len(touched)


def _override_conflict_candidates(overrides, *, label) -> list[tuple[str, str, str]]:
    """«المنصة غيّرت موعداً أنت معدّله» — **مستقلٌّ عن نقل الالتزامات**.

    التنبيهُ قرارُ مكتبٍ لا نتيجةَ تحديث: يُفحص **كلُّ تعديلٍ ساري × سطرِه في
    النسخة السارية لنظامه**، ولو لم يكن للمكتب التزامٌ غيرُ مقدَّمٍ يُنقل أصلاً.

    والشرط: نسخةٌ **أحدث** (بـ`version` أعلى) من نسخة اللقطة، وقيمُ سطرها لا
    تطابق `based_on`. فنسخةٌ جديدةٌ نسخت السطر حرفاً لا تُنبِّه؛ والتعديلُ يسري على
    كل سنوات نظامه، فنسخةٌ أحدثُ لأيّ سنةٍ يخالف سطرُها `based_on` تُنبِّه.

    والكلفةُ ثابتة: نسخُ الأنظمة المعنيّة استعلامٌ واحد، ونسخُ اللقطات استعلامٌ
    واحد، وأسطرُها استعلامٌ واحد — لا استعلامَ لكل تعديل.
    """
    systems = {override.tax_system for override in overrides.values()}
    if not systems:
        return []
    current: dict[tuple[str, int], Any] = {}
    for schedule in (
        DeadlineSchedule.objects
        .filter(tax_system__in=systems)
        .order_by("tax_system", "year", "-version")
    ):
        current.setdefault((schedule.tax_system, schedule.year), schedule)
    snapshot_ids = {
        (override.based_on or {}).get("schedule_id")
        for override in overrides.values()
    } - {None}
    snapshot_versions = dict(
        DeadlineSchedule.objects
        .filter(pk__in=snapshot_ids)
        .values_list("pk", "version"),
    )
    codes = {code for _system, code in overrides}
    rules = {
        (rule.schedule_id, rule.code): rule
        for rule in DeadlineRule.objects.filter(
            schedule__in=list(current.values()), code__in=codes,
        )
    }
    candidates: list[tuple[str, str, str]] = []
    for (system, code), override in overrides.items():
        snapshot = override.based_on or {}
        snapshot_version = snapshot_versions.get(snapshot.get("schedule_id"), 0)
        for (tax_system, _year), schedule in current.items():
            if tax_system != system or schedule.version <= snapshot_version:
                continue
            rule = rules.get((schedule.pk, code))
            if rule is None or _based_on_matches(snapshot, rule):
                continue
            candidates.append((
                OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED,
                f"override:{override.pk}:schedule:{schedule.pk}",
                (
                    f"المنصة غيّرت موعداً أنت معدّله: {rule.name} ({label(system)}) "
                    "— تُبقي تاريخك أم تأخذ الجديد؟"
                ),
            ))
            break
    return candidates


def _apply_platform_updates(tenant, *, day, context) -> dict:
    """**تحديثُ المنصة للائحة**: «التحديث» = نسخةٌ أحدث، والالتزامُ غيرُ المقدَّم يلحقها.

    كلُّ التزامٍ `pending`/`not_required` يشير إلى نسخةٍ ليست السارية لنظام زبونه
    وسنة `period_end`:

    - سطرُ كوده موجودٌ في النسخة السارية ⇒ يُنقل إليه ويُعاد حسابه (`platform_update`).
    - سطرُه غاب من الجديد ⇒ لا تاريخَ يتغيّر، وتُضاف `warnings` وحدها.

    **والمقدَّمُ لا يُمسّ** ولا يُنقل سطرُه. والكلفةُ ثابتة: التزاماتُ المكتب استعلامٌ
    واحد، وأسطرُ النسخ الجديدة استعلامٌ واحد مجمَّعةً بالكود، والكتابةُ دفعةٌ واحدة
    (`_recompute_obligations`). ولا `UPDATE … WHERE id IN (SELECT … من الجدول نفسه)`.

    ويُرجع `{schedule_id: (schedule, عددُ ما تغيّر تاريخُه)}` لتُبنى عليه تنبيهاتُ
    اللائحة.
    """
    obligations = list(
        Obligation.objects
        .filter(
            tenant=tenant,
            status__in=(OBLIGATION_STATUS_PENDING, OBLIGATION_STATUS_NOT_REQUIRED),
            rule__isnull=False,
        )
        .select_related(
            "rule__schedule",
            "client",
            "client_service__service",
            "task",
        )
        .prefetch_related("client_service__frequencies")
    )
    stale = []
    for obligation in obligations:
        system = context.setting(obligation.client, TAX_SYSTEM_KEY)
        if not system:
            continue
        schedule = context.schedule(system, obligation.period_end.year)[0]
        if schedule is None or obligation.rule.schedule_id == schedule.pk:
            continue
        stale.append((obligation, schedule))
    if not stale:
        return {}
    wanted: dict[int, set] = {}
    for obligation, schedule in stale:
        wanted.setdefault(schedule.pk, set()).add(obligation.rule_code)
    rules = {
        (rule.schedule_id, rule.code): rule
        for rule in DeadlineRule.objects.filter(
            schedule_id__in=list(wanted),
            code__in={code for codes in wanted.values() for code in codes},
        )
    }
    moved: list = []
    missing: list = []
    schedules: dict[int, Any] = {}
    for obligation, schedule in stale:
        rule = rules.get((schedule.pk, obligation.rule_code))
        if rule is None:
            missing.append(obligation)
            continue
        obligation.rule = rule
        # السطرُ عاد في النسخة السارية: تحذيرُ «لم يعد» السابقُ لم يعد صادقاً.
        obligation.warnings = [
            warning for warning in (obligation.warnings or [])
            if warning != PLATFORM_MISSING_LINE_WARNING
        ]
        moved.append(obligation)
        schedules[schedule.pk] = schedule
    _append_warnings(missing, PLATFORM_MISSING_LINE_WARNING)
    if not moved:
        return {}
    changed = _recompute_obligations(
        moved, context=context, reason=OBLIGATION_CHANGE_PLATFORM_UPDATE,
    )
    counts: dict[int, int] = {pk: 0 for pk in schedules}
    for obligation in changed:
        schedule_id = obligation.rule.schedule_id
        if schedule_id in counts:
            counts[schedule_id] += 1
    return {
        schedule_id: (schedules[schedule_id], count)
        for schedule_id, count in counts.items()
    }


def _generate_schedule_alerts(tenant, *, day, context, schedule_changes=None) -> int:
    """تنبيهاتُ اللائحة لأصحاب المكتب (`MANAGER_ROLE` النشطون) — بلا زبونٍ ولا مبلغ.

    - `schedule_dates_changed` **مرّةً لكل نسخةٍ** تغيّر بها التزامٌ واحدٌ على الأقل
      («تغيّر موعد N التزامات»)، و`ref_key="schedule:<id>"` — فالفرادةُ غيرُ
      المشروطة تمنع التكرار بتشغيلٍ ثانٍ.
    - `override_platform_changed` لكل تعديلٍ ساري تختلف لقطتُه `based_on` عن قيم
      السطر في النسخة السارية — «تُبقي تاريخك أم تأخذ الجديد؟»،
      و`ref_key="override:<id>:schedule:<sid>"`.

    ونوعاهما خارج `RESOLVED_ALERT_KINDS` فيبقيان حتى «شفته» — ويسقط الثاني وحده
    على القراءة إن لم يعد التعديلُ سارياً (`_live_override_alerts_q`).
    """
    recipients = _office_owner_ids(tenant)
    if not recipients:
        return 0
    candidates: list[tuple[str, str, str]] = []
    for schedule, count in (schedule_changes or {}).values():
        if count <= 0:
            continue
        candidates.append((
            OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
            f"schedule:{schedule.pk}",
            (
                f"تغيّر موعد {count} التزامات في لائحة "
                f"{tax_system_label(schedule.tax_system)} لسنة {schedule.year}"
            ),
        ))
    # **قرارُ المكتب مستقلٌّ عن النقل**: يُفحص كلُّ تعديلٍ ساري ولو لم يُنقل التزام.
    candidates.extend(
        _override_conflict_candidates(context.overrides, label=tax_system_label),
    )
    if not candidates:
        return 0
    ref_keys = {ref_key for _kind, ref_key, _message in candidates}
    existing = set(
        OfficeAlert.objects
        .filter(
            tenant=tenant,
            kind__in=(
                OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
                OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED,
            ),
            ref_key__in=ref_keys,
        )
        .values_list("recipient_id", "kind", "ref_key"),
    )
    rows: list = []
    for kind, ref_key, message in candidates:
        rows.extend(_new_alert_rows(
            tenant=tenant,
            kind=kind,
            ref_key=ref_key,
            recipients=recipients,
            message=message,
            day=day,
            client=None,
            task=None,
            obligation=None,
            existing=existing,
        ))
    if not rows:
        return 0
    OfficeAlert.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def _log_obligation_change(obligation, *, description, metadata, actor) -> None:
    """أثرُ التمديد وإلغائه في سجلّ **الزبون** — الوجهةُ التي يفتحها المكتب."""
    log_activity(
        action="update",
        entity_type="office_client",
        entity_id=obligation.client_id,
        entity_label=obligation.client.name,
        description=description,
        metadata=metadata,
        tenant=obligation.tenant,
        user=actor,
    )


def extend_obligation(obligation, *, until, note, actor) -> Obligation:
    """**«مدّد»**: تاريخٌ وملاحظة — يُسكِت الأحمرَ إلى الموعد الجديد.

    المنتظرُ وحده يُمدَّد: «انقدّم» نهائيٌّ، و«مش لازم هالفترة» تُرجَّع أوّلاً.
    والموعدُ الجديد **بعد الفعليّ** وملاحظتُه مطلوبة — تمديدٌ بلا سببٍ مكتوبٍ رقمٌ
    لا يُفسَّر بعد شهرين. والتاريخُ الرسميُّ لا يُكتب فوقه: التمديدُ قرارٌ زائدٌ
    يُلغى فيُرجع الفعليَّ كما كان.
    """
    if obligation.status == OBLIGATION_STATUS_SUBMITTED:
        raise ValidationError({"status": SUBMITTED_LOCKED})
    if obligation.status != OBLIGATION_STATUS_PENDING:
        raise ValidationError({"status": "مش لازم: رجّعها أولاً ثم مدّد."})
    if until is None:
        raise ValidationError({"until": "تاريخ التمديد مطلوب."})
    if until <= obligation.actual_deadline:
        raise ValidationError({
            "until": "التمديد بعد الموعد الفعلي — وما قبله تقديمٌ لا تمديد.",
        })
    clean_note = (note or "").strip()
    if not clean_note:
        raise ValidationError({"note": "ملاحظة التمديد مطلوبة."})
    before = _dates_snapshot(obligation)
    with transaction.atomic():
        obligation.extended_to = until
        obligation.extension_note = clean_note
        obligation.extended_by = actor if getattr(actor, "pk", None) else None
        obligation.extended_at = timezone.now()
        obligation.save(update_fields=[
            "extended_to",
            "extension_note",
            "extended_by",
            "extended_at",
            "updated_at",
        ])
        ObligationDateChange.objects.create(
            tenant=obligation.tenant,
            obligation=obligation,
            reason=OBLIGATION_CHANGE_EXTENSION,
            before=before,
            after=_dates_snapshot(obligation),
            changed_by=obligation.extended_by,
        )
    _log_obligation_change(
        obligation,
        description=(
            f"تمديد «{obligation.name}» في {obligation.client.name} إلى {until}"
        ),
        metadata={
            "obligation": obligation.pk,
            "until": until.isoformat(),
            "from": obligation.actual_deadline.isoformat(),
        },
        actor=actor,
    )
    return obligation


def clear_obligation_extension(obligation, *, actor) -> Obligation:
    """**«ألغِ التمديد»**: يرجع إلى الموعد الفعليّ، بصفٍّ `extension_cleared`."""
    if obligation.status == OBLIGATION_STATUS_SUBMITTED:
        raise ValidationError({"status": SUBMITTED_LOCKED})
    if obligation.extended_to is None:
        raise ValidationError({"status": "لا تمديدَ لهذا الالتزام لتُلغى."})
    before = _dates_snapshot(obligation)
    with transaction.atomic():
        obligation.extended_to = None
        obligation.extension_note = ""
        obligation.extended_by = None
        obligation.extended_at = None
        obligation.save(update_fields=[
            "extended_to",
            "extension_note",
            "extended_by",
            "extended_at",
            "updated_at",
        ])
        ObligationDateChange.objects.create(
            tenant=obligation.tenant,
            obligation=obligation,
            reason=OBLIGATION_CHANGE_EXTENSION_CLEARED,
            before=before,
            after=_dates_snapshot(obligation),
            changed_by=actor if getattr(actor, "pk", None) else None,
        )
    _log_obligation_change(
        obligation,
        description=(
            f"إلغاء تمديد «{obligation.name}» في {obligation.client.name} — "
            f"الموعد الفعليّ {obligation.actual_deadline}"
        ),
        metadata={
            "obligation": obligation.pk,
            "to": obligation.actual_deadline.isoformat(),
        },
        actor=actor,
    )
    return obligation


def _custom_rule_row(row) -> dict:
    """سطرُ التزام مكتبٍ كما يُعرض — بكوده المشتقّ وتسمياته من الثوابت."""
    return {
        "id": row.pk,
        "code": row.code,
        "name": row.name,
        "service": {
            "id": row.service_id,
            "code": row.service.code,
            "name": row.service.name,
        },
        "cadence": row.cadence,
        "cadence_label": dict(DEADLINE_CADENCE_CHOICES).get(row.cadence, ""),
        "rule_kind": row.rule_kind,
        "rule_kind_label": dict(OFFICE_CUSTOM_RULE_KIND_CHOICES).get(row.rule_kind, ""),
        "rule_day": row.rule_day,
        "rule_month": row.rule_month,
        "is_active": row.is_active,
        "origin_label": OBLIGATION_ORIGIN_LABELS.get(OBLIGATION_ORIGIN_OFFICE, ""),
    }


def custom_rules_payload(tenant) -> dict:
    """شاشةُ «التزامات المكتب»: القائمةُ مع اختياراتها — **قراءةٌ لا تزرع شيئاً**.

    والخدماتُ تُقرأ بلا `ensure_default_services`: القراءةُ لا تكتب، وزرعُ الكتالوج
    فعلُ شاشة الخدمات (`GET services/`).
    """
    return {
        "custom_rules": [
            _custom_rule_row(row)
            for row in (
                OfficeCustomRule.objects
                .filter(tenant=tenant)
                .select_related("service")
                .order_by("name", "id")
            )
        ],
        "cadence_choices": [
            {"value": value, "label": label}
            for value, label in OFFICE_CUSTOM_RULE_CADENCE_CHOICES
        ],
        "rule_kind_choices": [
            {"value": value, "label": label}
            for value, label in OFFICE_CUSTOM_RULE_KIND_CHOICES
        ],
        "services": [
            {"id": row.pk, "code": row.code, "name": row.name}
            for row in (
                OfficeService.objects
                .filter(tenant=tenant, is_active=True)
                .order_by("position", "name", "id")
            )
        ],
    }


def _clean_custom_rule_payload(*, cadence, rule_kind, rule_day, rule_month):
    """حدودُ قاعدة المكتب: دوريةٌ تُولّد، ونوعُ قاعدةٍ دوريّ، ويومٌ/شهرٌ في حدّيهما.

    والحدثُ يُرفض برسالته أوّلاً — **قبل فحص العضوية** — لأن دوريات التزام المكتب
    (`OFFICE_CUSTOM_RULE_CADENCE_CHOICES`) خارجها `event` أصلاً، فيأخذ المنادي
    رسالةَ «الحدث يُسجَّل من ملفّ الزبون» لا «دورية غير معروفة».
    """
    if cadence == CADENCE_EVENT:
        raise ValidationError({
            "cadence": "التزامُ المكتب دوريٌّ — والحدثُ يُسجَّل من ملفّ الزبون.",
        })
    if cadence not in {value for value, _label in OFFICE_CUSTOM_RULE_CADENCE_CHOICES}:
        raise ValidationError({"cadence": "دورية غير معروفة."})
    if rule_kind not in {value for value, _label in OFFICE_CUSTOM_RULE_KIND_CHOICES}:
        raise ValidationError({"rule_kind": "نوعُ قاعدة غير معروف لالتزام المكتب."})
    clean_day = _clean_override_number(rule_day, "rule_day", minimum=1, maximum=31)
    clean_month = _clean_override_number(rule_month, "rule_month", minimum=1, maximum=12)
    if rule_kind == RULE_KIND_MONTH_DAY_NEXT_YEAR:
        if clean_month is None or clean_day is None:
            raise ValidationError({
                "rule_day": "«يوم في السنة التالية» يحتاج شهراً ويوماً.",
            })
        return clean_day, clean_month
    if clean_day is None and rule_kind == RULE_KIND_DAY_OF_NEXT_MONTH:
        raise ValidationError({"rule_day": "«يوم في الشهر التالي» يحتاج يوماً."})
    return clean_day, None


def create_custom_rule(
    tenant, *, name, service, cadence, rule_kind, rule_day=None, rule_month=None,
    is_active=True, actor, day=None,
) -> OfficeCustomRule:
    """**التزامٌ خاص بالمكتب**: اسمٌ وخدمةٌ ودوريةٌ وقاعدة — يُولّد كالرسميّ.

    **ويُولَّد فور إنشائه** لزبائن خدمته (`_generate_for_service`): `refresh_office`
    لا يعمل إلا مرّةً في اليوم، فالقاعدةُ المنشأةُ بعد تشغيل اليوم كانت تنتظر الغد.
    و`day` هو يومُ التوليد نفسُه الذي يقرؤه التحديث (افتراضُه `timezone.localdate()`).
    """
    _assert_service_of_tenant(tenant, service)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError({"name": "اسمُ الالتزام مطلوب."})
    clean_day, clean_month = _clean_custom_rule_payload(
        cadence=cadence, rule_kind=rule_kind, rule_day=rule_day, rule_month=rule_month,
    )
    row = OfficeCustomRule.objects.create(
        tenant=tenant,
        name=clean_name,
        service=service,
        cadence=cadence,
        rule_kind=rule_kind,
        rule_day=clean_day,
        rule_month=clean_month,
        is_active=bool(is_active),
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    if row.is_active:
        _generate_for_service(tenant, service, day=day or timezone.localdate())
    return row


def _generate_for_service(tenant, service, *, day) -> None:
    """يحفظ المستحقَّ لزبائن خدمةٍ واحدة — **بمسار الحفظ نفسه** الذي يقرؤه `refresh_office`.

    الزبائنُ من لهم `ClientService` على هذه الخدمة لم تنتهِ قبل `day`. والحفظُ
    idempotent (القائمُ يُقرأ ولا يُكتب)، فتشغيلُ اليوم بعدها لا يكرّر صفّاً.
    """
    clients = list(
        OfficeClient.objects
        .filter(
            Q(services__ends_on__isnull=True) | Q(services__ends_on__gte=day),
            tenant=tenant,
            services__service=service,
        )
        .select_related("tax_card", "responsible")
        .prefetch_related("services__service", "services__frequencies")
        .distinct()
        .order_by("id"),
    )
    if not clients:
        return
    _save_due_for_clients(
        tenant, clients, day=day, context=calendar_context(tenant, clients),
    )


def update_custom_rule(
    row, *, name=None, service=None, cadence=None, rule_kind=None,
    rule_day=_UNSET, rule_month=_UNSET, is_active=None, actor, day=None,
) -> OfficeCustomRule:
    """تعديلُ التزام مكتبٍ — ويعيد حسابَ غير المقدَّم منه بالدالّة الواحدة.

    **والتعطيلُ لا يمحو شيئاً**: يوقف توليد الفترات الجديدة، وما وُلد يبقى بتاريخه.
    ولقطةُ الاسم والموعد في الالتزام المحفوظ لا تتغيّر بالاسم الجديد — تُحدَّث
    التواريخُ وحدها (`office_override`).

    **وتُولَّد الفتراتُ المستحقّة** (`_generate_for_service`) حين تتبدّل خدمتُها أو
    دوريتُها أو يعود المعطَّلُ إلى التفعيل — لا عند كل تعديل، فتعديلُ اليوم أو الاسم
    لا يفتح فتراتٍ جديدة.
    """
    changed = False
    regenerate = False
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError({"name": "اسمُ الالتزام مطلوب."})
        row.name = clean_name
        changed = True
    if service is not None:
        _assert_service_of_tenant(row.tenant, service)
        regenerate = regenerate or service.pk != row.service_id
        row.service = service
        changed = True
    next_cadence = row.cadence if cadence is None else cadence
    next_kind = row.rule_kind if rule_kind is None else rule_kind
    next_day = row.rule_day if rule_day is _UNSET else rule_day
    next_month = row.rule_month if rule_month is _UNSET else rule_month
    clean_day, clean_month = _clean_custom_rule_payload(
        cadence=next_cadence, rule_kind=next_kind,
        rule_day=next_day, rule_month=next_month,
    )
    if (next_cadence, next_kind, clean_day, clean_month) != (
        row.cadence, row.rule_kind, row.rule_day, row.rule_month,
    ):
        regenerate = regenerate or next_cadence != row.cadence
        row.cadence = next_cadence
        row.rule_kind = next_kind
        row.rule_day = clean_day
        row.rule_month = clean_month
        changed = True
    if is_active is not None and bool(is_active) != row.is_active:
        regenerate = regenerate or bool(is_active)
        row.is_active = bool(is_active)
        changed = True
    if not changed:
        return row
    row.save()
    _recompute_for_code(
        row.tenant, row.code, reason=OBLIGATION_CHANGE_OFFICE_OVERRIDE, actor=actor,
    )
    if regenerate and row.is_active:
        _generate_for_service(
            row.tenant, row.service, day=day or timezone.localdate(),
        )
    return row


def enabled_event_kinds(tenant) -> list[dict]:
    """أنواعُ الأحداث المفعّلة بتسمياتها — مصدرُ التحقّق والشاشة واحد."""
    enabled = resolve_setting(tenant, "enabled_event_kinds") or []
    return [
        {"value": key, "label": EVENT_KIND_LABELS.get(key, key)}
        for key, _label in EVENT_KIND_CHOICES
        if key in enabled
    ]


def _active_client_services(client, *, day) -> dict[str, Any]:
    """خدماتُ الزبون **النشطة** بتاريخ الحدث، بمفتاح كود الخدمة."""
    rows: dict[str, Any] = {}
    for row in client_services_of(client):
        if row.starts_on > day:
            continue
        if row.ends_on is not None and day > row.ends_on:
            continue
        rows[row.service.code] = row
    return rows


def _event_obligation_result(client, *, rule, occurred_on, context, system):
    """موعدُ التزام حدثٍ — **دالّةٌ واحدة** يقرؤها التوليدُ وإعادةُ الحساب.

    فترةُ الحدث (يومُ وقوعه، يومُ وقوعه) ليست في أيّ مجرى لائحةٍ، فتُحسب بقاعدة
    `days_after_event` وأيامِ الدورية الشهرية، وموعدُها الداخليُّ **لا يسبق يومَ
    الحدث** (`max`) — فلا نسخةَ ثانية من هذا الحساب في مسارٍ آخر ولا في الإعادة.
    """
    result = _deadline_result(
        client,
        rule=rule,
        override=context.overrides.get((system, rule.code)),
        period_start=occurred_on,
        period_end=occurred_on,
        cadence=FREQUENCY_MONTHLY,
        context=context,
        system=system,
    )
    if result is None:
        return None
    return replace(
        result, internal_deadline=max(occurred_on, result.internal_deadline),
    )


def _event_obligation(client, *, tenant, event, rule, client_service, context, system):
    """التزامُ حدثٍ واحد: فترتُه يومُ وقوعه، وقاعدتُه سطرُ `days_after_event`."""
    day = event.occurred_on
    result = _event_obligation_result(
        client, rule=rule, occurred_on=day, context=context, system=system,
    )
    if result is None:
        raise ValidationError({
            "kind": f"لا لائحةَ لسنة {day.year} في هذا النظام — لا موعدَ للحدث.",
        })
    task, _task_created = PeriodTask.objects.get_or_create(
        client_service=client_service,
        period_start=day,
        period_end=day,
        defaults={
            "tenant": tenant,
            "client": client,
            "internal_deadline": day,
        },
    )
    obligation, _created = Obligation.objects.get_or_create(
        client_service=client_service,
        rule_code=rule.code,
        period_end=day,
        defaults=_obligation_defaults(
            tenant, client,
            task=task,
            result=result,
            origin=OBLIGATION_ORIGIN_EVENT,
            name=rule.name,
            rule=rule,
            event=event,
        ),
    )
    if (
        obligation.task_id == task.pk
        and result.internal_deadline < task.internal_deadline
    ):
        task.internal_deadline = result.internal_deadline
        task.save(update_fields=["internal_deadline"])
    return obligation


def record_client_event(client, *, kind, occurred_on, note="", actor):
    """**«صار حدث»**: يسجّل الخبرَ ويولّد التزامَه من أسطر اللائحة لهذا النوع.

    الشروطُ قبل الكتابة: النوعُ مفعَّلٌ في إعداد المكتب، والتاريخُ ليس في المستقبل،
    وسطرُ الحدث موجودٌ في لائحة نظام الزبون (وإلا «لا قاعدة»)، وخدمةُ السطر
    نشطةٌ عند الزبون يومَ الحدث (وإلا لا جهةَ تُقدَّم لها).

    والالتزامُ يُولَّد بـ`compute_deadline` نفسها: `legal_date` من `days_after_event`
    (اقتطاعٌ في X ⇒ الالتزام في X+30)، والرسميُّ بسياسة يوم الراحة للنسخة،
    والداخليُّ بأيام الدورية الشهرية ولا يسبق يومَ الحدث.

    **وحدثان في اليوم نفسه بنفس النوع ⇒ التزامٌ واحد** (الفرادةُ القائمة على
    `(خدمة, كود, نهاية الفترة)`)، ويُرجع القائمَ كما هو. ويُرجع `(الحدث, التزاماتُه)`.
    """
    tenant = client.tenant
    enabled = resolve_setting(tenant, "enabled_event_kinds") or []
    if kind not in enabled:
        raise ValidationError({"kind": "نوع الحدث غير مفعّل — فعّله في إعدادات المكتب."})
    if occurred_on is None:
        raise ValidationError({"occurred_on": "تاريخ الحدث مطلوب."})
    if occurred_on > timezone.localdate():
        raise ValidationError({"occurred_on": "تاريخ الحدث لا يكون في المستقبل."})
    system = resolve_setting(tenant, TAX_SYSTEM_KEY, client=client)
    schedule, _estimated = schedule_for(system, occurred_on.year)
    rules = (
        []
        if schedule is None
        else [
            rule
            for rule in schedule.rules.all()
            if rule.cadence == CADENCE_EVENT and rule.event_kind == kind
        ]
    )
    if not rules:
        raise ValidationError({
            "kind": f"لا قاعدة لهذا الحدث في لائحة {tax_system_label(system)}.",
        })
    services_by_code = _active_client_services(client, day=occurred_on)
    for rule in rules:
        if rule.service_code in services_by_code:
            continue
        service = service_by_code(tenant, rule.service_code)
        raise ValidationError({
            "kind": f"الزبون ما عنده خدمة {service.name} نشطة بتاريخ الحدث.",
        })
    context = calendar_context(tenant, [client])
    with transaction.atomic():
        event = ClientEvent.objects.create(
            tenant=tenant,
            client=client,
            kind=kind,
            occurred_on=occurred_on,
            note=(note or "").strip(),
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        obligations = [
            _event_obligation(
                client,
                tenant=tenant,
                event=event,
                rule=rule,
                client_service=services_by_code[rule.service_code],
                context=context,
                system=system,
            )
            for rule in rules
        ]
    return event, obligations


def client_event_row(event, *, client, user, day=None, masked=None) -> dict:
    """سطرُ حدثٍ في ملفّ الزبون — والتزاماتُه بالشكل نفسه الذي يعرضه التبويب.

    و`day`/`masked` يُمرَّران من الحمولة حين تُبنى لأحداثٍ كثيرة: القناعُ يُحسب
    مرّةً للحمولة، واليومُ مرّةً للطلب — فلا استعلامَ مفتاحِ مبالغٍ لكل حدث.
    """
    day = day or timezone.localdate()
    if masked is None:
        masked = user is not None and not can_see_amounts(client.tenant, user)
    return {
        "id": event.pk,
        "kind": event.kind,
        "kind_label": EVENT_KIND_LABELS.get(event.kind, ""),
        "occurred_on": event.occurred_on.isoformat(),
        "note": event.note,
        "created_by_name": user_display_name(event.created_by),
        "created_at": event.created_at.isoformat(),
        "obligations": [
            _obligation_row(
                obligation, day=day, client=client,
                task=obligation.task, masked=masked,
            )
            for obligation in event.obligations.all()
        ],
    }


def client_events_payload(client, *, user, day=None) -> dict:
    """أحداثُ الزبون الأحدثَ وقوعاً أولاً، مع الأنواع المفعّلة لمنتقي التسجيل.

    **والكلفةُ ثابتة**: الأحداثُ استعلامٌ واحد، والتزاماتُها بشغلاتها ومسؤوليها
    **مُجلَبةٌ سلفاً** (`prefetch_related`) — فلا استعلامَ لكل حدثٍ ولا لكل
    التزام. والقناعُ واليومُ يُحسبان مرّةً للحمولة.
    """
    day = day or timezone.localdate()
    masked = user is not None and not can_see_amounts(client.tenant, user)
    events = list(
        client.events
        .select_related("created_by")
        .prefetch_related(
            "obligations__task__assignee",
            "obligations__task__client__responsible",
        )
        .order_by("-occurred_on", "-id")
    )
    return {
        "client": {"id": client.pk, "name": client.name},
        "event_kinds": enabled_event_kinds(client.tenant),
        "events": [
            client_event_row(
                event, client=client, user=user, day=day, masked=masked,
            )
            for event in events
        ],
    }

# ── قائمة الأوراق وشبكة الأشهر (#278) ───────────────────────────────────────
#
# **البندُ من الكتالوج، والصفُّ لقطة**: `_document_items_for` هي **الدالّة الوحيدة**
# التي تجيب «ما بنودُ هذا الزبون في هذه الفترة؟» — يقرؤها التوليد وحده، ولا نسخة
# ثانية منها في الواجهة ولا في الـpayload (الحمولةُ تقرأ الصفوف المحفوظة).
#
# **والتوليدُ داخل «حدّث المكتب»**: فترةٌ انتهت (`period_end <= day - 1`) صارت
# مستحقّة، وتُحفظ بـ`get_or_create` على `(زبون، بند، بداية الفترة)` — فتشغيلُ
# اليوم نفسه مرّتين لا يكتب صفاً، والقائمُ لا يُعاد كتابته أبداً.
#
# **و«ناقصه أوراق» تُحسب عند القراءة**: صفوفُ خدمة الالتزام داخل فترته، منها
# المطلوبُ أو الناقص. لا عمودَ لها، ولا تُخزَّن — وإلا تعفّنت بين تشغيلين.
DOCUMENT_STATUS_KEYS: tuple[str, ...] = tuple(
    value for value, _label in DOCUMENT_STATUS_CHOICES
)
DOCUMENT_CHANNEL_KEYS: tuple[str, ...] = tuple(
    value for value, _label in DOCUMENT_CHANNEL_CHOICES
)
DOCUMENT_CADENCE_KEYS: tuple[str, ...] = tuple(
    value for value, _label in DOCUMENT_CADENCE_CHOICES
)
#: الحالتان اللتان تعنيان «وصلت الورقة»: الكاملةُ والناقصة.
DOCUMENT_RECEIVED_STATUSES: frozenset[str] = frozenset({
    DOCUMENT_STATUS_RECEIVED, DOCUMENT_STATUS_PARTIAL,
})

#: الملفُّ المسموح: PDF أو صورة — حدُّه ١٠ ميجابايت (صندوقُ عملٍ لا أرشيفٌ قانونيّ).
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".png": frozenset({"image/png"}),
    ".webp": frozenset({"image/webp"}),
}
DOCUMENT_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    content_type
    for allowed in DOCUMENT_ALLOWED_EXTENSIONS.values()
    for content_type in allowed
)
#: أولُ بايتاتٍ تُقرأ للتعرّف على المحتوى — البايتاتُ هي الحَكَم لا الامتداد.
DOCUMENT_MAGIC_BYTES = 16
#: مجلّدُ التخزين في مزوّد الوسائط.
DOCUMENT_UPLOAD_FOLDER = "accounting_office_documents"


def document_status_label(status, cadence) -> str:
    """تسميةُ الحالة — والاستثناءُ يقول شهرَه أو سنتَه بحسب دورية الصفّ."""
    if status == DOCUMENT_STATUS_NOT_NEEDED and cadence == DOCUMENT_CADENCE_ANNUAL:
        return DOCUMENT_STATUS_NOT_NEEDED_ANNUAL_LABEL
    return DOCUMENT_STATUS_LABELS.get(status, "")


def document_status_choices() -> list[dict]:
    """الحالاتُ الأربع للواجهة — بتسميةٍ شهريةٍ وأخرى سنويةٍ للاستثناء."""
    return [
        {
            "value": value,
            "label": label,
            "annual_label": document_status_label(value, DOCUMENT_CADENCE_ANNUAL),
        }
        for value, label in DOCUMENT_STATUS_CHOICES
    ]


def document_channel_choices() -> list[dict]:
    """قنواتُ الوصول الثلاث — «كيف وصلت؟»."""
    return [
        {"value": value, "label": label}
        for value, label in DOCUMENT_CHANNEL_CHOICES
    ]


def document_cadence_choices() -> list[dict]:
    """دوريتا الصفّ — شهريٌّ وسنويّ."""
    return [
        {"value": value, "label": label}
        for value, label in DOCUMENT_CADENCE_CHOICES
    ]


# ── الكتالوج: أين تُقرأ البنود ولا تُخترَع ──────────────────────────────────
def _document_catalog(context, tax_system, cadence) -> list[dict]:
    """بنداتُ نظامٍ ودورية — المنصّة ثم المكتب، **مرّةً لكل طلب**.

    المنصّةُ بترتيب `sort_order` (ترتيبُ البحث)، وقائمةُ المكتب بعدها بالاسم:
    ما أضافه المكتب يبقى أسفل القائمة، فلا يُزيح بنداً قانونياً عن مكانه.

    **والحالةُ الابتدائيةُ لبند المنصّة وحدها** (#279): بندٌ اشتقّه القانونُ يبدأ
    «مش لازمة» حيث لا لزومَ له («تغييرات الموظفين»)، وبندُ المكتب يبدأ
    «مطلوبة» دائماً — ورقةٌ أضافها المكتب لا تُولَد ملغاةً بلا قراره.
    """
    key = (tax_system, cadence)
    cached = context.document_items.get(key)
    if cached is not None:
        return cached
    rows = [
        {
            "item_code": item.code,
            "name": item.name,
            "service_codes": list(item.service_codes or []),
            "card_conditions": dict(item.card_conditions or {}),
            "default_status": item.default_status,
        }
        for item in (
            PlatformDocumentItem.objects
            .filter(tax_system=tax_system, cadence=cadence)
            .order_by("sort_order", "name", "id")
        )
    ]
    rows.extend(
        {
            "item_code": item.code,
            "name": item.name,
            "service_codes": list(item.service_codes or []),
            "card_conditions": dict(item.card_conditions or {}),
            "default_status": DOCUMENT_STATUS_REQUIRED,
        }
        for item in (
            OfficeDocumentItem.objects
            .filter(
                tenant=context.tenant, tax_system=tax_system,
                cadence=cadence, is_active=True,
            )
            .order_by("name", "id")
        )
    )
    context.document_items[key] = rows
    return rows


def _document_office_choices(context) -> dict[str, bool]:
    """خيارُ المكتب على البنود — والغيابُ «ضمن القائمة»."""
    if context.document_choices is None:
        context.document_choices = dict(
            OfficeDocumentItemChoice.objects
            .filter(tenant=context.tenant)
            .values_list("item_code", "included"),
        )
    return context.document_choices


def _document_client_choices(context, client) -> dict[str, bool]:
    """خيارُ الزبون — يُقرأ مرّةً لكل زبونٍ في الطلب."""
    cached = context.document_client_choices.get(client.pk)
    if cached is None:
        cached = dict(
            ClientDocumentItemChoice.objects
            .filter(client=client)
            .values_list("item_code", "included"),
        )
        context.document_client_choices[client.pk] = cached
    return cached


def _document_item_applies(item, *, service_codes, card) -> bool:
    """هل تنطبق شروطُ البند على هذا الزبون في هذه الفترة؟

    الخدماتُ: قائمةٌ فارغةٌ تعني «لكل زبون»، وإلا فتقاطعٌ غيرُ فارغ. والبطاقةُ:
    **كلُّ** شرطٍ يجب أن يطابق، وقيمةٌ فارغةٌ في البطاقة **لا تطابق** شرطاً
    أبداً — «غير مسجّل» ليس «مسجّل» ولا «معفى».
    """
    required = item.get("service_codes") or []
    if required and not set(required) & service_codes:
        return False
    for field, allowed in (item.get("card_conditions") or {}).items():
        # مفتاحُ شرطٍ خارج حقول البطاقة لا يُطابِق: القائمةُ تُقرأ ولا تُخترَع.
        if field not in DOCUMENT_CARD_CONDITION_FIELDS:
            return False
        value = getattr(card, field, "") if card is not None else ""
        if not value or value not in (allowed or []):
            return False
    return True


def _document_period_disclaimed(period_start, period_end, skipped) -> bool:
    """هل تقع فترةُ المستندات **داخل** فترة خدمةٍ رُفع عنها «آخر فترة علينا»؟

    المرفوعُ فترةُ **الخدمة** (رُبعيةً أو سنويةً)، وقائمةُ المستندات شهرية؛ فالمقارنةُ
    احتواءٌ لا تساوٍ: شباط داخل كانون الثاني–آذار مرفوعٌ ولو لم يساوِه.
    """
    return any(
        skipped_start <= period_start and period_end <= skipped_end
        for skipped_start, skipped_end in skipped
    )


def _document_service_codes(
    client, period_start, period_end, *, context, skip=None,
) -> set[str]:
    """أكوادُ الخدمات التي يقدّمها المكتب لهذا الزبون **في هذه الفترة**.

    القاعدةُ هي `_period_is_ours` نفسها التي يحكم بها المحرّك على فترات
    الالتزامات: نشطةٌ، والمكتبُ مسؤولٌ عنها، ولم تُوقف قبل نهاية الفترة.
    **و`skip`**: خدمةٌ رُفع عنها «آخر فترة علينا» تسقط فترتُها من الحساب — فلا
    تُولد بنودُها لشهرٍ يقع داخل تلك الفترة.
    """
    codes: set[str] = set()
    for row in client_services_of(client, context):
        if not _period_is_ours(row, period_end):
            continue
        if _document_period_disclaimed(
            period_start, period_end, (skip or {}).get(row.pk, ()),
        ):
            continue
        codes.add(row.service.code)
    return codes


def _document_items_for(
    client, *, cadence, period_start, period_end, context=None, skip=None,
) -> list[dict]:
    """**الدالّةُ الواحدة**: بنودُ الزبون الفعّالة في فترةٍ — يقرؤها التوليدُ وحده.

    الترتيبُ: خيارُ الزبون إن وُجد (وغلب)، وإلا (خيارُ المكتب أو «ضمن») **و**
    انطباقُ الشروط. فالإخراجُ من المكتب يُسقط البند، والإدخالُ من الزبون يفرضه
    ولو لم تنطبق شروطه — قرارُه فوق قرار المكتب وقاعدةِ القانون.
    **و`skip`** فتراتُ الخدمات المرفوعة («آخر فترة ليست علينا») — تمرّ إلى
    `_document_service_codes` فتُسقط خدمةَ الفترة المرفوعة، والفتراتُ الأخرى تبقى.
    """
    context = context or calendar_context(client.tenant, [client])
    system = context.setting(client, TAX_SYSTEM_KEY)
    if not system:
        # نظامٌ غير مختار: لا لائحةَ تُقرأ، فلا بنودَ تُخترَع.
        return []
    service_codes = _document_service_codes(
        client, period_start, period_end, context=context, skip=skip,
    )
    # `getattr(..., None)` يلتقط `RelatedObjectDoesNotExist` لأنها AttributeError:
    # زبونٌ بلا بطاقةٍ لا يطابق شرطاً.
    card = getattr(client, "tax_card", None)
    office_choices = _document_office_choices(context)
    client_choices = _document_client_choices(context, client)
    items: list[dict] = []
    for item in _document_catalog(context, system, cadence):
        code = item["item_code"]
        if code in client_choices:
            included = client_choices[code]
        else:
            included = office_choices.get(code, True) and _document_item_applies(
                item, service_codes=service_codes, card=card,
            )
        if included:
            items.append(item)
    return items


def _document_item_order(tenant, tax_system, cadence) -> dict[str, int]:
    """ترتيبُ العرض: بنداتُ المنصّة بترتيبها ثم بنداتُ المكتب بالاسم."""
    order: dict[str, int] = {}
    position = 0
    if tax_system:
        for row in (
            PlatformDocumentItem.objects
            .filter(tax_system=tax_system, cadence=cadence)
            .order_by("sort_order", "name", "id")
        ):
            order[row.code] = position
            position += 1
    for row in (
        OfficeDocumentItem.objects
        .filter(tenant=tenant, tax_system=tax_system, cadence=cadence)
        .order_by("name", "id")
    ):
        order[row.code] = position
        position += 1
    return order


# ── التوليد ────────────────────────────────────────────────────────────────
def _document_period_due(client, period_start, period_end, *, service_rows, end, skip):
    """هل صارت قائمةُ هذه الفترة مستحقّةً؟ — القواعدُ التي يحكم بها المحرّك.

    مستحقّةٌ فقط إذا انتهت الفترةُ قبل اليوم (`period_end <= end`، و`end = day - 1`)،
    **ولم** تنقضِ بعد `ended_on` الزبون، **و**للمكتب فيها خدمةٌ مسؤولٌ عنها لم
    تُرفع فترتُها (`skip`، باحتواء `_document_period_disclaimed`).
    """
    if period_end > end:
        return False
    if client.ended_on is not None and period_end > client.ended_on:
        return False
    for row in service_rows:
        if not _period_is_ours(row, period_end):
            continue
        if _document_period_disclaimed(period_start, period_end, skip.get(row.pk, ())):
            continue
        return True
    return False


def _document_periods(client, service_rows, *, end, skip) -> list[tuple]:
    """الفتراتُ المستحقّة لهذا الزبون: شهريةٌ لكل شهرٍ وسنويةٌ لكل سنة.

    الأرضيةُ `min(starts_on, responsible_from)` كالمحرّك — بلا سقف: مكتبٌ بدأ
    سنة 2015 يلحق كلَّ ما فات عند أول تشغيل، والسقفُ في التقويم وحده.
    """
    floor = min(
        min(row.starts_on for row in service_rows),
        min(row.responsible_from for row in service_rows),
    )
    periods: list[tuple] = []
    cursor = _first_of_month(floor)
    while cursor <= end:
        period_end = deadlines.month_start_after(cursor, 1) - timedelta(days=1)
        if _document_period_due(
            client, cursor, period_end, service_rows=service_rows, end=end, skip=skip,
        ):
            periods.append((DOCUMENT_CADENCE_MONTHLY, cursor, period_end))
        cursor = deadlines.month_start_after(cursor, 1)
    for year in range(floor.year, end.year + 1):
        period_start = date(year, 1, 1)
        period_end = date(year, 12, 31)
        if _document_period_due(
            client, period_start, period_end,
            service_rows=service_rows, end=end, skip=skip,
        ):
            periods.append((DOCUMENT_CADENCE_ANNUAL, period_start, period_end))
    return periods


def _generate_document_rows(client, *, tenant, service_rows, end, context, skip) -> int:
    """يحفظ قوائم الفترات المستحقّة — **idempotent ولا يعيد كتابة صفّ**.

    الصفوفُ القائمة تُقرأ استعلاماً واحداً لكل زبون (المفاتيح `(كود، بداية)`)،
    والغائبُ وحده يُنشأ بـ`get_or_create` داخل معاملة الزبون في `_refresh_client`.
    """
    known = set(
        DocumentChecklistItem.objects
        .filter(client=client)
        .values_list("item_code", "period_start"),
    )
    created = 0
    for cadence, period_start, period_end in _document_periods(
        client, service_rows, end=end, skip=skip,
    ):
        for item in _document_items_for(
            client, cadence=cadence, period_start=period_start,
            period_end=period_end, context=context, skip=skip,
        ):
            key = (item["item_code"], period_start)
            if key in known:
                continue
            _row, was_created = DocumentChecklistItem.objects.get_or_create(
                client=client,
                item_code=item["item_code"],
                period_start=period_start,
                defaults={
                    "tenant": tenant,
                    "name": item["name"],
                    "service_codes": list(item["service_codes"]),
                    "cadence": cadence,
                    "period_end": period_end,
                    # #279: الحالةُ الابتدائيةُ من البند (بندُ المنصّة وحدها تحملها).
                    "status": item.get("default_status") or DOCUMENT_STATUS_REQUIRED,
                },
            )
            known.add(key)
            if was_created:
                created += 1
    return created


# ── الحالات: مَن ومتى وكيف ──────────────────────────────────────────────────
def set_document_status(
    row, *, status, channel="", actor, day=None,
) -> DocumentChecklistItem:
    """تسجيلُ حالة ورقة — «وصلت» و«وصلت ناقصة» تسألان عن القناة وتكتبان التاريخ.

    **القناةُ إلزاميةٌ لمن وصلت**: «وصلت» بلا «كيف» خبرٌ ناقص، والمكتبُ يسأل عنه
    بعد أسبوعين فلا يجد جواباً. والرجوعُ إلى «مطلوبة» أو «مش لازمة» **يمحو** أثرَ
    الوصول (تاريخاً وفاعلاً وقناة) — صفٌّ ينتظر ورقةً لا يكون مستلَماً.
    """
    if status not in DOCUMENT_STATUS_KEYS:
        raise ValidationError({
            "status": (
                "حالةٌ غير معروفة — مطلوبة أو وصلت ناقصة أو وصلت أو مش لازمة."
            ),
        })
    day = day or timezone.localdate()
    row.status = status
    row.updated_by = actor
    if status in DOCUMENT_RECEIVED_STATUSES:
        clean_channel = (channel or "").strip()
        if clean_channel not in DOCUMENT_CHANNEL_KEYS:
            raise ValidationError({"channel": "كيف وصلت؟ واتساب أو ورق أو إيميل."})
        row.channel = clean_channel
        row.received_on = day
        row.received_by = actor
    else:
        row.channel = ""
        row.received_on = None
        row.received_by = None
    row.save(update_fields=[
        "status", "updated_by", "updated_at",
        "channel", "received_on", "received_by",
    ])
    return row


# ── الملفُّ الاختياريّ: كيانٌ منفصلٌ لا يمسّ الحالة ─────────────────────────
def sniff_document_type(head: bytes):
    """نوعُ المحتوى من بايتاته الأولى — أو `None` لما لا نعرفه."""
    if not head:
        return None
    if head[:4] == b"%PDF":
        return "application/pdf"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_document_size(*, size) -> None:
    """حجمُ الملفّ وحده — يُقرأ من `upload.size` **قبل** أي قراءةٍ لبايتاته.

    الفارغُ والمتجاوزُ للسقف يُرفضان هنا، فلا يدخل ملفُّ ١٠ ميجابايت الذاكرةَ لِيُرفض.
    """
    if not size or size <= 0:
        raise ValidationError({"file": "الملف فارغ."})
    if size > MAX_DOCUMENT_BYTES:
        raise ValidationError({
            "file": "حجم الملف يتجاوز الحد المسموح (١٠ ميجابايت).",
        })


def validate_document_upload(*, size, filename, content_type, head) -> None:
    """التحقّقُ الذي يرفض قبل الكتابة — والحقلُ المرفوض `file`.

    المسموحُ PDF وJPEG وPNG وWEBP بسقف ١٠ ميجابايت، **والامتدادُ يجب أن يطابق
    نوعَ المحتوى المعلَن ثم بايتاتِه الأولى** — فملفٌّ يتسمّى `.pdf` وهو غيرُه
    يُرفض بدل أن يُخزَّن لبساً على من يقرؤه. والبايتاتُ تصل رأساً قصيراً لا ملفاً
    كاملاً (`DOCUMENT_MAGIC_BYTES`) — والحجمُ فُحص قبلها بـ`validate_document_size`.
    """
    validate_document_size(size=size)
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    extension = name[dot:] if dot > 0 else ""
    allowed = DOCUMENT_ALLOWED_EXTENSIONS.get(extension)
    if allowed is None:
        raise ValidationError({
            "file": "نوع الملف غير مسموح. المسموح: PDF أو صورة (JPG/PNG/WEBP).",
        })
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in DOCUMENT_ALLOWED_CONTENT_TYPES:
        raise ValidationError({
            "file": "نوع محتوى الملف غير مسموح. المسموح: PDF أو صورة.",
        })
    if declared not in allowed:
        raise ValidationError({"file": "امتداد الملف لا يطابق نوع محتواه."})
    actual = sniff_document_type(head)
    if actual is None or actual not in allowed:
        raise ValidationError({"file": "محتوى الملف لا يطابق امتداده."})


def document_file_payload(file) -> dict:
    """سطرُ ملفٍّ للعرض — **بلا `file_url`**: الرابطُ لا يخرج في أيّ ردّ."""
    return {
        "id": file.pk,
        "uid": str(file.uid),
        "document_type": file.document_type,
        "issuer_registration": file.issuer_registration,
        "document_date": (
            None if file.document_date is None else file.document_date.isoformat()
        ),
        "document_number": file.document_number,
        "captured_at": file.captured_at.isoformat() if file.captured_at else None,
        "file_name": file.file_name,
        "is_copy": file.is_copy,
        "copy_label": DOCUMENT_FILE_COPY_TAG if file.is_copy else "",
        "created_by_name": user_display_name(file.created_by),
    }


def create_document_file(
    row, *, file_url, file_name="", data=None, actor,
) -> DocumentFile:
    """يحفظ صفَّ الملفَّ بعد أن رُفع — **ولا يمسّ حالة الورقة** (قرار #278/D4).

    الرفعُ نفسه في الـview (فعلٌ يعتمد على مزوّد التخزين)، وهذه الدالّةُ تكتب
    السجلّ وحده: وصفُ נספח ז يأتي من الطلب، ونوعُ المستند افتراضُه اسمُ الورقة.
    """
    data = data or {}
    document_type = (data.get("document_type") or "").strip() or row.name
    file_row = DocumentFile(
        tenant=row.tenant,
        client=row.client,
        checklist_item=row,
        created_by=actor,
        document_type=document_type,
        issuer_registration=(data.get("issuer_registration") or "").strip(),
        document_date=data.get("document_date"),
        document_number=(data.get("document_number") or "").strip(),
        file_url=file_url,
        file_name=(file_name or "")[:255],
        is_copy=bool(data.get("is_copy", True)),
    )
    file_row.save()
    return file_row


def delete_document_file(file) -> str:
    """يحذف السجلَّ **أوّلاً** ويُرجع رابطه — والحذفُ من التخزين بعده بجهدٍ بذل.

    الترتيبُ مقصود: الصفُّ في القاعدة هو المصدرُ الموثوق، وفشلُ مزوّد التخزين لا
    يجوز أن يُبقي صفّاً يشير إلى ملفٍّ لم يعد يُقدَّم. **وحالةُ الورقة لا تتغيّر.**
    """
    url = file.file_url
    file.delete()
    return url


def document_retention_payload(client) -> list[dict]:
    """مددُ حفظ نظام الزبون — بياناتٌ معروضةٌ بنصّها، بلا حساب تاريخٍ في v1."""
    system = resolve_setting(client.tenant, TAX_SYSTEM_KEY, client=client)
    if not system:
        return []
    return [
        {
            "code": row.code,
            "name": row.name,
            "years": row.years,
            "alt_years": row.alt_years,
            "basis": row.basis,
            "basis_label": RETENTION_BASIS_LABELS.get(row.basis, ""),
            "source_url": row.source_url,
            "text": _retention_text(row),
        }
        for row in DocumentRetentionRule.objects
        .filter(tax_system=system)
        .order_by("code")
    ]


def _retention_text(row) -> str:
    """جملةُ المدة كما تُعرض — الصياغةُ هنا وحدها، والواجهةُ ترسم النصّ.

    «الأبعدُ منهما» قاعدةُ §25(ג) الإسرائيلية، فتُقال صريحةً حين يوجد `alt_years`؛
    وغيرُها جملةٌ واحدة: الاسمُ والسنواتُ وأساسُ الحساب.
    """
    if (
        row.alt_years is not None
        and row.basis == RETENTION_BASIS_LATER_OF_YEAR_END_OR_FILING
    ):
        return (
            f"{row.name} — {row.years} سنوات من نهاية السنة أو "
            f"{row.alt_years} من تاريخ التقديم، الأبعد منهما"
        )
    basis = RETENTION_BASIS_LABELS.get(row.basis, "")
    return f"{row.name} — {row.years} سنوات {basis}"


# ── «ناقصه أوراق» وعدّادُ وصل/مطلوب ─────────────────────────────────────────
def document_progress(tenant, obligations) -> dict[int, dict]:
    """تقدّمُ أوراق الالتزامات المنتظِرة — **استعلامان ثابتان** مهما كثرت الصفوف.

    صفوفُ الالتزام O: نفسُ الزبون، وكودُ خدمته داخل `row.service_codes`، والفترةُ
    محتواةٌ في فترته (`period_start >= O.period_start` و`period_end <= O.period_end`).
    و`required` = المحسوبُ بلا «مش لازمة»، و`received` = منه ما وصل، و`missing`
    = فيه صفٌّ «مطلوبة» أو «وصلت ناقصة». **والصفوفُ بلا خدمةٍ لا تُحسب** — لا
    نعرف من يطلبها فلا نُشعل بها شارة.

    **والقراءةُ مقيَّدةٌ بمدى الالتزامات المنتظِرة** (أدنى بدايةٍ وأقصى نهاية)، ثم
    مفهرَسةٌ في الذاكرة على `(الزبون, كود الخدمة)`: كلُّ التزامٍ يمسح دلوه وحده ولا
    يمسح صفوفَ خدمةٍ أخرى، فلا يُقرأ تاريخُ المكتب كلُّه لعدّ شهرٍ واحد.
    """
    pending = [
        row for row in obligations if row.status == OBLIGATION_STATUS_PENDING
    ]
    if not pending:
        return {}
    client_ids = {row.client_id for row in pending}
    index: dict[tuple[int, str], list[tuple]] = {}
    for client_id, period_start, period_end, codes, status in (
        DocumentChecklistItem.objects
        .filter(
            tenant=tenant,
            client_id__in=client_ids,
            period_start__gte=min(row.period_start for row in pending),
            period_end__lte=max(row.period_end for row in pending),
        )
        .values_list(
            "client_id", "period_start", "period_end", "service_codes", "status",
        )
    ):
        for code in set(codes or ()):
            index.setdefault((client_id, code), []).append(
                (period_start, period_end, status),
            )
    service_codes = dict(
        ClientService.objects
        .filter(pk__in={row.client_service_id for row in pending})
        .values_list("pk", "service__code"),
    )
    progress: dict[int, dict] = {}
    for obligation in pending:
        code = service_codes.get(obligation.client_service_id)
        if not code:
            continue
        received = 0
        required = 0
        missing = False
        for period_start, period_end, status in index.get(
            (obligation.client_id, code), (),
        ):
            if period_start < obligation.period_start:
                continue
            if period_end > obligation.period_end:
                continue
            if status == DOCUMENT_STATUS_NOT_NEEDED:
                continue
            required += 1
            if status == DOCUMENT_STATUS_RECEIVED:
                received += 1
            else:
                missing = True
        if not required:
            continue
        progress[obligation.pk] = {
            "received": received,
            "required": required,
            "missing": missing,
        }
    return progress


# ── الحمولات: الشبكة والقائمة السنوية والقالب ──────────────────────────────
def _document_values_payload(row, *, masked) -> dict:
    """حقولُ مبلغ الورقة الأربعة (#286/ج) — **وقرارُ القناع جاهزٌ يُمرَّر**.

    الحقولُ وقناعُها في `client_books` وحدها (`DOCUMENT_VALUE_FIELDS` و
    `document_values_payload`): المبلغان يمرّان بـ`mask_amounts`، والنسبةُ
    والطرفُ يبقيان لأن إخفاءهما يترك الحارسَ بلا وجه. استيرادٌ كسول:
    `client_books` يستورد هذه الوحدة، فالاستيرادُ أعلى الملفّ دورة.
    """
    from accounting_office import client_books

    return client_books.document_values_payload(row, masked=masked)


def _document_cell_payload(row, *, month, masked) -> dict:
    """خانةُ شهرٍ في الشبكة — `row_id=None` تعني «لا صفَّ لهذا البند في الشهر».

    **وحقولُ المبلغ الأربعة تخرج هنا أيضاً**: شبكةُ الأشهر هي مكانُ اختيار
    الورقة وإدخال مبلغها، فبلا هذه الحقول لا تقرأ الشاشةُ مبلغَ ورقةٍ أدخلته
    أمس (#286/ج). والخانةُ الفارغةُ تحملها `null` كي لا يختلف شكلُ الخانة.
    """
    if row is None:
        return {
            "month": month.isoformat(),
            "row_id": None,
            "status": None,
            "status_label": "",
            "received_on": None,
            "received_by_name": "",
            "channel": "",
            "channel_label": "",
            "files_count": 0,
            "amount": None,
            "tax_amount": None,
            "vat_rate": None,
            "side_party": "",
        }
    payload = {
        "month": month.isoformat(),
        "row_id": row.pk,
        "status": row.status,
        "status_label": document_status_label(row.status, row.cadence),
        "received_on": (
            None if row.received_on is None else row.received_on.isoformat()
        ),
        "received_by_name": user_display_name(row.received_by),
        "channel": row.channel,
        "channel_label": DOCUMENT_CHANNEL_LABELS.get(row.channel, ""),
        "files_count": len(list(row.files.all())),
    }
    payload.update(_document_values_payload(row, masked=masked))
    return payload


def document_row_payload(row, *, files=None, user=None, masked=None) -> dict:
    """سطرُ ورقةٍ كاملاً — يُرجع من فعل الحالة، ومن القائمة السنوية.

    **وحقولُ مبلغ الورقة الأربعة (#286/ج) تخرج من هنا**: بلا `amount` في السطر
    لا تقرأ قائمةُ الأوراق مبلغَ الورقة، فلا تُدخل حركةً من ورقها.

    **والقناعُ قرارٌ يُحسب مرّةً واحدة**: `user` يُترجَم إلى قرارٍ بـ
    `client_books.amounts_masked` (سؤالُ الصلاحية أربعةُ استعلاماتٍ إلى خمسة)،
    فقائمةُ ألف صفٍّ تمرّره جاهزاً بـ`masked` بدل ألف سؤال. **وغيابُ الطالب
    يُقنّع**: نداءٌ لا يقول مَن يقرأ لا يخرج له مبلغ — والخطأُ في هذا الاتجاه
    إخفاءُ رقمٍ لا كشفُه.
    """
    if masked is None:
        if user is None:
            masked = True
        else:
            from accounting_office import client_books

            masked = client_books.amounts_masked(row.tenant, user)
    payload = {
        "row_id": row.pk,
        "client_id": row.client_id,
        "item_code": row.item_code,
        "name": row.name,
        "service_codes": list(row.service_codes or []),
        "cadence": row.cadence,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "period_label": deadlines.period_label(row.period_start, row.period_end),
        "status": row.status,
        "status_label": document_status_label(row.status, row.cadence),
        "received_on": (
            None if row.received_on is None else row.received_on.isoformat()
        ),
        "received_by_name": user_display_name(row.received_by),
        "channel": row.channel,
        "channel_label": DOCUMENT_CHANNEL_LABELS.get(row.channel, ""),
        "files_count": len(files) if files is not None else row.files.count(),
    }
    if files is not None:
        payload["files"] = files
    payload.update(_document_values_payload(row, masked=masked))
    return payload


def client_documents_payload(client, *, year, user=None) -> dict:
    """شبكةُ الأشهر × البنود والقائمةُ السنوية — **كلُّ صفٍّ بعدد الأشهر نفسه**.

    `months` = الأشهرُ التي لها صفٌّ واحدٌ على الأقلّ لهذا الزبون في السنة
    (تصاعداً)، وكلُّ بندٍ خانةٌ لكل شهرٍ فيها — `row_id=None` حيث لا صفّ
    (معيار القبول ٥). والبنودُ مرتّبةٌ بترتيب الكتالوج ثم الاسم، والقائمةُ السنوية
    صفوفُ السنة نفسها بدوريتها السنوية وبملفاتها.

    **و`user` لقناع مبالغ الأوراق (#286/ج)**: قرارُ القناع يُحسب هنا مرّةً واحدة
    ويُمرَّر للخانات والسطور، لأن الشبكةَ عشراتُ الصفوف وسؤالُ الصلاحية أربعةُ
    استعلاماتٍ إلى خمسة. وغيابُه يُقنّع (`document_row_payload`) — النداءُ الذي
    لا يعرف قارئَه لا يخرج له مبلغُ ورقة.
    """
    tenant = client.tenant
    # استيرادٌ كسول: `client_books` يستورد هذه الوحدة (كما في `_document_values_payload`).
    from accounting_office import client_books

    masked = True if user is None else client_books.amounts_masked(tenant, user)
    rows = list(
        DocumentChecklistItem.objects
        .filter(
            tenant=tenant, client=client,
            period_start__gte=date(year, 1, 1),
            period_start__lte=date(year, 12, 31),
        )
        .select_related("received_by")
        .prefetch_related("files__created_by")
        .order_by("period_start", "item_code", "id"),
    )
    monthly = [row for row in rows if row.cadence == DOCUMENT_CADENCE_MONTHLY]
    annual = [row for row in rows if row.cadence == DOCUMENT_CADENCE_ANNUAL]
    months = sorted({row.period_start for row in monthly})
    by_key = {(row.item_code, row.period_start): row for row in monthly}
    names: dict[str, str] = {}
    # الأحدثُ يفوز: الصفُّ الأحدثُ يحمل لقطةَ الاسم السارية.
    for row in monthly:
        names[row.item_code] = row.name
    system = resolve_setting(tenant, TAX_SYSTEM_KEY, client=client)
    order = _document_item_order(tenant, system, DOCUMENT_CADENCE_MONTHLY)
    item_codes = sorted(
        names, key=lambda code: (order.get(code, len(order)), names[code]),
    )
    years = sorted(
        {
            value
            for value in (
                DocumentChecklistItem.objects
                .filter(tenant=tenant, client=client)
                .annotate(year=ExtractYear("period_start"))
                .values_list("year", flat=True)
            )
        }
        | {year},
        reverse=True,
    )
    return {
        "client": {"id": client.pk, "name": client.name},
        "year": year,
        "months": [month.isoformat() for month in months],
        "items": [
            {
                "item_code": code,
                "name": names[code],
                "cells": [
                    _document_cell_payload(
                        by_key.get((code, month)), month=month, masked=masked,
                    )
                    for month in months
                ],
            }
            for code in item_codes
        ],
        "annual": [
            document_row_payload(
                row,
                files=[document_file_payload(file) for file in row.files.all()],
                masked=masked,
            )
            for row in annual
        ],
        "retention": document_retention_payload(client),
        "status_choices": document_status_choices(),
        "channel_choices": document_channel_choices(),
        "cadence_choices": document_cadence_choices(),
        "available_years": years,
    }


def document_items_payload(tenant, *, tax_system, client=None) -> dict:
    """قالبُ المكتب: بنداتُ المنصّة وقائمةُ المكتب بحالة «ضمن القائمة».

    و`client` (اختياري) يُضيف `client_included` لكل بندٍ — يستعمله لوحُ
    «تخصيص القائمة» في ملفّ الزبون، فلا تُقرأ الخياراتُ من نسخةٍ ثانية في الواجهة.
    ومعه يُسرد من بنود المكتب **الفعّالُ وحده**: التوليدُ (`_document_catalog`) لا
    يقرأ المعطَّل، فخيارُ الزبون عليه مفتاحٌ لا يغيّر شيئاً. وبلا `client` (قسمُ
    الإعدادات) تُسرد كلُّها ليُعاد تفعيلُ المعطَّل.
    """
    _assert_tax_system(tax_system)
    office_qs = OfficeDocumentItem.objects.filter(
        tenant=tenant, tax_system=tax_system,
    )
    if client is not None:
        office_qs = office_qs.filter(is_active=True)
    office_rows = list(office_qs.order_by("name", "id"))
    choices = dict(
        OfficeDocumentItemChoice.objects
        .filter(tenant=tenant)
        .values_list("item_code", "included"),
    )
    client_choices = (
        {}
        if client is None
        else dict(
            ClientDocumentItemChoice.objects
            .filter(client=client)
            .values_list("item_code", "included"),
        )
    )
    items: list[dict] = []
    for row in (
        PlatformDocumentItem.objects
        .filter(tax_system=tax_system)
        .order_by("sort_order", "name", "id")
    ):
        items.append(_document_item_row_payload(
            row, included=choices.get(row.code, True), is_custom=False,
            client_choices=client_choices, client=client,
        ))
    for row in office_rows:
        items.append(_document_item_row_payload(
            row, included=row.is_active, is_custom=True,
            client_choices=client_choices, client=client,
        ))
    return {
        "system": tax_system,
        "items": items,
        "services": [
            {"code": row.code, "name": row.name}
            for row in (
                OfficeService.objects
                .filter(tenant=tenant, is_active=True)
                .order_by("position", "name", "id")
            )
        ],
        "cadence_choices": document_cadence_choices(),
        "condition_fields": sorted(DOCUMENT_CARD_CONDITION_FIELDS),
    }


def _document_item_row_payload(
    row, *, included, is_custom, client_choices, client,
) -> dict:
    """سطرُ بندٍ في القالب — واحدٌ لبند المنصّة وبند المكتب.

    **`id` فضاءُ بنود المكتب وحدها**: `OfficeDocumentItemViewSet` يحلّ المعرّف في
    `OfficeDocumentItem`، فبندُ المنصّة يعطي `id=None` بدل معرّفٍ يُحلّ إلى صفٍّ آخر.
    """
    payload = {
        "id": row.pk if is_custom else None,
        "item_code": row.code,
        "name": row.name,
        "cadence": row.cadence,
        "cadence_label": DOCUMENT_CADENCE_LABELS.get(row.cadence, ""),
        "service_codes": list(row.service_codes or []),
        "card_conditions": dict(row.card_conditions or {}),
        "included": included,
        "is_custom": is_custom,
        "is_active": getattr(row, "is_active", True),
        "sort_order": getattr(row, "sort_order", None),
    }
    if client is not None:
        payload["client_included"] = client_choices.get(row.code)
    return payload


def _office_document_item_from_code(tenant, code):
    """بندُ مكتبٍ من كوده المشتقّ `office_doc_<pk>` — أو `None`."""
    prefix = "office_doc_"
    if not code.startswith(prefix):
        return None
    try:
        pk = int(code[len(prefix):])
    except (TypeError, ValueError):
        return None
    return OfficeDocumentItem.objects.filter(tenant=tenant, pk=pk).first()


def document_item_system(tenant, code) -> str:
    """نظامُ بندٍ من كوده — من المنصّة أو من بنود المكتب، أو `""` لما لا يُعرف.

    يقرؤه فعلُ اختيار المكتب ليُرجع قائمةَ النظام المحدَّثة، فلا تُمرَّر النسخةُ
    الثانية من «أيّ نظامٍ هذا البند» في الـview.
    """
    system = (
        PlatformDocumentItem.objects.filter(code=code)
        .values_list("tax_system", flat=True)
        .first()
    )
    if system:
        return system
    row = _office_document_item_from_code(tenant, code)
    return row.tax_system if row is not None else ""


def _assert_document_item_code(tenant, tax_system, code) -> None:
    """الكودُ بندٌ معروفٌ لهذا المكتب — من المنصّة أو من قائمته."""
    if PlatformDocumentItem.objects.filter(
        tax_system=tax_system, code=code,
    ).exists():
        return
    if _office_document_item_from_code(tenant, code) is not None:
        return
    raise ValidationError({"item_code": "بندٌ غير معروف في قائمة الأوراق."})


def _clean_document_service_codes(tenant, service_codes) -> list[str]:
    """أكوادُ خدماتٍ معروفةٌ لكتالوج المكتب — لا كودَ مخترَع."""
    if service_codes is None:
        return []
    if not isinstance(service_codes, (list, tuple)):
        raise ValidationError({"service_codes": "الخدمات قائمةُ أكواد."})
    codes = [str(code).strip() for code in service_codes if str(code).strip()]
    known = set(
        OfficeService.objects.filter(tenant=tenant).values_list("code", flat=True),
    )
    unknown = sorted(set(codes) - known)
    if unknown:
        raise ValidationError({
            "service_codes": f"خدمات غير معروفة في الكتالوج: {unknown}",
        })
    return list(dict.fromkeys(codes))


def set_office_document_choice(tenant, *, item_code, included, actor):
    """«ضمن القائمة» على بندٍ في قالب المكتب — صفٌّ يُقلب ولا يُحذف.

    **بندُ المكتب لا يُقلَب من هنا**: «مفعَّل/معطَّل» له مصدرٌ واحد (`is_active` في
    `update_office_document_item`)، ولو قُبل هنا لصار له مصدران يقولان شيئين.
    """
    code = (item_code or "").strip()
    if not code:
        raise ValidationError({"item_code": "كود البند مطلوب."})
    if code.startswith("office_doc_"):
        raise ValidationError({"item_code": "بندُ المكتب يُفعَّل ويُعطَّل من قائمته"})
    if not PlatformDocumentItem.objects.filter(code=code).exists():
        raise ValidationError({"item_code": "بندٌ غير معروف في قائمة الأوراق."})
    row, _created = OfficeDocumentItemChoice.objects.update_or_create(
        tenant=tenant,
        item_code=code,
        defaults={"included": bool(included), "updated_by": actor},
    )
    return row


def set_client_document_choice(client, *, item_code, included, actor):
    """خيارُ الزبون على بندٍ — **يغلب قالب المكتب وشروطَ القانون**."""
    code = (item_code or "").strip()
    if not code:
        raise ValidationError({"item_code": "كود البند مطلوب."})
    system = resolve_setting(client.tenant, TAX_SYSTEM_KEY, client=client)
    if system:
        _assert_document_item_code(client.tenant, system, code)
    elif _office_document_item_from_code(client.tenant, code) is None:
        raise ValidationError({"item_code": "بندٌ غير معروف في قائمة الأوراق."})
    row, _created = ClientDocumentItemChoice.objects.update_or_create(
        client=client,
        item_code=code,
        defaults={
            "tenant": client.tenant,
            "included": bool(included),
            "updated_by": actor,
        },
    )
    return row


def create_office_document_item(
    tenant, *, tax_system, name, cadence, service_codes=None,
    is_active=True, actor,
) -> OfficeDocumentItem:
    """بندٌ يضيفه المكتب — بشروطه الفارغة افتراضاً، ويُعطَّل ولا يُحذف."""
    _assert_tax_system(tax_system)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError({"name": "اسم البند مطلوب."})
    if cadence not in DOCUMENT_CADENCE_KEYS:
        raise ValidationError({"cadence": "الدورية شهري أو سنوي."})
    return OfficeDocumentItem.objects.create(
        tenant=tenant,
        tax_system=tax_system,
        name=clean_name,
        cadence=cadence,
        service_codes=_clean_document_service_codes(tenant, service_codes),
        card_conditions={},
        is_active=bool(is_active),
        created_by=actor,
    )


def update_office_document_item(
    row, *, name=None, cadence=None, service_codes=None, is_active=None,
) -> OfficeDocumentItem:
    """تعديلُ بند مكتب — والغيابُ لا يمسّ شيئاً."""
    fields: list[str] = []
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError({"name": "اسم البند مطلوب."})
        row.name = clean_name
        fields.append("name")
    if cadence is not None:
        if cadence not in DOCUMENT_CADENCE_KEYS:
            raise ValidationError({"cadence": "الدورية شهري أو سنوي."})
        row.cadence = cadence
        fields.append("cadence")
    if service_codes is not None:
        row.service_codes = _clean_document_service_codes(row.tenant, service_codes)
        fields.append("service_codes")
    if is_active is not None:
        row.is_active = bool(is_active)
        fields.append("is_active")
    if fields:
        fields.append("updated_at")
        row.save(update_fields=fields)
    return row


# ── التذكيرات والرسائل (#280) ───────────────────────────────────────────────
#
# **قاعدةُ الموديول نفسها**: ما يختلف من مكتبٍ لمكتب = إعداد، وما يختلف من زبونٍ
# لزبون = تخصيصٌ فوقه. إيقاعُ التذكير (أوّلُ يومٍ، والمسافةُ بين تذكيرين، والحدُّ
# الأقصى) ثلاثةُ إعداداتٍ تُقرأ من المحلّل — لا أرقامَ في الكود تلزم من لم يطلبها.
#
# **ولا يُخزَّن «متى التذكير القادم»**: يُحسب من السجلّ والإعداد عند كل قراءة
# (`_reminder_candidates`). تخزينُه كان يحتاج مهمةً تُحدّثه كلَّ يوم، وتصحيحُ
# إعدادٍ كان يترك المواعيد القديمة على حالها. الحسابُ عند القراءة يعني أن
# إطفاءَ بندٍ أو تغييرَ الإيقاع يسري فوراً، وأن يومَ العطلة يُزحزح الظهورَ لا
# يُلغي التذكير.
#
# **والتاريخُ يُمرَّر صريحاً** (`day`) من الـview في كل دالّةٍ عامة، فلا ساعةَ في
# الخدمة تُفاجئ الاختبار.

REMINDER_TYPES_ENABLED_KEY = "reminder_types_enabled"
REMINDER_AUTO_SEND_KEY = "reminder_auto_send"
REMINDER_MERGE_DAILY_KEY = "reminder_merge_daily"
DOCUMENTS_REMINDER_START_DAYS_KEY = "documents_reminder_start_days"
DOCUMENTS_REMINDER_INTERVAL_DAYS_KEY = "documents_reminder_interval_days"
DOCUMENTS_REMINDER_MAX_KEY = "documents_reminder_max"
REMINDER_SEND_HOUR_START_KEY = "reminder_send_hour_start"
REMINDER_SEND_HOUR_END_KEY = "reminder_send_hour_end"
REMINDER_ESCALATION_OWNER_DAYS_KEY = "reminder_escalation_owner_days"
REMINDER_DEFAULT_CONSENT_TYPES_KEY = "reminder_default_consent_types"
#: #281: قبل كم يومٍ يُذكَّر الموعد — يُقرأ في المسحة نفسها (`_REMINDER_CLIENT_KEYS`)
#: ويُشتقّ منه اسمُه في `appointments`، فلا مفتاحان لنفس الإعداد.
APPOINTMENT_REMINDER_DAYS_KEY = "appointment_reminder_days"
#: #285: إعداداتُ «إشعار الدفع» الثلاثة — تُقرأ **لكل زبون** في مسحة الحساب نفسها
#: (`_REMINDER_CLIENT_KEYS`): إطفاءُ الإرفاق لزبونٍ واحد لا يمرّ بقراءةٍ ثانية،
#: والحدُّ الرماديُّ يخصّ زبونَه وحده.
PAYMENT_NOTICE_ATTACH_KEY = "payment_notice_attach"
PAYMENT_NOTICE_FORMAT_KEY = "payment_notice_format"
PAYMENT_NOTICE_GRAY_THRESHOLD_KEY = "payment_notice_gray_threshold"
#: #283/ج: حجبُ التسليم حتى الدفع — إعدادُ مكتبٍ مطفأٌ افتراضاً، وعلامتُه الواحدة
#: ورسالةُ رفضه. الثلاثةُ هنا لأن الحمولةَ (`payments.client_dues_payload`) والحارسَ
#: (`mark_client_delivered`) يقرؤون نصّاً واحداً لا نسختين تفترقان.
DELIVERY_HOLD_UNPAID_KEY = "delivery_hold_unpaid"
DELIVERY_HELD_LABEL = "لم يُسلَّم بعد"
DELIVERY_HOLD_MESSAGE = (
    "الزبون عليه رصيد — «حجب التسليم حتى الدفع» مفعّل، "
    "فلا يُعلَّم «تم التسليم» قبل سداد كامل رصيده."
)
#: والصيغتان مُشتقّتان من السجلّ — لا نسختان تفترقان عند إضافة صيغةٍ ثالثة.
PAYMENT_NOTICE_FORMAT_PDF = settings_registry.PAYMENT_NOTICE_FORMAT_PDF
PAYMENT_NOTICE_FORMAT_BOTH = settings_registry.PAYMENT_NOTICE_FORMAT_BOTH

#: رسالةُ القفل — ثابتٌ واحدٌ يقارنه الاختبار وتقرؤه الواجهة كما هو.
REMINDER_AUTO_SEND_LOCKED = "الإرسال التلقائي غير متاح قبل المرحلة الثانية"

#: إعداداتٌ **مطفأةٌ بقرار**: قيمتُها تُخزَّن `False` وحده، وأيُّ قيمةٍ أخرى
#: تُرفَض برسالتها. بابٌ واحدٌ للفتح لاحقاً: حذفُ المفتاح من هنا في تذكرة المرحلة
#: الثانية — لا مسارٌ ثانٍ في الـview.
LOCKED_SETTING_MESSAGES: dict[str, str] = {
    REMINDER_AUTO_SEND_KEY: REMINDER_AUTO_SEND_LOCKED,
    # #282: الاعتمادُ التلقائيُّ لمسودّات الأتعاب مقفلٌ مطفأً — المسودّةُ يراها
    # صاحبُ المكتب أو مديرُ المكتب قبل اعتمادها.
    FEE_AUTO_APPROVE_KEY: FEE_AUTO_APPROVE_LOCKED,
    # #290: مجموعتُه «التشغيل والنسخ» — الفوترةُ الرسمية والإرسالُ التلقائي
    # يُعرضان مطفأين ويُرفضان: قرارُ مرحلةٍ لا قرارُ مكتب، والرسالةُ واحدةٌ
    # تقول «يُفتح بقرارٍ من المنصة» بدل «غير متاحٍ بعد» المبهمة.
    OPERATIONS_OFFICIAL_INVOICING_KEY: settings_registry.LOCKED_SETTING_NOTE,
    OPERATIONS_AUTO_SEND_KEY: settings_registry.LOCKED_SETTING_NOTE,
}

#: زوجُ النافذة (`setting.key` ← نظيرُه): بدايةٌ لا تلحق نهايتَها. **والطرفان في
#: الخريطة**: كتابةُ أحدهما تُقارَن بالآخر، وإلا قُبلت بدايةُ 20 على نهاية 19.
_SEND_WINDOW_PREVIOUS: dict[str, str] = {
    REMINDER_SEND_HOUR_END_KEY: REMINDER_SEND_HOUR_START_KEY,
    REMINDER_SEND_HOUR_START_KEY: REMINDER_SEND_HOUR_END_KEY,
}


def _assert_locked_setting(key, value) -> None:
    """إعدادٌ مطفأٌ بقرار يرفض أيّ قيمةٍ غير المطفأة — برسالةٍ واحدةٍ معلَنة."""
    message = LOCKED_SETTING_MESSAGES.get(key)
    if message is None or value is False:
        return
    raise ValidationError({"value": message})


def _assert_send_window(tenant, key, value) -> None:
    """النافذةُ زوجٌ مرتَّب: طرفٌ يلحق الآخرَ همٌّ يُقصّ بصمت — يُرفَض صراحةً.

    **والفحصُ متساوٍ على الطرفين**: فحصُ النهاية وحدها يقبل بدايةَ 20 على نهاية
    19، فتُكتب نافذةٌ لا وجودَ لها. والرسالةُ واحدةٌ للحالتين وتدلّ على الاتجاهين.
    """
    other_key = _SEND_WINDOW_PREVIOUS.get(key)
    if other_key is None:
        return
    other = resolve_setting(tenant, other_key)
    if not isinstance(other, int):
        return
    if key == REMINDER_SEND_HOUR_START_KEY:
        start, end = value, other
    else:
        start, end = other, value
    if start >= end:
        raise ValidationError({
            "value": (
                "بداية نافذة الإرسال قبل نهايتها — اختر ساعةً «أبكر» للنهاية "
                "أو «أبعد» للبداية."
            ),
        })


# ── الموافقة على التذكير (#280/D2) ──────────────────────────────────────────
def _clean_consent_types(types) -> list[str]:
    if types is None:
        return []
    if not isinstance(types, (list, tuple)):
        raise ValidationError({"types": "الأنواع تُرسَل قائمةً."})
    clean = list(types)
    for reminder_type in clean:
        if reminder_type not in REMINDER_TYPES:
            raise ValidationError({
                "types": f"نوع تذكير غير معروف: {reminder_type}.",
            })
    return [key for key in REMINDER_TYPES if key in set(clean)]


def _clean_consent_channel(channel) -> str:
    value = (channel or "").strip()
    if value and value not in CONSENT_CHANNEL_LABELS:
        raise ValidationError({
            "channel": f"قناةُ إذنٍ غير معروفة: {value}.",
        })
    return value


def set_contact_consent(
    contact, *, consent, types=None, channel="", actor, day=None,
) -> Contact:
    """يُسجَّل الإذنُ بالتاريخ والطريق — والسحبُ لا يمحو الإذن.

    الإذن: `consent_on` و`consent_channel` ويُمسح أثرُ السحب. والسحبُ:
    `consent_withdrawn_on` و`consent_withdrawn_by` ويبقى تاريخُ الإذن قارئاً.
    و`types=None` في الإذن يعني «أبقِ الأنواع الحالية» — تعديلُ القناة وحدها
    لا يُعيد كتابة ما وافق عليه.
    """
    day = day or timezone.localdate()
    clean_types = _clean_consent_types(types)
    clean_channel = _clean_consent_channel(channel)
    fields = ["reminders_consent", "updated_at"]
    if consent:
        contact.reminders_consent = True
        if types is not None:
            contact.consent_types = clean_types
        elif not contact.consent_types:
            contact.consent_types = resolve_setting(
                contact.tenant, REMINDER_DEFAULT_CONSENT_TYPES_KEY,
            ) or []
        contact.consent_on = day
        contact.consent_channel = clean_channel
        contact.consent_withdrawn_on = None
        contact.consent_withdrawn_by = None
        fields += [
            "consent_types", "consent_on", "consent_channel",
            "consent_withdrawn_on", "consent_withdrawn_by",
        ]
    else:
        contact.reminders_consent = False
        contact.consent_withdrawn_on = day
        contact.consent_withdrawn_by = actor
        fields += ["consent_withdrawn_on", "consent_withdrawn_by"]
    contact.save(update_fields=fields)
    return contact


def contact_consent_payload(contact) -> dict:
    """جوابُ «بتحب نذكّرك؟» كما يُعرض ويُعدَّل — مسمّىً لا أرقاماً."""
    return {
        "contact_id": contact.pk,
        "name": contact.name,
        "reminders_consent": contact.reminders_consent,
        "consent_types": list(contact.consent_types or []),
        "consent_types_labels": [
            REMINDER_TYPE_LABELS[key]
            for key in (contact.consent_types or [])
            if key in REMINDER_TYPE_LABELS
        ],
        "consent_on": None if contact.consent_on is None else contact.consent_on.isoformat(),
        "consent_channel": contact.consent_channel,
        "consent_channel_label": CONSENT_CHANNEL_LABELS.get(contact.consent_channel, ""),
        "consent_withdrawn_on": (
            None if contact.consent_withdrawn_on is None
            else contact.consent_withdrawn_on.isoformat()
        ),
        "consent_withdrawn_by": (
            None if contact.consent_withdrawn_by_id is None
            else {
                "id": contact.consent_withdrawn_by_id,
                "name": user_display_name(contact.consent_withdrawn_by),
            }
        ),
        "type_choices": [
            {"value": key, "label": label} for key, label in REMINDER_TYPE_CHOICES
        ],
        "channel_choices": [
            {"value": key, "label": label}
            for key, label in sorted(CONSENT_CHANNEL_LABELS.items())
        ],
    }


def create_contact(tenant, *, name, phone="", language="ar") -> Contact:
    """جهةٌ جديدة **بأنواع الإذن الافتراضية للمكتب** — لا بقائمةٍ في الكود.

    تُقرأ مرّةً هنا عند الإنشاء وتُنسَخ على الصفّ؛ تغييرُ الإعداد بعدها لا يعيد
    كتابة مَن أذن قبله (الإذنُ فعلُ شخصٍ بتاريخه لا قيمةَ إعدادٍ تتبدّل).
    """
    if language not in dict(Contact.LANGUAGE_CHOICES):
        raise ValidationError({"language": "لغة غير معروفة."})
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError({"name": "الاسم مطلوب."})
    return Contact.objects.create(
        tenant=tenant,
        name=clean_name,
        phone=(phone or "").strip(),
        language=language,
        consent_types=resolve_setting(tenant, REMINDER_DEFAULT_CONSENT_TYPES_KEY) or [],
    )


# ── النصوص: الافتراضي في الكود وبديلُ المكتب (#280/D3) ───────────────────────
#: كلمةُ «لا شيء» بلغة المستلِم — تُوضع مكان قيمةٍ غائبة (`{amount}` بلا مبلغ،
#: `{missing_list}` بلا أوراقٍ ناقصة) في نصٍّ مسطَّحٍ لا يحذف عنوانه: بدونها يبقى
#: العنوانُ معلَّقاً («أوراق ناقصة: ») أو يظهر فراغٌ مزدوج.
REMINDER_ABSENT_TEXT: dict[str, str] = {"ar": "ولا شي", "he": "אין"}


def reminder_absent_text(language) -> str:
    """«لا شيء» بلغة المستلِم — **عُرفٌ واحدٌ لكل نوع** (أوراقٌ وموعدٌ ورسميّ).

    العربيةُ احتياطاً: لغةٌ خارج الاثنتين كانت تُعيد عنواناً بلا قيمةٍ (وكانت
    العناوينُ المعلَّقة هي العلّةَ التي أُعيدت الصياغةُ من أجلها).
    """
    return REMINDER_ABSENT_TEXT.get(language) or REMINDER_ABSENT_TEXT["ar"]


def render_reminder_body(body, values) -> str:
    """يستبدل الرموزَ المعروفة ويترك ما سواها كما هو (بلا `str.format`).

    **`str.format` ممنوع على نصٍّ يكتبه المستخدم**: قوسٌ واحدٌ زائد يُسقط الطلب
    500، و`{0}` أو `{office_name!r}` بابٌ لقراءة ما لا يُقصد. فالاستبدالُ هنا
    `str.replace` على الستّة المعتمدة وحدها، وما ليس منها يبقى نصّاً حرفياً.
    """
    rendered = body or ""
    for placeholder in REMINDER_PLACEHOLDERS:
        rendered = rendered.replace(
            "{" + placeholder + "}", str(values.get(placeholder, "") or ""),
        )
    return rendered


def validate_reminder_body(body) -> str:
    """نصُّ قالبٍ صالح: غيرُ فارغٍ، وكلُّ `{…}` فيه من الستّة المعتمدة.

    والرفضُ يسمّي الرمزَ المجهول — «نصٌّ غير صالح» لا تدلّ كاتبَه على خطئه.
    """
    text = (body or "").strip()
    if not text:
        raise ValidationError({"body": "نصُّ التذكير مطلوب."})
    for match in re.finditer(r"\{([^{}]*)\}", text):
        if match.group(1) not in REMINDER_PLACEHOLDERS:
            raise ValidationError({
                "body": f"رمزٌ غير معروف في النص: {{{match.group(1)}}}.",
            })
    return text


def _assert_reminder_type(reminder_type) -> str:
    if reminder_type not in REMINDER_TYPES:
        raise ValidationError({"reminder_type": "نوع تذكير غير معروف."})
    return reminder_type


def _assert_reminder_language(language) -> str:
    if language not in REMINDER_LANGUAGES:
        raise ValidationError({"language": "لغة تذكير غير معروفة."})
    return language


def reminder_templates_payload(tenant) -> dict:
    """كلُّ نوعٍ في كل لغة: النصَّ الفعليَّ والافتراضيَّ وعلمَ التخصيص.

    صفٌّ واحدٌ لكل زوج (نوع × لغة) — والواجهةُ تعرضها شبكةً بلا حسابٍ فيها.
    والقائمةُ تُقرأ لكل عضوٍ: معرفةُ ما سيُرسَل ليست صلاحيةَ إعدادات.
    """
    overrides = {
        (row.reminder_type, row.language): row
        for row in ReminderTemplate.objects.filter(tenant=tenant)
    }
    rows = []
    for reminder_type, type_label in REMINDER_TYPE_CHOICES:
        for language, language_label in REMINDER_LANGUAGE_CHOICES:
            override = overrides.get((reminder_type, language))
            default_body = REMINDER_DEFAULT_TEXTS.get(reminder_type, {}).get(language, "")
            rows.append({
                "reminder_type": reminder_type,
                "reminder_type_label": type_label,
                "language": language,
                "language_label": language_label,
                "body": override.body if override is not None else default_body,
                "default_body": default_body,
                "is_custom": override is not None,
                "updated_at": (
                    None if override is None else override.updated_at.isoformat()
                ),
                "updated_by": (
                    None if override is None or override.updated_by_id is None
                    else user_display_name(override.updated_by)
                ),
            })
    return {"placeholders": list(REMINDER_PLACEHOLDERS), "rows": rows}


def set_reminder_template(
    tenant, *, reminder_type, language, body, actor,
) -> ReminderTemplate:
    """بديلُ المكتب — يُتحقَّق نصُّه ثم يُكتب صفّاً واحداً لكل (نوع، لغة)."""
    _assert_reminder_type(reminder_type)
    _assert_reminder_language(language)
    clean_body = validate_reminder_body(body)
    row, _created = ReminderTemplate.objects.update_or_create(
        tenant=tenant,
        reminder_type=reminder_type,
        language=language,
        defaults={"body": clean_body, "updated_by": actor},
    )
    return row


def reset_reminder_template(tenant, *, reminder_type, language) -> None:
    """«ارجع للافتراضي» = **حذفُ البديل** لا كتابةُ الافتراضيِّ مكانه."""
    _assert_reminder_type(reminder_type)
    _assert_reminder_language(language)
    ReminderTemplate.objects.filter(
        tenant=tenant, reminder_type=reminder_type, language=language,
    ).delete()


# ── الحساب عند القراءة (#280/D5–D9) ──────────────────────────────────────────
@dataclass(frozen=True)
class ReminderCandidate:
    """تذكيرٌ **مستحقٌّ الآن** لزبونٍ في فترة — نتيجةُ حسابٍ لا صفٌّ محفوظ."""

    client: Any
    reminder_type: str
    period_start: Any
    period_end: Any
    missing: tuple[str, ...]
    missing_codes: tuple[str, ...]
    #: `count`/`maximum` = خانةُ «س من ن» في البند، ومعناها بحسب الإيقاع: للأوراق
    #: عدُّ الصفوف الصادرة من حدِّها، وللموعد صفوفُ نافذته السارية من سقفها (١)،
    #: وللموعد الرسميّ موضعُ نافذته من موضعَي (7، 2) — والسقفُ هنا بنيويّ.
    count: int
    maximum: int
    interval_days: int
    next_due: Any
    contact: Any
    #: نظامُ **الزبون صاحب البند** الضريبيّ — يُقرأ مع إعداداته في المسحة نفسها،
    #: ويرافق البندَ إلى الواجهة لأنها تبني منه رابطَ الواتساب (`wa.me` يريد
    #: مفتاحَ دولة، والأرضيُّ لا يُعرف مفتاحُه إلا من النظام) — #280/ب.
    tax_system: Any
    due: bool
    exhausted: bool
    postponed: bool
    #: مفتاحُ شارة البند كما تلوّنه «جاهز للإرسال»: لكل مولّدٍ شارته — نقصُ
    #: الأوراق لنوع الأوراق، و«قريب» لموعدٍ اقترب (موعدُ الزبون أو موعدُ التقديم).
    badge: str = OBLIGATION_BADGE_MISSING_DOCS
    #: اليومُ الذي يُطبع في `{due_date}`: لموعد التقديم تاريخُ تقديمه، وللموعد
    #: تاريخُه، وللأوراق تذكيرُها القادم — وكان هذا الأخير يُحسب في العرض وحده.
    render_due: Any = None
    #: تسميةُ الفترة حين لا تكون فترةً شهرية — «04/05/2026 10:30» لموعدٍ بيومه
    #: ووقته، وغيابُها يعني تسميةَ الفترة المحسوبة (`deadlines.period_label`).
    period_text: str | None = None
    #: المستحقُّ على الزبون في هذه الفترة — `None` حيث لا مبلغَ (أوراقٌ وموعد).
    #: مجموعُ التزامات الفترة في مولّد «موعد رسمي قريب» وحده (#281).
    amount: Decimal | None = None
    #: #285: إشعارُ الدفع المركَّبُ على بند «موعد رسمي قريب» — أسطرٌ ومجموعٌ واتجاه
    #: ورابط. `None` لبندٍ لا إشعارَ له: نوعُ تذكيرٍ آخر، أو زبونٌ أُطفئ إرفاقُه.
    #: ويُركَّب في `ready_to_send_payload` بعد الحواجز كلّها، فلا إشعارَ — ولا
    #: رابطَ يُنشَأ — لبندٍ لن يُرسَل.
    notice: Any = None
    #: #283/ب: سطرُ تفصيلٍ يكتبه الخادم ويُلحَق بنصّ البند بعد نصّ نوعه — إشعارُ
    #: القبض يحمل فيه رقمَه ومبلغَه وباقي الزبون. لا رمزَ جديداً في
    #: `REMINDER_PLACEHOLDERS` ولا قالبَ مكتبٍ يكتب أرقاماً ليست له.
    detail: str = ""
    #: #283/ب: تفصيلُ الإشعار المنظَّم كما يقرؤه البند في «جاهز للإرسال»
    #: (معرّفاتُ الدفعات وأرقامُها ومبلغُها وباقيها) — `None` لغير هذا النوع.
    receipt: Any = None
    #: #282/أ٢: فاتورةُ الأتعاب المركَّبةُ على بند «اللي عليه» — رقمُها ومبلغُها
    #: واستحقاقُها ورابطُ ورقتها. `None` لبندٍ ليس فاتورة (أوراقٌ ومواعيد).
    #: ويُركَّب الرابطُ في `attach_invoice_links` بعد الحواجز كالإشعار.
    invoice: Any = None
    #: #283/ج: كشفُ الشهر المركَّبُ على بند «اللي عليه» — نافذتُه أوّلاً، ثم أرقامُ
    #: `payments.statement_payload` عند بناء الرسالة (لا قبل الحواجز). وبندٌ لا
    #: كشفَ له يبقى `None`، ومفتاحُه في البند كسائر المفاتيح كي يقرأه القالبُ دائماً.
    statement: Any = None


#: الإعداداتُ التي تُقرأ لكل زبونٍ في مسحةٍ واحدةٍ (`resolve_settings_for_clients`) —
#: لا استعلامان لكل مفتاح، ولا محلّلٌ موازٍ يُعيد ترتيبَ القراءة بلا حارسيها.
_REMINDER_CLIENT_KEYS: tuple[str, ...] = (
    REMINDER_TYPES_ENABLED_KEY,
    DOCUMENTS_REMINDER_START_DAYS_KEY,
    DOCUMENTS_REMINDER_INTERVAL_DAYS_KEY,
    DOCUMENTS_REMINDER_MAX_KEY,
    APPOINTMENT_REMINDER_DAYS_KEY,
    # #285: إعداداتُ إشعار الدفع الثلاثة في المسحة نفسها — الإرفاقُ يُقرأ لكل
    # زبون (د6) والحدُّ الرماديُّ يخصّه، فقراءةٌ ثانية لكل مفتاح كانت تضاعف
    # الاستعلامات وتُخالف ترتيب الحلّ الذي حُجب به الحساب.
    PAYMENT_NOTICE_ATTACH_KEY,
    PAYMENT_NOTICE_FORMAT_KEY,
    PAYMENT_NOTICE_GRAY_THRESHOLD_KEY,
    "rest_days",
    # #280/ب: نظامُ الزبون لبند رسالته — يُقرأ في المسحة نفسها، فإضافةُ حقلٍ إلى
    # البند لا تكلّف استعلاماً لكل بند. **ولا يُخمَّن نظامٌ واحدٌ للمستلِم**:
    # رسالةُ شخصٍ قد تجمع بندَي زبونين بنظامين مختلفين.
    TAX_SYSTEM_KEY,
)


def _reminder_contacts(tenant, clients, reminder_types) -> dict[tuple[int, str], Any]:
    """المستلِمُ الفعليُّ لكل (زبون، نوع) — **استعلامان** لا استعلامان لكل زوج.

    نفسُ قاعدة `resolve_reminder_recipient`: التعيينُ إن وُجد، وإلا الرئيسية.
    """
    client_ids = [client.pk for client in clients]
    assigned = {
        (row.client_id, row.reminder_type): row.client_contact
        for row in (
            ClientReminderRecipient.objects
            .filter(
                tenant=tenant,
                client_id__in=client_ids,
                reminder_type__in=list(reminder_types),
            )
            .select_related("client_contact__contact")
        )
    }
    primary = {
        row.client_id: row
        for row in (
            ClientContact.objects
            .filter(tenant=tenant, client_id__in=client_ids, is_primary=True)
            .select_related("contact")
        )
    }
    contacts = {}
    for client_id in client_ids:
        for reminder_type in reminder_types:
            link = assigned.get((client_id, reminder_type)) or primary.get(client_id)
            contacts[(client_id, reminder_type)] = None if link is None else link.contact
    return contacts


def _reminder_log_day(row):
    """يومُ الصفّ — من لحظته المحلّية، فالإيقاعُ يُقاس بأيام العين لا بـUTC.

    والصفوفُ تصل قواميسَ من `.values()` لا كائنات (استعلامُ المسحة الواحد).
    """
    return timezone.localdate(row["created_at"])


def reminder_template_bodies(tenant, reminder_type) -> dict[str, str]:
    """نصوصُ مكتبٍ لنوعٍ في لغاته — **استعلامٌ واحد** يُمرَّر لبناء الرسائل."""
    overrides = {
        row.language: row.body
        for row in ReminderTemplate.objects.filter(
            tenant=tenant, reminder_type=reminder_type,
        )
    }
    return {
        language: overrides.get(
            language, REMINDER_DEFAULT_TEXTS.get(reminder_type, {}).get(language, ""),
        )
        for language, _label in REMINDER_LANGUAGE_CHOICES
    }


#: الأنواعُ التي لها **مولّدٌ** اليوم: الأوراق (#280)، وتذكيرُ الموعد، و«موعد
#: رسمي قريب» (#281)، و«اللي عليه» من فواتير الأتعاب (#282/أ٢)، وإشعارُ القبض
#: (#283/ب). والرابعُ كان بقالبٍ وإعدادٍ بلا مولّدٍ حتى صار له أوّله — فاتورةٌ
#: صادرةٌ تُطالب بمبلغها.
_GENERATED_REMINDER_TYPES: tuple[str, ...] = (
    REMINDER_DOCUMENTS, REMINDER_APPOINTMENT, REMINDER_DEADLINE, REMINDER_BALANCE,
    REMINDER_FEE_RECEIPT,
)


def _appointments_module():
    """الوحدةُ الجارة (#281) — **استيرادٌ مؤجَّل** يفكّ دورةً حقيقيّة.

    `appointments` يستورد `services` في أعلاه (المحلّلُ والرؤيةُ والسجلّ)، فلو
    استوردها هذا الملفُّ في أعلاه لدارت الدورةُ عند أوّل تحميل. والنداءُ هنا وقتَ
    الحاجة فقط، فلا ترتيبُ تحميلٍ يفترق.
    """
    from accounting_office import appointments

    return appointments


def _payments_module():
    """وحدةُ الدفعات (#283/ب) — استيرادٌ مؤجَّلٌ لدورةٍ حقيقيّة كذلك.

    `payments` يستورد `services` في أعلاه (المحلّلُ والقناعُ)، فاستيرادُه هنا في
    الأعلى يُدير الدورةَ عند أوّل تحميل. والنداءُ في `_reminder_candidates` وحده.
    """
    from accounting_office import payments

    return payments


def _fee_invoices_module():
    """وحدةُ فاتورة الأتعاب (#282/أ٢) — **استيرادٌ مؤجَّل** للسبب نفسه.

    `fee_invoices` يستورد `services` (الرؤيةُ والقناعُ و`ReminderCandidate`)،
    فالنداءُ وقتَ الحاجة فقط.
    """
    from accounting_office import fee_invoices

    return fee_invoices


def _reminder_candidates(
    tenant, clients, *, day, settings_by_client, reminder_type=None,
) -> list:
    """المستحقُّ لكل (زبون، نوع، فترة) — **كلفةٌ ثابتة** لا تكبر بعدد الزبائن.

    **ثلاثةُ مولّداتٍ في مسحةٍ واحدة** (#281): الأوراقُ الناقصة (هنا)، وتذكيرُ
    الموعد، و«موعد رسمي قريب» (في `appointments`) — كلُّها تُرجع
    `ReminderCandidate` فيمرّ الجميعُ في `ready_to_send_payload` بحواجزه نفسها:
    الموافقةُ ويومُ الراحة والعطلةُ والتأجيلُ والحدُّ الأقصى. فلا محرّكٌ موازٍ
    يفترق عن هذا عند أوّل تعديل.

    **والإعداداتُ تُمرَّر محلولةً** (`resolve_settings_for_clients`) لا تُقرأ هنا:
    «جاهز للإرسال» يحتاجها قبل الحساب لحجب يوم الراحة، فقراءتُها مرّتين كانت
    تضاعف الاستعلامات وإن اختلفت النتيجةُ بينهما وقع الحسابُ على غير ما حُجب به.

    والإيقاع: أوّلُ يومٍ = `period_end + start_days`، واليومُ التالي = **آخرُ
    صفٍّ صادر** (إرسالٌ أو تنحية) + `interval_days`، ولا تذكيرَ بعد `max` صفٍّ
    عدّاً صافياً. والصفوفُ المُبطَلة بـ`undo` لا تُعدّ (`reverted` في الاستعلام).
    """
    types = _GENERATED_REMINDER_TYPES
    if reminder_type is not None and _assert_reminder_type(reminder_type) not in types:
        return []
    clients = [client for client in clients if client.pk is not None]
    if not clients:
        return []
    contacts = _reminder_contacts(tenant, clients, types)

    #: الأوراقُ الناقصة وحدها: «وصلت» و«مش لازمة» خارجُ التذكير بطبيعتهما.
    rows = list(
        DocumentChecklistItem.objects
        .filter(
            client_id__in=[client.pk for client in clients],
            status__in=(DOCUMENT_STATUS_REQUIRED, DOCUMENT_STATUS_PARTIAL),
        )
        .values("client_id", "item_code", "name", "period_start", "period_end")
        .order_by("client_id", "period_start", "item_code"),
    )
    grouped: dict[tuple[int, Any, Any], dict] = {}
    for row in rows:
        key = (row["client_id"], row["period_start"], row["period_end"])
        bucket = grouped.setdefault(key, {"names": [], "codes": []})
        bucket["names"].append(row["name"])
        bucket["codes"].append(row["item_code"])

    #: التصحيحُ (`undo`) يشير إلى ما يُبطله — و`Exists` تُنقص المُبطَل من العدّ
    #: داخل الاستعلام نفسه فلا استعلامَ لكل صفّ.
    logs = list(
        ReminderLog.objects
        .filter(
            tenant=tenant,
            client_id__in=[client.pk for client in clients],
            reminder_type__in=types,
            kind__in=REMINDER_TIMER_KINDS,
        )
        .annotate(reverted=Exists(
            ReminderLog.objects.filter(reverts=OuterRef("pk")),
        ))
        .values("client_id", "reminder_type", "kind", "period_start", "period_end",
                "created_at", "reverted"),
    )
    by_pair: dict[tuple[int, str, Any, Any], list] = {}
    for row in logs:
        if row["reverted"]:
            continue
        key = (row["client_id"], row["reminder_type"], row["period_start"], row["period_end"])
        #: ويومُ الصفّ معه محسوباً: مولّدا #281 يقيسان **نافذةً** بأيّام الصفوف،
        #: و`localdate` مرّةً لكل صفٍّ أرخصُ من إعادتها في كل مولّد.
        by_pair.setdefault(key, []).append({**row, "day": _reminder_log_day(row)})
    #: العدُّ الصافي لكل بند — لمولّد الأوراق وحده: الإيقاعُ فيه عدُّ صفوفٍ لا
    #: نافذةُ أيام، ومولّدا #281 يقرآن `by_pair` بأيّامه.
    counted_by_pair = {
        key: sum(1 for row in pair if row["kind"] in REMINDER_COUNTED_KINDS)
        for key, pair in by_pair.items()
    }

    postponed = _reminder_postponed_pairs(tenant, clients, types, day)
    #: الفتراتُ مفهرسةٌ بزبونها: الحلقةُ لكل زبونٍ تقرأ فتراتِه وحدها، فلا
    #: مسحٌ كاملٌ لكل زبون (مكتبٌ بألف زبون لا يمرّ على جدول الأوراق مليون مرّة).
    periods_by_client: dict[int, list] = {}
    for (client_id, period_start, period_end), bucket in grouped.items():
        periods_by_client.setdefault(client_id, []).append(
            (period_start, period_end, bucket),
        )
    candidates = []
    for client in clients:
        resolved = settings_by_client[client.pk]
        enabled = resolved.get(REMINDER_TYPES_ENABLED_KEY) or []
        periods = periods_by_client.get(client.pk, ())
        # الأوراقُ وحدها في هذه الحلقة؛ والموعدُ والموعدُ الرسميُّ في
        # `appointments` — ودخولُهما هنا بنداً ثانياً يخنق هذا المسح.
        # وفلترُ الطلب يخصّها أيضاً: طلبُ نوعٍ آخر لا يعرض بندَ أوراق.
        if REMINDER_DOCUMENTS in enabled and reminder_type in (None, REMINDER_DOCUMENTS):
            for period_start, period_end, bucket in periods:
                pairs = by_pair.get(
                    (client.pk, REMINDER_DOCUMENTS, period_start, period_end), [],
                )
                count = counted_by_pair.get(
                    (client.pk, REMINDER_DOCUMENTS, period_start, period_end), 0,
                )
                interval_days = resolved.get(DOCUMENTS_REMINDER_INTERVAL_DAYS_KEY) or 1
                start_days = resolved.get(DOCUMENTS_REMINDER_START_DAYS_KEY) or 0
                maximum = resolved.get(DOCUMENTS_REMINDER_MAX_KEY) or 1
                last_day = max((row["day"] for row in pairs), default=None)
                next_due = (
                    period_end + timedelta(days=start_days) if last_day is None
                    else last_day + timedelta(days=interval_days)
                )
                candidates.append(ReminderCandidate(
                    client=client,
                    reminder_type=REMINDER_DOCUMENTS,
                    period_start=period_start,
                    period_end=period_end,
                    missing=tuple(bucket["names"]),
                    missing_codes=tuple(bucket["codes"]),
                    count=count,
                    maximum=maximum,
                    interval_days=interval_days,
                    next_due=next_due,
                    contact=contacts.get((client.pk, REMINDER_DOCUMENTS)),
                    tax_system=resolved.get(TAX_SYSTEM_KEY),
                    due=day >= next_due,
                    exhausted=count >= maximum,
                    postponed=(client.pk, REMINDER_DOCUMENTS) in postponed,
                    render_due=day + timedelta(days=interval_days),
                ))
    appointments = _appointments_module()
    candidates.extend(appointments.appointment_reminder_candidates(
        tenant, clients,
        day=day,
        settings_by_client=settings_by_client,
        contacts=contacts,
        by_pair=by_pair,
        postponed_pairs=postponed,
        reminder_type=reminder_type,
    ))
    candidates.extend(appointments.deadline_reminder_candidates(
        tenant, clients,
        day=day,
        settings_by_client=settings_by_client,
        contacts=contacts,
        by_pair=by_pair,
        missing_by_period=grouped,
        postponed_pairs=postponed,
        reminder_type=reminder_type,
    ))
    # #283/ب: إشعارُ القبض — مولّدُه في `payments` (مالُ الدفعات هناك)، ويمرّ
    # هنا فيدخل بحواجز `ready_to_send_payload` نفسها بلا محرّكٍ موازٍ.
    candidates.extend(_payments_module().fee_receipt_reminder_candidates(
        tenant, clients,
        day=day,
        settings_by_client=settings_by_client,
        contacts=contacts,
        by_pair=by_pair,
        postponed_pairs=postponed,
        reminder_type=reminder_type,
    ))
    # #282/أ٢: «اللي عليه» من فاتورةٍ صادرةٍ لم تُلغَ — مقدارُها واستحقاقُها بعد
    # سبعة أيام. مولّدٌ ثالثٌ يُرجع `ReminderCandidate` نفسه، فيمرّ في الحواجز
    # كلّها أدناه (الإذنُ ويومُ الراحة والعطلةُ والتأجيلُ والسقف) بلا استثناء.
    candidates.extend(_fee_invoices_module().invoice_reminder_candidates(
        tenant, clients,
        day=day,
        settings_by_client=settings_by_client,
        contacts=contacts,
        by_pair=by_pair,
        postponed_pairs=postponed,
        reminder_type=reminder_type,
    ))
    # #283/ج: «اللي عليه» بعد الاستحقاق — خيطٌ لكل زبونٍ من استحقاق آخر ورقةٍ
    # صادرة، ودرجتان (3 ثم 7) بسقف اثنتين من السجلّ. مولّدٌ رابعٌ يُرجع
    # `ReminderCandidate` نفسه فيمرّ في الحواجز كلّها بلا محرّكٍ موازٍ.
    candidates.extend(_payments_module().balance_reminder_candidates(
        tenant, clients,
        day=day,
        settings_by_client=settings_by_client,
        contacts=contacts,
        by_pair=by_pair,
        postponed_pairs=postponed,
        reminder_type=reminder_type,
    ))
    # #283/ج: كشفُ أوّل الشهر — بندٌ لكل زبونٍ عليه رصيد. والدَّمجُ مع بندٍ آخر في
    # اليوم نفسه يقع **بعد الحواجز** (`_with_monthly_statements`) كي لا يضيع
    # الكشفُ مع بندٍ حجبه يومُ راحةٍ أو انتهى سقفُه.
    candidates.extend(_payments_module().statement_reminder_candidates(
        tenant, clients,
        day=day,
        settings_by_client=settings_by_client,
        contacts=contacts,
        by_pair=by_pair,
        postponed_pairs=postponed,
        reminder_type=reminder_type,
    ))
    return candidates


def day_key_blocked(day, rest_days) -> bool:
    """هل اليومُ عطلةٌ لهذا الزبون؟ — من `rest_days` المحلولة وحدها."""
    return deadlines.weekday_key(day) in set(rest_days or ())


def _reminder_postponed_pairs(tenant, clients, reminder_types, day) -> set[tuple[int, str]]:
    """أزواجٌ مؤجَّلةٌ **يومَ القراءة** — أحدثُ صفٍّ لكل (زبون، نوع) هو الساري."""
    latest: dict[tuple[int, str], Any] = {}
    for row in (
        ReminderPostpone.objects
        .filter(
            tenant=tenant,
            client_id__in=[client.pk for client in clients],
            reminder_type__in=list(reminder_types),
        )
        .order_by("created_at", "id")
        .values("client_id", "reminder_type", "until")
    ):
        latest[(row["client_id"], row["reminder_type"])] = row["until"]
    return {
        key for key, until in latest.items()
        if until is not None and day < until
    }


def office_is_on_holiday(tenant, day) -> bool:
    """عطلةُ مكتبٍ في يومٍ بعينه — **قائمةٌ يكتبها المكتب** لا تقويمٌ مخترَع."""
    return OfficeHoliday.objects.filter(tenant=tenant, date=day).exists()


def _reminder_item_payload(candidate) -> dict:
    """بندٌ واحدٌ في رسالةٍ — بكلّ مفتاحٍ يحتاجه فعلُ الإرسال بعده.

    **ونظامُ الزبون الضريبيُّ في البند لا في المستلِم** (#280/ب): شخصٌ واحدٌ قد
    يكون مستلِماً لزبونين بنظامين مختلفين، فالرابطُ يُبنى من نظام صاحب البند —
    وواجهةُ «جاهز للإرسال» تُمرّره حين تتفق البنودُ عليه وحده.
    """
    return {
        "client_id": candidate.client.pk,
        "client_name": candidate.client.name,
        "tax_system": candidate.tax_system,
        "reminder_type": candidate.reminder_type,
        "reminder_type_label": REMINDER_TYPE_LABELS.get(candidate.reminder_type, ""),
        "badge": candidate.badge,
        "period_start": candidate.period_start.isoformat(),
        "period_end": candidate.period_end.isoformat(),
        "period_label": candidate.period_text or deadlines.period_label(
            candidate.period_start, candidate.period_end,
        ),
        "missing_list": list(candidate.missing),
        "missing_codes": list(candidate.missing_codes),
        "step": candidate.count + 1,
        "max": candidate.maximum,
        "due_date": candidate.next_due.isoformat(),
        # #285: الإشعارُ المركَّبُ على البند. مبالغُه **نصوصٌ مصيغة** لا `Decimal`
        # (قاموسٌ خام يمرّ مع DRF مائعاً)، وهي مكشوفةٌ كما في نصّ الرسالة نفسها:
        # الإشعارُ نصُّه للزبون، فقناعُ البند وحده يُخفي عن الموظف ما يقرؤه من
        # يُرسِل إليه — والقناعُ يبقى حيث كان على صفوف الجداول والحمولات.
        "notice": _appointments_module().payment_notice_item(candidate.notice),
        # #283/ب: تفصيلُ إشعار القبض — أرقامٌ مصيغةٌ كما في `notice` (قاموسٌ خام
        # يمرّ مع DRF مائعاً). ويبقى المفتاحُ موجوداً بقيمة `None` لغير النوع.
        "receipt": candidate.receipt,
        # #282/أ٢: بندُ الفاتورة — نصوصٌ مصيغةٌ ورابطُ ورقتها (يُركَّب بعد
        # الحواجز كالإشعار)، وبلا فاتورةٍ يخرج `None` فيبقى شكلُ البند ثابتاً.
        "invoice": _fee_invoices_module().invoice_item(candidate.invoice),
        # #283/ج: كشفُ الشهر — أرقامُه من `statement_payload` بعد الحواجز، و`None`
        # لبندٍ ليس كشفاً فيبقى شكلُ البند ثابتاً على كلّ نوع.
        "statement": candidate.statement,
        "subject": {"document_item_codes": list(candidate.missing_codes)},
    }


def _reminder_render_values(tenant, candidate, *, language="") -> dict:
    """قيمُ الرموز الستّة لبند — **و`{due_date}` يخصّ نوعَه**.

    للأوراق هو يومُ التذكير **القادم** (وكان يُحسب `day + interval_days` هنا
    لأن `next_due` ماضٍ بيقين بعد يوم راحةٍ أو عطلة)، ولموعد التقديم هو تاريخُ
    تقديمه، ولموعد الزبون تاريخُ موعده. واليومُ المحسوبُ في المولّد
    (`render_due`) لا يُعاد بناؤه هنا.

    **و`{amount}` مبلغُ الفترة المنسَّق** من `candidate.amount` (بخانتين كسائر
    مبالغ الموديول) لا فراغاً دائماً كما كان، و`{missing_list}` أسماءُ الناقص.
    والقيمةُ الغائبةُ تُنطق `REMINDER_ABSENT_TEXT` بلغة المستلِم: نصٌّ مسطَّحٌ بلا
    شرطٍ لا يستطيع حذف عنوانٍ من سطره، فكلمةُ «لا شيء» تُغلق الجملةَ في الحالات
    الثلاث (أوراقٌ وحدها · مبلغٌ وحده · الاثنان) ولا تُبقي كلمةً معلَّقة.
    """
    absent = reminder_absent_text(language)
    return {
        "client_name": candidate.client.name,
        "period": candidate.period_text or deadlines.period_label(
            candidate.period_start, candidate.period_end,
        ),
        "due_date": (candidate.render_due or candidate.next_due).strftime("%d/%m/%Y"),
        "amount": absent if candidate.amount is None else f"{candidate.amount:.2f}",
        "missing_list": "، ".join(candidate.missing) or absent,
        "office_name": tenant.CompanyName,
    }


def _reminder_message(tenant, contact, candidates, *, bodies_by_type) -> dict:
    """رسالةٌ واحدةٌ لشخص: بنودُها ونصُّها بلغته هو — **ولكلّ بندٍ نصُّ نوعه**.

    رسالةٌ قد تجمع بندَي نوعين (أوراقٌ ناقصة وموعدٌ قريب) لشخصٍ واحد، فيُقرأ لكل
    بندٍ نصُّ نوعه من مكتبه — لا نصُّ النوع الأول على الجميع.

    **وإشعارُ الدفع نصٌّ ملحَقٌ ببند «موعد رسمي قريب»** (#285): يُركَّب معه في
    `body` بعد نصّ نوعه، ولا نوعَ تذكيرٍ خامس ولا رمزاً من `REMINDER_PLACEHOLDERS`
    جديد — الإشعارُ يبنيه الخادم من بيانات الزبون، لا يكتبه المكتب في قالب.
    وبندٌ بلا إشعار (`notice is None`) يخرج بنصّه وحده كما كان.
    """
    appointments = _appointments_module()
    parts = []
    for candidate in candidates:
        parts.append(render_reminder_body(
            bodies_by_type.get(candidate.reminder_type, {}).get(contact.language, ""),
            _reminder_render_values(tenant, candidate, language=contact.language),
        ))
        if candidate.notice is not None:
            parts.append(appointments.payment_notice_text(candidate.notice))
        # #283/ب: سطرُ إشعار القبض بعد نصّه — رقمُ الإشعار والمبلغ والباقي.
        if candidate.detail:
            parts.append(candidate.detail)
        # #282/أ٢: سطرُ الفاتورة بعد نصّ نوعه كالإشعار — رقمٌ ومبلغٌ واستحقاقٌ
        # ورابط، ولا رمزَ جديداً في قوالب المكتب.
        if candidate.invoice is not None:
            parts.append(_fee_invoices_module().invoice_text(candidate.invoice))
        # #283/ج: سطرُ الكشف الشهريّ بعد الإشعار — أرقامٌ من الورقة نفسها.
        if candidate.statement is not None:
            parts.append(_payments_module().statement_reminder_text(
                candidate.statement, language=contact.language,
            ))
    body = "\n\n".join(parts)
    return {
        "recipient": {
            "contact_id": contact.pk,
            "name": contact.name,
            "phone": contact.phone,
            "has_phone": bool(contact.phone),
            "language": contact.language,
            "language_label": dict(Contact.LANGUAGE_CHOICES).get(contact.language, ""),
        },
        "items": [_reminder_item_payload(candidate) for candidate in candidates],
        "body": body,
    }


def _with_payment_notices(tenant, candidates, settings_by_client, *, user=None):
    """يُركّب «إشعار الدفع» على بنود «موعد رسمي قريب»، ويترك كلَّ نوعٍ آخر كما هو.

    **بعد الحواجز كلّها** لا قبلها: الإرفاقُ يقرأ إعدادَ **صاحب البند** (د6)،
    ورابطُ الورقة لا يُنشَأ لبندٍ لن يُرسَل (يومُ راحةٍ أو إذنٌ مسحوب). وكلُّ
    الظهور التالي يقرأ النسخةَ المجمَّدة نفسها، فلا حسابَ ثانٍ في العرض.

    **ومفتاحُ الإشعار (زبون، تاريخُ الاستحقاق) لا (زبون، بند)**: بندان لفترتين
    يستحقّان في يومٍ واحد — ربعيّةٌ وشهريّةٌ في 15 — كان الإشعارُ يُركَّب على كلٍّ
    منهما. والرسالةُ تُجمع للمستلِم، فتخرج بعنوانه ومجموعه **مرّتين**، و`items[]`
    بإشعارين متطابقين. فيُركَّب على **أوّل** بندٍ لكلّ مفتاحٍ وحده، والباقي
    `notice=None` — والبندُ نفسُه باقٍ بنصّه.

    **والمجموعةُ تُبنى دفعةً**: استعلامُ التزاماتٍ واحدٌ لكل الأزواج، واستعلامٌ
    واحدٌ للروابط الحيّة — لا ثلاثةُ استعلاماتٍ لكلّ بند.
    """
    first_of_key: dict[tuple[int, object], int] = {}
    for index, candidate in enumerate(candidates):
        if candidate.reminder_type != REMINDER_DEADLINE:
            continue
        first_of_key.setdefault((candidate.client.pk, candidate.render_due), index)
    if not first_of_key:
        return candidates
    notices = _appointments_module().payment_notice_attachments(
        tenant,
        list(first_of_key),
        settings_by_client=settings_by_client,
        user=user,
    )
    attached = list(candidates)
    for key, index in first_of_key.items():
        notice = notices.get(key)
        if notice is not None:
            attached[index] = replace(attached[index], notice=notice)
    return attached


def can_share_payment_notice(tenant, user) -> bool:
    """هل يملك هذا العضو إنشاءَ رابطٍ عامٍّ للإشعار؟ — صلاحيةُ نوع المستند نفسها.

    الرابطُ يُنشَأ في **مسار قراءة** («جاهز للإرسال»)، ومسارُ القراءة يفتحه من لا
    يملك المشاركة أيضاً. بلا هذا الحارس كان عضوٌ للقراءة يُنشئ — بفتح الشاشة —
    صفَّ `DocumentShare` حيّاً وأثراً في `ActivityLog` بمبالغ زبون، وهو فعلٌ
    تمنعه الصلاحية في مسار الكتابة. فمن لا يملكها يقرأ الإشعار **نصّاً** ولا
    يُنشَأ له رابط (انظر `payment_notice_attachments`).
    """
    if user is None:
        return False
    return user_has_perm(user, tenant, OFFICE_CLIENTS_WRITE_KEY)


def _with_monthly_statements(tenant, candidates, *, day):
    """يُدخل الكشفَ الشهريّ في **بندٍ واحدٍ لكل زبون** — بعد الحواجز كلّها.

    **والدمجُ قرارٌ لا صدفة**: كشفُ أوّل الشهر يخصّ الزبون نفسَه الذي قد يكون له
    في اليوم نفسه بندُ فاتورةٍ أو أوراق؛ ورسالتان بمفتاحين لبندٍ واحد تُقرأان
    إلحاحاً ويُرسَل الكشفُ مرّتين. فيُدمج نصُّه في أوّل بندٍ باقٍ للزبون،
    و**بندُ «اللي عليه» يُقدَّم** لأن الكشفَ امتدادُ رسالة الفاتورة في الشهر نفسه.
    وبلا بندٍ آخر يبقى الكشفُ بنداً مستقلاً بمفتاحه الشهريّ.

    **والكلفةُ على قدر المرسَل**: أرقامُ الكشف (`statement_payload`) تُقرأ هنا
    لبندٍ نجا من الحواجز وحده، لا لبندٍ حجبه يومُ راحةٍ أو انتهى سقفُه.
    """
    if not any(candidate.statement is not None for candidate in candidates):
        return candidates
    slots = list(candidates)
    for index, candidate in enumerate(slots):
        if candidate.statement is None:
            continue
        targets = [
            position
            for position, other in enumerate(slots)
            if position != index and other.client.pk == candidate.client.pk
        ]
        if not targets:
            continue
        host = next(
            (
                position for position in targets
                if slots[position].reminder_type == REMINDER_BALANCE
            ),
            targets[0],
        )
        slots[host] = replace(slots[host], statement=slots[index].statement)
        slots[index] = None
    payloads: dict[int, dict] = {}
    rows = []
    for candidate in slots:
        if candidate is None:
            continue
        if candidate.statement is not None:
            payloads.setdefault(
                candidate.client.pk,
                _payments_module().statement_reminder_payload(
                    tenant, candidate.client, day=day,
                ),
            )
            candidate = replace(
                candidate, statement=payloads[candidate.client.pk],
            )
        rows.append(candidate)
    return rows


def ready_to_send_payload(
    tenant, *, user, day, reminder_type=None, assignee=None,
) -> dict:
    """«جاهز للإرسال»: رسالةٌ واحدةٌ لكل شخصٍ في اليوم — لا لكل زبون.

    **التجميعُ على المستلِم** لا على الزبون: شخصٌ مستلِمٌ لزبونين يأخذ رسالةً
    واحدةً فيهما (وكانت رسالتان تُقرأان إلحاحاً وتُرسَلان مرّتين). ومفتاحُ
    `reminder_merge_daily` يقلبها إلى رسالةٍ لكل بند لمن يريد فصلَها.

    **وكلُّ حاجبٍ يُطبَّق هنا** لا في الحساب: يومُ راحة الزبون، وعطلةُ المكتب،
    وتأجيلُ الزوج، ورفضُ الإذن. فالتذكيرُ لا يُلغى بحاجز — يظهر في أوّل يومٍ
    مسموح، لأن الحسابَ من السجلّ لا من صفٍّ محفوظ.
    """
    queryset = (
        visible_clients(tenant, user)
        .filter(status=OfficeClient.STATUS_ACTIVE)
        .select_related("responsible")
        .order_by("id")
    )
    if assignee is not None:
        queryset = queryset.filter(responsible_id=assignee)
    clients = list(queryset)
    merge_daily = resolve_setting(tenant, REMINDER_MERGE_DAILY_KEY)
    payload = {
        "day": day.isoformat(),
        "merge_daily": bool(merge_daily),
        "reminder_type": reminder_type,
        "messages": [],
        "placeholders": list(REMINDER_PLACEHOLDERS),
    }
    if not clients or office_is_on_holiday(tenant, day):
        return payload
    # مرّةٌ واحدةٌ للحمولة كلِّها: الحسابُ يحتاجها ليحجب يومَ الراحة، وبناءُ
    # الرسائل يحتاجها لتاريخ الـ`{due_date}` — فتُقرأ هنا وتُمرَّر.
    settings_by_client = resolve_settings_for_clients(
        tenant, _REMINDER_CLIENT_KEYS, clients,
    )
    candidates = [
        candidate for candidate in _reminder_candidates(
            tenant, clients, day=day,
            settings_by_client=settings_by_client,
            reminder_type=reminder_type,
        )
        if candidate.due
        and not candidate.exhausted
        and not candidate.postponed
        and candidate.contact is not None
        and candidate.contact.allows_reminder(candidate.reminder_type)
        and not day_key_blocked(day, settings_by_client[candidate.client.pk].get("rest_days"))
    ]
    if not candidates:
        return payload
    # #283/ج: الكشفُ الشهريّ يُدمج في بندٍ واحدٍ لكل زبون **بعد الحواجز** — فلا
    # يُنشَأ كشفٌ لبندٍ حجبه يومُ راحةٍ، ولا يضيع كشفُ زبونٍ حُجِب بندُه الآخر.
    candidates = _with_monthly_statements(tenant, candidates, day=day)
    # #285: الإشعارُ يُركَّب هنا — بين الحاجز الأخير وبناء الرسالة — فلا رابطَ
    # يُنشَأ (ولا حسابَ سطرٍ) لبندٍ خارج «جاهز للإرسال». ودفعةً واحدة بمفتاح
    # (زبون، تاريخ) لا بنداً بنداً، فلا عملَ مكرَّرٌ ولا استعلامَ لكلّ زبون.
    candidates = _with_payment_notices(
        tenant, candidates, settings_by_client, user=user,
    )
    # #282/أ٢: رابطُ ورقة الفاتورة — بعد الحواجز كلّها كالإشعار، ولمن يملك
    # مشاركةَ النوع وحده (لا صفَّ مشاركةٍ من مسار قراءةٍ لعضوٍ للقراءة).
    candidates = _fee_invoices_module().attach_invoice_links(
        tenant, candidates, user=user,
    )
    # النصوصُ تُقرأ **مرّةً للنوع** لا مرّةً لكل رسالة: خمسةُ زبائن لا تكلّف
    # خمسَ قراءاتٍ لمكتبٍ واحدٍ في يوم. والأنواعُ من البنود المحسوبة وحدها — فلا
    # استعلامَ لنوعٍ لم يظهر، والرسالةُ المجمَّعةُ تأخذ نصَّ كلّ بندٍ بنوعه.
    bodies_by_type = {
        current_type: reminder_template_bodies(tenant, current_type)
        for current_type in sorted({candidate.reminder_type for candidate in candidates})
    }
    grouped: dict[int, list] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.contact.pk, []).append(candidate)
    messages = []
    for contact_id in sorted(grouped):
        group = grouped[contact_id]
        if merge_daily:
            messages.append(_reminder_message(
                tenant, group[0].contact, group, bodies_by_type=bodies_by_type,
            ))
        else:
            messages.extend(
                _reminder_message(
                    tenant, candidate.contact, [candidate],
                    bodies_by_type=bodies_by_type,
                )
                for candidate in group
            )
    payload["messages"] = messages
    return payload


# ── الأفعال: الإرسال والتنحية والتأجيل والتصحيح (#280/D4، D5، D9) ────────────
class ReminderClientNotVisible(ValidationError):
    """زبونٌ لا يراه هذا العضو — والـview يترجمها **404** لا 400.

    القاعدةُ القائمة منذ #272: 403 يثبت وجودَ الزبون، و404 لا يثبت شيئاً. وهذا
    الصنفُ يُميّز «غير موجودٍ لك» عن «حمولةٌ فاسدة» (400) داخل الخدمة نفسها،
    فتبقى الصلاحيةُ والرؤيةُ قرارَ طبقةٍ واحدة.
    """


def _visible_client_or_raise(tenant, user, client_id):
    """زبونٌ يراه هذا العضو — وإلا `ReminderClientNotVisible` (404 في الـview)."""
    try:
        pk = int(client_id)
    except (TypeError, ValueError):
        raise ValidationError({"client_id": "معرّفُ زبونٍ غير صالح."}) from None
    client = (
        visible_clients(tenant, user)
        .filter(pk=pk)
        .select_related("responsible")
        .first()
    )
    if client is None:
        raise ReminderClientNotVisible({"client_id": "الزبون غير موجود."})
    return client


def _clean_reminder_items(tenant, user, items) -> list[dict]:
    """بنودُ فعلٍ واحد: زبونٌ مرئيٌّ، ونوعٌ معروفٌ، وفترةٌ **كاملةُ الطرفين**.

    و`period_end` **مطلوبةٌ لا مستنتَجة**: مفتاحُ العدّ `(period_start, period_end)`
    لأن القائمةَ السنوية تبدأ في 1 يناير كالشهرية، واستنتاجُ النهاية عند غيابها
    يخلط أوراقَ السنة بأوراق كانون الثاني ويكتب في السجلّ فترةً غيرَ التي أُرسلت.
    ورسالةُ «جاهز للإرسال» تحمل المفتاحين، فالشاشةُ لا تحتاج تخميناً.
    """
    if not isinstance(items, (list, tuple)) or not items:
        raise ValidationError({"items": "اختر بنداً واحداً على الأقل."})
    clean = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValidationError({"items": "كلُّ بندٍ قاموس."})
        reminder_type = _assert_reminder_type(raw.get("reminder_type"))
        client = _visible_client_or_raise(tenant, user, raw.get("client_id"))
        if not raw.get("period_end"):
            raise ValidationError({
                "period_end": "نهايةُ الفترة مطلوبةٌ مع بدايتها — التاريخان معاً مفتاحُ التذكير.",
            })
        clean.append({
            "client": client,
            "reminder_type": reminder_type,
            "period_start": _reminder_period_date(raw.get("period_start"), "period_start"),
            "period_end": _reminder_period_date(raw.get("period_end"), "period_end"),
        })
    return clean


def _reminder_period_date(raw, field):
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        raise ValidationError({field: "تاريخٌ مطلوبٌ بالصيغة YYYY-MM-DD."}) from None


def _reminder_contact_of_tenant(tenant, contact_id) -> Contact:
    contact = Contact.objects.filter(tenant=tenant, pk=contact_id).first()
    if contact is None:
        raise ValidationError({"contact_id": "هذه الجهة ليست من جهات هذا المكتب."})
    return contact


def _reminder_missing_metadata(items) -> dict[tuple[int, Any, Any], dict]:
    """أكوادُ الأوراق الناقصة وأسماؤها وقت الإرسال — **استعلامٌ واحد** لكل البنود.

    لقطةٌ لا حساباً لاحقاً: ما كان ناقصاً حين أُرسل يُقرأ بعد سنة كما كان، ولو
    وصلت الورقةُ غداً.
    """
    wanted = {(item["client"].pk, item["period_start"], item["period_end"]) for item in items}
    rows = (
        DocumentChecklistItem.objects
        .filter(
            client_id__in={client_id for client_id, _start, _end in wanted},
            status__in=(DOCUMENT_STATUS_REQUIRED, DOCUMENT_STATUS_PARTIAL),
        )
        .order_by("item_code")
        .values_list("client_id", "period_start", "period_end", "item_code", "name")
    )
    meta: dict[tuple[int, Any, Any], dict] = {
        key: {"codes": [], "names": []} for key in wanted
    }
    for client_id, period_start, period_end, code, name in rows:
        bucket = meta.get((client_id, period_start, period_end))
        if bucket is None:
            continue
        bucket["codes"].append(code)
        bucket["names"].append(name)
    return meta


def _write_reminder_logs(
    *, tenant, actor, items, kind, channel, body, reason="",
):
    """صفوفُ السجلّ دفعةً واحدة — **المسارُ الوحيد** لكتابة `ReminderLog`.

    **والعائدُ استعلامٌ يُعاد قراءتُه بمعرّف الدفعة** (`batch`) لا ما أرجعه
    `bulk_create`: MySQL لا يُسنِد المفاتيحَ بعده، فالجوابُ كان يخرج بـ`id: null`
    فلا تستطيع الشاشةُ التراجعَ — وSQLite يُسنِدها فيُخفي العيب. قراءةٌ واحدة.

    **وكلُّ بندٍ يحمل `contact` مستلِمَه**: الإرسالُ يعطي جهةً واحدة للرسالة كلّها،
    والتنحيةُ تُحلّ لكل بندٍ مستلِمَه قبل النداء — فالمسارُ واحدٌ لا نسختان،
    والدفعةُ واحدةٌ مهما بلغ عددُ البنود.

    ولا `update` ولا `delete` هنا ولا في الـAPI: الصفُّ يُكتب مرّةً ويبقى،
    والتصحيحُ صفٌّ جديد يشير إليه.
    """
    meta_by_key = _reminder_missing_metadata(items)
    batch = uuid4()
    rows = []
    for item in items:
        contact = item.get("contact")
        meta = meta_by_key.get(
            (item["client"].pk, item["period_start"], item["period_end"]),
            {"codes": [], "names": []},
        )
        rows.append(ReminderLog(
            tenant=tenant,
            client=item["client"],
            contact=contact,
            recipient_name="" if contact is None else contact.name,
            recipient_phone="" if contact is None else contact.phone,
            reminder_type=item["reminder_type"],
            kind=kind,
            channel=channel,
            body=body,
            period_start=item["period_start"],
            period_end=item["period_end"],
            subject={
                "document_item_codes": meta["codes"],
                "document_item_names": meta["names"],
            },
            reason=reason,
            created_by=actor,
            batch=batch,
        ))
    ReminderLog.objects.bulk_create(rows)
    return (
        ReminderLog.objects
        .filter(tenant=tenant, batch=batch)
        .select_related("client", "created_by")
        .order_by("id")
    )


def _assert_contact_serves_items(contact, items) -> None:
    """الجهةُ المستلِمة مربوطةٌ بكلّ زبونٍ في الرسالة — وإلا فهي رسالةٌ لغير أهلها.

    **واستعلامٌ واحد**: زبائنُ الرسالة تُقرأ مرّةً ثم تُقارَن، فلا استعلامَ لكل
    بندٍ في رسالةٍ مجمَّعة.
    """
    client_ids = [item["client"].pk for item in items]
    linked = set(
        ClientContact.objects
        .filter(contact=contact, client_id__in=client_ids)
        .values_list("client_id", flat=True),
    )
    for item in items:
        if item["client"].pk not in linked:
            raise ValidationError({
                "contact_id": (
                    f"الجهة {contact.name} غير مربوطةٍ بالزبون "
                    f"{item['client'].name}."
                ),
            })


def mark_reminders_sent(tenant, *, user, contact_id, body, items, channel=""):
    """«انبعثت»: صفُّ `sent` لكل بندٍ بالنصّ نفسه — والواتسابُ قناتُه الوحيدة."""
    clean_channel = (channel or "").strip() or REMINDER_CHANNEL_WHATSAPP
    if clean_channel != REMINDER_CHANNEL_WHATSAPP:
        raise ValidationError({
            "channel": "«انبعثت» إرسالٌ بالواتساب وحده — وما عداه «كلّمناه».",
        })
    clean_body = (body or "").strip()
    if not clean_body:
        # السجلُّ إلحاقيٌّ لا يُمحى: صفُّ `sent` بلا نصٍّ لا يُصحَّح إلا بصفٍّ آخر.
        raise ValidationError({"body": "نصُّ الرسالة المُرسَلة مطلوب."})
    clean_items = _clean_reminder_items(tenant, user, items)
    contact = _reminder_contact_of_tenant(tenant, contact_id)
    _assert_contact_serves_items(contact, clean_items)
    return _write_reminder_logs(
        tenant=tenant,
        actor=user,
        items=[dict(item, contact=contact) for item in clean_items],
        kind=REMINDER_KIND_SENT,
        channel=clean_channel,
        body=clean_body,
    )


def mark_reminders_manual(tenant, *, user, contact_id, body, channel, items):
    """«كلّمناه»: هاتفٌ أو زيارة — والواتسابُ ليس «كلّمناه»."""
    if channel not in REMINDER_MANUAL_CHANNELS:
        raise ValidationError({
            "channel": "قناةُ التواصل اليدويّ: تلفون أو بالزيارة.",
        })
    clean_items = _clean_reminder_items(tenant, user, items)
    contact = _reminder_contact_of_tenant(tenant, contact_id)
    _assert_contact_serves_items(contact, clean_items)
    return _write_reminder_logs(
        tenant=tenant,
        actor=user,
        items=[dict(item, contact=contact) for item in clean_items],
        kind=REMINDER_KIND_MANUAL,
        channel=channel,
        body=(body or "").strip(),
    )


def dismiss_reminders(tenant, *, user, items, reason=""):
    """«شيل لهذه المرة»: يُعيد المؤقّت ولا يُعدّ في الحدّ الأقصى.

    والمستلِمُ يُحلّ هنا بالقاعدة نفسها التي تحلّه في القائمة (`_reminder_contacts`):
    التنحيةُ قرارُ مكتبٍ لا رسالة، فلا يُطلب معرّفُ جهةٍ من الشاشة. **والكتابةُ
    دفعةٌ واحدة**: كلُّ بندٍ يحمل مستلِمَه، فيبقى استعلامُ البيانات الوصفية و
    `bulk_create` واحدين مهما بلغ عددُ البنود.
    """
    clean_items = _clean_reminder_items(tenant, user, items)
    clients = [item["client"] for item in clean_items]
    contacts = _reminder_contacts(
        tenant, clients, {item["reminder_type"] for item in clean_items},
    )
    return _write_reminder_logs(
        tenant=tenant,
        actor=user,
        items=[
            dict(item, contact=contacts.get((item["client"].pk, item["reminder_type"])))
            for item in clean_items
        ],
        kind=REMINDER_KIND_DISMISSED,
        channel="",
        body="",
        reason=(reason or "").strip(),
    )


def postpone_reminder(
    tenant, *, user, day, client_id, reminder_type, until=None, reason="",
):
    """«أجّل التذكير لتاريخ…» — صفٌّ جديد، و`until=None` يمسح التأجيل."""
    _assert_reminder_type(reminder_type)
    client = _visible_client_or_raise(tenant, user, client_id)
    if until is not None:
        until = _reminder_period_date(until, "until")
        if until <= day:
            raise ValidationError({
                "until": "تاريخُ التأجيل يجب أن يكون بعد اليوم.",
            })
    return ReminderPostpone.objects.create(
        tenant=tenant,
        client=client,
        reminder_type=reminder_type,
        until=until,
        reason=(reason or "").strip(),
        created_by=user,
    )


def undo_reminder_log(row, *, actor):
    """«ما انبعتت» — صفُّ `undo` جديدٌ يشير إلى ما يُبطله، ولا يُبطل تصحيحاً.

    والصفُّ الأصلِيُّ يبقى: العدُّ يستثني المُبطَل، والسطرُ يبقى أثراً. وإبطالُ
    `undo` بمثابة إبطالٍ لإبطال — يُرفَض صراحةً حتى لا يدور السجلُّ في حلقة.
    """
    if row.kind not in REMINDER_COUNTED_KINDS:
        raise ValidationError({
            "row": "لا يُبطَل إلا تذكيرٌ أُرسل أو كلّمناه — هذا الصفُّ ليس إرسالاً.",
        })
    if ReminderLog.objects.filter(reverts=row).exists():
        raise ValidationError({"row": "هذا الصفُّ أُبطل مرّةً — لا يُبطل مرّتين."})
    return ReminderLog.objects.create(
        tenant=row.tenant,
        client=row.client,
        contact=row.contact,
        recipient_name=row.recipient_name,
        recipient_phone=row.recipient_phone,
        reminder_type=row.reminder_type,
        kind=REMINDER_KIND_UNDO,
        channel="",
        body="",
        period_start=row.period_start,
        period_end=row.period_end,
        subject=dict(row.subject or {}),
        reverts=row,
        created_by=actor,
    )


def reminder_log_row(row) -> dict:
    """سطرُ السجلّ كما تعرضه شاشةُ الزبون — بالمسمّيات لا بالمفاتيح."""
    return {
        "id": row.pk,
        "client": {"id": row.client_id, "name": row.client.name},
        "contact_id": row.contact_id,
        "recipient_name": row.recipient_name,
        "recipient_phone": row.recipient_phone,
        "reminder_type": row.reminder_type,
        "reminder_type_label": REMINDER_TYPE_LABELS.get(row.reminder_type, ""),
        "kind": row.kind,
        "kind_label": REMINDER_KIND_LABELS.get(row.kind, ""),
        "channel": row.channel,
        "channel_label": REMINDER_CHANNEL_LABELS.get(row.channel, ""),
        "body": row.body,
        "period_start": None if row.period_start is None else row.period_start.isoformat(),
        "period_end": None if row.period_end is None else row.period_end.isoformat(),
        "period_label": (
            "" if row.period_start is None or row.period_end is None
            else deadlines.period_label(row.period_start, row.period_end)
        ),
        "subject": dict(row.subject or {}),
        "reason": row.reason,
        "reverts_id": row.reverts_id,
        "created_by": (
            None if row.created_by_id is None
            else {"id": row.created_by_id, "name": user_display_name(row.created_by)}
        ),
        "created_at": row.created_at.isoformat(),
    }


def visible_reminder_logs(tenant, user):
    """**مصدر رؤية السجلّ الوحيد**: صفوفُ زبائن يراهم هذا العضو.

    ولا فلترةَ بغيره في أيّ نقطة: سطرُ سجلٍّ لزبونٍ لا يراه العضو **404**،
    وسطرٌ لا يمرّ من هنا لا يُقرأ ولا يُبطَل.
    """
    return (
        ReminderLog.objects
        .filter(
            tenant=tenant,
            client__in=visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "created_by")
    )


def reminder_log_payload(tenant, *, user, limit=100) -> dict:
    """سجلُّ المكتب كما يراه هذا العضو — الأحدثُ أوّلاً وبسقفٍ معلَن."""
    rows = visible_reminder_logs(tenant, user)[:limit]
    return {"rows": [reminder_log_row(row) for row in rows], "limit": limit}


def client_reminder_log_payload(client, *, limit=100) -> dict:
    """سجلُّ زبونٍ واحدٍ لتبويب ملفّه — الأحدثُ أوّلاً.

    الرؤيةُ مسؤوليةُ الـview (`get_object` عبر `visible_clients`)، والقائمةُ
    مقيَّدةٌ بالزبون نفسه لا بكلّ ما يراه العضو.
    """
    rows = (
        ReminderLog.objects
        .filter(tenant=client.tenant, client=client)
        .select_related("client", "created_by")
        .order_by("-created_at", "-id")[:limit]
    )
    return {
        "client": {"id": client.pk, "name": client.name},
        "rows": [reminder_log_row(row) for row in rows],
        "limit": limit,
    }


def reminder_postpone_row(row) -> dict:
    """تأجيلٌ كما يُعاد لصاحبه بعد كتابته — الشاشةُ تستبدل حالتها به."""
    return {
        "id": row.pk,
        "client_id": row.client_id,
        "reminder_type": row.reminder_type,
        "reminder_type_label": REMINDER_TYPE_LABELS.get(row.reminder_type, ""),
        "until": None if row.until is None else row.until.isoformat(),
        "reason": row.reason,
        "created_at": row.created_at.isoformat(),
    }


def office_holiday_row(row) -> dict:
    return {
        "id": row.pk,
        "date": row.date.isoformat(),
        "name": row.name,
    }


# ── التصعيد بعد الحدّ (#280/D11) ────────────────────────────────────────────
def _reminder_alert_ref(client_id, reminder_type, period_start, period_end) -> str:
    """مفتاحُ التنبيه — يحمل الفترةَ بطرفيها نصّاً فيُبحَث عنه بلا عمودٍ جديد.

    **والنهايةُ في المفتاح ليست زينة**: الفترةُ السنوية تبدأ في 1 يناير كما تبدأ
    كانون الثاني، فمفتاحٌ بالبداية وحدها يجعل تنبيهَ السنة وتنبيهَ الشهر صفّاً
    واحداً — فيُسقط أحدهما الآخرَ من الجرس بلا أن يُقرأ.
    """
    return (
        f"reminder:{client_id}:{reminder_type}:"
        f"{period_start.isoformat()}:{period_end.isoformat()}"
    )


def _live_reminder_alert_refs(tenant) -> set[str]:
    """مراجعُ التذكير التي ما زالت أوراقُها ناقصة — يُستبعَد ما اكتمل عند القراءة.

    **ونطاقُ المسح مقيَّدٌ بمن له تنبيهُ تذكيرٍ قائم**: فتحُ الجرس لا يمسح جدولَ
    الأوراق كلَّه، بل فتراتِ الزبائن الذين تنبيهُهم معروضٌ فعلاً. والشرطُ استعلامٌ
    فرعيٌّ واحد (`client_id__in`) لا مسحٌ في بايثون، فعددُ الاستعلامات ثابتٌ ولا
    يكبر بعدد الزبائن. والتنبيهُ «قائمٌ» ما دام صفُّه في القاعدة: إسقاطُه عند
    القراءة لا يمحو الصفّ، فالمفتاحُ يُحسب هنا بقاعدة الأوراق نفسِها.
    """
    return {
        _reminder_alert_ref(client_id, REMINDER_DOCUMENTS, period_start, period_end)
        for client_id, period_start, period_end in (
            DocumentChecklistItem.objects
            .filter(
                tenant=tenant,
                client_id__in=(
                    OfficeAlert.objects
                    .filter(tenant=tenant, kind__in=REMINDER_ALERT_KINDS)
                    .values("client_id")
                ),
                status__in=(DOCUMENT_STATUS_REQUIRED, DOCUMENT_STATUS_PARTIAL),
            )
            .values_list("client_id", "period_start", "period_end")
            .distinct()
        )
    }


def _generate_reminder_alerts(tenant, *, day) -> int:
    """يولّد تصعيدَ التذكير ليومٍ صريح ويُرجع **ما أنشأه هذا النداء**.

    - زبونٌ × أوراق × فترةٌ وصل عدُّها `max` وما زالت ناقصة، وحان يومُ التذكير
      التالي ⇒ تنبيهٌ للمسؤول برسالةٍ تسمّي الزبون والفترة والعدد **بلا مبلغ**.
    - وبعد `reminder_escalation_owner_days` (يومان افتراضاً) وما زالت ناقصة ⇒
      تنبيهٌ لصاحب المكتب — التعريفُ القائم نفسه (`_office_owner_ids`).

    **والكلفةُ ثابتة**: الحسابُ كلُّه مسحةٌ واحدة (`_reminder_candidates`)، ثم
    المفاتيحُ القائمة استعلامٌ واحدٌ محصورٌ بمراجع المرشّحين، ثم `bulk_create`
    دفعةً. والفرادةُ في القاعدة تحرس التكرارَ لو نُودِي النداءُ مرّتين في يوم.
    """
    clients = list(
        OfficeClient.objects
        .filter(tenant=tenant, status=OfficeClient.STATUS_ACTIVE)
        .select_related("responsible")
        .order_by("id"),
    )
    if not clients:
        return 0
    settings_by_client = resolve_settings_for_clients(
        tenant, _REMINDER_CLIENT_KEYS, clients,
    )
    candidates = [
        candidate for candidate in _reminder_candidates(
            tenant, clients, day=day,
            settings_by_client=settings_by_client,
            reminder_type=REMINDER_DOCUMENTS,
        )
        if candidate.exhausted and candidate.due
    ]
    if not candidates:
        return 0
    owner_days = resolve_setting(tenant, REMINDER_ESCALATION_OWNER_DAYS_KEY) or 0
    owners = _office_owner_ids(tenant)
    refs = {
        _reminder_alert_ref(
            candidate.client.pk, candidate.reminder_type,
            candidate.period_start, candidate.period_end,
        )
        for candidate in candidates
    }
    existing = set(
        OfficeAlert.objects
        .filter(tenant=tenant, ref_key__in=refs)
        .values_list("recipient_id", "kind", "ref_key"),
    )
    rows: list[OfficeAlert] = []
    for candidate in candidates:
        client = candidate.client
        responsible = client.responsible
        responsible_id = getattr(responsible, "pk", None)
        period = deadlines.period_label(candidate.period_start, candidate.period_end)
        ref = _reminder_alert_ref(
            client.pk, candidate.reminder_type,
            candidate.period_start, candidate.period_end,
        )
        rows.extend(_new_alert_rows(
            tenant=tenant,
            kind=OFFICE_ALERT_KIND_REMINDER_LIMIT,
            ref_key=ref,
            recipients=_alert_recipient_ids(
                settings_registry.ALERT_TO_ASSIGNEE,
                assignee_id=responsible_id,
                owners=owners,
            ),
            message=(
                f"{client.name} — أوراق ناقصة ({period}) — "
                f"{candidate.count} تذكيرات وما زالت ناقصة."
            ),
            day=day,
            client=client,
            task=None,
            obligation=None,
            existing=existing,
        ))
        if day < candidate.next_due + timedelta(days=owner_days):
            continue
        rows.extend(_new_alert_rows(
            tenant=tenant,
            kind=OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
            ref_key=ref,
            recipients=_alert_recipient_ids(
                settings_registry.ALERT_TO_OWNER,
                assignee_id=responsible_id,
                owners=owners,
            ),
            message=(
                f"{client.name} — أوراق ناقصة ({period}) — "
                f"{candidate.count} تذكيرات بلا نتيجة، والتذكيرُ توقّف."
            ),
            day=day,
            client=client,
            task=None,
            obligation=None,
            existing=existing,
        ))
    if not rows:
        return 0
    OfficeAlert.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


# ── الأتعاب: التوليدُ وقراءةُ الجرس (#282) ────────────────────────────────────
#
# الأتعابُ دومينُها في `accounting_office/fees.py` (كـ`client_books.py`): السعرُ
# المؤرَّخ والتناسبُ ومن يذهب إليه السطر. وما هنا جسران صغيران: نداءُ المولّد من
# «حدّث المكتب»، وقراءةُ بقاء تنبيه المسودّة في الجرس.
def _generate_fee_drafts(tenant, *, day) -> dict:
    """مسودّاتُ الأتعاب لدورة شهر `day` — `{"created_drafts", "created_alerts"}`.

    الاستيرادُ داخل الدالّة لا أعلى الملفّ: `fees` يقرأ `services` (المحلّل
    والقناع والرؤية)، فاستيرادٌ في الأعلى دورةُ استيراد. والجسمُ هناك لأن قواعد
    الأتعاب — السعرُ المؤرَّخ والتناسبُ والخياراتُ الثلاثة — تُقرأ وتُختبَر في
    موضعٍ واحد، لا نصفُها في خدمات الموديول ونصفُها في ملفّه.
    """
    from accounting_office import fees

    return fees.generate_fee_drafts(tenant, day=day)


# ── تذكيرُ نسخة البيانات (#290) ──────────────────────────────────────────────
#
# **تنبيهٌ لا بريدٌ ولا مُجدوِل**: المكتبُ لا يعرف أن نسخته لم تُؤخذ إلا إن قيل
# له، والقولُ في الجرس القائم — بنوعٍ جديدٍ (`data_export_due`) ومفتاحِ شهرٍ
# (`export:YYYY-MM`) تُكفل به فرادةُ `OfficeAlert` «مرّةً في الشهر» مهما تشغّل
# التحديث. وإسكاتُه **بمساره القائم** (`seen_at`): أخذُ النسخة يعلّم صفوفَ الشهر
# مقروءة — لا عمودَ حالةٍ ثانٍ يفترق عنه.
DATA_EXPORT_REMINDER_MESSAGE = (
    "نسخة بيانات المكتب لهذا الشهر — خُذها من الإعدادات ← التشغيل والنسخ"
)


def _sync_self_obligations(tenant, *, day) -> int:
    """جسرُ «حدّث المكتب» إلى `self_obligations` — استيرادٌ كسول كـ`_generate_fee_drafts`.

    `self_obligations` يقرأ `services.resolve_setting` و`client_books`، فاستيرادُه
    أعلى الملفّ دورةُ استيراد. والجسمُ هناك لأن قواعدَ السجلّ المستقلّ — المفتاحُ
    الطبيعيّ و«قُدِّم» النهائيّ — تُقرأ وتُختبَر في موضعٍ واحد.
    """
    from accounting_office import self_obligations

    return self_obligations.sync_self_obligations(tenant, day=day)


def data_export_ref_key(day) -> str:
    """مفتاحُ الشهر للتنبيه — `export:YYYY-MM`، مصدرُه الوحيدُ هنا."""
    return f"export:{day.year:04d}-{day.month:02d}"


def _approver_ids(tenant) -> set[int]:
    """مستلِمو التذكير: أعضاءُ المكتب النشطون بأدوار المستلِم المعتمِد.

    الأدوارُ من `client_books.ENTRY_APPROVER_ROLES` نفسِها — لا قائمةٌ ثانية
    تفترق عن أدوار من يعتمد القيود والمسودّات. والاستيرادُ كسول (دورةُ استيراد).
    """
    from accounting_office.client_books import ENTRY_APPROVER_ROLES

    return set(
        UserCompanyMembership.objects
        .filter(
            tenant=tenant, role__in=ENTRY_APPROVER_ROLES, user__is_active=True,
        )
        .values_list("user_id", flat=True),
    )


def _generate_data_export_reminders(tenant, *, day) -> int:
    """تذكيرُ الشهر — صفٌّ لكل مستلِمٍ إن كان الإعدادُ مفعّلاً، وإلا صفر.

    **ويُرجع ما أنشأه هذا النداء** لا عددَ المستلِمين: المفاتيحُ القائمة
    (`tenant` + النوع + مفتاحُ الشهر) تُقرأ استعلاماً واحداً وتُستبعَد قبل
    `bulk_create` كسائر المولّدات، فتشغيلُ اليوم نفسه مرّتين يعيد صفراً.
    والفرادةُ في القاعدة تبقى الحارسَ لو نُودِي النداءُ مرّتين في اللحظة نفسها.
    """
    if (
        resolve_setting(tenant, DATA_EXPORT_REMINDER_KEY)
        != settings_registry.DATA_EXPORT_REMINDER_MONTHLY
    ):
        return 0
    recipients = _approver_ids(tenant)
    if not recipients:
        return 0
    ref_key = data_export_ref_key(day)
    existing = set(
        OfficeAlert.objects
        .filter(
            tenant=tenant,
            kind=OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
            ref_key=ref_key,
        )
        .values_list("recipient_id", "kind", "ref_key"),
    )
    rows = _new_alert_rows(
        tenant=tenant,
        kind=OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
        ref_key=ref_key,
        recipients=recipients,
        message=DATA_EXPORT_REMINDER_MESSAGE,
        day=day,
        client=None,
        task=None,
        obligation=None,
        existing=existing,
    )
    if not rows:
        return 0
    OfficeAlert.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def mark_data_export_alerts_seen(tenant, *, day) -> int:
    """أخذُ النسخة يُسكِت تنبيهَ شهره — **كلَّ مستلِمي المكتب** لا مُنشئَه وحده.

    النسخةُ نسخةُ المكتب: صفٌّ يبقى غيرَ مقروءٍ على جرس زميلٍ بعد أن أُخذت
    يُلزمه بالبحث عن نسخةٍ موجودة. والصفوفُ لا تُحذف — «شوهد» كما في الجرس.
    """
    return OfficeAlert.objects.filter(
        tenant=tenant,
        kind=OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
        ref_key=data_export_ref_key(day),
        seen_at__isnull=True,
    ).update(seen_at=timezone.now())


def _live_fee_draft_refs(tenant) -> set[str]:
    """مراجعُ المسودّات غير المعتمدة — يُسقط ما اعتُمد أو أُلغي عند القراءة.

    **ونطاقُ المسح مقيَّدٌ بمن له تنبيهُ مسودّةٍ قائم**: فتحُ الجرس لا يقرأ
    مسودّات المكتب كلَّها، بل مسودّاتِ الزبائن الذين لهم صفُّ تنبيهٍ فعلاً. والشرطُ
    استعلامٌ فرعيٌّ واحد، فعددُ الاستعلامات ثابتٌ ولا يكبر بعدد المسودّات.
    """
    clients_with_alerts = OfficeAlert.objects.filter(
        tenant=tenant, kind=OFFICE_ALERT_KIND_FEE_DRAFT_PENDING,
    ).values("client_id")
    return {
        fee_draft_alert_ref(pk)
        for pk in (
            FeeDraft.objects
            .filter(
                tenant=tenant,
                status=FEE_DRAFT_STATUS_DRAFT,
                client_id__in=clients_with_alerts,
            )
            .values_list("pk", flat=True)
        )
    }
