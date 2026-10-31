"""خدمات مكتب المحاسبة — المحلّل الواحد، ودورة حياة الزبون، والجهات.

**المحلّل هو القانون:** `resolve_setting` يقرأ بالترتيب
**تخصيص الشغلة ← تخصيص الزبون ← قيمة المكتب ← الافتراضي**، ويرفض مستوىً غير
مسموحٍ للمفتاح. ولا كود خارج هذا الملفّ يقرأ `OfficeSettingValue` أو
`ClientSettingOverride` — النسخةُ الثانية من الترتيب تفترق عن الأولى بصمت.

**والكتابة تُتحقَّق قبلها**: كل ضبطٍ يمرّ بـ`settings_registry.validate_value`
(نوعُ الإعداد ومُتحقِّقه)، فيستحيل أن يدخل الجدولَ ما لا يعرفه السجلّ.
"""
import copy
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from accounting_office import settings_registry
from accounting_office.models import (
    CLIENT_SERVICE_FREQUENCY_CHOICES,
    CLIENT_SERVICE_STATUS_ACTIVE,
    CLIENT_SERVICE_STATUS_LABELS,
    DEFAULT_SERVICES,
    FREQUENCY_ANNUAL,
    FREQUENCY_BIMONTHLY,
    FREQUENCY_KEYS,
    FREQUENCY_LABELS,
    FREQUENCY_MONTHLY,
    FREQUENCY_ON_DEMAND,
    SERVICE_CODE_ANNUAL_ACCOUNTS,
    SERVICE_CODE_BOOKKEEPING,
    SERVICE_CODE_CONSULTING,
    SERVICE_CODE_PAYROLL,
    SERVICE_CODE_VAT,
    THRESHOLD_KIND_VAT_EXEMPT_DEALER,
    THRESHOLD_KIND_VAT_MONTHLY_REPORTING,
    ClientContact,
    ClientReminderRecipient,
    ClientService,
    ClientServiceFrequency,
    ClientSettingOverride,
    Contact,
    OfficeClient,
    OfficeService,
    OfficeSettingValue,
    ServicePackage,
    TaxCard,
    TaxThreshold,
    is_tenant_member,
    tax_card_choices,
)
from core.access import (
    OFFICE_AMOUNTS_VIEW_KEY,
    OFFICE_CLIENTS_ALL_KEY,
    user_has_perm,
)
from core.activity import log_activity

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

#: مفاتيح المبالغ في حمولة البطاقة الضريبية. مبلغٌ جديدٌ يُضاف هنا **أولاً**،
#: وإلا سقط حارسُ `accounting_office/tests/test_amounts_guard.py`.
TAX_CARD_AMOUNT_KEYS: tuple[str, ...] = ("annual_sales",)

#: مفاتيح مبالغ الباقات — الباقة تُقترح بسعرٍ اختياريّ، وهو مبلغُ تسويقٍ لا مبلغُ
#: زبون، لكنه يُعرض لعضوٍ قد لا يملك رؤية المبالغ فيمرّ بالقناع كغيره.
PACKAGE_AMOUNT_KEYS: tuple[str, ...] = ("suggested_price",)

#: كلُّ مفاتيح المبالغ في الموديول — يقارنها الحارس بحقول `DecimalField`
#: المعلَنة في مُسلسِلات الموديول وبمفاتيح حمولاته العشرية، فتضطرّ كلُّ تذكرةٍ
#: لاحقة فيها مبلغٌ أن تمرّ بالقناع.
AMOUNT_KEYS: frozenset[str] = frozenset(TAX_CARD_AMOUNT_KEYS + PACKAGE_AMOUNT_KEYS)


def visible_clients(tenant, user):
    """**مصدر الرؤية الوحيد**: كلُّ قائمةٍ أو نقطةٍ تُرجع زبوناً تمرّ من هنا.

    بلا `office.clients.all` («يرى زبائن غيره») لا تُرجع إلا زبائنَ هذا العضو
    (`responsible=user`)، ومعها كلُّ زبائن المكتب. والتفصيلُ المحجوب يُترجم في
    الـview إلى **404 لا 403**: 403 يثبت وجودَ الزبون، و404 لا يثبت شيئاً.

    **تذكرةُ الشغلات ستوسّع هذه الدالة وحدها** بـ«المحوَّلة له شغلاتهم»: الشغلةُ
    التي تُحوَّل إلى موظّفٍ تُريهِ زبونها ولو لم يكن مسؤولَه. موضعُ التوسيع هذا —
    لا شرطٌ جديدٌ في نقطةٍ ثانية يفترق عنه.
    """
    queryset = OfficeClient.objects.filter(tenant=tenant)
    if user_has_perm(user, tenant, OFFICE_CLIENTS_ALL_KEY):
        return queryset
    if user is None or not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(responsible=user)


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
def _assert_client_of_tenant(tenant, client) -> None:
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
        _assert_client_of_tenant(tenant, client)
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


