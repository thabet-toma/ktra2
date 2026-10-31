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

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from accounting_office import settings_registry
from accounting_office.models import (
    ClientContact,
    ClientReminderRecipient,
    ClientSettingOverride,
    Contact,
    OfficeClient,
    OfficeSettingValue,
    TaxCard,
    tax_card_choices,
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


def clients_customized_for(tenant, key):
    """«مخصَّص عند N زبون» — القائمة نفسها، لا عدّاً منفصلاً يفترق عنها."""
    settings_registry.get_definition(key)
    return (
        OfficeClient.objects
        .filter(tenant=tenant, setting_overrides__key=key)
        .distinct()
        .order_by("name", "id")
    )


def clients_customized_payload(tenant, key) -> list[dict]:
    """صفوفُ قائمة المخصِّصين — تُبنى هنا لا في الـview (مصدرٌ واحد للشكل)."""
    return [
        {
            "id": client.pk,
            "name": client.name,
            "status": client.status,
            "status_label": client.get_status_display(),
        }
        for client in clients_customized_for(tenant, key)
    ]


def _customization_counts(tenant) -> dict[str, int]:
    rows = (
        ClientSettingOverride.objects
        .filter(tenant=tenant)
        .values("key")
        .annotate(total=Count("id"))
    )
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


def office_settings_payload(tenant) -> dict:
    """سجلّ الإعدادات بقيمة المكتب الفعليّة والافتراضيِّ وعدد المخصِّصين."""
    counts = _customization_counts(tenant)
    return {
        **first_run_status(tenant),
        "groups": [
            {"id": group_id, "label": label}
            for group_id, label in settings_registry.SETTING_GROUPS
        ],
        "settings": [
            office_setting_row(tenant, key, counts=counts)
            for key in settings_registry.SETTINGS_REGISTRY
        ],
    }


def office_setting_row(tenant, key, *, counts=None) -> dict:
    """سطرُ إعدادٍ واحدٍ على مستوى المكتب — يستعمله العرض وردُّ الضبط والمسح."""
    definition = settings_registry.get_definition(key)
    stored = OfficeSettingValue.objects.filter(tenant=tenant, key=key).first()
    has_office_value = stored is not None
    value = (
        copy.deepcopy(stored.value) if has_office_value
        else (None if definition.has_no_default else copy.deepcopy(definition.default))
    )
    default = None if definition.has_no_default else copy.deepcopy(definition.default)
    counts = counts if counts is not None else _customization_counts(tenant)
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


def tax_card_payload(client) -> dict:
    """البطاقة بتسميات نظام الزبون — لا بتسميات نظامٍ آخر."""
    card = client.tax_card
    system = resolve_setting(client.tenant, TAX_SYSTEM_KEY, client=client)
    entity_labels = dict(tax_card_choices(system, "entity_type"))
    vat_labels = dict(tax_card_choices(system, "vat_classification"))
    return {
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


# ── دورة حياة الزبون ──────────────────────────────────────────────────────
def create_office_client(
    *, tenant, name, tax_file_number="", notes="", tax_card=None,
) -> OfficeClient:
    """الزبون وبطاقته في كتابةٍ واحدة — بطاقةٌ بلا زبون أو زبونٌ بلا بطاقة عطل.

    **وقبل ذلك: المكتب جاهز؟** زبونٌ يُنشأ قبل اختيار النظام الضريبي وحجم المكتب
    يولد ببطاقةٍ لا اختياراتِ لها، ثم يُفتح ملفُّه على أول تشغيلٍ ناقص. فيُرفض
    الإنشاء حتى يكتمل — والقاعدة نفسها تحرس شاشة القائمة (`first_run_status`).
    """
    if first_run_status(tenant)["first_run_required"]:
        raise ValidationError({
            "detail": "اختر نظام مكتبك الضريبي وحجمه أولاً — من إعدادات المكتب.",
        })
    if not (name or "").strip():
        raise ValidationError({"name": "اسم الزبون مطلوب."})
    card_fields = _clean_tax_card_fields(tenant, None, tax_card or {})
    with transaction.atomic():
        client = OfficeClient.objects.create(
            tenant=tenant,
            name=name.strip(),
            tax_file_number=(tax_file_number or "").strip(),
            notes=notes or "",
        )
        TaxCard.objects.create(client=client, **card_fields)
    return client


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