def resolve_setting_for_clients(tenant, key, clients) -> dict[int, object]:
    """القيمة الفعلية لمجموعة زبائن في **استعلامين** — لا استعلامين لكل زبون.

    نفس ترتيب المحلّل (تخصيص الزبون ← قيمة المكتب ← الافتراضي)، بلا مستوى الشغلة
    (الشغلة كائنٌ واحد يُمرَّر، لا مجموعة). تُستعمل في القوائم: صفُّ القائمة يقرأ
    من هنا بدل نداء `resolve_setting` مرّتين أو ثلاثاً لكل زبون.
    """
    definition = settings_registry.get_definition(key)
    settings_registry.validate_level(definition, settings_registry.LEVEL_CLIENT)

    clients = list(clients)
    for client in clients:
        # كلُّ زبونٍ يمرّ بالحارس: مجموعةٌ فيها زبونُ مكتبٍ آخر تُقرأ إعداداً عابراً.
        _assert_client_of_tenant(tenant, client)

    client_ids = [client.pk for client in clients]
    overrides = dict(
        ClientSettingOverride.objects
        .filter(tenant=tenant, key=key, client_id__in=client_ids)
        .values_list("client_id", "value")
    )
    office_row = OfficeSettingValue.objects.filter(tenant=tenant, key=key).first()
    if office_row is not None:
        fallback = office_row.value
    elif definition.has_no_default:
        fallback = None
    else:
        fallback = definition.default

    resolved = {}
    for client_id in client_ids:
        if client_id in overrides:
            resolved[client_id] = copy.deepcopy(overrides[client_id])
        else:
            # نسخةٌ لكل زبون: قائمةُ الأيام الافتراضية مشتركةٌ وإلا عدّلها صفٌّ فأفسد غيره.
            resolved[client_id] = copy.deepcopy(fallback)
    return resolved


# ── الكتابة: تُتحقَّق بالنوع والمستوى قبل أن تلمس الجدول ────────────────────
def set_office_setting(tenant, key, value):
    definition = settings_registry.get_definition(key)
    settings_registry.validate_level(definition, settings_registry.LEVEL_OFFICE)
    clean = settings_registry.validate_value(definition, value)
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
    with transaction.atomic():
        OfficeSettingValue.objects.filter(tenant=tenant, key=key).delete()
        _propagate_tax_system(tenant, key, _clients_without_override(tenant, key))


def set_client_setting(client, key, value, *, tenant=None):
    tenant = tenant if tenant is not None else client.tenant
    _assert_client_of_tenant(tenant, client)
    definition = settings_registry.get_definition(key)
    settings_registry.validate_level(definition, settings_registry.LEVEL_CLIENT)
    clean = settings_registry.validate_value(definition, value)
    with transaction.atomic():
        row, _created = ClientSettingOverride.objects.update_or_create(
            tenant=tenant, client=client, key=key, defaults={"value": clean},
        )
        _propagate_tax_system(tenant, key, [client])
    return row.value


def reset_client_setting(client, key, *, tenant=None) -> None:
    """«ارجع لإعداد المكتب» — حذفُ التخصيص فيرتفع الترتيب إلى قيمة المكتب."""
    tenant = tenant if tenant is not None else client.tenant
    _assert_client_of_tenant(tenant, client)
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
                "employees_count": f"عدد الموظفين عددٌ صحيح بين 0 و{MAX_EMPLOYEES_COUNT}.",
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


def stop_client_service(client_service, *, ends_on) -> ClientService:
    """الإيقافُ يكتب `ends_on` ويُبقي الصفّ — **ولا حذف**: التاريخُ سؤالٌ له جواب.

    وثلاثةُ رفوضٍ قبله: تاريخٌ مطلوب، وصفٌّ موقوفٌ سابقاً (الإيقافُ مرّةٌ واحدة —
    كتابةُ تاريخٍ ثانٍ كانت تمحو الأول بلا أثر)، و`ends_on` يسبق تاريخَ سريان
    دوريةٍ مسجَّلة (فلا دوريةَ تُسجَّل بعد انتهاء الخدمة). والتحقّقُ والكتابةُ في
    معاملةٍ واحدة كالإضافة وتغيير الدورية.
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
        client_service.save(update_fields=["ends_on"])
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
